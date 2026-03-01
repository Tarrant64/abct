"""
Surf Lending Adapter - Cardano lending/borrowing protocol (formerly Flow Lending).

Surf Lending allows users to supply ADA and other assets to earn yield.
Detection first tries the Surf Lending REST API, falling back to on-chain
UTXO scanning of the staking contract.

Detection: UTXO_SCAN (API-first with on-chain fallback)
"""

import logging
from typing import List, Optional

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client, blockfrost_fetch
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)
from services.defi_protocols.cardano.utils import get_payment_credential

logger = logging.getLogger(__name__)

# Surf Lending API
SURF_LENDING_API = "https://api.surflending.org"

# Surf staking contract address for on-chain fallback
# NOTE: This address is used in the original defi.py but was referenced without
# being defined as a top-level constant there. If the on-chain fallback is needed,
# verify this address is correct for the current Surf Lending deployment.
SURF_STAKING_ADDRESS = ""  # TODO: Set correct staking contract address


class SurfAdapter(ProtocolAdapter):
    """Adapter for Surf Lending on Cardano."""

    PROTOCOL_NAME = "Surf Lending"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://surflending.org"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Surf Lending positions.

        First tries the Surf Lending REST API for position data.
        Falls back to on-chain UTXO scanning of the staking contract
        if the API is unavailable.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for supplied assets
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            headers = {"project_id": BLOCKFROST_API_KEY}
            client = get_client("blockfrost", timeout=15.0)

            # Try Surf Lending API first
            try:
                response = await client.get(
                    f"{SURF_LENDING_API}/api/v1/positions/{address}"
                )
                if response.status_code == 200:
                    data = response.json()
                    total_supplied = data.get('total_supplied', 0)
                    if total_supplied > 0:
                        positions = [ProtocolPosition(
                            protocol=self.PROTOCOL_NAME,
                            chain="cardano",
                            position_type=PositionType.LENDING_SUPPLY,
                            token_symbol="ADA",
                            token_name="Cardano",
                            amount=total_supplied,
                            apy=data.get('supply_apy'),
                            pending_rewards=data.get('pending_rewards', 0),
                            reward_token="SURF",
                            extra={
                                'total_borrowed': data.get('total_borrowed', 0),
                                'api_positions': data.get('positions', [])
                            }
                        )]
                        return positions
            except Exception as e:
                logger.warning(f"Surf Lending API not available: {e}")

            # Fallback: Query on-chain data
            if not SURF_STAKING_ADDRESS:
                logger.debug("[Surf] No staking address configured for on-chain fallback")
                return []

            response = await blockfrost_fetch(
                f"/addresses/{SURF_STAKING_ADDRESS}/utxos",
                headers=headers,
                params={"count": 100},
                timeout=30.0
            )

            if response.status_code != 200:
                return []

            utxos = response.json()
            total_supplied = 0
            position_count = 0

            for utxo in utxos:
                inline_datum = utxo.get('inline_datum') or ''
                if payment_cred in inline_datum:
                    # Found user's position
                    ada_amount = 0
                    for asset in utxo.get('amount', []):
                        if asset.get('unit') == 'lovelace':
                            ada_amount = int(asset.get('quantity', 0)) / 1_000_000

                    if ada_amount > 0:
                        total_supplied += ada_amount
                        position_count += 1

            if total_supplied > 0:
                return [ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol="ADA",
                    token_name="Cardano",
                    amount=total_supplied,
                    extra={'position_count': position_count}
                )]

        except Exception as e:
            logger.error(f"Error getting Surf Lending positions: {e}")

        return []
