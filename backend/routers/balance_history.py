"""
Balance History Router — V2 On-Chain History API

Endpoints for collecting, querying, and managing real on-chain balance history.
Uses the V2 engine pipeline (expand -> index -> hydrate -> normalize -> enrich)
as the primary data source, with V1 balance_history table as fallback.
"""

import logging
import sys
import os
from typing import List

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_utils import verify_session
from database import (
    get_latest_balance_history_job,
    get_balance_history_coverage,
    get_user_setting,
    set_user_setting,
    get_username_by_user_id,
)
from middleware.demo_mode import is_demo_user
from services.balance_history import balance_history_service
from services.demo_data_generator import generate_portfolio_history
from services.logging_service import get_logging_service

router = APIRouter(prefix="/balance-history", tags=["balance-history"])
logger = logging.getLogger(__name__)
log_service = get_logging_service()


@router.post("/collect")
async def start_collection(
    user_id: int = Depends(verify_session),
    blockchain: str = Query(None, description="Optional chain filter"),
    max_days: int = Query(730, description="Max days back to collect"),
    force: bool = Query(False, description="Force full re-collection, ignoring existing data"),
):
    """Start background balance history collection via the V2 engine pipeline.

    Triggers a full engine backfill: expand -> index -> hydrate -> normalize -> enrich.
    Falls back to V1 collection if the engine fails to start.
    """
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"status": "completed", "job_id": -1}

    logger.info(f"Balance history collect requested: user={user_id}, chain={blockchain}, max_days={max_days}, force={force}")
    await log_service.info("balance_history", f"Collection requested via engine: user={user_id}, chain={blockchain or 'all'}, max_days={max_days}")

    # Try V2 engine backfill
    try:
        from engine.orchestrator import backfill_orchestrator
        from engine.models import BackfillRequest, ChainId, WorkDomain
        from engine import db as engine_db

        if blockchain:
            chains = [ChainId(blockchain)]
        else:
            chains = list(ChainId)

        request = BackfillRequest(
            chains=chains,
            domains=[WorkDomain.INDEX, WorkDomain.HYDRATE, WorkDomain.NORMALIZE, WorkDomain.ENRICH_PRICE],
        )

        backfill_id = await backfill_orchestrator.plan_backfill(user_id, request)

        # Create scheduler run record for manual trigger
        run_id = await engine_db.create_scheduler_run(user_id, backfill_id, 'manual')
        backfill_orchestrator.set_run_id(backfill_id, run_id)

        await backfill_orchestrator.run_backfill(backfill_id)

        await log_service.info("balance_history", f"Engine backfill started: id={backfill_id}, run={run_id}")
        return {"status": "started", "job_id": backfill_id}

    except Exception as e:
        logger.warning(f"Engine backfill failed, falling back to V1: {e}")
        await log_service.warning("balance_history", f"Engine backfill failed ({e}), using V1 collector")

        # V1 fallback
        job_id = await balance_history_service.collect_history(
            user_id=user_id,
            blockchain=blockchain,
            max_days_back=max_days,
            force=force,
        )
        return {"status": "started", "job_id": job_id}


@router.post("/collect/wallets")
async def start_wallet_collection(
    user_id: int = Depends(verify_session),
    wallet_ids: List[int] = Query(..., description="Wallet IDs to collect"),
    max_days: int = Query(730),
    force: bool = Query(False),
):
    """Start balance history collection for specific wallets."""
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"status": "completed", "job_id": -1}

    logger.info(f"Balance history collect for wallets requested: user={user_id}, wallets={wallet_ids}")
    await log_service.info("balance_history", f"Wallet-specific collection requested: user={user_id}, wallets={wallet_ids}")

    job_id = await balance_history_service.collect_history(
        user_id=user_id,
        max_days_back=max_days,
        force=force,
        wallet_ids=wallet_ids,
    )
    return {"status": "started", "job_id": job_id}


