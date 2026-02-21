"""
Balancer Protocol Adapter

Detects staked LP positions via Balancer gauge contracts.
- Gauge.balanceOf(address) for staked BPT (Balancer Pool Tokens)
  Selector: 0x70a08231 (standard ERC-20 balanceOf)

This adapter checks popular Balancer gauges. Full coverage would require
querying the Balancer gauge registry or subgraph.
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
    },
    "arbitrum": {
        "wstETH-WETH": "0xa14453084318277b11D38FbE05D857A4f647442B",
        "RDNT-WETH": "0xcf9f895296F5e1D66a7EE4F3b8726Dc2B2F60CCf",
    },
    "polygon": {
        "MaticX-WMATIC": "0x4B6e54F59616cBF3457E2c4B9C4E68a29098F1B0",
        "stMATIC-WMATIC": "0x4C88B6bCf19e8e0A79bfa1B27Fa78ceE5a58Bb8f",
    },
}

BPT_DECIMALS = 18


class BalancerAdapter(BaseEVMAdapter):
    """Balancer adapter - detects staked BPT positions via gauges.

    NOTE: This checks a curated list of popular gauges. For full coverage,
    the Balancer subgraph should be queried.
    """

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
            results = await asyncio.gather(
                *[
                    self._get_erc20_balance(c, gauge_addr, address)
                    for _, gauge_addr in gauge_list
                ]
            )

            for (pool_name, gauge_addr), balance in zip(gauge_list, results):
                if balance and balance > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LP_POSITION,
                        token_symbol=f"BPT-{pool_name}",
                        amount=balance / (10 ** BPT_DECIMALS),
                        contract_address=gauge_addr,
                    ))

        return positions


protocol_registry.register(BalancerAdapter())
