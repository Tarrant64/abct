"""Orca Whirlpool adapter - concentrated LP position detection via REST API."""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"

# Orca/Whirlpool REST API
ORCA_API_BASE = "https://api.mainnet.orca.so/v1"
ORCA_WHIRLPOOL_API = "https://api.mainnet.orca.so"

# Known token mint → symbol mapping
KNOWN_TOKEN_MINTS = {
    "So11111111111111111111111111111111111111112": "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "stSOL",
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": "bSOL",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux": "HNT",
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "wBTC",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "wETH",
    "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7": "DRIFT",
    "RNDRzNmkFcyPSgFPNsMcP4BruJNPHCEpNktT4jjAbLw": "RNDR",
}


class OrcaAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Orca"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://www.orca.so"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Orca Whirlpool concentrated LP positions.

        Strategy: Try REST API first for position details, fall back to on-chain detection.
        """
        positions = await self._try_api(address)
        if positions is not None:
            return positions

        return await self._detect_onchain(address)

    async def _try_api(self, address: str) -> List[ProtocolPosition]:
        """Try Orca Whirlpool API for detailed position data."""
        try:
            client = get_client("orca", timeout=15.0)

            # Try portfolio/positions endpoint
            response = await client.get(
                f"{ORCA_WHIRLPOOL_API}/v1/whirlpool/positions",
                params={"wallet": address},
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                # Try alternate endpoint
                response = await client.get(
                    f"{ORCA_API_BASE}/portfolio/positions",
                    params={"address": address},
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
            for i, pos in enumerate(raw_positions):
                # Pool/pair info
                token_a_mint = pos.get("tokenMintA", pos.get("token_a_mint", pos.get("tokenA", {}).get("mint", "")))
                token_b_mint = pos.get("tokenMintB", pos.get("token_b_mint", pos.get("tokenB", {}).get("mint", "")))
                token_a_symbol = KNOWN_TOKEN_MINTS.get(token_a_mint, pos.get("tokenA", {}).get("symbol", pos.get("symbolA", "?")))
                token_b_symbol = KNOWN_TOKEN_MINTS.get(token_b_mint, pos.get("tokenB", {}).get("symbol", pos.get("symbolB", "?")))

                pair_name = f"{token_a_symbol}/{token_b_symbol}"

                # Token amounts in position
                amount_a = float(pos.get("amountA", pos.get("tokenA", {}).get("amount", pos.get("token_a_amount", 0))) or 0)
                amount_b = float(pos.get("amountB", pos.get("tokenB", {}).get("amount", pos.get("token_b_amount", 0))) or 0)

                # USD values
                value_a = float(pos.get("valueA", pos.get("tokenA", {}).get("valueUsd", 0)) or 0)
                value_b = float(pos.get("valueB", pos.get("tokenB", {}).get("valueUsd", 0)) or 0)
                total_value = float(pos.get("totalValueUsd", pos.get("value_usd", 0)) or 0)
                if total_value == 0:
                    total_value = value_a + value_b

                # Tick range (concentrated liquidity bounds)
                tick_lower = pos.get("tickLowerIndex", pos.get("tick_lower", None))
                tick_upper = pos.get("tickUpperIndex", pos.get("tick_upper", None))
                current_tick = pos.get("currentTick", pos.get("whirlpool_current_tick", None))

                # Price range
                price_lower = float(pos.get("priceLower", pos.get("price_lower", 0)) or 0)
                price_upper = float(pos.get("priceUpper", pos.get("price_upper", 0)) or 0)
                current_price = float(pos.get("currentPrice", pos.get("current_price", 0)) or 0)

                # Check if in range
                in_range = True
                if tick_lower is not None and tick_upper is not None and current_tick is not None:
                    in_range = int(tick_lower) <= int(current_tick) <= int(tick_upper)
                elif price_lower > 0 and price_upper > 0 and current_price > 0:
                    in_range = price_lower <= current_price <= price_upper

                # Fees
                fees_a = float(pos.get("feesOwedA", pos.get("fees_a", pos.get("unclaimedFeesA", 0))) or 0)
                fees_b = float(pos.get("feesOwedB", pos.get("fees_b", pos.get("unclaimedFeesB", 0))) or 0)
                fees_usd = float(pos.get("feesUsd", pos.get("fees_usd", 0)) or 0)

                # Liquidity
                liquidity = pos.get("liquidity", None)

                # Position account
                position_pubkey = pos.get("address", pos.get("position_address", pos.get("pubkey", "")))
                whirlpool_pubkey = pos.get("whirlpool", pos.get("whirlpool_address", ""))

                underlying = []
                if amount_a > 0 or value_a > 0:
                    underlying.append({
                        "symbol": token_a_symbol,
                        "amount": round(amount_a, 6),
                        "value_usd": round(value_a, 2),
                    })
                if amount_b > 0 or value_b > 0:
                    underlying.append({
                        "symbol": token_b_symbol,
                        "amount": round(amount_b, 6),
                        "value_usd": round(value_b, 2),
                    })

                extra = {
                    "pair": pair_name,
                    "in_range": in_range,
                    "position_index": i,
                    "source": "api",
                }

                if position_pubkey:
                    extra["position_account"] = position_pubkey
                if whirlpool_pubkey:
                    extra["whirlpool"] = whirlpool_pubkey
                if price_lower > 0:
                    extra["price_lower"] = round(price_lower, 6)
                if price_upper > 0:
                    extra["price_upper"] = round(price_upper, 6)
                if current_price > 0:
                    extra["current_price"] = round(current_price, 6)
                if fees_usd > 0 or fees_a > 0 or fees_b > 0:
                    extra["unclaimed_fees_usd"] = round(fees_usd, 2) if fees_usd > 0 else round(fees_a + fees_b, 2)
                if liquidity:
                    extra["liquidity"] = str(liquidity)

                positions.append(ProtocolPosition(
                    protocol="Orca",
                    chain="solana",
                    position_type=PositionType.CONCENTRATED_LP,
                    token_symbol="ORCA-LP",
                    token_name=f"Orca {pair_name} LP",
                    amount=amount_a + amount_b if (amount_a + amount_b) > 0 else 1.0,
                    value_usd=round(total_value, 2),
                    underlying_tokens=underlying,
                    pending_rewards=round(fees_usd, 2) if fees_usd > 0 else None,
                    reward_token="USD" if fees_usd > 0 else None,
                    token_id=position_pubkey,
                    extra=extra,
                ))

            return positions if positions else None

        except Exception as e:
            logger.debug(f"Orca API unavailable for {address[:20]}...: {e}")
            return None

    async def _detect_onchain(self, address: str) -> List[ProtocolPosition]:
        """Fallback: detect position existence on-chain via getProgramAccounts."""
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
                    WHIRLPOOL_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": 216},
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
                        "note": "API unavailable - showing position existence only",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Orca positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(OrcaAdapter())
