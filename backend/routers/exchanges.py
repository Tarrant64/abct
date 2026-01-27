"""
Exchange Router - API endpoints for cryptocurrency exchange integrations.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.coinbase import coinbase_service
from services.pricing import pricing_service
from database import get_cache, set_cache
from middleware.auth import verify_admin

router = APIRouter(prefix="/exchanges", tags=["exchanges"])

# Cache TTL in seconds
EXCHANGE_CACHE_TTL = 300  # 5 minutes for exchange data

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
                "configured": coinbase_service.is_configured(),
                "name": "Coinbase"
            }
        }
    }


@router.get("/coinbase")
async def get_coinbase_portfolio(refresh: bool = Query(False, description="Force refresh cache")):
    """
    Get Coinbase portfolio with USD values.
    Only returns assets with USD value >= $1.00.
    """
    if not coinbase_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Coinbase API not configured. Add cdp_api_key.json to project root."
        )

    cache_key = "coinbase_portfolio"

    if not refresh:
        cached = await get_cache(cache_key)
        if cached:
            cached['from_cache'] = True
            return cached

    portfolio = await coinbase_service.get_portfolio_balances()

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

    await set_cache(cache_key, result, EXCHANGE_CACHE_TTL)
    return result


@router.get("/summary")
async def get_all_exchanges_summary():
    """Get summary of all configured exchanges."""
    result = {
        "exchanges": [],
        "total_usd": 0,
        "total_assets": 0
    }

    # Coinbase
    if coinbase_service.is_configured():
        try:
            coinbase_data = await get_coinbase_portfolio()
            result["exchanges"].append({
                "name": "Coinbase",
                "total_usd": coinbase_data.get("total_usd", 0),
                "asset_count": coinbase_data.get("asset_count", 0),
                "status": "connected"
            })
            result["total_usd"] += coinbase_data.get("total_usd", 0)
            result["total_assets"] += coinbase_data.get("asset_count", 0)
        except Exception as e:
            result["exchanges"].append({
                "name": "Coinbase",
                "status": "error",
                "error": str(e)
            })
    else:
        result["exchanges"].append({
            "name": "Coinbase",
            "status": "not_configured"
        })

    return result


@router.post("/coinbase/refresh", dependencies=[Depends(verify_admin)])
async def refresh_coinbase_portfolio():
    """Refresh Coinbase portfolio data. Requires admin authentication."""
    return await get_coinbase_portfolio(refresh=True)


@router.get("/coinbase/orders")
async def get_coinbase_open_orders():
    """
    Get open orders from Coinbase.
    Returns pending, open, or queued orders.
    """
    if not coinbase_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Coinbase API not configured"
        )

    orders = await coinbase_service.get_open_orders()
    return {
        "orders": orders,
        "count": len(orders)
    }
