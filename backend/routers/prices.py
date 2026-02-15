"""
Pricing API Endpoints

Provides current cryptocurrency prices from CoinGecko.
"""

from fastapi import APIRouter, Query, HTTPException
import sys
import os
import httpx
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.pricing import pricing_service
from services.http_client import get_client

router = APIRouter(prefix="/prices", tags=["prices"])
logger = logging.getLogger(__name__)

# Cache for global market data (5 min TTL)
_global_market_cache = {"data": None, "timestamp": 0}


@router.get("")
async def get_prices():
    """
    Get current USD prices for main cryptocurrencies (ADA, BTC, ETH, SOL, MATIC).
    Prices are cached for 5 minutes to respect rate limits.
    """
    prices = await pricing_service.get_prices(['ADA', 'BTC', 'ETH', 'SOL', 'MATIC'])
    return {
        "prices": prices,
        "currency": "USD",
        "source": "CoinGecko"
    }


@router.get("/all")
async def get_all_prices():
    """
    Get prices for all tracked assets including DeFi tokens.
    """
    prices = await pricing_service.get_all_tracked_prices()
    return {
        "prices": prices,
        "currency": "USD",
        "source": "CoinGecko"
    }


@router.get("/search/{query}")
async def search_token(query: str):
    """
    Search for a cryptocurrency by ticker or name using CoinGecko.
    Returns price data if found.
    """
    try:
        # First try to search CoinGecko for the token
        client = get_client("coingecko", timeout=10.0)
        # Search for the coin
        search_response = await client.get(
            f"https://api.coingecko.com/api/v3/search?query={query}"
        )

        if search_response.status_code != 200:
            logger.error(f"CoinGecko search failed: {search_response.status_code}")
            raise HTTPException(status_code=500, detail="Search API unavailable")

        search_data = search_response.json()
        coins = search_data.get('coins', [])

        if not coins:
            return {
                "found": False,
                "message": f"No token found matching '{query}'"
            }

        # Get the first match (most relevant)
        coin = coins[0]
        coin_id = coin.get('id')

        logger.info(f"Found coin: {coin.get('name')} ({coin.get('symbol')}) - ID: {coin_id}")

        # Fetch detailed price data for this coin
        price_response = await client.get(
            f"https://api.coingecko.com/api/v3/coins/markets",
            params={
                'ids': coin_id,
                'vs_currency': 'usd',
                'price_change_percentage': '1h,24h'
            }
        )

        if price_response.status_code != 200:
            logger.error(f"CoinGecko price fetch failed: {price_response.status_code}")
            # Return basic info even if price fetch fails
            return {
                "found": True,
                "symbol": coin.get('symbol', '').upper(),
                "name": coin.get('name'),
                "coin_id": coin_id,
                "usd": None,
                "market_cap": None,
                "usd_1h_change": None,
                "usd_24h_change": None
            }

        price_data = price_response.json()

        if not price_data:
            return {
                "found": True,
                "symbol": coin.get('symbol', '').upper(),
                "name": coin.get('name'),
                "coin_id": coin_id,
                "usd": None,
                "market_cap": None,
                "usd_1h_change": None,
                "usd_24h_change": None
            }

        market_data = price_data[0]

        return {
            "found": True,
            "symbol": coin.get('symbol', '').upper(),
            "name": coin.get('name'),
            "coin_id": coin_id,
            "usd": market_data.get('current_price'),
            "market_cap": market_data.get('market_cap'),
            "usd_1h_change": market_data.get('price_change_percentage_1h_in_currency'),
            "usd_24h_change": market_data.get('price_change_percentage_24h_in_currency'),
            "thumb": coin.get('thumb'),
            "source": "CoinGecko"
        }

    except httpx.TimeoutException:
        logger.error(f"Timeout searching for token: {query}")
        raise HTTPException(status_code=504, detail="Search request timed out")
    except Exception as e:
        logger.error(f"Error searching for token {query}: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/global")
