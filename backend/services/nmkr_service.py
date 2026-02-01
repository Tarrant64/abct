"""
NMKR Service - Token image and metadata API integration

Provides methods to fetch token images and metadata for Cardano native assets
using the NMKR Studio API.

NMKR is particularly useful for tokens like Liqwid, IAG, Indy, etc. that have
proper token metadata and images but aren't available through generic crypto logo services.
"""

import httpx
import logging
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
