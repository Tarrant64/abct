"""
System Management Router - Backend and server restart endpoints

Provides endpoints to restart the uvicorn backend process or the entire
Docker container via supervisord signals.
"""

import asyncio
import logging
import os
import signal
import subprocess
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from auth_utils import verify_session

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger(__name__)


class RestartServerRequest(BaseModel):
    confirm: bool


@router.post("/restart-backend")
async def restart_backend(user_id: int = Depends(verify_session)):
    """
    Restart the uvicorn backend process.

    Uses supervisorctl to gracefully restart uvicorn. Falls back to
    sending SIGTERM to the current process if supervisorctl is unavailable.
    The HTTP response is sent before the restart occurs.
    """
    logger.warning(f"Backend restart requested by user {user_id}")

    def do_restart():
        try:
            result = subprocess.run(
                ["supervisorctl", "restart", "uvicorn"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                logger.error(f"supervisorctl restart failed: {result.stderr}")
                os.kill(os.getpid(), signal.SIGTERM)
        except FileNotFoundError:
            logger.warning("supervisorctl not found, falling back to SIGTERM")
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception as e:
            logger.error(f"Restart failed: {e}, falling back to SIGTERM")
            os.kill(os.getpid(), signal.SIGTERM)

    loop = asyncio.get_event_loop()
    loop.call_later(1.0, do_restart)

    return {"status": "restarting", "message": "Backend restarting..."}


@router.post("/restart-server")
async def restart_server(
    request: RestartServerRequest,
    user_id: int = Depends(verify_session)
):
    """
    Restart the entire Docker container.

    Sends SIGTERM to PID 1 (supervisord), which stops all processes.
    Docker's restart policy (restart: unless-stopped) brings the container back up.
    Requires explicit confirmation.
    """
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")

    logger.warning(f"Server restart requested by user {user_id}")

    def do_server_restart():
        try:
            os.kill(1, signal.SIGTERM)
        except Exception as e:
            logger.error(f"Server restart failed: {e}")

    loop = asyncio.get_event_loop()
    loop.call_later(2.0, do_server_restart)

    return {"status": "restarting", "message": "Server rebooting..."}
