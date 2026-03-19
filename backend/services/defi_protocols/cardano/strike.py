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
        """Detect Strike staking positions.

        Queries the Strike staking contract for UTXOs containing a
        per-user staking NFT (policy STRIKE_STAKING_NFT_POLICY) whose
        asset name matches the user's payment key hash. If found, reads
        STRIKE token amount from the same UTXO.

        Uses parallel page fetching to handle large contract state (1000+ UTXOs).

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for staked STRIKE
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            headers = {"project_id": BLOCKFROST_API_KEY}
            client = get_client("blockfrost", timeout=15.0)
            sem = asyncio.Semaphore(5)

            async def fetch_page(pg):
                async with sem:
                    try:
                        resp = await blockfrost_fetch(
                            f"/addresses/{STRIKE_STAKING_ADDRESS}/utxos",
                            headers=headers,
                            params={"count": 100, "page": pg},
                            timeout=15.0
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        elif resp.status_code == 404:
                            return []
                        else:
                            logger.warning(f"[Strike] Page {pg} returned HTTP {resp.status_code}")
                            return None
                    except Exception as e:
                        logger.warning(f"[Strike] Page {pg} fetch failed: {e}")
                        return None

            # Fetch first page, then remaining in parallel
            first_page = await fetch_page(1)
            if not first_page:
                return []

            remaining = await asyncio.gather(
                *[fetch_page(pg) for pg in range(2, 16)],
                return_exceptions=True
            )

            all_utxos = list(first_page)
            failed_pages = []
            for i, result in enumerate(remaining):
                pg = i + 2
                if isinstance(result, Exception):
                    logger.warning(f"[Strike] Page {pg} raised exception: {result}")
                    failed_pages.append(pg)
                elif result is None:
                    failed_pages.append(pg)
                else:
                    all_utxos.extend(result)

            if failed_pages:
                logger.info(f"[Strike] Retrying {len(failed_pages)} failed pages sequentially...")
                for pg in failed_pages:
                    try:
                        result = await fetch_page(pg)
                        if result:
                            all_utxos.extend(result)
                    except Exception as e:
                        logger.warning(f"[Strike] Retry page {pg} failed: {e}")

            logger.info(f"[Strike] Scanned {len(all_utxos)} UTxOs for PKH {payment_cred[:16]}...")

            # Search for UTXOs with user's staking NFT
            total_staked = 0
            position_count = 0

            for utxo in all_utxos:
                has_user_nft = False
                strike_amount = 0

                for asset in utxo.get('amount', []):
                    unit = asset.get('unit', '')
                    qty = int(asset.get('quantity', 0))

                    # Check if this UTXO has an NFT with user's PKH
                    if unit.startswith(STRIKE_STAKING_NFT_POLICY):
                        asset_name = unit[len(STRIKE_STAKING_NFT_POLICY):]
                        if asset_name == payment_cred:
                            has_user_nft = True

                    # Check for STRIKE tokens
                    if unit.startswith(STRIKE_TOKEN_POLICY):
                        strike_amount = qty

                if has_user_nft and strike_amount > 0:
                    total_staked += strike_amount
                    position_count += 1

            if total_staked <= 0:
                return []

            return [ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.STAKING,
                token_symbol="STRIKE",
                token_name="Strike Finance",
                amount=total_staked / 1_000_000,
                extra={'position_count': position_count}
            )]

        except Exception as e:
            logger.error(f"Error getting Strike staking: {e}")
            return []

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending STRIKE rewards.

        Checks the staking UTXOs for accumulated rewards by finding
        the user's staking NFT and reading additional STRIKE tokens
        in the same UTXO.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            Dict with reward info or None
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return None

            headers = {"project_id": BLOCKFROST_API_KEY}
            client = get_client("blockfrost", timeout=15.0)

            pending_strike = 0
            accumulated_rewards = 0

            # Check for pending rewards in the staking UTXOs datum
            response = await blockfrost_fetch(
                f"/addresses/{STRIKE_STAKING_ADDRESS}/utxos",
                headers=headers,
                params={"count": 100},
                timeout=15.0
            )

            if response.status_code == 200:
                utxos = response.json()
                for utxo in utxos:
                    # Check if this UTXO belongs to user
                    has_user_nft = False
                    for asset in utxo.get('amount', []):
                        unit = asset.get('unit', '')
                        if unit.startswith(STRIKE_STAKING_NFT_POLICY):
                            asset_name = unit[len(STRIKE_STAKING_NFT_POLICY):]
                            if asset_name == payment_cred:
                                has_user_nft = True
                                break

                    if has_user_nft:
                        # Check for STRIKE tokens in the UTXO (accumulated rewards)
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
