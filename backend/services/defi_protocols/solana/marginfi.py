"""Marginfi adapter - lending supply and borrow position detection via REST API."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

MARGINFI_PROGRAM = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
MARGINFI_ACCOUNT_SIZE = 1736

# Marginfi REST API base
MARGINFI_API_BASE = "https://api.marginfi.com"

# Known bank mint → token symbol mapping
BANK_TOKEN_MAP = {
    "So11111111111111111111111111111111111111112": ("SOL", 9),
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC", 6),
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": ("USDT", 6),
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": ("mSOL", 9),
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": ("JitoSOL", 9),
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": ("stSOL", 9),
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": ("bSOL", 9),
}


class MarginfiAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Marginfi"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://app.marginfi.com"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Marginfi lending/borrowing positions.

        Strategy: Try REST API first for rich data, fall back to on-chain detection.
        """
        positions = await self._try_api(address)
        if positions is not None:
            return positions

        # Fallback: on-chain account detection
        return await self._detect_onchain(address)

    async def _try_api(self, address: str) -> List[ProtocolPosition]:
        """Try Marginfi REST API for detailed position data."""
        try:
            client = get_client("marginfi", timeout=15.0)

            # Try the accounts endpoint
            response = await client.get(
                f"{MARGINFI_API_BASE}/accounts/{address}",
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                return None

            data = response.json()
            if not data:
                return None

            positions = []
            accounts = data if isinstance(data, list) else [data]

            for account in accounts:
                # Parse lending balances from API response
                balances = account.get("balances", account.get("lending_accounts", []))
                if not balances:
                    continue

                for balance in balances:
                    mint = balance.get("mint", balance.get("bank_mint", ""))
                    token_info = BANK_TOKEN_MAP.get(mint, (None, None))
                    symbol = token_info[0] or balance.get("symbol", "UNKNOWN")

                    # Supply (deposit) balance
                    supply_amount = float(balance.get("deposit_amount", balance.get("supply", balance.get("assets", 0))) or 0)
                    if supply_amount > 0.000001:
                        supply_usd = float(balance.get("deposit_value_usd", balance.get("supply_usd", 0)) or 0)
                        apy = float(balance.get("deposit_apy", balance.get("supply_apy", 0)) or 0)
                        positions.append(ProtocolPosition(
                            protocol="Marginfi",
                            chain="solana",
                            position_type=PositionType.LENDING_SUPPLY,
                            token_symbol=symbol,
                            token_name=f"Marginfi {symbol} Supply",
                            amount=supply_amount,
                            value_usd=supply_usd,
                            apy=apy * 100 if apy < 1 else apy,  # Normalize to percentage
                            extra={
                                "underlying_token": symbol,
                                "mint": mint,
                                "source": "api",
                            },
                        ))

                    # Borrow (liability) balance
                    borrow_amount = float(balance.get("borrow_amount", balance.get("liability", balance.get("liabilities", 0))) or 0)
                    if borrow_amount > 0.000001:
                        borrow_usd = float(balance.get("borrow_value_usd", balance.get("liability_usd", 0)) or 0)
                        borrow_apy = float(balance.get("borrow_apy", balance.get("liability_apy", 0)) or 0)
                        positions.append(ProtocolPosition(
                            protocol="Marginfi",
                            chain="solana",
                            position_type=PositionType.LENDING_BORROW,
                            token_symbol=symbol,
                            token_name=f"Marginfi {symbol} Borrow",
                            amount=borrow_amount,
                            value_usd=borrow_usd,
                            apy=borrow_apy * 100 if borrow_apy < 1 else borrow_apy,
                            extra={
                                "underlying_token": symbol,
                                "mint": mint,
                                "source": "api",
                            },
                        ))

                # Health factor from account-level data
                health = float(account.get("health_factor", account.get("health", 0)) or 0)
                if health > 0 and positions:
                    for pos in positions:
                        if pos.position_type == PositionType.LENDING_BORROW:
                            pos.extra["health_factor"] = health

            return positions if positions else None

        except Exception as e:
            logger.debug(f"Marginfi API unavailable for {address[:20]}...: {e}")
            return None

    async def _detect_onchain(self, address: str) -> List[ProtocolPosition]:
        """Fallback: detect account existence on-chain via getProgramAccounts."""
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
                        "note": "API unavailable - showing position existence only",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Marginfi positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(MarginfiAdapter())
