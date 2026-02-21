"""BlazeStake adapter - bSOL liquid staking."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class BlazeStakeAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "BlazeStake"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://stake.solblaze.org"

    BSOL_MINT = "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        balance = await self._get_spl_balance(address, self.BSOL_MINT)
        if balance and balance > 0:
            return [ProtocolPosition(
                protocol="BlazeStake",
                chain="solana",
                position_type=PositionType.LIQUID_STAKING,
                token_symbol="bSOL",
                token_name="BlazeStake Staked SOL",
                amount=balance,
                contract_address=self.BSOL_MINT,
            )]
        return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(BlazeStakeAdapter())
