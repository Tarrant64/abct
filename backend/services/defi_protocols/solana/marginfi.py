"""Marginfi adapter - lending supply and borrow position detection."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

MARGINFI_PROGRAM = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
# Marginfi account size for v2
MARGINFI_ACCOUNT_SIZE = 1736


class MarginfiAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Marginfi"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://app.marginfi.com"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Marginfi lending/borrowing positions.

        Marginfi user accounts are program accounts with the wallet authority
        stored at a known offset in the account data.
        """
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
                    MARGINFI_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": MARGINFI_ACCOUNT_SIZE},
                            # Authority is at offset 40 in the marginfi account
                            {"memcmp": {"offset": 40, "bytes": address}},
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

            # Each marginfi account represents a user's margin position
            # Detailed parsing of balances requires decoding borsh-serialized data
            # For now, report position existence with account reference
            positions = []
            for account in accounts:
                pubkey = account.get('pubkey', '')
                positions.append(ProtocolPosition(
                    protocol="Marginfi",
                    chain="solana",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol="mrgn",
                    token_name="Marginfi Position",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": MARGINFI_PROGRAM,
                        "account": pubkey,
                        "note": "Exact balances require on-chain data decoding",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Marginfi positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(MarginfiAdapter())
