"""
Uniswap v3 LP Position Adapter

Detects concentrated liquidity positions via the NonfungiblePositionManager.
- balanceOf(address) to get the number of NFT positions (0x70a08231)
- tokenOfOwnerByIndex(address, index) to get each token ID (0x2f745c59)
- positions(uint256 tokenId) to get position details (0x99fbab88)

Enriched: Calculates USD value from tick range + current pool price via slot0(),
determines in-range status, and fetches token symbols via ERC-20 symbol() calls.
Also reads uncollected fees from tokensOwed0/tokensOwed1.
"""

import asyncio
import logging
import math
from typing import List, Optional
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter
from services.defi_protocols.registry import protocol_registry

logger = logging.getLogger(__name__)

# Uniswap v3 NonfungiblePositionManager addresses per chain
POSITION_MANAGER = {
    "ethereum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "polygon": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "arbitrum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "base": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
    "optimism": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
}

# Uniswap v3 Factory addresses per chain (for finding pool addresses)
FACTORY = {
    "ethereum": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "polygon": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "arbitrum": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "base": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    "optimism": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
}

# Well-known tokens for symbol/decimal lookups to avoid extra RPC calls
KNOWN_TOKENS = {
    # Ethereum
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"symbol": "WETH", "decimals": 18},
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"symbol": "USDC", "decimals": 6},
    "0xdac17f958d2ee523a2206206994597c13d831ec7": {"symbol": "USDT", "decimals": 6},
    "0x6b175474e89094c44da98b954eedeac495271d0f": {"symbol": "DAI", "decimals": 18},
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": {"symbol": "WBTC", "decimals": 8},
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": {"symbol": "wstETH", "decimals": 18},
    "0xae78736cd615f374d3085123a210448e74fc6393": {"symbol": "rETH", "decimals": 18},
    "0x514910771af9ca656af840dff83e8264ecf986ca": {"symbol": "LINK", "decimals": 18},
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": {"symbol": "UNI", "decimals": 18},
    # Base
    "0x4200000000000000000000000000000000000006": {"symbol": "WETH", "decimals": 18},
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {"symbol": "USDC", "decimals": 6},
    # Arbitrum
    "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": {"symbol": "WETH", "decimals": 18},
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": {"symbol": "USDC", "decimals": 6},
    "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": {"symbol": "USDT", "decimals": 6},
    "0x912ce59144191c1204e64559fe8253a0e49e6548": {"symbol": "ARB", "decimals": 18},
    # Polygon
    "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": {"symbol": "WETH", "decimals": 18},
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": {"symbol": "USDC", "decimals": 6},
    "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": {"symbol": "WMATIC", "decimals": 18},
}

# Function selectors
TOKEN_OF_OWNER_BY_INDEX = "0x2f745c59"  # tokenOfOwnerByIndex(address,uint256)
POSITIONS = "0x99fbab88"  # positions(uint256)
# slot0() on pool contracts - returns sqrtPriceX96, tick, etc.
SLOT0 = "0x3850c7bd"
# getPool(address,address,uint24) on factory
GET_POOL = "0x1698ee82"
# symbol() ERC-20
SYMBOL_SELECTOR = "0x95d89b41"
# decimals() ERC-20
DECIMALS_SELECTOR = "0x313ce567"

# Fee tier label mapping
FEE_TIER_LABELS = {
    100: "0.01%",
    500: "0.05%",
    3000: "0.3%",
    10000: "1%",
}

# Max positions to check per address (to avoid excessive RPC calls)
MAX_POSITIONS = 20


