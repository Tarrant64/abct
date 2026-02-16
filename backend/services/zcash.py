import httpx
import re
from typing import Optional
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Blockchair ZCash API base URL (free, no key required)
BLOCKCHAIR_ZEC_BASE_URL = "https://api.blockchair.com/zcash"

# Valid ZCash transparent address prefixes:
#   t1 - Transparent P2PKH addresses (35 chars total)
#   t3 - Transparent P2SH addresses (35 chars total)
# Shielded addresses (z-prefixed) cannot be queried via public APIs.
_ZEC_TRANSPARENT_REGEX = re.compile(r'^t[13][a-km-zA-HJ-NP-Z1-9]{33}$')


class ZCashService:
    """
    Service for fetching ZCash wallet data using Blockchair API.
    Only transparent (t-) addresses are supported. Shielded (z-) addresses
    cannot be queried via public block explorers.
    """

    def __init__(self):
        self.base_url = BLOCKCHAIR_ZEC_BASE_URL

    def validate_address(self, address: str) -> bool:
        """
        Validate a ZCash transparent address format.
        Only t1 (P2PKH) and t3 (P2SH) addresses are supported.
        Shielded z-addresses are explicitly rejected.
        """
        if not address or not isinstance(address, str):
            return False

        # Reject shielded addresses with a clear message
        if address.startswith('z'):
            logger.warning(f"Shielded ZCash address not supported: {address[:20]}...")
            return False

        return bool(_ZEC_TRANSPARENT_REGEX.match(address))

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including ZEC balance.
        Uses Blockchair's free API (no authentication required).

        Only transparent (t1/t3) addresses are supported.
        Shielded (z-) addresses cannot be queried.

        Args:
            address: ZCash transparent address (t1 or t3 prefix)

        Returns:
            Dict with balance data or None on failure.
        """
        if not self.validate_address(address):
            logger.error(f"Invalid ZCash transparent address format: {address[:20]}...")
            return None

        try:
            client = get_client("blockchair_zec", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/dashboards/address/{address}",
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid ZCash address: {address}")
                return None

            if response.status_code == 429:
                logger.warning("Blockchair ZEC rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"Blockchair ZEC error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Blockchair response structure:
            # {data: {<address>: {address: {balance: <satoshis>, ...}, transactions: [...]}}}
            address_data = data.get('data', {}).get(address, {})
            address_info = address_data.get('address', {})

            if not address_info:
                logger.error(f"No data returned for ZCash address: {address[:20]}...")
                return None

            # Balance is in satoshis (zatoshis: 1 ZEC = 100,000,000 zatoshis)
            balance_satoshis = address_info.get('balance', 0)

            # Convert to ZEC
            balance_zec = balance_satoshis / 100_000_000

            return {
                'address': address,
                'balance_zec': f"{balance_zec:.8f}",
                'balance_satoshis': str(balance_satoshis),
                'tx_count': address_info.get('transaction_count', 0),
                'source': 'blockchair'
            }

        except httpx.TimeoutException:
            logger.error(f"Blockchair ZEC timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Blockchair ZEC error: {e}")
            return None


# Singleton instance
zcash_service = ZCashService()
