"""
Demo Price Service - Returns fake cryptocurrency prices

Provides mock price data for demo accounts:
- Realistic crypto prices (close to real market)
- Mock price history
- Fake 24h change percentages
- No real API calls to CoinGecko, CoinMarketCap, etc.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import random


class DemoPriceService:
    """Service for returning fake price data in demo mode."""

    def __init__(self):
        """Initialize demo price service with realistic mock prices."""
        # Base prices (somewhat realistic as of early 2025)
        self.base_prices = {
            # Major cryptocurrencies
            "ADA": 1.05,
            "BTC": 98000.00,
            "ETH": 3500.00,
            "SOL": 180.00,
            "MATIC": 0.90,
            "POL": 0.90,  # Polygon rebranded

            # Stablecoins
            "USDC": 1.00,
            "USDT": 1.00,
            "DAI": 1.00,

            # Cardano DeFi tokens
            "INDY": 0.85,
            "LQ": 0.042,
            "MIN": 0.045,
            "SUNDAE": 0.012,
            "WRT": 0.085,
            "DJED": 1.00,
            "SHEN": 0.25,
            "LENFI": 0.65,
            "SNEK": 0.0012,
            "STRIKE": 0.015,
            "IAG": 0.055,
            "AGIX": 0.72,
            "XER": 0.025,
            "NIGHT": 0.18,
            "FLOW": 0.028,

            # Other popular tokens
            "LINK": 22.50,
            "UNI": 12.80,
            "AAVE": 185.00,
            "DOT": 8.50,
            "AVAX": 42.00,
        }

        # 24h change percentages (randomized but realistic)
        self.price_changes_24h = {}
        for symbol in self.base_prices.keys():
            # Most coins have small changes, some have larger swings
            if random.random() < 0.2:  # 20% chance of larger move
                change = random.uniform(-8, 12)
            else:
                change = random.uniform(-3, 4)
            self.price_changes_24h[symbol] = round(change, 2)

    async def get_price(self, symbol: str) -> float:
        """
        Get current price for a cryptocurrency.

        Args:
            symbol: Cryptocurrency symbol (e.g., "ADA", "BTC")

        Returns:
            Price in USD
        """
        # Add small random variation to make it feel live
        base_price = self.base_prices.get(symbol.upper(), 0)
        if base_price > 0:
            variation = random.uniform(-0.005, 0.005)  # ±0.5% variation
            return base_price * (1 + variation)
        return 0

    async def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get prices for multiple cryptocurrencies.

        Args:
            symbols: List of cryptocurrency symbols

        Returns:
            Dict mapping symbols to prices
        """
        prices = {}
        for symbol in symbols:
            prices[symbol] = await self.get_price(symbol)
        return prices

    async def get_price_with_change(self, symbol: str) -> Dict:
        """
        Get price with 24h change data.

        Args:
            symbol: Cryptocurrency symbol

        Returns:
            Dict with price and change data
        """
        price = await self.get_price(symbol)
        change_24h = self.price_changes_24h.get(symbol.upper(), 0)

        return {
            "symbol": symbol.upper(),
            "price_usd": price,
            "change_24h": change_24h,
            "price_24h_ago": price / (1 + change_24h / 100),
            "updated_at": datetime.now().isoformat()
        }

    async def get_price_history(
        self,
        symbol: str,
        days: int = 30
    ) -> List[Dict]:
        """
        Get historical price data for a cryptocurrency.

        Args:
            symbol: Cryptocurrency symbol
            days: Number of days of history

        Returns:
            List of price data points
        """
        current_price = self.base_prices.get(symbol.upper(), 0)
        if current_price == 0:
            return []

        history = []
        price = current_price

        # Work backwards from current price
        for i in range(days):
            date = datetime.now() - timedelta(days=days - i - 1)

            # Random daily change (±3% typical, ±8% rare)
            if random.random() < 0.1:  # 10% chance of larger move
                daily_change = random.uniform(-0.08, 0.08)
            else:
                daily_change = random.uniform(-0.03, 0.03)

            # Calculate price for this day (working backwards)
            if i == 0:
                price = current_price
            else:
                # Apply inverse of change to go backwards
                price = price / (1 + daily_change)

            history.append({
                "date": date.date().isoformat(),
                "timestamp": int(date.timestamp()),
                "price_usd": round(price, 6),
                "volume_24h": round(random.uniform(100000, 10000000), 2)
            })

        return history

    async def get_market_data(self, symbol: str) -> Dict:
        """
        Get comprehensive market data for a cryptocurrency.

        Args:
            symbol: Cryptocurrency symbol

        Returns:
            Dict with price, volume, market cap, etc.
        """
        price = await self.get_price(symbol)
        change_24h = self.price_changes_24h.get(symbol.upper(), 0)

        # Generate fake but realistic volume and market cap
        if symbol.upper() in ["BTC", "ETH"]:
            volume_24h = random.uniform(20e9, 50e9)  # $20B-$50B
            market_cap = price * random.uniform(1e9, 2e9)  # Fake supply
        elif symbol.upper() == "ADA":
            volume_24h = random.uniform(500e6, 2e9)  # $500M-$2B
            market_cap = price * 35e9  # ~35B ADA supply
        else:
            volume_24h = random.uniform(10e6, 500e6)  # $10M-$500M
            market_cap = price * random.uniform(100e6, 1e9)

        return {
            "symbol": symbol.upper(),
            "price_usd": price,
            "change_24h": change_24h,
            "volume_24h": volume_24h,
            "market_cap": market_cap,
            "high_24h": price * (1 + abs(change_24h) / 100 + 0.01),
            "low_24h": price * (1 - abs(change_24h) / 100 - 0.01),
            "all_time_high": price * random.uniform(1.5, 5.0),
            "all_time_low": price * random.uniform(0.1, 0.5),
            "circulating_supply": market_cap / price if price > 0 else 0,
            "updated_at": datetime.now().isoformat()
        }

    async def get_trending_tokens(self, limit: int = 10) -> List[Dict]:
        """
        Get trending tokens (fake trending list).

        Args:
            limit: Number of trending tokens to return

        Returns:
            List of trending token data
        """
        # Pick random tokens from our list
        symbols = list(self.base_prices.keys())
        random.shuffle(symbols)
        trending = symbols[:limit]

        trending_data = []
        for symbol in trending:
            data = await self.get_price_with_change(symbol)
            trending_data.append({
                **data,
                "trending_rank": len(trending_data) + 1,
                "volume_24h": random.uniform(1e6, 100e6)
            })

        # Sort by absolute change (biggest movers)
        trending_data.sort(key=lambda x: abs(x["change_24h"]), reverse=True)

        return trending_data

    async def search_tokens(self, query: str) -> List[Dict]:
        """
        Search for tokens by name or symbol.

        Args:
            query: Search query

        Returns:
            List of matching tokens
        """
        query = query.upper()
        results = []

        for symbol in self.base_prices.keys():
            if query in symbol:
                price = await self.get_price(symbol)
                results.append({
                    "symbol": symbol,
                    "name": self._get_token_name(symbol),
                    "price_usd": price,
                    "change_24h": self.price_changes_24h.get(symbol, 0)
                })

        return results[:10]  # Return top 10 matches

    def _get_token_name(self, symbol: str) -> str:
        """Get full name for a token symbol."""
        names = {
            "ADA": "Cardano",
            "BTC": "Bitcoin",
            "ETH": "Ethereum",
            "SOL": "Solana",
            "MATIC": "Polygon",
            "POL": "Polygon",
            "USDC": "USD Coin",
            "USDT": "Tether",
            "DAI": "Dai",
            "INDY": "Indigo Protocol",
            "LQ": "Liqwid",
            "MIN": "Minswap",
            "SUNDAE": "SundaeSwap",
            "SNEK": "Snek",
            "AGIX": "SingularityNET",
            "LINK": "Chainlink",
            "UNI": "Uniswap",
            "AAVE": "Aave",
            "DOT": "Polkadot",
            "AVAX": "Avalanche"
        }
        return names.get(symbol.upper(), symbol)


# Global instance
demo_price_service = DemoPriceService()
