"""
Off-Chain Balance Helpers

Standalone helper functions extracted from SnapshotService for calculating
off-chain component values (staking, DeFi, exchange, NFTs) from cached data.

Used by offchain_collector.py. These are pure async functions that read from
cache/APIs and don't depend on any class state.
"""

import logging

logger = logging.getLogger(__name__)


async def _stale_fallback(key: str, user_id=None):
    """Try stale cache as fallback when fresh cache misses."""
    from database import get_stale_cache
    data, _ = await get_stale_cache(key, user_id=user_id)
    return data


async def get_staking_value(prices: dict, user_id: int = None) -> float:
    """Get total staking value from cached data (including pending rewards)."""
    try:
        from database import get_cache, get_all_wallets

        wallets = await get_all_wallets(user_id=user_id)
        total_usd = 0.0

        for wallet in wallets:
            if wallet['blockchain'] == 'cardano':
                cache_key = f"staking_positions_{wallet['address']}"
                # Staking endpoint caches without user_id, try both
                cached = await get_cache(cache_key, user_id=user_id)
                if not cached:
                    cached = await get_cache(cache_key)
                if not cached:
                    cached = await _stale_fallback(cache_key, user_id=user_id)
                    if not cached:
                        cached = await _stale_fallback(cache_key)
                if not cached:
                    continue
                # Cache structure: {protocols: {ProtocolName: {staked: [{token, amount}], reward_token, pending_rewards}}}
                for protocol_name, protocol_data in (cached.get('protocols') or {}).items():
                    for stake in (protocol_data.get('staked') or []):
                        amount = float(stake.get('amount', 0))
                        token = stake.get('token', 'ADA')
                        price_data = prices.get(token, {})
                        price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                        total_usd += amount * price
                    # Include pending rewards (matches web dashboard logic)
                    reward_token = protocol_data.get('reward_token')
                    pending_rewards = float(protocol_data.get('pending_rewards', 0))
                    if reward_token and pending_rewards > 0:
                        price_data = prices.get(reward_token, {})
                        price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                        total_usd += pending_rewards * price

        return total_usd
    except Exception as e:
        logger.debug(f"Could not get staking value: {e}")
        return 0.0


async def get_defi_value(prices: dict, user_id: int = None) -> float:
    """Get total DeFi value from cached data."""
    try:
        from database import get_cache

        cached = await get_cache("defi_summary", user_id=user_id)
        if not cached:
            cached = await _stale_fallback("defi_summary", user_id=user_id)
        if not cached:
            return 0.0
        # Use pre-calculated total if available
        if 'total_value_usd' in cached:
            return float(cached['total_value_usd'])
        # Calculate from positions using prices
        total = 0.0
        positions_by_category = cached.get('positions_by_category', {})
        for category, positions in positions_by_category.items():
            for pos in positions:
                token = pos.get('token') or pos.get('asset_name', '')
                quantity = float(pos.get('quantity', 0))
                price_data = prices.get(token, {})
                price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                total += quantity * price
        return total
    except Exception as e:
        logger.debug(f"Could not get DeFi value: {e}")
        return 0.0


async def get_nft_value(ada_price: float, user_id: int = None) -> float:
    """Get total NFT value from cached data."""
    try:
        from services.nft import nft_service

        summary = await nft_service.get_nft_summary(user_id=user_id)
        total_ada = summary.get('total_value_ada', 0)
        return total_ada * ada_price
    except Exception as e:
        logger.debug(f"Could not get NFT value: {e}")
        return 0.0


async def get_exchange_value(prices: dict, user_id: int = None) -> float:
    """Get total exchange value from cached data (all exchanges)."""
    try:
        from database import get_cache

        total = 0.0

        # Check all exchange cache keys
        exchange_keys = [
            "coinbase_portfolio",
            "binance_portfolio",
            "binance_us_portfolio",
            "okx_portfolio",
            "bitget_portfolio",
            "gate_portfolio",
            "kucoin_portfolio",
        ]
        for key in exchange_keys:
            cached = await get_cache(key, user_id=user_id)
            if not cached:
                cached = await _stale_fallback(key, user_id=user_id)
            if cached and 'total_usd' in cached:
                total += float(cached['total_usd'])

        return total
    except Exception as e:
        logger.debug(f"Could not get exchange value: {e}")
        return 0.0
