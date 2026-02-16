import httpx
import re
from typing import Optional
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

# BlockCypher Dogecoin API base URL (free, no key required)
BLOCKCYPHER_DOGE_BASE_URL = "https://api.blockcypher.com/v1/doge/main"

# Valid Dogecoin address prefixes:
#   D - Standard P2PKH addresses (most common)
#   A - P2SH multisig addresses
#   9 - P2SH addresses (less common)
_DOGE_ADDRESS_REGEX = re.compile(r'^D[5-9A-HJ-NP-U][a-km-zA-HJ-NP-Z1-9]{32}$')


class DogecoinService:
    """Service for fetching Dogecoin wallet data using BlockCypher API."""

    def __init__(self):
        self.base_url = BLOCKCYPHER_DOGE_BASE_URL

    def validate_address(self, address: str) -> bool:
        """
        Validate a Dogecoin address format.
        Standard Dogecoin addresses start with 'D' and are 34 characters.
        """
        if not address or not isinstance(address, str):
            return False
        return bool(_DOGE_ADDRESS_REGEX.match(address))

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including DOGE balance.
        Uses BlockCypher's free API (no authentication required).

        Args:
            address: Dogecoin address (D prefix)

        Returns:
            Dict with balance data or None on failure.
        """
        if not self.validate_address(address):
            logger.error(f"Invalid Dogecoin address format: {address[:20]}...")
            return None

        try:
            client = get_client("blockcypher_doge", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/addrs/{address}/balance",
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid Dogecoin address: {address}")
                return None

            if response.status_code == 429:
                logger.warning("BlockCypher DOGE rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"BlockCypher DOGE error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # BlockCypher returns balance in satoshis (koinus)
            # final_balance = confirmed balance
            balance_satoshis = data.get('final_balance', 0)
            unconfirmed_satoshis = data.get('unconfirmed_balance', 0)

            # Convert to DOGE (1 DOGE = 100,000,000 koinus/satoshis)
            balance_doge = balance_satoshis / 100_000_000

            return {
                'address': address,
                'balance_doge': f"{balance_doge:.8f}",
                'balance_satoshis': str(balance_satoshis),
                'unconfirmed_satoshis': str(unconfirmed_satoshis),
                'tx_count': data.get('n_tx', 0),
                'source': 'blockcypher'
            }

        except httpx.TimeoutException:
            logger.error(f"BlockCypher DOGE timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"BlockCypher DOGE error: {e}")
            return None


# Singleton instance
dogecoin_service = DogecoinService()
