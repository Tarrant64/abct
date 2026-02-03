"""
Transaction History Router - API endpoints for consolidated transaction history
"""

from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
import logging

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.transaction_history import transaction_history_service
from auth_utils import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])


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


@router.post("/refresh")
async def refresh_transaction_history(
    user_id: int = Depends(verify_session),
    days: int = Query(7, ge=1, le=100000, description="Number of days to fetch"),
    blockchain: Optional[str] = Query(None, description="Fetch for specific blockchain only")
):
    """
    Fetch fresh transaction data from blockchains.

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
