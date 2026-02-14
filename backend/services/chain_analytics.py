"""
Chain Analytics Service - DefiLlama integration

Provides chain-level metrics: TVL, fees, revenue, DEX volume.
All data from DefiLlama (free, no API key required).
"""

import logging
import time
from typing import Dict, List, Optional

from services.http_client import get_client
from database import get_cache, set_cache
from config import CACHE_TTL_WARM

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

        # Fetch TVL per chain
        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/v2/chains")
            if resp.status_code == 200:
                for item in resp.json():
                    name = item.get('name', '')
                    # Gecko ID match fallback
                    if name == 'Binance':
                        name = 'BSC'
                    if name in chains_data:
                        chains_data[name]['tvl'] = item.get('tvl', 0)
                        chains_data[name]['tvl_change_1d'] = item.get('change_1d', 0)
        except Exception as e:
            logger.warning(f"DefiLlama chains TVL fetch failed: {e}")

        # Fetch 24h fees & revenue
        try:
            resp = await self.client.get(f"{DEFILLAMA_BASE}/overview/fees")
            if resp.status_code == 200:
                data = resp.json()
                for protocol in data.get('protocols', []):
                    chain = protocol.get('chains', [None])
                    if isinstance(chain, list) and len(chain) == 1:
                        chain = chain[0]
                    else:
                        chain = protocol.get('chain', '')
                    # Skip multi-chain protocols for per-chain breakdown
                    # (they'd be double-counted)

                # Use totalDataChartBreakdown or chain field from data
                for chain_item in data.get('allChains', []):
                    pass  # allChains is just a list of chain names

                # Better approach: use chain-level totals from the response
                chain_totals = {}
                for protocol in data.get('protocols', []):
                    chains = protocol.get('chains', [])
                    total24h = protocol.get('total24h') or 0
                    revenue24h = protocol.get('totalRevenue24h') or protocol.get('revenue24h') or 0
                    # Distribute evenly across chains if multi-chain
                    if chains and total24h:
                        per_chain = total24h / len(chains)
                        rev_per_chain = revenue24h / len(chains) if revenue24h else 0
                        for c in chains:
                            if c == 'Binance':
                                c = 'BSC'
                            if c in chains_data:
                                chains_data[c]['fees_24h'] += per_chain
                                chains_data[c]['revenue_24h'] += rev_per_chain
        except Exception as e:
            logger.warning(f"DefiLlama fees fetch failed: {e}")

        # Fetch DEX volume
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

        result = {'chains': chains_data, 'timestamp': int(time.time())}
        await set_cache(cache_key, result, CACHE_TTL_WARM)
        return result

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


chain_analytics_service = ChainAnalyticsService()
