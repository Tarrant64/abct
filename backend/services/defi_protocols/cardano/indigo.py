"""
Indigo Protocol Adapter - Cardano synthetic asset platform.

Indigo Protocol enables users to:
- Stake INDY governance tokens for rewards
- Open CDPs (Collateralized Debt Positions) to mint iAssets (iUSD, iBTC, iETH, iSOL)
- Deposit iAssets in Stability Pools for liquidation premiums

Detection: UTXO_SCAN via Indigo Analytics API (matches payment credential)

API Endpoints:
- /api/v1/staking/positions — INDY staking positions
- /api/v1/loans — CDP positions (collateral + minted iAssets)
- /api/v1/stability-pools/accounts — Stability Pool deposits
"""

import logging
from typing import List, Optional, Dict

from services.http_client import get_client
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)
from services.defi_protocols.cardano.utils import get_payment_credential

logger = logging.getLogger(__name__)

# Indigo Protocol API
INDIGO_API_BASE = "https://analytics.indigoprotocol.io"

# iAsset decimals: iUSD uses 6, iBTC/iETH/iSOL use smaller units
# From the API, minted amounts are in base units — iUSD is 6 decimals,
# iBTC is ~8 satoshi-like (but Indigo uses variable precision).
# The API returns raw integers; we normalize per asset.
IASSET_DECIMALS = {
    'iUSD': 6,
    'iBTC': 6,
    'iETH': 6,
    'iSOL': 6,
}

# Minimum collateral ratios per iAsset (Indigo governance parameters, on-chain public data).
# These are the minimum ratios; below this, CDPs are eligible for liquidation.
MIN_COLLATERAL_RATIO = {
    'iUSD': 150,  # 150%
    'iBTC': 150,
    'iETH': 150,
    'iSOL': 150,
}


