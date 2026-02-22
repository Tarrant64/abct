"""
Monero Service - Price tracking only (manual balance entry).

Monero (XMR) uses ring signatures, stealth addresses, and RingCT to make
all transactions completely private. No public API can return wallet balances.
Users manually enter their XMR holdings.

Address formats:
  Primary:    95 chars starting with '4'
  Subaddress: 95 chars starting with '8'
  Integrated: 106 chars starting with '4'
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MoneroService:
    """
    Monero (XMR) service - price tracking only.

    Monero uses ring signatures, stealth addresses, and RingCT to make all
    transactions completely private. No public API can return wallet balances.
    Users manually enter their XMR holdings.
    """

    def validate_address(self, address: str) -> bool:
        """
        Validate XMR address format.

        Primary:    95 chars starting with '4'
        Subaddress: 95 chars starting with '8'
        Integrated: 106 chars starting with '4'
        """
        if not address or not isinstance(address, str):
            return False

        # Primary address: 95 chars starting with '4'
        if address.startswith('4') and len(address) == 95:
            return True

        # Subaddress: 95 chars starting with '8'
        if address.startswith('8') and len(address) == 95:
            return True

        # Integrated address: 106 chars starting with '4'
        if address.startswith('4') and len(address) == 106:
            return True

        return False

    async def get_address_info(self, address: str, manual_balance: float = 0.0) -> dict:
        """
        Returns manual balance only — no API calls.
        XMR balances cannot be fetched from public APIs.

        Args:
            address: Monero wallet address (stored for reference only)
            manual_balance: Manually entered XMR balance

        Returns:
            Dict with manual balance data.
        """
        return {
            'address': address,
            'balance_xmr': manual_balance,
            'manual': True,
            'blockchain': 'monero',
            'source': 'manual',
            'privacy_note': 'Monero is fully private. Balance set manually.'
        }


# Singleton instance
monero_service = MoneroService()
