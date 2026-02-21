"""Lifinity adapter - concentrated liquidity LP position detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

LIFINITY_PROGRAM = "EewxydAPCCVuNEyrVN68PuSYdQ7wKn27V9Gjeoi8dy3S"

# Known Lifinity LP token mints
KNOWN_LP_MINTS = {
    "LFNTY-SOL LP": "7VZGHb3pDrGPy4Q3GwVNznLNjkJnPguinJzjkYBjPGr9",
    "USDC-USDT LP": "8V3zyLMSgGFUjNFzYbfmrKnRLg6FJXSaBMoFYkKxdCzH",
    "SOL-USDC LP": "3uTzTX5GBSfbW7eM9R9k95H7Lqd8hYKxMTZZHXNvE4Y",
}


class LifinityAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Lifinity"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://lifinity.io"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Lifinity LP token positions."""
        positions = []
        for pool_name, lp_mint in KNOWN_LP_MINTS.items():
            balance = await self._get_spl_balance(address, lp_mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Lifinity",
                    chain="solana",
                    position_type=PositionType.LP_POSITION,
                    token_symbol="LFNTY-LP",
                    token_name=pool_name,
                    amount=balance,
                    contract_address=lp_mint,
                    extra={
                        "program_id": LIFINITY_PROGRAM,
                        "pool": pool_name,
                    },
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(LifinityAdapter())
