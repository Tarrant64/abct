import httpx
from typing import Optional, List
import logging

import sys
import os
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL, CEXPLORER_API_KEY, CEXPLORER_BASE_URL
from database import get_token_metadata, save_token_metadata

# Import API tracker
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'middleware'))
from api_tracker import get_blockfrost_client, get_cexplorer_client

logger = logging.getLogger(__name__)

class CardanoService:
    """Service for fetching Cardano wallet data with Blockfrost primary and cexplorer fallback."""

    def __init__(self):
        self.blockfrost_headers = {
            "project_id": BLOCKFROST_API_KEY
        }
        self.cexplorer_headers = {
            "api-key": CEXPLORER_API_KEY
        }

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including ADA balance and native assets.
        Tries Blockfrost first, falls back to cexplorer.io on failure.
        """
        # Try Blockfrost first
        result = await self._get_address_blockfrost(address)
        if result is not None:
            return result

        # Fallback to cexplorer
        logger.info(f"Blockfrost failed for {address[:20]}..., trying cexplorer")
        return await self._get_address_cexplorer(address)

    async def _get_address_blockfrost(self, address: str) -> Optional[dict]:
        """Fetch address data from Blockfrost API."""
        try:
            async with get_blockfrost_client(headers=self.blockfrost_headers, timeout=30.0) as client:
                # Get address info
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/addresses/{address}",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )

                if response.status_code == 404:
                    # Address exists but has no transactions
                    return {
                        'address': address,
                        'balance_lovelace': '0',
                        'balance_ada': '0',
                        'native_assets': [],
                        'source': 'blockfrost'
                    }

                if response.status_code != 200:
                    logger.error(f"Blockfrost error: {response.status_code} - {response.text}")
                    return None

                data = response.json()

                # Parse balance (in lovelace)
                balance_lovelace = '0'
                native_assets = []

                for amount in data.get('amount', []):
                    if amount['unit'] == 'lovelace':
                        balance_lovelace = amount['quantity']
                    else:
                        # Native asset
                        asset_id = amount['unit']
                        policy_id = asset_id[:56]
                        asset_name_hex = asset_id[56:]

                        # Try to decode asset name from hex
                        try:
                            asset_name = bytes.fromhex(asset_name_hex).decode('utf-8')
                        except:
                            asset_name = asset_name_hex

                        native_assets.append({
                            'asset_id': asset_id,
                            'policy_id': policy_id,
                            'asset_name': asset_name,
                            'quantity': amount['quantity'],
                            'decimals': 0  # Will be enriched below
                        })

                # Enrich native assets with metadata (decimals, ticker, etc.)
                native_assets = await self._enrich_native_assets(native_assets)

                # Convert lovelace to ADA (1 ADA = 1,000,000 lovelace)
                balance_ada = str(int(balance_lovelace) / 1_000_000)

                return {
                    'address': address,
                    'balance_lovelace': balance_lovelace,
                    'balance_ada': balance_ada,
                    'native_assets': native_assets,
                    'source': 'blockfrost'
                }

        except httpx.TimeoutException:
            logger.error(f"Blockfrost timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Blockfrost error: {e}")
            return None

    async def _get_address_cexplorer(self, address: str) -> Optional[dict]:
        """Fetch address data from cexplorer.io API as fallback."""
        try:
            async with httpx.AsyncClient() as client:
                # cexplorer API endpoint for address info
                response = await client.get(
                    f"{CEXPLORER_BASE_URL}/address/{address}/balance",
                    headers=self.cexplorer_headers,
                    timeout=30.0
                )

                if response.status_code == 404:
                    return {
                        'address': address,
                        'balance_lovelace': '0',
                        'balance_ada': '0',
                        'native_assets': [],
                        'source': 'cexplorer'
                    }

                if response.status_code != 200:
                    logger.error(f"cexplorer error: {response.status_code} - {response.text}")
                    return None

                data = response.json()

                # cexplorer returns balance in lovelace
                balance_lovelace = str(data.get('balance', 0))
                balance_ada = str(int(balance_lovelace) / 1_000_000)

                # Get native assets separately
                native_assets = await self._get_assets_cexplorer(client, address)

                return {
                    'address': address,
                    'balance_lovelace': balance_lovelace,
                    'balance_ada': balance_ada,
                    'native_assets': native_assets,
                    'source': 'cexplorer'
                }

        except httpx.TimeoutException:
            logger.error(f"cexplorer timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"cexplorer error: {e}")
            return None

    async def _get_assets_cexplorer(self, client: httpx.AsyncClient, address: str) -> list:
        """Fetch native assets from cexplorer.io."""
        try:
            response = await client.get(
                f"{CEXPLORER_BASE_URL}/address/{address}/asset",
                headers=self.cexplorer_headers,
                timeout=30.0
            )

            if response.status_code != 200:
                return []

            data = response.json()
            native_assets = []

            for asset in data.get('data', []):
                native_assets.append({
                    'asset_id': asset.get('unit', ''),
                    'policy_id': asset.get('policy_id', ''),
                    'asset_name': asset.get('asset_name', ''),
                    'quantity': str(asset.get('quantity', 0)),
                    'decimals': asset.get('decimals', 0)
                })

            return native_assets

        except Exception as e:
            logger.error(f"cexplorer assets error: {e}")
            return []

    async def get_stake_address(self, address: str) -> Optional[str]:
        """Get the stake address associated with a payment address."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/addresses/{address}",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('stake_address')
                return None

        except Exception as e:
            logger.error(f"Error getting stake address: {e}")
            return None

    async def get_asset_metadata(self, asset_id: str) -> Optional[dict]:
        """Get metadata for a native asset."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/assets/{asset_id}",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        'asset_id': asset_id,
                        'policy_id': data.get('policy_id'),
                        'asset_name': data.get('asset_name'),
                        'fingerprint': data.get('fingerprint'),
                        'quantity': data.get('quantity'),
                        'metadata': data.get('onchain_metadata') or data.get('metadata')
                    }
                return None

        except Exception as e:
            logger.error(f"Error getting asset metadata: {e}")
            return None

    async def _enrich_native_assets(self, native_assets: List[dict]) -> List[dict]:
        """
        Enrich native assets with metadata (decimals, ticker, name).
        Uses cached metadata when available, fetches from API otherwise.
        """
        if not native_assets:
            return native_assets

        enriched = []
        for asset in native_assets:
            asset_id = asset.get('asset_id')
            if not asset_id:
                enriched.append(asset)
                continue

            # Check cache first
            cached = await get_token_metadata(asset_id)
            if cached:
                asset['decimals'] = cached.get('decimals', 0)
                asset['ticker'] = cached.get('ticker')
                asset['token_name'] = cached.get('name')
                enriched.append(asset)
                continue

            # Fetch from API if not cached
            try:
                metadata = await self.get_asset_metadata(asset_id)
                if metadata and metadata.get('metadata'):
                    meta = metadata['metadata']
                    decimals = meta.get('decimals', 0)
                    ticker = meta.get('ticker')
                    name = meta.get('name')

                    # Handle decimals that might be string or int
                    if isinstance(decimals, str):
                        try:
                            decimals = int(decimals)
                        except:
                            decimals = 0

                    asset['decimals'] = decimals
                    asset['ticker'] = ticker
                    asset['token_name'] = name

                    # Cache for future use
                    await save_token_metadata({
                        'asset_id': asset_id,
                        'policy_id': asset.get('policy_id'),
                        'asset_name': asset.get('asset_name'),
                        'ticker': ticker,
                        'name': name,
                        'decimals': decimals
                    })
            except Exception as e:
                logger.warning(f"Could not enrich asset {asset_id[:20]}...: {e}")

            enriched.append(asset)

        return enriched

    async def get_stake_account_info(self, stake_address: str) -> Optional[dict]:
        """
        Get account info for a stake address including rewards and pool delegation.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/accounts/{stake_address}",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )

                if response.status_code == 404:
                    return {
                        'stake_address': stake_address,
                        'active': False,
                        'controlled_amount': '0',
                        'rewards_sum': '0',
                        'withdrawable_amount': '0',
                        'pool_id': None
                    }

                if response.status_code != 200:
                    logger.error(f"Blockfrost account error: {response.status_code} - {response.text}")
                    return None

                data = response.json()
                return {
                    'stake_address': stake_address,
                    'active': data.get('active', False),
                    'controlled_amount': data.get('controlled_amount', '0'),
                    'controlled_ada': str(int(data.get('controlled_amount', 0)) / 1_000_000),
                    'rewards_sum': data.get('rewards_sum', '0'),
                    'rewards_ada': str(int(data.get('rewards_sum', 0)) / 1_000_000),
                    'withdrawable_amount': data.get('withdrawable_amount', '0'),
                    'withdrawable_ada': str(int(data.get('withdrawable_amount', 0)) / 1_000_000),
                    'pool_id': data.get('pool_id')
                }

        except Exception as e:
            logger.error(f"Error getting stake account info: {e}")
            return None

    async def get_addresses_from_stake(self, stake_address: str) -> Optional[list]:
        """
        Get all payment addresses associated with a stake address.
        Returns list of payment addresses that share this stake key.
        """
        try:
            addresses = []
            page = 1

            async with httpx.AsyncClient() as client:
                while True:
                    response = await client.get(
                        f"{BLOCKFROST_BASE_URL}/accounts/{stake_address}/addresses",
                        headers=self.blockfrost_headers,
                        params={'page': page, 'count': 100},
                        timeout=30.0
                    )

                    if response.status_code == 404:
                        return []

                    if response.status_code != 200:
                        logger.error(f"Blockfrost addresses error: {response.status_code}")
                        return None

                    data = response.json()
                    if not data:
                        break

                    for addr_info in data:
                        addresses.append(addr_info.get('address'))

                    # If we got fewer than 100, we've reached the end
                    if len(data) < 100:
                        break

                    page += 1

            return addresses

        except Exception as e:
            logger.error(f"Error getting addresses from stake: {e}")
            return None

    async def get_stake_address_totals(self, stake_address: str) -> Optional[dict]:
        """
        Get aggregated totals for a stake address including all associated wallets.
        """
        # Get account info
        account_info = await self.get_stake_account_info(stake_address)
        if not account_info:
            return None

        # Get associated addresses
        addresses = await self.get_addresses_from_stake(stake_address)
        if addresses is None:
            addresses = []

        # Fetch balances for each address
        total_lovelace = 0
        all_native_assets = []
        address_details = []

        for addr in addresses:
            addr_info = await self.get_address_info(addr)
            if addr_info:
                total_lovelace += int(addr_info.get('balance_lovelace', 0))
                all_native_assets.extend(addr_info.get('native_assets', []))
                address_details.append({
                    'address': addr,
                    'balance_ada': addr_info.get('balance_ada', '0'),
                    'native_assets_count': len(addr_info.get('native_assets', []))
                })

        # Aggregate native assets by asset_id
        asset_totals = {}
        for asset in all_native_assets:
            asset_id = asset['asset_id']
            if asset_id not in asset_totals:
                asset_totals[asset_id] = {
                    'asset_id': asset_id,
                    'policy_id': asset['policy_id'],
                    'asset_name': asset['asset_name'],
                    'quantity': 0,
                    'decimals': asset.get('decimals', 0)
                }
            asset_totals[asset_id]['quantity'] += int(asset['quantity'])

        return {
            'stake_address': stake_address,
            'account_info': account_info,
            'total_ada': str(total_lovelace / 1_000_000),
            'total_with_rewards_ada': str((total_lovelace + int(account_info.get('withdrawable_amount', 0))) / 1_000_000),
            'address_count': len(addresses),
            'addresses': address_details,
            'native_assets': list(asset_totals.values()),
            'native_assets_count': len(asset_totals)
        }


    async def get_pool_metadata(self, pool_id: str) -> Optional[dict]:
        """Get staking pool metadata (name, ticker, etc.)."""
        if not pool_id:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/pools/{pool_id}/metadata",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        'pool_id': pool_id,
                        'name': data.get('name', 'Unknown Pool'),
                        'ticker': data.get('ticker', ''),
                        'description': data.get('description', ''),
                        'homepage': data.get('homepage', '')
                    }
                elif response.status_code == 404:
                    return {
                        'pool_id': pool_id,
                        'name': 'Unknown Pool',
                        'ticker': pool_id[:8] + '...'
                    }
                return None

        except Exception as e:
            logger.error(f"Error getting pool metadata: {e}")
            return None

    async def get_drep_delegation(self, stake_address: str) -> Optional[dict]:
        """Get DRep (Delegated Representative) delegation for a stake address."""
        try:
            async with httpx.AsyncClient() as client:
                # Blockfrost Conway governance endpoint
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/accounts/{stake_address}",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )

                if response.status_code != 200:
                    return None

                data = response.json()
                drep_id = data.get('drep_id')

                if not drep_id:
                    return {
                        'delegated': False,
                        'drep_id': None,
                        'drep_name': None
                    }

                # Try to get DRep metadata
                drep_info = await self._get_drep_info(client, drep_id)

                return {
                    'delegated': True,
                    'drep_id': drep_id,
                    'drep_name': drep_info.get('name') if drep_info else None,
                    'drep_type': self._classify_drep(drep_id)
                }

        except Exception as e:
            logger.error(f"Error getting DRep delegation: {e}")
            return None

    async def _get_drep_info(self, client: httpx.AsyncClient, drep_id: str) -> Optional[dict]:
        """Get DRep metadata from multiple sources: Blockfrost, Koios, and registered metadata."""
        drep_name = None
        drep_bio = ''

        # 1. First try Blockfrost DRep metadata endpoint
        try:
            response = await client.get(
                f"{BLOCKFROST_BASE_URL}/governance/dreps/{drep_id}/metadata",
                headers=self.blockfrost_headers,
                timeout=30.0
            )
            logger.info(f"Blockfrost DRep metadata response for {drep_id}: status={response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Blockfrost DRep metadata for {drep_id}: {data}")
                # Try various field names that might contain the name
                drep_name = data.get('givenName') or data.get('name') or data.get('displayName')
                drep_bio = data.get('bio', data.get('motivations', ''))

                # If no name found but there's a URL, fetch the metadata from the URL
                if not drep_name and data.get('url'):
                    meta_url = data['url']
                    logger.info(f"Fetching DRep metadata from URL: {meta_url}")
                    try:
                        meta_response = await client.get(meta_url, timeout=30.0)
                        if meta_response.status_code == 200:
                            meta_data = meta_response.json()
                            logger.info(f"DRep metadata from URL: {meta_data}")
                            # CIP-100/CIP-119 format uses 'body' containing the metadata
                            body = meta_data.get('body', meta_data)
                            drep_name = (body.get('givenName') or body.get('name') or
                                        body.get('displayName') or meta_data.get('givenName') or
                                        meta_data.get('name'))
                            drep_bio = body.get('bio', body.get('motivations', ''))
                    except Exception as e:
                        logger.info(f"Failed to fetch DRep metadata from URL {meta_url}: {e}")
        except Exception as e:
            logger.info(f"Blockfrost DRep metadata fetch failed: {e}")

        # 2. Try Koios API for DRep metadata (uses POST with body)
        if not drep_name:
            try:
                response = await client.post(
                    "https://api.koios.rest/api/v1/drep_metadata",
                    json={"_drep_ids": [drep_id]},
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                logger.info(f"Koios DRep metadata response: status={response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Koios DRep metadata for {drep_id}: {data}")
                    if data and isinstance(data, list) and len(data) > 0:
                        drep_data = data[0]
                        # Koios returns meta_json which contains the actual metadata
                        meta_json = drep_data.get('meta_json', {}) or {}
                        drep_name = (meta_json.get('givenName') or meta_json.get('name') or
                                    drep_data.get('givenName') or drep_data.get('name'))
                        drep_bio = meta_json.get('bio', meta_json.get('motivations', ''))
            except Exception as e:
                logger.info(f"Koios DRep metadata fetch failed: {e}")

        # 3. Try Blockfrost DRep general info (might have different fields)
        if not drep_name:
            try:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/governance/dreps/{drep_id}",
                    headers=self.blockfrost_headers,
                    timeout=30.0
                )
                logger.info(f"Blockfrost DRep info response: status={response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Blockfrost DRep info for {drep_id}: {data}")
                    # Check if there's a metadata URL we can fetch
                    meta_url = data.get('url')
                    if meta_url:
                        try:
                            meta_response = await client.get(meta_url, timeout=30.0)
                            if meta_response.status_code == 200:
                                meta_data = meta_response.json()
                                logger.info(f"DRep metadata from URL: {meta_data}")
                                drep_name = (meta_data.get('givenName') or meta_data.get('name') or
                                            meta_data.get('displayName'))
                                drep_bio = meta_data.get('bio', meta_data.get('motivations', ''))
                        except Exception as e:
                            logger.info(f"Failed to fetch DRep metadata from URL: {e}")
            except Exception as e:
                logger.info(f"Blockfrost DRep info fetch failed: {e}")

        if drep_name:
            return {
                'drep_id': drep_id,
                'name': drep_name,
                'bio': drep_bio
            }
        return None

    def _classify_drep(self, drep_id: str) -> str:
        """Classify the type of DRep delegation."""
        if drep_id == 'drep_always_abstain':
            return 'Always Abstain'
        elif drep_id == 'drep_always_no_confidence':
            return 'Always No Confidence'
        elif drep_id.startswith('drep1'):
            return 'DRep'
        else:
            return 'Unknown'

    async def get_wallet_governance_info(self, address: str) -> Optional[dict]:
        """Get complete governance and staking info for a wallet address."""
        # First get the stake address
        stake_address = await self.get_stake_address(address)
        if not stake_address:
            return {
                'has_stake_key': False,
                'stake_address': None,
                'pool': None,
                'drep': None,
                'rewards': None
            }

        # Get account info (includes pool_id and rewards)
        account_info = await self.get_stake_account_info(stake_address)

        # Get pool metadata if delegated
        pool_info = None
        if account_info and account_info.get('pool_id'):
            pool_info = await self.get_pool_metadata(account_info['pool_id'])

        # Get DRep delegation
        drep_info = await self.get_drep_delegation(stake_address)

        return {
            'has_stake_key': True,
            'stake_address': stake_address,
            'pool': pool_info,
            'drep': drep_info,
            'rewards': {
                'total_earned': account_info.get('rewards_ada', '0') if account_info else '0',
                'withdrawable': account_info.get('withdrawable_ada', '0') if account_info else '0',
                'withdrawable_lovelace': account_info.get('withdrawable_amount', '0') if account_info else '0'
            } if account_info else None
        }


def is_stake_address(address: str) -> bool:
    """Check if an address is a stake address."""
    return address.startswith('stake1')


# Singleton instance
cardano_service = CardanoService()
