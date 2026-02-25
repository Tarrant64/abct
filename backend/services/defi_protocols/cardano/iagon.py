"""
Iagon Adapter - Cardano DePIN (Decentralized Physical Infrastructure) protocol.

Iagon provides decentralized storage and compute on Cardano. Users stake IAG
tokens across multiple staking contracts (old, operator, delegated). Position
tracking uses incremental transaction scanning with persistent cache to avoid
re-scanning the full history on each call.

Detection: UTXO_SCAN (incremental transaction scan tracking IAG flows through staking contracts)
"""

import asyncio
import logging
from typing import List, Optional

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)

logger = logging.getLogger(__name__)

# Iagon staking contracts (addresses from DefiLlama adapter maintained by Iagon)
# NOTE: Old staking contract excluded — it's deprecated and shows ~7568 IAG that was refunded
# separately. Including it would double-count staked IAG.
IAGON_OLD_STAKING_ADDRESS = "addr1w9k25wa83tyfk5d26tgx4w99e5yhxd86hg33yl7x7ej7yusggvmu3"  # DEPRECATED
IAGON_OPERATOR_STAKING_ADDRESS = "addr1zxkrtm5fcf43ukp8w8kstt65kelawutmht4a0aezl06rp43y2c4s7gthspjk2c4557c9zltqcssl4qz7x5syzf7yknhqma7zxx"
IAGON_DELEGATED_STAKING_ADDRESS = "addr1z8awewqwaek2m7w6c5vyycldf5tykw87w820da273a4smgpy2c4s7gthspjk2c4557c9zltqcssl4qz7x5syzf7yknhq6uv6j0"
IAGON_BATCHER_ADDRESS = "addr1v8ckrqqrj4u34sxt45vdu8s8nqq3lm3lc8s7su5nyzaq9tcqy2n8j"  # Active batcher/aggregator

IAGON_ALL_STAKING_ADDRESSES = {
    IAGON_OPERATOR_STAKING_ADDRESS,
    IAGON_DELEGATED_STAKING_ADDRESS, IAGON_BATCHER_ADDRESS
}

# Staking-only addresses (excluding batcher and deprecated old contract)
# The batcher is transient; only actual staking contract outputs reflect current stake
IAGON_STAKING_CONTRACT_ADDRESSES = {
    IAGON_OPERATOR_STAKING_ADDRESS,
    IAGON_DELEGATED_STAKING_ADDRESS
}

IAGON_IAG_POLICY = "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114"
IAGON_IAG_ASSET = "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114494147"

# Global semaphore to limit concurrent Iagon scans (each scan makes many Blockfrost calls).
# Without this, 44+ wallets scanning simultaneously overwhelms Blockfrost rate limits.
_iagon_scan_semaphore = asyncio.Semaphore(3)


