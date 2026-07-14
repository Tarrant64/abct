"""
Pricing API Endpoints

Provides current cryptocurrency prices from CoinGecko with
CoinPaprika and DefiLlama fallbacks.
"""

from fastapi import APIRouter, Query, HTTPException, Depends
import sys
import os
import httpx
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.pricing import pricing_service
from services.http_client import get_client
from auth_utils import verify_session, verify_session_sse

router = APIRouter(prefix="/prices", tags=["prices"])
logger = logging.getLogger(__name__)

# Cache for global market data (5 min TTL)
_global_market_cache = {"data": None, "timestamp": 0}


@router.get("")
async def get_prices(_user_id: int = Depends(verify_session)):
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
async def get_all_prices(_user_id: int = Depends(verify_session)):
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
async def search_token(query: str, _user_id: int = Depends(verify_session)):
    """
    Search for a cryptocurrency by ticker or name.
    Tries CoinGecko first, falls back to CoinPaprika.
    """
    # --- Try CoinGecko first ---
    try:
        client = get_client("coingecko", timeout=10.0)
        search_response = await client.get(
            f"https://api.coingecko.com/api/v3/search?query={query}"
        )

        if search_response.status_code == 200:
            search_data = search_response.json()
            coins = search_data.get('coins', [])

            if coins:
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

                if price_response.status_code == 200:
                    price_data = price_response.json()
                    if price_data:
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

                # Price fetch failed but we found the coin
                return {
                    "found": True,
                    "symbol": coin.get('symbol', '').upper(),
                    "name": coin.get('name'),
                    "coin_id": coin_id,
                    "usd": None,
                    "market_cap": None,
                    "usd_1h_change": None,
                    "usd_24h_change": None,
                    "source": "CoinGecko"
                }

            # CoinGecko returned 200 but no results — fall through to CoinPaprika
            logger.debug(f"CoinGecko search returned no results for '{query}', trying CoinPaprika")
        else:
            logger.warning(f"CoinGecko search returned {search_response.status_code}, trying CoinPaprika")

    except Exception as e:
        logger.warning(f"CoinGecko search failed for '{query}': {e}, trying CoinPaprika")

    # --- CoinPaprika fallback ---
    try:
        cp_client = get_client("coinpaprika", timeout=10.0)
        cp_response = await cp_client.get(
            "https://api.coinpaprika.com/v1/search",
            params={"q": query, "c": "currencies", "limit": 10}
        )

        if cp_response.status_code == 200:
            cp_data = cp_response.json()
            cp_coins = cp_data.get("currencies", [])

            if cp_coins:
                cp_coin = cp_coins[0]
                cp_id = cp_coin.get("id", "")

                # Fetch ticker data for price info
                ticker_resp = await cp_client.get(
                    f"https://api.coinpaprika.com/v1/tickers/{cp_id}"
                )

                if ticker_resp.status_code == 200:
                    ticker = ticker_resp.json()
                    quotes = ticker.get("quotes", {}).get("USD", {})
                    return {
                        "found": True,
                        "symbol": (cp_coin.get("symbol") or "").upper(),
                        "name": cp_coin.get("name"),
                        "coin_id": cp_id,
                        "usd": quotes.get("price"),
                        "market_cap": quotes.get("market_cap"),
                        "usd_1h_change": quotes.get("percent_change_1h"),
                        "usd_24h_change": quotes.get("percent_change_24h"),
                        "thumb": None,
                        "source": "CoinPaprika"
                    }

                # Ticker fetch failed, return basic info
                return {
                    "found": True,
                    "symbol": (cp_coin.get("symbol") or "").upper(),
                    "name": cp_coin.get("name"),
                    "coin_id": cp_id,
                    "usd": None,
                    "market_cap": None,
                    "usd_1h_change": None,
                    "usd_24h_change": None,
                    "source": "CoinPaprika"
                }

        logger.warning(f"CoinPaprika search also failed for '{query}'")
    except Exception as e:
        logger.error(f"CoinPaprika search failed for '{query}': {e}")

    return {
        "found": False,
        "message": f"No token found matching '{query}'"
    }


