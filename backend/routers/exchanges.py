"""
Exchange Router - API endpoints for cryptocurrency exchange integrations.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import asyncio
import logging
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.coinbase import coinbase_service
from services.binance_service import binance_service
from services.binance_us_service import binance_us_service
from services.okx_service import okx_service
from services.bitget_service import bitget_service
from services.gate_service import gate_service
from services.kucoin_service import kucoin_service
from services.pricing import pricing_service
from services.demo_exchange_service import demo_exchange_service
from services.transaction_history import transaction_history_service
from database import get_cache, set_cache, clear_cache, get_username_by_user_id
from middleware.auth import verify_admin
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session

router = APIRouter(prefix="/exchanges", tags=["exchanges"])

# Cache TTL in seconds
from config import CACHE_TTL_HOT, CACHE_TTL_WARM
EXCHANGE_CACHE_TTL = CACHE_TTL_HOT  # 5 minutes for exchange data

# Minimum USD value threshold for displaying assets
MIN_USD_VALUE = 1.00

# Map common Coinbase currency codes to our pricing service symbols
CURRENCY_MAP = {
    "BTC": "BTC",
    "ETH": "ETH",
    "ADA": "ADA",
    "SOL": "SOL",
    "DOGE": "DOGE",
    "XRP": "XRP",
    "DOT": "DOT",
    "LINK": "LINK",
    "AVAX": "AVAX",
    "MATIC": "MATIC",
    "ATOM": "ATOM",
    "LTC": "LTC",
    "UNI": "UNI",
    "SHIB": "SHIB",
    "NEAR": "NEAR",
    "APE": "APE",
    "AAVE": "AAVE",
    "MKR": "MKR",
    "GRT": "GRT",
    "FIL": "FIL",
    "ALGO": "ALGO",
    "XLM": "XLM",
    "USDC": "USDC",
    "USDT": "USDT",
    "DAI": "DAI",
}


@router.get("/status")
async def get_exchange_status():
    """Get status of configured exchanges."""
    return {
        "exchanges": {
            "coinbase": {
                "configured": await coinbase_service.is_configured(),
                "name": "Coinbase"
            },
            "binance": {
                "configured": await binance_service.ensure_configured(),
                "name": "Binance"
            },
            "binance_us": {
                "configured": await binance_us_service.ensure_configured(),
                "name": "Binance.US"
            },
            "okx": {
                "configured": okx_service.is_configured(),
                "name": "OKX"
            },
            "bitget": {
                "configured": bitget_service.is_configured(),
                "name": "Bitget"
            },
            "gate": {
                "configured": gate_service.is_configured(),
                "name": "Gate.io"
            },
            "kucoin": {
                "configured": kucoin_service.is_configured(),
                "name": "KuCoin"
            }
        }
    }


@router.get("/coinbase")
async def get_coinbase_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False, description="Force refresh cache")):
    """
    Get Coinbase portfolio with USD values.
    Only returns assets with USD value >= $1.00.
    """
    import sys
    sys.stderr.write(f"[COINBASE DEBUG] GET /exchanges/coinbase called for user_id={user_id}, refresh={refresh}\n")
    sys.stderr.flush()
    print(f"[COINBASE DEBUG] GET /exchanges/coinbase called for user_id={user_id}, refresh={refresh}", flush=True)
    logger.info(f"GET /exchanges/coinbase called for user_id={user_id}, refresh={refresh}")

    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo exchange balances
        logger.info("Returning demo exchange data for Coinbase")
        return await demo_exchange_service.get_portfolio_balances(user_id=user_id)

    # Normal mode
    is_configured = await coinbase_service.is_configured(user_id=user_id)
    logger.info(f"Coinbase is_configured: {is_configured}")

    if not is_configured:
        raise HTTPException(
            status_code=503,
            detail="Coinbase API not configured. Add cdp_api_key.json to project root."
        )

    cache_key = f"coinbase_portfolio"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            logger.info(f"Returning cached Coinbase data: {len(cached.get('assets', []))} assets")
            cached['from_cache'] = True
            return cached

    logger.info("Fetching fresh Coinbase portfolio data...")
    portfolio = await coinbase_service.get_portfolio_balances(user_id=user_id)
    logger.info(f"Coinbase portfolio result: {portfolio.get('asset_count', 0)} assets, ${portfolio.get('total_usd', 0)} total")

    if not portfolio.get("assets"):
        return portfolio

    # Get prices for crypto assets
    crypto_symbols = [
        a["currency"] for a in portfolio["assets"]
        if a.get("needs_price") and a["currency"] in CURRENCY_MAP
    ]

    prices = {}
    if crypto_symbols:
        # Get prices from our pricing service (CoinGecko)
        mapped_symbols = [CURRENCY_MAP.get(s, s) for s in crypto_symbols]
        prices = await pricing_service.get_prices(mapped_symbols)

    # Also try to get prices directly from Coinbase for unlisted tokens
    for asset in portfolio["assets"]:
        currency = asset["currency"]
        if asset.get("needs_price") and currency not in prices:
            # Try Coinbase spot price
            spot_price = await coinbase_service.get_spot_price(f"{currency}-USD")
            if spot_price:
                prices[currency] = spot_price

    # Calculate USD values and filter
    filtered_assets = []
    total_usd = 0.0

    for asset in portfolio["assets"]:
        currency = asset["currency"]
        balance = asset["balance"]

        if currency == "USD":
            usd_value = balance
        elif currency in prices:
            usd_value = balance * prices[currency]
        elif CURRENCY_MAP.get(currency) in prices:
            usd_value = balance * prices[CURRENCY_MAP[currency]]
        else:
            # Try to get price from Coinbase directly
            spot_price = await coinbase_service.get_spot_price(f"{currency}-USD")
            if spot_price:
                usd_value = balance * spot_price
                prices[currency] = spot_price
            else:
                usd_value = 0

        asset["usd_value"] = usd_value
        asset["price"] = prices.get(currency) or prices.get(CURRENCY_MAP.get(currency, ""), 0)

        # Only include if above threshold
        if usd_value >= MIN_USD_VALUE:
            filtered_assets.append(asset)
            total_usd += usd_value

    # Sort by USD value descending
    filtered_assets.sort(key=lambda x: x.get("usd_value", 0), reverse=True)

    result = {
        "exchange": "coinbase",
        "configured": True,
        "assets": filtered_assets,
        "total_usd": total_usd,
        "asset_count": len(filtered_assets),
        "min_value_filter": MIN_USD_VALUE,
        "from_cache": False
    }

    await set_cache(cache_key, result, EXCHANGE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/summary")
async def get_all_exchanges_summary(user_id: int = Depends(verify_session)):
    """Get summary of all configured exchanges."""
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo exchange summary
        coinbase_data = await demo_exchange_service.get_portfolio_balances(user_id=user_id)
        return {
            "exchanges": [{
                "name": "Coinbase",
                "total_usd": coinbase_data.get("total_usd", 0),
                "asset_count": coinbase_data.get("asset_count", 0),
                "status": "connected"
            }],
            "total_usd": coinbase_data.get("total_usd", 0),
            "total_assets": coinbase_data.get("asset_count", 0),
            "demo_mode": True
        }

    # Normal mode
    result = {
        "exchanges": [],
        "total_usd": 0,
        "total_assets": 0
    }

    # List of all exchange services
    exchanges = [
        (coinbase_service, "Coinbase", get_coinbase_portfolio),
        (binance_service, "Binance", get_binance_portfolio),
        (binance_us_service, "Binance.US", get_binance_us_portfolio),
        (okx_service, "OKX", get_okx_portfolio),
        (bitget_service, "Bitget", get_bitget_portfolio),
        (gate_service, "Gate.io", get_gate_portfolio),
        (kucoin_service, "KuCoin", get_kucoin_portfolio),
    ]

    for service, name, get_func in exchanges:
        # Handle both sync and async is_configured (coinbase is async, others sync)
        configured = service.is_configured()
        if asyncio.iscoroutine(configured):
            configured = await configured
        if configured:
            try:
                exchange_data = await get_func(user_id=user_id)
                result["exchanges"].append({
                    "name": name,
                    "total_usd": exchange_data.get("total_usd", 0),
                    "asset_count": exchange_data.get("asset_count", 0),
                    "status": "connected"
                })
                result["total_usd"] += exchange_data.get("total_usd", 0)
                result["total_assets"] += exchange_data.get("asset_count", 0)
            except Exception as e:
                result["exchanges"].append({
                    "name": name,
                    "status": "error",
                    "error": str(e)
                })

    return result


@router.post("/coinbase/refresh")
async def refresh_coinbase_portfolio(user_id: int = Depends(verify_session)):
    """Refresh Coinbase portfolio data."""
    return await get_coinbase_portfolio(user_id=user_id, refresh=True)


async def process_exchange_portfolio(exchange_service, exchange_name: str, user_id: int, refresh: bool = False):
    """
    Generic function to process exchange portfolio with pricing.
    Works for all exchanges that return the standard format.
    """
    cache_key = f"{exchange_name}_portfolio"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    portfolio = await exchange_service.get_account_balances(user_id=user_id)

    if not portfolio.get("assets"):
        return portfolio

    # Get prices for crypto assets
    crypto_symbols = [
        a["currency"] for a in portfolio["assets"]
        if a.get("needs_price") and a["currency"] in CURRENCY_MAP
    ]

    prices = {}
    if crypto_symbols:
        # Get prices from our pricing service (CoinGecko)
        mapped_symbols = [CURRENCY_MAP.get(s, s) for s in crypto_symbols]
        prices = await pricing_service.get_prices(mapped_symbols)

    # Calculate USD values and filter
    filtered_assets = []
    total_usd = 0.0

    for asset in portfolio["assets"]:
        currency = asset["currency"]
        balance = asset["balance"]

        if currency == "USD" or currency == "USDT" or currency == "USDC":
            # Stablecoins are 1:1 with USD
            usd_value = balance
        elif currency in prices:
            usd_value = balance * prices[currency]
        elif CURRENCY_MAP.get(currency) in prices:
            usd_value = balance * prices[CURRENCY_MAP[currency]]
        else:
            # Try to get price from pricing service directly
            direct_prices = await pricing_service.get_prices([currency])
            if currency in direct_prices:
                usd_value = balance * direct_prices[currency]
                prices[currency] = direct_prices[currency]
            else:
                usd_value = 0

        asset["usd_value"] = usd_value
        asset["price"] = prices.get(currency) or prices.get(CURRENCY_MAP.get(currency, ""), 0)

        # Only include if above threshold
        if usd_value >= MIN_USD_VALUE:
            filtered_assets.append(asset)
            total_usd += usd_value

    # Sort by USD value descending
    filtered_assets.sort(key=lambda x: x.get("usd_value", 0), reverse=True)

    result = {
        "exchange": exchange_name,
        "configured": True,
        "assets": filtered_assets,
        "total_usd": total_usd,
        "asset_count": len(filtered_assets),
        "min_value_filter": MIN_USD_VALUE,
        "from_cache": False
    }

    await set_cache(cache_key, result, EXCHANGE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/binance")
async def get_binance_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Binance portfolio with USD values."""
    if not await binance_service.ensure_configured():
        raise HTTPException(
            status_code=503,
            detail="Binance API not configured. Add BINANCE_API_KEY and BINANCE_API_SECRET to .env file."
        )
    return await process_exchange_portfolio(binance_service, "binance", user_id, refresh)


