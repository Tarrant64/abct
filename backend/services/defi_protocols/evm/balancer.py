"""
Balancer Protocol Adapter

Detects staked LP positions via Balancer gauge contracts.
- Gauge.balanceOf(address) for staked BPT (Balancer Pool Tokens)
  Selector: 0x70a08231 (standard ERC-20 balanceOf)

Enriched: Also queries claimable_tokens(address) on gauges for accrued BAL rewards,
and expanded gauge coverage.
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

# Popular Balancer gauge contracts: {chain: {pool_name: gauge_address}}
BALANCER_GAUGES = {
    "ethereum": {
        "wstETH-WETH": "0x5C0F23A5c1be65Fa710d385814a7Fd1Bda480b1C",
        "rETH-WETH": "0x79eF6103A513951a3b25743DB509E267685726B7",
        "BAL-WETH-80/20": "0x68d019f64A7aa97e2D4e7363AEE42251D08124Fb",
        "GHO-USDT-USDC": "0xBc02E3D3FBf5f24E79aa8B1B3B51F33b4F99BAdC",
        "wstETH-sfrxETH-rETH": "0x5F032510B3C9ec5B1a0D8a5e3E53D9a4e6F4Aa38",
        "WETH-AURA": "0x275dF57d2B23d53e20322b4bb71Bf1dCb21D0A00",
        "GHO-USDC-USDT": "0xBc02E3D3FBf5f24E79aa8B1B3B51F33b4F99BAdC",
    },
    "arbitrum": {
        "wstETH-WETH": "0xa14453084318277b11D38FbE05D857A4f647442B",
        "RDNT-WETH": "0xcf9f895296F5e1D66a7EE4F3b8726Dc2B2F60CCf",
        "rETH-WETH": "0x8135d6AbFd42707A87A7b94c5CFA3529f9b432AD",
        "USDC-DAI-USDT": "0x0052688295413b32626D226a205b95cDB337DE86",
    },
    "polygon": {
        "MaticX-WMATIC": "0x4B6e54F59616cBF3457E2c4B9C4E68a29098F1B0",
        "stMATIC-WMATIC": "0x4C88B6bCf19e8e0A79bfa1B27Fa78ceE5a58Bb8f",
        "WETH-BAL": "0xFeBab87Cd0f5eE5ed2c0fd2FF2A2C16f16e3FDB1",
    },
    "base": {
        "cbETH-WETH": "0xC66Fc6568F91066B93b9E94b1dEe52a1Fb5e5D5D",
    },
}

# claimable_tokens(address) selector — returns accrued BAL
CLAIMABLE_TOKENS = "0xd294f093"
# BAL token decimals
BAL_DECIMALS = 18
BPT_DECIMALS = 18


class BalancerAdapter(BaseEVMAdapter):
    """Balancer adapter - detects staked BPT positions via gauges with BAL rewards."""

    PROTOCOL_NAME = "Balancer"
    SUPPORTED_CHAINS = list(BALANCER_GAUGES.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://balancer.fi"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            gauges = BALANCER_GAUGES.get(c, {})
            if not gauges:
                continue

            gauge_list = list(gauges.items())
            balance_tasks = [
                self._get_erc20_balance(c, gauge_addr, address)
                for _, gauge_addr in gauge_list
            ]
            reward_tasks = [
                self._get_claimable_bal(c, gauge_addr, address)
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
                bal_reward = rewards[i] if not isinstance(rewards[i], Exception) else 0.0

                if balance and balance > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LP_POSITION,
                        token_symbol=f"BPT-{pool_name}",
                        token_name=f"Balancer {pool_name}",
                        amount=balance / (10 ** BPT_DECIMALS),
                        contract_address=gauge_addr,
                        pending_rewards=bal_reward if bal_reward > 0 else None,
                        reward_token="BAL" if bal_reward > 0 else None,
                        extra={
                            "pool_name": pool_name,
                            "gauge_address": gauge_addr,
                        },
                    ))

        return positions

    async def _get_claimable_bal(
        self, chain: str, gauge_addr: str, address: str
    ) -> float:
        """Call claimable_tokens(address) on a gauge to get accrued BAL.

        Returns BAL amount in human-readable units, or 0 if unavailable.
        """
        data = CLAIMABLE_TOKENS + self._encode_address(address)
        result = await self._eth_call(chain, gauge_addr, data)
        if not result or result == "0x":
            return 0.0

        try:
            raw = int(result, 16)
            if raw > 0:
                return raw / (10 ** BAL_DECIMALS)
        except (ValueError, TypeError):
            pass

        return 0.0


protocol_registry.register(BalancerAdapter())
