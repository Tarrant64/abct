import httpx
from typing import Optional, List, Tuple
import logging
import asyncio

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from config import BLOCKSTREAM_BASE_URL
from services.http_client import get_client

logger = logging.getLogger(__name__)

# xpub support requires bip_utils. A broken import here disables extended-public-key
# expansion entirely, which makes a funded xpub wallet report a zero balance rather
# than an error - so the failure reason is kept and surfaced instead of swallowed.
BIP_UTILS_AVAILABLE = False
BIP_UTILS_ERROR: Optional[str] = None
try:
    from bip_utils import (
        Bip44, Bip49, Bip84,
        Bip44Coins, Bip49Coins, Bip84Coins,
        Bip44Changes
    )
    BIP_UTILS_AVAILABLE = True
except Exception as e:
    BIP_UTILS_ERROR = f"{type(e).__name__}: {e}"
    logger.error(
        "bip_utils unusable - Bitcoin xpub/ypub/zpub support is DISABLED (%s). "
        "Extended public keys cannot be expanded to addresses; check the "
        "bip_utils pin in backend/requirements.txt.",
        BIP_UTILS_ERROR
    )


class XpubError(Exception):
    """Raised when an extended public key cannot be expanded to addresses."""


class XpubUnavailableError(XpubError):
    """Raised when bip_utils is missing or incompatible."""


class XpubDerivationError(XpubError):
    """Raised when derivation fails for an otherwise well-formed xpub."""


