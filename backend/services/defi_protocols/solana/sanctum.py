"""Sanctum adapter - INF (Infinity) liquid staking aggregator."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class SanctumAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Sanctum"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://sanctum.so"

    INF_MINT = "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        balance = await self._get_spl_balance(address, self.INF_MINT)
        if balance and balance > 0:
            return [ProtocolPosition(
                protocol="Sanctum",
                chain="solana",
                position_type=PositionType.LIQUID_STAKING,
                token_symbol="INF",
                token_name="Sanctum Infinity",
                amount=balance,
                contract_address=self.INF_MINT,
            )]
        return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(SanctumAdapter())
