"""
Liqwid Finance Adapter - Cardano lending/borrowing protocol with LQ staking.

Liqwid Finance is a decentralized lending and borrowing protocol on Cardano.
Users can stake LQ governance tokens in the protocol's staking contract.
Users can also supply assets (receiving qTokens) and borrow against collateral.
Rewards are distributed via the SundaeSwap rewards portal.

Detection: UTXO_SCAN (staking) + TOKEN_BALANCE (lending supply via qTokens)
"""

import asyncio
import logging
from typing import List, Optional, Dict

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client, blockfrost_fetch
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)
from services.defi_protocols.cardano.utils import (
    get_payment_credential, get_stake_address, check_token_in_wallet
)

logger = logging.getLogger(__name__)

# Liqwid Finance constants
LIQWID_STAKING_ADDRESS = "addr1w8arvq7j9qlrmt0wpdvpp7h4jr4fmfk8l653p9t907v2nsss7w7r4"
LIQWID_LQ_TOKEN = "da8c30857834c6ae7203935b89278c532b3995245295456f993e1d244c51"
LIQWID_REWARDS_API = "https://api.sundae-rewards.sundaeswap.finance/api/v1/liqwid"

# qToken policy ID for supply receipt tokens
LIQWID_QTOKEN_POLICY = "d195ca7b121c6a0689e84cf3d6d526f1813e53266661c55a91027bdd"

# DefiLlama yields API for APY data
DEFILLAMA_YIELDS_API = "https://yields.llama.fi/pools"

# Known qToken asset name hex -> underlying token mapping
# qTokens have the asset name as hex-encoded underlying token symbol
QTOKEN_UNDERLYING_MAP = {
    "71414441": "ADA",        # qADA
    "7155534443": "USDC",     # qUSDC
    "7155534454": "USDT",     # qUSDT
    "71444a4544": "DJED",     # qDJED
    "7155534441": "USDA",     # qUSDA
    "7155534443_58": "USDCX", # qUSDCX (variant)
    "71555344_4d": "USDM",    # qUSDM
    "71694553_44": "iUSD",    # qiUSD
    "71534e454b": "SNEK",     # qSNEK
    "714d494e": "MIN",        # qMIN
    "71494147": "IAG",        # qIAG
    "7153_48454e": "SHEN",    # qSHEN
    "714254_43": "BTC",       # qBTC
    "71455247": "ERG",        # qERG
    "714e49474854": "NIGHT",  # qNIGHT
}