@router.get("/collect/status")
async def collection_status(user_id: int = Depends(verify_session)):
    """Poll the current balance history collection job status.

    Checks engine backfill status first, falls back to V1 job status.
    """
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"status": "completed", "progress": 100, "step": "Demo data loaded"}

    # Try engine backfill status first
    try:
        from engine import db as engine_db
        backfills = await engine_db.get_user_backfills(user_id)
        if backfills:
            latest = backfills[0]  # Sorted by created_at DESC
            status = latest['status']

            step_map = {
                'planning': 'Planning backfill...',
                'running': 'Processing transactions...',
                'completed': 'Collection complete',
                'failed': 'Collection failed',
                'cancelled': 'Cancelled',
            }

            return {
                "job_id": latest['id'],
                "status": status,
                "progress": latest.get('progress_pct', 0),
                "step": step_map.get(status, status),
                "total_items": latest.get('total_work_units', 0),
                "processed_items": latest.get('completed_work_units', 0),
                "error_message": latest.get('error_message'),
            }
    except Exception as e:
        logger.debug(f"Engine status check failed: {e}")

    # V1 fallback
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
    logger.info(f"Balance history collection cancel requested: user={user_id}")
    await log_service.info("balance_history", f"Collection cancel requested: user={user_id}")

    # Try cancelling engine backfill
    try:
        from engine import db as engine_db
        from engine.orchestrator import backfill_orchestrator
        backfills = await engine_db.get_user_backfills(user_id)
        for bf in backfills:
            if bf['status'] in ('planning', 'running'):
                await backfill_orchestrator.cancel_backfill(bf['id'])
                return {"status": "cancelled"}
    except Exception as e:
        logger.debug(f"Engine cancel failed: {e}")

    # V1 fallback
    await balance_history_service.cancel_collection(user_id)
    return {"status": "cancelled"}


@router.get("/data")
async def get_history_data(
    user_id: int = Depends(verify_session),
    range: str = Query("1y", description="Time range: 24h, 1w, 1m, 3m, 6m, 1y, 2y, all"),
    start_date: str = Query(None, description="Start date for custom range (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date for custom range (YYYY-MM-DD)"),
):
    """Get aggregated balance history data for chart rendering.

    Uses the V2 engine (canonical events + price history) as primary source.
    Falls back to V1 balance_history table if engine has no data.
    """
    # Demo users get pre-generated fake history
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        range_to_days_demo = {
            '24h': 1, '1w': 7, '1m': 30, '3m': 90,
            '6m': 180, '1y': 365, '2y': 730,
        }
        days_back = range_to_days_demo.get(range, 90)
        history = generate_portfolio_history(days=days_back)
        data = []
        for snap in history:
            data.append({
                'date': snap['snapshot_date'],
                'value': snap['total_value_usd'],
                'chains': snap.get('blockchain_breakdown', {}),
            })
        oldest = data[0]['date'] if data else None
        newest = data[-1]['date'] if data else None
        return {
            'data': data,
            'coverage': {
                'oldest_date': oldest,
                'newest_date': newest,
                'total_days': len(data),
            },
        }

    logger.info(f"Balance history data requested: user={user_id}, range={range}")

    # Try V2 engine first
    try:
        from engine import db as engine_db
        from engine.orchestrator import backfill_orchestrator

        event_count = await engine_db.get_event_count(user_id)
        if event_count > 0:
            result = await backfill_orchestrator.get_history_data(user_id, range)
            if result.get('data'):
                logger.info(f"Serving history from engine: {len(result['data'])} data points")
                return result
    except Exception as e:
        logger.warning(f"Engine history failed, falling back to V1: {e}")

    # V1 fallback
    range_to_days = {
        '24h': 1, '1w': 7, '1m': 30, '3m': 90,
        '6m': 180, '1y': 365, '2y': 730,
    }
    days = range_to_days.get(range)  # None for 'all' and 'custom'

    result = await balance_history_service.get_aggregated_history(
        user_id=user_id,
        days=days,
        start_date=start_date if range == 'custom' else None,
        end_date=end_date if range == 'custom' else None,
    )
    return result


@router.post("/backfill-prices")
async def backfill_prices(user_id: int = Depends(verify_session)):
    """Re-fetch prices for records missing price data.

    Uses DefiLlama (free) -> CoinGecko fallback via the engine's price enricher.
    Also backfills prices in V1 balance_history table.
    """
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"status": "completed", "updated": 0}

    logger.info(f"Price backfill requested: user={user_id}")
    await log_service.info("balance_history", f"Price backfill requested: user={user_id}")

    # Engine price enrichment for engine_events
    engine_enriched = 0
    try:
        from engine import db as engine_db
        from engine.enrichment.price_enricher import price_enricher

        event_count = await engine_db.get_event_count(user_id)
        if event_count > 0:
            # Find dates with events but no prices
            events = await engine_db.get_events(user_id, limit=500000)
            dates_by_chain = {}
            for evt in events:
                if evt.get('block_time') and evt.get('asset_id') == 'native':
                    from datetime import datetime
                    dt = datetime.utcfromtimestamp(evt['block_time'])
                    date_str = dt.strftime('%Y-%m-%d')
                    chain = evt['chain']
                    if chain not in dates_by_chain:
                        dates_by_chain[chain] = set()
                    dates_by_chain[chain].add(date_str)

            chain_to_symbol = {
                'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH',
                'solana': 'SOL', 'polygon': 'MATIC', 'base': 'ETH',
            }
            for chain, dates in dates_by_chain.items():
                symbol = chain_to_symbol.get(chain)
                if symbol:
                    prices = await price_enricher.fetch_historical_prices_batch(symbol, sorted(dates))
                    engine_enriched += len(prices)
                    logger.info(f"Engine: enriched {len(prices)} {symbol} prices")
    except Exception as e:
        logger.warning(f"Engine price enrichment failed: {e}")

    # Also backfill V1 balance_history prices
    result = await balance_history_service.backfill_prices(user_id)
    result['engine_enriched'] = engine_enriched
    return result