class IndigoAdapter(ProtocolAdapter):
    """Adapter for Indigo Protocol on Cardano — staking, CDPs, and Stability Pool."""

    PROTOCOL_NAME = "Indigo"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://app.indigoprotocol.io"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect all Indigo positions: staking, CDPs, and Stability Pool.

        Queries the Indigo Analytics API for staking positions, CDPs (loans),
        and stability pool accounts, filtering by payment credential.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for all detected Indigo positions
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            results = []

            # Fetch staking, CDPs, and stability pool in parallel
            client = get_client("blockfrost", timeout=15.0)

            staking_positions = await self._fetch_staking(client, payment_cred)
            results.extend(staking_positions)

            cdp_positions = await self._fetch_cdps(client, payment_cred)
            results.extend(cdp_positions)

            sp_positions = await self._fetch_stability_pool(client, payment_cred)
            results.extend(sp_positions)

            return results

        except Exception as e:
            logger.error(f"Error detecting Indigo positions: {e}")
            return []

    async def _fetch_staking(
        self, client, payment_cred: str
    ) -> List[ProtocolPosition]:
        """Fetch INDY staking positions."""
        try:
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/staking/positions"
            )

            if response.status_code != 200:
                logger.error(f"Indigo staking API error: {response.status_code}")
                return []

            positions = response.json()
            total_staked = 0

            for pos in positions:
                if pos.get('owner') == payment_cred:
                    staked = pos.get('stakedIndy', 0)
                    total_staked += staked

            if total_staked <= 0:
                return []

            return [ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.STAKING,
                token_symbol="INDY",
                token_name="Indigo",
                amount=total_staked / 1_000_000,
                extra={
                    'position_count': sum(
                        1 for p in positions if p.get('owner') == payment_cred
                    )
                }
            )]

        except Exception as e:
            logger.error(f"Error fetching Indigo staking: {e}")
            return []

    async def _fetch_cdps(
        self, client, payment_cred: str
    ) -> List[ProtocolPosition]:
        """Fetch CDP (loan) positions from the Indigo Analytics API.

        Each CDP has: collateral (ADA in lovelace), minted iAsset amount,
        and the iAsset type (iUSD, iBTC, iETH, iSOL).
        """
        try:
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/loans"
            )

            if response.status_code != 200:
                logger.error(f"Indigo loans API error: {response.status_code}")
                return []

            loans = response.json()
            results = []

            for loan in loans:
                if loan.get('owner') != payment_cred:
                    continue

                asset = loan.get('asset', 'iUSD')
                collateral_lovelace = loan.get('collateral', 0)
                minted_raw = loan.get('minted', 0)

                collateral_ada = parseFloat(collateral_lovelace) / 1_000_000
                decimals = IASSET_DECIMALS.get(asset, 6)
                minted_amount = parseFloat(minted_raw) / (10 ** decimals)

                if collateral_ada <= 0 and minted_amount <= 0:
                    continue

                # Calculate collateral ratio (requires knowing ADA and iAsset prices)
                # We store the raw data and let the frontend calculate with live prices
                min_ratio = MIN_COLLATERAL_RATIO.get(asset, 150)

                results.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.CDP,
                    token_symbol=asset,
                    token_name=f"Indigo {asset} CDP",
                    amount=minted_amount,
                    extra={
                        'cdp_type': 'mint',
                        'collateral_ada': collateral_ada,
                        'minted_asset': asset,
                        'minted_amount': minted_amount,
                        'min_collateral_ratio': min_ratio,
                        'output_hash': loan.get('outputHash', ''),
                    }
                ))

            if results:
                logger.info(
                    f"Indigo CDPs: found {len(results)} position(s) "
                    f"for {payment_cred[:12]}..."
                )

            return results

        except Exception as e:
            logger.error(f"Error fetching Indigo CDPs: {e}")
            return []

    async def _fetch_stability_pool(
        self, client, payment_cred: str
    ) -> List[ProtocolPosition]:
        """Fetch Stability Pool deposit positions.

        The stability pool snapshot data uses large-precision integer strings.
        snapshotD represents the deposit amount scaled by pool precision.
        """
        try:
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/stability-pools/accounts"
            )

            if response.status_code != 200:
                logger.error(
                    f"Indigo stability pools API error: {response.status_code}"
                )
                return []

            accounts = response.json()
            results = []

            # Group deposits by asset for the same owner
            deposits_by_asset = {}

            for acct in accounts:
                if acct.get('owner') != payment_cred:
                    continue

                asset = acct.get('asset', 'iUSD')
                snapshot_d = acct.get('snapshotD', '0')

                # snapshotD is a scaled deposit amount (large integer string).
                # The precision is 1e18 (standard Indigo pool math).
                try:
                    deposit_scaled = parseFloat(snapshot_d)
                except (ValueError, TypeError):
                    deposit_scaled = 0

                if deposit_scaled <= 0:
                    continue

                # Convert from pool-precision to human-readable amount
                # snapshotD is scaled by 1e18 in Indigo's math
                decimals = IASSET_DECIMALS.get(asset, 6)
                deposit_amount = deposit_scaled / (10 ** 18) / (10 ** decimals)

                # Some deposits can be tiny dust — skip if less than threshold
                if deposit_amount < 0.000001:
                    continue

                if asset not in deposits_by_asset:
                    deposits_by_asset[asset] = {
                        'total_deposit': 0,
                        'position_count': 0,
                    }

                deposits_by_asset[asset]['total_deposit'] += deposit_amount
                deposits_by_asset[asset]['position_count'] += 1

            for asset, data in deposits_by_asset.items():
                results.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.STABILITY_POOL,
                    token_symbol=asset,
                    token_name=f"Indigo {asset} Stability Pool",
                    amount=data['total_deposit'],
                    extra={
                        'pool_asset': asset,
                        'deposited_amount': data['total_deposit'],
                        'position_count': data['position_count'],
                    }
                ))

            if results:
                logger.info(
                    f"Indigo Stability Pool: found {len(results)} pool(s) "
                    f"for {payment_cred[:12]}..."
                )

            return results

        except Exception as e:
            logger.error(f"Error fetching Indigo Stability Pool: {e}")
            return []

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending INDY and ADA rewards from Indigo Protocol.

        Uses Indigo Analytics API to fetch staking positions which include
        rewards data. Indigo stakers earn both INDY and ADA rewards.

        The lockedAmount may include accumulated rewards beyond staked principal.

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

            client = get_client("blockfrost", timeout=15.0)

            # Fetch staking positions which include rewards data
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/staking/positions"
            )

            if response.status_code != 200:
                logger.warning(f"Indigo staking API returned {response.status_code}")
                return None

            positions_data = response.json()

            # Find user's positions and rewards
            total_staked = 0
            total_locked = 0
            snapshot_ada = 0

            for pos in positions_data:
                if pos.get('owner') == payment_cred:
                    staked = pos.get('stakedIndy', 0) / 1_000_000

                    # lockedAmount can be a dict or int
                    locked_raw = pos.get('lockedAmount', 0)
                    if isinstance(locked_raw, dict):
                        locked = sum(
                            v for v in locked_raw.values()
                            if isinstance(v, (int, float))
                        ) / 1_000_000
                    else:
                        locked = locked_raw / 1_000_000

                    ada_snapshot = pos.get('snapshotAda', 0) / 1_000_000

                    total_staked += staked
                    total_locked += locked
                    snapshot_ada += ada_snapshot

                    logger.info(
                        f"Indigo position: staked={staked:.2f}, "
                        f"locked={locked:.2f}, snapshotAda={ada_snapshot:.2f}"
                    )

            # snapshotAda is the ADA backing/collateral value, not pending rewards.
            # Actual pending rewards require epoch-based calculation not available via this API.
            pending_indy = max(0, total_locked - total_staked) if total_locked > 0 else 0

            return {
                'protocol': 'Indigo',
                'pending_indy': pending_indy,
                'pending_ada': 0,  # ADA rewards need to be checked in app
                'total_staked': total_staked,
                'ada_backing': snapshot_ada,
                'reward_tokens': ['INDY', 'ADA'],
                'rewards_url': 'https://app.indigoprotocol.io/earn'
            }

        except Exception as e:
            logger.error(f"Error fetching Indigo rewards: {e}")
            return None

    async def get_cdp_positions(self, address: str) -> Optional[Dict]:
        """Get CDP positions for an address.

        Standalone method for the legacy DeFiService integration.

        Returns:
            Dict with CDP position data or None
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)
            response = await client.get(f"{INDIGO_API_BASE}/api/v1/loans")

            if response.status_code != 200:
                logger.error(f"Indigo loans API error: {response.status_code}")
                return None

            loans = response.json()
            user_cdps = []
            total_collateral_ada = 0

            for loan in loans:
                if loan.get('owner') != payment_cred:
                    continue

                asset = loan.get('asset', 'iUSD')
                collateral_lovelace = loan.get('collateral', 0)
                minted_raw = loan.get('minted', 0)

                collateral_ada = parseFloat(collateral_lovelace) / 1_000_000
                decimals = IASSET_DECIMALS.get(asset, 6)
                minted_amount = parseFloat(minted_raw) / (10 ** decimals)

                if collateral_ada <= 0 and minted_amount <= 0:
                    continue

                total_collateral_ada += collateral_ada

                user_cdps.append({
                    'asset': asset,
                    'collateral_ada': collateral_ada,
                    'minted_amount': minted_amount,
                    'min_collateral_ratio': MIN_COLLATERAL_RATIO.get(asset, 150),
                })

            if not user_cdps:
                return None

            return {
                'protocol': 'Indigo',
                'address': address,
                'cdps': user_cdps,
                'total_collateral_ada': total_collateral_ada,
                'cdp_count': len(user_cdps),
            }

        except Exception as e:
            logger.error(f"Error getting Indigo CDPs: {e}")
            return None

    async def get_stability_pool_positions(self, address: str) -> Optional[Dict]:
        """Get Stability Pool positions for an address.

        Standalone method for the legacy DeFiService integration.

        Returns:
            Dict with stability pool data or None
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/stability-pools/accounts"
            )

            if response.status_code != 200:
                logger.error(
                    f"Indigo stability pools API error: {response.status_code}"
                )
                return None

            accounts = response.json()
            deposits_by_asset = {}

            for acct in accounts:
                if acct.get('owner') != payment_cred:
                    continue

                asset = acct.get('asset', 'iUSD')
                snapshot_d = acct.get('snapshotD', '0')

                try:
                    deposit_scaled = parseFloat(snapshot_d)
                except (ValueError, TypeError):
                    deposit_scaled = 0

                if deposit_scaled <= 0:
                    continue

                decimals = IASSET_DECIMALS.get(asset, 6)
                deposit_amount = deposit_scaled / (10 ** 18) / (10 ** decimals)

                if deposit_amount < 0.000001:
                    continue

                if asset not in deposits_by_asset:
                    deposits_by_asset[asset] = {
                        'deposited': 0,
                        'position_count': 0,
                    }

                deposits_by_asset[asset]['deposited'] += deposit_amount
                deposits_by_asset[asset]['position_count'] += 1

            if not deposits_by_asset:
                return None

            sp_positions = []
            for asset, data in deposits_by_asset.items():
                sp_positions.append({
                    'asset': asset,
                    'deposited': data['deposited'],
                    'position_count': data['position_count'],
                })

            return {
                'protocol': 'Indigo',
                'address': address,
                'stability_pool': sp_positions,
                'pool_count': len(sp_positions),
            }

        except Exception as e:
            logger.error(f"Error getting Indigo Stability Pool: {e}")
            return None

    async def get_apy(self) -> Optional[float]:
        """Fetch current Indigo staking APY from protocol stats."""
        try:
            client = get_client("blockfrost", timeout=15.0)
            response = await client.get(f"{INDIGO_API_BASE}/api/v1/protocol/stats")
            if response.status_code == 200:
                stats = response.json()
                return stats.get('stakingApy', stats.get('apy'))
        except Exception as e:
            logger.warning(f"Could not fetch Indigo APY: {e}")
        return None


def parseFloat(value) -> float:
    """Safely parse a numeric value that may be int, float, or string."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
