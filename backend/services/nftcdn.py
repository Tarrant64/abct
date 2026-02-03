"""
NFT CDN Service - Fetches Cardano NFT metadata and images.

Priority service for NFT metadata over TapTools.
Documentation: https://nftcdn.io/doc
"""

import httpx
import logging
from typing import Optional, Dict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

NFTCDN_BASE_URL = "https://api.nftcdn.io/v1"


class NFTCDNService(APIKeyManager):
    """Service for fetching Cardano NFT metadata and images from NFT CDN."""

    def __init__(self):
        super().__init__(api_name='nftcdn', env_var='NFTCDN_API_KEY')
        self.base_url = NFTCDN_BASE_URL

    async def _get_headers(self) -> dict:
        """Get request headers with API key."""
        api_key = await self.get_api_key()
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def get_nft_metadata(self, policy_id: str, asset_name: str = None) -> Optional[Dict]:
        """
        Get NFT metadata for a specific policy or asset.

        Args:
            policy_id: NFT policy ID
            asset_name: Optional asset name (hex encoded)

        Returns:
            NFT metadata dict or None
        """
        if not await self.is_configured():
            logger.debug("NFT CDN API not configured")
            return None

        try:
            headers = await self._get_headers()

            # Build URL
            if asset_name:
                url = f"{self.base_url}/nft/{policy_id}/{asset_name}"
            else:
                url = f"{self.base_url}/policy/{policy_id}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.debug(f"NFT not found: {policy_id}")
                    return None
                else:
                    logger.error(f"NFT CDN API error: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching NFT metadata from NFT CDN: {e}")
            return None

    async def get_nft_image(self, policy_id: str, asset_name: str) -> Optional[str]:
        """
        Get NFT image URL.

        Args:
            policy_id: NFT policy ID
            asset_name: Asset name (hex encoded)

        Returns:
            Image URL or None
        """
        metadata = await self.get_nft_metadata(policy_id, asset_name)
        if not metadata:
            return None

        # Try to extract image URL from metadata
        if isinstance(metadata, dict):
            # Check common image field locations
            if 'image' in metadata:
                return metadata['image']
            elif 'metadata' in metadata and 'image' in metadata['metadata']:
                return metadata['metadata']['image']

        return None

    async def get_collection_metadata(self, policy_id: str) -> Optional[Dict]:
        """
        Get collection-level metadata for a policy ID.

        Args:
            policy_id: NFT policy ID

        Returns:
            Collection metadata dict with name, description, etc. or None
        """
        if not await self.is_configured():
            logger.debug("NFT CDN API not configured")
            return None

        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/policy/{policy_id}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()

                    # Extract collection info from response
                    if isinstance(data, dict):
                        collection_info = {
                            'name': data.get('collection_name') or data.get('name') or data.get('projectName'),
                            'description': data.get('description') or data.get('projectDescription'),
                            'policy_id': policy_id,
                            'source': 'nftcdn'
                        }

                        # Add any additional fields that might be useful
                        if 'supply' in data:
                            collection_info['supply'] = data['supply']
                        if 'website' in data:
                            collection_info['website'] = data['website']
                        if 'twitter' in data:
                            collection_info['twitter'] = data['twitter']

                        # Only return if we got a collection name
                        if collection_info['name']:
                            logger.info(f"Found collection name '{collection_info['name']}' from NFT CDN for policy {policy_id[:16]}...")
                            return collection_info

                    return None
                elif response.status_code == 404:
                    logger.debug(f"Collection not found in NFT CDN: {policy_id[:16]}...")
                    return None
                else:
                    logger.debug(f"NFT CDN API error {response.status_code} for policy: {policy_id[:16]}...")
                    return None

        except Exception as e:
            logger.debug(f"Error fetching collection from NFT CDN for {policy_id[:16]}...: {e}")
            return None


# Singleton instance
nftcdn_service = NFTCDNService()
