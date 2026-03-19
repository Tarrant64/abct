"""Jupiter Perpetuals adapter - perpetual position detection via REST API."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

JUPITER_PERPS_PROGRAM = "PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu"
JUPITER_POSITION_SIZE = 232

# Jupiter Perps REST API
JUP_PERPS_API = "https://perps-api.jup.ag"

# Known custody token mappings
JUP_CUSTODY_TOKENS = {
    "So11111111111111111111111111111111111111112": "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "wBTC",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "wETH",
}

# Precision for Jupiter Perps
USD_PRECISION = 1_000_000  # 10^6


class JupiterPerpsAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Jupiter Perps"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://jup.ag/perps"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Jupiter Perpetuals open positions.

        Strategy: Try REST API first for rich position data, fall back to on-chain.
        """
        positions = await self._try_api(address)
        if positions is not None:
            return positions

        return await self._detect_onchain(address)

    async def _try_api(self, address: str) -> List[ProtocolPosition]:
        """Try Jupiter Perps API for detailed position data."""
        try:
            client = get_client("jupiter_perps", timeout=15.0)

            # Try positions endpoint
            response = await client.get(
                f"{JUP_PERPS_API}/v1/positions",
                params={"wallet": address},
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                # Try alternate endpoint format
                response = await client.get(
                    f"{JUP_PERPS_API}/positions",
                    params={"walletAddress": address},
                    headers={"Accept": "application/json"}
                )
                if response.status_code != 200:
                    return None

            data = response.json()
            if not data:
                return None

            raw_positions = data if isinstance(data, list) else data.get("positions", data.get("data", []))
            if not raw_positions:
                return None

            positions = []
            for pos in raw_positions:
                # Parse token/market info
                custody_mint = pos.get("custody", pos.get("custody_mint", ""))
                token_symbol = JUP_CUSTODY_TOKENS.get(custody_mint, pos.get("token", pos.get("symbol", "UNKNOWN")))
                market_symbol = pos.get("market", pos.get("market_symbol", f"{token_symbol}-PERP"))

                # Position size
                size_usd = float(pos.get("sizeUsd", pos.get("size_usd", pos.get("notionalUsd", 0))) or 0)
                if size_usd > USD_PRECISION:
                    size_usd = size_usd / USD_PRECISION

                size_tokens = float(pos.get("sizeTokens", pos.get("size_amount", pos.get("size", 0))) or 0)

                if size_usd < 0.01 and size_tokens < 0.000001:
                    continue

                # Collateral
                collateral_usd = float(pos.get("collateralUsd", pos.get("collateral_usd", pos.get("collateral", 0))) or 0)
                if collateral_usd > USD_PRECISION:
                    collateral_usd = collateral_usd / USD_PRECISION

                # PnL
                pnl = float(pos.get("pnl", pos.get("unrealizedPnl", pos.get("unrealized_pnl", 0))) or 0)
                if abs(pnl) > USD_PRECISION:
                    pnl = pnl / USD_PRECISION

                # Entry price
                entry_price = float(pos.get("entryPrice", pos.get("entry_price", pos.get("averageEntryPrice", 0))) or 0)
                if entry_price > USD_PRECISION:
                    entry_price = entry_price / USD_PRECISION

                # Mark/current price
                mark_price = float(pos.get("markPrice", pos.get("current_price", pos.get("price", 0))) or 0)
                if mark_price > USD_PRECISION:
                    mark_price = mark_price / USD_PRECISION

                # Liquidation price
                liq_price = float(pos.get("liquidationPrice", pos.get("liquidation_price", 0)) or 0)
                if liq_price > USD_PRECISION:
                    liq_price = liq_price / USD_PRECISION

                # Side (long/short)
                side_raw = pos.get("side", pos.get("direction", ""))
                if isinstance(side_raw, str):
                    side = "long" if side_raw.lower() in ("long", "buy") else "short"
                else:
                    side = "long" if size_tokens > 0 else "short"

                # Leverage
                leverage = 0
                if collateral_usd > 0 and size_usd > 0:
                    leverage = round(size_usd / collateral_usd, 1)
                else:
                    leverage = float(pos.get("leverage", 0) or 0)

                display_name = f"Jupiter {market_symbol} {side.capitalize()}"

                positions.append(ProtocolPosition(
                    protocol="Jupiter Perps",
                    chain="solana",
                    position_type=PositionType.PERPETUALS,
                    token_symbol=market_symbol,
                    token_name=display_name,
                    amount=abs(size_tokens) if size_tokens else abs(size_usd),
                    value_usd=abs(size_usd),
                    extra={
                        "side": side,
                        "size_usd": round(size_usd, 2),
                        "collateral_usd": round(collateral_usd, 2),
                        "pnl": round(pnl, 2),
                        "entry_price": round(entry_price, 4),
                        "mark_price": round(mark_price, 4),
                        "liquidation_price": round(liq_price, 4) if liq_price > 0 else None,
                        "leverage": leverage,
                        "source": "api",
                    },
                ))

            return positions if positions else None

        except Exception as e:
            logger.debug(f"Jupiter Perps API unavailable for {address[:20]}...: {e}")
            return None

    async def _detect_onchain(self, address: str) -> List[ProtocolPosition]:
        """Fallback: detect position existence on-chain."""
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
                        "note": "API unavailable - showing position existence only",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Jupiter Perps positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(JupiterPerpsAdapter())
