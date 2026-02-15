"""
Pricing Service - Smart chain-aware routing with fallback sources.

Routing strategy:
- Cardano tokens: Charli3 -> TapTools -> DefiLlama
- Major coins (BTC, ETH, ADA, SOL, etc.): CoinGecko -> CMC -> Coinbase -> DefiLlama
- Other tokens (DeFi mapped in CoinGecko): CoinGecko -> DefiLlama

Historical prices:
- Cardano tokens: Charli3 OHLCV -> DefiLlama chart -> CoinGecko
- Other tokens: Engine cache -> DefiLlama chart -> CoinGecko

All three routing groups run in parallel via asyncio.gather().
"""

import asyncio
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
    # New chain native tokens
    'XRP': 'ripple',
    'HBAR': 'hedera-hashgraph',
    'EGLD': 'elrond-erd-2',
    'SUI': 'sui',
    'APT': 'aptos',
    'FIL': 'filecoin',
    # Existing chains missing from map
    'BNB': 'binancecoin',
    'AVAX': 'avalanche-2',
    'TRX': 'tron',
    'LINK': 'chainlink',
}

# Map our asset names to CoinMarketCap symbols
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
    'XRP': 'XRP',
    'HBAR': 'HBAR',
    'EGLD': 'EGLD',
    'SUI': 'SUI',
    'APT': 'APT',
    'FIL': 'FIL',
    'BNB': 'BNB',
    'AVAX': 'AVAX',
    'TRX': 'TRX',
    'LINK': 'LINK',
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

# Major coins that can be priced by multiple sources
MAJOR_SYMBOLS = {'ADA', 'BTC', 'ETH', 'SOL', 'MATIC', 'ALGO', 'USDC', 'USDT', 'DAI',
                  'XRP', 'HBAR', 'EGLD', 'SUI', 'APT', 'FIL', 'BNB', 'AVAX', 'TRX', 'LINK'}


def _classify_symbol(symbol: str) -> str:
    """Classify a symbol for smart routing."""
    upper = symbol.upper()
    if upper in CARDANO_TOKEN_POLICIES and upper not in MAJOR_SYMBOLS:
        return 'cardano'
    elif upper in MAJOR_SYMBOLS:
        return 'major'
    else:
        return 'other'


