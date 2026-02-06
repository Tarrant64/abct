"""
Algorand NFT Service - Fetches Algorand NFT metadata and images.

Supports ARC-3 and ARC-69 NFT standards on Algorand.
Handles IPFS gateway resolution for metadata and images.
"""

import httpx
import logging
import json
from typing import Optional, Dict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.algorand import algorand_service
from services.http_client import get_client

logger = logging.getLogger(__name__)

# IPFS gateways (fallback chain)
IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://dweb.link/ipfs/"
]


class AlgorandNFTService:
    """Service for fetching Algorand NFT metadata and images."""

    def __init__(self):
        self._metadata_cache: Dict[int, dict] = {}  # asset_id -> metadata

    def _resolve_ipfs_url(self, url: str) -> str:
        """
        Convert IPFS URL to HTTP gateway URL.

        Supports:
        - ipfs://QmXxx... -> https://ipfs.io/ipfs/QmXxx...
        - ipfs://ipfs/QmXxx... -> https://ipfs.io/ipfs/QmXxx...
        """
        if not url:
            return url

        if url.startswith('ipfs://'):
            # Remove ipfs:// prefix
            ipfs_path = url[7:]
            # Remove /ipfs/ if present
            if ipfs_path.startswith('ipfs/'):
                ipfs_path = ipfs_path[5:]
            # Use first gateway
            return f"{IPFS_GATEWAYS[0]}{ipfs_path}"

        return url

    async def _fetch_json_from_url(self, url: str) -> Optional[dict]:
        """Fetch JSON data from a URL with IPFS gateway fallback."""
        if not url:
            return None

        # Resolve IPFS URLs
        resolved_url = self._resolve_ipfs_url(url)

        # Try each gateway if IPFS
        urls_to_try = []
        if 'ipfs' in resolved_url.lower():
            # Extract IPFS hash
            ipfs_hash = None
            for part in resolved_url.split('/'):
                if part.startswith('Qm') or part.startswith('bafy'):
                    ipfs_hash = part
                    break

            if ipfs_hash:
                urls_to_try = [f"{gateway}{ipfs_hash}" for gateway in IPFS_GATEWAYS]
        else:
            urls_to_try = [resolved_url]

        for url_attempt in urls_to_try:
            try:
                client = get_client("ipfs_gateway", timeout=15.0)
                response = await client.get(url_attempt)

                if response.status_code == 200:
                    return response.json()

            except Exception as e:
                logger.debug(f"Failed to fetch JSON from {url_attempt[:50]}...: {e}")
                continue

        return None

    async def fetch_nft_metadata(self, asset_id: int) -> Optional[dict]:
        """
        Fetch NFT metadata from IPFS or ARC-3/ARC-69 standard.

        Returns:
        {
            'asset_id': 123456,
            'name': 'NFT Name',
            'description': 'NFT Description',
            'image': 'ipfs://...' or 'https://...',
            'image_url': 'https://...',  # Resolved HTTP URL
            'properties': {...},  # Additional metadata
            'standard': 'ARC3' or 'ARC69'
        }
        """
        # Check cache
        if asset_id in self._metadata_cache:
            return self._metadata_cache[asset_id]

        # Get asset info from Algorand service
        asset_info = await algorand_service.get_asset_info(asset_id)
        if not asset_info:
            return None

        metadata_url = asset_info.get('url', '')
        metadata_hash = asset_info.get('metadata_hash', '')

        metadata = {
            'asset_id': asset_id,
            'name': asset_info.get('name', ''),
            'unit_name': asset_info.get('unit_name', ''),
            'description': '',
            'image': None,
            'image_url': None,
            'properties': {},
            'standard': 'Unknown'
        }

        # Check if this looks like an NFT (total supply of 1 or low decimals)
        total = asset_info.get('total', 0)
        decimals = asset_info.get('decimals', 0)
        is_likely_nft = (total == 1 and decimals == 0) or total <= 1000

        if not is_likely_nft:
            return metadata

        # Try to fetch metadata from URL if available
        if metadata_url:
            fetched_metadata = await self._fetch_json_from_url(metadata_url)

            if fetched_metadata:
                # ARC-3 format
                metadata['standard'] = 'ARC3'
                metadata['description'] = fetched_metadata.get('description', '')
                metadata['image'] = fetched_metadata.get('image', '')
                metadata['properties'] = fetched_metadata.get('properties', {})

                # Resolve image URL
                if metadata['image']:
                    metadata['image_url'] = self._resolve_ipfs_url(metadata['image'])

        # ARC-69 uses metadata in asset note (not commonly exposed via public APIs)
        # Would need to query transactions to get ARC-69 metadata

        # Cache the result
        self._metadata_cache[asset_id] = metadata
        return metadata

    async def get_nft_image_url(self, metadata: dict) -> Optional[str]:
        """
        Extract and resolve NFT image URL (IPFS gateway support).

        Args:
            metadata: NFT metadata dict from fetch_nft_metadata()

        Returns:
            Resolved HTTP URL for the image
        """
        if not metadata:
            return None

        # Try image_url first (already resolved)
        if metadata.get('image_url'):
            return metadata['image_url']

        # Fall back to resolving image field
        if metadata.get('image'):
            return self._resolve_ipfs_url(metadata['image'])

        return None

    async def get_nfts_for_address(self, address: str) -> list:
        """
        Get all NFTs for an Algorand address.

        Returns list of NFT metadata dicts.
        """
        if not algorand_service.is_algorand_address(address):
            return []

        # Get all assets
        assets = await algorand_service.get_wallet_assets(address)

        nfts = []
        for asset in assets:
            asset_id = asset.get('asset_id')
            if not asset_id:
                continue

            # Fetch metadata
            metadata = await self.fetch_nft_metadata(asset_id)
            if metadata:
                # Add balance info
                metadata['balance'] = asset.get('amount', 0)
                metadata['decimals'] = asset.get('decimals', 0)
                nfts.append(metadata)

        return nfts

    def clear_cache(self):
        """Clear the metadata cache."""
        self._metadata_cache.clear()
        logger.info("Algorand NFT cache cleared")


# Singleton instance
algorand_nft_service = AlgorandNFTService()
