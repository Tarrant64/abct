"""
Cloudflare Tunnel management router.

Provides endpoints to install, configure, start, stop, and remove
cloudflared tunnel service via supervisor (for Docker environments).
Token is stored encrypted in the database.

Install runs as a background task to avoid HTTP timeouts. The frontend
polls GET /cloudflare/status for progress updates.

Supervisor integration:
  The [program:cloudflared] section is written directly into the main
  supervisord.conf (not a separate include file) because supervisor
  only evaluates [include] directives at initial startup. We also add
  [unix_http_server], [rpcinterface:supervisor], and [supervisorctl]
  sections so supervisorctl can manage processes at runtime.
"""

import asyncio
import logging
import os
import re
import signal
import shutil

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import get_api_setting, save_api_setting, delete_api_setting
from auth_utils import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cloudflare", tags=["cloudflare"])

SUPERVISORD_CONF = "/etc/supervisor/conf.d/supervisord.conf"
SUPERVISOR_SOCK = "/var/run/supervisor.sock"

# Marker comments to find our managed section
CF_SECTION_START = "# --- cloudflared managed section ---"
CF_SECTION_END = "# --- end cloudflared managed section ---"

# Module-level install progress (shared across requests)
_install_progress = {
    "active": False,
    "step": "",
    "error": None,
}


class SetupRequest(BaseModel):
    token: str


def _set_progress(step: str, error: str = None):
    """Update the install progress state."""
    _install_progress["step"] = step
    _install_progress["error"] = error
    if error:
        _install_progress["active"] = False
    logger.info(f"Cloudflare install: {step}" + (f" ERROR: {error}" if error else ""))


async def _run_cmd(cmd: list[str], ignore_errors: bool = False) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    err = stderr.decode().strip()
    if proc.returncode != 0 and not ignore_errors:
        logger.warning(f"Command {cmd} failed ({proc.returncode}): {err}")
    return proc.returncode, out, err


def _ensure_supervisor_ctl():
    """Ensure supervisord.conf has the sections needed for supervisorctl.

    Adds [unix_http_server], [rpcinterface:supervisor], and [supervisorctl]
    if missing, then sends SIGHUP to reload.
    """
    if not os.path.exists(SUPERVISORD_CONF):
        logger.warning(f"supervisord.conf not found at {SUPERVISORD_CONF}")
        return False

    try:
        with open(SUPERVISORD_CONF, "r") as f:
            content = f.read()
    except OSError:
        return False

    modified = False

    if "[unix_http_server]" not in content:
        content += f"\n[unix_http_server]\nfile={SUPERVISOR_SOCK}\n"
        modified = True

    if "[rpcinterface:supervisor]" not in content:
        content += (
            "\n[rpcinterface:supervisor]\n"
            "supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface\n"
        )
        modified = True

    if "[supervisorctl]" not in content:
        content += f"\n[supervisorctl]\nserverurl=unix://{SUPERVISOR_SOCK}\n"
        modified = True

    if modified:
        try:
            with open(SUPERVISORD_CONF, "w") as f:
                f.write(content)
            logger.info("Patched supervisord.conf with ctl sections")
        except OSError as e:
            logger.error(f"Failed to patch supervisord.conf: {e}")
            return False

        _sighup_supervisor()

    return True


def _sighup_supervisor():
    """Send SIGHUP to PID 1 (supervisord) to reload config."""
    try:
        os.kill(1, signal.SIGHUP)
        logger.info("Sent SIGHUP to supervisord (PID 1)")
    except OSError as e:
        logger.error(f"Failed to send SIGHUP: {e}")


def _write_cloudflared_program(token: str):
    """Write [program:cloudflared] directly into supervisord.conf."""
    if not os.path.exists(SUPERVISORD_CONF):
        return False

    try:
        with open(SUPERVISORD_CONF, "r") as f:
            content = f.read()
    except OSError:
        return False

    # Remove any existing cloudflared section first
    content = _remove_cloudflared_section(content)

    # Append the new program section
    program_block = (
        f"\n{CF_SECTION_START}\n"
        "[program:cloudflared]\n"
        f"command=/usr/bin/cloudflared tunnel run --token {token}\n"
        "autostart=true\n"
        "autorestart=true\n"
        "priority=30\n"
        "stdout_logfile=/dev/stdout\n"
        "stdout_logfile_maxbytes=0\n"
        "stderr_logfile=/dev/stderr\n"
        "stderr_logfile_maxbytes=0\n"
        f"{CF_SECTION_END}\n"
    )
    content += program_block

    try:
        with open(SUPERVISORD_CONF, "w") as f:
            f.write(content)
        logger.info("Wrote [program:cloudflared] into supervisord.conf")
        return True
    except OSError as e:
        logger.error(f"Failed to write supervisord.conf: {e}")
        return False


