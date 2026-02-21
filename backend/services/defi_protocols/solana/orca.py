"""Orca Whirlpool adapter - concentrated LP position NFT detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
# Whirlpool position NFTs are tracked by the position account program
WHIRLPOOL_POSITION_PREFIX = bytes([0x70, 0x6f, 0x73, 0x69, 0x74, 0x69, 0x6f, 0x6e])  # "position"


class OrcaAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Orca"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://www.orca.so"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Orca Whirlpool concentrated LP positions.

        Whirlpool positions are represented as NFTs. We query getProgramAccounts
        filtering by the wallet owner in the position account data.
        """
        rpc_url = await get_helius_rpc_url()
        if not rpc_url:
            return []

        try:
            client = get_client("helius", timeout=30.0)
            # Filter: memcmp on whirlpool position accounts owned by this wallet
            # Position account layout: offset 8 = whirlpool pubkey (32), offset 40 = position mint (32)
            # We use a dataSize filter + owner filter on the token accounts holding position NFTs
            response = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    WHIRLPOOL_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": 216},  # Whirlpool Position account size
                            {"memcmp": {"offset": 8, "bytes": address}},  # Position authority/owner
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
            for i, account in enumerate(accounts):
                pubkey = account.get('pubkey', '')
                positions.append(ProtocolPosition(
                    protocol="Orca",
                    chain="solana",
                    position_type=PositionType.CONCENTRATED_LP,
                    token_symbol="ORCA-LP",
                    token_name="Orca Whirlpool Position",
                    amount=1.0,
                    token_id=pubkey,
                    extra={
                        "program_id": WHIRLPOOL_PROGRAM,
                        "position_account": pubkey,
                        "position_index": i,
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Orca positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(OrcaAdapter())
