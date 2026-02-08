"""
Price Enricher

Wraps the existing pricing_service to fetch historical prices for events.
Stores results in engine_price_history for reuse.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from engine import db as engine_db

logger = logging.getLogger(__name__)

# Asset ID → CoinGecko ID mapping for native assets
NATIVE_ASSET_MAP = {
    "cardano:native": "ADA",
    "bitcoin:native": "BTC",
    "ethereum:native": "ETH",
    "solana:native": "SOL",
    "polygon:native": "MATIC",
    "base:native": "ETH",
}


class PriceEnricher:
    """Fetches and caches historical prices for canonical events."""

    async def enrich_date(self, asset_id: str, chain: str, date: str) -> Optional[float]:
        """
        Get the USD price for an asset on a specific date.

        Args:
            asset_id: The asset identifier (e.g., 'native', contract address).
            chain: The chain name.
            date: Date string (YYYY-MM-DD).

        Returns:
            Price in USD or None if unavailable.
        """
        # Build a canonical price key
        price_key = f"{chain}:{asset_id}"

        # Check cache first
        existing = await engine_db.get_prices(price_key, start_date=date, end_date=date)
        if existing:
            return existing[0]['price_usd']

        # Resolve to a symbol the pricing service understands
        symbol = NATIVE_ASSET_MAP.get(price_key)
        if not symbol and asset_id == "native":
            symbol = NATIVE_ASSET_MAP.get(f"{chain}:native")

        if not symbol:
            # For non-native tokens, we'd need token metadata to resolve
            # For now, skip non-native tokens
            return None

        # Use the pricing service to get the price
        try:
            from services.pricing import pricing_service
            prices = await pricing_service.get_prices([symbol])
            price = prices.get(symbol)
            if price:
                await engine_db.upsert_price(price_key, date, price, "pricing_service")
                return price
        except Exception as e:
            logger.warning(f"Price enrichment failed for {price_key} on {date}: {e}")

        return None

    async def enrich_events_batch(self, events: list, chain: str) -> Dict[str, float]:
        """
        Enrich a batch of events with prices.

        Returns a map of {date: price} for native assets.
        """
        dates = set()
        for evt in events:
            if evt.get('block_time'):
                dt = datetime.utcfromtimestamp(evt['block_time'])
                dates.add(dt.strftime('%Y-%m-%d'))

        prices = {}
        for date in sorted(dates):
            price = await self.enrich_date("native", chain, date)
            if price:
                prices[date] = price

        return prices


price_enricher = PriceEnricher()
