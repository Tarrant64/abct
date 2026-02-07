"""
Pricing Service - Fetches cryptocurrency prices with fallback sources.

Sources (in order of priority):
1. CoinGecko (free tier, ~10-30 calls/minute) - Primary source for all tokens
2. CoinMarketCap (requires API key) - Fallback with rich market data
3. Coinbase (free, no key required) - Fallback for major coins (BTC, ETH, ADA, SOL, MATIC)
4. DefiLlama (free, no key required) - Universal fallback for all chains
5. TapTools (Cardano tokens, requires API key) - Cardano-specific with detailed data

DefiLlama API supports:
- Major coins via coingecko: prefix
- Cardano tokens via cardano:policyId format
- EVM tokens via chain:address format (ethereum, polygon, base, etc.)
See: https://api-docs.defillama.com/llms.txt
"""

import httpx
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TAPTOOLS_API_KEY, CEXPLORER_API_KEY, TAPTOOLS_BASE_URL, CEXPLORER_BASE_URL, CMC_API_KEY, CMC_BASE_URL
from services.http_client import get_client, fetch_with_retry

logger = logging.getLogger(__name__)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINBASE_BASE_URL = "https://api.coinbase.com/v2"

# Map our asset names to CoinGecko IDs
ASSET_TO_COINGECKO = {
    'ADA': 'cardano',
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'ALGO': 'algorand',
    'MATIC': 'polygon-ecosystem-token',  # POL (ex-MATIC)
    # Stablecoins
    'USDC': 'usd-coin',
    'USDT': 'tether',
    'DAI': 'dai',
    # DeFi tokens
    'INDY': 'indigo-dao-governance-token',
    'LQ': 'liqwid-finance',
    'MIN': 'minswap',
    'SUNDAE': 'sundaeswap',
    'WRT': 'wingriders',
    'DJED': 'djed',
    'SHEN': 'shen',
    'LENFI': 'aada-finance',
    'AGIX': 'singularitynet',
    'SNEK': 'snek',
    'STRIKE': 'strike-finance',
    'IAG': 'iagon',
    'XER': 'xerberus',
    'NIGHT': 'midnight-3',
    'FLOW': 'flow-lending',
}

# Map our asset names to CoinMarketCap symbols
# CMC uses symbols directly, but some need special handling
ASSET_TO_CMC = {
    'ADA': 'ADA',
    'BTC': 'BTC',
    'ETH': 'ETH',
    'SOL': 'SOL',
    'ALGO': 'ALGO',
    'MATIC': 'POL',  # Polygon rebranded to POL
    'USDC': 'USDC',
    'USDT': 'USDT',
    'DAI': 'DAI',
    'INDY': 'INDY',
    'MIN': 'MIN',
    'SNEK': 'SNEK',
    'AGIX': 'AGIX',
}

# Map token symbols to their policy IDs and asset names for TapTools/CExplorer
# Format: {symbol: (policy_id, hex_asset_name)}
CARDANO_TOKEN_POLICIES = {
    'INDY': ('533bb94a8850ee3ccbe483106489399112b74c905342cb1792a797a0', '494e4459'),
    'LQ': ('da8c30857834c6ae7203935b89278c532b3995245295456f993e1d24', '4c51'),
    'MIN': ('29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c6', '4d494e'),
    'SUNDAE': ('9a9693a9a37912a5097918f97918d15240c92ab729a0b7c4aa144d77', '53554e444145'),
    'DJED': ('8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61', '446a65644d6963726f555344'),
    'SHEN': ('8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61', '5368656e4d6963726f555344'),
    'SNEK': ('279c909f348e533da5808898f87f9a14bb2c3dfbbacccd631d927a3f', '534e454b'),
    'STRIKE': ('f13ac4d66b3ee19a6aa0f2a22298737bd907cc95121662fc971b5275', '535452494b45'),
    'IAG': ('5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114', '494147'),
    'AGIX': ('f43a62fdc3965df486de8a0d32fe800963589c41b38946602a0dc535', '41474958'),
    'XER': ('6d06570ddd778ec7c0cca09d381eca194e90c8cffa7582879735dbde', '584552'),
    'NIGHT': ('0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa', '4e49474854'),
    'FLOW': ('2d9db8a89f074aa045eab177f23a3395f62ced8b53499a9e4ad46c80', '464c4f57'),
}


