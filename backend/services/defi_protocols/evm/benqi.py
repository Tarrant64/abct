"""
Benqi Finance Adapter (Avalanche)

Benqi is a Compound v2 fork on Avalanche.
Detection via Comptroller.getAssetsIn(address) + qiToken.balanceOf/borrowBalanceCurrent.

Comptroller: 0x486Af39519B4Dc9a7fCcd318217352830E8AD9b4

qiToken addresses on Avalanche:
- qiAVAX:  0x5C0401e81Bc07Ca70fAD469b451682c0d747Ef1c
- qiUSDC:  0xBEb5d47A3f720Ec0a390d04b4d41ED7d9688bC7F
- qiUSDT:  0xc9e5999b8e75C3fEB117F6f73E664b9f3C8ca65a
- qiETH:   0x334AD834Cd4481BB02d09615E7c11a00579A7909
- qiBTC:   0xe194c4c5aC32a3C9ffDb358d9Bfd523a0B6d1568
"""

import asyncio
import logging
from typing import List, Optional
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter
from services.defi_protocols.registry import protocol_registry

logger = logging.getLogger(__name__)

CHAIN = "avalanche"
COMPTROLLER = "0x486Af39519B4Dc9a7fCcd318217352830E8AD9b4"

QI_TOKENS = [
    {"address": "0x5C0401e81Bc07Ca70fAD469b451682c0d747Ef1c", "symbol": "qiAVAX", "underlying": "AVAX", "decimals": 8},
    {"address": "0xBEb5d47A3f720Ec0a390d04b4d41ED7d9688bC7F", "symbol": "qiUSDC", "underlying": "USDC", "decimals": 8},
    {"address": "0xc9e5999b8e75C3fEB117F6f73E664b9f3C8ca65a", "symbol": "qiUSDT", "underlying": "USDT", "decimals": 8},
    {"address": "0x334AD834Cd4481BB02d09615E7c11a00579A7909", "symbol": "qiETH", "underlying": "ETH", "decimals": 8},
    {"address": "0xe194c4c5aC32a3C9ffDb358d9Bfd523a0B6d1568", "symbol": "qiBTC", "underlying": "BTC", "decimals": 8},
]

# balanceOf(address) selector
BALANCE_OF = "0x70a08231"
# borrowBalanceCurrent(address) selector: 0x17bfdfbc
BORROW_BALANCE_CURRENT = "0x17bfdfbc"


class BenqiAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Benqi"
    SUPPORTED_CHAINS = [CHAIN]
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://benqi.fi"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        if chain and chain != CHAIN:
            return positions

        async def _check_token(token_info: dict) -> List[Optional[ProtocolPosition]]:
            results = []
            encoded = self._encode_address(address)
            try:
                # Check supply balance (qiToken balance)
                supply_raw = await self._get_erc20_balance(CHAIN, token_info["address"], address)
                if supply_raw and supply_raw > 0:
                    amount = supply_raw / (10 ** token_info["decimals"])
                    results.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=CHAIN,
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol=token_info["symbol"],
                        token_name=f"Benqi {token_info['underlying']} Supply",
                        amount=amount,
                        contract_address=token_info["address"],
                        extra={"underlying": token_info["underlying"]},
                    ))

                # Check borrow balance
                borrow_result = await self._eth_call(CHAIN, token_info["address"], f"{BORROW_BALANCE_CURRENT}{encoded}")
                if borrow_result and borrow_result != "0x":
                    borrow_raw = self._decode_uint256(borrow_result, 0)
                    if borrow_raw > 0:
                        borrow_amount = borrow_raw / (10 ** token_info["decimals"])
                        results.append(ProtocolPosition(
                            protocol=self.PROTOCOL_NAME,
                            chain=CHAIN,
                            position_type=PositionType.LENDING_BORROW,
                            token_symbol=f"{token_info['symbol']}-DEBT",
                            token_name=f"Benqi {token_info['underlying']} Borrow",
                            amount=borrow_amount,
                            contract_address=token_info["address"],
                            extra={"underlying": token_info["underlying"]},
                        ))
            except Exception as e:
                logger.debug(f"Benqi check error for {token_info['symbol']}: {e}")
            return results

        all_results = await asyncio.gather(*[_check_token(t) for t in QI_TOKENS], return_exceptions=True)
        for result in all_results:
            if isinstance(result, list):
                positions.extend(result)

        return positions


protocol_registry.register(BenqiAdapter())
