import httpx
from typing import Optional
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Cosmos LCD REST API (free, no key required)
COSMOS_LCD_BASE_URL = "https://cosmos-rest.publicnode.com"

# 1 ATOM = 1,000,000 uatom
UATOM_DECIMALS = 6
UATOM_DIVISOR = 10 ** UATOM_DECIMALS


class CosmosService:
    """Service for fetching Cosmos Hub (ATOM) wallet data using the LCD REST API."""

    def __init__(self):
        self.base_url = COSMOS_LCD_BASE_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if an address looks like a valid Cosmos Hub address."""
        return (
            isinstance(address, str)
            and address.startswith("cosmos1")
            and len(address) >= 39
        )

    def _uatom_to_atom(self, uatom: str) -> float:
        """Convert a uatom string amount to ATOM float."""
        try:
            return int(uatom) / UATOM_DIVISOR
        except (ValueError, TypeError):
            return 0.0

    async def _get_balances(self, address: str) -> Optional[list]:
        """
        Fetch bank balances for an address.

        GET /cosmos/bank/v1beta1/balances/{address}
        Returns list of {"denom": "uatom", "amount": "1234567"} objects.
        """
        try:
            client = get_client("cosmos_lcd", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/cosmos/bank/v1beta1/balances/{address}",
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Cosmos LCD balances error: {response.status_code} - {response.text[:200]}")
                return None

            data = response.json()
            return data.get("balances", [])

        except httpx.TimeoutException:
            logger.error(f"Cosmos LCD timeout fetching balances for {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Cosmos LCD balances error: {e}")
            return None

    async def _get_delegations(self, address: str) -> Optional[list]:
        """
        Fetch staking delegations for an address.

        GET /cosmos/staking/v1beta1/delegations/{address}
        Returns list of delegation_response objects with balance info.
        """
        try:
            client = get_client("cosmos_lcd", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/cosmos/staking/v1beta1/delegations/{address}",
                timeout=30.0,
            )

            if response.status_code == 404:
                # No delegations
                return []

            if response.status_code != 200:
                logger.error(f"Cosmos LCD delegations error: {response.status_code} - {response.text[:200]}")
                return None

            data = response.json()
            return data.get("delegation_responses", [])

        except httpx.TimeoutException:
            logger.error(f"Cosmos LCD timeout fetching delegations for {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Cosmos LCD delegations error: {e}")
            return None

    async def _get_rewards(self, address: str) -> Optional[dict]:
        """
        Fetch pending staking rewards for an address.

        GET /cosmos/distribution/v1beta1/delegators/{address}/rewards
        Returns total rewards and per-validator breakdown.
        """
        try:
            client = get_client("cosmos_lcd", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/cosmos/distribution/v1beta1/delegators/{address}/rewards",
                timeout=30.0,
            )

            if response.status_code == 404:
                # No rewards
                return {"rewards": [], "total": []}

            if response.status_code != 200:
                logger.error(f"Cosmos LCD rewards error: {response.status_code} - {response.text[:200]}")
                return None

            return response.json()

        except httpx.TimeoutException:
            logger.error(f"Cosmos LCD timeout fetching rewards for {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Cosmos LCD rewards error: {e}")
            return None

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get comprehensive address information including balance, staking, and rewards.

        Args:
            address: A Cosmos Hub address starting with "cosmos1".

        Returns:
            Dict with balance_atom, delegated_atom, pending_rewards_atom,
            tokens list, and metadata. Returns None on errors.
        """
        if not self._is_valid_address(address):
            logger.error(f"Invalid Cosmos address: {address}")
            return None

        try:
            # Fetch balances, delegations, and rewards in parallel
            import asyncio
            balances_result, delegations_result, rewards_result = await asyncio.gather(
                self._get_balances(address),
                self._get_delegations(address),
                self._get_rewards(address),
                return_exceptions=True,
            )

            # Handle exceptions from gather
            if isinstance(balances_result, Exception):
                logger.error(f"Cosmos balances gather error: {balances_result}")
                balances_result = None
            if isinstance(delegations_result, Exception):
                logger.error(f"Cosmos delegations gather error: {delegations_result}")
                delegations_result = None
            if isinstance(rewards_result, Exception):
                logger.error(f"Cosmos rewards gather error: {rewards_result}")
                rewards_result = None

            # If we couldn't even get balances, fail
            if balances_result is None:
                return None

            # --- Parse bank balances ---
            balance_atom = 0.0
            tokens = []

            for bal in balances_result:
                denom = bal.get("denom", "")
                amount_raw = bal.get("amount", "0")

                if denom == "uatom":
                    balance_atom = self._uatom_to_atom(amount_raw)
                    tokens.append({
                        "denom": "uatom",
                        "symbol": "ATOM",
                        "amount_raw": amount_raw,
                        "amount": balance_atom,
                        "decimals": UATOM_DECIMALS,
                    })
                else:
                    # IBC tokens or other denoms — store raw
                    # IBC denoms look like "ibc/27394FB092D2ECCD56123..."
                    try:
                        amount_val = int(amount_raw)
                    except (ValueError, TypeError):
                        amount_val = 0

                    tokens.append({
                        "denom": denom,
                        "symbol": denom[:20] if len(denom) > 20 else denom,
                        "amount_raw": amount_raw,
                        "amount": amount_val,
                        "decimals": None,  # Unknown for IBC tokens
                    })

            # --- Parse staking delegations ---
            delegated_atom = 0.0
            delegations = []

            if delegations_result:
                for deleg in delegations_result:
                    balance_info = deleg.get("balance", {})
                    deleg_denom = balance_info.get("denom", "")
                    deleg_amount_raw = balance_info.get("amount", "0")

                    if deleg_denom == "uatom":
                        deleg_atom = self._uatom_to_atom(deleg_amount_raw)
                        delegated_atom += deleg_atom

                    delegation_info = deleg.get("delegation", {})
                    validator_address = delegation_info.get("validator_address", "")

                    delegations.append({
                        "validator": validator_address,
                        "amount_raw": deleg_amount_raw,
                        "amount_atom": self._uatom_to_atom(deleg_amount_raw),
                        "denom": deleg_denom,
                    })

            # --- Parse pending rewards ---
            pending_rewards_atom = 0.0

            if rewards_result:
                total_rewards = rewards_result.get("total", [])
                for reward in total_rewards:
                    if reward.get("denom") == "uatom":
                        # Rewards can have decimal amounts (e.g. "123456.789")
                        try:
                            pending_rewards_atom = float(reward.get("amount", "0")) / UATOM_DIVISOR
                        except (ValueError, TypeError):
                            pending_rewards_atom = 0.0

            return {
                "address": address,
                "balance_atom": balance_atom,
                "delegated_atom": delegated_atom,
                "pending_rewards_atom": round(pending_rewards_atom, 6),
                "tokens": tokens,
                "delegations": delegations,
                "blockchain": "cosmos",
                "source": "cosmos_lcd",
            }

        except Exception as e:
            logger.error(f"Cosmos get_address_info error for {address[:20]}...: {e}")
            return None


# Singleton instance
cosmos_service = CosmosService()
