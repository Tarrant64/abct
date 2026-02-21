"""Kamino adapter - kToken lending supply detection."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class KaminoAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Kamino"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://app.kamino.finance"

    # kToken mints for Kamino lending reserves
    KTOKENS = {
        "kSOL": ("CgEY5fPVsMTCsN1YHfVLrscLaKhgcFnyFLo2MPVFGW2Q", "SOL"),
        "kUSDC": ("9TD2TSv4pENb8VwfbVYg25jvym7HN6iuAR6UXNtFCKRt", "USDC"),
        "kUSDT": ("H9vmCVd77N1HZa36eBn3UnfYmCudNnmk14zgz6NETuS6", "USDT"),
        "kmSOL": ("DELMLHhFUsGsaJJEhCHFHHmfKFoJEz7URrFgBW1FMzW4", "mSOL"),
    }

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        positions = []
        for ktoken_symbol, (mint, underlying_symbol) in self.KTOKENS.items():
            balance = await self._get_spl_balance(address, mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Kamino",
                    chain="solana",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=ktoken_symbol,
                    token_name=f"Kamino {underlying_symbol} Supply",
                    amount=balance,
                    contract_address=mint,
                    extra={"underlying_symbol": underlying_symbol},
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(KaminoAdapter())
