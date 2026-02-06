"""
Exchange Router - API endpoints for cryptocurrency exchange integrations.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import asyncio
import logging
import sys
import os

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
from database import get_cache, set_cache, get_username_by_user_id
from middleware.auth import verify_admin
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session

router = APIRouter(prefix="/exchanges", tags=["exchanges"])

# Cache TTL in seconds
from config import CACHE_TTL_HOT
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
                "configured": binance_service.is_configured(),
                "name": "Binance"
            },
            "binance_us": {
                "configured": binance_us_service.is_configured(),
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
    if not await binance_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Binance API not configured. Add BINANCE_API_KEY and BINANCE_API_SECRET to .env file."
        )
    return await process_exchange_portfolio(binance_service, "binance", user_id, refresh)


@router.get("/binance-us")
async def get_binance_us_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Binance.US portfolio with USD values."""
    if not await binance_us_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Binance.US API not configured. Add BINANCE_US_API_KEY and BINANCE_US_API_SECRET to .env file."
        )
    return await process_exchange_portfolio(binance_us_service, "binance_us", user_id, refresh)


@router.get("/okx")
async def get_okx_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get OKX portfolio with USD values."""
    if not await okx_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="OKX API not configured. Add OKX_API_KEY, OKX_API_SECRET, and OKX_API_PASSPHRASE to .env file."
        )
    return await process_exchange_portfolio(okx_service, "okx", user_id, refresh)


@router.get("/bitget")
async def get_bitget_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Bitget portfolio with USD values."""
    if not await bitget_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Bitget API not configured. Add BITGET_API_KEY, BITGET_API_SECRET, and BITGET_API_PASSPHRASE to .env file."
        )
    return await process_exchange_portfolio(bitget_service, "bitget", user_id, refresh)


@router.get("/gate")
async def get_gate_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get Gate.io portfolio with USD values."""
    if not await gate_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Gate.io API not configured. Add GATE_API_KEY and GATE_API_SECRET to .env file."
        )
    return await process_exchange_portfolio(gate_service, "gate", user_id, refresh)


@router.get("/kucoin")
async def get_kucoin_portfolio(user_id: int = Depends(verify_session), refresh: bool = Query(False)):
    """Get KuCoin portfolio with USD values."""
    if not await kucoin_service.is_configured():
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
    if binance_service.is_configured():
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
    if binance_us_service.is_configured():
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
