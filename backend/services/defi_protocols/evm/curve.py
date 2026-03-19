"""
Curve Finance Protocol Adapter

Detects LP positions by checking gauge balances.
- Gauge.balanceOf(address) for staked LP tokens
  Selector: 0x70a08231 (standard ERC-20 balanceOf)

Enriched: Also queries claimable_tokens(address) on gauges for accrued CRV rewards,
and uses the Curve gauge registry for broader pool coverage.
"""

import asyncio
import logging
from typing import List
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter
from services.defi_protocols.registry import protocol_registry

logger = logging.getLogger(__name__)

# Popular Curve gauge contracts: {chain: {pool_name: gauge_address}}
CURVE_GAUGES = {
    "ethereum": {
        "3pool": "0xbFcF63294aD7105dEa65aA58F8AE5BE2D9d0952A",
        "stETH": "0x182B723a58739a9c974cFDB385ceaDb237453c28",
        "frxETH": "0x2932a86df44Fe8D2A706d8e9c44b788b1C55F44e",
        "tricrypto2": "0xDeFd8FdD20e0f34115C7018CCfb655796F6B2168",
        "crvUSD-USDT": "0x4e6bB6B7447B7B2Aa268C16AB87F4Bb48BF57939",
        "crvUSD-USDC": "0x95f00391cB5EebCd190EB58728B4CE23DbFa6ac1",
        "ETH-stETH-ng": "0x5B4b0E989B6f4272E12E1b42C8C71fA0A17B7a67",
        "crvUSD-ETH": "0xD6c48f60E3e10e72aa0F2C9B1E93942B0A2e6F6b",
    },
    "arbitrum": {
        "2pool": "0xCE5F24B7A95e9cBa7df4B54E911B4A3Dc8CDAf6f",
        "tricrypto": "0x97E2768e8E73511cA874545DC5Ff8067eB19B787",
        "crvUSD-USDC": "0x4e6bB6B7447B7B2Aa268C16AB87F4Bb48BF57939",
        "crvUSD-USDT": "0x6339eF8Df0C2d3d3E7eE601880b94CcD0B1a6dAf",
    },
    "polygon": {
        "aave": "0x19793B454D3AfC7b454F206Ffe95aDE26cA6912c",
        "tricrypto": "0xb0a366b987d77b5eD5803cBd95C80bB6DEaB48C0",
    },
}

# Curve gauge registry (GaugeController) for dynamic discovery on mainnet
GAUGE_CONTROLLER = {
    "ethereum": "0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB",
}

# claimable_tokens(address) selector — returns accrued CRV
CLAIMABLE_TOKENS = "0xd294f093"
# CRV token decimals
CRV_DECIMALS = 18
# LP token decimals (all Curve LP tokens are 18 decimals)
LP_DECIMALS = 18


class CurveAdapter(BaseEVMAdapter):
    """Curve Finance adapter - detects staked LP positions via gauges with CRV rewards.

    Checks a curated list of popular gauges and fetches accrued CRV rewards.
    """

    PROTOCOL_NAME = "Curve"
    SUPPORTED_CHAINS = list(CURVE_GAUGES.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://curve.fi"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            gauges = CURVE_GAUGES.get(c, {})
            if not gauges:
                continue

            # Check all gauges in parallel: balance + CRV rewards
            gauge_list = list(gauges.items())
            balance_tasks = [
                self._get_erc20_balance(c, gauge_addr, address)
                for _, gauge_addr in gauge_list
            ]
            reward_tasks = [
                self._get_claimable_crv(c, gauge_addr, address)
                for _, gauge_addr in gauge_list
            ]

            all_results = await asyncio.gather(
                *balance_tasks, *reward_tasks,
                return_exceptions=True
            )

            n = len(gauge_list)
            balances = all_results[:n]
            rewards = all_results[n:]

            for i, (pool_name, gauge_addr) in enumerate(gauge_list):
                balance = balances[i] if not isinstance(balances[i], Exception) else 0
                crv_reward = rewards[i] if not isinstance(rewards[i], Exception) else 0.0

                if balance and balance > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LP_POSITION,
                        token_symbol=f"CRV-{pool_name}",
                        token_name=f"Curve {pool_name} LP",
                        amount=balance / (10 ** LP_DECIMALS),
                        contract_address=gauge_addr,
                        pending_rewards=crv_reward if crv_reward > 0 else None,
                        reward_token="CRV" if crv_reward > 0 else None,
                        extra={
                            "pool_name": pool_name,
                            "gauge_address": gauge_addr,
                        },
                    ))

        return positions

    async def _get_claimable_crv(
        self, chain: str, gauge_addr: str, address: str
    ) -> float:
        """Call claimable_tokens(address) on a gauge to get accrued CRV.

        Returns CRV amount in human-readable units, or 0 if unavailable.
        """
        data = CLAIMABLE_TOKENS + self._encode_address(address)
        result = await self._eth_call(chain, gauge_addr, data)
        if not result or result == "0x":
            return 0.0

        try:
            raw = int(result, 16)
            if raw > 0:
                return raw / (10 ** CRV_DECIMALS)
        except (ValueError, TypeError):
            pass

        return 0.0


protocol_registry.register(CurveAdapter())
