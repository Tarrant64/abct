"""Kamino adapter - lending supply, borrow, and vault position detection via REST API."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Kamino REST API
KAMINO_API_BASE = "https://api.hubbleprotocol.io/v2/kamino-market"
KAMINO_MAIN_MARKET = "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF"

# kToken mints → underlying mapping
KTOKENS = {
    "kSOL": ("CgEY5fPVsMTCsN1YHfVLrscLaKhgcFnyFLo2MPVFGW2Q", "SOL"),
    "kUSDC": ("9TD2TSv4pENb8VwfbVYg25jvym7HN6iuAR6UXNtFCKRt", "USDC"),
    "kUSDT": ("H9vmCVd77N1HZa36eBn3UnfYmCudNnmk14zgz6NETuS6", "USDT"),
    "kmSOL": ("DELMLHhFUsGsaJJEhCHFHHmfKFoJEz7URrFgBW1FMzW4", "mSOL"),
}


class KaminoAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Kamino"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://app.kamino.finance"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Kamino positions.

        Strategy: Try Kamino/Hubble REST API for obligations (lending/borrowing),
        then check kToken balances for vault positions.
        """
        positions = []

        # Phase 1: Try REST API for lending obligations
        api_positions = await self._try_lending_api(address)
        if api_positions:
            positions.extend(api_positions)

        # Phase 2: Check kToken balances for vault supply (only if API didn't return data)
        if not positions:
            ktoken_positions = await self._check_ktokens(address)
            positions.extend(ktoken_positions)

        return positions

    async def _try_lending_api(self, address: str) -> List[ProtocolPosition]:
        """Try Kamino/Hubble API for lending obligations."""
        try:
            client = get_client("kamino", timeout=15.0)

            # Kamino obligations endpoint via Hubble API
            response = await client.get(
                f"{KAMINO_API_BASE}/{KAMINO_MAIN_MARKET}/users/{address}/obligations",
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                # Try alternate Kamino endpoint
                response = await client.get(
                    f"https://api.kamino.finance/users/{address}/obligations",
                    headers={"Accept": "application/json"}
                )
                if response.status_code != 200:
                    return None

            data = response.json()
            if not data:
                return None

            obligations = data if isinstance(data, list) else [data]
            positions = []

            for obligation in obligations:
                # Supply/deposit positions
                deposits = obligation.get("deposits", obligation.get("collateral", []))
                if isinstance(deposits, list):
                    for dep in deposits:
                        symbol = dep.get("symbol", dep.get("token_symbol", "UNKNOWN"))
                        amount = float(dep.get("amount", dep.get("deposit_amount", 0)) or 0)
                        if amount > 0.000001:
                            value_usd = float(dep.get("value_usd", dep.get("market_value", 0)) or 0)
                            apy = float(dep.get("supply_apy", dep.get("apy", 0)) or 0)
                            positions.append(ProtocolPosition(
                                protocol="Kamino",
                                chain="solana",
                                position_type=PositionType.LENDING_SUPPLY,
                                token_symbol=symbol,
                                token_name=f"Kamino {symbol} Supply",
                                amount=amount,
                                value_usd=value_usd,
                                apy=apy * 100 if 0 < apy < 1 else apy,
                                extra={
                                    "underlying_token": symbol,
                                    "market": KAMINO_MAIN_MARKET,
                                    "source": "api",
                                },
                            ))

                # Borrow positions
                borrows = obligation.get("borrows", obligation.get("loans", []))
                if isinstance(borrows, list):
                    for bor in borrows:
                        symbol = bor.get("symbol", bor.get("token_symbol", "UNKNOWN"))
                        amount = float(bor.get("amount", bor.get("borrow_amount", 0)) or 0)
                        if amount > 0.000001:
                            value_usd = float(bor.get("value_usd", bor.get("market_value", 0)) or 0)
                            borrow_apy = float(bor.get("borrow_apy", bor.get("apy", 0)) or 0)
                            positions.append(ProtocolPosition(
                                protocol="Kamino",
                                chain="solana",
                                position_type=PositionType.LENDING_BORROW,
                                token_symbol=symbol,
                                token_name=f"Kamino {symbol} Borrow",
                                amount=amount,
                                value_usd=value_usd,
                                apy=borrow_apy * 100 if 0 < borrow_apy < 1 else borrow_apy,
                                extra={
                                    "underlying_token": symbol,
                                    "source": "api",
                                },
                            ))

                # Health/LTV from obligation level
                ltv = float(obligation.get("current_ltv", obligation.get("ltv", 0)) or 0)
                max_ltv = float(obligation.get("max_ltv", obligation.get("liquidation_ltv", 0)) or 0)
                if ltv > 0 and max_ltv > 0:
                    health_factor = max_ltv / ltv if ltv > 0 else 999
                    for pos in positions:
                        if pos.position_type == PositionType.LENDING_BORROW:
                            pos.extra["health_factor"] = round(health_factor, 2)
                            pos.extra["ltv"] = round(ltv * 100 if ltv < 1 else ltv, 2)

            return positions if positions else None

        except Exception as e:
            logger.debug(f"Kamino API unavailable for {address[:20]}...: {e}")
            return None

    async def _check_ktokens(self, address: str) -> List[ProtocolPosition]:
        """Fallback: check kToken SPL balances."""
        positions = []
        for ktoken_symbol, (mint, underlying_symbol) in KTOKENS.items():
            balance = await self._get_spl_balance(address, mint)
            if balance and balance > 0:
                positions.append(ProtocolPosition(
                    protocol="Kamino",
                    chain="solana",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=ktoken_symbol,
                    token_name=f"Kamino {underlying_symbol} Supply",
                    amount=balance,
                    contract_address=mint,
                    extra={
                        "underlying_token": underlying_symbol,
                        "note": "kToken balance - underlying value may differ",
                        "source": "ktoken",
                    },
                ))
        return positions


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(KaminoAdapter())
