"""
Liqwid Finance Adapter - Cardano lending/borrowing protocol with LQ staking.

Liqwid Finance is a decentralized lending and borrowing protocol on Cardano.
Users can stake LQ governance tokens in the protocol's staking contract.
Rewards are distributed via the SundaeSwap rewards portal.

Detection: UTXO_SCAN (scans staking contract UTXOs for user's payment key hash in datum)
"""

import asyncio
import logging
from typing import List, Optional

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)
from services.defi_protocols.cardano.utils import get_payment_credential, get_stake_address

logger = logging.getLogger(__name__)

# Liqwid Finance constants
LIQWID_STAKING_ADDRESS = "addr1w8arvq7j9qlrmt0wpdvpp7h4jr4fmfk8l653p9t907v2nsss7w7r4"
LIQWID_LQ_TOKEN = "da8c30857834c6ae7203935b89278c532b3995245295456f993e1d244c51"
LIQWID_REWARDS_API = "https://api.sundae-rewards.sundaeswap.finance/api/v1/liqwid"


class LiqwidAdapter(ProtocolAdapter):
    """Adapter for Liqwid Finance staking on Cardano."""

    PROTOCOL_NAME = "Liqwid"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://liqwid.finance"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Liqwid LQ staking positions.

        Queries the Liqwid staking contract for UTXOs with the user's
        payment key hash (PKH) in the inline datum. Uses parallel page
        fetching to handle large contract state (2700+ UTXOs).

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for staked LQ
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            headers = {"project_id": BLOCKFROST_API_KEY}
            client = get_client("blockfrost", timeout=15.0)
            sem = asyncio.Semaphore(5)  # Limit concurrent Blockfrost requests

            async def fetch_page(pg):
                async with sem:
                    try:
                        resp = await client.get(
                            f"{BLOCKFROST_BASE_URL}/addresses/{LIQWID_STAKING_ADDRESS}/utxos",
                            headers=headers,
                            params={"count": 100, "page": pg}
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        elif resp.status_code == 404:
                            return []  # No more pages
                        else:
                            logger.warning(f"[Liqwid] Page {pg} returned HTTP {resp.status_code}")
                            return None  # Error - eligible for retry
                    except Exception as e:
                        logger.warning(f"[Liqwid] Page {pg} fetch failed: {e}")
                        return None

            # Phase 1: Fetch first page to confirm contract has UTXOs
            first_page = await fetch_page(1)
            if not first_page:
                return []

            # Phase 2: Fetch remaining pages in parallel (contract has ~2700+ UTXOs = ~28 pages)
            remaining = await asyncio.gather(
                *[fetch_page(pg) for pg in range(2, 31)],
                return_exceptions=True
            )

            all_utxos = list(first_page)
            failed_pages = []
            for i, result in enumerate(remaining):
                pg = i + 2
                if isinstance(result, Exception):
                    logger.warning(f"[Liqwid] Page {pg} raised exception: {result}")
                    failed_pages.append(pg)
                elif result is None:
                    failed_pages.append(pg)
                else:
                    all_utxos.extend(result)

            # Retry failed pages sequentially (rate-limit safe)
            if failed_pages:
                logger.info(f"[Liqwid] Retrying {len(failed_pages)} failed pages sequentially...")
                for pg in failed_pages:
                    try:
                        result = await fetch_page(pg)
                        if result:
                            all_utxos.extend(result)
                    except Exception as e:
                        logger.warning(f"[Liqwid] Retry page {pg} failed: {e}")

            logger.info(f"[Liqwid] Scanned {len(all_utxos)} UTxOs for PKH {payment_cred[:16]}...")

            # Search for UTXOs with user's PKH in the inline datum
            total_staked = 0
            position_count = 0

            for utxo in all_utxos:
                inline_datum = utxo.get('inline_datum') or ''

                if inline_datum and payment_cred in inline_datum:
                    lq_amount = 0
                    for asset in utxo.get('amount', []):
                        if asset.get('unit') == LIQWID_LQ_TOKEN:
                            lq_amount = int(asset.get('quantity', 0))

                    if lq_amount > 0:
                        total_staked += lq_amount
                        position_count += 1

            if total_staked <= 0:
                logger.info(f"[Liqwid] No positions found in {len(all_utxos)} UTxOs for {address[:20]}...")
                return []

            logger.info(
                f"[Liqwid] Found {position_count} positions, "
                f"{total_staked/1_000_000:.2f} LQ for {address[:20]}..."
            )

            return [ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.STAKING,
                token_symbol="LQ",
                token_name="Liqwid",
                amount=total_staked / 1_000_000,
                extra={'position_count': position_count}
            )]

        except Exception as e:
            logger.error(f"Error getting Liqwid staking: {e}")
            return []

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending LQ rewards via the SundaeSwap rewards portal.

        Requires the stake address (not payment address) to query
        the Liqwid rewards API endpoint.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            Dict with reward info or None
        """
        try:
            # Get stake address from wallet address
            stake_address = await get_stake_address(address)

            client = get_client("blockfrost", timeout=15.0)

            pending_lq = 0
            claimed_lq = 0
            total_earned = 0

            if stake_address:
                try:
                    # Liqwid rewards API requires POST with stake address
                    response = await client.post(
                        f"{LIQWID_REWARDS_API}/rewards",
                        json={"stakeAddress": stake_address},
                        headers={"Content-Type": "application/json"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        rewards_data = data.get('rewards', {})
                        # Parse rewards data - structure: {epochNumber: {pending: X, claimed: Y}}
                        for epoch, epoch_data in rewards_data.items():
                            if isinstance(epoch_data, dict):
                                pending_lq += epoch_data.get('pending', 0) / 1_000_000
                                claimed_lq += epoch_data.get('claimed', 0) / 1_000_000
                        total_earned = pending_lq + claimed_lq
                        logger.info(
                            f"Liqwid rewards for {stake_address[:20]}...: "
                            f"pending={pending_lq}, claimed={claimed_lq}"
                        )
                except Exception as e:
                    logger.warning(f"Could not fetch from Liqwid rewards API: {e}")

            return {
                'protocol': 'Liqwid',
                'pending_rewards': pending_lq,
                'claimed_rewards': claimed_lq,
                'total_earned': total_earned,
                'reward_token': 'LQ',
                'rewards_url': 'https://liqwid-rewards.sundaeswap.finance/'
            }

        except Exception as e:
            logger.error(f"Error fetching Liqwid rewards: {e}")
            return None
