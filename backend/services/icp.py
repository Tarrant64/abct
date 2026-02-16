import httpx
from typing import Optional
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

ROSETTA_BASE_URL = "https://rosetta-api.internetcomputer.org"

# ICP network identifier for mainnet
NETWORK_IDENTIFIER = {
    "blockchain": "Internet Computer",
    "network": "00000000000000020101"
}


class ICPService:
    """Service for fetching Internet Computer (ICP) wallet data using the Rosetta API."""

    def __init__(self):
        self.base_url = ROSETTA_BASE_URL

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including ICP balance.
        Uses the ICP Rosetta API (free, no authentication required).

        Args:
            address: ICP account identifier (64 hex chars) or Principal ID.

        Returns:
            Dict with address, balance_icp, blockchain, and source, or None on error.
        """
        try:
            client = get_client("icp_rosetta", timeout=30.0)

            payload = {
                "network_identifier": NETWORK_IDENTIFIER,
                "account_identifier": {
                    "address": address
                }
            }

            response = await client.post(
                f"{self.base_url}/account/balance",
                json=payload,
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid ICP address: {address}")
                return None

            if response.status_code != 200:
                logger.error(f"ICP Rosetta error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Parse balances array for ICP amount
            balances = data.get("balances", [])
            if not balances:
                logger.warning(f"No balances returned for ICP address {address[:20]}...")
                return {
                    "address": address,
                    "balance_icp": "0.00000000",
                    "blockchain": "icp",
                    "source": "rosetta"
                }

            # Find the ICP balance entry (symbol == "ICP", decimals == 8)
            balance_e8s = 0
            for bal in balances:
                currency = bal.get("currency", {})
                if currency.get("symbol") == "ICP" and currency.get("decimals") == 8:
                    balance_e8s = int(bal.get("value", "0"))
                    break
            else:
                # If no explicit ICP entry found, use the first balance
                balance_e8s = int(balances[0].get("value", "0"))

            # Convert from e8s to ICP (1 ICP = 10^8 e8s)
            balance_icp = balance_e8s / 100_000_000

            return {
                "address": address,
                "balance_icp": f"{balance_icp:.8f}",
                "blockchain": "icp",
                "source": "rosetta"
            }

        except httpx.TimeoutException:
            logger.error(f"ICP Rosetta timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"ICP Rosetta error: {e}")
            return None


# Singleton instance
icp_service = ICPService()
