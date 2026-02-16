"""
Stacks (STX) Blockchain Service - Fetches Stacks wallet data using Hiro API.

Hiro API provides:
- STX balance and locked STX (stacking)
- Fungible token balances (SIP-010 tokens)
- Non-fungible token holdings (SIP-009 NFTs)
- No API key required (free, public API)

API Documentation: https://docs.hiro.so/stacks/api
"""

import httpx
import logging
from typing import List, Optional

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

HIRO_BASE_URL = "https://api.mainnet.hiro.so"


class StacksService:
    """Service for fetching Stacks (STX) wallet data using Hiro API."""

    def __init__(self):
        self.base_url = HIRO_BASE_URL

    def _validate_address(self, address: str) -> bool:
        """
        Validate a Stacks address format.
        Mainnet addresses start with 'SP', testnet with 'ST'.
        """
        if not address or len(address) < 10:
            return False
        return address.startswith(('SP', 'ST'))

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including STX balance, locked STX, and token holdings.

        Uses Hiro's free API (no authentication required).
        Endpoint: GET /extended/v1/address/{principal}/balances

        Args:
            address: Stacks address (starts with SP for mainnet, ST for testnet)

        Returns:
            Dictionary with address info, balances, and token holdings, or None on error.
            Format: {
                address, balance_stx, locked_stx, tokens: [...],
                blockchain: 'stacks', source: 'hiro'
            }
        """
        if not self._validate_address(address):
            logger.error(f"Invalid Stacks address format: {address[:20]}...")
            return None

        try:
            client = get_client("hiro_stacks", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/extended/v1/address/{address}/balances",
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid Stacks address: {address}")
                return None

            if response.status_code != 200:
                logger.error(f"Hiro API error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Parse STX balance (in microSTX, 1 STX = 1,000,000 microSTX)
            stx_data = data.get('stx', {})
            balance_micro = int(stx_data.get('balance', '0'))
            locked_micro = int(stx_data.get('locked', '0'))

            balance_stx = balance_micro / 1_000_000
            locked_stx = locked_micro / 1_000_000

            # Parse fungible tokens (SIP-010)
            tokens = []
            fungible_tokens = data.get('fungible_tokens', {})
            for token_id, token_data in fungible_tokens.items():
                token_balance = int(token_data.get('balance', '0'))
                if token_balance > 0:
                    # token_id format: "SP...::token-name"
                    parts = token_id.split('::')
                    contract_id = parts[0] if parts else token_id
                    token_name = parts[1] if len(parts) > 1 else 'unknown'

                    tokens.append({
                        'token_id': token_id,
                        'contract_id': contract_id,
                        'token_name': token_name,
                        'balance': str(token_balance),
                    })

            return {
                'address': address,
                'balance_stx': f"{balance_stx:.6f}",
                'balance_micro_stx': str(balance_micro),
                'locked_stx': f"{locked_stx:.6f}",
                'locked_micro_stx': str(locked_micro),
                'tokens': tokens,
                'nft_count': sum(
                    v.get('count', 0)
                    for v in data.get('non_fungible_tokens', {}).values()
                ),
                'blockchain': 'stacks',
                'source': 'hiro',
            }

        except httpx.TimeoutException:
            logger.error(f"Hiro API timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Hiro API error: {e}")
            return None

    async def get_all_nfts(self, addresses: List[str], user_id: int = None) -> List[dict]:
        """
        Fetch all NFT holdings for the given Stacks addresses.

        Uses Hiro's NFT holdings endpoint:
        GET /extended/v1/tokens/nft/holdings?principal={address}&limit=50

        Args:
            addresses: List of Stacks wallet addresses to query.
            user_id: Optional user ID (for future cache key scoping).

        Returns:
            List of NFT objects across all provided addresses.
        """
        all_nfts = []

        for address in addresses:
            if not self._validate_address(address):
                logger.warning(f"Skipping invalid Stacks address: {address[:20]}...")
                continue

            offset = 0
            limit = 50

            while True:
                nfts_page = await self._fetch_nft_page(address, limit=limit, offset=offset)
                if nfts_page is None:
                    break

                results = nfts_page.get('results', [])
                if not results:
                    break

                for nft_data in results:
                    parsed = self._parse_nft(nft_data, address)
                    if parsed:
                        all_nfts.append(parsed)

                total = nfts_page.get('total', 0)
                offset += limit

                if offset >= total:
                    break

            logger.info(f"Fetched {len(all_nfts)} NFTs for Stacks address {address[:12]}...")

        return all_nfts

    async def _fetch_nft_page(self, address: str, limit: int = 50, offset: int = 0) -> Optional[dict]:
        """
        Fetch a single page of NFT holdings from Hiro API.

        Args:
            address: Stacks wallet address.
            limit: Number of results per page (max 50).
            offset: Pagination offset.

        Returns:
            Raw API response dict or None on error.
        """
        try:
            client = get_client("hiro_stacks", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/extended/v1/tokens/nft/holdings",
                params={
                    'principal': address,
                    'limit': limit,
                    'offset': offset,
                },
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"Hiro NFT API error: {response.status_code} - {response.text}")
                return None

            return response.json()

        except httpx.TimeoutException:
            logger.error(f"Hiro NFT API timeout for {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Hiro NFT API error: {e}")
            return None

    def _parse_nft(self, nft_data: dict, wallet_address: str) -> Optional[dict]:
        """
        Parse Hiro NFT holdings response into a standardized format.

        Args:
            nft_data: Single NFT entry from Hiro holdings API.
            wallet_address: Owner's Stacks address.

        Returns:
            Standardized NFT dictionary, or None if parsing fails.
        """
        try:
            asset_identifier = nft_data.get('asset_identifier', '')
            value_repr = nft_data.get('value', {}).get('repr', '')

            # asset_identifier format: "SP...contract::asset-name"
            parts = asset_identifier.split('::')
            contract_id = parts[0] if parts else asset_identifier
            asset_name = parts[1] if len(parts) > 1 else 'unknown'

            # value repr is typically something like "u123" (unsigned int token ID)
            token_id = value_repr.lstrip('u') if value_repr.startswith('u') else value_repr

            # Build explorer link
            explorer_url = f"https://explorer.hiro.so/txid/{nft_data.get('tx_id', '')}?chain=mainnet"

            return {
                'asset_id': f"{contract_id}::{asset_name}#{token_id}",
                'asset_identifier': asset_identifier,
                'contract_id': contract_id,
                'asset_name': asset_name,
                'token_id': token_id,
                'name': f"{asset_name} #{token_id}",
                'image_url': '',  # Hiro holdings API doesn't include metadata/images
                'collection': {
                    'name': asset_name,
                    'contract_id': contract_id,
                },
                'links': {
                    'explorer': explorer_url,
                },
                'blockchain': 'stacks',
                'wallet_address': wallet_address,
                'tx_id': nft_data.get('tx_id', ''),
                'block_height': nft_data.get('block_height', 0),
            }
        except Exception as e:
            logger.error(f"Error parsing Stacks NFT: {e}")
            return None


# Singleton instance
stacks_service = StacksService()
