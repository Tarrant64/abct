import httpx
import re
from typing import Optional
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

# BlockCypher Litecoin API base URL (free, no key required)
BLOCKCYPHER_LTC_BASE_URL = "https://api.blockcypher.com/v1/ltc/main"

# Valid Litecoin address prefixes:
#   L or M - Legacy P2PKH
#   3     - P2SH (shared prefix with Bitcoin, but context-dependent)
#   ltc1  - Native SegWit (Bech32)
_LTC_ADDRESS_REGEX = re.compile(r'^(L[a-km-zA-HJ-NP-Z1-9]{26,33}|M[a-km-zA-HJ-NP-Z1-9]{26,33}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|ltc1[a-zA-HJ-NP-Z0-9]{25,90})$')


class LitecoinService:
    """Service for fetching Litecoin wallet data using BlockCypher API."""

    def __init__(self):
        self.base_url = BLOCKCYPHER_LTC_BASE_URL

    def validate_address(self, address: str) -> bool:
        """
        Validate a Litecoin address format.
        Accepts L/M prefixed legacy, 3-prefixed P2SH, and ltc1 Bech32 addresses.
        """
        if not address or not isinstance(address, str):
            return False
        return bool(_LTC_ADDRESS_REGEX.match(address))

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including LTC balance.
        Uses BlockCypher's free API (no authentication required).

        Args:
            address: Litecoin address (L/M/3/ltc1 prefix)

        Returns:
            Dict with balance data or None on failure.
        """
        if not self.validate_address(address):
            logger.error(f"Invalid Litecoin address format: {address[:20]}...")
            return None

        try:
            client = get_client("blockcypher_ltc", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/addrs/{address}/balance",
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid Litecoin address: {address}")
                return None

            if response.status_code == 429:
                logger.warning("BlockCypher LTC rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"BlockCypher LTC error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # BlockCypher returns balance in satoshis (litoshis)
            # final_balance = confirmed balance (balance - unconfirmed)
            balance_satoshis = data.get('final_balance', 0)
            unconfirmed_satoshis = data.get('unconfirmed_balance', 0)

            # Convert to LTC (1 LTC = 100,000,000 litoshis)
            balance_ltc = balance_satoshis / 100_000_000

            return {
                'address': address,
                'balance_ltc': f"{balance_ltc:.8f}",
                'balance_satoshis': str(balance_satoshis),
                'unconfirmed_satoshis': str(unconfirmed_satoshis),
                'tx_count': data.get('n_tx', 0),
                'source': 'blockcypher'
            }

        except httpx.TimeoutException:
            logger.error(f"BlockCypher LTC timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"BlockCypher LTC error: {e}")
            return None


# Singleton instance
litecoin_service = LitecoinService()