class LiqwidAdapter(ProtocolAdapter):
    """Adapter for Liqwid Finance staking and lending on Cardano."""

    PROTOCOL_NAME = "Liqwid"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://liqwid.finance"
    LOGO_URL = ""

    # Cache for DefiLlama market data (refreshed per detect_positions call)
    _market_cache: Optional[Dict] = None
    _market_cache_time: float = 0

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Liqwid LQ staking and lending supply positions.

        Scans for:
        1. LQ governance staking (UTXO scan of staking contract)
        2. qToken supply positions (token balance check)

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for staked LQ and supply positions
        """
        positions = []

        # Run staking detection and lending detection in parallel
        staking_task = self._detect_staking(address)
        lending_task = self._detect_lending_supply(address)

        staking_positions, lending_positions = await asyncio.gather(
            staking_task, lending_task, return_exceptions=True
        )

        if isinstance(staking_positions, list):
            positions.extend(staking_positions)
        elif isinstance(staking_positions, Exception):
            logger.error(f"[Liqwid] Staking detection error: {staking_positions}")

        if isinstance(lending_positions, list):
            positions.extend(lending_positions)
        elif isinstance(lending_positions, Exception):
            logger.error(f"[Liqwid] Lending detection error: {lending_positions}")

        return positions

    async def _detect_staking(self, address: str) -> List[ProtocolPosition]:
        """Detect LQ governance staking positions via UTXO scan."""
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            headers = {"project_id": BLOCKFROST_API_KEY}
            sem = asyncio.Semaphore(5)

            async def fetch_page(pg):
                async with sem:
                    try:
                        resp = await blockfrost_fetch(
                            f"/addresses/{LIQWID_STAKING_ADDRESS}/utxos",
                            headers=headers,
                            params={"count": 100, "page": pg},
                            timeout=15.0
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        elif resp.status_code == 404:
                            return []
                        else:
                            logger.warning(f"[Liqwid] Page {pg} returned HTTP {resp.status_code}")
                            return None
                    except Exception as e:
                        logger.warning(f"[Liqwid] Page {pg} fetch failed: {e}")
                        return None

            first_page = await fetch_page(1)
            if not first_page:
                return []

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
                logger.info(f"[Liqwid] No staking positions found for {address[:20]}...")
                return []

            logger.info(
                f"[Liqwid] Found {position_count} staking positions, "
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

    async def _detect_lending_supply(self, address: str) -> List[ProtocolPosition]:
        """Detect Liqwid lending supply positions via qToken balance.

        qTokens (policy d195ca7b...) are receipt tokens issued when users
        supply assets to Liqwid markets. The qToken amount represents the
        user's share of the supply pool.
        """
        try:
            matched = await check_token_in_wallet(address, LIQWID_QTOKEN_POLICY)
            if not matched:
                return []

            # Fetch market APY data from DefiLlama (fire-and-forget if it fails)
            market_data = await self._fetch_market_data()

            positions = []
            for token in matched:
                qty = token["quantity"]
                asset_hex = token.get("asset_name_hex", "")

                # Determine underlying token from hex asset name
                underlying = self._resolve_underlying_token(asset_hex)
                q_symbol = f"q{underlying}" if underlying else "qToken"

                # qTokens have 6 decimals
                amount = float(qty) / 1_000_000

                # Look up APY from DefiLlama data
                apy = None
                if market_data and underlying:
                    pool_info = market_data.get(underlying.upper())
                    if pool_info:
                        apy = pool_info.get('apy')

                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=q_symbol,
                    token_name=f"Liqwid {underlying or 'Supply'} Market",
                    amount=amount,
                    value_usd=0.0,  # Requires exchange rate for accurate calc
                    apy=apy,
                    extra={
                        'underlying_token': underlying or 'unknown',
                        'qtoken_amount': amount,
                        'receipt_token': token.get("unit", ""),
                    },
                ))

            if positions:
                logger.info(
                    f"[Liqwid] Found {len(positions)} lending supply position(s) "
                    f"for {address[:20]}..."
                )

            return positions

        except Exception as e:
            logger.error(f"[Liqwid] Lending supply detection error: {e}")
            return []

    def _resolve_underlying_token(self, asset_hex: str) -> str:
        """Resolve qToken asset name hex to underlying token symbol.

        First checks the hardcoded map, then attempts direct hex decode.
        """
        if asset_hex in QTOKEN_UNDERLYING_MAP:
            return QTOKEN_UNDERLYING_MAP[asset_hex]

        # Try decoding hex as UTF-8 and stripping 'q' prefix
        try:
            decoded = bytes.fromhex(asset_hex).decode("utf-8", errors="replace").strip("\x00")
            if decoded.startswith("q") and len(decoded) > 1:
                return decoded[1:]
            return decoded or "unknown"
        except Exception:
            return "unknown"

    async def _fetch_market_data(self) -> Optional[Dict]:
        """Fetch Liqwid market data from DefiLlama yields API.

        Returns dict mapping symbol -> {apy, tvl} for Liqwid pools.
        Cached for the duration of the detect_positions call.
        """
        import time
        now = time.time()

        # Use cache if less than 5 minutes old
        if self._market_cache and (now - self._market_cache_time) < 300:
            return self._market_cache

        try:
            client = get_client("blockfrost", timeout=15.0)
            response = await client.get(DEFILLAMA_YIELDS_API, timeout=15.0)
            if response.status_code != 200:
                logger.warning(f"[Liqwid] DefiLlama API returned {response.status_code}")
                return self._market_cache

            data = response.json()
            pools = data.get('data', [])

            market_map = {}
            for pool in pools:
                if pool.get('project', '').lower() == 'liqwid' and pool.get('chain', '').lower() == 'cardano':
                    symbol = pool.get('symbol', '').upper()
                    market_map[symbol] = {
                        'apy': pool.get('apy', 0),
                        'tvl': pool.get('tvlUsd', 0),
                        'apy_base': pool.get('apyBase', 0),
                        'apy_reward': pool.get('apyReward', 0),
                    }

            if market_map:
                LiqwidAdapter._market_cache = market_map
                LiqwidAdapter._market_cache_time = now
                logger.info(f"[Liqwid] Cached {len(market_map)} market pools from DefiLlama")

            return market_map

        except Exception as e:
            logger.warning(f"[Liqwid] Failed to fetch DefiLlama data: {e}")
            return self._market_cache

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
