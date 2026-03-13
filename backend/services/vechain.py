import httpx
from typing import Optional
import logging

from services.http_client import get_client

logger = logging.getLogger(__name__)

VECHAIN_THOR_BASE_URL = "https://mainnet.vechain.org"


class VeChainService:
    """Service for fetching VeChain wallet data using the Thor REST API."""

    def __init__(self):
        self.base_url = VECHAIN_THOR_BASE_URL

    def validate_address(self, address: str) -> bool:
        """Validate a VeChain address (0x-prefixed, 42 chars hex)."""
        if not address.startswith("0x") or len(address) != 42:
            return False
        try:
            int(address, 16)
            return True
        except ValueError:
            return False

    def strip_prefix(self, address: str) -> str:
        """
        Strip vechain: or vet: prefix from address if present.

        Users must use a prefix to distinguish VeChain addresses from
        Ethereum addresses since both use the same 0x format.
        """
        lower = address.lower()
        if lower.startswith("vechain:"):
            return address[len("vechain:"):]
        if lower.startswith("vet:"):
            return address[len("vet:"):]
        return address

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including VET and VTHO balances.

        Uses VeChain Thor REST API (free, no authentication required).
        The API returns balances as hex strings in wei (18 decimals).

        Args:
            address: VeChain address, optionally prefixed with vechain: or vet:

        Returns:
            Dict with address, balance_vet, balance_vtho, tokens, blockchain,
            and source fields, or None on error.
        """
        raw_address = self.strip_prefix(address)

        if not self.validate_address(raw_address):
            logger.error(f"Invalid VeChain address: {raw_address}")
            return None

        try:
            client = get_client("vechain_thor", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/accounts/{raw_address}",
                timeout=30.0
            )

            if response.status_code == 400:
                logger.error(f"Invalid VeChain address per API: {raw_address}")
                return None

            if response.status_code != 200:
                logger.error(
                    f"VeChain Thor error: {response.status_code} - {response.text}"
                )
                return None

            data = response.json()

            # Parse hex balances (wei with 18 decimals)
            balance_hex = data.get("balance", "0x0")
            energy_hex = data.get("energy", "0x0")

            balance_wei = int(balance_hex, 16)
            energy_wei = int(energy_hex, 16)

            balance_vet = balance_wei / 10**18
            balance_vtho = energy_wei / 10**18

            # Include VTHO as a token entry for portfolio tracking
            tokens = []
            if balance_vtho > 0:
                tokens.append({
                    "symbol": "VTHO",
                    "name": "VeThor",
                    "balance": f"{balance_vtho:.8f}",
                    "decimals": 18,
                })

            return {
                "address": raw_address,
                "balance_vet": f"{balance_vet:.8f}",
                "balance_vtho": f"{balance_vtho:.8f}",
                "has_code": data.get("hasCode", False),
                "tokens": tokens,
                "blockchain": "vechain",
                "source": "thor",
            }

        except httpx.TimeoutException:
            logger.error(f"VeChain Thor timeout for address {raw_address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"VeChain Thor error: {e}")
            return None


# Singleton instance
vechain_service = VeChainService()
