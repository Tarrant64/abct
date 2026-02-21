"""Jupiter Perpetuals adapter - perpetual position detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

JUPITER_PERPS_PROGRAM = "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu"
# Jupiter Perp position account size
JUPITER_POSITION_SIZE = 232


class JupiterPerpsAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Jupiter Perps"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://jup.ag/perps"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Jupiter Perpetuals open positions."""
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
                    JUPITER_PERPS_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": JUPITER_POSITION_SIZE},
                            # Owner/authority at offset 8
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
                    protocol="Jupiter Perps",
                    chain="solana",
                    position_type=PositionType.PERPETUALS,
                    token_symbol="JLP",
                    token_name="Jupiter Perpetual Position",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": JUPITER_PERPS_PROGRAM,
                        "position_account": pubkey,
                        "note": "Exact size/PnL requires on-chain data decoding",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Jupiter Perps positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(JupiterPerpsAdapter())
