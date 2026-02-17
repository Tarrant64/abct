"""
Chain Analytics Service - DefiLlama integration

Provides chain-level metrics: TVL, fees, revenue, DEX volume.
All data from DefiLlama (free, no API key required).
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

from services.http_client import get_client
from database import get_cache, set_cache
from config import CACHE_TTL_WARM, CACHE_TTL_HOT, CMC_BASE_URL

logger = logging.getLogger(__name__)

DEFILLAMA_BASE = "https://api.llama.fi"

# Chain name mapping: our name -> DefiLlama chain slug
CHAIN_SLUGS = {
    'Ethereum': 'Ethereum',
    'Solana': 'Solana',
    'Cardano': 'Cardano',
    'Bitcoin': 'Bitcoin',
    'Polygon': 'Polygon',
    'Base': 'Base',
    'Arbitrum': 'Arbitrum',
    'Avalanche': 'Avalanche',
    'BSC': 'BSC',
}

SUPPORTED_CHAINS = list(CHAIN_SLUGS.keys())

STABLECOIN_CLASSIFICATIONS = {
    'fiat-backed': 'Fiat-Backed',
    'crypto-backed': 'Crypto-Backed',
    'algorithmic': 'Algorithmic',
    'hybrid': 'Hybrid',
    '': 'Unknown',
}


class ChainAnalyticsService:
    """Aggregates on-chain metrics from DefiLlama."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_client("defillama_analytics", timeout=30.0)
        return self._client

    async def get_chain_overview(self) -> Dict:
        """Get TVL, fees, revenue, and DEX volume for all supported chains."""
        cache_key = "analytics:chain_overview"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        chains_data = {}
        for chain in SUPPORTED_CHAINS:
            chains_data[chain] = {
                'tvl': 0, 'tvl_change_1d': 0,
                'fees_24h': 0, 'revenue_24h': 0, 'dex_volume_24h': 0
            }

        # Fetch all data sources in parallel
        await asyncio.gather(
            self._fetch_tvl_and_change(chains_data),
            self._fetch_per_chain_fees_revenue(chains_data),
            self._fetch_dex_volume(chains_data),
            return_exceptions=True
        )

        result = {'chains': chains_data, 'timestamp': int(time.time())}
        await set_cache(cache_key, result, CACHE_TTL_WARM)
        return result

    async def _fetch_tvl_and_change(self, chains_data: dict) -> None:
        """Fetch TVL from bulk endpoint, TVL change from historical data."""
        # Bulk TVL from /v2/chains
        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/v2/chains")
            if resp.status_code == 200:
                for item in resp.json():
                    name = item.get('name', '')
                    if name == 'Binance':
                        name = 'BSC'
                    if name in chains_data:
                        chains_data[name]['tvl'] = item.get('tvl', 0) or 0
        except Exception as e:
            logger.warning(f"DefiLlama chains TVL fetch failed: {e}")

        # Calculate TVL change from historical data (parallel per chain)
        async def calc_tvl_change(chain: str):
            slug = CHAIN_SLUGS.get(chain, chain)
            try:
                resp = await self.client.get(f"{DEFILLAMA_BASE}/v2/historicalChainTvl/{slug}")
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) >= 2:
                        today_tvl = data[-1].get('tvl', 0)
                        yesterday_tvl = data[-2].get('tvl', 0)
                        if yesterday_tvl > 0:
                            chains_data[chain]['tvl_change_1d'] = ((today_tvl - yesterday_tvl) / yesterday_tvl) * 100
            except Exception as e:
                logger.debug(f"TVL change calc failed for {chain}: {e}")

        await asyncio.gather(*[calc_tvl_change(c) for c in SUPPORTED_CHAINS], return_exceptions=True)

    async def _fetch_per_chain_fees_revenue(self, chains_data: dict) -> None:
        """Fetch 24h fees and revenue using per-chain DefiLlama endpoints."""
        async def fetch_one(chain: str):
            slug = CHAIN_SLUGS.get(chain, chain)
            # Fetch fees
            try:
                resp = await self.client.get(f"{DEFILLAMA_BASE}/overview/fees/{slug}")
                if resp.status_code == 200:
                    chains_data[chain]['fees_24h'] = resp.json().get('total24h', 0) or 0
            except Exception as e:
                logger.debug(f"Per-chain fees fetch failed for {chain}: {e}")

            # Fetch revenue
            try:
                resp = await self.client.get(
                    f"{DEFILLAMA_BASE}/overview/fees/{slug}",
                    params={'dataType': 'dailyRevenue'}
                )
                if resp.status_code == 200:
                    chains_data[chain]['revenue_24h'] = resp.json().get('total24h', 0) or 0
            except Exception as e:
                logger.debug(f"Per-chain revenue fetch failed for {chain}: {e}")

        await asyncio.gather(*[fetch_one(c) for c in SUPPORTED_CHAINS], return_exceptions=True)

    async def _fetch_dex_volume(self, chains_data: dict) -> None:
        """Fetch DEX volume from bulk endpoint, distributed across chains."""
        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/overview/dexs")
            if resp.status_code == 200:
                data = resp.json()
                for protocol in data.get('protocols', []):
                    chains = protocol.get('chains', [])
                    total24h = protocol.get('total24h') or 0
                    if chains and total24h:
                        per_chain = total24h / len(chains)
                        for c in chains:
                            if c == 'Binance':
                                c = 'BSC'
                            if c in chains_data:
                                chains_data[c]['dex_volume_24h'] += per_chain
        except Exception as e:
            logger.warning(f"DefiLlama DEX volume fetch failed: {e}")

    async def get_chain_fees_history(self, chain: str, days: int = 30) -> List[Dict]:
        """Get daily fee history for a specific chain."""
        slug = CHAIN_SLUGS.get(chain, chain)
        cache_key = f"analytics:fees_history:{slug}:{days}"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/summary/fees/{slug}")
            if resp.status_code == 200:
                data = resp.json()
                # totalDataChart is list of [timestamp, value]
                chart_data = data.get('totalDataChart', [])
                # Take last N days
                result = []
                for entry in chart_data[-days:]:
                    if isinstance(entry, list) and len(entry) >= 2:
                        result.append({
                            'date': entry[0],
                            'fees': entry[1]
                        })
                    elif isinstance(entry, dict):
                        result.append({
                            'date': entry.get('date', 0),
                            'fees': entry.get('Fees', entry.get('fees', 0))
                        })

                await set_cache(cache_key, result, CACHE_TTL_WARM)
                return result
        except Exception as e:
            logger.warning(f"DefiLlama fee history for {chain} failed: {e}")

        return []

    async def get_chain_tvl_history(self, chain: str) -> List[Dict]:
        """Get historical TVL for a specific chain."""
        slug = CHAIN_SLUGS.get(chain, chain)
        cache_key = f"analytics:tvl_history:{slug}"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/v2/historicalChainTvl/{slug}")
            if resp.status_code == 200:
                data = resp.json()
                # Returns list of {date: timestamp, tvl: value}
                result = [{'date': d.get('date', 0), 'tvl': d.get('tvl', 0)} for d in data[-90:]]
                await set_cache(cache_key, result, CACHE_TTL_WARM)
                return result
        except Exception as e:
            logger.warning(f"DefiLlama TVL history for {chain} failed: {e}")

        return []

    async def get_total_tvl(self) -> float:
        """Get total DeFi TVL across all chains."""
        cache_key = "analytics:total_tvl"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/v2/chains")
            if resp.status_code == 200:
                total = sum(item.get('tvl', 0) for item in resp.json())
                await set_cache(cache_key, total, CACHE_TTL_WARM)
                return total
        except Exception as e:
            logger.warning(f"DefiLlama total TVL fetch failed: {e}")

        return 0

    async def get_total_dex_volume(self) -> float:
        """Get total 24h DEX volume across all chains."""
        cache_key = "analytics:total_dex_volume"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/overview/dexs")
            if resp.status_code == 200:
                data = resp.json()
                total = data.get('total24h', 0)
                if not total:
                    total = sum(p.get('total24h', 0) or 0 for p in data.get('protocols', []))
                await set_cache(cache_key, total, CACHE_TTL_WARM)
                return total
        except Exception as e:
            logger.warning(f"DefiLlama total DEX volume fetch failed: {e}")

        return 0


    async def get_top_cryptos(self, limit: int = 20, source: str = "cmc") -> Dict:
        """Get top cryptocurrencies by market cap.

        Args:
            limit: Number of coins to return.
            source: 'cmc' for CoinMarketCap, 'coingecko' for CoinGecko.
        """
        cache_key = f"analytics:market:top_cryptos:{source}:{limit}"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        from database import get_api_key

        cryptos = []

        if source == "cmc":
            cmc_key = await get_api_key("coinmarketcap")
            if not cmc_key:
                return {'cryptos': [], 'source': 'CMC', 'error': 'CoinMarketCap API key not configured'}
            try:
                client = get_client("coinmarketcap", timeout=10.0)
                resp = await client.get(
                    f"{CMC_BASE_URL}/cryptocurrency/listings/latest",
                    params={'limit': limit, 'convert': 'USD'},
                    headers={'X-CMC_PRO_API_KEY': cmc_key, 'Accept': 'application/json'}
                )
                if resp.status_code == 200:
                    for coin in resp.json().get('data', []):
                        quote = coin.get('quote', {}).get('USD', {})
                        cryptos.append({
                            'rank': coin.get('cmc_rank', 0),
                            'name': coin.get('name', ''),
                            'symbol': coin.get('symbol', ''),
                            'price': quote.get('price', 0),
                            'market_cap': quote.get('market_cap', 0),
                            'change_24h': quote.get('percent_change_24h', 0),
                            'change_7d': quote.get('percent_change_7d', 0),
                            'volume_24h': quote.get('volume_24h', 0),
                        })
                    logger.info(f"Top cryptos loaded from CMC ({len(cryptos)} coins)")
                else:
                    logger.warning(f"CMC listings returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"CMC top cryptos failed: {e}")

        elif source == "coingecko":
            cg_key = await get_api_key("coingecko")
            if not cg_key:
                return {'cryptos': [], 'source': 'CoinGecko', 'error': 'CoinGecko API key not configured'}
            try:
                client = get_client("coingecko", timeout=10.0)
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/coins/markets",
                    params={
                        'vs_currency': 'usd',
                        'order': 'market_cap_desc',
                        'per_page': limit,
                        'page': 1,
                        'sparkline': 'false',
                        'price_change_percentage': '24h,7d'
                    },
                    headers={"x-cg-demo-api-key": cg_key}
                )
                if resp.status_code == 200:
                    for i, coin in enumerate(resp.json()):
                        cryptos.append({
                            'rank': coin.get('market_cap_rank', i + 1),
                            'name': coin.get('name', ''),
                            'symbol': (coin.get('symbol', '') or '').upper(),
                            'price': coin.get('current_price', 0),
                            'market_cap': coin.get('market_cap', 0),
                            'change_24h': coin.get('price_change_percentage_24h', 0),
                            'change_7d': coin.get('price_change_percentage_7d_in_currency', 0),
                            'volume_24h': coin.get('total_volume', 0),
                        })
                    logger.info(f"Top cryptos loaded from CoinGecko ({len(cryptos)} coins)")
                else:
                    logger.warning(f"CoinGecko markets returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"CoinGecko top cryptos failed: {e}")

        display_source = 'CMC' if source == 'cmc' else 'CoinGecko'
        result = {'cryptos': cryptos, 'source': display_source}
        if cryptos:
            await set_cache(cache_key, result, CACHE_TTL_HOT)
        return result

    async def get_stablecoin_market(self) -> Dict:
        """Get top stablecoins by market cap from DefiLlama."""
        cache_key = "analytics:market:stablecoins"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get("https://stablecoins.llama.fi/stablecoins?includePrices=true")
            if resp.status_code != 200:
                logger.warning(f"DefiLlama stablecoins returned {resp.status_code}")
                return {"total_stablecoin_mcap": 0, "stablecoins": []}

            pegged_assets = resp.json().get('peggedAssets', [])

            stablecoins = []
            total_mcap = 0

            for coin in pegged_assets:
                # Sum circulating mcap across all chains
                circ = coin.get('circulating', {})
                mcap = 0
                for peg_type_val in circ.values():
                    if isinstance(peg_type_val, (int, float)):
                        mcap += peg_type_val

                if mcap <= 0:
                    continue

                total_mcap += mcap

                # 7d change
                mcap_change_7d = 0
                circ_prev = coin.get('circulatingPrevWeek', {})
                prev_mcap = 0
                for peg_type_val in circ_prev.values():
                    if isinstance(peg_type_val, (int, float)):
                        prev_mcap += peg_type_val
                if prev_mcap > 0:
                    mcap_change_7d = ((mcap - prev_mcap) / prev_mcap) * 100

                # Price from peggedAsset price field
                price = coin.get('price', 1.0)

                # Chains this stablecoin is on
                chain_circ = coin.get('chainCirculating', {})
                chains = list(chain_circ.keys()) if chain_circ else []

                peg_mechanism = coin.get('pegMechanism', '') or ''
                classification = STABLECOIN_CLASSIFICATIONS.get(
                    peg_mechanism.lower(), peg_mechanism or 'Unknown'
                )

                stablecoins.append({
                    'name': coin.get('name', 'Unknown'),
                    'symbol': coin.get('symbol', ''),
                    'mcap': mcap,
                    'mcap_change_7d': mcap_change_7d,
                    'price': price,
                    'chains': chains[:10],
                    'classification': classification,
                })

            # Sort by mcap desc, take top 50 (frontend handles pagination)
            stablecoins.sort(key=lambda x: x['mcap'], reverse=True)
            stablecoins = stablecoins[:50]

            result = {'total_stablecoin_mcap': total_mcap, 'stablecoins': stablecoins}
            await set_cache(cache_key, result, CACHE_TTL_WARM)
            return result

        except Exception as e:
            logger.warning(f"DefiLlama stablecoin market fetch failed: {e}")
            return {"total_stablecoin_mcap": 0, "stablecoins": []}

    async def get_all_chains_tvl(self, limit: int = 25) -> Dict:
        """Get top chains by TVL from DefiLlama (all chains, not just our 9)."""
        cache_key = f"analytics:market:chains_tvl:{limit}"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/v2/chains")
            if resp.status_code != 200:
                logger.warning(f"DefiLlama chains returned {resp.status_code}")
                return {"total_tvl": 0, "chains": []}

            raw_chains = resp.json()
            total_tvl = 0
            chains = []

            for item in raw_chains:
                tvl = item.get('tvl', 0) or 0
                total_tvl += tvl

                name = item.get('name', '')
                if name == 'Binance':
                    name = 'BSC'

                chains.append({
                    'name': name,
                    'tvl': tvl,
                    'tvl_change_1d': item.get('change_1d', 0) or 0,
                    'tvl_change_7d': item.get('change_7d', 0) or 0,
                })

            # Sort by TVL desc, take top N
            chains.sort(key=lambda x: x['tvl'], reverse=True)
            chains = chains[:limit]

            result = {'total_tvl': total_tvl, 'chains': chains}
            await set_cache(cache_key, result, CACHE_TTL_WARM)
            return result

        except Exception as e:
            logger.warning(f"DefiLlama all chains TVL fetch failed: {e}")
            return {"total_tvl": 0, "chains": []}

    async def get_rwa_protocols(self, limit: int = 15) -> Dict:
        """Get RWA (Real World Asset) protocols from DefiLlama."""
        cache_key = f"analytics:market:rwa:{limit}"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/protocols")
            if resp.status_code != 200:
                logger.warning(f"DefiLlama protocols returned {resp.status_code}")
                return {"total_rwa_tvl": 0, "protocols": []}

            all_protocols = resp.json()
            rwa_protocols = []
            total_rwa_tvl = 0

            for p in all_protocols:
                category = p.get('category', '')
                if category != 'RWA':
                    continue

                tvl = p.get('tvl', 0) or 0
                total_rwa_tvl += tvl

                rwa_protocols.append({
                    'name': p.get('name', 'Unknown'),
                    'tvl': tvl,
                    'tvl_change_1d': p.get('change_1d', 0) or 0,
                    'category': category,
                    'chains': (p.get('chains', []) or [])[:5],
                    'logo': p.get('logo', ''),
                })

            # Sort by TVL desc, take top N
            rwa_protocols.sort(key=lambda x: x['tvl'], reverse=True)
            rwa_protocols = rwa_protocols[:limit]

            result = {'total_rwa_tvl': total_rwa_tvl, 'protocols': rwa_protocols}
            await set_cache(cache_key, result, CACHE_TTL_WARM)
            return result

        except Exception as e:
            logger.warning(f"DefiLlama RWA protocols fetch failed: {e}")
            return {"total_rwa_tvl": 0, "protocols": []}

    async def get_chain_stablecoin_supply(self, chain: str) -> float:
        """Get total stablecoin supply circulating on a specific chain."""
        slug = CHAIN_SLUGS.get(chain, chain)
        cache_key = f"analytics:stablecoin_supply:{slug}"
        cached = await get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            resp = await self.client.get("https://stablecoins.llama.fi/stablecoins?includePrices=true")
            if resp.status_code == 200:
                total = 0
                for coin in resp.json().get('peggedAssets', []):
                    chain_circ = coin.get('chainCirculating', {}).get(slug, {})
                    for peg_type in chain_circ.values():
                        if isinstance(peg_type, dict):
                            total += peg_type.get('peggedUSD', 0)
                await set_cache(cache_key, total, CACHE_TTL_WARM)
                return total
        except Exception as e:
            logger.warning(f"DefiLlama stablecoin supply for {chain} failed: {e}")

        return 0


chain_analytics_service = ChainAnalyticsService()
