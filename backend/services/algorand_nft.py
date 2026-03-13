"""
Algorand NFT Service - Fetches Algorand NFT metadata and images.

Supports ARC-3 and ARC-69 NFT standards on Algorand.
Handles IPFS gateway resolution for metadata and images.
"""

import httpx
import logging
import json
from typing import Optional, Dict, List
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.algorand import algorand_service
from services.http_client import get_client
from database import get_all_wallets

logger = logging.getLogger(__name__)

# IPFS gateways (fallback chain)
IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
    "https://dweb.link/ipfs/",
    "https://w3s.link/ipfs/"
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

        # Check if this looks like an NFT (total supply of 1 or low decimals)
        total = asset_info.get('total', 0)
        decimals = asset_info.get('decimals', 0)
        is_likely_nft = (total == 1 and decimals == 0) or (total <= 1000 and decimals == 0)

        metadata = {
            'asset_id': asset_id,
            'name': asset_info.get('name', ''),
            'unit_name': asset_info.get('unit_name', ''),
            'description': '',
            'image': None,
            'image_url': None,
            'properties': {},
            'standard': 'Unknown',
            'is_likely_nft': is_likely_nft,
            'creator': asset_info.get('creator', ''),
        }

        if not is_likely_nft:
            return metadata

        # Try to fetch metadata from URL if available
        if metadata_url:
            # Strip URL fragment (e.g. #i, #arc3) before processing
            clean_url = metadata_url.split('#')[0] if '#' in metadata_url else metadata_url

            # Check if URL points directly to an image (common for some Algorand NFTs)
            image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')
            url_lower = clean_url.lower()
            is_direct_image = any(url_lower.endswith(ext) for ext in image_extensions)

            if is_direct_image:
                # URL is the image itself, not metadata JSON
                metadata['image'] = metadata_url
                metadata['image_url'] = self._resolve_ipfs_url(metadata_url)
                metadata['standard'] = 'Direct'
            else:
                # Try fetching as JSON metadata (ARC-3)
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
                else:
                    # JSON fetch failed — URL may be an image without extension
                    # Use the URL as a direct image link as fallback
                    resolved = self._resolve_ipfs_url(metadata_url)
                    if resolved and ('ipfs' in resolved.lower() or resolved.startswith('http')):
                        metadata['image'] = metadata_url
                        metadata['image_url'] = resolved
                        metadata['standard'] = 'Direct'

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

        Returns list of normalized NFT dicts (only assets that pass the NFT heuristic).
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
            if not metadata or not metadata.get('is_likely_nft'):
                continue

            # Normalize to frontend-expected format (matching other chains)
            nft = {
                'name': metadata.get('name') or metadata.get('unit_name') or f'ASA #{asset_id}',
                'asset_id': asset_id,
                'image_url': metadata.get('image_url'),
                'collection': {
                    'name': metadata.get('unit_name') or metadata.get('creator', '')[:12] or 'Unknown',
                },
                'description': metadata.get('description', ''),
                'price_usd': 0,  # No pricing source for Algorand NFTs yet
                'blockchain': 'algorand',
                'standard': metadata.get('standard', 'Unknown'),
                'balance': asset.get('amount', 0),
            }
            nfts.append(nft)

        return nfts

    async def get_nft_summary(self, user_id: int) -> dict:
        """
        Get NFT summary across all Algorand wallets for a user.

        Returns { total_nfts, total_value_usd, collections }
        """
        wallets = await get_all_wallets(user_id=user_id)
        algo_wallets = [w for w in wallets if w['blockchain'] == 'algorand']

        total_nfts = 0
        collections_seen = set()

        for wallet in algo_wallets:
            try:
                nfts = await self.get_nfts_for_address(wallet['address'])
                total_nfts += len(nfts)
                for nft in nfts:
                    col_name = nft.get('collection', {}).get('name', '')
                    if col_name:
                        collections_seen.add(col_name)
            except Exception as e:
                logger.error(f"Error fetching Algorand NFTs for {wallet['address'][:12]}...: {e}")

        return {
            'total_nfts': total_nfts,
            'total_value_usd': 0,  # No pricing source for Algorand NFTs
            'collections': list(collections_seen),
        }

    def clear_cache(self):
        """Clear the metadata cache."""
        self._metadata_cache.clear()
        logger.info("Algorand NFT cache cleared")


# Singleton instance
algorand_nft_service = AlgorandNFTService()
