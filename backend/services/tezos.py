"""
Tezos Blockchain Service

Fetches XTZ balance, token holdings, delegation info, and NFTs using
the TzKT API (free, no API key required).

API docs: https://api.tzkt.io

Usage:
    from services.tezos import tezos_service

    info = await tezos_service.get_address_info("tz1...")
    nfts = await tezos_service.get_all_nfts(["tz1..."], user_id=1)
"""

import httpx
from typing import Optional, List
import logging

from services.http_client import get_client

logger = logging.getLogger(__name__)

TZKT_BASE_URL = "https://api.tzkt.io/v1"


class TezosService:
    """Service for fetching Tezos wallet data using the TzKT API."""

    def __init__(self):
        self.base_url = TZKT_BASE_URL

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including XTZ balance, delegation, and token holdings.

        Uses TzKT free API (no authentication required).

        Args:
            address: Tezos address (tz1/tz2/tz3 implicit or KT1 contract)

        Returns:
            Dict with balance, delegation, and token info, or None on error.
        """
        try:
            client = get_client("tzkt", timeout=30.0)

            # Fetch account info and token balances in parallel
            account_resp = await client.get(
                f"{self.base_url}/accounts/{address}",
                timeout=30.0
            )

            if account_resp.status_code == 400:
                logger.error(f"Invalid Tezos address: {address}")
                return None

            if account_resp.status_code == 204:
                # Address exists but has no on-chain activity
                return {
                    'address': address,
                    'balance_xtz': 0.0,
                    'balance_mutez': 0,
                    'delegate': None,
                    'tokens': [],
                    'blockchain': 'tezos',
                    'source': 'tzkt'
                }

            if account_resp.status_code != 200:
                logger.error(f"TzKT account error: {account_resp.status_code} - {account_resp.text}")
                return None

            account_data = account_resp.json()

            # Balance is in mutez (1 XTZ = 1,000,000 mutez)
            balance_mutez = account_data.get('balance', 0)
            balance_xtz = balance_mutez / 1_000_000

            # Extract delegation info
            delegate_info = account_data.get('delegate')
            delegate = None
            if delegate_info:
                delegate = {
                    'alias': delegate_info.get('alias'),
                    'address': delegate_info.get('address')
                }

            staking_balance = account_data.get('stakingBalance', 0)

            # Fetch token balances
            tokens = await self._get_token_balances(address)

            return {
                'address': address,
                'balance_xtz': balance_xtz,
                'balance_mutez': balance_mutez,
                'type': account_data.get('type'),
                'alias': account_data.get('alias'),
                'delegate': delegate,
                'staking_balance_mutez': staking_balance,
                'staking_balance_xtz': staking_balance / 1_000_000 if staking_balance else 0.0,
                'tokens': tokens or [],
                'blockchain': 'tezos',
                'source': 'tzkt'
            }

        except httpx.TimeoutException:
            logger.error(f"TzKT timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"TzKT error for address {address}: {e}")
            return None

    async def _get_token_balances(self, address: str) -> Optional[list]:
        """
        Get FA1.2 and FA2 token balances for an address.

        Args:
            address: Tezos address

        Returns:
            List of token balance dicts, or None on error.
        """
        try:
            client = get_client("tzkt", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/tokens/balances",
                params={
                    'account': address,
                    'balance.gt': '0',
                    'limit': 100,
                    'sort.desc': 'balance'
                },
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"TzKT token balances error: {response.status_code}")
                return None

            raw_tokens = response.json()
            tokens = []

            for item in raw_tokens:
                token_info = item.get('token', {})
                metadata = token_info.get('metadata') or {}
                decimals = int(metadata.get('decimals', 0))
                raw_balance = int(item.get('balance', '0'))

                # Skip NFTs (decimals=0 with balance=1 on FA2) — those go through get_all_nfts
                standard = token_info.get('standard')
                if standard == 'fa2' and decimals == 0:
                    continue

                # Convert balance using decimals
                if decimals > 0:
                    display_balance = raw_balance / (10 ** decimals)
                else:
                    display_balance = raw_balance

                tokens.append({
                    'contract': token_info.get('contract', {}).get('address', ''),
                    'token_id': token_info.get('tokenId', '0'),
                    'standard': standard,
                    'symbol': metadata.get('symbol', ''),
                    'name': metadata.get('name', ''),
                    'decimals': decimals,
                    'balance_raw': str(raw_balance),
                    'balance': display_balance,
                    'thumbnail_uri': metadata.get('thumbnailUri', ''),
                })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching token balances for {address}: {e}")
            return None

    async def get_all_nfts(self, addresses: List[str], user_id: int = None) -> List[dict]:
        """
        Get all NFTs across the provided Tezos addresses.

        Fetches FA2 tokens with decimals=0, which is the standard NFT pattern
        on Tezos.

        Args:
            addresses: List of Tezos wallet addresses to scan
            user_id: Optional user ID (for future cache keying)

        Returns:
            List of NFT objects.
        """
        all_nfts = []
        seen_ids = set()

        for address in addresses:
            nfts = await self._get_nfts_for_address(address)
            if not nfts:
                continue

            for nft in nfts:
                # Deduplicate by unique asset ID (contract:tokenId)
                asset_id = nft.get('asset_id', '')
                if asset_id in seen_ids:
                    continue
                seen_ids.add(asset_id)
                all_nfts.append(nft)

        logger.info(f"Found {len(all_nfts)} Tezos NFTs across {len(addresses)} address(es)")
        return all_nfts

    async def _get_nfts_for_address(self, address: str) -> Optional[list]:
        """
        Fetch NFTs for a single Tezos address using the TzKT token balances API
        filtered to FA2 tokens with decimals=0.

        Args:
            address: Tezos address

        Returns:
            List of NFT dicts, or None on error.
        """
        try:
            client = get_client("tzkt", timeout=30.0)
            nfts = []
            offset = 0
            limit = 100

            while True:
                response = await client.get(
                    f"{self.base_url}/tokens/balances",
                    params={
                        'account': address,
                        'token.standard': 'fa2',
                        'token.metadata.decimals': '0',
                        'balance.gt': '0',
                        'limit': limit,
                        'offset': offset,
                        'sort.desc': 'id'
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    logger.error(f"TzKT NFT fetch error: {response.status_code}")
                    return nfts if nfts else None

                batch = response.json()
                if not batch:
                    break

                for item in batch:
                    token_info = item.get('token', {})
                    metadata = token_info.get('metadata') or {}
                    contract_info = token_info.get('contract', {})
                    contract_address = contract_info.get('address', '')
                    token_id = token_info.get('tokenId', '0')

                    # Build unique asset ID
                    asset_id = f"{contract_address}:{token_id}"

                    # Extract image URI (IPFS or HTTP)
                    image_uri = (
                        metadata.get('displayUri')
                        or metadata.get('artifactUri')
                        or metadata.get('thumbnailUri')
                        or ''
                    )

                    # Convert ipfs:// URIs to gateway URL
                    if image_uri.startswith('ipfs://'):
                        ipfs_hash = image_uri.replace('ipfs://', '')
                        image_uri = f"https://ipfs.io/ipfs/{ipfs_hash}"

                    nfts.append({
                        'asset_id': asset_id,
                        'contract_address': contract_address,
                        'token_id': token_id,
                        'name': metadata.get('name', f'Tezos NFT #{token_id}'),
                        'description': metadata.get('description', ''),
                        'image_url': image_uri,
                        'collection_name': contract_info.get('alias', contract_address[:12] + '...'),
                        'standard': 'fa2',
                        'wallet_address': address,
                        'blockchain': 'tezos',
                        'source': 'tzkt',
                        'balance': int(item.get('balance', '1')),
                        'metadata': {
                            'creators': metadata.get('creators', []),
                            'tags': metadata.get('tags', []),
                            'formats': metadata.get('formats', []),
                            'royalties': metadata.get('royalties', {}),
                        }
                    })

                if len(batch) < limit:
                    break
                offset += limit

            return nfts

        except httpx.TimeoutException:
            logger.error(f"TzKT NFT timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Error fetching Tezos NFTs for {address}: {e}")
            return None


# Singleton instance
tezos_service = TezosService()
