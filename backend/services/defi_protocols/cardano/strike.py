"""
Strike Finance Adapter - Cardano perpetuals DEX with STRIKE staking.

Strike Finance is a perpetual futures DEX on Cardano. Users stake STRIKE
governance tokens in the staking contract, identified by a per-user NFT
whose asset name matches the user's payment key hash.

Strike is primarily a perpetuals DEX, not a lending protocol. It does not
currently have separate lending/borrowing markets like Liqwid or Lenfi.
Users provide margin for perpetual positions, but this is handled via the
perps contract rather than a standalone lending market.

Detection: UTXO_SCAN (scans staking contract for user's staking NFT + STRIKE tokens)
"""

import asyncio
import logging
from typing import List, Optional

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client, blockfrost_fetch
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)
from services.defi_protocols.cardano.utils import get_payment_credential

logger = logging.getLogger(__name__)

# Strike Finance constants
STRIKE_STAKING_ADDRESS = "addr1z9yh4zcqs4gh78ysvh8nqp40fsnxg49nn3h6x25az9k8tms6409492020k6xml8uvwn34wrexagjh5fsk5xk96jyxk2qf3a7kj"
STRIKE_STAKING_NFT_POLICY = "497a8b0085517f1c9065cf3006af4c266454b39c6fa32a9d116c75ee"
STRIKE_TOKEN_POLICY = "f13ac4d66b3ee19a6aa0f2a22298737bd907cc95121662fc971b5275"
STRIKE_REWARDS_ADDRESS = "addr1z9yh4zcqs4gh78ysvh8nqp40fsnxg49nn3h6x25az9k8tms6409492020k6xml8uvwn34wrexagjh5fsk5xk96jyxk2qf3a7kj"


class StrikeAdapter(ProtocolAdapter):
    """Adapter for Strike Finance staking on Cardano."""

    PROTOCOL_NAME = "Strike"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://app.strikefinance.org"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Strike staking and yield_vault positions."""
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            client = get_client("blockfrost", timeout=15.0)
            
            # We'll use the generic approach: the main DeFiService calls 
            # the specialized V2 path for actual vault data.
            # This adapter is primarily for the 'lending-summary' (registry) path.
            # Since the V2 API is the source of truth, we'll return an empty 
            # list here and let the specialized V2 service handle it, 
            # OR we could implement a lightweight version here.
            # For now, we stick to the specialized V2 service for accuracy.
            return []
        except Exception as e:
            logger.error(f"Error in Strike detect_positions: {e}")
            return []

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending STRIKE rewards."""
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)

            pending_strike = 0
            accumulated_rewards = 0

            # Check for pending rewards in the staking UTXOs datum
            response = await blockfrost_fetch(
                f"/addresses/{STRIKE_STAKING_ADDRESS}/utxos",
                headers=self.headers,
                params={"count": 100},
                timeout=15.0
            )

            if response.status_code == 200:
                utxos = response.json()
                for utxo in utxos:
                    has_user_nft = False
                    for asset in utxo.get('amount', []):
                        unit = asset.get('unit', '')
                        if unit.startswith(STRIKE_STAKING_NFT_POLICY):
                            asset_name = unit[len(STRIKE_STAKING_NFT_policy):]
                            if asset_name == payment_cred:
                                has_user_nft = True
                                break

                    if has_user_nft:
                        for asset in utxo.get('amount', []):
                            unit = asset.get('unit', '')
                            if unit.startswith(STRIKE_TOKEN_POLICY) and unit != f"{STRIKE_TOKEN_POLICY}":
                                qty = int(asset.get('quantity', 0))
                                if qty > 0:
                                    accumulated_rewards += qty / 1_000_000

            return {
                'protocol': 'Strike',
                'pending_rewards': pending_strike,
                'accumulated_rewards': accumulated_rewards,
                'reward_token': 'STRIKE',
                'rewards_url': 'https://app.strikefinance.org/perpetuals/ada'
            }

        except Exception as e:
            logger.error(f"Error fetching Strike rewards: {e}")
            return None
