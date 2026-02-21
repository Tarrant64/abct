"""Drift Protocol adapter - perpetuals and spot position detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

DRIFT_PROGRAM = "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH"
# Drift user account size (v2)
DRIFT_USER_SIZE = 4376


class DriftAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Drift"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://app.drift.trade"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Drift Protocol user accounts (perpetuals and spot positions)."""
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
                    DRIFT_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": DRIFT_USER_SIZE},
                            # Drift user account: authority is at offset 8
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
                    protocol="Drift",
                    chain="solana",
                    position_type=PositionType.PERPETUALS,
                    token_symbol="DRIFT",
                    token_name="Drift User Account",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": DRIFT_PROGRAM,
                        "user_account": pubkey,
                        "note": "Exact positions require borsh decoding of account data",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Drift positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(DriftAdapter())
