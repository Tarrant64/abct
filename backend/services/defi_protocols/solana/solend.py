"""Solend adapter - cToken lending supply + borrow position detection via REST API."""

import logging
from typing import List, Dict
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Solend REST API
SOLEND_API_BASE = "https://api.solend.fi/v1"

# cToken mints for main pool reserves
CTOKENS = {
    "cSOL": ("5h6ssFpeDeRbzsEHcTNtSq7J3HMGY6bExK4xksMaXspr", "SOL", 9),
    "cUSDC": ("993dVFL2uXWYeoXuEBFXR4BijeXdTv4s6BzsCjJZuwqk", "USDC", 6),
    "cUSDT": ("BTsbZDV7aCMRJ3VNy9ygV4Q2UeEo9GpR8wre1hFMZEiL", "USDT", 6),
    "cETH": ("MdExmPxCYyEMFLqJTGnRJFxCBuMxSGGfFKVZkMVcZ2K", "ETH", 18),
    "cBTC": ("3JFC4cB56Er45nWVe29Bhnn5GnwQzSmHVf6eUq9ac91h", "BTC", 8),
}

# Solend main pool
SOLEND_MAIN_POOL = "4UpD2fh7xH3VP9QQaXtsS1YY3bxzWhtfpks7FatyKvdY"


class SolendAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Solend"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://solend.fi"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Solend lending and borrowing positions.

        Strategy: Try REST API first for full obligation data (supply + borrow + health),
        then fall back to cToken balance checks (supply only).
        """
        positions = await self._try_api(address)
        if positions is not None:
            return positions

        return await self._check_ctokens(address)

    async def _try_api(self, address: str) -> List[ProtocolPosition]:
        """Try Solend REST API for obligation data (supply + borrow + health factor)."""
        try:
            client = get_client("solend", timeout=15.0)

            # Try obligations endpoint
            response = await client.get(
                f"{SOLEND_API_BASE}/obligations",
                params={"wallet": address, "poolAddress": SOLEND_MAIN_POOL},
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                # Try alternate endpoint
                response = await client.get(
                    f"https://api.solend.fi/v2/positions/{address}",
                    headers={"Accept": "application/json"}
                )
                if response.status_code != 200:
                    return None

            data = response.json()
            if not data:
                return None

            positions = []

            # Parse obligations
            obligations = data if isinstance(data, list) else data.get("obligations", data.get("positions", [data]))

            for obligation in obligations:
                if not obligation:
                    continue

                # Supply positions (deposits)
                deposits = obligation.get("deposits", obligation.get("collateral", obligation.get("supply", [])))
                if isinstance(deposits, list):
                    for dep in deposits:
                        symbol = dep.get("symbol", dep.get("mintSymbol", "UNKNOWN"))
                        amount = float(dep.get("amount", dep.get("depositedAmount", 0)) or 0)
                        if amount < 0.000001:
                            continue

                        value_usd = float(dep.get("value_usd", dep.get("marketValue", dep.get("usdValue", 0))) or 0)
                        apy = float(dep.get("supplyApy", dep.get("apy", dep.get("supply_apy", 0))) or 0)

                        positions.append(ProtocolPosition(
                            protocol="Solend",
                            chain="solana",
                            position_type=PositionType.LENDING_SUPPLY,
                            token_symbol=symbol,
                            token_name=f"Solend {symbol} Supply",
                            amount=amount,
                            value_usd=value_usd,
                            apy=apy * 100 if 0 < apy < 1 else apy,
                            extra={
                                "underlying_token": symbol,
                                "pool": "main",
                                "source": "api",
                            },
                        ))

                # Borrow positions
                borrows = obligation.get("borrows", obligation.get("loans", obligation.get("borrow", [])))
                if isinstance(borrows, list):
                    for bor in borrows:
                        symbol = bor.get("symbol", bor.get("mintSymbol", "UNKNOWN"))
                        amount = float(bor.get("amount", bor.get("borrowedAmount", 0)) or 0)
                        if amount < 0.000001:
                            continue

                        value_usd = float(bor.get("value_usd", bor.get("marketValue", bor.get("usdValue", 0))) or 0)
                        borrow_apy = float(bor.get("borrowApy", bor.get("apy", bor.get("borrow_apy", 0))) or 0)

                        positions.append(ProtocolPosition(
                            protocol="Solend",
                            chain="solana",
                            position_type=PositionType.LENDING_BORROW,
                            token_symbol=symbol,
                            token_name=f"Solend {symbol} Borrow",
                            amount=amount,
                            value_usd=value_usd,
                            apy=borrow_apy * 100 if 0 < borrow_apy < 1 else borrow_apy,
                            extra={
                                "underlying_token": symbol,
                                "pool": "main",
                                "source": "api",
                            },
                        ))

                # Health factor / utilization
                deposited_value = float(obligation.get("depositedValue", obligation.get("totalDeposited", 0)) or 0)
                borrowed_value = float(obligation.get("borrowedValue", obligation.get("totalBorrowed", 0)) or 0)
                borrow_limit = float(obligation.get("borrowLimit", obligation.get("allowedBorrowValue", 0)) or 0)

                if borrowed_value > 0 and deposited_value > 0:
                    # Calculate health factor as (borrow limit / borrowed value)
                    health_factor = borrow_limit / borrowed_value if borrowed_value > 0 else 999
                    for pos in positions:
                        if pos.position_type == PositionType.LENDING_BORROW:
                            pos.extra["health_factor"] = round(health_factor, 2)
                            pos.extra["utilization"] = round((borrowed_value / borrow_limit) * 100 if borrow_limit > 0 else 0, 2)

            return positions if positions else None

        except Exception as e:
            logger.debug(f"Solend API unavailable for {address[:20]}...: {e}")
            return None

    async def _check_ctokens(self, address: str) -> List[ProtocolPosition]:
        """Fallback: check cToken balances for supply positions."""
        positions = []
        for ctoken_symbol, (mint, underlying_symbol, decimals) in CTOKENS.items():
            balance = await self._get_spl_balance(address, mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Solend",
                    chain="solana",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=ctoken_symbol,
                    token_name=f"Solend {underlying_symbol} Supply",
                    amount=balance,
                    contract_address=mint,
                    extra={
                        "underlying_token": underlying_symbol,
                        "note": "cToken balance - underlying value may differ due to exchange rate",
                        "source": "ctoken",
                    },
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(SolendAdapter())
