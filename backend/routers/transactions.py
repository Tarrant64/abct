"""
Transaction History Router - API endpoints for consolidated transaction history
"""

from fastapi import APIRouter, Query, Depends, HTTPException, BackgroundTasks
from typing import Optional, Dict, List
import logging
import asyncio
import aiosqlite
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.transaction_history import transaction_history_service
from auth_utils import verify_session
from middleware.demo_mode import (
    is_demo_user,
    get_demo_transactions,
    get_demo_transaction_stats,
    get_demo_transaction_analytics
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])

# Background task tracking
background_tasks: Dict[int, Dict] = {}  # user_id -> task info


@router.get("")
async def get_transaction_history(
    user_id: int = Depends(verify_session),
    days: int = Query(7, ge=1, le=100000, description="Number of days to look back"),
    blockchain: Optional[str] = Query(None, description="Filter by blockchain"),
    direction: Optional[str] = Query(None, description="Filter by direction (sent/received)"),
    search: Optional[str] = Query(None, description="Search in tx hash, addresses, tokens"),
    refresh: bool = Query(False, description="Fetch fresh data from blockchain APIs")
):
    """
    Get transaction history with optional filters.

    Args:
        user_id: Authenticated user ID (from session)
        days: Number of days of history (1-90)
        blockchain: Filter by specific blockchain
        direction: Filter by sent or received
        search: Text search across transaction details
        refresh: If True, fetch fresh data from blockchains

    Returns:
        Transaction list with filters applied
    """
    try:
        # Check if demo user
        from database import get_username_by_user_id
        username = await get_username_by_user_id(user_id)
        if await is_demo_user(username):
            logger.info(f"Demo mode: Returning demo transactions for user {user_id}")
            return await get_demo_transactions(user_id, days, blockchain, direction, search)
        if refresh:
            # Fetch fresh data from blockchain APIs
            logger.info(f"Refreshing transaction history for user {user_id} ({days} days)")
            counts = await transaction_history_service.fetch_transactions(
                user_id, days, blockchain
            )
            logger.info(f"Fetched transactions: {counts}")

        # Get from database with filters
        transactions = await transaction_history_service.get_transactions(
            user_id, days, blockchain, direction, search
        )

        # Format timestamps for frontend (convert datetime to string for JSON)
        for tx in transactions:
            if tx.get('tx_time'):
                tx_time = tx['tx_time']
                if isinstance(tx_time, str):
                    tx['tx_time_formatted'] = tx_time
                else:
                    tx['tx_time_formatted'] = tx_time.isoformat() if hasattr(tx_time, 'isoformat') else str(tx_time)
                    tx['tx_time'] = tx['tx_time_formatted']

            # Convert any other datetime fields
            if tx.get('fetched_at'):
                fetched = tx['fetched_at']
                if not isinstance(fetched, str):
                    tx['fetched_at'] = fetched.isoformat() if hasattr(fetched, 'isoformat') else str(fetched)

        return {
            'success': True,
            'transactions': transactions,
            'total_count': len(transactions),
            'days': days,
            'filters': {
                'blockchain': blockchain,
                'direction': direction,
                'search': search
            }
        }

    except Exception as e:
        logger.error(f"Error getting transaction history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _background_fetch_task(user_id: int, days: int, blockchain: Optional[str], wallet_ids: List[int] = None):
    """Background task to fetch transactions"""
    try:
        background_tasks[user_id]['status'] = 'running'
        background_tasks[user_id]['message'] = 'Fetching transactions from blockchains...'

        logger.info(f"Background fetch started for user {user_id}, days={days}, blockchain={blockchain}, wallet_ids={wallet_ids}")

        counts = await transaction_history_service.fetch_transactions(
            user_id, days, blockchain, wallet_ids=wallet_ids
        )

        total = sum(counts.values())
        background_tasks[user_id]['status'] = 'completed'
        background_tasks[user_id]['message'] = f'Fetched {total} transactions'
        background_tasks[user_id]['counts'] = counts
        background_tasks[user_id]['total_fetched'] = total
        background_tasks[user_id]['completed_at'] = datetime.now().isoformat()

        logger.info(f"Background fetch completed for user {user_id}: {counts}")

    except Exception as e:
        logger.error(f"Background fetch failed for user {user_id}: {e}")
        background_tasks[user_id]['status'] = 'failed'
        background_tasks[user_id]['message'] = f'Error: {str(e)}'
        background_tasks[user_id]['error'] = str(e)


@router.post("/refresh/start")
async def start_background_refresh(
    background_tasks_runner: BackgroundTasks,
    user_id: int = Depends(verify_session),
    days: int = Query(7, ge=1, le=100000, description="Number of days to fetch"),
    blockchain: Optional[str] = Query(None, description="Fetch for specific blockchain only")
):
    """
    Start background transaction fetch task.
    Returns immediately while fetch continues in background.

    Args:
        user_id: Authenticated user ID (from session)
        days: Number of days of history to fetch
        blockchain: Optionally fetch only for specific blockchain

    Returns:
        Task ID and initial status
    """
    # Check if already running
    if user_id in background_tasks and background_tasks[user_id]['status'] == 'running':
        return {
            'success': False,
            'message': 'Transaction fetch already in progress',
            'task_id': user_id
        }

    # Initialize task
    background_tasks[user_id] = {
        'task_id': user_id,
        'status': 'starting',
        'message': 'Starting transaction fetch...',
        'started_at': datetime.now().isoformat(),
        'days': days,
        'blockchain': blockchain
    }

    # Start background task
    background_tasks_runner.add_task(_background_fetch_task, user_id, days, blockchain)

    return {
        'success': True,
        'message': 'Transaction fetch started',
        'task_id': user_id
    }


@router.get("/refresh/status")
async def get_refresh_status(
    user_id: int = Depends(verify_session)
):
    """
    Get status of background transaction fetch task.

    Returns:
        Current status of fetch task
    """
    if user_id not in background_tasks:
        return {
            'success': True,
            'status': 'none',
            'message': 'No fetch task running'
        }

    task = background_tasks[user_id]

    return {
        'success': True,
        **task
    }


@router.post("/refresh")
async def refresh_transaction_history(
    user_id: int = Depends(verify_session),
    days: int = Query(7, ge=1, le=100000, description="Number of days to fetch"),
    blockchain: Optional[str] = Query(None, description="Fetch for specific blockchain only")
):
    """
    Fetch fresh transaction data from blockchains (blocking).

    DEPRECATED: Use /refresh/start for background fetching instead.

    This endpoint explicitly refreshes transaction data from blockchain APIs.
    Use this when you want to force a refresh without immediately viewing results.

    Args:
        user_id: Authenticated user ID (from session)
        days: Number of days of history to fetch
        blockchain: Optionally fetch only for specific blockchain

    Returns:
        Status and counts of fetched transactions
    """
    try:
        logger.info(f"Refreshing transactions for user {user_id}, days={days}, blockchain={blockchain}")

        counts = await transaction_history_service.fetch_transactions(
            user_id, days, blockchain
        )

        return {
            'success': True,
            'message': 'Transaction history refreshed',
            'counts': counts,
            'total_fetched': sum(counts.values())
        }

    except Exception as e:
        logger.error(f"Error refreshing transaction history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh/wallets")
async def start_wallet_refresh(
    background_tasks_runner: BackgroundTasks,
    user_id: int = Depends(verify_session),
    wallet_ids: List[int] = Query(..., description="Wallet IDs to fetch"),
    days: int = Query(30, ge=1, le=100000),
):
    """Start background transaction fetch for specific wallets."""
    if user_id in background_tasks and background_tasks[user_id].get('status') == 'running':
        return {'success': False, 'message': 'Transaction fetch already in progress', 'task_id': user_id}

    background_tasks[user_id] = {
        'task_id': user_id,
        'status': 'starting',
        'message': 'Starting transaction fetch...',
        'started_at': datetime.now().isoformat(),
        'days': days,
        'wallet_ids': wallet_ids,
    }
    background_tasks_runner.add_task(_background_fetch_task, user_id, days, None, wallet_ids)
    return {'success': True, 'message': 'Transaction fetch started', 'task_id': user_id}


@router.get("/last-run")
async def get_tx_last_run(user_id: int = Depends(verify_session)):
    """Get the most recent transaction fetch timestamp."""
    from config import DATABASE_PATH
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT MAX(fetched_at) FROM transaction_history WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            last_run = row[0] if row and row[0] else None
        return {'success': True, 'last_run': last_run}
    except Exception as e:
        return {'success': True, 'last_run': None}


@router.get("/stats")
async def get_transaction_stats(
    user_id: int = Depends(verify_session),
    days: int = Query(30, ge=1, le=90, description="Number of days for stats")
):
    """
    Get transaction statistics.

    Returns summary stats like total transactions, breakdown by blockchain,
    sent vs received counts, etc.

    Args:
        user_id: Authenticated user ID (from session)
        days: Number of days to analyze

    Returns:
        Transaction statistics
    """
    try:
        # Check if demo user
        from database import get_username_by_user_id
        username = await get_username_by_user_id(user_id)
        if await is_demo_user(username):
            logger.info(f"Demo mode: Returning demo transaction stats for user {user_id}")
            return await get_demo_transaction_stats(user_id, days)
        transactions = await transaction_history_service.get_transactions(
            user_id, days
        )

        # Calculate stats
        total = len(transactions)
        by_blockchain = {}
        by_direction = {'sent': 0, 'received': 0}

        for tx in transactions:
            chain = tx.get('blockchain', 'unknown')
            by_blockchain[chain] = by_blockchain.get(chain, 0) + 1

            direction = tx.get('direction', 'unknown')
            if direction in by_direction:
                by_direction[direction] += 1

        return {
            'success': True,
            'total_transactions': total,
            'by_blockchain': by_blockchain,
            'by_direction': by_direction,
            'days': days
        }

    except Exception as e:
        logger.error(f"Error getting transaction stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/by-chain")
async def get_transaction_analytics(
    days: int = Query(30, description="Time period in days (7, 30, 365, or 99999 for all)"),
    user_id: int = Depends(verify_session)
):
    """
    Get transaction analytics grouped by blockchain and time buckets.

    Args:
        days: Time period in days (7, 30, 365, or 99999 for all)
        user_id: Authenticated user ID (from session)

    Returns:
        Transaction counts by blockchain over time buckets
    """
    try:
        # Check if demo user
        from database import get_username_by_user_id
        username = await get_username_by_user_id(user_id)
        if await is_demo_user(username):
            logger.info(f"Demo mode: Returning demo transaction analytics for user {user_id}")
            return await get_demo_transaction_analytics(user_id, days)
        # Get all transactions for the time period
        transactions = await transaction_history_service.get_transactions(
            user_id, days
        )

        if not transactions:
            return {
                'success': True,
                'period': f"{days} days" if days < 99999 else "all time",
                'buckets': [],
                'chains': {}
            }

        # Determine bucket size based on time period
        if days <= 30:
            bucket_format = '%Y-%m-%d'  # Daily buckets
            bucket_label = 'day'
        elif days <= 365:
            bucket_format = '%Y-W%U'  # Weekly buckets
            bucket_label = 'week'
        else:
            bucket_format = '%Y-%m'  # Monthly buckets
            bucket_label = 'month'

        # Group transactions by blockchain and time bucket
        from collections import defaultdict
        chain_buckets = defaultdict(lambda: defaultdict(int))
        all_buckets = set()

        for tx in transactions:
            chain = tx.get('blockchain', 'unknown')
            tx_time = tx.get('tx_time')

            if not tx_time:
                continue

            # Parse timestamp
            if isinstance(tx_time, str):
                tx_dt = datetime.fromisoformat(tx_time.replace('Z', '+00:00'))
            else:
                tx_dt = tx_time

            # Create bucket key
            bucket_key = tx_dt.strftime(bucket_format)
            all_buckets.add(bucket_key)
            chain_buckets[chain][bucket_key] += 1

        # Sort buckets chronologically
        sorted_buckets = sorted(list(all_buckets))

        # Build response with aligned data for each chain
        chains_data = {}
        for chain in chain_buckets.keys():
            chain_counts = []
            for bucket in sorted_buckets:
                chain_counts.append(chain_buckets[chain].get(bucket, 0))
            chains_data[chain] = chain_counts

        # Format bucket labels for display
        display_buckets = []
        for bucket in sorted_buckets:
            if bucket_label == 'day':
                display_buckets.append(bucket)
            elif bucket_label == 'week':
                # Convert week format to readable
                year, week = bucket.split('-W')
                display_buckets.append(f"{year}-W{week}")
            else:
                # Month format
                display_buckets.append(bucket)

        return {
            'success': True,
            'period': f"{days} days" if days < 99999 else "all time",
            'bucket_type': bucket_label,
            'buckets': display_buckets,
            'chains': chains_data
        }

    except Exception as e:
        logger.error(f"Error getting transaction analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
