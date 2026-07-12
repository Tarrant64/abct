"""
Token Image Cache Service

Downloads and caches cryptocurrency token images locally.
Eliminates runtime dependency on CoinGecko CDN for token logos.
Falls back to LogoKit if original source unavailable.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from config import DATA_DIR
from services.http_client import get_client

logger = logging.getLogger(__name__)

IMAGE_DIR = DATA_DIR / "token_images"


class ImageCacheService:
    """Caches token logo images on disk to avoid CDN dependency at runtime."""

    def __init__(self):
        self._dir = IMAGE_DIR

    async def init_cache(self) -> None:
        """Create the cache directory if it doesn't exist."""
        await asyncio.to_thread(self._dir.mkdir, parents=True, exist_ok=True)
        logger.info(f"Image cache directory ready: {self._dir}")

    async def get_image_path(self, symbol: str) -> Optional[str]:
        """Return the path to a cached image, or None if not cached."""
        path = self._dir / f"{symbol.lower()}.png"
        exists = await asyncio.to_thread(path.exists)
        if exists:
            return str(path)
        return None

    async def cache_image(self, symbol: str, image_url: str) -> bool:
        """Download an image from *image_url* and save it to disk.

        Returns True on success, False otherwise.
        """
        try:
            client = get_client("image_cache", timeout=15.0)
            response = await client.get(image_url)
            if response.status_code != 200:
                logger.debug(f"Image download failed for {symbol}: HTTP {response.status_code}")
                return False

            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                logger.debug(f"Non-image content-type for {symbol}: {content_type}")
                return False

            dest = self._dir / f"{symbol.lower()}.png"
            await asyncio.to_thread(dest.write_bytes, response.content)
            logger.debug(f"Cached image for {symbol} ({len(response.content)} bytes)")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache image for {symbol}: {e}")
            return False

    async def get_or_fetch_image(self, symbol: str) -> Optional[str]:
        """Check cache first; if missing, try fallback sources and save.

        Fallback chain:
        1. CoinGecko image URL from pricing cache
        2. CoinGecko /coins/{id} lookup (works before any pricing cycle)
        3. CoinPaprika coin logo
        4. LogoKit URL
        """
        # Already cached?
        path = await self.get_image_path(symbol)
        if path:
            return path

        # --- Source 1: pricing service cache (CoinGecko image field) ---
        try:
            from services.pricing import pricing_service
            cache_entry = pricing_service.cache.get(symbol.upper(), {})
            cg_image_url = cache_entry.get("image")
            if cg_image_url:
                if await self.cache_image(symbol, cg_image_url):
                    return await self.get_image_path(symbol)
        except Exception as e:
            logger.debug(f"Pricing cache image lookup failed for {symbol}: {e}")

        # --- Source 2: CoinGecko coin lookup ---
        # The pricing cache only carries an image after a markets fetch has
        # included the symbol, so ask CoinGecko directly as well.
        try:
            from services.pricing import ASSET_TO_COINGECKO
            cg_id = ASSET_TO_COINGECKO.get(symbol.upper())
            if cg_id:
                client = get_client("image_cache", timeout=15.0)
                resp = await client.get(
                    f"https://api.coingecko.com/api/v3/coins/{cg_id}",
                    params={"localization": "false", "tickers": "false",
                            "market_data": "false", "community_data": "false",
                            "developer_data": "false"},
                )
                if resp.status_code == 200:
                    img = resp.json().get("image", {})
                    cg_image = img.get("small") or img.get("large") or img.get("thumb")
                    if cg_image and await self.cache_image(symbol, cg_image):
                        return await self.get_image_path(symbol)
        except Exception as e:
            logger.debug(f"CoinGecko coin image lookup failed for {symbol}: {e}")

        # --- Source 3: CoinPaprika ---
        try:
            from services.coinpaprika import SYMBOL_TO_COINPAPRIKA
            pap_id = SYMBOL_TO_COINPAPRIKA.get(symbol.upper())
            if pap_id:
                client = get_client("image_cache", timeout=15.0)
                resp = await client.get(f"https://api.coinpaprika.com/v1/coins/{pap_id}")
                if resp.status_code == 200:
                    logo_url = resp.json().get("logo")
                    if logo_url and await self.cache_image(symbol, logo_url):
                        return await self.get_image_path(symbol)
        except Exception as e:
            logger.debug(f"CoinPaprika image lookup failed for {symbol}: {e}")

        # --- Source 4: LogoKit ---
        logokit_url = f"https://img.logokit.com/crypto/{symbol.upper()}?size=128"
        if await self.cache_image(symbol, logokit_url):
            return await self.get_image_path(symbol)

        return None

    async def warm_image_cache(self) -> None:
        """Pre-fetch images for all known symbols that are not yet cached.

        Called at startup to populate the cache in the background.
        """
        from services.pricing import ASSET_TO_COINGECKO, CARDANO_TOKEN_POLICIES

        all_symbols = set(ASSET_TO_COINGECKO.keys()) | set(CARDANO_TOKEN_POLICIES.keys())
        logger.info(f"Warming image cache for {len(all_symbols)} symbols")

        cached = 0
        fetched = 0
        for symbol in sorted(all_symbols):
            existing = await self.get_image_path(symbol)
            if existing:
                cached += 1
                continue
            result = await self.get_or_fetch_image(symbol)
            if result:
                fetched += 1
            # Small delay to avoid hammering upstream APIs
            await asyncio.sleep(0.25)

        logger.info(
            f"Image cache warm complete: {cached} already cached, "
            f"{fetched} newly fetched, {len(all_symbols) - cached - fetched} failed"
        )

    async def get_cache_stats(self) -> dict:
        """Return cache statistics: total files and total disk usage."""
        if not await asyncio.to_thread(self._dir.exists):
            return {"total_cached": 0, "disk_usage_bytes": 0}

        def _stats():
            files = list(self._dir.glob("*.png"))
            total_bytes = sum(f.stat().st_size for f in files)
            return len(files), total_bytes

        count, size = await asyncio.to_thread(_stats)
        return {"total_cached": count, "disk_usage_bytes": size}


# Singleton
image_cache_service = ImageCacheService()
