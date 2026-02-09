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

        # Determine if this is an NFT
        is_nft = self._is_nft_asset(chain, asset_id)

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
        # Cardano NFTs are harder to distinguish from tokens (both use policy_id.asset_name)
        # We'll treat them as tokens unless we can't price them
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
        """Fetch Cardano NFT collection floor price via nft_price_client."""
        try:
            from services.nft_price_client import nft_price_client
            floor_ada = await nft_price_client.get_floor_price(policy_id)
            if floor_ada and floor_ada > 0:
                # Convert ADA floor to USD
                ada_price = await self.fetch_historical_price(
                    "native", "cardano", datetime.utcnow().strftime('%Y-%m-%d')
                )
                if ada_price:
                    return floor_ada * ada_price
        except Exception as e:
            logger.debug(f"Cardano NFT floor price error for {policy_id[:16]}: {e}")
        return None

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
        except Exception as e:
            logger.debug(f"DefiLlama historical price error for {defillama_key}: {e}")
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