def _remove_cloudflared_section(content: str) -> str:
    """Remove the cloudflared managed section from supervisord.conf content."""
    # Remove between markers
    pattern = re.escape(CF_SECTION_START) + r".*?" + re.escape(CF_SECTION_END) + r"\n?"
    content = re.sub(pattern, "", content, flags=re.DOTALL)
    # Also remove any standalone [program:cloudflared] section without markers
    content = re.sub(
        r"\[program:cloudflared\].*?(?=\n\[|\Z)",
        "",
        content,
        flags=re.DOTALL,
    )
    return content.rstrip() + "\n"


def _remove_cloudflared_from_conf():
    """Remove cloudflared program from supervisord.conf."""
    if not os.path.exists(SUPERVISORD_CONF):
        return

    try:
        with open(SUPERVISORD_CONF, "r") as f:
            content = f.read()
    except OSError:
        return

    content = _remove_cloudflared_section(content)

    try:
        with open(SUPERVISORD_CONF, "w") as f:
            f.write(content)
        logger.info("Removed [program:cloudflared] from supervisord.conf")
    except OSError as e:
        logger.error(f"Failed to update supervisord.conf: {e}")


async def _get_service_state() -> str:
    """Get cloudflared supervisor state. Returns RUNNING, STOPPED, etc. or empty string."""
    rc, out, _ = await _run_cmd(["supervisorctl", "status", "cloudflared"], ignore_errors=True)
    if out and "RUNNING" in out:
        return "RUNNING"
    if out and "STOPPED" in out:
        return "STOPPED"
    if out and "STARTING" in out:
        return "STARTING"
    if out and "FATAL" in out:
        return "FATAL"
    if out and "ERROR" in out:
        return "ERROR"
    return ""


