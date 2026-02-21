"""Raydium adapter - LP token position detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Raydium AMM v4 program ID
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

# Known Raydium LP token mints for major pools
KNOWN_LP_MINTS = {
    "RAY-SOL LP": "89ZKE4aoyfLBe2RuV6NpNN2629TNjKdzB9DSi5mLG3HM",
    "RAY-USDC LP": "FbC6K13MzHvN42bXrtGaWsvZY9fxrackRSZcBGfjPc7Y",
    "RAY-USDT LP": "C3sT1R3nsw4AVdepvLTLKr5Gvszr7jufyBWUCvy4TUvT",
    "SOL-USDC LP": "8HoQnePLqPj4M7PUDzfw8e3Ymdwgc7NLGnaTUapubyvu",
    "SOL-USDT LP": "Epm4KfTj4DMrvqn6Bwg2Tr2N8vhQuNbuK8bESFp4k33K",
}


class RaydiumAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Raydium"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://raydium.io"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        positions = []
        for pool_name, lp_mint in KNOWN_LP_MINTS.items():
            balance = await self._get_spl_balance(address, lp_mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Raydium",
                    chain="solana",
                    position_type=PositionType.LP_POSITION,
                    token_symbol="RAY-LP",
                    token_name=pool_name,
                    amount=balance,
                    contract_address=lp_mint,
                    extra={"program_id": RAYDIUM_AMM_PROGRAM, "pool": pool_name},
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(RaydiumAdapter())