class PricingService:
    """Service for fetching and caching cryptocurrency prices with fallback sources."""

    def __init__(self):
        self.cache: Dict[str, dict] = {}
        self.cache_duration = timedelta(minutes=5)
        self.last_fetch: Optional[datetime] = None
        # CoinGecko cooldown: skip CoinGecko for 60s after a 429
        self._coingecko_cooldown_until: Optional[datetime] = None
        # Stale cache: backup of last known good prices for graceful degradation
        self._stale_cache: Dict[str, dict] = {}

    async def get_prices(self, symbols: list = None, force_refresh: bool = False) -> Dict[str, float]:
        """
        Get current USD prices for specified symbols.
        Uses multiple sources with fallback logic.
        """
        if symbols is None:
            symbols = ['ADA', 'BTC', 'ETH']

        # Check cache - but only return if all symbols have VALID (non-zero) prices
        if not force_refresh and self._is_cache_valid():
            all_cached_and_valid = all(
                s in self.cache and self.cache.get(s, {}).get('usd', 0) > 0
                for s in symbols
                if ASSET_TO_COINGECKO.get(s.upper()) or s.upper() in CARDANO_TOKEN_POLICIES
            )
            if all_cached_and_valid:
                return {s: self.cache.get(s, {}).get('usd', 0) for s in symbols}

        # First try CoinGecko for all known symbols (skip if in cooldown from recent 429)
        if self._coingecko_cooldown_until and datetime.now() < self._coingecko_cooldown_until:
            logger.info(f"Skipping CoinGecko (cooldown until {self._coingecko_cooldown_until.strftime('%H:%M:%S')}), going straight to fallbacks")
        else:
            await self._fetch_from_coingecko(symbols)

        # Check for missing symbols and try CoinMarketCap as fallback
        missing_for_cmc = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0
                          and s.upper() in ASSET_TO_CMC]
        if missing_for_cmc and CMC_API_KEY:
            logger.info(f"Trying CoinMarketCap fallback for: {missing_for_cmc}")
            await self._fetch_from_cmc(missing_for_cmc)

        # Check for missing major symbols and try Coinbase as fallback
        major_missing = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0
                        and s.upper() in {'ADA', 'BTC', 'ETH', 'SOL', 'MATIC'}]
        if major_missing:
            logger.info(f"Trying Coinbase fallback for: {major_missing}")
            await self._fetch_from_coinbase(major_missing)

        # Check again for still missing major symbols - try DefiLlama
        still_missing_major = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0
                              and s.upper() in ASSET_TO_COINGECKO]
        if still_missing_major:
            logger.info(f"Trying DefiLlama fallback for: {still_missing_major}")
            await self._fetch_from_defillama(still_missing_major, include_major=True)

        # Find Cardano tokens still missing prices
        missing_cardano = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0 and s.upper() in CARDANO_TOKEN_POLICIES]

        # Try TapTools for missing Cardano tokens
        if missing_cardano and TAPTOOLS_API_KEY:
            await self._fetch_from_taptools(missing_cardano)

        # Check again for still missing Cardano tokens
        still_missing_cardano = [s for s in missing_cardano if self.cache.get(s, {}).get('usd', 0) == 0]

        # Try DefiLlama for still missing Cardano tokens (free, no API key required)
        if still_missing_cardano:
            await self._fetch_from_defillama(still_missing_cardano)

        # Only update last_fetch if we got at least some valid prices
        # This prevents cache from being "valid" when all sources are failing
        has_valid_prices = any(self.cache.get(s.upper(), {}).get('usd', 0) > 0 for s in symbols)
        if has_valid_prices:
            self.last_fetch = datetime.now()
            # Save good prices to stale cache as backup
            for s in symbols:
                price_data = self.cache.get(s.upper())
                if price_data and price_data.get('usd', 0) > 0:
                    self._stale_cache[s.upper()] = price_data.copy()

        # Build result, falling back to stale cache for any symbols still at 0
        result = {}
        for s in symbols:
            price = self.cache.get(s, {}).get('usd', 0)
            if price == 0 and s.upper() in self._stale_cache:
                stale_price = self._stale_cache[s.upper()].get('usd', 0)
                if stale_price > 0:
                    logger.info(f"Using stale cached price for {s}: ${stale_price}")
                    price = stale_price
            result[s] = price

        return result

    async def _fetch_from_coingecko(self, symbols: List[str]) -> None:
        """Fetch prices from CoinGecko using /coins/markets for 1hr change and market cap."""
        cg_ids = []
        symbol_map = {}
        for symbol in symbols:
            cg_id = ASSET_TO_COINGECKO.get(symbol.upper())
            if cg_id:
                cg_ids.append(cg_id)
                symbol_map[cg_id] = symbol.upper()

        if not cg_ids:
            return

        try:
            client = get_client("coingecko", timeout=30.0)
            # Use /coins/markets endpoint which provides 1hr change and market cap
            response = await fetch_with_retry(
                client, "GET",
                f"{COINGECKO_BASE_URL}/coins/markets",
                params={
                    'ids': ','.join(cg_ids),
                    'vs_currency': 'usd',
                    'price_change_percentage': '1h,24h'
                }
            )

            if response.status_code == 200:
                data = response.json()
                for coin in data:
                    cg_id = coin.get('id')
                    symbol = symbol_map.get(cg_id)
                    if symbol and coin.get('current_price'):
                        self.cache[symbol] = {
                            'usd': coin.get('current_price', 0),
                            'usd_1h_change': coin.get('price_change_percentage_1h_in_currency', 0) or 0,
                            'usd_24h_change': coin.get('price_change_percentage_24h', 0) or 0,
                            'market_cap': coin.get('market_cap', 0) or 0,
                            'total_supply': coin.get('total_supply'),
                            'circulating_supply': coin.get('circulating_supply'),
                            'max_supply': coin.get('max_supply'),
                            'source': 'CoinGecko',
                            'updated_at': datetime.now().isoformat()
                        }
                logger.info(f"CoinGecko: fetched prices for {len(data)} tokens")
            elif response.status_code == 429:
                # Set cooldown to skip CoinGecko for 60 seconds
                self._coingecko_cooldown_until = datetime.now() + timedelta(seconds=60)
                logger.warning(f"CoinGecko RATE LIMITED (429) - cooldown 60s, attempting fallbacks for {len(cg_ids)} symbols: {list(symbol_map.values())}")
            else:
                logger.warning(f"CoinGecko API error: {response.status_code}")

        except Exception as e:
            logger.error(f"CoinGecko fetch error: {e}")

    async def _fetch_from_cmc(self, symbols: List[str]) -> None:
        """Fetch prices from CoinMarketCap API (requires API key)."""
        if not CMC_API_KEY:
            logger.debug("CMC API key not configured, skipping")
            return

        # Build list of CMC symbols to fetch
        cmc_symbols = []
        symbol_map = {}
        for symbol in symbols:
            # Skip if already have a valid price
            if self.cache.get(symbol.upper(), {}).get('usd', 0) > 0:
                continue

            cmc_symbol = ASSET_TO_CMC.get(symbol.upper())
            if cmc_symbol:
                cmc_symbols.append(cmc_symbol)
                symbol_map[cmc_symbol] = symbol.upper()

        if not cmc_symbols:
            return

        try:
            client = get_client("coinmarketcap", timeout=30.0)
            response = await client.get(
                f"{CMC_BASE_URL}/cryptocurrency/quotes/latest",
                params={'symbol': ','.join(cmc_symbols), 'convert': 'USD'},
                headers={
                    'X-CMC_PRO_API_KEY': CMC_API_KEY,
                    'Accept': 'application/json'
                }
            )

            if response.status_code == 200:
                data = response.json()
                coins = data.get('data', {})
                fetched_count = 0

                for cmc_symbol, coin_data in coins.items():
                    our_symbol = symbol_map.get(cmc_symbol)
                    if not our_symbol:
                        continue

                    quote = coin_data.get('quote', {}).get('USD', {})
                    price = quote.get('price', 0)

                    if price and price > 0:
                        self.cache[our_symbol] = {
                            'usd': price,
                            'usd_1h_change': quote.get('percent_change_1h', 0) or 0,
                            'usd_24h_change': quote.get('percent_change_24h', 0) or 0,
                            'market_cap': quote.get('market_cap', 0) or 0,
                            'volume_24h': quote.get('volume_24h', 0) or 0,
                            'source': 'CoinMarketCap',
                            'updated_at': datetime.now().isoformat()
                        }
                        fetched_count += 1

                if fetched_count > 0:
                    logger.info(f"CoinMarketCap: fetched prices for {fetched_count} tokens")
            elif response.status_code == 429:
                logger.warning("CoinMarketCap rate limited")
            else:
                logger.warning(f"CoinMarketCap API error: {response.status_code}")

        except Exception as e:
            logger.error(f"CoinMarketCap fetch error: {e}")

    async def _fetch_from_coinbase(self, symbols: List[str]) -> None:
        """Fetch prices from Coinbase public API (no auth required, fallback source)."""
        # Coinbase supports these major symbols directly
        coinbase_symbols = {'ADA', 'BTC', 'ETH', 'SOL', 'MATIC', 'USDC', 'USDT', 'DAI'}

        try:
            client = get_client("coinbase_public", timeout=30.0)
            for symbol in symbols:
                if symbol.upper() not in coinbase_symbols:
                    continue

                # Skip if already have a price from CoinGecko
                if self.cache.get(symbol.upper(), {}).get('usd', 0) > 0:
                    continue

                # Coinbase uses POL for MATIC now
                cb_symbol = 'POL' if symbol.upper() == 'MATIC' else symbol.upper()

                response = await client.get(
                    f"{COINBASE_BASE_URL}/prices/{cb_symbol}-USD/spot"
                )

                if response.status_code == 200:
                    data = response.json()
                    price = float(data.get('data', {}).get('amount', 0))
                    if price > 0:
                        self.cache[symbol.upper()] = {
                            'usd': price,
                            'usd_1h_change': 0,  # Coinbase spot doesn't provide change data
                            'usd_24h_change': 0,
                            'market_cap': 0,
                            'source': 'Coinbase',
                            'updated_at': datetime.now().isoformat()
                        }
                        logger.info(f"Coinbase: got price for {symbol}: ${price}")
                else:
                    logger.debug(f"Coinbase API error for {symbol}: {response.status_code}")

        except Exception as e:
            logger.error(f"Coinbase fetch error: {e}")

    async def _fetch_from_taptools(self, symbols: List[str]) -> None:
        """Fetch prices from TapTools API for Cardano tokens."""
        try:
            client = get_client("taptools", timeout=30.0)
            for symbol in symbols:
                policy_info = CARDANO_TOKEN_POLICIES.get(symbol.upper())
                if not policy_info:
                    continue

                policy_id, asset_name = policy_info
                unit = f"{policy_id}{asset_name}"

                response = await client.get(
                    f"{TAPTOOLS_BASE_URL}/token/prices",
                    params={'unit': unit},
                    headers={'x-api-key': TAPTOOLS_API_KEY}
                )

                if response.status_code == 200:
                    data = response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        price = data[0].get('price', 0)
                        if price > 0:
                            self.cache[symbol.upper()] = {
                                'usd': price,
                                'usd_1h_change': data[0].get('priceChange1h', 0) or 0,
                                'usd_24h_change': data[0].get('priceChange24h', 0) or 0,
                                'market_cap': data[0].get('mcap', 0) or 0,
                                'source': 'TapTools',
                                'updated_at': datetime.now().isoformat()
                            }
                            logger.info(f"TapTools: got price for {symbol}: ${price}")
                else:
                    logger.warning(f"TapTools API error for {symbol}: {response.status_code}")

        except Exception as e:
            logger.error(f"TapTools fetch error: {e}")

    async def _fetch_from_defillama(self, symbols: List[str], include_major: bool = False) -> None:
        """
        Fetch prices from DefiLlama API (free, no key required).

        Supports:
        - Major coins via coingecko: prefix (BTC, ETH, ADA, SOL, MATIC)
        - Cardano tokens via cardano: prefix with policy ID
        - EVM tokens via chain:address format

        Args:
            symbols: List of symbols to fetch
            include_major: If True, also fetch major coins (BTC, ETH, etc.)
        """
        try:
            client = get_client("defilama", timeout=30.0)
            units = []
            symbol_to_unit = {}

            for symbol in symbols:
                upper_symbol = symbol.upper()

                # Skip if already have a valid price
                if self.cache.get(upper_symbol, {}).get('usd', 0) > 0:
                    continue

                # Major coins - use coingecko: prefix
                if include_major and upper_symbol in ASSET_TO_COINGECKO:
                    cg_id = ASSET_TO_COINGECKO[upper_symbol]
                    unit = f"coingecko:{cg_id}"
                    units.append(unit)
                    symbol_to_unit[unit] = upper_symbol

                # Cardano tokens - use cardano: prefix with policy ID
                elif upper_symbol in CARDANO_TOKEN_POLICIES:
                    policy_id, asset_name = CARDANO_TOKEN_POLICIES[upper_symbol]
                    unit = f"cardano:{policy_id}{asset_name}"
                    units.append(unit)
                    symbol_to_unit[unit] = upper_symbol

            if not units:
                return

            # DefiLlama accepts comma-separated list (batch request)
            response = await client.get(
                f"https://coins.llama.fi/prices/current/{','.join(units)}"
            )

            if response.status_code == 200:
                data = response.json()
                coins = data.get('coins', {})
                fetched_count = 0
                for unit, price_data in coins.items():
                    symbol = symbol_to_unit.get(unit)
                    if symbol and price_data.get('price'):
                        self.cache[symbol] = {
                            'usd': price_data.get('price', 0),
                            'usd_1h_change': 0,
                            'usd_24h_change': 0,
                            'market_cap': 0,
                            'confidence': price_data.get('confidence', 0),
                            'source': 'DefiLlama',
                            'updated_at': datetime.now().isoformat()
                        }
                        fetched_count += 1
                if fetched_count > 0:
                    logger.info(f"DefiLlama: fetched prices for {fetched_count} tokens")
            else:
                logger.warning(f"DefiLlama API error: {response.status_code}")

        except Exception as e:
            logger.error(f"DefiLlama fetch error: {e}")

    async def get_price(self, symbol: str) -> float:
        """Get current USD price for a single symbol."""
        prices = await self.get_prices([symbol])
        return prices.get(symbol.upper(), 0)

    async def get_all_tracked_prices(self) -> Dict[str, dict]:
        """Get prices for all tracked assets with metadata."""
        # Combine all known symbols from both mappings
        all_symbols = set(ASSET_TO_COINGECKO.keys()) | set(CARDANO_TOKEN_POLICIES.keys())
        await self.get_prices(list(all_symbols))
        return self.cache.copy()

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self.last_fetch:
            return False
        return datetime.now() - self.last_fetch < self.cache_duration

    def get_cached_prices(self) -> Dict[str, dict]:
        """Get cached prices without fetching."""
        return self.cache.copy()

    async def get_historical_prices(self, symbols: List[str] = None, days: int = 30) -> Dict[str, List[dict]]:
        """
        Get historical prices for specified symbols from CoinGecko.
        Returns dict mapping symbol to list of {date, price, time} objects.

        Args:
            symbols: List of symbols (e.g., ['ADA', 'BTC', 'ETH', 'SOL', 'MATIC'])
            days: Number of days (1, 7, 30, 90, 180, 365)

        CoinGecko free API: /coins/{id}/market_chart
        Automatic granularity:
            - days=1: 5-minute intervals (288 data points)
            - days=2-90: hourly intervals
            - days>90: daily intervals
        """
        if symbols is None:
            # Default to all blockchain native tokens
            symbols = ['ADA', 'BTC', 'ETH', 'SOL', 'MATIC']

        historical_data = {}

        try:
            client = get_client("coingecko_historical", timeout=60.0)
            for symbol in symbols:
                cg_id = ASSET_TO_COINGECKO.get(symbol)
                if not cg_id:
                    continue

                # CoinGecko market_chart endpoint - auto granularity based on days
                response = await fetch_with_retry(
                    client, "GET",
                    f"{COINGECKO_BASE_URL}/coins/{cg_id}/market_chart",
                    params={
                        'vs_currency': 'usd',
                        'days': days
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    prices = data.get('prices', [])

                    # Convert to {date, price, time} format
                    # 'time' field is for TradingView lightweight-charts compatibility
                    # TradingView expects: Unix timestamp (seconds) for intraday, YYYY-MM-DD for daily
                    historical_data[symbol] = []
                    for timestamp_ms, price in prices:
                        timestamp_sec = int(timestamp_ms / 1000)
                        dt = datetime.fromtimestamp(timestamp_sec)

                        # Format based on granularity
                        if days <= 90:
                            # Intraday/hourly: use Unix timestamp in seconds
                            time_value = timestamp_sec
                            date_str = dt.strftime('%Y-%m-%d %H:%M')
                        else:
                            # Daily intervals: use YYYY-MM-DD string
                            time_value = dt.strftime('%Y-%m-%d')
                            date_str = dt.strftime('%Y-%m-%d')

                        historical_data[symbol].append({
                            'date': date_str,
                            'price': price,
                            'time': time_value  # Unix timestamp (int) or date string
                        })

                    logger.info(f"CoinGecko: fetched {len(prices)} historical prices for {symbol} (days={days})")
                elif response.status_code == 429:
                    logger.warning(f"CoinGecko rate limited for {symbol}, waiting...")
                    import asyncio
                    await asyncio.sleep(60)  # Wait 60 seconds for rate limit
                else:
                    logger.warning(f"CoinGecko historical API error for {symbol}: {response.status_code}")

                # Small delay between requests to avoid rate limiting
                import asyncio
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching historical prices: {e}")

        return historical_data


# Singleton instance
pricing_service = PricingService()
