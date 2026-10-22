"""
Manual Stocks Router (WQ-0382) -- API for manually-tracked stock/ETF holdings.

Separate from /custom-tokens (crypto) on purpose: quantities are manual,
prices come from the keyless stock engine (services/stock_data.py), and
nothing here touches a chain. Auth convention matches the rest of the app
(verify_session, per-user rows).

Endpoints:
  GET    /stocks                holdings with live-enriched prices + total
  POST   /stocks                add a holding (symbol + manual quantity)
  GET    /stocks/{id}           one holding
  PUT    /stocks/{id}           update quantity/cost basis/name/...
  DELETE /stocks/{id}           remove a holding
  GET    /stocks/{id}/history   daily bars (backfills once when empty)
  GET    /stocks/search?q=      symbol validation/lookup (add-dialog helper)
  GET    /stocks/scheduler      engine status (times, next runs, last cycle)
  POST   /stocks/scheduler/run  force a refresh cycle now
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, field_validator

from database import (
    add_manual_stock, get_all_manual_stocks, get_manual_stock_by_id,
    update_manual_stock, delete_manual_stock,
    get_stock_price_history, upsert_stock_price_history,
)
from services.stock_data import stock_data_service, normalize_symbol
from services.stock_scheduler import stock_scheduler
from auth_utils import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stocks", tags=["stocks"])


class StockAddRequest(BaseModel):
    symbol: str
    quantity: float
    name: Optional[str] = None
    cost_basis: Optional[float] = None      # USD per share (optional)
    asset_class: Optional[str] = "stock"    # stock | etf
    include_in_total: Optional[int] = 1
    description: Optional[str] = None       # custodian note ("Fidelity", ...)

    @field_validator("description")
    @classmethod
    def _trim_desc(cls, v):
        return v.strip()[:120] or None if v else None

    @field_validator("symbol")
    @classmethod
    def _valid_symbol(cls, v: str) -> str:
        n = normalize_symbol(v)
        if not n:
            raise ValueError("symbol must be 1-10 letters/digits/./- starting with a letter")
        return n

    @field_validator("quantity")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @field_validator("asset_class")
    @classmethod
    def _class(cls, v: Optional[str]) -> Optional[str]:
        if v not in (None, "stock", "etf"):
            raise ValueError("asset_class must be 'stock' or 'etf'")
        return v


class StockUpdateRequest(BaseModel):
    quantity: Optional[float] = None
    name: Optional[str] = None
    cost_basis: Optional[float] = None
    asset_class: Optional[str] = None
    include_in_total: Optional[int] = None
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def _trim_desc(cls, v):
        return v.strip()[:120] or None if v else None

    @field_validator("quantity")
    @classmethod
    def _positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @field_validator("asset_class")
    @classmethod
    def _class(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("stock", "etf"):
            raise ValueError("asset_class must be 'stock' or 'etf'")
        return v


def _enrich(row: dict, quotes: dict) -> dict:
    """Merge the freshest quote (cache/live) over the stored row."""
    q = quotes.get(row["symbol"]) or {}
    price = q.get("price_usd", row.get("price_usd"))
    prev = q.get("prev_close_usd", row.get("prev_close_usd"))
    qty = row.get("quantity") or 0
    change_pct = q.get("change_pct", row.get("change_pct"))
    if change_pct is None and price and prev:
        change_pct = round((price - prev) / prev * 100, 4)
    cost = row.get("cost_basis")
    value = round(price * qty, 2) if price is not None else None
    cost_value = round(cost * qty, 2) if cost is not None and qty else None
    pnl = (round(value - cost_value, 2)
           if value is not None and cost_value is not None else None)
    pnl_pct = (round((value - cost_value) / cost_value * 100, 2)
               if pnl is not None and cost_value else None)
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "name": q.get("name") or row.get("name"),
        "quantity": qty,
        "cost_basis": cost,
        "asset_class": row.get("asset_class") or "stock",
        "price_usd": price,
        "prev_close_usd": prev,
        "change_pct": change_pct,
        "value_usd": value,
        "cost_value_usd": cost_value,
        "unrealized_pnl_usd": pnl,
        "unrealized_pnl_pct": pnl_pct,
        "price_source": q.get("source") or row.get("price_source"),
        "market_status": q.get("market_status"),
        # naive UTC per repo convention (container clock is UTC; the web
        # layer's parseServerDate() appends the Z)
        "last_price_update": (row.get("last_price_update").isoformat()
                              if hasattr(row.get("last_price_update"), "isoformat")
                              else row.get("last_price_update")),
        "include_in_total": row.get("include_in_total", 1),
        "description": row.get("description"),
    }


@router.get("")
async def list_stocks(user_id: int = Depends(verify_session)):
    """Manual stock holdings with current prices and portfolio total."""
    rows = await get_all_manual_stocks(user_id)
    symbols = sorted({r["symbol"] for r in rows})
    quotes = await stock_data_service.get_quotes(symbols) if symbols else {}
    stocks = [_enrich(r, quotes) for r in rows]
    total = sum(s["value_usd"] or 0 for s in stocks if s["include_in_total"])
    return {"stocks": stocks, "tracked_total_usd": round(total, 2),
            "last_updated": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}


@router.post("")
async def add_stock(request: StockAddRequest,
                    user_id: int = Depends(verify_session)):
    """Add a manual holding (or update the quantity of an existing symbol).

    Validates the ticker against the live feed before storing, and seeds the
    row with the current quote + recent daily history (one best-effort
    backfill so the detail chart is not empty on day one).
    """
    symbol = request.symbol
    # Live lookup: refuse an unknown ticker instead of storing dead weight.
    quotes = await stock_data_service.get_quotes([symbol], use_cache=False)
    if symbol not in quotes:
        raise HTTPException(
            status_code=404,
            detail=f"No public quote found for {symbol} "
                   "(checked CNBC + Nasdaq). Use the exact listed ticker.")
    q = quotes[symbol]
    asset_class = request.asset_class or q.get("asset_class") or "stock"

    stock_id = await add_manual_stock({
        "symbol": symbol,
        "quantity": request.quantity,
        "name": request.name or q.get("name"),
        "cost_basis": request.cost_basis,
        "asset_class": asset_class,
        "price_usd": q["price_usd"],
        "prev_close_usd": q.get("prev_close_usd"),
        "change_pct": q.get("change_pct"),
        "price_source": q.get("source"),
        "description": request.description,
    }, user_id)

    row = await get_manual_stock_by_id(stock_id, user_id)
    try:
        await upsert_stock_price_history(symbol,
                                         stock_data_service.market_date(),
                                         {"last_price": q["price_usd"]},
                                         source=q.get("source"))
        await stock_data_service.backfill_history(symbol, asset_class, days=120)
    except Exception as e:
        logger.warning("stocks: add-time history backfill %s failed: %s",
                       symbol, e)

    return {"status": "success", "id": stock_id,
            "stock": _enrich(row, {symbol: q})}


@router.get("/scheduler")
async def scheduler_status(user_id: int = Depends(verify_session)):
    """Stock engine status: schedule, next runs, last cycle stats."""
    from config import STOCK_REFRESH_TIMES, STOCK_MARKET_TZ, STOCK_SCHEDULER_ENABLED
    next_runs = []
    if stock_scheduler.scheduler:
        try:
            next_runs = [j.next_run_time.isoformat()
                         for j in stock_scheduler.scheduler.get_jobs()
                         if j.next_run_time]
        except Exception:
            pass
    return {
        "enabled": STOCK_SCHEDULER_ENABLED,
        "running": bool(stock_scheduler.scheduler),
        "schedule_times_et": STOCK_REFRESH_TIMES,
        "timezone": STOCK_MARKET_TZ,
        "next_runs": sorted(next_runs),
        "stats": stock_scheduler.stats,
        "feed": stock_data_service.stats,
    }


@router.post("/scheduler/run")
async def scheduler_run(user_id: int = Depends(verify_session)):
    """Force one refresh cycle now (same code path the cron runs)."""
    stats = await stock_scheduler.run_cycle(reason="manual")
    return {"status": "success", "cycle": stats}


@router.get("/search")
async def search_symbol(q: str = Query(..., min_length=1, max_length=10),
                        user_id: int = Depends(verify_session)):
    """Validate/look up a ticker for the add dialog (exact match only)."""
    symbol = normalize_symbol(q)
    if not symbol:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    quotes = await stock_data_service.get_quotes([symbol])
    if symbol not in quotes:
        return {"found": False, "symbol": symbol}
    q_ = quotes[symbol]
    return {
        "found": True,
        "symbol": symbol,
        "name": q_.get("name"),
        "price_usd": q_["price_usd"],
        "change_pct": q_.get("change_pct"),
        "asset_class": q_.get("asset_class"),
        "exchange": q_.get("exchange"),
        "source": q_.get("source"),
    }


@router.get("/{stock_id}")
async def get_stock(stock_id: int, user_id: int = Depends(verify_session)):
    row = await get_manual_stock_by_id(stock_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock holding not found")
    quotes = await stock_data_service.get_quotes([row["symbol"]])
    return {"stock": _enrich(row, quotes)}


@router.put("/{stock_id}")
async def update_stock(stock_id: int, request: StockUpdateRequest,
                       user_id: int = Depends(verify_session)):
    row = await get_manual_stock_by_id(stock_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock holding not found")
    updates = request.model_dump(exclude_unset=True)
    # Explicit nulls are meaningful only for the clearable fields (cost
    # basis, description). Other fields must never be nulled through PUT.
    for k in ("quantity", "name", "asset_class", "include_in_total"):
        if k in updates and updates[k] is None:
            del updates[k]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    await update_manual_stock(stock_id, updates, user_id)
    row = await get_manual_stock_by_id(stock_id, user_id)
    quotes = await stock_data_service.get_quotes([row["symbol"]])
    return {"status": "success", "stock": _enrich(row, quotes)}


@router.delete("/{stock_id}")
async def delete_stock(stock_id: int, user_id: int = Depends(verify_session)):
    row = await get_manual_stock_by_id(stock_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock holding not found")
    await delete_manual_stock(stock_id, user_id)
    return {"status": "success", "deleted_id": stock_id}


@router.get("/{stock_id}/history")
async def stock_history(stock_id: int, days: int = Query(90, ge=5, le=365),
                        user_id: int = Depends(verify_session)):
    """Daily bars from stock_price_history; backfills once when empty."""
    row = await get_manual_stock_by_id(stock_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Stock holding not found")

    bars = await get_stock_price_history(row["symbol"], days)
    if len(bars) < 5:
        try:
            n = await stock_data_service.backfill_history(
                row["symbol"], row.get("asset_class") or "stock",
                days=days + 40)
            if n:
                bars = await get_stock_price_history(row["symbol"], days)
        except Exception as e:
            logger.warning("stocks: history backfill %s failed: %s",
                           row["symbol"], e)

    return {
        "symbol": row["symbol"],
        "days": days,
        "bars": [{"date": b["trade_date"], "open": b.get("open"),
                  "high": b.get("high"), "low": b.get("low"),
                  "close": b.get("close"), "volume": b.get("volume")}
                 for b in bars],
    }
