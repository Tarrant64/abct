"""
Pricing API Endpoints

Provides current cryptocurrency prices from CoinGecko.
"""

from fastapi import APIRouter
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.pricing import pricing_service

router = APIRouter(prefix="/prices", tags=["prices"])


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