@router.get("/binance-us")
async def get_binance_us_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Binance.US portfolio with USD values."""
    if not await binance_us_service.ensure_configured():
        raise HTTPException(
            status_code=503,
            detail="Binance.US API not configured. Add BINANCE_US_API_KEY and BINANCE_US_API_SECRET to .env file."
        )
    return await process_exchange_portfolio(binance_us_service, "binance_us", user_id, refresh)


@router.get("/okx")
async def get_okx_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get OKX portfolio with USD values."""
    if not okx_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="OKX API not configured. Add OKX_API_KEY, OKX_API_SECRET, and OKX_API_PASSPHRASE to .env file."
        )
    return await process_exchange_portfolio(okx_service, "okx", user_id, refresh)


@router.get("/bitget")
async def get_bitget_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Bitget portfolio with USD values."""
    if not bitget_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Bitget API not configured. Add BITGET_API_KEY, BITGET_API_SECRET, and BITGET_API_PASSPHRASE to .env file."
        )
    return await process_exchange_portfolio(bitget_service, "bitget", user_id, refresh)


@router.get("/gate")
async def get_gate_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Gate.io portfolio with USD values."""
    if not gate_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Gate.io API not configured. Add GATE_API_KEY and GATE_API_SECRET to .env file."
        )
    return await process_exchange_portfolio(gate_service, "gate", user_id, refresh)


