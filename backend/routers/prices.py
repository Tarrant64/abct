"""
Pricing API Endpoints

Provides current cryptocurrency prices from CoinGecko.
"""

from fastapi import APIRouter, Query, HTTPException
import sys
import os
import httpx
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.pricing import pricing_service

router = APIRouter(prefix="/prices", tags=["prices"])
logger = logging.getLogger(__name__)


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
        async with httpx.AsyncClient(timeout=10.0) as client:
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