class IagonAdapter(ProtocolAdapter):
    """Adapter for Iagon DePIN staking on Cardano."""

    PROTOCOL_NAME = "Iagon"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://iagon.com/staking"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Iagon staking positions via incremental transaction scanning.

        Checks all 3 Iagon staking contracts (old, operator, delegated).
        Uses a persistent cache to track last-scanned block height and
        accumulated deposit/withdrawal totals, so subsequent calls only
        scan new transactions.

        Rate-limited by a global semaphore (max 3 concurrent scans).

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for staked IAG
        """
        async with _iagon_scan_semaphore:
            return await self._detect_positions_inner(address)

    async def _detect_positions_inner(self, address: str) -> List[ProtocolPosition]:
        """Inner implementation of Iagon staking scan (called under semaphore)."""
        from database import get_cache, set_cache

        try:
            headers = {"project_id": BLOCKFROST_API_KEY}
            client = get_client("blockfrost", timeout=15.0)

            # Load incremental scan state from persistent cache (7-day TTL)
            # Version marker: bump when calculation logic changes to invalidate stale data
            SCAN_STATE_VERSION = 5  # v5: exclude deprecated old staking contract (refunded separately)
            scan_key = f"iagon_scan_state_{address}"
            scan_state = await get_cache(scan_key)

            # Track flows through STAKING CONTRACTS ONLY (not batcher).
            # Key insight from on-chain analysis:
            #   - Principal deposits/withdrawals go through staking contract addresses
            #   - Reward claims go through the batcher ONLY
            # By ignoring batcher-only flows, we get accurate staked = deposits - withdrawals.
            staking_deposits = 0
            staking_withdrawals = 0
            total_rewards = 0  # informational: batcher-only outflows (reward claims)
            from_block = None

            if scan_state and scan_state.get('version') == SCAN_STATE_VERSION:
                staking_deposits = scan_state.get('staking_deposits', 0)
                staking_withdrawals = scan_state.get('staking_withdrawals', 0)
                total_rewards = scan_state.get('total_rewards', 0)
                from_block = scan_state.get('last_block_height')
                logger.info(
                    f"[Iagon] Resuming scan for {address[:20]}... from block {from_block}, "
                    f"staked={(staking_deposits - staking_withdrawals)/1_000_000:.2f} IAG"
                )
            elif scan_state:
                logger.info(
                    f"[Iagon] Discarding stale v{scan_state.get('version', 1)} scan state "
                    f"for {address[:20]}... (need v{SCAN_STATE_VERSION})"
                )

            # Fetch transactions (incremental if we have scan state)
            all_txs = []
            page = 1

            while True:
                params = {"count": 100, "page": page, "order": "asc"}
                if from_block:
                    # Start from next block to avoid re-processing already-counted txs
                    params["from"] = str(from_block + 1)

                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/addresses/{address}/transactions",
                    headers=headers,
                    params=params
                )

                if response.status_code != 200:
                    break

                txs = response.json()
                if not txs:
                    break

                all_txs.extend(txs)
                if len(txs) < 100:
                    break  # Last page
                page += 1

            logger.info(
                f"[Iagon] Scanned {len(all_txs)} {'new ' if from_block else ''}transactions "
                f"across {page} pages for {address[:20]}..."
            )

            # If incremental and no new txs, return cached result
            if from_block and not all_txs:
                net_staked = staking_deposits - staking_withdrawals
                if net_staked <= 0:
                    return []
                return [ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.DEPIN,
                    token_symbol="IAG",
                    token_name="Iagon",
                    amount=net_staked / 1_000_000,
                    extra={
                        'total_deposited': staking_deposits / 1_000_000,
                        'total_withdrawn': staking_withdrawals / 1_000_000,
                        'total_rewards_claimed': total_rewards / 1_000_000,
                        'position_count': 1,
                        'contract': 'multiple'
                    }
                )]

            if not all_txs and not scan_state:
                return []

            # Fetch UTxOs in parallel batches (5 concurrent to respect Blockfrost limits)
            sem = asyncio.Semaphore(5)

            async def fetch_tx_utxos(tx_hash):
                async with sem:
                    try:
                        resp = await client.get(
                            f"{BLOCKFROST_BASE_URL}/txs/{tx_hash}/utxos",
                            headers=headers
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        else:
                            logger.warning(f"[Iagon] UTxO fetch for tx {tx_hash[:16]} returned HTTP {resp.status_code}")
                            return None
                    except Exception as e:
                        logger.warning(f"[Iagon] UTxO fetch for tx {tx_hash[:16]} failed: {e}")
                        return None

            if all_txs:
                utxo_results = await asyncio.gather(
                    *[fetch_tx_utxos(tx['tx_hash']) for tx in all_txs],
                    return_exceptions=True
                )

                # Track last block for incremental scan
                last_block = from_block or 0

                for i, tx_data in enumerate(utxo_results):
                    if isinstance(tx_data, Exception) or tx_data is None:
                        continue

                    tx_block = all_txs[i].get('block_height', 0)
                    if tx_block > last_block:
                        last_block = tx_block

                    # Calculate IAG flows separately for staking contracts vs batcher
                    staking_receives = 0  # IAG received by staking contracts
                    staking_sends = 0     # IAG sent from staking contracts
                    batcher_receives = 0  # IAG received by batcher
                    batcher_sends = 0     # IAG sent from batcher
                    user_receives_iag = 0

                    for inp in tx_data.get('inputs', []):
                        for amt in inp.get('amount', []):
                            if amt['unit'] == IAGON_IAG_ASSET:
                                qty = int(amt['quantity'])
                                if inp['address'] in IAGON_STAKING_CONTRACT_ADDRESSES:
                                    staking_sends += qty
                                elif inp['address'] == IAGON_BATCHER_ADDRESS:
                                    batcher_sends += qty

                    for out in tx_data.get('outputs', []):
                        for amt in out.get('amount', []):
                            if amt['unit'] == IAGON_IAG_ASSET:
                                qty = int(amt['quantity'])
                                if out['address'] == address:
                                    user_receives_iag += qty
                                elif out['address'] in IAGON_STAKING_CONTRACT_ADDRESSES:
                                    staking_receives += qty
                                elif out['address'] == IAGON_BATCHER_ADDRESS:
                                    batcher_receives += qty

                    # Track staking contract flows (principal deposits/withdrawals)
                    net_to_staking = staking_receives - staking_sends
                    if net_to_staking > 0:
                        staking_deposits += net_to_staking
                    elif net_to_staking < 0:
                        staking_withdrawals += abs(net_to_staking)

                    # Track batcher-only flows as reward claims (informational)
                    if staking_sends == 0 and staking_receives == 0:
                        net_batcher = batcher_receives - batcher_sends
                        if net_batcher < 0 and user_receives_iag > 0:
                            total_rewards += user_receives_iag

                # Save scan state persistently (7-day TTL)
                await set_cache(scan_key, {
                    'version': SCAN_STATE_VERSION,
                    'staking_deposits': staking_deposits,
                    'staking_withdrawals': staking_withdrawals,
                    'total_rewards': total_rewards,
                    'last_block_height': last_block
                }, ttl_seconds=604800)

            net_staked = staking_deposits - staking_withdrawals

            logger.info(
                f"[Iagon] {address[:20]}... staked={net_staked/1_000_000:.2f} IAG "
                f"(deposits={staking_deposits/1_000_000:.2f}, "
                f"withdrawals={staking_withdrawals/1_000_000:.2f}, "
                f"rewards_claimed={total_rewards/1_000_000:.2f})"
            )

            if net_staked <= 0:
                return []

            return [ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.DEPIN,
                token_symbol="IAG",
                token_name="Iagon",
                amount=net_staked / 1_000_000,
                extra={
                    'total_deposited': staking_deposits / 1_000_000,
                    'total_withdrawn': staking_withdrawals / 1_000_000,
                    'total_rewards_claimed': total_rewards / 1_000_000,
                    'position_count': 1,
                    'contract': 'multiple'
                }
            )]

        except Exception as e:
            logger.error(f"Error getting Iagon staking: {e}")
            return []
