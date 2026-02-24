"""
P&L Router - Per-asset profit/loss tracking and cost basis management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import logging

from services.cost_basis_engine import cost_basis_engine
from auth_utils import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pnl", tags=["pnl"])

# Per-user compute progress tracking
_compute_progress: dict = {}


class ManualLotRequest(BaseModel):
    token_symbol: str
    quantity: float
    cost_per_unit: float
    acquisition_date: Optional[str] = None
    source: Optional[str] = "manual"


class DisposeRequest(BaseModel):
    token_symbol: str
    quantity: float
    proceeds_usd: float
    method: Optional[str] = "fifo"
    disposal_type: Optional[str] = "sell"
    disposal_date: Optional[str] = None


@router.get("/summary")
async def get_pnl_summary(user_id: int = Depends(verify_session)):
    """Get portfolio-wide P&L summary including unrealized and realized gains"""
    try:
        return await cost_basis_engine.get_portfolio_performance(user_id)
    except Exception as e:
        logger.error(f"Error getting P&L summary for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute P&L summary")


@router.get("/asset/{symbol}")
async def get_asset_pnl(symbol: str, user_id: int = Depends(verify_session)):
    """Get detailed P&L for a specific asset including open lots and realized history"""
    try:
        return await cost_basis_engine.get_asset_detail(user_id, symbol.upper())
    except Exception as e:
        logger.error(f"Error getting P&L for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get P&L for {symbol}")


@router.get("/unrealized")
async def get_unrealized_pnl(
    user_id: int = Depends(verify_session),
    token: Optional[str] = None,
):
    """Get unrealized P&L for all assets or a specific token"""
    try:
        return await cost_basis_engine.compute_unrealized_pnl(user_id, token)
    except Exception as e:
        logger.error(f"Error computing unrealized P&L: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute unrealized P&L")


@router.get("/realized")
async def get_realized_gains(
    user_id: int = Depends(verify_session),
    token: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get realized gains/losses log with optional date filtering"""
    try:
        return await cost_basis_engine.compute_realized_pnl(
            user_id, token, start_date, end_date
        )
    except Exception as e:
        logger.error(f"Error fetching realized gains: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch realized gains")


@router.get("/realized/monthly")
async def get_monthly_realized(
    user_id: int = Depends(verify_session),
    months: int = Query(default=12, ge=1, le=60),
):
    """Get realized gains aggregated by month"""
    try:
        return await cost_basis_engine.get_monthly_realized(user_id, months)
    except Exception as e:
        logger.error(f"Error fetching monthly realized gains: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch monthly realized gains")


@router.get("/lots/{symbol}")
async def get_open_lots(symbol: str, user_id: int = Depends(verify_session)):
    """View open cost basis lots for a token"""
    try:
        return await cost_basis_engine.get_open_lots(user_id, symbol.upper())
    except Exception as e:
        logger.error(f"Error fetching lots for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get lots for {symbol}")


@router.post("/lots/manual")
async def add_manual_lot(req: ManualLotRequest, user_id: int = Depends(verify_session)):
    """Add a manual cost basis entry"""
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    if req.cost_per_unit < 0:
        raise HTTPException(status_code=400, detail="Cost per unit cannot be negative")

    try:
        lot_id = await cost_basis_engine.record_manual_lot(
            user_id, req.token_symbol.upper(),
            req.quantity, req.cost_per_unit,
            req.acquisition_date, req.source
        )
        return {"success": True, "lot_id": lot_id}
    except Exception as e:
        logger.error(f"Error adding manual lot: {e}")
        raise HTTPException(status_code=500, detail="Failed to add manual lot")


@router.post("/dispose")
async def dispose_lots(req: DisposeRequest, user_id: int = Depends(verify_session)):
    """Manually dispose of lots (record a sale/withdrawal)"""
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    if req.method and req.method.lower() not in ('fifo', 'lifo', 'average'):
        raise HTTPException(status_code=400, detail="Method must be fifo, lifo, or average")

    try:
        result = await cost_basis_engine.dispose_lots(
            user_id, req.token_symbol.upper(),
            req.quantity, req.proceeds_usd,
            req.method or "fifo", req.disposal_type or "sell",
            req.disposal_date
        )
        return result
    except Exception as e:
        logger.error(f"Error disposing lots: {e}")
        raise HTTPException(status_code=500, detail="Failed to dispose lots")


