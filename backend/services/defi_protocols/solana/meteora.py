"""Meteora adapter - DLMM LP position detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

METEORA_DLMM_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
# Meteora position account size
METEORA_POSITION_SIZE = 184


class MeteoraAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Meteora"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://app.meteora.ag"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Meteora DLMM (Dynamic Liquidity Market Maker) positions."""
        rpc_url = await get_helius_rpc_url()
        if not rpc_url:
            return []

        try:
            client = get_client("helius", timeout=30.0)
            response = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    METEORA_DLMM_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": METEORA_POSITION_SIZE},
                            # Position owner at offset 8
                            {"memcmp": {"offset": 8, "bytes": address}},
                        ]
                    }
                ]
            })

            if response.status_code != 200:
                return []

            data = response.json()
            accounts = data.get('result', [])

            if not accounts:
                return []

            positions = []
            for account in accounts:
                pubkey = account.get('pubkey', '')
                positions.append(ProtocolPosition(
                    protocol="Meteora",
                    chain="solana",
                    position_type=PositionType.LP_POSITION,
                    token_symbol="MET-LP",
                    token_name="Meteora DLMM Position",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": METEORA_DLMM_PROGRAM,
                        "position_account": pubkey,
                        "note": "Exact liquidity amounts require on-chain data decoding",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Meteora positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(MeteoraAdapter())
