"""Marinade Finance adapter - mSOL liquid staking."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class MarinadeAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Marinade"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://marinade.finance"

    MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        balance = await self._get_spl_balance(address, self.MSOL_MINT)
        if balance and balance > 0:
            return [ProtocolPosition(
                protocol="Marinade",
                chain="solana",
                position_type=PositionType.LIQUID_STAKING,
                token_symbol="mSOL",
                token_name="Marinade Staked SOL",
                amount=balance,
                contract_address=self.MSOL_MINT,
            )]
        return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(MarinadeAdapter())