@router.get("/compute/status")
async def get_compute_status(user_id: int = Depends(verify_session)):
    """Get current P&L computation progress for this user"""
    status = _compute_progress.get(user_id, {
        "stage": "idle", "progress": 0, "details": ""
    })
    return status


@router.post("/compute")
async def compute_pnl(
    user_id: int = Depends(verify_session),
    exchange: Optional[str] = None,
    include_wallets: bool = Query(default=True),
):
    """Trigger full P&L recomputation from exchange and wallet transactions"""
    try:
        if include_wallets:
            # Unified chronological ingestion (correct FIFO across both sources)
            _compute_progress[user_id] = {
                "stage": "detecting_transfers",
                "progress": 5,
                "details": "Detecting internal transfers..."
            }
            skip_ids = await cost_basis_engine.detect_internal_transfers(user_id)

            _compute_progress[user_id] = {
                "stage": "ingesting_transactions",
                "progress": 15,
                "details": "Ingesting all transactions in chronological order..."
            }

            result = await cost_basis_engine.ingest_all_transactions(
                user_id, skip_tx_ids=skip_ids
            )

            _compute_progress[user_id] = {
                "stage": "ingesting_transactions",
                "progress": 70,
                "details": f"Processed: {result.get('lots_created', 0)} lots, {result.get('disposals_processed', 0)} disposals, {result.get('transfers_matched', 0)} transfers matched"
            }
        else:
            # Exchange-only mode
            _compute_progress[user_id] = {
                "stage": "exchange_transactions",
                "progress": 10,
                "details": "Ingesting exchange transactions..."
            }

            result = await cost_basis_engine.ingest_exchange_transactions(
                user_id, exchange
            )

            _compute_progress[user_id] = {
                "stage": "exchange_transactions",
                "progress": 70,
                "details": f"Exchange: {result.get('lots_created', 0)} lots, {result.get('disposals_processed', 0)} disposals"
            }

        _compute_progress[user_id] = {
            "stage": "refreshing_summary",
            "progress": 80,
            "details": "Recomputing P&L summary..."
        }

        await cost_basis_engine.refresh_pnl_summary(user_id)

        _compute_progress[user_id] = {
            "stage": "complete",
            "progress": 100,
            "details": "P&L computation complete"
        }

        return result
    except Exception as e:
        _compute_progress[user_id] = {
            "stage": "error",
            "progress": 0,
            "details": str(e)
        }
        logger.error(f"Error computing P&L: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute P&L")


@router.post("/compute/wallets")
async def compute_wallet_pnl(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = None,
):
    """Trigger P&L computation from self-custody wallet transactions only"""
    try:
        _compute_progress[user_id] = {
            "stage": "wallet_transactions",
            "progress": 20,
            "details": "Ingesting wallet transactions..."
        }

        result = await cost_basis_engine.ingest_wallet_transactions(user_id, blockchain)

        _compute_progress[user_id] = {
            "stage": "refreshing_summary",
            "progress": 80,
            "details": "Recomputing P&L summary..."
        }

        await cost_basis_engine.refresh_pnl_summary(user_id)

        _compute_progress[user_id] = {
            "stage": "complete",
            "progress": 100,
            "details": "Wallet P&L computation complete"
        }

        return result
    except Exception as e:
        _compute_progress[user_id] = {
            "stage": "error",
            "progress": 0,
            "details": str(e)
        }
        logger.error(f"Error computing wallet P&L: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute wallet P&L")


@router.post("/refresh")
async def refresh_summary(user_id: int = Depends(verify_session)):
    """Refresh the P&L summary cache (materialized view)"""
    try:
        await cost_basis_engine.refresh_pnl_summary(user_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error refreshing P&L summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh P&L summary")


@router.get("/performance")
async def get_performance(user_id: int = Depends(verify_session)):
    """Get total invested vs current value"""
    try:
        return await cost_basis_engine.get_portfolio_performance(user_id)
    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to get performance data")
