"""
NMKR Studio Service - Fetches Cardano NFT metadata via NMKR API.

Priority service for NFT metadata over TapTools.
Documentation: https://studio-api.nmkr.io/swagger/index.html
"""

import httpx
import logging
from typing import Optional, Dict, List
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

NMKR_BASE_URL = "https://studio-api.nmkr.io/v2"


class NMKRService(APIKeyManager):
    """Service for fetching Cardano NFT metadata from NMKR Studio API."""

    def __init__(self):
        super().__init__(api_name='nmkr', env_var='NMKR_API_KEY')
        self.base_url = NMKR_BASE_URL

    async def _get_headers(self) -> dict:
        """Get request headers with API key."""
        api_key = await self.get_api_key()
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def get_nft_details(self, policy_id: str, asset_name_hex: str = None) -> Optional[Dict]:
        """
        Get NFT details from NMKR.

        Args:
            policy_id: NFT policy ID
            asset_name_hex: Optional asset name in hex

        Returns:
            NFT details dict or None
        """
        if not await self.is_configured():
            logger.debug("NMKR API not configured")
            return None

        try:
            headers = await self._get_headers()

            # NMKR uses combined asset ID (policy + asset name)
            if asset_name_hex:
                asset_id = f"{policy_id}{asset_name_hex}"
            else:
                asset_id = policy_id

            url = f"{self.base_url}/GetNftDetails/{asset_id}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.debug(f"NFT not found in NMKR: {asset_id}")
                    return None
                else:
                    logger.error(f"NMKR API error: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching NFT from NMKR: {e}")
            return None

    async def get_nft_metadata(self, policy_id: str, asset_name_hex: str) -> Optional[Dict]:
        """
        Get NFT metadata.

        Args:
            policy_id: NFT policy ID
            asset_name_hex: Asset name in hex

        Returns:
            Metadata dict or None
        """
        details = await self.get_nft_details(policy_id, asset_name_hex)
        if not details:
            return None

        # Extract metadata from response
        if isinstance(details, dict):
            return details.get('metadata', details)

        return None

    async def get_nft_image(self, policy_id: str, asset_name_hex: str) -> Optional[str]:
        """
        Get NFT image URL.

        Args:
            policy_id: NFT policy ID
            asset_name_hex: Asset name in hex

        Returns:
            Image URL or None
        """
        details = await self.get_nft_details(policy_id, asset_name_hex)
        if not details:
            return None

        # Try to extract image URL
        if isinstance(details, dict):
            # Check various possible image field locations
            if 'image' in details:
                return details['image']
            elif 'ipfsLink' in details:
                return details['ipfsLink']
            elif 'displayImageUrl' in details:
                return details['displayImageUrl']
            elif 'metadata' in details:
                metadata = details['metadata']
                if 'image' in metadata:
                    return metadata['image']

        return None

    async def get_collection_metadata(self, policy_id: str) -> Optional[Dict]:
        """
        Get collection-level metadata for a policy ID.

        Note: NMKR doesn't have a direct policy-level endpoint,
        so this fetches details for the first asset in the policy.

        Args:
            policy_id: NFT policy ID

        Returns:
            Collection metadata dict with name, description, etc. or None
        """
        if not await self.is_configured():
            logger.debug("NMKR API not configured")
            return None

        try:
            headers = await self._get_headers()

            # NMKR doesn't have a policy-only endpoint
            # We could try to get project details by policy, but it's not directly supported
            # For now, return None and let other services handle it
            logger.debug(f"NMKR doesn't support policy-level queries for {policy_id[:16]}...")
            return None

        except Exception as e:
            logger.debug(f"Error fetching collection from NMKR for {policy_id[:16]}...: {e}")
            return None


# Singleton instance
nmkr_service = NMKRService()
