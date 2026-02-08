"""
Price Enricher

Fetches historical prices using DefiLlama (free, no key) -> CoinGecko fallback.
Stores results in engine_price_history for reuse.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from engine import db as engine_db
from services.http_client import get_client
from services.pricing import ASSET_TO_COINGECKO

logger = logging.getLogger(__name__)

NATIVE_ASSET_MAP = {
    "cardano:native": "ADA",
    "bitcoin:native": "BTC",
    "ethereum:native": "ETH",
    "solana:native": "SOL",
    "polygon:native": "MATIC",
    "base:native": "ETH",
}

DEFILLAMA_BASE = "https://coins.llama.fi"


class PriceEnricher:
    """Fetches and caches historical prices for canonical events."""

    async def enrich_date(self, asset_id: str, chain: str, date: str) -> Optional[float]:
        """Get USD price for asset on a specific date (used by engine pipeline)."""
        return await self.fetch_historical_price(asset_id, chain, date)

    async def fetch_historical_price(self, asset_id: str, chain: str, date: str) -> Optional[float]:
        """Fetch historical price with DefiLlama -> CoinGecko fallback."""
        price_key = f"{chain}:{asset_id}"

        # Check engine cache first
        existing = await engine_db.get_prices(price_key, start_date=date, end_date=date)
        if existing:
            return existing[0]['price_usd']

        symbol = NATIVE_ASSET_MAP.get(price_key)
        if not symbol and asset_id == "native":
            symbol = NATIVE_ASSET_MAP.get(f"{chain}:native")
        if not symbol:
            return None

        cg_id = ASSET_TO_COINGECKO.get(symbol)
        if not cg_id:
            return None

        ts = int(datetime.strptime(date, '%Y-%m-%d').replace(hour=12).timestamp())

        # Try DefiLlama first (free, no API key)
        price = await self._fetch_from_defillama(cg_id, ts)
        source = "defillama"

        # Fallback to CoinGecko single-date endpoint
        if not price:
            price = await self._fetch_from_coingecko_date(cg_id, date)
            source = "coingecko"

        if price and price > 0:
            await engine_db.upsert_price(price_key, date, price, source)
            return price
        return None

    async def fetch_historical_prices_batch(self, symbol: str, dates: List[str]) -> Dict[str, float]:
        """Fetch historical prices for multiple dates. Returns {date: price}."""
        cg_id = ASSET_TO_COINGECKO.get(symbol)
        if not cg_id:
            return {}

        chain_for_symbol = {
            'ADA': 'cardano', 'BTC': 'bitcoin', 'ETH': 'ethereum',
            'SOL': 'solana', 'MATIC': 'polygon', 'ALGO': 'algorand',
        }
        chain = chain_for_symbol.get(symbol)
        if not chain:
            return {}
        price_key = f"{chain}:native"

        # Check engine cache -- only fetch dates we don't have
        cached = await engine_db.get_prices(price_key)
        cached_dates = {p['date'] for p in cached}
        missing_dates = [d for d in dates if d not in cached_dates]

        result = {p['date']: p['price_usd'] for p in cached if p['date'] in set(dates)}

        if not missing_dates:
            return result

        logger.info(f"Fetching {len(missing_dates)} historical prices for {symbol} ({len(result)} cached)")

        # Fetch missing dates from DefiLlama (one request per date, with delays)
        batch_to_store = []
        for i, date in enumerate(sorted(missing_dates)):
            ts = int(datetime.strptime(date, '%Y-%m-%d').replace(hour=12).timestamp())
            price = await self._fetch_from_defillama(cg_id, ts)
            source = "defillama"

            if not price:
                price = await self._fetch_from_coingecko_date(cg_id, date)
                source = "coingecko"

            if price and price > 0:
                result[date] = price
                batch_to_store.append({
                    'asset_id': price_key, 'date': date,
                    'price_usd': price, 'source': source,
                })

            # Rate limit: ~2 requests/sec for DefiLlama
            if (i + 1) % 2 == 0 and i < len(missing_dates) - 1:
                await asyncio.sleep(1)

            # Periodic batch store every 50 prices
            if len(batch_to_store) >= 50:
                await engine_db.upsert_prices_batch(batch_to_store)
                batch_to_store = []

            # Progress logging every 100 dates
            if (i + 1) % 100 == 0:
                logger.info(f"  {symbol}: {i+1}/{len(missing_dates)} prices fetched")

        # Store remaining
        if batch_to_store:
            await engine_db.upsert_prices_batch(batch_to_store)

        logger.info(f"Fetched {len(result)} total prices for {symbol}")
        return result

    async def _fetch_from_defillama(self, cg_id: str, timestamp: int) -> Optional[float]:
        """Fetch single historical price from DefiLlama."""
        try:
            client = get_client("defilama", timeout=30.0)
            url = f"{DEFILLAMA_BASE}/prices/historical/{timestamp}/coingecko:{cg_id}"
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                coin_data = data.get('coins', {}).get(f'coingecko:{cg_id}', {})
                return coin_data.get('price')
        except Exception as e:
            logger.debug(f"DefiLlama historical price error for {cg_id}: {e}")
        return None

    async def _fetch_from_coingecko_date(self, cg_id: str, date: str) -> Optional[float]:
        """Fetch single historical price from CoinGecko /coins/{id}/history endpoint."""
        try:
            # CoinGecko expects DD-MM-YYYY format
            dt = datetime.strptime(date, '%Y-%m-%d')
            cg_date = dt.strftime('%d-%m-%Y')

            client = get_client("coingecko_historical", timeout=30.0)
            response = await client.get(
                f"https://api.coingecko.com/api/v3/coins/{cg_id}/history",
                params={'date': cg_date, 'localization': 'false'}
            )
            if response.status_code == 200:
                data = response.json()
                market_data = data.get('market_data', {})
                current_price = market_data.get('current_price', {})
                return current_price.get('usd')
            elif response.status_code == 429:
                await asyncio.sleep(65)
        except Exception as e:
            logger.debug(f"CoinGecko historical price error for {cg_id} on {date}: {e}")
        return None

    async def enrich_events_batch(self, events: list, chain: str) -> Dict[str, float]:
        """Enrich a batch of events with prices."""
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
