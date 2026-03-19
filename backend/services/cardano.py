import httpx
from typing import Optional, List
import logging

import sys
import os
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from config import BLOCKFROST_BASE_URL, CEXPLORER_BASE_URL
from database import get_token_metadata, save_token_metadata, get_api_key

# Import API tracker
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'middleware'))
from api_tracker import get_blockfrost_client, get_cexplorer_client
from services.http_client import get_client, blockfrost_fetch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local bech32 stake-key derivation (no external dependencies)
# ---------------------------------------------------------------------------
# Cardano addr1q (type 0, base address) encodes:
#   header (1 byte) | payment_credential (28 bytes) | stake_credential (28 bytes)
# A stake/reward address (stake1...) is:
#   header (1 byte, 0xe1 for mainnet) | stake_credential (28 bytes)
# We can extract the stake credential from any valid addr1q address
# without hitting any API.

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_CHARSET_REV = {c: i for i, c in enumerate(_BECH32_CHARSET)}
_BECH32_GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]


def _bech32_polymod(values):
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            chk ^= _BECH32_GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_verify_checksum(hrp, data):
    return _bech32_polymod(_bech32_hrp_expand(hrp) + data) == 1


def _bech32_decode(bech_str: str, verify: bool = True):
    """Decode a bech32 string. Returns (hrp, 5-bit data) or (None, None).

    Args:
        bech_str: The bech32-encoded string
        verify: If True, verify checksum (strict mode). If False, skip
                checksum verification (best-effort for mangled addresses).
    """
    if bech_str.lower() != bech_str and bech_str.upper() != bech_str:
        return None, None
    bech_str = bech_str.lower()
    pos = bech_str.rfind('1')
    if pos < 1 or pos + 7 > len(bech_str):
        return None, None
    hrp = bech_str[:pos]
    data_part = bech_str[pos + 1:]
    if any(c not in _BECH32_CHARSET for c in data_part):
        return None, None
    data = [_BECH32_CHARSET_REV[c] for c in data_part]
    if verify and not _bech32_verify_checksum(hrp, data):
        return None, None
    return hrp, data[:-6]  # strip checksum


def _bech32_create_checksum(hrp, data):
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _bech32_encode(hrp, data):
    combined = data + _bech32_create_checksum(hrp, data)
    return hrp + '1' + ''.join(_BECH32_CHARSET[d] for d in combined)


def _convert_bits(data, frombits, tobits, pad=True):
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def _derive_stake_key_local(address: str) -> Optional[str]:
    """Derive the stake key (stake1...) from a Cardano base address (addr1q...).

    Returns None if the address is not a valid base address or can't be decoded.
    """
    hrp, data5 = _bech32_decode(address)
    if hrp is None or data5 is None:
        # Retry without checksum verification (best-effort for mangled addresses)
        hrp, data5 = _bech32_decode(address, verify=False)
        if hrp is None or data5 is None:
            return None

    # Only mainnet base addresses (addr) supported
    if hrp != 'addr':
        return None

    # Convert from 5-bit to 8-bit
    data8 = _convert_bits(data5, 5, 8, pad=False)
    if data8 is None or len(data8) < 57:
        # Base address = 1 header + 28 payment + 28 stake = 57 bytes
        return None

    header = data8[0]
    addr_type = (header >> 4) & 0x0f
    network = header & 0x0f

    # Type 0 = base address (payment key hash + stake key hash)
    # Type 2 = base address (payment script hash + stake key hash)
    # Type 3 = base address (payment script hash + stake script hash)
    # Only types 0-3 contain a stake credential
    if addr_type > 3:
        return None  # Enterprise, pointer, or other address — no stake key

    # Extract stake credential (last 28 bytes)
    stake_credential = data8[29:57]
    if len(stake_credential) != 28:
        return None

    # Build reward (stake) address header:
    # type 14 (0xe) for key hash stake cred, type 15 (0xf) for script stake cred
    # Types 0,2 have key-hash stake cred; types 1,3 have script-hash stake cred
    if addr_type in (0, 2):
        reward_header = (0x0e << 4) | network  # 0xe0 | network = 0xe1 for mainnet
    else:
        reward_header = (0x0f << 4) | network  # 0xf0 | network = 0xf1 for mainnet

    reward_bytes = [reward_header] + stake_credential

    # Convert back to 5-bit and bech32 encode with "stake" hrp
    reward_data5 = _convert_bits(reward_bytes, 8, 5)
    if reward_data5 is None:
        return None

    return _bech32_encode('stake', reward_data5)


