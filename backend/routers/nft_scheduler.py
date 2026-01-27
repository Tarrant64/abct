"""
NFT Background Scheduler API Router

Provides endpoints for controlling and monitoring the NFT background scheduler.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

from services.nft_scheduler import nft_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nft-scheduler", tags=["NFT Scheduler"])


class RegisterCollectionRequest(BaseModel):
    policy_id: str
    name: Optional[str] = None
    priority: int = 0


class RegisterCollectionsBatchRequest(BaseModel):
    collections: List[RegisterCollectionRequest]


@router.get("/status")
async def get_scheduler_status():
    """
    Get detailed NFT scheduler status.

    Returns:
        - enabled: Whether scheduler is enabled
        - running: Whether scheduler is currently running
        - next_run: Next scheduled update time (ISO format)
        - update_interval_minutes: Minutes between updates
        - calls_per_update: Collections updated per cycle
        - api_calls_today: TapTools API calls made today
        - api_calls_remaining: Remaining calls for today
        - collections_total: Total collections being tracked
        - collections_updated_24h: Collections updated in last 24 hours
        - collections_stale: Collections needing update
        - stats: Historical statistics (total_updates, successful_updates, etc.)
    """
    try:
        status = await nft_scheduler.get_status()
        return status
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enable")
async def enable_scheduler():
    """
    Enable the NFT background scheduler.

    This will start the scheduler if it's not already running.
    The scheduler will begin updating NFT floor prices at the configured interval.
    """
    try:
        await nft_scheduler.enable()
        return {
            "success": True,
            "message": "NFT scheduler enabled",
            "status": await nft_scheduler.get_status()
        }
    except Exception as e:
        logger.error(f"Error enabling scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disable")
async def disable_scheduler():
    """
    Disable the NFT background scheduler.

    This will stop the scheduler and prevent future updates.
    Current state is saved and will resume when re-enabled.
    """
    try:
        await nft_scheduler.disable()
        return {
            "success": True,
            "message": "NFT scheduler disabled",
            "status": await nft_scheduler.get_status()
        }
    except Exception as e:
        logger.error(f"Error disabling scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger")
async def trigger_update():
    """
    Manually trigger an NFT floor price update cycle.

    This respects rate limits and will not run if daily limit is reached.
    Useful for testing or forcing an immediate update.
    """
    try:
        # Check if scheduler is enabled
        if not nft_scheduler.enabled:
            raise HTTPException(
                status_code=400,
                detail="Scheduler is disabled. Enable it first."
            )

        # Check rate limits
        calls_today = await nft_scheduler.get_api_calls_today()
        from config import NFT_MAX_DAILY_CALLS

        if calls_today >= NFT_MAX_DAILY_CALLS:
            raise HTTPException(
                status_code=429,
                detail=f"Daily rate limit reached: {calls_today}/{NFT_MAX_DAILY_CALLS} calls"
            )

        # Trigger update in background
        import asyncio
        asyncio.create_task(nft_scheduler.scheduled_update())

        return {
            "success": True,
            "message": "Update triggered",
            "calls_today": calls_today,
            "calls_remaining": NFT_MAX_DAILY_CALLS - calls_today
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register")
async def register_collection(request: RegisterCollectionRequest):
    """
    Register a new NFT collection for tracking.

    Args:
        policy_id: NFT collection policy ID
        name: Optional collection name
        priority: Priority level (higher = updated more frequently)

    Collections with higher priority are updated first.
    Newly registered collections are updated within ~2 hours.
    """
    try:
        await nft_scheduler.register_collection(
            policy_id=request.policy_id,
            name=request.name,
            priority=request.priority
        )

        return {
            "success": True,
            "message": "Collection registered",
            "policy_id": request.policy_id,
            "priority": request.priority
        }

    except Exception as e:
        logger.error(f"Error registering collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-batch")
async def register_collections_batch(request: RegisterCollectionsBatchRequest):
    """
    Register multiple NFT collections at once.

    Useful for bulk importing collections from user NFT holdings.
    """
    try:
        registered = 0
        errors = []

        for collection in request.collections:
            try:
                await nft_scheduler.register_collection(
                    policy_id=collection.policy_id,
                    name=collection.name,
                    priority=collection.priority
                )
                registered += 1
            except Exception as e:
                errors.append({
                    "policy_id": collection.policy_id,
                    "error": str(e)
                })

        return {
            "success": True,
            "registered": registered,
            "total": len(request.collections),
            "errors": errors if errors else None
        }

    except Exception as e:
        logger.error(f"Error registering collections batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections")
async def list_tracked_collections(
    limit: int = 50,
    offset: int = 0,
    stale_only: bool = False
):
    """
    List all collections being tracked by the scheduler.

    Args:
        limit: Maximum number of collections to return
        offset: Number of collections to skip
        stale_only: If true, only return collections needing update

    Returns:
        List of collections with their current floor prices and update status.
    """
    try:
        from database import get_db

        db = await get_db()

        if stale_only:
            query = """
                SELECT * FROM nft_scheduler_collections
                WHERE last_updated IS NULL OR last_updated < datetime('now', '-1 hour')
                ORDER BY priority DESC, last_updated ASC
                LIMIT ? OFFSET ?
            """
        else:
            query = """
                SELECT * FROM nft_scheduler_collections
                ORDER BY priority DESC, last_updated DESC
                LIMIT ? OFFSET ?
            """

        cursor = await db.execute(query, (limit, offset))
        rows = await cursor.fetchall()

        collections = [dict(row) for row in rows]

        # Get total count
        cursor = await db.execute("SELECT COUNT(*) as count FROM nft_scheduler_collections")
        row = await cursor.fetchone()
        total = row["count"] if row else 0

        await db.close()

        return {
            "collections": collections,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))
