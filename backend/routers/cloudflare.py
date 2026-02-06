"""
Cloudflare Tunnel management router.

Provides endpoints to install, configure, start, stop, and remove
cloudflared tunnel service via supervisor (for Docker environments).
Token is stored encrypted in the database.
"""

import asyncio
import logging
import os
import shutil

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from database import get_api_setting, save_api_setting, delete_api_setting
from auth_utils import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cloudflare", tags=["cloudflare"])

SUPERVISOR_CONF = "/etc/supervisor/conf.d/cloudflared.conf"


class SetupRequest(BaseModel):
    token: str


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


async def _get_service_state() -> str:
    """Get cloudflared supervisor state. Returns RUNNING, STOPPED, etc. or empty string."""
    rc, out, _ = await _run_cmd(["supervisorctl", "status", "cloudflared"], ignore_errors=True)
    # Output format: "cloudflared                      RUNNING   pid 123, uptime 0:01:00"
    if out:
        parts = out.split()
        if len(parts) >= 2:
            return parts[1]
    return ""


@router.get("/status")
async def cloudflare_status(user_id: int = Depends(verify_session)):
    """Return installed/running/token-saved status for cloudflared."""
    installed = shutil.which("cloudflared") is not None or os.path.exists("/usr/bin/cloudflared")

    state = ""
    if installed:
        state = await _get_service_state()

    running = state == "RUNNING"

    setting = await get_api_setting("cloudflare_tunnel", user_id=user_id)
    token_saved = bool(setting and setting.get("api_key"))

    return {
        "installed": installed,
        "running": running,
        "token_saved": token_saved,
        "service_state": state or None,
    }


@router.post("/setup")
async def cloudflare_setup(req: SetupRequest, user_id: int = Depends(verify_session)):
    """Save token, install cloudflared, and start via supervisor."""
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    # Save token to DB (encrypted)
    await save_api_setting("cloudflare_tunnel", token, enabled=True, user_id=user_id)
    logger.info("Cloudflare tunnel token saved")

    # Install cloudflared if not present
    if not (shutil.which("cloudflared") or os.path.exists("/usr/bin/cloudflared")):
        logger.info("Installing cloudflared...")

        # Create keyrings directory
        rc, _, err = await _run_cmd(["mkdir", "-p", "--mode=0755", "/usr/share/keyrings"])
        if rc != 0:
            raise HTTPException(status_code=500, detail=f"Failed to create keyrings dir: {err}")

        # Download GPG key
        proc = await asyncio.create_subprocess_shell(
            "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg "
            "> /usr/share/keyrings/cloudflare-main.gpg",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err_bytes = await proc.communicate()
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to download GPG key: {err_bytes.decode()}")

        # Add apt repository
        repo_line = (
            "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] "
            "https://pkg.cloudflare.com/cloudflared any main"
        )
        try:
            with open("/etc/apt/sources.list.d/cloudflared.list", "w") as f:
                f.write(repo_line + "\n")
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to write apt source: {e}")

        # Install
        rc, _, err = await _run_cmd(["apt-get", "update", "-qq"])
        if rc != 0:
            raise HTTPException(status_code=500, detail=f"apt-get update failed: {err}")

        rc, _, err = await _run_cmd(["apt-get", "install", "-y", "-qq", "cloudflared"])
        if rc != 0:
            raise HTTPException(status_code=500, detail=f"apt-get install cloudflared failed: {err}")

        logger.info("cloudflared installed successfully")

    # Write supervisor config
    supervisor_conf = (
        "[program:cloudflared]\n"
        f"command=/usr/bin/cloudflared tunnel run --token {token}\n"
        "autostart=true\n"
        "autorestart=true\n"
        "priority=30\n"
        "stdout_logfile=/dev/stdout\n"
        "stdout_logfile_maxbytes=0\n"
        "stderr_logfile=/dev/stderr\n"
        "stderr_logfile_maxbytes=0\n"
    )
    try:
        with open(SUPERVISOR_CONF, "w") as f:
            f.write(supervisor_conf)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write supervisor config: {e}")

    # Start via supervisor
    await _run_cmd(["supervisorctl", "reread"], ignore_errors=True)
    await _run_cmd(["supervisorctl", "update"], ignore_errors=True)

    # Brief pause then check status
    await asyncio.sleep(2)
    state = await _get_service_state()

    logger.info(f"cloudflared service state: {state}")
    return {
        "success": True,
        "message": "Cloudflare tunnel installed and started",
        "running": state == "RUNNING",
        "service_state": state or None,
    }


@router.post("/stop")
async def cloudflare_stop(user_id: int = Depends(verify_session)):
    """Stop cloudflared service."""
    rc, _, err = await _run_cmd(["supervisorctl", "stop", "cloudflared"], ignore_errors=True)
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

    if not os.path.exists(SUPERVISOR_CONF):
        raise HTTPException(status_code=400, detail="Supervisor config missing. Run setup first.")

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
    # Stop service
    await _run_cmd(["supervisorctl", "stop", "cloudflared"], ignore_errors=True)

    # Remove supervisor config
    try:
        if os.path.exists(SUPERVISOR_CONF):
            os.remove(SUPERVISOR_CONF)
    except OSError:
        pass

    # Update supervisor to remove the program
    await _run_cmd(["supervisorctl", "reread"], ignore_errors=True)
    await _run_cmd(["supervisorctl", "update"], ignore_errors=True)

    # Uninstall cloudflared
    await _run_cmd(["apt-get", "remove", "-y", "-qq", "cloudflared"], ignore_errors=True)

    # Delete token from DB
    await delete_api_setting("cloudflare_tunnel", user_id=user_id)

    logger.info("Cloudflare tunnel fully removed")
    return {
        "success": True,
        "message": "Cloudflare tunnel removed and token deleted",
    }