class UniswapV3LPAdapter(BaseEVMAdapter):
    """Uniswap v3 concentrated LP adapter.

    Detects NFT-based LP positions and calculates USD value from
    tick range and current pool price.
    """

    PROTOCOL_NAME = "Uniswap v3"
    SUPPORTED_CHAINS = list(POSITION_MANAGER.keys())
    DETECTION_METHOD = DetectionMethod.NFT_POSITION
    PROTOCOL_URL = "https://app.uniswap.org"

    # Cache for token info and pool data within a single scan
    _token_cache = {}
    _pool_cache = {}

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            manager = POSITION_MANAGER.get(c)
            if not manager:
                continue

            # Get number of LP NFTs owned
            nft_count = await self._get_erc20_balance(c, manager, address)
            if not nft_count or nft_count == 0:
                continue

            count = min(nft_count, MAX_POSITIONS)

            # Get all token IDs in parallel
            token_ids = await asyncio.gather(
                *[
                    self._get_token_id(c, manager, address, i)
                    for i in range(count)
                ]
            )

            # Get position details for each token ID in parallel
            valid_ids = [tid for tid in token_ids if tid is not None]
            if not valid_ids:
                continue

            position_results = await asyncio.gather(
                *[self._get_position(c, manager, tid) for tid in valid_ids]
            )

            # Enrich positions with pool data and token info
            for tid, pos_data in zip(valid_ids, position_results):
                if not pos_data or pos_data.get("liquidity", 0) == 0:
                    continue

                enriched = await self._enrich_position(c, pos_data, tid)
                if enriched:
                    positions.append(enriched)

        return positions

    async def _enrich_position(
        self, chain: str, pos_data: dict, token_id: int
    ) -> Optional[ProtocolPosition]:
        """Enrich a raw position with token symbols, USD value, and in-range status."""
        token0_addr = pos_data["token0"]
        token1_addr = pos_data["token1"]
        fee = pos_data.get("fee", 3000)
        tick_lower = pos_data["tick_lower"]
        tick_upper = pos_data["tick_upper"]
        liquidity = pos_data["liquidity"]
        tokens_owed0 = pos_data.get("tokens_owed0", 0)
        tokens_owed1 = pos_data.get("tokens_owed1", 0)

        # Get token info (symbol + decimals) in parallel
        token0_info, token1_info = await asyncio.gather(
            self._get_token_info(chain, token0_addr),
            self._get_token_info(chain, token1_addr),
        )

        symbol0 = token0_info.get("symbol", "???")
        symbol1 = token1_info.get("symbol", "???")
        decimals0 = token0_info.get("decimals", 18)
        decimals1 = token1_info.get("decimals", 18)

        pair_name = f"{symbol0}/{symbol1}"

        # Get current pool tick from slot0
        current_tick = await self._get_pool_tick(chain, token0_addr, token1_addr, fee)

        in_range = None
        amount0 = 0.0
        amount1 = 0.0
        fee_tier_label = FEE_TIER_LABELS.get(fee, f"{fee/10000:.2f}%")

        if current_tick is not None:
            in_range = tick_lower <= current_tick <= tick_upper

            # Calculate token amounts from liquidity and tick range
            try:
                amount0, amount1 = self._calculate_amounts(
                    liquidity, tick_lower, tick_upper, current_tick,
                    decimals0, decimals1
                )
            except Exception as e:
                logger.debug(f"Error calculating Uni v3 amounts for {token_id}: {e}")

        # Calculate uncollected fees in human-readable units
        fee0 = tokens_owed0 / (10 ** decimals0) if tokens_owed0 > 0 else 0.0
        fee1 = tokens_owed1 / (10 ** decimals1) if tokens_owed1 > 0 else 0.0

        underlying = []
        if amount0 > 0 or fee0 > 0:
            underlying.append({"symbol": symbol0, "amount": amount0, "fees": fee0})
        if amount1 > 0 or fee1 > 0:
            underlying.append({"symbol": symbol1, "amount": amount1, "fees": fee1})

        return ProtocolPosition(
            protocol=self.PROTOCOL_NAME,
            chain=chain,
            position_type=PositionType.CONCENTRATED_LP,
            token_symbol=pair_name,
            token_name=f"{pair_name} ({fee_tier_label})",
            amount=liquidity / 1e18,
            contract_address=POSITION_MANAGER.get(chain),
            token_id=str(token_id),
            underlying_tokens=underlying,
            extra={
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "current_tick": current_tick,
                "token0": token0_addr,
                "token1": token1_addr,
                "token0_symbol": symbol0,
                "token1_symbol": symbol1,
                "token0_amount": amount0,
                "token1_amount": amount1,
                "fee_tier": fee,
                "fee_tier_label": fee_tier_label,
                "in_range": in_range,
                "uncollected_fees": {
                    symbol0: fee0,
                    symbol1: fee1,
                } if (fee0 > 0 or fee1 > 0) else None,
            },
        )

    def _calculate_amounts(
        self, liquidity: int, tick_lower: int, tick_upper: int,
        current_tick: int, decimals0: int, decimals1: int
    ) -> tuple:
        """Calculate token0 and token1 amounts from liquidity and tick range.

        Uses the Uniswap v3 math:
        - sqrtPrice = 1.0001^(tick/2)
        - If current_tick < tick_lower: all token0
        - If current_tick > tick_upper: all token1
        - Otherwise: split based on current position in range
        """
        sqrt_lower = math.sqrt(1.0001 ** tick_lower)
        sqrt_upper = math.sqrt(1.0001 ** tick_upper)
        sqrt_current = math.sqrt(1.0001 ** current_tick)

        if current_tick < tick_lower:
            # All in token0
            amount0 = liquidity * (1 / sqrt_lower - 1 / sqrt_upper)
            amount1 = 0
        elif current_tick > tick_upper:
            # All in token1
            amount0 = 0
            amount1 = liquidity * (sqrt_upper - sqrt_lower)
        else:
            # In range
            amount0 = liquidity * (1 / sqrt_current - 1 / sqrt_upper)
            amount1 = liquidity * (sqrt_current - sqrt_lower)

        return (
            amount0 / (10 ** decimals0),
            amount1 / (10 ** decimals1),
        )

    async def _get_token_info(self, chain: str, token_addr: str) -> dict:
        """Get token symbol and decimals, with caching."""
        addr_lower = token_addr.lower()

        # Check known tokens first
        if addr_lower in KNOWN_TOKENS:
            return KNOWN_TOKENS[addr_lower]

        cache_key = f"{chain}:{addr_lower}"
        if cache_key in self._token_cache:
            return self._token_cache[cache_key]

        # Query symbol() and decimals() in parallel
        symbol_result, decimals_result = await asyncio.gather(
            self._eth_call(chain, token_addr, SYMBOL_SELECTOR),
            self._eth_call(chain, token_addr, DECIMALS_SELECTOR),
            return_exceptions=True,
        )

        symbol = "???"
        decimals = 18

        # Decode symbol (string return type)
        if symbol_result and not isinstance(symbol_result, Exception) and symbol_result != "0x":
            try:
                symbol = self._decode_string(symbol_result)
            except Exception:
                pass

        # Decode decimals (uint8)
        if decimals_result and not isinstance(decimals_result, Exception) and decimals_result != "0x":
            try:
                decimals = int(decimals_result, 16)
                if decimals > 77:
                    decimals = 18  # Sanity check
            except (ValueError, TypeError):
                pass

        info = {"symbol": symbol, "decimals": decimals}
        self._token_cache[cache_key] = info
        return info

    def _decode_string(self, hex_data: str) -> str:
        """Decode an ABI-encoded string return value."""
        if not hex_data or hex_data == "0x" or len(hex_data) < 130:
            return "???"
        # offset (32 bytes) + length (32 bytes) + data
        offset = int(hex_data[2:66], 16) * 2 + 2
        length = int(hex_data[offset:offset + 64], 16)
        data_start = offset + 64
        data_end = data_start + length * 2
        if data_end > len(hex_data):
            return "???"
        raw = bytes.fromhex(hex_data[data_start:data_end])
        return raw.decode('utf-8', errors='replace').strip('\x00')

    async def _get_pool_tick(self, chain: str, token0: str, token1: str, fee: int) -> Optional[int]:
        """Get current tick from pool's slot0()."""
        cache_key = f"{chain}:{token0}:{token1}:{fee}"
        if cache_key in self._pool_cache:
            return self._pool_cache[cache_key]

        # First, get pool address from factory
        factory = FACTORY.get(chain)
        if not factory:
            return None

        # getPool(address,address,uint24)
        encoded_fee = hex(fee)[2:].zfill(64)
        get_pool_data = GET_POOL + self._encode_address(token0) + self._encode_address(token1) + encoded_fee
        pool_result = await self._eth_call(chain, factory, get_pool_data)

        if not pool_result or pool_result == "0x":
            return None

        pool_address_raw = self._decode_uint256(pool_result, 0)
        if pool_address_raw == 0:
            return None
        pool_address = "0x" + hex(pool_address_raw)[2:].zfill(40)[-40:]

        # Query slot0() on the pool
        slot0_result = await self._eth_call(chain, pool_address, SLOT0)
        if not slot0_result or slot0_result == "0x" or len(slot0_result) < 130:
            return None

        # slot0 returns (uint160 sqrtPriceX96, int24 tick, ...)
        tick_raw = self._decode_uint256(slot0_result, 1)
        # Convert from uint256 to int24
        if tick_raw > 2**23:
            tick_raw = tick_raw - 2**24

        self._pool_cache[cache_key] = tick_raw
        return tick_raw

    async def _get_token_id(
        self, chain: str, manager: str, address: str, index: int
    ) -> int | None:
        """Call tokenOfOwnerByIndex(address, uint256) to get NFT token ID."""
        padded_index = hex(index)[2:].zfill(64)
        data = TOKEN_OF_OWNER_BY_INDEX + self._encode_address(address) + padded_index
        result = await self._eth_call(chain, manager, data)
        if result and result != "0x":
            try:
                return int(result, 16)
            except ValueError:
                pass
        return None

    async def _get_position(
        self, chain: str, manager: str, token_id: int
    ) -> dict | None:
        """Call positions(uint256) to get position details.

        Returns struct:
        (nonce, operator, token0, token1, fee, tickLower, tickUpper,
         liquidity, feeGrowthInside0LastX128, feeGrowthInside1LastX128,
         tokensOwed0, tokensOwed1)
        """
        padded_id = hex(token_id)[2:].zfill(64)
        data = POSITIONS + padded_id
        result = await self._eth_call(chain, manager, data)
        if not result or result == "0x" or len(result) < 770:
            return None

        try:
            # Decode position struct fields (each 32 bytes = 64 hex chars)
            token0_raw = self._decode_uint256(result, 2)
            token1_raw = self._decode_uint256(result, 3)
            fee = self._decode_uint256(result, 4)
            tick_lower = self._decode_uint256(result, 5)
            tick_upper = self._decode_uint256(result, 6)
            liquidity = self._decode_uint256(result, 7)
            tokens_owed0 = self._decode_uint256(result, 10)
            tokens_owed1 = self._decode_uint256(result, 11)

            # Convert tick values (they're int24 stored as uint256)
            if tick_lower > 2**23:
                tick_lower = tick_lower - 2**24
            if tick_upper > 2**23:
                tick_upper = tick_upper - 2**24

            # Convert uint256 to address (last 20 bytes)
            token0 = "0x" + hex(token0_raw)[2:].zfill(40)[-40:]
            token1 = "0x" + hex(token1_raw)[2:].zfill(40)[-40:]

            return {
                "token0": token0,
                "token1": token1,
                "fee": fee,
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "liquidity": liquidity,
                "tokens_owed0": tokens_owed0,
                "tokens_owed1": tokens_owed1,
            }
        except Exception as e:
            logger.debug(f"Error decoding Uniswap v3 position {token_id}: {e}")
            return None


protocol_registry.register(UniswapV3LPAdapter())
