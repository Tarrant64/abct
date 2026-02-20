"""
Logs Router - Centralized Logging Endpoints

Provides endpoints for viewing and managing application logs:
- GET /logs - List recent logs with filtering and pagination
- GET /logs/recent - Get recent in-memory logs
- GET /logs/stream - Server-Sent Events endpoint for real-time logs
- GET /logs/stats - Get logging statistics
- DELETE /logs - Clear logs (requires confirmation)
"""

import sys
import os
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.logging_service import get_logging_service, LogLevel
from auth_utils import verify_session

router = APIRouter(prefix="/logs", tags=["logs"])


class ClearLogsRequest(BaseModel):
    """Request model for clearing logs."""
    confirm: bool
    older_than_days: Optional[int] = None


@router.get("")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    level: Optional[str] = Query(None, description="Filter by log level (ERROR, WARNING, INFO, DEBUG)"),
    source: Optional[str] = Query(None, description="Filter by source component"),
    start_time: Optional[str] = Query(None, description="Filter by start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="Filter by end time (ISO format)"),
    user_id: int = Depends(verify_session)
):
    """
    Get logs from database with filtering and pagination.

    Returns logs in reverse chronological order (newest first).
    """
    logger = get_logging_service()

    # Parse log level
    log_level = None
    if level:
        try:
            log_level = LogLevel(level.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid log level. Must be one of: ERROR, WARNING, INFO, DEBUG"
            )

    # Parse timestamps
    start_dt = None
    end_dt = None
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format")
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_time format")

    result = await logger.get_from_db(
        limit=limit,
        offset=offset,
        level=log_level,
        source=source,
        start_time=start_dt,
        end_time=end_dt
    )

    return result


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to return"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    source: Optional[str] = Query(None, description="Filter by source component"),
    user_id: int = Depends(verify_session)
):
    """
    Get recent logs from in-memory buffer.

    This is faster than querying the database and includes all log levels.
    """
    logger = get_logging_service()

    # Parse log level
    log_level = None
    if level:
        try:
            log_level = LogLevel(level.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid log level. Must be one of: ERROR, WARNING, INFO, DEBUG"
            )

    logs = await logger.get_recent(
        limit=limit,
        level=log_level,
        source=source
    )

    return {
        "logs": logs,
        "total": len(logs),
        "source": "memory"
    }


@router.get("/stream")
async def stream_logs(request: Request, user_id: int = Depends(verify_session)):
    """
    Server-Sent Events endpoint for real-time log streaming.

    Streams new log entries as they are created. Clients should use EventSource
    to connect to this endpoint.

    Example client:
        const eventSource = new EventSource('/logs/stream');
        eventSource.onmessage = (event) => {
            const log = JSON.parse(event.data);
            console.log(log);
        };
    """
    logger = get_logging_service()

    async def event_generator():
        """Generate SSE events from log stream."""
        queue = await logger.subscribe()

        try:
            # Send initial connection message
            yield f"data: {{'event': 'connected', 'timestamp': '{datetime.utcnow().isoformat()}'}}\n\n"

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for new log entry (with timeout)
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Format as SSE
                    import json
                    data = json.dumps(entry.to_dict())
                    yield f"data: {data}\n\n"

                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield f"data: {{'event': 'ping', 'timestamp': '{datetime.utcnow().isoformat()}'}}\n\n"

        finally:
            await logger.unsubscribe(queue)

    import asyncio
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


@router.get("/stats")
async def get_log_stats(user_id: int = Depends(verify_session)):
    """
    Get logging statistics.

    Returns information about log counts, distribution by level/source,
    and active subscribers.
    """
    logger = get_logging_service()
    stats = await logger.get_stats()

    return {
        "status": "ok",
        "stats": stats
    }


@router.delete("")
async def clear_logs(data: ClearLogsRequest, user_id: int = Depends(verify_session)):
    """
    Clear logs from database and/or buffer.

    Requires confirmation flag to prevent accidental deletion.
    Can optionally clear only logs older than specified days.

    Args:
        confirm: Must be true to proceed
        older_than_days: If provided, only clear logs older than this many days
    """
    if not data.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm deletion by setting 'confirm' to true"
        )

    logger = get_logging_service()

    # Clear database
    await logger.clear_db(older_than_days=data.older_than_days)

    # Clear buffer if no date filter
    if not data.older_than_days:
        await logger.clear_buffer()

    message = "All logs cleared"
    if data.older_than_days:
        message = f"Logs older than {data.older_than_days} days cleared"

    return {
        "status": "ok",
        "message": message
    }


@router.post("/test")
async def create_test_log(
    level: str = Query("INFO", description="Log level to test"),
    message: str = Query("Test log message", description="Message to log"),
    user_id: int = Depends(verify_session)
):
    """
    Create a test log entry.

    Useful for testing the logging system.
    """
    logger = get_logging_service()

    try:
        log_level = LogLevel(level.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid log level. Must be one of: ERROR, WARNING, INFO, DEBUG"
        )

    await logger.log(
        level=log_level,
        source="test",
        message=message,
        test=True
    )

    return {
        "status": "ok",
        "message": "Test log created",
        "level": log_level.value,
        "log_message": message
    }
