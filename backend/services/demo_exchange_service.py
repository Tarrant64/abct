"""
Demo Exchange Service - Returns fake exchange balances

Provides mock exchange data for demo accounts:
- Fake Coinbase balances
- Mock exchange holdings
- No real API calls

All data is pre-defined and realistic but entirely fake.
"""

from typing import Dict, List
from datetime import datetime


class DemoExchangeService:
    """Service for returning fake exchange data in demo mode."""

    def __init__(self):
        """Initialize demo exchange service with fake balances."""
        # Demo Coinbase holdings
        self.coinbase_balances = [
            {
                "currency": "BTC",
                "balance": 0.5,
                "available": 0.5,
                "price_usd": 98000.00,
                "value_usd": 0.5 * 98000.00,  # $49,000
                "name": "Bitcoin"
            },
            {
                "currency": "ETH",
                "balance": 8.0,
                "available": 8.0,
                "price_usd": 3000.00,
                "value_usd": 8.0 * 3000.00,  # $24,000
                "name": "Ethereum"
            },
            {
                "currency": "ADA",
                "balance": 25000.0,
                "available": 25000.0,
                "price_usd": 0.95,
                "value_usd": 25000.0 * 0.95,  # $23,750
                "name": "Cardano"
            },
            {
                "currency": "SOL",
                "balance": 150.0,
                "available": 150.0,
                "price_usd": 140.00,
                "value_usd": 150.0 * 140.00,  # $21,000
                "name": "Solana"
            },
            {
                "currency": "MATIC",
                "balance": 15000.0,
                "available": 15000.0,
                "price_usd": 0.75,
                "value_usd": 15000.0 * 0.75,  # $11,250
                "name": "Polygon"
            }
        ]

    async def get_portfolio_balances(self, user_id: int = None) -> Dict:
        """
        Get demo Coinbase portfolio balances.

        Args:
            user_id: User ID (ignored in demo mode)

        Returns:
            Dict with demo exchange balances
        """
        total_usd = sum(asset["value_usd"] for asset in self.coinbase_balances)

        return {
            "exchange": "coinbase",
            "configured": True,
            "assets": self.coinbase_balances,
            "total_usd": total_usd,
            "asset_count": len(self.coinbase_balances),
            "updated_at": datetime.now().isoformat(),
            "demo_mode": True
        }

    async def get_spot_price(self, currency_pair: str) -> float:
        """
        Get demo spot price for a currency pair.

        Args:
            currency_pair: Currency pair (e.g., "BTC-USD")

        Returns:
            Demo spot price
        """
        # Extract base currency
        base_currency = currency_pair.split("-")[0]

        # Find matching asset
        for asset in self.coinbase_balances:
            if asset["currency"] == base_currency:
                return asset["price_usd"]

        return 0.0

    async def get_open_orders(self, user_id: int = None) -> List[Dict]:
        """
        Get demo open orders (always empty for demo).

        Args:
            user_id: User ID (ignored in demo mode)

        Returns:
            Empty list (demo has no open orders)
        """
        return []

    def is_configured(self) -> bool:
        """Check if exchange is configured (always True for demo)."""
        return True


# Global instance
demo_exchange_service = DemoExchangeService()
