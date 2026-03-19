"""Drift Protocol adapter - perpetuals and spot position detection via REST API."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

DRIFT_PROGRAM = "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH"
DRIFT_USER_SIZE = 4376

# Drift REST API endpoints
DRIFT_API_BASE = "https://dlob.drift.trade"
DRIFT_MAINNET_API = "https://mainnet-beta.api.drift.trade"

# Drift market index → symbol mapping
DRIFT_PERP_MARKETS = {
    0: "SOL-PERP",
    1: "BTC-PERP",
    2: "ETH-PERP",
    3: "APT-PERP",
    4: "MATIC-PERP",
    5: "ARB-PERP",
    6: "DOGE-PERP",
    7: "BNB-PERP",
    8: "SUI-PERP",
    9: "1MPEPE-PERP",
    10: "OP-PERP",
    11: "RENDER-PERP",
    12: "XRP-PERP",
    13: "HNT-PERP",
    14: "INJ-PERP",
    15: "LINK-PERP",
    16: "RLB-PERP",
    17: "PYTH-PERP",
    18: "TIA-PERP",
    19: "JTO-PERP",
    20: "SEI-PERP",
    21: "AVAX-PERP",
    22: "WIF-PERP",
    23: "JUP-PERP",
    24: "DYM-PERP",
    25: "TAO-PERP",
    26: "W-PERP",
    27: "KMNO-PERP",
    28: "TNSR-PERP",
}

DRIFT_SPOT_MARKETS = {
    0: "USDC",
    1: "SOL",
    2: "mSOL",
    3: "wBTC",
    4: "wETH",
    5: "USDT",
    6: "jitoSOL",
    7: "PYTH",
    8: "bSOL",
    9: "JTO",
    10: "WIF",
    11: "JUP",
    12: "RNDR",
    13: "W",
    14: "TNSR",
    15: "DRIFT",
}

# Precision constants for Drift protocol
PRICE_PRECISION = 1_000_000  # 10^6
BASE_PRECISION = 1_000_000_000  # 10^9
QUOTE_PRECISION = 1_000_000  # 10^6


class DriftAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Drift"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://app.drift.trade"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Drift Protocol positions.

        Strategy: Try REST API first, fall back to on-chain detection.
        """
        positions = await self._try_api(address)
        if positions is not None:
            return positions

        return await self._detect_onchain(address)

    async def _try_api(self, address: str) -> List[ProtocolPosition]:
        """Try Drift REST API for detailed position data."""
        try:
            client = get_client("drift", timeout=15.0)

            # Try the user positions endpoint
            response = await client.get(
                f"{DRIFT_MAINNET_API}/positions",
                params={"userAuthority": address},
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                # Try alternate endpoint
                response = await client.get(
                    f"{DRIFT_API_BASE}/userPositions",
                    params={"authority": address},
                    headers={"Accept": "application/json"}
                )
                if response.status_code != 200:
                    return None

            data = response.json()
            if not data:
                return None

            positions = []

            # Parse perp positions
            perp_positions = data.get("perpPositions", data.get("perp_positions", []))
            for perp in perp_positions:
                market_index = int(perp.get("marketIndex", perp.get("market_index", -1)))
                market_name = DRIFT_PERP_MARKETS.get(market_index, f"PERP-{market_index}")

                base_amount = float(perp.get("baseAssetAmount", perp.get("base_asset_amount", 0)) or 0)
                # Drift stores base amounts in BASE_PRECISION (10^9)
                if abs(base_amount) > BASE_PRECISION:
                    base_amount = base_amount / BASE_PRECISION

                if abs(base_amount) < 0.000001:
                    continue

                # Quote entry and current value
                quote_entry = float(perp.get("quoteEntryAmount", perp.get("quote_entry_amount", 0)) or 0)
                quote_break_even = float(perp.get("quoteBreakEvenAmount", perp.get("quote_break_even_amount", 0)) or 0)
                if abs(quote_entry) > QUOTE_PRECISION:
                    quote_entry = quote_entry / QUOTE_PRECISION
                if abs(quote_break_even) > QUOTE_PRECISION:
                    quote_break_even = quote_break_even / QUOTE_PRECISION

                # Settled PnL
                settled_pnl = float(perp.get("settledPnl", perp.get("settled_pnl", 0)) or 0)
                if abs(settled_pnl) > QUOTE_PRECISION:
                    settled_pnl = settled_pnl / QUOTE_PRECISION

                unsettled_pnl = float(perp.get("unsettledPnl", perp.get("unsettled_pnl", 0)) or 0)
                if abs(unsettled_pnl) > QUOTE_PRECISION:
                    unsettled_pnl = unsettled_pnl / QUOTE_PRECISION

                total_pnl = settled_pnl + unsettled_pnl

                side = "Long" if base_amount > 0 else "Short"
                entry_price = abs(quote_entry / base_amount) if abs(base_amount) > 0.000001 else 0

                positions.append(ProtocolPosition(
                    protocol="Drift",
                    chain="solana",
                    position_type=PositionType.PERPETUALS,
                    token_symbol=market_name,
                    token_name=f"Drift {market_name} {side}",
                    amount=abs(base_amount),
                    value_usd=abs(quote_entry),
                    extra={
                        "side": side.lower(),
                        "entry_price": round(entry_price, 4),
                        "pnl": round(total_pnl, 2),
                        "settled_pnl": round(settled_pnl, 2),
                        "unsettled_pnl": round(unsettled_pnl, 2),
                        "market_index": market_index,
                        "source": "api",
                    },
                ))

            # Parse spot positions (deposits/borrows)
            spot_positions = data.get("spotPositions", data.get("spot_positions", []))
            for spot in spot_positions:
                market_index = int(spot.get("marketIndex", spot.get("market_index", -1)))
                symbol = DRIFT_SPOT_MARKETS.get(market_index, f"SPOT-{market_index}")

                scaled_balance = float(spot.get("scaledBalance", spot.get("scaled_balance", 0)) or 0)
                if abs(scaled_balance) > BASE_PRECISION:
                    scaled_balance = scaled_balance / BASE_PRECISION

                if abs(scaled_balance) < 0.000001:
                    continue

                balance_type = spot.get("balanceType", spot.get("balance_type", "deposit"))
                is_borrow = balance_type in ("borrow", "Borrow", 1)

                if is_borrow:
                    positions.append(ProtocolPosition(
                        protocol="Drift",
                        chain="solana",
                        position_type=PositionType.LENDING_BORROW,
                        token_symbol=symbol,
                        token_name=f"Drift {symbol} Borrow",
                        amount=abs(scaled_balance),
                        extra={
                            "underlying_token": symbol,
                            "market_index": market_index,
                            "source": "api",
                        },
                    ))
                else:
                    positions.append(ProtocolPosition(
                        protocol="Drift",
                        chain="solana",
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol=symbol,
                        token_name=f"Drift {symbol} Deposit",
                        amount=abs(scaled_balance),
                        extra={
                            "underlying_token": symbol,
                            "market_index": market_index,
                            "source": "api",
                        },
                    ))

            # Account-level data (collateral, free collateral, leverage)
            total_collateral = float(data.get("totalCollateral", data.get("total_collateral", 0)) or 0)
            if total_collateral > QUOTE_PRECISION:
                total_collateral = total_collateral / QUOTE_PRECISION
            free_collateral = float(data.get("freeCollateral", data.get("free_collateral", 0)) or 0)
            if free_collateral > QUOTE_PRECISION:
                free_collateral = free_collateral / QUOTE_PRECISION
            leverage = float(data.get("leverage", 0) or 0)
            if leverage > 10000:
                leverage = leverage / 10000  # Drift stores as basis points

            if total_collateral > 0:
                for pos in positions:
                    if pos.position_type == PositionType.PERPETUALS:
                        pos.extra["total_collateral"] = round(total_collateral, 2)
                        pos.extra["free_collateral"] = round(free_collateral, 2)
                        if leverage > 0:
                            pos.extra["leverage"] = round(leverage, 2)

            return positions if positions else None

        except Exception as e:
            logger.debug(f"Drift API unavailable for {address[:20]}...: {e}")
            return None

    async def _detect_onchain(self, address: str) -> List[ProtocolPosition]:
        """Fallback: detect account existence on-chain."""
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
                        "note": "API unavailable - showing position existence only",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Drift positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(DriftAdapter())
