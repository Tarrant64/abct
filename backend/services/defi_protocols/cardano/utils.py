"""
Shared utilities for Cardano DeFi protocol adapters.

Contains common helpers used across multiple Cardano adapters,
like address decoding and stake address lookup.
"""

import bech32
import logging
from typing import Optional

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client

logger = logging.getLogger(__name__)


def get_payment_credential(address: str) -> Optional[str]:
    """Extract payment credential (key hash) from a Cardano address.

    Decodes a bech32 Cardano address and extracts the 28-byte
    payment credential (key hash) as a hex string.

    Args:
        address: Cardano bech32 address (addr1...)

    Returns:
        Hex string of the payment credential, or None on error
    """
    try:
        hrp, data = bech32.bech32_decode(address)
        if data is None:
            return None

        decoded = bech32.convertbits(data, 5, 8, False)
        if decoded is None or len(decoded) < 29:
            return None

        # First byte is header, next 28 bytes are payment credential
        return bytes(decoded[1:29]).hex()

    except Exception as e:
        logger.error(f"Error decoding address: {e}")
        return None


async def get_stake_address(address: str) -> Optional[str]:
    """Get the stake address associated with a wallet address via Blockfrost.

    Args:
        address: Cardano bech32 address

    Returns:
        Stake address string (stake1...) or None
    """
    try:
        headers = {"project_id": BLOCKFROST_API_KEY}
        client = get_client("blockfrost", timeout=30.0)
        response = await client.get(
            f"{BLOCKFROST_BASE_URL}/addresses/{address}",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('stake_address')
    except Exception as e:
        logger.warning(f"Could not get stake address: {e}")
    return None
