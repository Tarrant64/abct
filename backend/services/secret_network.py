"""
Secret Network Service - Fetches SCRT wallet balance.

Secret Network (SCRT) uses Bech32 addresses starting with 'secret1'.
Wallet balances are fully public and queryable via the REST API.
Smart contract state is private (encrypted via Intel SGX TEE).

API: Secret Foundation LCD at https://lcd.mainnet.secretsaturn.net
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

SECRET_LCD_URL = "https://lcd.mainnet.secretsaturn.net"
USCRT_DIVISOR = 1_000_000  # 1 SCRT = 1,000,000 uscrt

# Known privacy contract addresses on Secret Network
KNOWN_PRIVACY_CONTRACTS = {
    'secret1k0jntykt7e4g3y88ltc60czgjuqdy4c9e8fzek',  # SecretSwap
    'secret18wpjn83dayu4meu6wnn29khfkwdxs7kyrz9c8f',  # Shade Protocol
}


class SecretNetworkService:
    """
    Service for fetching Secret Network wallet data.

    Secret Network encrypts smart contract state using Intel SGX TEE.
    Wallet (SCRT) balances are public and fully queryable.
    SNIP-20 token balances are private and cannot be fetched.
    """

    def __init__(self):
        self.base_url = SECRET_LCD_URL

    def validate_address(self, address: str) -> bool:
        """
        Validate a Secret Network address.
        Must start with 'secret1' and be 45 characters total.
        """
        if not address or not isinstance(address, str):
            return False
        return address.startswith('secret1') and len(address) == 45

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get SCRT balance for an address via Secret Foundation LCD API.

        Args:
            address: Secret Network address (secret1...)

        Returns:
            Dict with balance data or None on failure.
        """
        if not self.validate_address(address):
            logger.error(f"Invalid Secret Network address format: {address[:20]}...")
            return None

        try:
            client = get_client("secret_network", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/cosmos/bank/v1beta1/balances/{address}"
            )

            if response.status_code == 400:
                logger.error(f"Invalid Secret Network address: {address[:20]}...")
                return None

            if response.status_code == 404:
                # Address not found — return zero balance (new/unfunded address)
                return {
                    'address': address,
                    'balance_scrt': 0.0,
                    'tx_count': 0,
                    'has_private_contract_interactions': False,
                    'blockchain': 'secret_network',
                    'source': 'secret_foundation'
                }

            if response.status_code == 429:
                logger.warning("Secret Network LCD rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"Secret Network LCD error: {response.status_code} - {response.text[:200]}")
                return None

            data = response.json()

            # Response: {"balances": [{"denom": "uscrt", "amount": "1234567"}]}
            balances = data.get('balances', [])
            balance_uscrt = 0
            for entry in balances:
                if entry.get('denom') == 'uscrt':
                    balance_uscrt = int(entry.get('amount', 0))
                    break

            balance_scrt = balance_uscrt / USCRT_DIVISOR

            return {
                'address': address,
                'balance_scrt': balance_scrt,
                'tx_count': 0,
                'has_private_contract_interactions': False,
                'blockchain': 'secret_network',
                'source': 'secret_foundation'
            }

        except Exception as e:
            logger.error(f"Secret Network get_address_info error: {e}")
            return None


# Singleton instance
secret_network_service = SecretNetworkService()
