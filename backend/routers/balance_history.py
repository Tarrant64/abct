"""
Balance History Router — V2 On-Chain History API

Endpoints for collecting, querying, and managing real on-chain balance history.
"""

import logging
import sys
import os

from fastapi import APIRouter, Query, Depends

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_utils import verify_session
from database import (
    get_latest_balance_history_job,
    get_balance_history_coverage,
)
from services.balance_history import balance_history_service

router = APIRouter(prefix="/balance-history", tags=["balance-history"])
logger = logging.getLogger(__name__)


@router.post("/collect")
async def start_collection(
    user_id: int = Depends(verify_session),
    blockchain: str = Query(None, description="Optional chain filter"),
    max_days: int = Query(730, description="Max days back to collect"),
):
    """Start background balance history collection.

    Returns a job_id that can be polled for progress.
    """
    job_id = await balance_history_service.collect_history(
        user_id=user_id,
        blockchain=blockchain,
        max_days_back=max_days,
    )
    return {"status": "started", "job_id": job_id}


@router.get("/collect/status")
async def collection_status(user_id: int = Depends(verify_session)):
    """Poll the current balance history collection job status."""
    job = await get_latest_balance_history_job(user_id)
    if not job:
        return {"status": "idle", "progress": 0, "step": "No collection started"}

    return {
        "job_id": job['id'],
        "status": job['status'],
        "progress": job.get('progress', 0),
        "step": job.get('step', ''),
        "total_items": job.get('total_items', 0),
        "processed_items": job.get('processed_items', 0),
        "error_message": job.get('error_message'),
    }


@router.post("/collect/cancel")
async def cancel_collection(user_id: int = Depends(verify_session)):
    """Cancel a running balance history collection."""
    await balance_history_service.cancel_collection(user_id)
    return {"status": "cancelled"}


@router.get("/data")
async def get_history_data(
    user_id: int = Depends(verify_session),
    range: str = Query("1y", description="Time range: 3m, 1y, 2y, all, custom"),
    start_date: str = Query(None, description="Start date for custom range (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date for custom range (YYYY-MM-DD)"),
):
    """Get aggregated balance history data for chart rendering.

    Returns daily total values with per-chain breakdown.
    """
    range_to_days = {
        '24h': 1,
        '1w': 7,
        '1m': 30,
        '3m': 90,
        '6m': 180,
        '1y': 365,
        '2y': 730,
    }
    days = range_to_days.get(range)  # None for 'all' and 'custom'

    result = await balance_history_service.get_aggregated_history(
        user_id=user_id,
        days=days,
        start_date=start_date if range == 'custom' else None,
        end_date=end_date if range == 'custom' else None,
    )
    return result


@router.get("/coverage")
async def get_coverage(user_id: int = Depends(verify_session)):
    """Get per-wallet collection coverage info."""
    wallets = await get_balance_history_coverage(user_id)
    return {"wallets": wallets}
