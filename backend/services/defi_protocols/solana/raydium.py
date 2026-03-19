"""Raydium adapter - LP token position detection with underlying value calculation."""

import logging
from typing import List, Optional, Dict
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Raydium AMM v4 program ID
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

# Raydium REST API
RAYDIUM_API_BASE = "https://api-v3.raydium.io"

# Known Raydium LP token mints for major pools
KNOWN_LP_MINTS = {
    "RAY-SOL LP": "89ZKE4aoyfLBe2RuV6NpNN2629TNjKdzB9DSi5mLG3HM",
    "RAY-USDC LP": "FbC6K13MzHvN42bXrtGaWsvZY9fxrackRSZcBGfjPc7Y",
    "RAY-USDT LP": "C3sT1R3nsw4AVdepvLTLKr5Gvszr7jufyBWUCvy4TUvT",
    "SOL-USDC LP": "8HoQnePLqPj4M7PUDzfw8e3Ymdwgc7NLGnaTUapubyvu",
    "SOL-USDT LP": "Epm4KfTj4DMrvqn6Bwg2Tr2N8vhQuNbuK8bESFp4k33K",
}

# Reverse lookup: mint → pool name
LP_MINT_TO_POOL = {v: k for k, v in KNOWN_LP_MINTS.items()}

# Pool token pair info
POOL_TOKEN_PAIRS = {
    "RAY-SOL LP": ("RAY", "SOL"),
    "RAY-USDC LP": ("RAY", "USDC"),
    "RAY-USDT LP": ("RAY", "USDT"),
    "SOL-USDC LP": ("SOL", "USDC"),
    "SOL-USDT LP": ("SOL", "USDT"),
}


class RaydiumAdapter(BaseSolanaAdapter):
    PROTOCOL_NAME = "Raydium"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://raydium.io"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect Raydium LP positions with underlying value calculation.

        Strategy: Check LP token balances, then try to enrich with pool data from API.
        """
        positions = []
        pool_data_cache = {}

        # Try to pre-fetch pool data from Raydium API
        pool_data_cache = await self._fetch_pool_data()

        for pool_name, lp_mint in KNOWN_LP_MINTS.items():
            balance = await self._get_spl_balance(address, lp_mint)
            if not balance or balance <= 0:
                continue

            token_pair = POOL_TOKEN_PAIRS.get(pool_name, ("?", "?"))
            token_a_symbol, token_b_symbol = token_pair

            # Try to calculate underlying amounts from pool data
            underlying_tokens = []
            value_usd = 0.0
            pool_share_pct = 0.0
            pool_info = pool_data_cache.get(lp_mint, {})

            if pool_info:
                lp_supply = float(pool_info.get("lp_supply", pool_info.get("lpSupply", 0)) or 0)
                if lp_supply > 0:
                    share = balance / lp_supply
                    pool_share_pct = share * 100

                    # Token A amount
                    reserve_a = float(pool_info.get("reserve_a", pool_info.get("mintAmountA", 0)) or 0)
                    amount_a = reserve_a * share
                    price_a = float(pool_info.get("price_a", pool_info.get("mintPriceA", 0)) or 0)
                    value_a = amount_a * price_a

                    # Token B amount
                    reserve_b = float(pool_info.get("reserve_b", pool_info.get("mintAmountB", 0)) or 0)
                    amount_b = reserve_b * share
                    price_b = float(pool_info.get("price_b", pool_info.get("mintPriceB", 0)) or 0)
                    value_b = amount_b * price_b

                    value_usd = value_a + value_b

                    if amount_a > 0:
                        underlying_tokens.append({
                            "symbol": token_a_symbol,
                            "amount": round(amount_a, 6),
                            "value_usd": round(value_a, 2),
                        })
                    if amount_b > 0:
                        underlying_tokens.append({
                            "symbol": token_b_symbol,
                            "amount": round(amount_b, 6),
                            "value_usd": round(value_b, 2),
                        })

                tvl = float(pool_info.get("tvl", 0) or 0)
                apy = float(pool_info.get("apy", pool_info.get("apr", 0)) or 0)
            else:
                tvl = 0
                apy = 0

            positions.append(ProtocolPosition(
                protocol="Raydium",
                chain="solana",
                position_type=PositionType.LP_POSITION,
                token_symbol="RAY-LP",
                token_name=pool_name,
                amount=balance,
                value_usd=round(value_usd, 2),
                underlying_tokens=underlying_tokens,
                apy=apy if apy > 0 else None,
                contract_address=lp_mint,
                extra={
                    "program_id": RAYDIUM_AMM_PROGRAM,
                    "pool": pool_name,
                    "pool_share_pct": round(pool_share_pct, 6) if pool_share_pct > 0 else None,
                    "tvl": round(tvl, 2) if tvl > 0 else None,
                    "source": "api" if pool_info else "token_balance",
                },
            ))

        return positions

    async def _fetch_pool_data(self) -> Dict[str, dict]:
        """Fetch pool reserve and price data from Raydium API."""
        try:
            client = get_client("raydium", timeout=15.0)

            # Build comma-separated list of pool IDs (LP mints)
            lp_mints = list(KNOWN_LP_MINTS.values())

            # Try Raydium V3 API for pool info
            response = await client.get(
                f"{RAYDIUM_API_BASE}/pools/info/lps",
                params={"lps": ",".join(lp_mints)},
                headers={"Accept": "application/json"}
            )

            if response.status_code != 200:
                # Try alternate endpoint
                response = await client.get(
                    f"{RAYDIUM_API_BASE}/main/pairs",
                    headers={"Accept": "application/json"}
                )
                if response.status_code != 200:
                    return {}

            data = response.json()
            pool_map = {}

            # Parse response based on format
            pools = data if isinstance(data, list) else data.get("data", data.get("pools", []))

            if isinstance(pools, dict):
                # Key-value format: {lp_mint: pool_data}
                for lp_mint, pool_info in pools.items():
                    if lp_mint in LP_MINT_TO_POOL:
                        pool_map[lp_mint] = pool_info
            elif isinstance(pools, list):
                for pool in pools:
                    lp_mint = pool.get("lpMint", pool.get("lp_mint", ""))
                    if lp_mint in LP_MINT_TO_POOL:
                        pool_map[lp_mint] = pool

            return pool_map

        except Exception as e:
            logger.debug(f"Raydium API unavailable: {e}")
            return {}


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(RaydiumAdapter())