@router.get("/coverage")
async def get_coverage(user_id: int = Depends(verify_session)):
    """Get per-wallet collection coverage info."""
    logger.info(f"Balance history coverage requested: user={user_id}")

    # Include engine coverage info
    engine_info = {}
    try:
        from engine import db as engine_db
        event_count = await engine_db.get_event_count(user_id)
        engine_info['engine_events'] = event_count
        subjects = await engine_db.get_account_subjects(user_id)
        engine_info['engine_accounts'] = len(subjects)
    except Exception:
        pass

    wallets = await get_balance_history_coverage(user_id)
    return {"wallets": wallets, "engine": engine_info}


# ------------------------------------------------------------------
# Schedule endpoints
# ------------------------------------------------------------------

class ScheduleRequest(BaseModel):
    enabled: bool
    interval_hours: int = 24


@router.get("/schedule")
async def get_schedule(user_id: int = Depends(verify_session)):
    """Get the current balance history auto-collection schedule."""
    enabled = await get_user_setting(user_id, 'balance_history_schedule_enabled', '0')
    interval_hours = await get_user_setting(user_id, 'balance_history_schedule_hours', '0')
    return {
        "enabled": enabled == '1',
        "interval_hours": int(interval_hours),
    }


@router.post("/schedule")
async def set_schedule(
    body: ScheduleRequest,
    user_id: int = Depends(verify_session),
):
    """Set the balance history auto-collection schedule."""
    await set_user_setting(user_id, 'balance_history_schedule_enabled', '1' if body.enabled else '0')
    await set_user_setting(user_id, 'balance_history_schedule_hours', str(body.interval_hours))

    # Use V2 engine scheduler
    try:
        from engine.orchestrator import backfill_orchestrator
        if body.enabled and body.interval_hours > 0:
            await backfill_orchestrator.start_auto_collect(user_id, body.interval_hours)
            await log_service.info("balance_history", f"V2 scheduler started: user={user_id}, interval={body.interval_hours}h")
            logger.info(f"V2 engine scheduler started: user={user_id}, interval={body.interval_hours}h")
        else:
            await backfill_orchestrator.stop_auto_collect(user_id)
            await log_service.info("balance_history", f"V2 scheduler stopped: user={user_id}")
            logger.info(f"V2 engine scheduler stopped: user={user_id}")
    except Exception as e:
        logger.warning(f"V2 scheduler failed, falling back to V1: {e}")
        if body.enabled and body.interval_hours > 0:
            await balance_history_service.start_scheduler(user_id, body.interval_hours)
        else:
            await balance_history_service.stop_scheduler(user_id)

    return {
        "status": "ok",
        "enabled": body.enabled,
        "interval_hours": body.interval_hours,
    }


@router.get("/last-run")
async def get_last_run(user_id: int = Depends(verify_session)):
    """Get the most recent collection run info and next scheduled run time."""
    from datetime import datetime, timedelta

    run = None
    try:
        from engine import db as engine_db
        run = await engine_db.get_latest_scheduler_run(user_id)
    except Exception as e:
        logger.debug(f"Failed to get last run: {e}")

    # Calculate next run from schedule settings + last run time
    next_run = None
    try:
        enabled = await get_user_setting(user_id, 'balance_history_schedule_enabled', '0')
        interval_hours = int(await get_user_setting(user_id, 'balance_history_schedule_hours', '0'))
        if enabled == '1' and interval_hours > 0 and run and run.get('started_at'):
            started = datetime.fromisoformat(run['started_at'])
            next_dt = started + timedelta(hours=interval_hours)
            next_run = next_dt.isoformat()
    except Exception:
        pass

    return {"run": run, "next_run": next_run}
