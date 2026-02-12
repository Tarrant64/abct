"""
Price Enricher

Fetches historical prices using DefiLlama (free, no key) -> CoinGecko fallback.
Supports native assets, DeFi/staking tokens, and NFT floor prices.
Stores results in engine_price_history for reuse.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from engine import db as engine_db
from services.http_client import get_client
from services.pricing import ASSET_TO_COINGECKO, CARDANO_TOKEN_POLICIES

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

# Reverse lookup: (policy_id, asset_name_hex) -> symbol
_CARDANO_POLICY_REVERSE = {}
for _sym, (_pid, _aname) in CARDANO_TOKEN_POLICIES.items():
    _CARDANO_POLICY_REVERSE[f"{_pid}.{_aname}"] = _sym
    # Also index by concatenated form (policy_id + asset_name) for flexibility
    _CARDANO_POLICY_REVERSE[f"{_pid}{_aname}"] = _sym


class PriceEnricher:
    """Fetches and caches historical prices for canonical events."""

    # In-memory cache for resolved token info to avoid repeated DB lookups
    _token_info_cache: Dict[Tuple[str, str], Optional[Dict]] = {}

    async def enrich_date(self, asset_id: str, chain: str, date: str) -> Optional[float]:
        """Get USD price for asset on a specific date (used by engine pipeline)."""
        return await self.fetch_historical_price(asset_id, chain, date)

    async def resolve_token_info(self, chain: str, asset_id: str) -> Optional[Dict]:
        """
        Resolve token metadata: decimals, symbol, DefiLlama key.

        1. Check engine_token_info cache in DB
        2. Build DefiLlama key from asset_id format
        3. Call DefiLlama /prices/current to discover decimals+symbol
        4. Store result for future use
        """
        cache_key = (chain, asset_id)
        if cache_key in self._token_info_cache:
            return self._token_info_cache[cache_key]

        # Check DB cache
        info = await engine_db.get_token_info(chain, asset_id)
        if info:
            self._token_info_cache[cache_key] = info
            return info

        # Determine if this is an NFT (EVM format-based check first)
        is_nft = self._is_nft_asset(chain, asset_id)

        # For Cardano, cross-reference with V1 nft_floor_prices to detect NFTs
        if chain == "cardano" and not is_nft and '.' in asset_id:
            policy_id = asset_id.split('.')[0]
            try:
                from database import get_latest_nft_floor_price
                v1_floor = await get_latest_nft_floor_price(policy_id)
                if v1_floor:
                    is_nft = True
                    logger.debug(f"Cardano NFT detected via V1 data: {asset_id[:30]}...")
            except Exception as e:
                logger.debug(f"V1 NFT lookup error for {policy_id[:16]}: {e}")

        # Build DefiLlama key
        defillama_key = self._build_defillama_key(chain, asset_id)
        coingecko_id = None

        # For Cardano tokens, try reverse lookup to get CoinGecko ID
        if chain == "cardano" and not is_nft:
            symbol = _CARDANO_POLICY_REVERSE.get(asset_id)
            if symbol:
                coingecko_id = ASSET_TO_COINGECKO.get(symbol)
                if coingecko_id:
                    defillama_key = f"coingecko:{coingecko_id}"

        if not defillama_key and not is_nft:
            self._token_info_cache[cache_key] = None
            return None

        # Discover decimals and symbol from DefiLlama
        symbol = None
        decimals = 0
        if defillama_key and not is_nft:
            discovered = await self._discover_token_metadata(defillama_key)
            if discovered:
                symbol = discovered.get('symbol')
                decimals = discovered.get('decimals', 0)
            elif chain == "cardano" and '.' in asset_id:
                # DefiLlama returned nothing for this Cardano asset with decimals=0
                # → likely an NFT, not a fungible token
                is_nft = True
                logger.debug(f"Cardano NFT detected via DefiLlama miss: {asset_id[:30]}...")

        # Store in DB
        await engine_db.upsert_token_info(
            chain=chain,
            asset_id=asset_id,
            symbol=symbol,
            decimals=decimals,
            defillama_key=defillama_key,
            coingecko_id=coingecko_id,
            is_nft=is_nft,
        )

        info = {
            'chain': chain,
            'asset_id': asset_id,
            'symbol': symbol,
            'decimals': decimals,
            'defillama_key': defillama_key,
            'coingecko_id': coingecko_id,
            'is_nft': is_nft,
        }
        self._token_info_cache[cache_key] = info
        return info

    def _is_nft_asset(self, chain: str, asset_id: str) -> bool:
        """Determine if an asset_id represents an NFT."""
        # EVM NFTs use format "{contract}:{tokenId}"
        if chain in ("ethereum", "polygon", "base") and ':' in asset_id:
            return True
        # Cardano: check in-memory cache (populated by resolve_token_info)
        if chain == "cardano":
            cached = self._token_info_cache.get((chain, asset_id))
            if cached and cached.get('is_nft'):
                return True
        return False

    def _build_defillama_key(self, chain: str, asset_id: str) -> Optional[str]:
        """Build DefiLlama pricing key from chain + asset_id."""
        if chain == "cardano":
            # Cardano tokens: asset_id = "{policy_id}.{asset_name_hex}"
            if '.' in asset_id:
                policy_id, asset_name = asset_id.split('.', 1)
                return f"cardano:{policy_id}{asset_name}"
            return None

        if chain == "ethereum":
            # EVM tokens: asset_id = contract_address
            # NFTs: asset_id = "{contract}:{tokenId}" - skip
            if ':' in asset_id:
                return None
            return f"ethereum:{asset_id}"

        if chain == "polygon":
            if ':' in asset_id:
                return None
            return f"polygon:{asset_id}"

        if chain == "base":
            if ':' in asset_id:
                return None
            return f"base:{asset_id}"

        if chain == "solana":
            return f"solana:{asset_id}"

        return None

    async def _discover_token_metadata(self, defillama_key: str) -> Optional[Dict]:
        """Call DefiLlama /prices/current to discover token decimals and symbol."""
        try:
            client = get_client("defilama", timeout=15.0)
            url = f"{DEFILLAMA_BASE}/prices/current/{defillama_key}"
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                coin_data = data.get('coins', {}).get(defillama_key, {})
                if coin_data:
                    return {
                        'symbol': coin_data.get('symbol'),
                        'decimals': coin_data.get('decimals', 0),
                        'price': coin_data.get('price'),
                    }
        except Exception as e:
            logger.debug(f"DefiLlama metadata discovery error for {defillama_key}: {e}")
        return None

    async def fetch_historical_price(self, asset_id: str, chain: str, date: str) -> Optional[float]:
        """Fetch historical price with DefiLlama -> CoinGecko fallback."""
        price_key = f"{chain}:{asset_id}"

        # Check engine cache first
        existing = await engine_db.get_prices(price_key, start_date=date, end_date=date)
        if existing:
            return existing[0]['price_usd']

        ts = int(datetime.strptime(date, '%Y-%m-%d').replace(hour=12).timestamp())

        # Native assets: use existing CoinGecko ID path
        if asset_id == "native":
            symbol = NATIVE_ASSET_MAP.get(price_key)
            if not symbol:
                symbol = NATIVE_ASSET_MAP.get(f"{chain}:native")
            if not symbol:
                return None

            cg_id = ASSET_TO_COINGECKO.get(symbol)
            if not cg_id:
                return None

            price = await self._fetch_from_defillama(cg_id, ts)
            source = "defillama"

            if not price:
                price = await self._fetch_from_coingecko_date(cg_id, date)
                source = "coingecko"

            if price and price > 0:
                await engine_db.upsert_price(price_key, date, price, source)
                return price
            return None

        # Non-native assets: resolve token info to get DefiLlama key
        token_info = await self.resolve_token_info(chain, asset_id)
        if not token_info:
            return None

        # Skip NFTs for historical pricing (handled separately via floor prices)
        if token_info.get('is_nft'):
            return None

        defillama_key = token_info.get('defillama_key')
        if not defillama_key:
            return None

        price = await self._fetch_defillama_by_key(defillama_key, ts)
        source = "defillama"

        # Fallback: if token has a coingecko_id, try CoinGecko
        if not price and token_info.get('coingecko_id'):
            price = await self._fetch_from_coingecko_date(token_info['coingecko_id'], date)
            source = "coingecko"

        if price and price > 0:
            await engine_db.upsert_price(price_key, date, price, source)
            return price
        return None

    async def fetch_historical_prices_batch(self, symbol: str, dates: List[str]) -> Dict[str, float]:
        """Fetch historical prices for multiple dates. Returns {date: price}.

        Strategy (multi-source with caching):
          1. Check engine_price_history cache first
          2. CoinGecko /market_chart?days=365 bulk fetch for last year (free tier)
          3. DefiLlama per-date for any remaining gaps (older dates, etc.)
          4. All fetched prices are cached in engine_price_history for reuse
        """
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

        # Step 1: Check engine cache — only fetch dates we don't have
        cached = await engine_db.get_prices(price_key)
        cached_dates = {p['date'] for p in cached}
        result = {p['date']: p['price_usd'] for p in cached if p['date'] in set(dates)}
        missing_dates = [d for d in dates if d not in cached_dates]

        if not missing_dates:
            logger.info(f"{symbol}: all {len(result)} prices found in cache")
            return result

        logger.info(f"Fetching {len(missing_dates)} historical prices for {symbol} ({len(result)} cached)")

        # Step 2: CoinGecko bulk fetch (free tier: /market_chart?days=365)
        # This gets daily prices for the last year in a single API call.
        cg_bulk_count = 0
        retries = 0
        while retries < 3:
            try:
                client = get_client("coingecko_historical", timeout=60.0)
                response = await client.get(
                    f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart",
                    params={'vs_currency': 'usd', 'days': 365}
                )
                if response.status_code == 200:
                    data = response.json()
                    prices_list = data.get('prices', [])
                    batch_to_store = []
                    for ts_ms, price in prices_list:
                        date_str = datetime.utcfromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d')
                        if price and price > 0 and date_str in set(missing_dates):
                            result[date_str] = price
                            batch_to_store.append({
                                'asset_id': price_key, 'date': date_str,
                                'price_usd': price, 'source': 'coingecko',
                            })
                            cg_bulk_count += 1
                    if batch_to_store:
                        await engine_db.upsert_prices_batch(batch_to_store)
                    logger.info(f"CoinGecko bulk: {cg_bulk_count} prices for {symbol} (from {len(prices_list)} points)")
                    break
                elif response.status_code == 429:
                    retries += 1
                    logger.warning(f"CoinGecko rate limit for {symbol}, waiting 60s (retry {retries}/3)")
                    await asyncio.sleep(60)
                    continue
                else:
                    logger.warning(f"CoinGecko market_chart returned {response.status_code} for {symbol}")
                    break
            except Exception as e:
                logger.warning(f"CoinGecko market_chart error for {symbol}: {e}")
                break

        # Step 3: DefiLlama per-date for anything still missing
        still_missing = [d for d in missing_dates if d not in result]

        if still_missing:
            logger.info(f"DefiLlama: fetching {len(still_missing)} remaining {symbol} prices")
            batch_to_store = []
            dl_count = 0
            for i, date in enumerate(sorted(still_missing)):
                ts = int(datetime.strptime(date, '%Y-%m-%d').replace(hour=12).timestamp())
                price = await self._fetch_from_defillama(cg_id, ts)
                source = "defillama"

                if not price:
                    price = await self._fetch_from_coingecko_date(cg_id, date)
                    source = "coingecko"

                if price and price > 0:
                    result[date] = price
                    dl_count += 1
                    batch_to_store.append({
                        'asset_id': price_key, 'date': date,
                        'price_usd': price, 'source': source,
                    })

                # Rate limit: ~2 requests/sec for DefiLlama
                if (i + 1) % 2 == 0 and i < len(still_missing) - 1:
                    await asyncio.sleep(1)

                # Periodic batch store every 50 prices
                if len(batch_to_store) >= 50:
                    await engine_db.upsert_prices_batch(batch_to_store)
                    batch_to_store = []

                # Progress logging every 100 dates
                if (i + 1) % 100 == 0:
                    logger.info(f"  DefiLlama {symbol}: {i+1}/{len(still_missing)} fetched ({dl_count} prices)")

            if batch_to_store:
                await engine_db.upsert_prices_batch(batch_to_store)
            logger.info(f"DefiLlama: got {dl_count}/{len(still_missing)} prices for {symbol}")

        total_fetched = len(result)
        logger.info(f"Total prices for {symbol}: {total_fetched}/{len(dates)} "
                     f"(cache={len(dates)-len(missing_dates)}, CG={cg_bulk_count}, DL={total_fetched-len(dates)+len(missing_dates)-cg_bulk_count})")
        return result

    async def fetch_token_prices_batch(self, chain: str, asset_id: str,
                                        dates: List[str]) -> Dict[str, float]:
        """Fetch historical prices for a token across multiple dates."""
        token_info = await self.resolve_token_info(chain, asset_id)
        if not token_info or token_info.get('is_nft'):
            return {}

        defillama_key = token_info.get('defillama_key')
        if not defillama_key:
            return {}

        price_key = f"{chain}:{asset_id}"

        # Check cache
        cached = await engine_db.get_prices(price_key)
        cached_dates = {p['date'] for p in cached}
        missing_dates = [d for d in dates if d not in cached_dates]

        result = {p['date']: p['price_usd'] for p in cached if p['date'] in set(dates)}

        if not missing_dates:
            return result

        logger.info(f"Fetching {len(missing_dates)} token prices for {chain}:{asset_id[:16]}... ({len(result)} cached)")

        batch_to_store = []
        for i, date in enumerate(sorted(missing_dates)):
            ts = int(datetime.strptime(date, '%Y-%m-%d').replace(hour=12).timestamp())
            price = await self._fetch_defillama_by_key(defillama_key, ts)
            source = "defillama"

            # Fallback to CoinGecko if we have a coingecko_id
            if not price and token_info.get('coingecko_id'):
                price = await self._fetch_from_coingecko_date(token_info['coingecko_id'], date)
                source = "coingecko"

            if price and price > 0:
                result[date] = price
                batch_to_store.append({
                    'asset_id': price_key, 'date': date,
                    'price_usd': price, 'source': source,
                })

            # Rate limit
            if (i + 1) % 2 == 0 and i < len(missing_dates) - 1:
                await asyncio.sleep(1)

            if len(batch_to_store) >= 50:
                await engine_db.upsert_prices_batch(batch_to_store)
                batch_to_store = []

        if batch_to_store:
            await engine_db.upsert_prices_batch(batch_to_store)

        return result

    async def fetch_nft_floor_price(self, chain: str, asset_id: str) -> Optional[float]:
        """
        Fetch current NFT floor price (best-effort).

        For EVM: uses Alchemy getFloorPrice via ethereum_nft service
        For Cardano: uses TapTools via nft_price_client service

        Returns USD value, or None if unavailable.
        """
        try:
            if chain in ("ethereum", "polygon", "base") and ':' in asset_id:
                contract = asset_id.split(':')[0]
                return await self._fetch_evm_nft_floor(chain, contract)

            if chain == "cardano" and '.' in asset_id:
                policy_id = asset_id.split('.')[0]
                return await self._fetch_cardano_nft_floor(policy_id)

        except Exception as e:
            logger.debug(f"NFT floor price error for {chain}:{asset_id[:20]}: {e}")
        return None

    async def _fetch_evm_nft_floor(self, chain: str, contract: str) -> Optional[float]:
        """Fetch EVM NFT collection floor price via Alchemy."""
        try:
            from services.ethereum_nft import EthereumNFTService
            nft_svc = EthereumNFTService()
            if not await nft_svc.is_configured():
                return None

            api_key = await nft_svc.get_api_key()
            if not api_key:
                return None

            chain_subdomain = {
                "ethereum": "eth-mainnet",
                "polygon": "polygon-mainnet",
                "base": "base-mainnet",
            }.get(chain, "eth-mainnet")

            client = get_client("alchemy", timeout=15.0)
            url = f"https://{chain_subdomain}.g.alchemy.com/nft/v3/{api_key}/getFloorPrice"
            response = await client.get(url, params={"contractAddress": contract})
            if response.status_code == 200:
                data = response.json()
                opensea = data.get('openSea', {})
                floor_eth = opensea.get('floorPrice')
                if floor_eth and floor_eth > 0:
                    # Convert ETH floor to USD using native chain price
                    native_chain = "ethereum" if chain == "base" else chain
                    native_price = await self.fetch_historical_price(
                        "native", native_chain, datetime.utcnow().strftime('%Y-%m-%d')
                    )
                    if native_price:
                        return floor_eth * native_price
        except Exception as e:
            logger.debug(f"EVM NFT floor price error for {contract}: {e}")
        return None

    async def _fetch_cardano_nft_floor(self, policy_id: str) -> Optional[float]:
        """Fetch Cardano NFT collection floor price.

        Fallback chain:
        1. V1 nft_floor_prices table (already has data, free, instant)
        2. nft_price_client external service (if configured)
        3. TapTools direct API call (rate-limited, last resort)
        """
        # Helper to convert ADA floor to USD
        async def _ada_to_usd(floor_ada: float) -> Optional[float]:
            ada_price = await self.fetch_historical_price(
                "native", "cardano", datetime.utcnow().strftime('%Y-%m-%d')
            )
            if ada_price:
                return floor_ada * ada_price
            return None

        # 1. Check V1 floor price cache (main database)
        try:
            from database import get_latest_nft_floor_price
            cached = await get_latest_nft_floor_price(policy_id)
            if cached and cached.get('floor_price_ada') and cached['floor_price_ada'] > 0:
                usd = await _ada_to_usd(cached['floor_price_ada'])
                if usd:
                    logger.debug(f"NFT floor from V1 cache: {policy_id[:16]}... = {cached['floor_price_ada']} ADA")
                    return usd
        except Exception as e:
            logger.debug(f"V1 floor price lookup error for {policy_id[:16]}: {e}")

        # 2. Try nft_price_client external service
        try:
            from services.nft_price_client import nft_price_client
            floor_ada = await nft_price_client.get_floor_price(policy_id)
            if floor_ada and floor_ada > 0:
                usd = await _ada_to_usd(floor_ada)
                if usd:
                    # Persist back to V1 table for future lookups
                    await self._save_floor_to_v1(policy_id, floor_ada, "nft_price_service")
                    return usd
        except Exception as e:
            logger.debug(f"nft_price_client error for {policy_id[:16]}: {e}")

        # 3. Direct TapTools API call (last resort)
        try:
            floor_ada = await self._fetch_taptools_floor_direct(policy_id)
            if floor_ada and floor_ada > 0:
                usd = await _ada_to_usd(floor_ada)
                if usd:
                    # Persist back to V1 table for future lookups
                    await self._save_floor_to_v1(policy_id, floor_ada, "taptools_direct")
                    return usd
        except Exception as e:
            logger.debug(f"TapTools direct floor price error for {policy_id[:16]}: {e}")

        return None

    async def _fetch_taptools_floor_direct(self, policy_id: str) -> Optional[float]:
        """Direct TapTools floor price call as last-resort fallback."""
        try:
            from services.api_key_manager import APIKeyManager
            mgr = APIKeyManager(api_name='taptools', env_var='TAPTOOLS_API_KEY')
            api_key = await mgr.get_api_key()
            if not api_key:
                return None

            client = get_client("taptools_nft", timeout=15.0)
            response = await client.get(
                "https://openapi.taptools.io/api/v1/nft/collection/stats",
                params={"policy": policy_id},
                headers={"x-api-key": api_key},
            )
            if response.status_code == 200:
                data = response.json()
                price = data.get('price')
                if price and float(price) > 0:
                    return float(price)
            elif response.status_code == 429:
                logger.warning("TapTools rate limit hit during NFT floor price fetch")
        except Exception as e:
            logger.debug(f"TapTools direct API error for {policy_id[:16]}: {e}")
        return None

    async def _save_floor_to_v1(self, policy_id: str, floor_ada: float, source: str):
        """Persist fetched floor price back to V1 nft_floor_prices table."""
        try:
            from database import save_nft_floor_price
            await save_nft_floor_price({
                'policy_id': policy_id,
                'floor_price_ada': floor_ada,
                'source': source,
                'fetched_at': datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.debug(f"Failed to save floor price to V1: {e}")

    async def _fetch_from_defillama(self, cg_id: str, timestamp: int) -> Optional[float]:
        """Fetch single historical price from DefiLlama using coingecko: prefix."""
        key = f"coingecko:{cg_id}"
        return await self._fetch_defillama_by_key(key, timestamp)

    async def _fetch_defillama_by_key(self, defillama_key: str, timestamp: int) -> Optional[float]:
        """Fetch single historical price from DefiLlama using any key format."""
        try:
            client = get_client("defilama", timeout=30.0)
            url = f"{DEFILLAMA_BASE}/prices/historical/{timestamp}/{defillama_key}"
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                coin_data = data.get('coins', {}).get(defillama_key, {})
                return coin_data.get('price')
            else:
                logger.warning(f"DefiLlama returned {response.status_code} for {defillama_key} at {timestamp}")
        except Exception as e:
            logger.warning(f"DefiLlama historical price error for {defillama_key}: {e}")
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
                logger.warning(f"CoinGecko rate limit hit for {cg_id} on {date}, waiting 65s")
                await asyncio.sleep(65)
            else:
                logger.warning(f"CoinGecko historical returned {response.status_code} for {cg_id} on {date}")
        except Exception as e:
            logger.warning(f"CoinGecko historical price error for {cg_id} on {date}: {e}")
        return None

    async def fetch_hourly_prices(self, asset_id: str, chain: str, hours: int = 24) -> Dict[str, float]:
        """Fetch hourly prices for the last N hours. Returns {datetime_str: price}."""
        from datetime import timedelta

        price_key = f"{chain}:{asset_id}"
        now = datetime.utcnow()

        # Generate hourly timestamps for the last N hours
        hourly_times = []
        for h in range(hours, -1, -1):
            dt = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
            hourly_times.append(dt)

        # Check cache for existing hourly prices
        start_dt = hourly_times[0].strftime('%Y-%m-%dT%H:00')
        end_dt = hourly_times[-1].strftime('%Y-%m-%dT%H:00')
        cached = await engine_db.get_hourly_prices(price_key, start_datetime=start_dt, end_datetime=end_dt)
        cached_map = {p['datetime']: p['price_usd'] for p in cached}

        # Find missing hours
        missing = []
        for dt in hourly_times:
            dt_str = dt.strftime('%Y-%m-%dT%H:00')
            if dt_str not in cached_map:
                missing.append(dt)

        if not missing:
            return cached_map

        # Resolve DefiLlama key
        if asset_id == "native":
            symbol = NATIVE_ASSET_MAP.get(price_key) or NATIVE_ASSET_MAP.get(f"{chain}:native")
            if not symbol:
                return cached_map
            cg_id = ASSET_TO_COINGECKO.get(symbol)
            if not cg_id:
                return cached_map
            defillama_key = f"coingecko:{cg_id}"
        else:
            token_info = await self.resolve_token_info(chain, asset_id)
            if not token_info or not token_info.get('defillama_key'):
                return cached_map
            defillama_key = token_info['defillama_key']

        # Fetch missing hourly prices from DefiLlama
        batch_to_store = []
        for i, dt in enumerate(missing):
            ts = int(dt.timestamp())
            price = await self._fetch_defillama_by_key(defillama_key, ts)
            if price and price > 0:
                dt_str = dt.strftime('%Y-%m-%dT%H:00')
                cached_map[dt_str] = price
                batch_to_store.append({
                    'asset_id': price_key,
                    'datetime': dt_str,
                    'price_usd': price,
                    'source': 'defillama',
                })

            # Rate limit: 2 requests/sec
            if (i + 1) % 2 == 0 and i < len(missing) - 1:
                await asyncio.sleep(1)

        if batch_to_store:
            await engine_db.upsert_hourly_prices_batch(batch_to_store)

        return cached_map

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