async def get_global_market():
    """
    Get global crypto market cap and 24h change percentage.
    Tries CMC first (saves CoinGecko calls), falls back to CoinGecko.
    """
    global _global_market_cache
    now = time.time()

    # Return cache if fresh (5 min)
    if _global_market_cache["data"] and now - _global_market_cache["timestamp"] < 300:
        return _global_market_cache["data"]

    # Try CMC first (save CoinGecko calls)
    try:
        from config import CMC_API_KEY, CMC_BASE_URL
        if CMC_API_KEY:
            client = get_client("coinmarketcap", timeout=10.0)
            response = await client.get(
                f"{CMC_BASE_URL}/global-metrics/quotes/latest",
                headers={
                    'X-CMC_PRO_API_KEY': CMC_API_KEY,
                    'Accept': 'application/json'
                }
            )
            if response.status_code == 200:
                cmc_data = response.json().get("data", {})
                quote = cmc_data.get("quote", {}).get("USD", {})
                result = {
                    "total_market_cap_usd": quote.get("total_market_cap", 0),
                    "market_cap_change_percentage_24h": quote.get("total_market_cap_yesterday_percentage_change", 0),
                    "total_volume_usd": quote.get("total_volume_24h", 0),
                    "btc_dominance": cmc_data.get("btc_dominance", 0),
                    "active_cryptocurrencies": cmc_data.get("active_cryptocurrencies", 0),
                    "source": "CoinMarketCap"
                }
                _global_market_cache = {"data": result, "timestamp": now}
                logger.info("Global market data from CoinMarketCap")
                return result
    except Exception as e:
        logger.debug(f"CMC global market failed, falling back to CoinGecko: {e}")

    # CoinGecko fallback
    try:
        client = get_client("coingecko", timeout=10.0)
        response = await client.get("https://api.coingecko.com/api/v3/global")

        if response.status_code == 200:
            data = response.json().get("data", {})
            result = {
                "total_market_cap_usd": data.get("total_market_cap", {}).get("usd", 0),
                "market_cap_change_percentage_24h": data.get("market_cap_change_percentage_24h_usd", 0),
                "total_volume_usd": data.get("total_volume", {}).get("usd", 0),
                "btc_dominance": data.get("market_cap_percentage", {}).get("btc", 0),
                "active_cryptocurrencies": data.get("active_cryptocurrencies", 0),
                "source": "CoinGecko"
            }
            _global_market_cache = {"data": result, "timestamp": now}
            return result
        elif response.status_code == 429:
            logger.warning("CoinGecko rate limited on /global")
            if _global_market_cache["data"]:
                return _global_market_cache["data"]
            return {"error": "Rate limited", "total_market_cap_usd": 0}
        else:
            logger.error(f"CoinGecko /global failed: {response.status_code}")
            if _global_market_cache["data"]:
                return _global_market_cache["data"]
            return {"error": "API error", "total_market_cap_usd": 0}
    except Exception as e:
        logger.error(f"Error fetching global market data: {e}")
        if _global_market_cache["data"]:
            return _global_market_cache["data"]
        return {"error": str(e), "total_market_cap_usd": 0}


@router.get("/trending")
async def get_trending():
    """Get trending coins."""
    trending = await pricing_service.get_trending_coins()
    return {"coins": trending, "source": "CoinGecko"}


@router.get("/stream/cardano")
async def stream_cardano_prices():
    """
    SSE endpoint for live Cardano token prices via Charli3 streaming.
    Falls back to polling if Charli3 streaming is unavailable.
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    import json

    async def event_generator():
        try:
            from services.charli3 import charli3_service
            if not await charli3_service.is_configured():
                yield f"data: {json.dumps({'error': 'Charli3 not configured'})}\n\n"
                return

            # Get pool IDs for tracked Cardano tokens
            from services.charli3 import CHARLI3_TOKEN_MAP
            pool_ids = list(CHARLI3_TOKEN_MAP.values())

            if not pool_ids:
                yield f"data: {json.dumps({'error': 'No Cardano tokens configured'})}\n\n"
                return

            try:
                async for event in charli3_service.stream_tokens(pool_ids):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                logger.warning(f"Charli3 stream failed, falling back to polling: {e}")
                # Fallback: poll every 30 seconds
                while True:
                    try:
                        prices = await charli3_service.get_token_prices_batch(pool_ids)
                        if prices:
                            yield f"data: {json.dumps({'prices': prices, 'source': 'poll'})}\n\n"
                    except Exception as pe:
                        logger.error(f"Charli3 poll error: {pe}")
                    await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/{symbol}")
async def get_price(symbol: str):
    """
    Get current USD price for a specific cryptocurrency.
    """
    price = await pricing_service.get_price(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "price_usd": price,
        "currency": "USD",
        "source": "CoinGecko"
    }
