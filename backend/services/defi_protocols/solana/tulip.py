"""Tulip Protocol adapter - yield vault token detection."""

from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter


class TulipAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Tulip"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://tulip.garden"

    # Tulip yield-bearing vault token mints
    VAULT_TOKENS = {
        "tulipSOL": ("TuLipcqtGVXP9XR62wM8WWCm6a9vhLs7T1uoWBk6FDs", "SOL"),
        "tulipUSDC": ("Amig8TisuLpzun8XyGfC5HJHHGUQEscjLgoTWsCqZnXD", "USDC"),
        "tulipUSDT": ("RH9tXDCMBessCMKDEgSNtAfUbWCkFHBqMiitCnFuBCG", "USDT"),
        "tulipRAY": ("4B5qsJpjLAm9AMsR2TXBBNjQ9nqkEP5xb5UEetbZ9MSd", "RAY"),
    }

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        positions = []
        for vault_symbol, (mint, underlying_symbol) in self.VAULT_TOKENS.items():
            balance = await self._get_spl_balance(address, mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Tulip",
                    chain="solana",
                    position_type=PositionType.YIELD_VAULT,
                    token_symbol=vault_symbol,
                    token_name=f"Tulip {underlying_symbol} Vault",
                    amount=balance,
                    contract_address=mint,
                    extra={"underlying_symbol": underlying_symbol},
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(TulipAdapter())
