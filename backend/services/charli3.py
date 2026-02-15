"""
Charli3 Service - Cardano token pricing, OHLCV history, and DEX analytics.

Charli3 provides:
- Current token prices with TVL, volume, and change data (17K+ Cardano tokens)
- OHLCV candlestick history at multiple resolutions
- DEX group/protocol listings (Minswap, SundaeSwap, etc.)
- Token logos (base64 PNG)
- SSE streaming for real-time price updates

Auth: Bearer token via Authorization header.
Base URL: https://api.charli3.io/api/v1
"""

import asyncio
import logging
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CHARLI3_BASE_URL
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Map token symbols to Charli3 policy_hex format (policy_id + hex_asset_name)
# Derived from CARDANO_TOKEN_POLICIES in pricing.py
CHARLI3_TOKEN_MAP = {
    'INDY': '533bb94a8850ee3ccbe483106489399112b74c905342cb1792a797a0494e4459',
    'LQ': 'da8c30857834c6ae7203935b89278c532b3995245295456f993e1d244c51',
    'MIN': '29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c64d494e',
    'SUNDAE': '9a9693a9a37912a5097918f97918d15240c92ab729a0b7c4aa144d7753554e444145',
    'DJED': '8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61446a65644d6963726f555344',
    'SHEN': '8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd615368656e4d6963726f555344',
    'SNEK': '279c909f348e533da5808898f87f9a14bb2c3dfbbacccd631d927a3f534e454b',
    'STRIKE': 'f13ac4d66b3ee19a6aa0f2a22298737bd907cc95121662fc971b5275535452494b45',
    'IAG': '5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114494147',
    'AGIX': 'f43a62fdc3965df486de8a0d32fe800963589c41b38946602a0dc53541474958',
    'XER': '6d06570ddd778ec7c0cca09d381eca194e90c8cffa7582879735dbde584552',
    'NIGHT': '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854',
    'FLOW': '2d9db8a89f074aa045eab177f23a3395f62ced8b53499a9e4ad46c80464c4f57',
    'WRT': 'c0ee29a85b13209423b10447d3c2e6a50641a15c57770e27cb9d5073',  # WingRiders
    'LENFI': '8fef2d34078659493ce161a6c7fba4b56afefa8535296a5743f69587',  # Lenfi
}


