"""
Abracadabra Money Adapter

Detects borrowing positions (cauldrons) where users deposit collateral and borrow MIM.
Also detects SPELL staking (sSPELL).

Detection method:
- Check sSPELL (staked SPELL) token balance
- Check MIM (Magic Internet Money) token balance as indicator of protocol use

sSPELL: 0x26FA3fFFB6EfE8c1E69103aCb4044C26B9A106a9 (Ethereum)
MIM: 0x99D8a9C45b2ecA8864373A26D1459e3Dff1e17F3 (Ethereum)
SPELL: 0x090185f2135308BaD17527004364eBcC2D37e5F
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

# sSPELL staking contract addresses
SSPELL_CONTRACTS = {
    "ethereum": "0x26FA3fFFB6EfE8c1E69103aCb4044C26B9A106a9",
}

# MIM stablecoin addresses
MIM_TOKENS = {
    "ethereum": "0x99D8a9C45b2ecA8864373A26D1459e3Dff1e17F3",
    "arbitrum": "0xFEa7a6a0B346362BF88Cf9a383880eFeB0E3324",
    "avalanche": "0x130966628846BFd36ff31a822705796e8cb8C18D",
}

# SPELL token addresses
SPELL_TOKENS = {
    "ethereum": "0x090185f2135308BaD17527004364eBcC2D37e5F",
    "arbitrum": "0x3E6648C5a70A150A88bCE65F4aD4d506Fe15d2AF",
}


class AbracadabraAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Abracadabra"
    SUPPORTED_CHAINS = list(set(list(SSPELL_CONTRACTS.keys()) + list(MIM_TOKENS.keys()) + list(SPELL_TOKENS.keys())))
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://abracadabra.money"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        async def _check_sspell(c: str):
            contract = SSPELL_CONTRACTS.get(c)
            if not contract:
                return None
            try:
                raw = await self._get_erc20_balance(c, contract, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="sSPELL",
                        token_name="Staked SPELL",
                        amount=raw / 1e18,
                        contract_address=contract,
                    )
            except Exception as e:
                logger.debug(f"Abracadabra sSPELL check error on {c}: {e}")
            return None

        async def _check_mim(c: str):
            token = MIM_TOKENS.get(c)
            if not token:
                return None
            try:
                raw = await self._get_erc20_balance(c, token, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_BORROW,
                        token_symbol="MIM",
                        token_name="Magic Internet Money",
                        amount=raw / 1e18,
                        contract_address=token,
                        extra={"note": "MIM balance — may represent borrowed position"},
                    )
            except Exception as e:
                logger.debug(f"Abracadabra MIM check error on {c}: {e}")
            return None

        async def _check_spell(c: str):
            token = SPELL_TOKENS.get(c)
            if not token:
                return None
            try:
                raw = await self._get_erc20_balance(c, token, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="SPELL",
                        token_name="Spell Token",
                        amount=raw / 1e18,
                        contract_address=token,
                    )
            except Exception as e:
                logger.debug(f"Abracadabra SPELL check error on {c}: {e}")
            return None

        tasks = (
            [_check_sspell(c) for c in chains]
            + [_check_mim(c) for c in chains]
            + [_check_spell(c) for c in chains]
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


protocol_registry.register(AbracadabraAdapter())