async def _install_cloudflared_background(token: str, user_id: int):
    """Background task: install cloudflared and start via supervisor."""
    try:
        _install_progress["active"] = True

        # Step 1: Save token
        _set_progress("Saving tunnel token...")
        await save_api_setting("cloudflare_tunnel", token, enabled=True, user_id=user_id)

        # Step 2: Ensure supervisorctl works
        _set_progress("Configuring process manager...")
        _ensure_supervisor_ctl()
        await asyncio.sleep(2)

        # Step 3: Check if already installed
        if shutil.which("cloudflared") or os.path.exists("/usr/bin/cloudflared"):
            _set_progress("cloudflared already installed, configuring...")
        else:
            # Step 4: Add GPG key
            _set_progress("Adding Cloudflare GPG key...")
            rc, _, err = await _run_cmd(["mkdir", "-p", "--mode=0755", "/usr/share/keyrings"])
            if rc != 0:
                _set_progress("Failed", error=f"Could not create keyrings dir: {err}")
                return

            proc = await asyncio.create_subprocess_shell(
                "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg "
                "> /usr/share/keyrings/cloudflare-main.gpg",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err_bytes = await proc.communicate()
            if proc.returncode != 0:
                _set_progress("Failed", error=f"Could not download GPG key: {err_bytes.decode()}")
                return

            # Step 5: Add apt repository
            _set_progress("Adding Cloudflare apt repository...")
            repo_line = (
                "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] "
                "https://pkg.cloudflare.com/cloudflared any main"
            )
            try:
                with open("/etc/apt/sources.list.d/cloudflared.list", "w") as f:
                    f.write(repo_line + "\n")
            except OSError as e:
                _set_progress("Failed", error=f"Could not write apt source: {e}")
                return

            # Step 6: apt-get update (only cloudflared repo for speed)
            _set_progress("Updating package lists...")
            rc, _, err = await _run_cmd([
                "apt-get", "update",
                "-o", "Dir::Etc::sourcelist=sources.list.d/cloudflared.list",
                "-o", "Dir::Etc::sourceparts=-",
                "-o", "APT::Get::List-Cleanup=0",
                "-qq",
            ])
            if rc != 0:
                _set_progress("Updating all package lists (fallback)...")
                rc, _, err = await _run_cmd(["apt-get", "update", "-qq"])
                if rc != 0:
                    _set_progress("Failed", error=f"apt-get update failed: {err}")
                    return

            # Step 7: Install
            _set_progress("Installing cloudflared package...")
            rc, _, err = await _run_cmd(["apt-get", "install", "-y", "-qq", "cloudflared"])
            if rc != 0:
                _set_progress("Failed", error=f"apt-get install failed: {err}")
                return

        # Step 8: Write [program:cloudflared] into supervisord.conf
        _set_progress("Registering tunnel service...")
        if not _write_cloudflared_program(token):
            _set_progress("Failed", error="Could not write supervisor program config")
            return

        # Step 9: Reload supervisor and start the program
        _set_progress("Starting Cloudflare tunnel...")
        _sighup_supervisor()
        await asyncio.sleep(2)
        await _run_cmd(["supervisorctl", "reread"], ignore_errors=True)
        await _run_cmd(["supervisorctl", "update"], ignore_errors=True)

        # Wait for the service to come up
        await asyncio.sleep(3)
        state = await _get_service_state()

        if state == "RUNNING":
            _set_progress("Tunnel is running")
        elif state == "STARTING":
            await asyncio.sleep(5)
            state = await _get_service_state()
            _set_progress("Tunnel is running" if state == "RUNNING" else f"Service state: {state or 'unknown'}")
        else:
            _set_progress(f"Service state: {state or 'unknown'}")

    except Exception as e:
        _set_progress("Failed", error=str(e))
    finally:
        _install_progress["active"] = False


@router.get("/status")
async def cloudflare_status(user_id: int = Depends(verify_session)):
    """Return installed/running/token-saved status and install progress."""
    installed = shutil.which("cloudflared") is not None or os.path.exists("/usr/bin/cloudflared")

    state = ""
    if installed:
        state = await _get_service_state()

    running = state == "RUNNING"

    setting = await get_api_setting("cloudflare_tunnel", user_id=user_id)
    token_saved = bool(setting and setting.get("api_key"))

    result = {
        "installed": installed,
        "running": running,
        "token_saved": token_saved,
        "service_state": state or None,
    }

    # Include install progress if active or recently completed
    if _install_progress["active"] or _install_progress["step"]:
        result["install_progress"] = {
            "active": _install_progress["active"],
            "step": _install_progress["step"],
            "error": _install_progress["error"],
        }

    return result


@router.post("/setup")
async def cloudflare_setup(req: SetupRequest, user_id: int = Depends(verify_session)):
    """Save token and kick off background install. Returns immediately."""
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    if _install_progress["active"]:
        raise HTTPException(status_code=409, detail="Installation already in progress")

    # Reset progress and start background task
    _install_progress["step"] = ""
    _install_progress["error"] = None
    _install_progress["active"] = True

    asyncio.create_task(_install_cloudflared_background(token, user_id))

    return {
        "success": True,
        "message": "Installation started. Poll /cloudflare/status for progress.",
    }


@router.post("/stop")
async def cloudflare_stop(user_id: int = Depends(verify_session)):
    """Stop cloudflared service."""
    _ensure_supervisor_ctl()
    await _run_cmd(["supervisorctl", "stop", "cloudflared"], ignore_errors=True)
    state = await _get_service_state()

    return {
        "success": True,
        "message": "Cloudflare tunnel stopped",
        "running": state == "RUNNING",
        "service_state": state or None,
    }


@router.post("/start")
async def cloudflare_start(user_id: int = Depends(verify_session)):
    """Start cloudflared service (must be installed with token configured)."""
    if not (shutil.which("cloudflared") or os.path.exists("/usr/bin/cloudflared")):
        raise HTTPException(status_code=400, detail="cloudflared is not installed. Run setup first.")

    _ensure_supervisor_ctl()
    await _run_cmd(["supervisorctl", "start", "cloudflared"], ignore_errors=True)
    await asyncio.sleep(1)
    state = await _get_service_state()

    return {
        "success": True,
        "message": "Cloudflare tunnel started",
        "running": state == "RUNNING",
        "service_state": state or None,
    }


@router.delete("/remove")
async def cloudflare_remove(user_id: int = Depends(verify_session)):
    """Stop, uninstall cloudflared, remove config, and delete token."""
    _ensure_supervisor_ctl()

    # Stop service
    await _run_cmd(["supervisorctl", "stop", "cloudflared"], ignore_errors=True)

    # Remove cloudflared from supervisord.conf
    _remove_cloudflared_from_conf()
    _sighup_supervisor()
    await asyncio.sleep(1)
    await _run_cmd(["supervisorctl", "reread"], ignore_errors=True)
    await _run_cmd(["supervisorctl", "update"], ignore_errors=True)

    # Also remove the old separate conf file if it exists
    try:
        old_conf = "/etc/supervisor/conf.d/cloudflared.conf"
        if os.path.exists(old_conf):
            os.remove(old_conf)
    except OSError:
        pass

    # Uninstall cloudflared
    await _run_cmd(["apt-get", "remove", "-y", "-qq", "cloudflared"], ignore_errors=True)

    # Delete token from DB
    await delete_api_setting("cloudflare_tunnel", user_id=user_id)

    # Clear any leftover progress
    _install_progress["active"] = False
    _install_progress["step"] = ""
    _install_progress["error"] = None

    logger.info("Cloudflare tunnel fully removed")
    return {
        "success": True,
        "message": "Cloudflare tunnel removed and token deleted",
    }


async def auto_restore_tunnel():
    """Restore Cloudflare tunnel on startup if a token is saved in the DB.

    Called from main.py lifespan. If cloudflared isn't installed, installs it
    via apt, writes the supervisor program config, and starts the service.
    If already installed, just ensures it's running.

    This preserves tunnel connectivity across Docker container rebuilds since
    the token lives in the SQLite database on a persistent volume.
    """
    from database import get_all_users

    # Find any user with a saved cloudflare tunnel token
    users = await get_all_users()
    token = None
    for user in users:
        setting = await get_api_setting("cloudflare_tunnel", user_id=user['id'])
        if setting and setting.get("api_key"):
            token = setting["api_key"]
            break

    if not token:
        logger.debug("Cloudflare auto-restore: no tunnel token found, skipping")
        return

    logger.info("Cloudflare auto-restore: tunnel token found, checking status...")

    # Ensure supervisorctl sections exist
    _ensure_supervisor_ctl()

    # If cloudflared is already running under supervisor, nothing to do.
    # This prevents a restart loop: SIGHUP restarts all supervisor processes
    # (including uvicorn), which triggers auto_restore_tunnel again.
    current_state = await _get_service_state()
    if current_state == "RUNNING":
        logger.info("Cloudflare auto-restore: tunnel already running, skipping")
        return

    installed = shutil.which("cloudflared") is not None or os.path.exists("/usr/bin/cloudflared")

    if not installed:
        logger.info("Cloudflare auto-restore: cloudflared not installed, installing...")

        # Install GPG key
        rc, _, err = await _run_cmd(["mkdir", "-p", "--mode=0755", "/usr/share/keyrings"])
        if rc != 0:
            logger.warning(f"Cloudflare auto-restore: failed to create keyrings dir: {err}")
            return

        proc = await asyncio.create_subprocess_shell(
            "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg "
            "> /usr/share/keyrings/cloudflare-main.gpg",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err_bytes = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(f"Cloudflare auto-restore: GPG key download failed: {err_bytes.decode()}")
            return

        # Add apt repo
        repo_line = (
            "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] "
            "https://pkg.cloudflare.com/cloudflared any main"
        )
        try:
            with open("/etc/apt/sources.list.d/cloudflared.list", "w") as f:
                f.write(repo_line + "\n")
        except OSError as e:
            logger.warning(f"Cloudflare auto-restore: could not write apt source: {e}")
            return

        # apt-get update (cloudflared repo only for speed)
        rc, _, err = await _run_cmd([
            "apt-get", "update",
            "-o", "Dir::Etc::sourcelist=sources.list.d/cloudflared.list",
            "-o", "Dir::Etc::sourceparts=-",
            "-o", "APT::Get::List-Cleanup=0",
            "-qq",
        ])
        if rc != 0:
            rc, _, err = await _run_cmd(["apt-get", "update", "-qq"])
            if rc != 0:
                logger.warning(f"Cloudflare auto-restore: apt-get update failed: {err}")
                return

        # Install
        rc, _, err = await _run_cmd(["apt-get", "install", "-y", "-qq", "cloudflared"])
        if rc != 0:
            logger.warning(f"Cloudflare auto-restore: apt-get install failed: {err}")
            return

        logger.info("Cloudflare auto-restore: cloudflared installed successfully")

    # Write supervisor program config and start
    if not _write_cloudflared_program(token):
        logger.warning("Cloudflare auto-restore: could not write supervisor config")
        return

    _sighup_supervisor()
    await asyncio.sleep(2)
    await _run_cmd(["supervisorctl", "reread"], ignore_errors=True)
    await _run_cmd(["supervisorctl", "update"], ignore_errors=True)

    await asyncio.sleep(3)
    state = await _get_service_state()
    if state == "RUNNING":
        logger.info("Cloudflare auto-restore: tunnel is running")
    else:
        logger.warning(f"Cloudflare auto-restore: service state is {state or 'unknown'}")
