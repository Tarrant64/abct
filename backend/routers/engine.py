"""
Engine API Router

Exposes the V2 ingestion engine endpoints.
All endpoints require authentication via verify_session.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from auth_utils import verify_session
from engine.models import BackfillRequest, BackfillStatus
from engine.orchestrator import backfill_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engine", tags=["Engine"])


@router.post("/backfill")
async def start_backfill(request: BackfillRequest,
                         user_id: int = Depends(verify_session)):
    """
    Start a new backfill job.

    Creates a plan, expands wallets into account subjects,
    generates work units, and begins execution.
    """
    try:
        backfill_id = await backfill_orchestrator.plan_backfill(user_id, request)
        # Start execution in background
        await backfill_orchestrator.run_backfill(backfill_id)

        return {
            "backfill_id": backfill_id,
            "status": "running",
            "chains": [c.value for c in request.chains],
            "domains": [d.value for d in request.domains],
        }
    except Exception as e:
        logger.error(f"Backfill start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backfill/{backfill_id}/status")
async def get_backfill_status(backfill_id: int,
                               user_id: int = Depends(verify_session)):
    """Get the current status of a backfill job."""
    status = await backfill_orchestrator.get_status(backfill_id)
    if not status:
        raise HTTPException(status_code=404, detail="Backfill not found")
    return status


@router.post("/backfill/{backfill_id}/cancel")
async def cancel_backfill(backfill_id: int,
                           user_id: int = Depends(verify_session)):
    """Cancel a running backfill job."""
    try:
        await backfill_orchestrator.cancel_backfill(backfill_id)
        return {"status": "cancelled", "backfill_id": backfill_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backfills")
async def list_backfills(user_id: int = Depends(verify_session)):
    """List all backfill jobs for the current user."""
    from engine import db as engine_db
    backfills = await engine_db.get_user_backfills(user_id)
    return {"backfills": backfills}


@router.get("/gaps")
async def get_gaps(user_id: int = Depends(verify_session)):
    """Analyze data coverage gaps across wallets."""
    gaps = await backfill_orchestrator.get_gaps(user_id)
    return {"wallets": gaps}


@router.get("/snapshot")
async def get_snapshot(at_time: Optional[str] = None,
                       user_id: int = Depends(verify_session)):
    """
    Compute portfolio snapshot from canonical events.

    Query params:
        at_time: ISO datetime for historical snapshot (omit for current)
    """
    snapshot = await backfill_orchestrator.compute_snapshot(user_id, at_time)
    return snapshot


@router.get("/history/data")
async def get_history_data(range: str = "1y",
                           user_id: int = Depends(verify_session)):
    """
    Get portfolio history data (backward-compatible with /balance-history/data).

    Same output format as the existing balance history endpoint,
    built from canonical events + price history.
    """
    data = await backfill_orchestrator.get_history_data(user_id, range)
    return data


@router.get("/providers")
async def list_providers(user_id: int = Depends(verify_session)):
    """List all registered providers and their capabilities."""
    if not backfill_orchestrator.registry:
        return {"providers": []}
    return {"providers": backfill_orchestrator.registry.list_providers()}


@router.get("/providers/health")
async def get_provider_health(user_id: int = Depends(verify_session)):
    """Get health status of all providers."""
    if not backfill_orchestrator.scheduler:
        return {"health": {}}
    return {"health": backfill_orchestrator.scheduler.get_health_summary()}


@router.get("/events")
async def get_events(chain: Optional[str] = None,
                     asset_id: Optional[str] = None,
                     limit: int = 100,
                     user_id: int = Depends(verify_session)):
    """Query canonical events with optional filters."""
    from engine import db as engine_db
    events = await engine_db.get_events(
        user_id, chain=chain, asset_id=asset_id, limit=min(limit, 10000)
    )
    return {"events": events, "count": len(events)}


@router.get("/events/count")
async def get_event_count(chain: Optional[str] = None,
                          user_id: int = Depends(verify_session)):
    """Get total event count."""
    from engine import db as engine_db
    count = await engine_db.get_event_count(user_id, chain=chain)
    return {"count": count}
