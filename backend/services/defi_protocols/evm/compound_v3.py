"""
Compound v3 (Comet) Protocol Adapter

Detects lending/borrowing positions via:
- balanceOf(address) for supply balance (selector: 0x70a08231)
- borrowBalanceOf(address) for borrow balance (selector: 0x374c49b4)

Enriched: Also fetches accrued COMP rewards via CometRewards.getRewardOwed().
Each Comet market is a separate contract (e.g., cUSDCv3, cWETHv3).
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

# Compound v3 Comet contracts: {chain: {market_name: address}}
COMPOUND_V3_MARKETS = {
    "ethereum": {
        "cUSDCv3": "0xc3d688B66703497DAA19211EEdff47f25384cdc3",
        "cWETHv3": "0xA17581A9E3356d9A858b789D68B4d866e593aE94",
        "cUSDTv3": "0x3Afdc9BCA9213A35503b077a6072F3D0d5AB0840",
    },
    "polygon": {
        "cUSDCv3": "0xF25212E676D1F7F89Cd72fFEe66158f541246445",
    },
    "arbitrum": {
        "cUSDCv3": "0xA5EDBDD9646f8dFF606d7448e414884C7d905dCA",
        "cUSDC.ev3": "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf",
    },
    "base": {
        "cUSDCv3": "0xb125E6687d4313864e53df431d5425969c15Eb2F",
        "cUSDbCv3": "0x46e6b214b524310239732D51387075E0e70970bf",
        "cWETHv3": "0x46e6b214b524310239732D51387075E0e70970bf",
    },
}

# CometRewards contract addresses per chain
COMET_REWARDS = {
    "ethereum": "0x1B0e765F6224C21223AeA2af16c1C46E38885a40",
    "polygon": "0x45939657d1CA34A8FA39A924B71D28Fe8431e581",
    "arbitrum": "0x88730d254A2f7e6AC8388c3198aFd694bA9f7fae",
    "base": "0x123964802e6ABabBE1Bc9547D72Ef1B69B00A6b1",
}

# Market base token decimals
MARKET_DECIMALS = {
    "cUSDCv3": 6,
    "cUSDC.ev3": 6,
    "cUSDbCv3": 6,
    "cUSDTv3": 6,
    "cWETHv3": 18,
}

# Market underlying symbol
MARKET_SYMBOLS = {
    "cUSDCv3": "USDC",
    "cUSDC.ev3": "USDC",
    "cUSDbCv3": "USDbC",
    "cUSDTv3": "USDT",
    "cWETHv3": "WETH",
}

# borrowBalanceOf(address) selector
BORROW_BALANCE_OF = "0x374c49b4"
# getRewardOwed(address comet, address account) selector
GET_REWARD_OWED = "0x70ddd2c8"
# COMP token decimals
COMP_DECIMALS = 18


class CompoundV3Adapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Compound v3"
    SUPPORTED_CHAINS = list(COMPOUND_V3_MARKETS.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://compound.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            markets = COMPOUND_V3_MARKETS.get(c, {})
            if not markets:
                continue

            for market_name, contract in markets.items():
                decimals = MARKET_DECIMALS.get(market_name, 6)
                underlying = MARKET_SYMBOLS.get(market_name, market_name)

                # Check supply, borrow, and rewards in parallel
                supply_balance, borrow_balance, comp_reward = await asyncio.gather(
                    self._get_erc20_balance(c, contract, address),
                    self._get_borrow_balance(c, contract, address),
                    self._get_comp_rewards(c, contract, address),
                )

                if supply_balance and supply_balance > 0:
                    amount = supply_balance / (10 ** decimals)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol=market_name,
                        token_name=f"Compound {underlying} Supply",
                        amount=amount,
                        contract_address=contract,
                        pending_rewards=comp_reward if comp_reward > 0 else None,
                        reward_token="COMP" if comp_reward > 0 else None,
                        extra={
                            "underlying_token": underlying,
                        },
                    ))

                if borrow_balance and borrow_balance > 0:
                    amount = borrow_balance / (10 ** decimals)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_BORROW,
                        token_symbol=f"{market_name}-DEBT",
                        token_name=f"Compound {underlying} Borrow",
                        amount=amount,
                        contract_address=contract,
                        extra={
                            "underlying_token": underlying,
                        },
                    ))

        return positions

    async def _get_borrow_balance(
        self, chain: str, contract: str, address: str
    ) -> int:
        """Call borrowBalanceOf(address) on a Comet contract."""
        data = BORROW_BALANCE_OF + self._encode_address(address)
        result = await self._eth_call(chain, contract, data)
        if result and result != "0x":
            try:
                return int(result, 16)
            except ValueError:
                pass
        return 0

    async def _get_comp_rewards(
        self, chain: str, comet: str, address: str
    ) -> float:
        """Fetch accrued COMP rewards from CometRewards.getRewardOwed(comet, account).

        Returns rewards in COMP (human-readable), or 0 if unavailable.
        """
        rewards_contract = COMET_REWARDS.get(chain)
        if not rewards_contract:
            return 0.0

        # getRewardOwed(address comet, address account)
        data = GET_REWARD_OWED + self._encode_address(comet) + self._encode_address(address)
        result = await self._eth_call(chain, rewards_contract, data)
        if not result or result == "0x" or len(result) < 130:
            return 0.0

        try:
            # Returns (address token, uint owed) — owed is at offset 1
            owed_raw = self._decode_uint256(result, 1)
            if owed_raw > 0:
                return owed_raw / (10 ** COMP_DECIMALS)
        except Exception as e:
            logger.debug(f"Error decoding COMP rewards on {chain}: {e}")

        return 0.0


protocol_registry.register(CompoundV3Adapter())
