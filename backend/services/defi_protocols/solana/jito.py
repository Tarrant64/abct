"""Jito adapter - jitoSOL liquid staking."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class JitoAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Jito"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://www.jito.network"

    JITOSOL_MINT = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        balance = await self._get_spl_balance(address, self.JITOSOL_MINT)
        if balance and balance > 0:
            return [ProtocolPosition(
                protocol="Jito",
                chain="solana",
                position_type=PositionType.LIQUID_STAKING,
                token_symbol="jitoSOL",
                token_name="Jito Staked SOL",
                amount=balance,
                contract_address=self.JITOSOL_MINT,
            )]
        return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(JitoAdapter())
