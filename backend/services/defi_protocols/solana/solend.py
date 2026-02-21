"""Solend adapter - cToken lending supply detection."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class SolendAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Solend"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://solend.fi"

    # cToken mints for main pool reserves
    CTOKENS = {
        "cSOL": ("5h6ssFpeDeRbzsEHcTNtSq7J3HMGY6bExK4xksMaXspr", "SOL"),
        "cUSDC": ("993dVFL2uXWYeoXuEBFXR4BijeXdTv4s6BzsCjJZuwqk", "USDC"),
        "cUSDT": ("BTsbZDV7aCMRJ3VNy9ygV4Q2UeEo9GpR8wre1hFMZEiL", "USDT"),
        "cETH": ("MdExmPxCYyEMFLqJTGnRJFxCBuMxSGGfFKVZkMVcZ2K", "ETH"),
        "cBTC": ("3JFC4cB56Er45nWVe29Bhnn5GnwQzSmHVf6eUq9ac91h", "BTC"),
    }

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        positions = []
        for ctoken_symbol, (mint, underlying_symbol) in self.CTOKENS.items():
            balance = await self._get_spl_balance(address, mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Solend",
                    chain="solana",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=ctoken_symbol,
                    token_name=f"Solend {underlying_symbol} Supply",
                    amount=balance,
                    contract_address=mint,
                    extra={"underlying_symbol": underlying_symbol},
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(SolendAdapter())