class BitcoinService:
    """Service for fetching Bitcoin wallet data using Blockstream API."""

    def __init__(self):
        self.base_url = BLOCKSTREAM_BASE_URL

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including BTC balance.
        Uses Blockstream's free API (no authentication required).
        """
        try:
            client = get_client("blockstream", timeout=30.0)
            # Get address info
            response = await client.get(
                f"{self.base_url}/address/{address}",
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid Bitcoin address: {address}")
                return None

            if response.status_code != 200:
                logger.error(f"Blockstream error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Calculate balance from chain_stats and mempool_stats
            chain_stats = data.get('chain_stats', {})
            mempool_stats = data.get('mempool_stats', {})

            # Confirmed balance
            funded_sum = chain_stats.get('funded_txo_sum', 0)
            spent_sum = chain_stats.get('spent_txo_sum', 0)
            confirmed_balance = funded_sum - spent_sum

            # Unconfirmed (mempool) balance
            mempool_funded = mempool_stats.get('funded_txo_sum', 0)
            mempool_spent = mempool_stats.get('spent_txo_sum', 0)
            unconfirmed_balance = mempool_funded - mempool_spent

            # Total balance in satoshis
            total_satoshis = confirmed_balance + unconfirmed_balance

            # Convert to BTC (1 BTC = 100,000,000 satoshis)
            balance_btc = total_satoshis / 100_000_000

            return {
                'address': address,
                'balance_satoshis': str(total_satoshis),
                'balance_btc': f"{balance_btc:.8f}",
                'confirmed_satoshis': str(confirmed_balance),
                'unconfirmed_satoshis': str(unconfirmed_balance),
                'tx_count': chain_stats.get('tx_count', 0),
                'source': 'blockstream'
            }

        except httpx.TimeoutException:
            logger.error(f"Blockstream timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Blockstream error: {e}")
            return None

    async def get_utxos(self, address: str) -> Optional[list]:
        """Get unspent transaction outputs for an address."""
        try:
            client = get_client("blockstream", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/address/{address}/utxo",
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"Blockstream UTXO error: {response.status_code}")
                return None

            utxos = response.json()
            return [{
                'txid': utxo['txid'],
                'vout': utxo['vout'],
                'value': utxo['value'],
                'confirmed': utxo.get('status', {}).get('confirmed', False)
            } for utxo in utxos]

        except Exception as e:
            logger.error(f"Error getting UTXOs: {e}")
            return None

    async def get_transactions(self, address: str, limit: int = 25) -> Optional[list]:
        """Get recent transactions for an address."""
        try:
            client = get_client("blockstream", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/address/{address}/txs",
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"Blockstream txs error: {response.status_code}")
                return None

            txs = response.json()[:limit]
            return [{
                'txid': tx['txid'],
                'confirmed': tx.get('status', {}).get('confirmed', False),
                'block_height': tx.get('status', {}).get('block_height'),
                'fee': tx.get('fee', 0),
                'size': tx.get('size', 0)
            } for tx in txs]

        except Exception as e:
            logger.error(f"Error getting transactions: {e}")
            return None

    def is_xpub(self, key: str) -> bool:
        """Check if a string is an extended public key (xpub/ypub/zpub)."""
        return key.startswith(('xpub', 'ypub', 'zpub', 'tpub', 'upub', 'vpub'))

    def get_xpub_type(self, xpub: str) -> Optional[str]:
        """
        Determine the type of extended public key.

        Returns:
            'legacy' for xpub (BIP44 - addresses start with 1)
            'nested_segwit' for ypub (BIP49 - addresses start with 3)
            'native_segwit' for zpub (BIP84 - addresses start with bc1)
            'testnet_*' for testnet variants
        """
        if xpub.startswith('xpub'):
            return 'legacy'
        elif xpub.startswith('ypub'):
            return 'nested_segwit'
        elif xpub.startswith('zpub'):
            return 'native_segwit'
        elif xpub.startswith('tpub'):
            return 'testnet_legacy'
        elif xpub.startswith('upub'):
            return 'testnet_nested_segwit'
        elif xpub.startswith('vpub'):
            return 'testnet_native_segwit'
        return None

    def derive_addresses_from_xpub(
        self,
        xpub: str,
        account: int = 0,
        start_index: int = 0,
        count: int = 20,
        change: bool = False
    ) -> List[Tuple[str, int]]:
        """
        Derive Bitcoin addresses from an extended public key.

        Args:
            xpub: Extended public key (xpub/ypub/zpub)
            account: Account number (usually 0)
            start_index: Starting address index
            count: Number of addresses to derive
            change: If True, derive change addresses (internal chain)

        Returns:
            List of (address, index) tuples

        Raises:
            XpubUnavailableError: bip_utils is missing or incompatible.
            XpubDerivationError: the key is unsupported or derivation failed.
        """
        if not BIP_UTILS_AVAILABLE:
            raise XpubUnavailableError(self.xpub_unavailable_reason())

        xpub_type = self.get_xpub_type(xpub)
        if not xpub_type:
            raise XpubDerivationError("Unrecognized extended public key format")

        # Bip49/Bip84 subclass Bip44Base, so they share one derivation shape;
        # only the context class and coin enum differ per purpose.
        derivers = {
            'legacy': (Bip44, Bip44Coins.BITCOIN),            # BIP44 - 1...
            'nested_segwit': (Bip49, Bip49Coins.BITCOIN),     # BIP49 - 3...
            'native_segwit': (Bip84, Bip84Coins.BITCOIN),     # BIP84 - bc1...
        }
        if xpub_type not in derivers:
            raise XpubDerivationError(
                f"Testnet extended public keys are not supported ({xpub_type})"
            )

        bip_cls, coin = derivers[xpub_type]
        chain = Bip44Changes.CHAIN_INT if change else Bip44Changes.CHAIN_EXT

        try:
            chain_ctx = bip_cls.FromExtendedKey(xpub, coin).Change(chain)
            return [
                (chain_ctx.AddressIndex(i).PublicKey().ToAddress(), i)
                for i in range(start_index, start_index + count)
            ]
        except Exception as e:
            logger.error(f"Error deriving addresses from xpub: {e}")
            raise XpubDerivationError(f"Address derivation failed: {e}") from e

    async def discover_xpub_addresses(
        self,
        xpub: str,
        gap_limit: int = 20,
        max_addresses: int = 100
    ) -> dict:
        """
        Discover all used addresses from an extended public key.

        Uses a gap limit approach: keeps scanning until finding
        `gap_limit` consecutive unused addresses.

        Args:
            xpub: Extended public key
            gap_limit: Number of consecutive unused addresses before stopping
            max_addresses: Maximum addresses to scan (safety limit)

        Returns:
            Dict with discovered addresses, total balance, and metadata
        """
        if not BIP_UTILS_AVAILABLE:
            return {
                'error': 'xpub_unavailable',
                'message': self.xpub_unavailable_reason()
            }

        xpub_type = self.get_xpub_type(xpub)
        if not xpub_type:
            return {
                'error': 'invalid_xpub',
                'message': 'Unrecognized extended public key format'
            }

        discovered_addresses = []
        total_satoshis = 0
        total_btc = 0.0
        tx_count = 0

        # Scan both receive (external) and change (internal) chains
        for chain_name, is_change in [('receive', False), ('change', True)]:
            consecutive_empty = 0
            index = 0

            while consecutive_empty < gap_limit and index < max_addresses:
                # Derive batch of addresses
                batch_size = min(10, max_addresses - index)
                try:
                    addresses = self.derive_addresses_from_xpub(
                        xpub,
                        start_index=index,
                        count=batch_size,
                        change=is_change
                    )
                except XpubError as e:
                    # Never fall through to a zero-balance "success": a derivation
                    # failure is indistinguishable from an empty wallet downstream.
                    logger.error(f"xpub discovery aborted: {e}")
                    return {
                        'error': 'xpub_derivation_failed',
                        'message': str(e)
                    }

                if not addresses:
                    break

                # Check each address for activity
                for address, addr_index in addresses:
                    info = await self.get_address_info(address)

                    if info:
                        addr_tx_count = info.get('tx_count', 0)
                        addr_satoshis = int(info.get('balance_satoshis', 0))

                        if addr_tx_count > 0 or addr_satoshis > 0:
                            # Address has been used
                            consecutive_empty = 0
                            discovered_addresses.append({
                                'address': address,
                                'index': addr_index,
                                'chain': chain_name,
                                'balance_satoshis': addr_satoshis,
                                'balance_btc': float(info.get('balance_btc', 0)),
                                'tx_count': addr_tx_count
                            })
                            total_satoshis += addr_satoshis
                            tx_count += addr_tx_count
                        else:
                            consecutive_empty += 1
                    else:
                        # API error - count as empty but continue
                        consecutive_empty += 1

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.1)

                index += batch_size

        total_btc = total_satoshis / 100_000_000

        # Determine address type label
        address_type_labels = {
            'legacy': 'Legacy (P2PKH)',
            'nested_segwit': 'Nested SegWit (P2SH-P2WPKH)',
            'native_segwit': 'Native SegWit (P2WPKH)'
        }

        return {
            'xpub': xpub[:20] + '...' + xpub[-8:],
            'xpub_type': xpub_type,
            'address_type': address_type_labels.get(xpub_type, xpub_type),
            'total_addresses': len(discovered_addresses),
            'total_balance_satoshis': total_satoshis,
            'total_balance_btc': f"{total_btc:.8f}",
            'total_tx_count': tx_count,
            'addresses': discovered_addresses,
            'receive_addresses': [a for a in discovered_addresses if a['chain'] == 'receive'],
            'change_addresses': [a for a in discovered_addresses if a['chain'] == 'change'],
            'gap_limit_used': gap_limit,
            'source': 'blockstream'
        }

    def xpub_available(self) -> bool:
        """Check if xpub support is available."""
        return BIP_UTILS_AVAILABLE

    def xpub_unavailable_reason(self) -> Optional[str]:
        """Explain why xpub support is off, or None when it is working."""
        if BIP_UTILS_AVAILABLE:
            return None
        return (
            f"xpub support disabled: bip_utils failed to load ({BIP_UTILS_ERROR}). "
            "Verify the bip_utils pin in backend/requirements.txt."
        )


# Singleton instance
bitcoin_service = BitcoinService()