class Charli3Service(APIKeyManager):
    """Service for Charli3 Cardano token pricing and analytics."""

    def __init__(self):
        super().__init__(api_name='charli3', env_var='CHARLI3_API_KEY')
        self.base_url = CHARLI3_BASE_URL
        self._groups_cache: Optional[dict] = None
        self._groups_cache_time: Optional[datetime] = None
        self._symbol_info_cache: Dict[str, dict] = {}

    async def _get_headers(self) -> dict:
        """Get request headers with Bearer auth."""
        api_key = await self.get_api_key()
        if not api_key:
            return {}
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

    async def get_token_price(self, policy_hex: str) -> Optional[dict]:
        """
        Get current price for a Cardano token.

        Args:
            policy_hex: Concatenated policy_id + hex_asset_name

        Returns:
            {price, tvl, change_1h, change_24h, volume_24h} or None
        """
        if not await self.is_configured():
            return None

        try:
            headers = await self._get_headers()
            client = get_client("charli3", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/tokens/current",
                params={"policy": policy_hex},
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                if data:
                    return {
                        'price': data.get('price', 0),
                        'tvl': data.get('tvl', 0),
                        'change_1h': data.get('change1h', 0) or 0,
                        'change_24h': data.get('change24h', 0) or 0,
                        'volume_24h': data.get('volume24h', 0) or 0,
                        'source': 'Charli3'
                    }
            elif response.status_code == 429:
                logger.warning("Charli3 rate limited (429)")
            else:
                logger.debug(f"Charli3 token price error: {response.status_code}")

        except Exception as e:
            logger.error(f"Charli3 get_token_price error: {e}")

        return None

    async def get_token_prices_batch(self, symbols: List[str]) -> Dict[str, dict]:
        """
        Get prices for multiple Cardano tokens in parallel.

        Args:
            symbols: List of token symbols (e.g., ['INDY', 'MIN', 'SNEK'])

        Returns:
            {symbol: {price, tvl, change_1h, change_24h, volume_24h, source}} for each resolved symbol
        """
        if not await self.is_configured():
            return {}

        tasks = {}
        for symbol in symbols:
            policy_hex = CHARLI3_TOKEN_MAP.get(symbol.upper())
            if policy_hex:
                tasks[symbol.upper()] = self.get_token_price(policy_hex)

        if not tasks:
            return {}

        # Run all requests in parallel with semaphore to limit concurrency
        sem = asyncio.Semaphore(5)

        async def fetch_with_sem(sym, coro):
            async with sem:
                return sym, await coro

        results_raw = await asyncio.gather(
            *[fetch_with_sem(sym, coro) for sym, coro in tasks.items()],
            return_exceptions=True
        )

        results = {}
        for item in results_raw:
            if isinstance(item, Exception):
                continue
            sym, data = item
            if data:
                results[sym] = data

        if results:
            logger.info(f"Charli3: fetched prices for {len(results)} Cardano tokens")

        return results

    async def get_ohlcv_history(
        self,
        symbol: str,
        resolution: str = "1d",
        from_ts: int = 0,
        to_ts: int = 0
    ) -> Optional[List[dict]]:
        """
        Get OHLCV candlestick history for a token.

        Args:
            symbol: Token symbol (must be in CHARLI3_TOKEN_MAP)
            resolution: Candle resolution (1min, 5min, 15min, 60min, 1d)
            from_ts: Start timestamp (Unix seconds)
            to_ts: End timestamp (Unix seconds)

        Returns:
            List of {time, open, high, low, close, volume} or None
        """
        if not await self.is_configured():
            return None

        # Look up symbol in our map for the Charli3 symbol parameter
        policy_hex = CHARLI3_TOKEN_MAP.get(symbol.upper())
        if not policy_hex:
            return None

        try:
            headers = await self._get_headers()
            client = get_client("charli3", timeout=60.0)
            params = {
                "symbol": policy_hex,
                "resolution": resolution,
                "from": from_ts,
                "to": to_ts,
                "include_tvl": "false"
            }

            response = await client.get(
                f"{self.base_url}/history",
                params=params,
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                if not data:
                    return []

                candles = []
                # Charli3 returns arrays: t[], o[], h[], l[], c[], v[]
                times = data.get('t', [])
                opens = data.get('o', [])
                highs = data.get('h', [])
                lows = data.get('l', [])
                closes = data.get('c', [])
                volumes = data.get('v', [])

                for i in range(len(times)):
                    candles.append({
                        'time': times[i],
                        'open': opens[i] if i < len(opens) else 0,
                        'high': highs[i] if i < len(highs) else 0,
                        'low': lows[i] if i < len(lows) else 0,
                        'close': closes[i] if i < len(closes) else 0,
                        'volume': volumes[i] if i < len(volumes) else 0,
                    })

                logger.info(f"Charli3: fetched {len(candles)} OHLCV candles for {symbol} ({resolution})")
                return candles

            elif response.status_code == 429:
                logger.warning("Charli3 rate limited (429) on history")
            else:
                logger.warning(f"Charli3 OHLCV error: {response.status_code}")

        except Exception as e:
            logger.error(f"Charli3 get_ohlcv_history error: {e}")

        return None

    async def get_token_logo(self, policy_hex: str) -> Optional[str]:
        """
        Get base64-encoded PNG logo for a token.

        Args:
            policy_hex: Concatenated policy_id + hex_asset_name

        Returns:
            Base64 PNG string or None
        """
        if not await self.is_configured():
            return None

        try:
            headers = await self._get_headers()
            client = get_client("charli3", timeout=15.0)
            response = await client.get(
                f"{self.base_url}/tokens/logo/{policy_hex}",
                headers=headers
            )

            if response.status_code == 200:
                return response.text
            else:
                logger.debug(f"Charli3 logo not found for {policy_hex[:20]}...")

        except Exception as e:
            logger.error(f"Charli3 get_token_logo error: {e}")

        return None

    async def get_groups(self) -> List[dict]:
        """
        Get list of DEX protocols (Minswap, SundaeSwap, etc.).
        Cached for 24 hours.

        Returns:
            List of DEX group dicts
        """
        if not await self.is_configured():
            return []

        # Check cache (24hr)
        if self._groups_cache and self._groups_cache_time:
            if datetime.now() - self._groups_cache_time < timedelta(hours=24):
                return self._groups_cache.get('groups', [])

        try:
            headers = await self._get_headers()
            client = get_client("charli3", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/groups",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                groups = data if isinstance(data, list) else data.get('groups', [])
                self._groups_cache = {'groups': groups}
                self._groups_cache_time = datetime.now()
                logger.info(f"Charli3: fetched {len(groups)} DEX groups")
                return groups

        except Exception as e:
            logger.error(f"Charli3 get_groups error: {e}")

        return []

    async def get_symbol_info(self, group: str) -> List[dict]:
        """
        Get trading pairs for a specific DEX group.
        Cached for 1 hour.

        Args:
            group: DEX group name (e.g., 'minswap')

        Returns:
            List of trading pair dicts
        """
        if not await self.is_configured():
            return []

        # Check cache (1hr)
        cached = self._symbol_info_cache.get(group)
        if cached and datetime.now() - cached['time'] < timedelta(hours=1):
            return cached['data']

        try:
            headers = await self._get_headers()
            client = get_client("charli3", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/symbol_info",
                params={"group": group},
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                pairs = data if isinstance(data, list) else data.get('pairs', [])
                self._symbol_info_cache[group] = {
                    'data': pairs,
                    'time': datetime.now()
                }
                return pairs

        except Exception as e:
            logger.error(f"Charli3 get_symbol_info error for {group}: {e}")

        return []

    async def stream_tokens(self, pool_ids: List[str]) -> AsyncGenerator:
        """
        Stream real-time price updates via SSE.

        Args:
            pool_ids: List of pool IDs to subscribe to

        Yields:
            Parsed SSE event dicts with price updates
        """
        if not await self.is_configured():
            return

        try:
            import httpx
            headers = await self._get_headers()
            headers["Accept"] = "text/event-stream"

            async with httpx.AsyncClient(timeout=None) as stream_client:
                async with stream_client.stream(
                    "POST",
                    f"{self.base_url}/tokens/stream",
                    json=pool_ids,
                    headers=headers
                ) as response:
                    if response.status_code != 200:
                        logger.error(f"Charli3 SSE stream error: {response.status_code}")
                        return

                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                import json
                                event_data = json.loads(line[5:].strip())
                                yield event_data
                            except Exception:
                                continue

        except Exception as e:
            logger.error(f"Charli3 stream error: {e}")

    def clear_cache(self):
        """Clear all caches."""
        self._groups_cache = None
        self._groups_cache_time = None
        self._symbol_info_cache.clear()


# Singleton instance
charli3_service = Charli3Service()
