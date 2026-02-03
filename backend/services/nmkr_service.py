"""
NMKR Service - Token image and metadata API integration

Provides methods to fetch token images and metadata for Cardano native assets
using the NMKR Studio API.

NMKR is particularly useful for tokens like Liqwid, IAG, Indy, etc. that have
proper token metadata and images but aren't available through generic crypto logo services.
"""

import httpx
import logging
import binascii
from typing import Optional, Dict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_api_key

logger = logging.getLogger(__name__)

NMKR_BASE_URL = "https://studio-api.nmkr.io"


class NMKRService:
    """Service for fetching Cardano token images and metadata from NMKR Studio API."""

    def __init__(self):
        self.base_url = NMKR_BASE_URL
        self._api_key_cache = {}

    async def get_api_key(self, user_id: int = 1) -> Optional[str]:
        """
        Get NMKR API key from database settings.

        Args:
            user_id: User ID for multi-user support

        Returns:
            API key string or None if not configured
        """
        # Check cache first (avoid repeated DB queries)
        cache_key = f"nmkr_{user_id}"
        if cache_key in self._api_key_cache:
            return self._api_key_cache[cache_key]

        try:
            api_key = await get_api_key('nmkr', user_id=user_id)
            if api_key:
                self._api_key_cache[cache_key] = api_key
                return api_key
        except Exception as e:
            logger.debug(f"Could not fetch NMKR API key: {e}")

        return None

    async def is_configured(self, user_id: int = 1) -> bool:
        """Check if NMKR API key is configured for the user."""
        api_key = await self.get_api_key(user_id)
        return api_key is not None

    def get_token_image_proxy_url(
        self,
        policy_id: str,
        token_name_hex: str
    ) -> Optional[str]:
        """
        Get proxied NMKR image URL (routes through backend to hide API key).

        The backend /nmkr/image/{policy_id}/{token_name_hex} endpoint will
        fetch the image from NMKR with proper authentication and proxy it.

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format

        Returns:
            Backend proxy URL that frontend can use

        Examples:
            >>> service.get_token_image_proxy_url(
            ...     "baa09dce474fb007b30e29eaf665e567ee7cbd9c0de00f0d2d88cf12",
            ...     "4c6971776964"
            ... )
            '/nmkr/image/baa09.../4c69...'
        """
        if not policy_id or not token_name_hex:
            logger.warning("Missing policy_id or token_name_hex for NMKR image")
            return None

        return f"/nmkr/image/{policy_id}/{token_name_hex}"

    async def get_token_image_url_with_key(
        self,
        policy_id: str,
        token_name_hex: str,
        user_id: int = 1
    ) -> Optional[str]:
        """
        Get NMKR preview image URL with API key included (async version).

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format
            user_id: User ID for API key lookup

        Returns:
            Full NMKR image URL with apikey param, or None if not configured
        """
        api_key = await self.get_api_key(user_id)
        if not api_key:
            logger.debug("NMKR API key not configured, cannot generate image URL")
            return None

        base_url = self.get_token_image_url(policy_id, token_name_hex, require_api_key=False)
        if not base_url:
            return None

        return f"{base_url}?apikey={api_key}"

    async def get_token_ipfs_image_url(
        self,
        policy_id: str,
        token_name_hex: str,
        user_id: int = 1
    ) -> Optional[str]:
        """
        Fetch token image from NMKR and convert IPFS URL to HTTP gateway URL.

        This method makes an actual API call to NMKR to get the image URL,
        then converts ipfs:// URLs to https://ipfs.io/ipfs/ gateway URLs
        that can be used directly in <img> tags.

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format
            user_id: User ID for API key lookup

        Returns:
            HTTP gateway URL for the image, or None if fetch fails
        """
        api_key = await self.get_api_key(user_id)
        if not api_key:
            return None

        nmkr_url = f"{self.base_url}/v2/GetPreviewImageForToken/{policy_id}/{token_name_hex}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    nmkr_url,
                    headers={"Authorization": api_key}
                )

                if response.status_code == 200:
                    ipfs_url = response.text.strip()

                    # Convert IPFS URL to HTTP gateway URL
                    if ipfs_url.startswith("ipfs://"):
                        ipfs_hash = ipfs_url.replace("ipfs://", "")
                        return f"https://ipfs.io/ipfs/{ipfs_hash}"
                    else:
                        # Return as-is if not IPFS
                        return ipfs_url
                else:
                    logger.debug(f"NMKR returned {response.status_code} for {policy_id}/{token_name_hex}")
                    return None

        except Exception as e:
            logger.debug(f"Failed to fetch NMKR image URL: {e}")
            return None

    async def get_cached_logo_url(
        self,
        policy_id: str,
        token_name_hex: str
    ) -> Optional[str]:
        """
        Get logo URL from database cache.

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format

        Returns:
            Cached logo URL or None if not in cache
        """
        import aiosqlite
        from config import DATABASE_PATH

        asset_id = policy_id + token_name_hex

        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    "SELECT logo_url FROM token_metadata WHERE asset_id = ?",
                    (asset_id,)
                )
                row = await cursor.fetchone()
                if row and row[0]:
                    logger.debug(f"Got cached logo URL for {asset_id}")
                    return row[0]
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")

        return None

    async def save_logo_url_to_cache(
        self,
        policy_id: str,
        token_name_hex: str,
        logo_url: str
    ):
        """
        Save logo URL to database cache.

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format
            logo_url: Logo URL to cache
        """
        import aiosqlite
        from config import DATABASE_PATH

        asset_id = policy_id + token_name_hex

        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                # Insert or update token_metadata with logo_url
                await db.execute("""
                    INSERT INTO token_metadata (asset_id, policy_id, logo_url, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(asset_id) DO UPDATE SET
                        logo_url = excluded.logo_url,
                        updated_at = datetime('now')
                """, (asset_id, policy_id, logo_url))
                await db.commit()
                logger.debug(f"Cached logo URL for {asset_id}")
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")

    async def get_token_logo_with_fallbacks(
        self,
        policy_id: str,
        token_name_hex: str,
        ticker: Optional[str] = None,
        user_id: int = 1,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get token logo with multiple fallback strategies and caching.

        Tries in order:
        1. Database cache (if use_cache=True)
        2. NMKR API (if configured)
        3. Cardano Token Registry (GitHub)
        4. Blockfrost on-chain metadata (if configured)
        5. LogoKit (ticker-based)

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format
            ticker: Optional ticker symbol for LogoKit fallback
            user_id: User ID for API key lookup
            use_cache: Whether to check/update cache (default: True)

        Returns:
            Image URL or None if all methods fail
        """
        # Check cache first
        if use_cache:
            cached_url = await self.get_cached_logo_url(policy_id, token_name_hex)
            if cached_url:
                return cached_url
        # Try to fetch logo from various sources
        logo_url = None

        # Try NMKR first (if configured)
        if await self.is_configured(user_id):
            nmkr_url = await self.get_token_ipfs_image_url(policy_id, token_name_hex, user_id)
            if nmkr_url:
                logger.debug(f"Got logo from NMKR for {policy_id}/{token_name_hex}")
                logo_url = nmkr_url

        # Try Cardano Token Registry (free, no auth required)
        if not logo_url:
            try:
                # Registry uses GitHub raw JSON with base64-encoded logos
                registry_url = f"https://raw.githubusercontent.com/cardano-foundation/cardano-token-registry/master/mappings/{policy_id}{token_name_hex}.json"

                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(registry_url)
                    if response.status_code == 200:
                        metadata = response.json()

                        # Extract logo from JSON structure
                        if 'logo' in metadata and 'value' in metadata['logo']:
                            logo_base64 = metadata['logo']['value']

                            # Return as data URL for direct browser display
                            data_url = f"data:image/png;base64,{logo_base64}"
                            logger.debug(f"Got logo from Cardano Token Registry for {policy_id}/{token_name_hex}")
                            logo_url = data_url
            except Exception as e:
                logger.debug(f"Cardano Token Registry check failed: {e}")

        # Try Blockfrost on-chain metadata (if configured)
        if not logo_url:
            try:
                from services.cardano import cardano_service

                if cardano_service.blockfrost_api:
                    asset_id = policy_id + token_name_hex
                    metadata = await cardano_service.get_asset_metadata(asset_id)

                    if metadata and metadata.get('onchain_metadata'):
                        onchain = metadata['onchain_metadata']

                        # Try various common metadata fields
                        onchain_logo = None
                        if 'logo' in onchain:
                            onchain_logo = onchain['logo']
                        elif 'image' in onchain:
                            onchain_logo = onchain['image']

                        if onchain_logo:
                            # Convert IPFS URLs to HTTP gateway
                            if onchain_logo.startswith('ipfs://'):
                                ipfs_hash = onchain_logo.replace('ipfs://', '')
                                onchain_logo = f"https://ipfs.io/ipfs/{ipfs_hash}"

                            logger.debug(f"Got logo from Blockfrost metadata for {policy_id}/{token_name_hex}")
                            logo_url = onchain_logo
            except Exception as e:
                logger.debug(f"Blockfrost metadata check failed: {e}")

        # Final fallback to LogoKit (if ticker provided)
        if not logo_url and ticker:
            from services.logokit_service import logokit_service
            logokit_url = logokit_service.get_crypto_logo_url(ticker, size=64)
            logger.debug(f"Falling back to LogoKit for {ticker}")
            logo_url = logokit_url

        # Save to cache before returning (if we found a URL and caching is enabled)
        if logo_url and use_cache:
            await self.save_logo_url_to_cache(policy_id, token_name_hex, logo_url)

        return logo_url

    async def prefetch_logos_for_wallet_assets(self, user_id: int = 1):
        """
        Background task to pre-fetch and cache logos for all wallet assets.

        This should be called after wallet sync to populate the logo cache
        without blocking the user.

        Args:
            user_id: User ID for API key lookup
        """
        import aiosqlite
        from config import DATABASE_PATH

        try:
            # Get all unique native assets without cached logos
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT DISTINCT
                        na.policy_id,
                        na.asset_id,
                        COALESCE(ct.ticker, tm.ticker) as ticker
                    FROM native_assets na
                    LEFT JOIN token_metadata tm ON na.asset_id = tm.asset_id
                    LEFT JOIN custom_tokens ct ON
                        ct.policy_id = na.policy_id
                        AND ct.asset_name = na.asset_name
                        AND ct.user_id = na.user_id
                    WHERE tm.logo_url IS NULL OR tm.logo_url = ''
                    LIMIT 100
                """)
                rows = await cursor.fetchall()
                assets = [dict(row) for row in rows]

            if not assets:
                logger.debug("No assets need logo pre-fetching")
                return

            logger.info(f"Pre-fetching logos for {len(assets)} assets...")

            # Fetch logos in small batches to avoid overloading APIs
            batch_size = 5
            for i in range(0, len(assets), batch_size):
                batch = assets[i:i + batch_size]

                # Process batch concurrently
                import asyncio
                tasks = []
                for asset in batch:
                    policy_id = asset['policy_id']
                    asset_id = asset['asset_id']
                    ticker = asset.get('ticker')

                    # Extract hex asset name
                    asset_name_hex = asset_id[len(policy_id):] if len(asset_id) > len(policy_id) else None

                    if policy_id and asset_name_hex:
                        task = self.get_token_logo_with_fallbacks(
                            policy_id,
                            asset_name_hex,
                            ticker=ticker,
                            user_id=user_id,
                            use_cache=True  # Will cache automatically
                        )
                        tasks.append(task)

                # Wait for batch to complete
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Small delay between batches to be nice to APIs
                await asyncio.sleep(0.5)

            logger.info(f"Completed logo pre-fetching for {len(assets)} assets")

        except Exception as e:
            logger.error(f"Logo pre-fetching failed: {e}")

    async def get_token_metadata(
        self,
        policy_id: str,
        token_name_hex: str,
        user_id: int = 1
    ) -> Optional[Dict]:
        """
        Fetch full token metadata from NMKR API (makes actual API call).

        This is useful for getting token name, description, and other metadata
        in addition to the image.

        Args:
            policy_id: Cardano policy ID (hex)
            token_name_hex: Token name in hexadecimal format
            user_id: User ID for API key lookup

        Returns:
            Token metadata dict or None if request fails

        Note:
            This makes an actual HTTP request and counts against your NMKR API quota.
            For images only, use get_token_image_url() which generates a URL.
        """
        api_key = await self.get_api_key(user_id)
        if not api_key:
            logger.warning("NMKR API key not configured")
            return None

        url = f"{self.base_url}/v2/GetAssetMetadata/{policy_id}/{token_name_hex}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": api_key}
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"NMKR API returned {response.status_code} for {policy_id}/{token_name_hex}")
                    return None

        except Exception as e:
            logger.error(f"Failed to fetch NMKR metadata: {e}")
            return None

    async def get_token_info_batch(
        self,
        tokens: list[tuple[str, str]],
        user_id: int = 1
    ) -> Dict[str, Optional[str]]:
        """
        Get image URLs for multiple tokens at once.

        Args:
            tokens: List of (policy_id, token_name_hex) tuples
            user_id: User ID for API key lookup

        Returns:
            Dict mapping "policy_id:token_name_hex" to image URL

        Example:
            >>> tokens = [
            ...     ("baa09dce...", "4c6971776964"),  # Liqwid
            ...     ("f43a62fdc...", "000de140494147")  # IAG
            ... ]
            >>> urls = await service.get_token_info_batch(tokens)
        """
        api_key = await self.get_api_key(user_id)
        if not api_key:
            return {}

        result = {}
        for policy_id, token_name_hex in tokens:
            key = f"{policy_id}:{token_name_hex}"
            url = self.get_token_image_url(policy_id, token_name_hex, require_api_key=False)
            if url:
                result[key] = f"{url}?apikey={api_key}"

        return result


# Singleton instance
nmkr_service = NMKRService()