@router.get("/kucoin")
async def get_kucoin_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get KuCoin portfolio with USD values."""
    if not kucoin_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="KuCoin API not configured. Add KUCOIN_API_KEY, KUCOIN_API_SECRET, and KUCOIN_API_PASSPHRASE to .env file."
        )
    return await process_exchange_portfolio(kucoin_service, "kucoin", user_id, refresh)


@router.get("/coinbase/orders")
async def get_coinbase_open_orders(user_id: int = Depends(verify_session)):
    """
    Get open orders from Coinbase.
    Returns pending, open, or queued orders.
    """
    if not await coinbase_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Coinbase API not configured"
        )

    orders = await coinbase_service.get_open_orders(user_id=user_id)
    return {
        "orders": orders,
        "count": len(orders)
    }


@router.get("/all")
async def get_all_exchanges(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """
    Get portfolio data from all configured exchanges.
    Combines assets from all exchanges into a single response.
    """
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo exchange data
        coinbase_data = await demo_exchange_service.get_portfolio_balances(user_id=user_id)
        return {
            "exchanges": [coinbase_data],
            "total_usd": coinbase_data.get("total_usd", 0),
            "total_assets": coinbase_data.get("asset_count", 0),
            "demo_mode": True
        }

    # List of all exchanges
    all_exchanges = []
    total_usd = 0
    total_assets = 0

    # Coinbase
    if await coinbase_service.is_configured():
        try:
            data = await get_coinbase_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "coinbase",
                "name": "Coinbase",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    # Binance
    if await binance_service.ensure_configured():
        try:
            data = await get_binance_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "binance",
                "name": "Binance",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    # Binance.US
    if await binance_us_service.ensure_configured():
        try:
            data = await get_binance_us_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "binance_us",
                "name": "Binance.US",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    # OKX
    if okx_service.is_configured():
        try:
            data = await get_okx_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "okx",
                "name": "OKX",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    # Bitget
    if bitget_service.is_configured():
        try:
            data = await get_bitget_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "bitget",
                "name": "Bitget",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    # Gate.io
    if gate_service.is_configured():
        try:
            data = await get_gate_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "gate",
                "name": "Gate.io",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    # KuCoin
    if kucoin_service.is_configured():
        try:
            data = await get_kucoin_portfolio(user_id=user_id, refresh=refresh)
            all_exchanges.append(data)
            total_usd += data.get("total_usd", 0)
            total_assets += data.get("asset_count", 0)
        except Exception as e:
            all_exchanges.append({
                "exchange": "kucoin",
                "name": "KuCoin",
                "error": str(e),
                "configured": True,
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            })

    return {
        "exchanges": all_exchanges,
        "total_usd": total_usd,
        "total_assets": total_assets,
        "exchange_count": len(all_exchanges)
    }


def _map_v2_tx_type_to_side(tx_type: str, amount: str = "0") -> str:
    """Map Coinbase v2 transaction type to a normalized direction/side."""
    tx_type_lower = tx_type.lower()
    if tx_type_lower in ("buy", "subscription"):
        return "BUY"
    elif tx_type_lower == "sell":
        return "SELL"
    elif tx_type_lower == "send":
        return "SEND"
    elif tx_type_lower == "receive":
        return "RECEIVE"
    elif tx_type_lower in ("fiat_deposit", "deposit"):
        return "DEPOSIT"
    elif tx_type_lower in ("fiat_withdrawal", "withdrawal"):
        return "WITHDRAWAL"
    elif tx_type_lower in ("staking_reward", "inflation_reward"):
        return "REWARD"
    elif tx_type_lower in ("trade", "advanced_trade_fill"):
        # Determine buy/sell based on amount sign
        try:
            if float(amount) >= 0:
                return "BUY"
            else:
                return "SELL"
        except (ValueError, TypeError):
            return "BUY"
    else:
        return tx_type.upper()


def _db_tx_to_normalized(row: dict) -> dict:
    """Convert an exchange_transactions DB row to the normalized API format."""
    tx_type = row.get("tx_type", "")
    amount_str = row.get("amount", "0")
    side = _map_v2_tx_type_to_side(tx_type, amount_str)

    # Parse amount (remove negative sign for display)
    try:
        amount_val = abs(float(amount_str)) if amount_str else 0
    except (ValueError, TypeError):
        amount_val = 0

    # Parse native USD amount
    try:
        native_amount = abs(float(row.get("native_amount", "0") or "0"))
    except (ValueError, TypeError):
        native_amount = 0

    # Parse fee
    try:
        fee = abs(float(row.get("fee", "0") or "0"))
    except (ValueError, TypeError):
        fee = 0

    return {
        "exchange": row.get("exchange", "coinbase"),
        "time": row.get("tx_time", ""),
        "side": side,
        "tx_type": tx_type,
        "amount": amount_val,
        "token": row.get("token_symbol", ""),
        "quote_amount": native_amount,
        "quote_token": row.get("native_currency", "USD"),
        "price": round(native_amount / amount_val, 2) if amount_val > 0 else 0,
        "fee": fee,
        "fee_token": row.get("fee_currency", "USD"),
        "order_id": row.get("tx_id", ""),
        "from_address": row.get("from_address", ""),
        "to_address": row.get("to_address", ""),
        "network_hash": row.get("network_hash", ""),
        "_isCex": True,
    }


@router.get("/transactions")
async def get_exchange_transactions(
    user_id: int = Depends(verify_session),
    days: int = Query(90, description="Number of days to fetch"),
    exchange: str = Query(None, description="Filter by exchange name"),
    refresh: bool = Query(False, description="Force re-fetch from APIs"),
):
    """Get normalized trade history from all configured exchanges.

    First checks the exchange_transactions DB table (fast path).
    Falls back to live API fetch for exchanges without DB data.
    """
    cache_key = f"exchange_transactions_{days}_{exchange or 'all'}"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    all_transactions = []
    exchange_counts = {}

    # --- Coinbase: read from DB (v2 full history) ---
    if not exchange or exchange == "coinbase":
        if await coinbase_service.is_configured(user_id=user_id):
            db_count = await transaction_history_service.get_exchange_transaction_count(user_id, "coinbase")

            if db_count == 0 or refresh:
                # Auto-fetch on first load or explicit refresh
                try:
                    v2_txs = await coinbase_service.get_all_v2_transactions(user_id=user_id)
                    await transaction_history_service.save_exchange_transactions(user_id, "coinbase", v2_txs)
                    logger.info(f"Auto-fetched {len(v2_txs)} Coinbase v2 transactions")
                except Exception as e:
                    logger.error(f"Error auto-fetching Coinbase v2 transactions: {e}")

            # Read from DB
            db_rows = await transaction_history_service.get_exchange_transactions(
                user_id, days=days, exchange="coinbase"
            )
            coinbase_txs = [_db_tx_to_normalized(row) for row in db_rows]
            all_transactions.extend(coinbase_txs)
            exchange_counts["coinbase"] = len(coinbase_txs)

    # --- Binance: read from DB (full history) ---
    if not exchange or exchange == "binance":
        if await binance_service.ensure_configured():
            db_count = await transaction_history_service.get_exchange_transaction_count(user_id, "binance")
            if db_count == 0 or refresh:
                try:
                    txs = await binance_service.get_all_transactions(user_id=user_id)
                    await transaction_history_service.save_exchange_transactions(user_id, "binance", txs)
                    logger.info(f"Auto-fetched {len(txs)} Binance transactions")
                except Exception as e:
                    logger.error(f"Error auto-fetching Binance transactions: {e}")
            db_rows = await transaction_history_service.get_exchange_transactions(
                user_id, days=days, exchange="binance"
            )
            binance_txs = [_db_tx_to_normalized(row) for row in db_rows]
            all_transactions.extend(binance_txs)
            exchange_counts["binance"] = len(binance_txs)

    # --- Binance.US: read from DB (full history) ---
    if not exchange or exchange == "binance_us":
        if await binance_us_service.ensure_configured():
            db_count = await transaction_history_service.get_exchange_transaction_count(user_id, "binance_us")
            if db_count == 0 or refresh:
                try:
                    txs = await binance_us_service.get_all_transactions(user_id=user_id)
                    await transaction_history_service.save_exchange_transactions(user_id, "binance_us", txs)
                    logger.info(f"Auto-fetched {len(txs)} Binance.US transactions")
                except Exception as e:
                    logger.error(f"Error auto-fetching Binance.US transactions: {e}")
            db_rows = await transaction_history_service.get_exchange_transactions(
                user_id, days=days, exchange="binance_us"
            )
            binance_us_txs = [_db_tx_to_normalized(row) for row in db_rows]
            all_transactions.extend(binance_us_txs)
            exchange_counts["binance_us"] = len(binance_us_txs)

    # Sort by time descending
    all_transactions.sort(key=lambda x: x.get("time", ""), reverse=True)

    result = {
        "success": True,
        "transactions": all_transactions,
        "exchanges": exchange_counts,
        "total_count": len(all_transactions),
        "days": days,
        "from_cache": False
    }

    await set_cache(cache_key, result, CACHE_TTL_WARM, user_id=user_id)
    return result


def _filter_by_cutoff(transactions: list, cutoff: datetime) -> list:
    """Filter transactions to only include those after cutoff."""
    filtered = []
    for tx in transactions:
        try:
            tx_time = tx.get("time", "")
            if tx_time:
                tx_dt = datetime.fromisoformat(tx_time.replace("Z", "+00:00"))
                if tx_dt >= cutoff:
                    filtered.append(tx)
            else:
                filtered.append(tx)
        except (ValueError, TypeError):
            filtered.append(tx)
    return filtered


@router.post("/transactions/refresh")
async def refresh_exchange_transactions(
    user_id: int = Depends(verify_session),
    exchange: str = Query(None, description="Exchange to refresh (default: all)"),
):
    """Trigger a full re-fetch of exchange transactions and store in DB."""
    results = {}

    if not exchange or exchange == "coinbase":
        if await coinbase_service.is_configured(user_id=user_id):
            try:
                v2_txs = await coinbase_service.get_all_v2_transactions(user_id=user_id)
                inserted = await transaction_history_service.save_exchange_transactions(
                    user_id, "coinbase", v2_txs
                )
                total = await transaction_history_service.get_exchange_transaction_count(user_id, "coinbase")
                results["coinbase"] = {
                    "fetched": len(v2_txs),
                    "new": inserted,
                    "total_stored": total,
                }
            except Exception as e:
                logger.error(f"Error refreshing Coinbase transactions: {e}")
                results["coinbase"] = {"error": str(e)}

    if not exchange or exchange == "binance":
        if await binance_service.ensure_configured():
            try:
                txs = await binance_service.get_all_transactions(user_id=user_id)
                inserted = await transaction_history_service.save_exchange_transactions(
                    user_id, "binance", txs
                )
                total = await transaction_history_service.get_exchange_transaction_count(user_id, "binance")
                results["binance"] = {
                    "fetched": len(txs),
                    "new": inserted,
                    "total_stored": total,
                }
            except Exception as e:
                logger.error(f"Error refreshing Binance transactions: {e}")
                results["binance"] = {"error": str(e)}

    if not exchange or exchange == "binance_us":
        if await binance_us_service.ensure_configured():
            try:
                txs = await binance_us_service.get_all_transactions(user_id=user_id)
                inserted = await transaction_history_service.save_exchange_transactions(
                    user_id, "binance_us", txs
                )
                total = await transaction_history_service.get_exchange_transaction_count(user_id, "binance_us")
                results["binance_us"] = {
                    "fetched": len(txs),
                    "new": inserted,
                    "total_stored": total,
                }
            except Exception as e:
                logger.error(f"Error refreshing Binance.US transactions: {e}")
                results["binance_us"] = {"error": str(e)}

    # Invalidate transaction and analytics caches
    await clear_cache("exchange_transactions_", user_id=user_id)
    await clear_cache("exchange_analytics_", user_id=user_id)
    await clear_cache("intelligence_", user_id=user_id)

    return {"success": True, "results": results}


@router.get("/analytics/by-exchange")
async def get_analytics_by_exchange(
    user_id: int = Depends(verify_session),
    days: int = Query(30, description="Number of days to analyze")
):
    """Get trade count analytics bucketed by time period and exchange."""
    cache_key = f"exchange_analytics_{days}"

    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        cached['from_cache'] = True
        return cached

    # Fetch from DB + API
    tx_response = await get_exchange_transactions(user_id=user_id, days=days)
    transactions = tx_response.get("transactions", [])

    if not transactions:
        return {
            "success": True,
            "buckets": [],
            "exchanges": {},
            "days": days,
            "from_cache": False
        }

    # Determine bucket size
    if days <= 30:
        bucket_format = "%Y-%m-%d"
        bucket_label_fn = lambda d: d.strftime("%b %d")
    elif days <= 365:
        bucket_format = "%Y-W%W"
        bucket_label_fn = lambda d: f"W{d.strftime('%W')} {d.strftime('%b')}"
    else:
        bucket_format = "%Y-%m"
        bucket_label_fn = lambda d: d.strftime("%b %Y")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    bucket_labels = []
    bucket_keys = []
    current = cutoff
    while current <= now:
        bk = current.strftime(bucket_format)
        bl = bucket_label_fn(current)
        if bk not in bucket_keys:
            bucket_keys.append(bk)
            bucket_labels.append(bl)
        if days <= 30:
            current += timedelta(days=1)
        elif days <= 365:
            current += timedelta(weeks=1)
        else:
            current += timedelta(days=30)

    exchange_buckets = defaultdict(lambda: defaultdict(int))

    for tx in transactions:
        try:
            tx_time = tx.get("time", "")
            if not tx_time:
                continue
            tx_dt = datetime.fromisoformat(tx_time.replace("Z", "+00:00"))
            bk = tx_dt.strftime(bucket_format)
            ex_name = tx.get("exchange", "unknown")
            exchange_buckets[ex_name][bk] += 1
        except (ValueError, TypeError):
            continue

    exchanges = {}
    for ex_name, bucket_counts in exchange_buckets.items():
        exchanges[ex_name] = [bucket_counts.get(bk, 0) for bk in bucket_keys]

    result = {
        "success": True,
        "buckets": bucket_labels,
        "exchanges": exchanges,
        "days": days,
        "from_cache": False
    }

    await set_cache(cache_key, result, CACHE_TTL_WARM, user_id=user_id)
    return result