ADA_HANDLE_POLICY_ID = 'f0ff48bbb7bbe9d59a40f1ce90e9e9d0ff5002ec48f232b49ca0fb9a'


def detect_ada_handle(native_assets: List[dict]) -> Optional[str]:
    """Detect an ADA Handle from a list of native assets.

    ADA Handles are NFTs under the well-known policy ID. The hex-decoded
    asset_name is the handle text (without the '$' prefix).

    Returns the handle as '$name' or None if no handle found.
    """
    for asset in native_assets:
        policy_id = asset.get('policy_id', '')
        if policy_id == ADA_HANDLE_POLICY_ID:
            asset_name = asset.get('asset_name', '')
            # asset_name is already decoded from hex in _get_address_blockfrost
            if asset_name:
                return f'${asset_name}'
    return None


class CardanoService:
    """Service for fetching Cardano wallet data with Blockfrost primary and cexplorer fallback."""

    def __init__(self):
        # API keys are now loaded dynamically from database or environment
        self._blockfrost_key_cache = None
        self._blockfrost_cache_time = None
        self._cexplorer_key_cache = None
        self._cexplorer_cache_time = None
        self._cache_ttl_seconds = 60  # 1 minute cache

    async def _get_blockfrost_key(self) -> str:
        """Get Blockfrost API key from database or environment."""
        from datetime import datetime, timedelta
        now = datetime.utcnow()

        # Check cache
        if self._blockfrost_key_cache and self._blockfrost_cache_time:
            if now - self._blockfrost_cache_time < timedelta(seconds=self._cache_ttl_seconds):
                return self._blockfrost_key_cache

        # Try database
        try:
            db_key = await get_api_key('blockfrost', user_id=1)
            if db_key:
                self._blockfrost_key_cache = db_key
                self._blockfrost_cache_time = now
                return db_key
        except Exception:
            pass

        # Fall back to environment
        import os
        env_key = os.getenv('BLOCKFROST_API_KEY', '')
        self._blockfrost_key_cache = env_key
        self._blockfrost_cache_time = now
        return env_key

    async def _get_cexplorer_key(self) -> str:
        """Get CExplorer API key from database or environment."""
        from datetime import datetime, timedelta
        now = datetime.utcnow()

        # Check cache
        if self._cexplorer_key_cache and self._cexplorer_cache_time:
            if now - self._cexplorer_cache_time < timedelta(seconds=self._cache_ttl_seconds):
                return self._cexplorer_key_cache

        # Try database
        try:
            db_key = await get_api_key('cexplorer', user_id=1)
            if db_key:
                self._cexplorer_key_cache = db_key
                self._cexplorer_cache_time = now
                return db_key
        except Exception:
            pass

        # Fall back to environment
        import os
        env_key = os.getenv('CEXPLORER_API_KEY', '')
        self._cexplorer_key_cache = env_key
        self._cexplorer_cache_time = now
        return env_key

    async def _get_blockfrost_headers(self) -> dict:
        """Get Blockfrost request headers."""
        key = await self._get_blockfrost_key()
        return {"project_id": key} if key else {}

    async def _get_cexplorer_headers(self) -> dict:
        """Get CExplorer request headers."""
        key = await self._get_cexplorer_key()
        return {"api-key": key} if key else {}

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

    async def resolve_ada_handle(self, handle: str) -> Optional[str]:
        """Resolve an ADA Handle (e.g., '$chriscata') to a Cardano address.

        Uses the Blockfrost API to look up the handle NFT and find the
        address that holds it.

        Args:
            handle: The handle with or without '$' prefix

        Returns:
            The Cardano address holding the handle, or None if not found.
        """
        # Strip '$' prefix if present
        handle_name = handle.lstrip('$')
        if not handle_name:
            return None

        # Encode handle name to hex for asset lookup
        handle_hex = handle_name.encode('utf-8').hex()
        asset_id = f"{ADA_HANDLE_POLICY_ID}{handle_hex}"

        try:
            response = await blockfrost_fetch(
                f"/assets/{asset_id}/addresses",
                headers=await self._get_blockfrost_headers(),
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    # The first address holding the handle NFT is the owner
                    return data[0].get('address')

            logger.info(f"ADA Handle '{handle_name}' not found (status {response.status_code})")
            return None

        except Exception as e:
            logger.error(f"Error resolving ADA Handle '{handle_name}': {e}")
            return None

    async def _get_address_blockfrost(self, address: str) -> Optional[dict]:
        """Fetch address data from Blockfrost API."""
        try:
            async with get_blockfrost_client(headers=await self._get_blockfrost_headers(), timeout=30.0) as client:
                # Get address info
                response = await blockfrost_fetch(
                    f"/addresses/{address}",
                    headers=await self._get_blockfrost_headers(),
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
                        except Exception:
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
            client = get_client("blockfrost", timeout=30.0)
            # cexplorer API endpoint for address info
            response = await client.get(
                f"{CEXPLORER_BASE_URL}/address/{address}/balance",
                headers=await self._get_cexplorer_headers(),
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
                headers=await self._get_cexplorer_headers(),
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
        """Get the stake address associated with a payment address.

        Tries Blockfrost API first, then falls back to local bech32
        derivation for addr1q base addresses (which encode the stake
        credential directly in the address bytes).
        """
        # Try Blockfrost API first
        try:
            response = await blockfrost_fetch(
                f"/addresses/{address}",
                headers=await self._get_blockfrost_headers(),
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                stake = data.get('stake_address')
                if stake:
                    return stake

        except Exception as e:
            logger.error(f"Error getting stake address from Blockfrost: {e}")

        # Fallback: derive stake key locally from addr1q base addresses
        try:
            return _derive_stake_key_local(address)
        except Exception as e:
            logger.debug(f"Local stake key derivation failed for {address[:20]}...: {e}")
            return None

    async def get_asset_metadata(self, asset_id: str) -> Optional[dict]:
        """Get metadata for a native asset."""
        try:
            response = await blockfrost_fetch(
                f"/assets/{asset_id}",
                headers=await self._get_blockfrost_headers(),
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
                        except Exception:
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
            response = await blockfrost_fetch(
                f"/accounts/{stake_address}",
                headers=await self._get_blockfrost_headers(),
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
                'pool_id': data.get('pool_id'),
                'drep_id': data.get('drep_id'),
                '_raw': data
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

            while True:
                response = await blockfrost_fetch(
                    f"/accounts/{stake_address}/addresses",
                    headers=await self._get_blockfrost_headers(),
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
            response = await blockfrost_fetch(
                f"/pools/{pool_id}/metadata",
                headers=await self._get_blockfrost_headers(),
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

    async def get_drep_delegation(self, stake_address: str, account_data: dict = None) -> Optional[dict]:
        """Get DRep (Delegated Representative) delegation for a stake address.

        Args:
            stake_address: The stake address to query
            account_data: Optional raw Blockfrost account data to reuse (avoids duplicate API call)
        """
        try:
            if account_data:
                data = account_data
            else:
                # Blockfrost Conway governance endpoint
                response = await blockfrost_fetch(
                    f"/accounts/{stake_address}",
                    headers=await self._get_blockfrost_headers(),
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
            client = get_client("blockfrost", timeout=30.0)
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
            response = await blockfrost_fetch(
                f"/governance/dreps/{drep_id}/metadata",
                headers=await self._get_blockfrost_headers(),
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
                response = await blockfrost_fetch(
                    f"/governance/dreps/{drep_id}",
                    headers=await self._get_blockfrost_headers(),
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

        # Get account info (includes pool_id, drep_id, and rewards)
        account_info = await self.get_stake_account_info(stake_address)

        # Get pool metadata if delegated
        pool_info = None
        if account_info and account_info.get('pool_id'):
            pool_info = await self.get_pool_metadata(account_info['pool_id'])

        # Get DRep delegation - reuse raw account data to avoid duplicate Blockfrost call
        drep_info = await self.get_drep_delegation(
            stake_address,
            account_data=account_info.get('_raw') if account_info else None
        )

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