@router.get("/global")
async def get_global_market(_user_id: int = Depends(verify_session)):
    """
    Get global crypto market cap and 24h change percentage.
    Tries CMC first, then CoinGecko, then CoinPaprika.
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
        else:
            logger.warning(f"CoinGecko /global returned {response.status_code}, trying CoinPaprika")
    except Exception as e:
        logger.debug(f"CoinGecko global market failed: {e}")

    # CoinPaprika fallback
    try:
        cp_client = get_client("coinpaprika", timeout=10.0)
        cp_response = await cp_client.get("https://api.coinpaprika.com/v1/global")

        if cp_response.status_code == 200:
            cp_data = cp_response.json()
            result = {
                "total_market_cap_usd": cp_data.get("market_cap_usd", 0),
                "market_cap_change_percentage_24h": cp_data.get("market_cap_change_24h", 0),
                "total_volume_usd": cp_data.get("volume_24h_usd", 0),
                "btc_dominance": cp_data.get("bitcoin_dominance_percentage", 0),
                "active_cryptocurrencies": cp_data.get("cryptocurrencies_number", 0),
                "source": "CoinPaprika"
            }
            _global_market_cache = {"data": result, "timestamp": now}
            logger.info("Global market data from CoinPaprika")
            return result
        else:
            logger.warning(f"CoinPaprika /global returned {cp_response.status_code}")
    except Exception as e:
        logger.debug(f"CoinPaprika global market failed: {e}")

    # Stale cache as last resort
    if _global_market_cache["data"]:
        return _global_market_cache["data"]
    return {"error": "All global market sources failed", "total_market_cap_usd": 0}


@router.get("/trending")
async def get_trending(_user_id: int = Depends(verify_session)):
    """Get trending coins. Falls back to CoinPaprika top gainers if CoinGecko is empty."""
    trending = await pricing_service.get_trending_coins()
    if trending:
        return {"coins": trending, "source": "CoinGecko"}

    # CoinPaprika fallback — use top tickers sorted by 24h change as "trending"
    logger.debug("CoinGecko trending empty, trying CoinPaprika tickers")
    try:
        cp_client = get_client("coinpaprika", timeout=10.0)
        cp_response = await cp_client.get(
            "https://api.coinpaprika.com/v1/tickers",
            params={"limit": 50}
        )
        if cp_response.status_code == 200:
            tickers = cp_response.json()
            # Sort by absolute 24h change to find "trending" coins
            for t in tickers:
                t["_abs_change"] = abs((t.get("quotes", {}).get("USD", {}).get("percent_change_24h") or 0))
            tickers.sort(key=lambda t: t["_abs_change"], reverse=True)

            cp_trending = []
            for t in tickers[:15]:
                quotes = t.get("quotes", {}).get("USD", {})
                cp_trending.append({
                    "name": t.get("name"),
                    "symbol": (t.get("symbol") or "").upper(),
                    "price": quotes.get("price"),
                    "change_24h": quotes.get("percent_change_24h"),
                    "market_cap": quotes.get("market_cap"),
                })
            return {"coins": cp_trending, "source": "CoinPaprika"}
    except Exception as e:
        logger.error(f"CoinPaprika trending fallback failed: {e}")

    return {"coins": [], "source": "none"}


@router.get("/top-movers")
async def get_top_movers(
    min_change: float = 3.0,
    min_mcap: float = 100_000_000,
    limit: int = 15,
    _user_id: int = Depends(verify_session)
):
    """
    Get top movers in last 24h: coins with >min_change% absolute price change
    and >min_mcap market cap. Returns sorted by absolute 24h change descending.
    """
    cache_key = f"prices:top_movers:{min_change}:{min_mcap}"
    from database import get_cache, set_cache
    from config import CACHE_TTL_HOT

    cached = await get_cache(cache_key)
    if cached:
        return {"success": True, "movers": cached, "source": "cache"}

    source = "CoinGecko"
    coins_data = None

    # --- Try CoinGecko first ---
    try:
        client = get_client("coingecko", timeout=15.0)
        resp = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "price_change_percentage": "24h",
                "sparkline": "false",
            }
        )

        if resp.status_code == 200:
            raw = resp.json()
            coins_data = []
            for coin in raw:
                coins_data.append({
                    "name": coin.get("name"),
                    "symbol": (coin.get("symbol") or "").upper(),
                    "image": coin.get("image"),
                    "price": coin.get("current_price"),
                    "market_cap": coin.get("market_cap") or 0,
                    "change_24h": coin.get("price_change_percentage_24h") or 0,
                    "volume_24h": coin.get("total_volume") or 0,
                })
        else:
            logger.warning(f"CoinGecko markets returned {resp.status_code}, trying CoinPaprika")
    except Exception as e:
        logger.warning(f"CoinGecko top movers failed: {e}, trying CoinPaprika")

    # --- CoinPaprika fallback ---
    if coins_data is None:
        try:
            cp_client = get_client("coinpaprika", timeout=15.0)
            cp_resp = await cp_client.get(
                "https://api.coinpaprika.com/v1/tickers",
                params={"limit": 250}
            )

            if cp_resp.status_code == 200:
                source = "CoinPaprika"
                tickers = cp_resp.json()
                coins_data = []
                for t in tickers:
                    quotes = t.get("quotes", {}).get("USD", {})
                    coins_data.append({
                        "name": t.get("name"),
                        "symbol": (t.get("symbol") or "").upper(),
                        "image": None,
                        "price": quotes.get("price"),
                        "market_cap": quotes.get("market_cap") or 0,
                        "change_24h": quotes.get("percent_change_24h") or 0,
                        "volume_24h": quotes.get("volume_24h") or 0,
                    })
            else:
                logger.error(f"CoinPaprika tickers returned {cp_resp.status_code}")
        except Exception as e:
            logger.error(f"CoinPaprika top movers also failed: {e}")

    if coins_data is None:
        return {"success": False, "error": "All market data sources failed", "movers": []}

    # Filter and sort
    movers = []
    for coin in coins_data:
        mcap = coin["market_cap"]
        change_24h = coin["change_24h"]
        if mcap >= min_mcap and abs(change_24h) >= min_change:
            coin["change_24h"] = round(change_24h, 2)
            movers.append(coin)

    movers.sort(key=lambda x: abs(x["change_24h"]), reverse=True)
    movers = movers[:limit]

    await set_cache(cache_key, movers, CACHE_TTL_HOT)
    return {"success": True, "movers": movers, "source": source}


@router.get("/top-assets")
async def get_top_assets(
    limit: int = 20,
    _user_id: int = Depends(verify_session)
):
    """
    Top coins by market cap: symbol, name, price, 24h change. Consumed by the
    mobile app's watch complication gallery (WATCH-5), which lets users track
    prices of tokens they don't hold.

    Unlike /top-movers this is cap-ordered and unfiltered, and its cache key
    INCLUDES limit — top-movers' key omits it, so differing-limit callers
    would poison each other's cached view (a trap this endpoint must avoid).
    """
    limit = max(1, min(limit, 50))
    cache_key = f"prices:top_assets:{limit}"
    from database import get_cache, set_cache
    from config import CACHE_TTL_HOT

    cached = await get_cache(cache_key)
    if cached:
        return {"success": True, "assets": cached, "source": "cache"}

    source = "CoinGecko"
    assets = None

    # --- Try CoinGecko first ---
    try:
        client = get_client("coingecko", timeout=15.0)
        resp = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "price_change_percentage": "24h",
                "sparkline": "false",
            }
        )

        if resp.status_code == 200:
            raw = resp.json()
            assets = []
            # Slice defensively — never trust upstream to honor per_page.
            for coin in raw[:limit]:
                assets.append({
                    "symbol": (coin.get("symbol") or "").upper(),
                    "name": coin.get("name"),
                    "price": coin.get("current_price"),
                    "change_24h": round(coin.get("price_change_percentage_24h") or 0, 2),
                })
        else:
            logger.warning(f"CoinGecko markets returned {resp.status_code}, trying CoinPaprika")
    except Exception as e:
        logger.warning(f"CoinGecko top assets failed: {e}, trying CoinPaprika")

    # --- CoinPaprika fallback ---
    if assets is None:
        try:
            cp_client = get_client("coinpaprika", timeout=15.0)
            cp_resp = await cp_client.get(
                "https://api.coinpaprika.com/v1/tickers",
                params={"limit": 250}
            )

            if cp_resp.status_code == 200:
                source = "CoinPaprika"
                tickers = cp_resp.json()
                ranked = sorted(
                    tickers,
                    key=lambda t: (t.get("quotes", {}).get("USD", {}).get("market_cap") or 0),
                    reverse=True,
                )
                assets = []
                for t in ranked[:limit]:
                    quotes = t.get("quotes", {}).get("USD", {})
                    assets.append({
                        "symbol": (t.get("symbol") or "").upper(),
                        "name": t.get("name"),
                        "price": quotes.get("price"),
                        "change_24h": round(quotes.get("percent_change_24h") or 0, 2),
                    })
            else:
                logger.error(f"CoinPaprika tickers returned {cp_resp.status_code}")
        except Exception as e:
            logger.error(f"CoinPaprika top assets also failed: {e}")

    if assets is None:
        return {"success": False, "error": "All market data sources failed", "assets": []}

    await set_cache(cache_key, assets, CACHE_TTL_HOT)
    return {"success": True, "assets": assets, "source": source}


@router.get("/quota")
async def get_quota(_user_id: int = Depends(verify_session)):
    """Get CoinGecko API usage stats with warning thresholds."""
    try:
        client = get_client("coingecko", timeout=10.0)
        cg_headers = await pricing_service._get_cg_headers()
        if not cg_headers:
            return {"configured": False, "message": "No CoinGecko API key configured"}

        response = await client.get(
            "https://api.coingecko.com/api/v3/key",
            headers=cg_headers
        )
        if response.status_code == 200:
            data = response.json()
            current = data.get("current_total_monthly_calls", 0)
            limit = data.get("monthly_call_credit", 10000)
            pct = (current / limit * 100) if limit > 0 else 0
            return {
                "configured": True,
                "current_calls": current,
                "monthly_limit": limit,
                "usage_percent": round(pct, 1),
                "status": "critical" if pct >= 95 else "warning" if pct >= 80 else "ok",
                "message": f"{current:,}/{limit:,} calls ({pct:.1f}%)"
            }
        return {"configured": True, "error": f"API returned {response.status_code}"}
    except Exception as e:
        return {"configured": False, "error": str(e)}


@router.get("/stream/cardano")
async def stream_cardano_prices(_user_id: int = Depends(verify_session_sse)):
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
async def get_price(symbol: str, _user_id: int = Depends(verify_session)):
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
