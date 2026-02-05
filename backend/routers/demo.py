"""
Demo Router - Endpoints for demo account management

Provides endpoints for:
- Checking if demo data is populated
- Triggering demo data population
- Getting population progress
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json
import asyncio
import logging

from auth_utils import verify_session
from middleware.demo_mode import is_demo_user
from services.demo_populator import (
    demo_populator,
    is_demo_populated,
    populate_demo_on_first_login
)

router = APIRouter(prefix="/api/demo", tags=["demo"])
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_demo_status(user_id: int = Depends(verify_session)):
    """
    Check if demo account is populated.

    Returns:
        Dict with populated status
    """
    if not is_demo_user(user_id):
        raise HTTPException(status_code=403, detail="Not a demo account")

    populated = await is_demo_populated(user_id)

    return {
        "is_populated": populated,
        "user_id": user_id
    }


@router.post("/populate")
async def populate_demo(user_id: int = Depends(verify_session)):
    """
    Populate demo account with fake data.

    This endpoint triggers the population process and returns immediately.
    Use /demo/progress to track progress.

    Returns:
        Dict with status
    """
    if not is_demo_user(user_id):
        raise HTTPException(status_code=403, detail="Not a demo account")

    # Check if already populated
    if await is_demo_populated(user_id):
        return {
            "already_populated": True,
            "message": "Demo account already has data"
        }

    # Start population in background
    asyncio.create_task(demo_populator.populate_demo_account(user_id))

    return {
        "started": True,
        "message": "Demo population started"
    }


@router.get("/progress")
async def get_population_progress(user_id: int = Depends(verify_session)):
    """
    Get current progress of demo population.

    Returns:
        Dict with progress percentage and current step
    """
    if not is_demo_user(user_id):
        raise HTTPException(status_code=403, detail="Not a demo account")

    progress = demo_populator.get_progress()

    return {
        "progress": progress["progress"],
        "status": progress["status"],
        "current_step": progress["current_step"]
    }


@router.get("/populate/stream")
async def populate_demo_stream(user_id: int = Depends(verify_session)):
    """
    Populate demo account with real-time progress streaming.

    Returns Server-Sent Events (SSE) stream with progress updates.
    """
    if not is_demo_user(user_id):
        raise HTTPException(status_code=403, detail="Not a demo account")

    # Check if already populated
    if await is_demo_populated(user_id):
        async def already_populated_stream():
            yield f"data: {json.dumps({'progress': 100, 'status': 'completed', 'current_step': 'Already populated'})}\n\n"

        return StreamingResponse(
            already_populated_stream(),
            media_type="text/event-stream"
        )

    async def progress_stream() -> AsyncGenerator[str, None]:
        """Stream progress updates."""
        try:
            # Start population
            progress_updates = []

            def progress_callback(progress: int, status: str):
                progress_updates.append((progress, status))

            # Run population with callback
            result = await demo_populator.populate_demo_account(user_id, progress_callback)

            # Stream all progress updates
            for progress, status in progress_updates:
                data = {
                    "progress": progress,
                    "status": "running",
                    "current_step": status
                }
                yield f"data: {json.dumps(data)}\n\n"
                await asyncio.sleep(0.1)  # Small delay for smooth UI updates

            # Send final completion message
            final_data = {
                "progress": 100,
                "status": "completed",
                "current_step": "Demo account ready!",
                "result": result
            }
            yield f"data: {json.dumps(final_data)}\n\n"

        except Exception as e:
            logger.error(f"Error in progress stream: {e}")
            error_data = {
                "progress": 0,
                "status": "error",
                "current_step": f"Error: {str(e)}"
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/reset")
async def reset_demo_data(user_id: int = Depends(verify_session)):
    """
    Reset demo account data (clear populated flag).

    Allows re-population of demo data.
    This doesn't delete existing data, just clears the flag.
    """
    if not is_demo_user(user_id):
        raise HTTPException(status_code=403, detail="Not a demo account")

    import sqlite3
    from config import DATABASE_PATH

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM user_settings WHERE user_id = ? AND setting_key = 'demo_data_populated'",
            (user_id,)
        )

        conn.commit()
        conn.close()

        return {
            "reset": True,
            "message": "Demo data flag cleared. You can re-populate now."
        }

    except Exception as e:
        logger.error(f"Error resetting demo data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset: {str(e)}")