class PricingService:
    """Service for fetching and caching cryptocurrency prices with smart chain-aware routing."""

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

        Smart routing: classifies symbols by chain and routes to best-fit API.
        Cardano tokens -> Charli3/TapTools, Major coins -> CoinGecko/CMC, Others -> CoinGecko.
        All three groups run in parallel.
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

        # Classify symbols into routing groups
        cardano_syms = [s for s in symbols if _classify_symbol(s) == 'cardano']
        major_syms = [s for s in symbols if _classify_symbol(s) == 'major']
        other_syms = [s for s in symbols if _classify_symbol(s) == 'other']

        # Run all three routing groups in parallel
        await asyncio.gather(
            self._fetch_cardano_prices(cardano_syms),
            self._fetch_major_prices(major_syms),
            self._fetch_other_prices(other_syms),
            return_exceptions=True
        )

        # Only update last_fetch if we got at least some valid prices
        has_valid_prices = any(self.cache.get(s.upper(), {}).get('usd', 0) > 0 for s in symbols)
        if has_valid_prices:
            self.last_fetch = datetime.now()
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

        # Write current prices to engine price cache for today
        if has_valid_prices:
            try:
                from engine import db as engine_db
                today = datetime.now().strftime('%Y-%m-%d')
                prices_to_cache = []
                for s in symbols:
                    p = result.get(s, 0)
                    cg_id = ASSET_TO_COINGECKO.get(s.upper())
                    if p > 0 and cg_id:
                        prices_to_cache.append({
                            'asset_id': cg_id,
                            'date': today,
                            'price_usd': p,
                            'source': 'pricing_service'
                        })
                if prices_to_cache:
                    await engine_db.upsert_prices_batch(prices_to_cache)
            except Exception:
                pass  # Don't break current pricing if engine cache write fails

        return result

    # ============ Smart Routing Groups ============

    async def _fetch_cardano_prices(self, symbols: List[str]) -> None:
        """Route: Charli3 -> TapTools -> DefiLlama for Cardano tokens."""
        if not symbols:
            return

        # Try Charli3 first
        try:
            from services.charli3 import charli3_service
            charli3_results = await charli3_service.get_token_prices_batch(symbols)
            for sym, data in charli3_results.items():
                if data and data.get('price', 0) > 0:
                    self.cache[sym] = {
                        'usd': data['price'],
                        'usd_1h_change': data.get('change_1h', 0),
                        'usd_24h_change': data.get('change_24h', 0),
                        'market_cap': 0,
                        'volume_24h': data.get('volume_24h', 0),
                        'source': 'Charli3',
                        'updated_at': datetime.now().isoformat()
                    }
        except Exception as e:
            logger.warning(f"Charli3 pricing failed: {e}")

        # TapTools fallback for missing Cardano tokens
        missing = [s for s in symbols if self.cache.get(s.upper(), {}).get('usd', 0) == 0]
        if missing and TAPTOOLS_API_KEY:
            await self._fetch_from_taptools(missing)

        # DefiLlama final fallback
        still_missing = [s for s in symbols if self.cache.get(s.upper(), {}).get('usd', 0) == 0]
        if still_missing:
            await self._fetch_from_defillama(still_missing)

    async def _fetch_major_prices(self, symbols: List[str]) -> None:
        """Route: CoinGecko -> CMC -> Coinbase -> DefiLlama for major coins."""
        if not symbols:
            return

        # CoinGecko (skip if in cooldown)
        if self._coingecko_cooldown_until and datetime.now() < self._coingecko_cooldown_until:
            logger.info(f"Skipping CoinGecko (cooldown), going to CMC for majors")
        else:
            await self._fetch_from_coingecko(symbols)

        # CMC fallback
        missing_for_cmc = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0
                          and s.upper() in ASSET_TO_CMC]
        if missing_for_cmc and CMC_API_KEY:
            await self._fetch_from_cmc(missing_for_cmc)

        # Coinbase fallback
        still_missing = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0]
        if still_missing:
            await self._fetch_from_coinbase(still_missing)

        # DefiLlama final fallback
        still_missing_2 = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0
                          and s.upper() in ASSET_TO_COINGECKO]
        if still_missing_2:
            await self._fetch_from_defillama(still_missing_2, include_major=True)

    async def _fetch_other_prices(self, symbols: List[str]) -> None:
        """Route: CoinGecko -> DefiLlama for other tokens (DeFi tokens mapped in CoinGecko)."""
        if not symbols:
            return

        # CoinGecko (skip if in cooldown)
        if self._coingecko_cooldown_until and datetime.now() < self._coingecko_cooldown_until:
            logger.info(f"Skipping CoinGecko (cooldown) for other tokens")
        else:
            await self._fetch_from_coingecko(symbols)

        # DefiLlama fallback
        still_missing = [s for s in symbols if self.cache.get(s, {}).get('usd', 0) == 0
                        and s.upper() in ASSET_TO_COINGECKO]
        if still_missing:
            await self._fetch_from_defillama(still_missing, include_major=True)

    # ============ Individual Source Fetchers ============

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

        cmc_symbols = []
        symbol_map = {}
        for symbol in symbols:
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
        coinbase_symbols = {'ADA', 'BTC', 'ETH', 'SOL', 'MATIC', 'USDC', 'USDT', 'DAI',
                            'XRP', 'HBAR', 'SUI', 'APT', 'FIL', 'AVAX', 'LINK'}

        try:
            client = get_client("coinbase_public", timeout=30.0)
            for symbol in symbols:
                if symbol.upper() not in coinbase_symbols:
                    continue
                if self.cache.get(symbol.upper(), {}).get('usd', 0) > 0:
                    continue

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
                            'usd_1h_change': 0,
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
        """Fetch prices from DefiLlama API (free, no key required)."""
        try:
            client = get_client("defilama", timeout=30.0)
            units = []
            symbol_to_unit = {}

            for symbol in symbols:
                upper_symbol = symbol.upper()
                if self.cache.get(upper_symbol, {}).get('usd', 0) > 0:
                    continue

                if include_major and upper_symbol in ASSET_TO_COINGECKO:
                    cg_id = ASSET_TO_COINGECKO[upper_symbol]
                    unit = f"coingecko:{cg_id}"
                    units.append(unit)
                    symbol_to_unit[unit] = upper_symbol
                elif upper_symbol in CARDANO_TOKEN_POLICIES:
                    policy_id, asset_name = CARDANO_TOKEN_POLICIES[upper_symbol]
                    unit = f"cardano:{policy_id}{asset_name}"
                    units.append(unit)
                    symbol_to_unit[unit] = upper_symbol

            if not units:
                return

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

    # ============ Historical Prices ============

    async def get_historical_prices(self, symbols: List[str] = None, days: int = 30) -> Dict[str, List[dict]]:
        """
        Get historical prices for specified symbols.

        Routing:
        1. Engine price cache (for days > 90)
        2. Charli3 OHLCV (for Cardano tokens)
        3. DefiLlama chart (for non-Cardano, free unlimited)
        4. CoinGecko market_chart (final fallback)
        """
        if symbols is None:
            symbols = ['ADA', 'BTC', 'ETH', 'SOL', 'MATIC']

        historical_data = {}
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Step 1: Check engine price cache (for daily granularity, days > 90)
        if days > 90:
            try:
                from engine import db as engine_db
                for symbol in symbols:
                    cg_id = ASSET_TO_COINGECKO.get(symbol)
                    if not cg_id:
                        continue
                    cached = await engine_db.get_prices(cg_id, start_date, end_date)
                    if cached and len(cached) >= days * 0.8:
                        historical_data[symbol] = [
                            {'date': row['date'], 'price': row['price_usd'], 'time': row['date']}
                            for row in cached if row.get('price_usd', 0) > 0
                        ]
                        logger.info(f"Engine cache hit: {len(historical_data[symbol])} daily prices for {symbol}")
            except Exception as e:
                logger.warning(f"Engine price cache lookup failed: {e}")

        symbols_to_fetch = [s for s in symbols if s not in historical_data]
        if not symbols_to_fetch:
            return historical_data

        # Step 2: Charli3 OHLCV for Cardano tokens
        cardano_to_fetch = [s for s in symbols_to_fetch if s.upper() in CARDANO_TOKEN_POLICIES]
        if cardano_to_fetch:
            await self._fetch_historical_charli3(cardano_to_fetch, days, historical_data)

        # Step 3: DefiLlama chart for remaining symbols
        remaining = [s for s in symbols_to_fetch if s not in historical_data]
        if remaining:
            await self._fetch_historical_defillama(remaining, days, historical_data)

        # Step 4: CoinGecko as final fallback
        still_remaining = [s for s in symbols_to_fetch if s not in historical_data]
        if still_remaining:
            await self._fetch_historical_coingecko(still_remaining, days, historical_data)

        return historical_data

    async def _fetch_historical_charli3(self, symbols: List[str], days: int, historical_data: dict) -> None:
        """Fetch OHLCV history from Charli3 for Cardano tokens."""
        try:
            from services.charli3 import charli3_service
            if not await charli3_service.is_configured():
                return

            now_ts = int(datetime.now().timestamp())
            from_ts = now_ts - (days * 86400)
            resolution = "1d" if days > 7 else "60min"

            for symbol in symbols:
                candles = await charli3_service.get_ohlcv_history(
                    symbol, resolution=resolution, from_ts=from_ts, to_ts=now_ts
                )
                if candles:
                    historical_data[symbol] = []
                    for candle in candles:
                        ts = candle['time']
                        dt = datetime.fromtimestamp(ts)
                        if days <= 90:
                            time_value = ts
                            date_str = dt.strftime('%Y-%m-%d %H:%M')
                        else:
                            time_value = dt.strftime('%Y-%m-%d')
                            date_str = dt.strftime('%Y-%m-%d')

                        historical_data[symbol].append({
                            'date': date_str,
                            'price': candle['close'],
                            'time': time_value,
                            'open': candle.get('open'),
                            'high': candle.get('high'),
                            'low': candle.get('low'),
                            'close': candle.get('close'),
                            'volume': candle.get('volume'),
                        })
                    logger.info(f"Charli3: fetched {len(candles)} OHLCV candles for {symbol}")

        except Exception as e:
            logger.warning(f"Charli3 historical fetch failed: {e}")

    async def _fetch_historical_defillama(self, symbols: List[str], days: int, historical_data: dict) -> None:
        """Fetch historical prices from DefiLlama chart endpoint."""
        sem = asyncio.Semaphore(5)

        async def fetch_one(symbol: str):
            async with sem:
                cg_id = ASSET_TO_COINGECKO.get(symbol.upper())
                if not cg_id:
                    return

                try:
                    client = get_client("defilama", timeout=60.0)
                    # DefiLlama chart endpoint
                    now_ts = int(datetime.now().timestamp())
                    from_ts = now_ts - (days * 86400)
                    # Use period parameter for resolution
                    period = "1d" if days > 7 else "1h"

                    response = await client.get(
                        f"https://coins.llama.fi/chart/coingecko:{cg_id}",
                        params={"start": from_ts, "end": now_ts, "period": period}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        coins = data.get('coins', {})
                        coin_key = f"coingecko:{cg_id}"
                        coin_data = coins.get(coin_key, {})
                        prices = coin_data.get('prices', [])

                        if prices:
                            historical_data[symbol] = []
                            for entry in prices:
                                ts = entry.get('timestamp', 0)
                                price = entry.get('price', 0)
                                dt = datetime.fromtimestamp(ts)

                                if days <= 90:
                                    time_value = ts
                                    date_str = dt.strftime('%Y-%m-%d %H:%M')
                                else:
                                    time_value = dt.strftime('%Y-%m-%d')
                                    date_str = dt.strftime('%Y-%m-%d')

                                historical_data[symbol].append({
                                    'date': date_str,
                                    'price': price,
                                    'time': time_value
                                })
                            logger.info(f"DefiLlama: fetched {len(prices)} historical prices for {symbol}")
                    else:
                        logger.debug(f"DefiLlama chart error for {symbol}: {response.status_code}")

                except Exception as e:
                    logger.warning(f"DefiLlama historical fetch error for {symbol}: {e}")

        await asyncio.gather(*[fetch_one(s) for s in symbols], return_exceptions=True)

    async def _fetch_historical_coingecko(self, symbols: List[str], days: int, historical_data: dict) -> None:
        """Fetch historical prices from CoinGecko (final fallback)."""
        try:
            client = get_client("coingecko_historical", timeout=60.0)
            for symbol in symbols:
                cg_id = ASSET_TO_COINGECKO.get(symbol)
                if not cg_id:
                    continue

                response = await fetch_with_retry(
                    client, "GET",
                    f"{COINGECKO_BASE_URL}/coins/{cg_id}/market_chart",
                    params={'vs_currency': 'usd', 'days': days}
                )

                if response.status_code == 200:
                    data = response.json()
                    prices = data.get('prices', [])

                    historical_data[symbol] = []
                    for timestamp_ms, price in prices:
                        timestamp_sec = int(timestamp_ms / 1000)
                        dt = datetime.fromtimestamp(timestamp_sec)

                        if days <= 90:
                            time_value = timestamp_sec
                            date_str = dt.strftime('%Y-%m-%d %H:%M')
                        else:
                            time_value = dt.strftime('%Y-%m-%d')
                            date_str = dt.strftime('%Y-%m-%d')

                        historical_data[symbol].append({
                            'date': date_str,
                            'price': price,
                            'time': time_value
                        })

                    logger.info(f"CoinGecko: fetched {len(prices)} historical prices for {symbol} (days={days})")

                    # Write daily prices back to engine cache
                    if days > 90:
                        try:
                            from engine import db as engine_db
                            prices_to_cache = [
                                {'asset_id': cg_id, 'date': e['date'][:10], 'price_usd': e['price'], 'source': 'coingecko'}
                                for e in historical_data[symbol]
                                if isinstance(e['time'], str) and e['price'] > 0
                            ]
                            if prices_to_cache:
                                await engine_db.upsert_prices_batch(prices_to_cache)
                                logger.info(f"Cached {len(prices_to_cache)} daily prices for {symbol} in engine")
                        except Exception as cache_err:
                            logger.warning(f"Failed to cache prices for {symbol}: {cache_err}")

                elif response.status_code == 429:
                    logger.warning(f"CoinGecko rate limited for {symbol}, waiting...")
                    await asyncio.sleep(60)
                else:
                    logger.warning(f"CoinGecko historical API error for {symbol}: {response.status_code}")

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching historical prices from CoinGecko: {e}")

    # ============ Utility Methods ============

    async def get_price(self, symbol: str) -> float:
        """Get current USD price for a single symbol."""
        prices = await self.get_prices([symbol])
        return prices.get(symbol.upper(), 0)

    async def get_all_tracked_prices(self) -> Dict[str, dict]:
        """Get prices for all tracked assets with metadata."""
        all_symbols = set(ASSET_TO_COINGECKO.keys()) | set(CARDANO_TOKEN_POLICIES.keys())
        await self.get_prices(list(all_symbols))
        return self.cache.copy()

    async def get_trending_coins(self) -> List[dict]:
        """
        Get trending coins. Tries CMC first, falls back to CoinGecko.
        """
        # Try CoinGecko trending (always available on free tier)
        try:
            client = get_client("coingecko", timeout=15.0)
            response = await client.get(f"{COINGECKO_BASE_URL}/search/trending")
            if response.status_code == 200:
                data = response.json()
                trending = []
                for item in data.get('coins', [])[:10]:
                    coin = item.get('item', {})
                    trending.append({
                        'name': coin.get('name'),
                        'symbol': coin.get('symbol', '').upper(),
                        'thumb': coin.get('thumb'),
                        'market_cap_rank': coin.get('market_cap_rank'),
                        'price_btc': coin.get('price_btc', 0),
                        'source': 'CoinGecko'
                    })
                return trending
        except Exception as e:
            logger.error(f"Error fetching trending coins: {e}")

        return []

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self.last_fetch:
            return False
        return datetime.now() - self.last_fetch < self.cache_duration

    def get_cached_prices(self) -> Dict[str, dict]:
        """Get cached prices without fetching."""
        return self.cache.copy()


# Singleton instance
pricing_service = PricingService()
