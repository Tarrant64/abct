"""
DEPRECATED: V1 Snapshot Service

This module is deprecated. V1 snapshots have been replaced by:
  - offchain_collector.py + offchain_helpers.py (off-chain data collection)
  - engine/materializer.py (on-chain materialization to wallet_daily_balances)

Helper methods have been extracted to services/offchain_helpers.py.
Do not add new code here. Kept for reference and migration script compatibility.

Original description:
Portfolio Snapshot Service - Captures portfolio value every 2 hours.
Snapshots are stored per-day (one per day) but updated every 2 hours
to keep values current throughout the day.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    save_portfolio_snapshot,
    get_portfolio_history,
    get_latest_snapshot_date,
    get_latest_snapshot_time,
    get_all_wallets,
    get_wallet_balance
)

logger = logging.getLogger(__name__)

# Central Time zone (handles CST/CDT automatically)
CT_TIMEZONE = ZoneInfo("America/Chicago")
SNAPSHOT_INTERVAL_HOURS = 2  # Update snapshot every 2 hours


class SnapshotService:
    """Service for managing daily portfolio snapshots."""

    def __init__(self):
        self.pricing_service = None
        self.nft_service = None

    async def _get_pricing_service(self):
        """Lazy load pricing service to avoid circular imports."""
        if self.pricing_service is None:
            from services.pricing import pricing_service
            self.pricing_service = pricing_service
        return self.pricing_service

    async def _get_nft_service(self):
        """Lazy load NFT service to avoid circular imports."""
        if self.nft_service is None:
            from services.nft import nft_service
            self.nft_service = nft_service
        return self.nft_service

    async def should_create_snapshot(self, user_id: int = None) -> bool:
        """Check if we should create or update a snapshot for a user."""
        now_ct = datetime.now(CT_TIMEZONE)
        today = str(now_ct.date())

        # Get the latest snapshot info for this user
        latest_date = await get_latest_snapshot_date(user_id=user_id)
        latest_time = await get_latest_snapshot_time(user_id=user_id)

        # If no snapshot exists at all, create one
        if not latest_date:
            return True

        # If today's snapshot doesn't exist, create one
        if latest_date != today:
            return True

        # If today's snapshot exists, check if it's older than 4 hours
        if latest_time:
            try:
                # Parse the snapshot time
                snapshot_dt = datetime.fromisoformat(latest_time)
                # Make sure it's timezone-aware
                if snapshot_dt.tzinfo is None:
                    snapshot_dt = snapshot_dt.replace(tzinfo=CT_TIMEZONE)

                hours_since_snapshot = (now_ct - snapshot_dt).total_seconds() / 3600

                if hours_since_snapshot >= SNAPSHOT_INTERVAL_HOURS:
                    logger.info(f"Snapshot is {hours_since_snapshot:.1f} hours old, updating...")
                    return True
                else:
                    logger.debug(f"Snapshot is {hours_since_snapshot:.1f} hours old, still fresh")
                    return False
            except Exception as e:
                logger.warning(f"Could not parse snapshot time: {e}")
                return True

        return False

    async def create_snapshot(self, user_id: int = None, force: bool = False) -> dict:
        """
        Create a portfolio snapshot with current values.

        Now supports multiple snapshots per day for hourly tracking (1-day chart).
        Uses snapshot_time as the unique identifier instead of snapshot_date.

        Args:
            user_id: User ID to create snapshot for (required for multi-user)
            force: If True, create snapshot regardless of timing

        Returns:
            dict with snapshot data
        """
        now_ct = datetime.now(CT_TIMEZONE)
        today = str(now_ct.date())

        # Check if we should create/update (unless forcing)
        if not force:
            should_update = await self.should_create_snapshot(user_id=user_id)
            if not should_update:
                logger.info(f"Snapshot for {today} (user {user_id}) is still fresh, skipping")
                return {"status": "skipped", "date": today, "reason": "still_fresh"}

        logger.info(f"Creating portfolio snapshot for {today} (user {user_id})...")

        # Get pricing service
        pricing = await self._get_pricing_service()

        # Fetch current prices
        prices = await pricing.get_all_tracked_prices()
        ada_price = prices.get('ADA', {}).get('usd', 0)
        btc_price = prices.get('BTC', {}).get('usd', 0)
        eth_price = prices.get('ETH', {}).get('usd', 0)
        sol_price = prices.get('SOL', {}).get('usd', 0)

        # Calculate wallet totals for this user (all chains + on-chain tokens)
        wallets = await get_all_wallets(user_id=user_id)
        ada_amount = 0.0
        btc_amount = 0.0
        eth_amount = 0.0
        sol_amount = 0.0

        # Track all chain native coin amounts
        chain_amounts = {
            'cardano': 0.0, 'bitcoin': 0.0, 'ethereum': 0.0, 'solana': 0.0,
            'polygon': 0.0, 'base': 0.0, 'algorand': 0.0, 'bsc': 0.0,
            'arbitrum': 0.0, 'avalanche': 0.0, 'tron': 0.0,
        }

        # Native assets (tokens) value across all wallets
        native_assets_total_usd = 0.0

        for wallet in wallets:
            balance = await get_wallet_balance(wallet['id'])
            if balance:
                amount = float(balance['amount'])
                blockchain = wallet['blockchain']
                if blockchain in chain_amounts:
                    chain_amounts[blockchain] += amount
                # Keep legacy vars for snapshot columns
                if blockchain == 'cardano':
                    ada_amount += amount
                elif blockchain == 'bitcoin':
                    btc_amount += amount
                elif blockchain == 'ethereum':
                    eth_amount += amount
                elif blockchain == 'solana':
                    sol_amount += amount

            # Calculate on-chain token values (native_assets_value_usd)
            try:
                from routers.portfolio import calculate_wallet_native_assets_value
                token_value = await calculate_wallet_native_assets_value(
                    wallet['id'], wallet['blockchain'], user_id
                )
                native_assets_total_usd += token_value
            except Exception as e:
                logger.debug(f"Could not get native assets value for wallet {wallet['id']}: {e}")

        # Map chains to price symbols
        chain_price_map = {
            'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH', 'solana': 'SOL',
            'polygon': 'POL', 'base': 'ETH', 'algorand': 'ALGO', 'bsc': 'BNB',
            'arbitrum': 'ETH', 'avalanche': 'AVAX', 'tron': 'TRX',
        }

        # Calculate wallet USD values from all chains
        wallet_value_usd = 0.0
        for chain, amount in chain_amounts.items():
            if amount > 0:
                symbol = chain_price_map[chain]
                price = prices.get(symbol, {}).get('usd', 0)
                wallet_value_usd += amount * price

        # Add on-chain token values
        wallet_value_usd += native_assets_total_usd

        # Get staking value (from cache if available)
        staking_value_usd = await self._get_staking_value(prices, user_id=user_id)

        # Get DeFi value (from cache if available)
        defi_value_usd = await self._get_defi_value(prices, user_id=user_id)

        # Get exchange value (from cache if available)
        exchange_value_usd = await self._get_exchange_value(prices, user_id=user_id)

        # Get NFT value (from cache if available)
        nft_value_usd = await self._get_nft_value(ada_price, user_id=user_id)

        # Get tracked native tokens value (from cache if available)
        tracked_tokens_value_usd = await self._get_tracked_tokens_value(prices, user_id=user_id)

        # Get exchange quantities for historical recalculation
        exchange_quantities = await self._get_exchange_quantities(user_id=user_id)

        # Get tracked tokens quantities for historical recalculation
        tracked_tokens_quantities = await self._get_tracked_tokens_quantities(user_id=user_id)

        # Calculate total
        total_value_usd = (
            wallet_value_usd +
            staking_value_usd +
            defi_value_usd +
            exchange_value_usd +
            nft_value_usd +
            tracked_tokens_value_usd
        )

        # Get MATIC price for Polygon
        matic_price = prices.get('MATIC', {}).get('usd', 0) or prices.get('POL', {}).get('usd', 0)

        # Prepare snapshot data
        import json
        snapshot_data = {
            'snapshot_date': today,
            'snapshot_time': now_ct.isoformat(),
            'total_value_usd': total_value_usd,
            'ada_amount': ada_amount,
            'ada_price': ada_price,
            'btc_amount': btc_amount,
            'btc_price': btc_price,
            'eth_amount': eth_amount,
            'eth_price': eth_price,
            'sol_amount': sol_amount,
            'sol_price': sol_price,
            'matic_price': matic_price,
            'staking_value_usd': staking_value_usd,
            'defi_value_usd': defi_value_usd,
            'exchange_value_usd': exchange_value_usd,
            'nft_value_usd': nft_value_usd,
            'tracked_tokens_value_usd': tracked_tokens_value_usd,
            # Exchange quantities
            'exchange_btc_amount': exchange_quantities['btc'],
            'exchange_eth_amount': exchange_quantities['eth'],
            'exchange_ada_amount': exchange_quantities['ada'],
            'exchange_sol_amount': exchange_quantities['sol'],
            'exchange_matic_amount': exchange_quantities['matic'],
            'exchange_other_json': json.dumps(exchange_quantities['other']),
            # Tracked tokens quantities
            'tracked_tokens_json': json.dumps(tracked_tokens_quantities)
        }

        # Save to database with user_id
        await save_portfolio_snapshot(snapshot_data, user_id=user_id)
        logger.info(f"Portfolio snapshot saved for user {user_id}: ${total_value_usd:,.2f}")

        return {
            "status": "created",
            "date": today,
            "total_value_usd": total_value_usd,
            "breakdown": {
                "wallets": wallet_value_usd,
                "staking": staking_value_usd,
                "defi": defi_value_usd,
                "exchange": exchange_value_usd,
                "nfts": nft_value_usd,
                "tracked_tokens": tracked_tokens_value_usd
            }
        }

    async def _get_staking_value(self, prices: dict, user_id: int = None) -> float:
        """Get total staking value from cached data."""
        try:
            from database import get_cache
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
                        continue
                    # Cache structure: {protocols: {ProtocolName: {staked: [{token, amount}]}}}
                    for protocol_name, protocol_data in (cached.get('protocols') or {}).items():
                        for stake in (protocol_data.get('staked') or []):
                            amount = float(stake.get('amount', 0))
                            token = stake.get('token', 'ADA')
                            price_data = prices.get(token, {})
                            price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                            total_usd += amount * price

            return total_usd
        except Exception as e:
            logger.debug(f"Could not get staking value: {e}")
            return 0.0

    async def _get_defi_value(self, prices: dict, user_id: int = None) -> float:
        """Get total DeFi value from cached data."""
        try:
            from database import get_cache
            cached = await get_cache("defi_summary", user_id=user_id)
            if not cached:
                return 0.0
            # Use pre-calculated total if available
            if 'total_value_usd' in cached:
                return float(cached['total_value_usd'])
            # Calculate from positions using prices (defi/summary doesn't store total_value_usd)
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

    async def _get_exchange_value(self, prices: dict, user_id: int = None) -> float:
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
                if cached and 'total_usd' in cached:
                    total += float(cached['total_usd'])

            return total
        except Exception as e:
            logger.debug(f"Could not get exchange value: {e}")
            return 0.0

    async def _get_exchange_quantities(self, user_id: int = None) -> dict:
        """Get exchange asset quantities broken down by currency.

        Returns:
            dict with major coins (BTC, ETH, ADA, SOL, MATIC) as floats
            and other_currencies as dict {currency: amount}
        """
        try:
            from database import get_cache

            # Initialize result
            result = {
                'btc': 0.0,
                'eth': 0.0,
                'ada': 0.0,
                'sol': 0.0,
                'matic': 0.0,
                'other': {}  # Other currencies stored as dict
            }

            # Get Coinbase portfolio
            cached = await get_cache("coinbase_portfolio", user_id=user_id)
            if cached and 'assets' in cached:
                for asset in cached['assets']:
                    currency = asset.get('currency', '').upper()
                    balance = float(asset.get('balance', 0))

                    if balance == 0:
                        continue

                    # Map to major currencies
                    if currency == 'BTC':
                        result['btc'] += balance
                    elif currency == 'ETH':
                        result['eth'] += balance
                    elif currency == 'ADA':
                        result['ada'] += balance
                    elif currency == 'SOL':
                        result['sol'] += balance
                    elif currency in ['MATIC', 'POL']:  # Polygon rebrand
                        result['matic'] += balance
                    elif currency != 'USD':  # Skip USD, store others
                        result['other'][currency] = result['other'].get(currency, 0) + balance

            return result

        except Exception as e:
            logger.debug(f"Could not get exchange quantities: {e}")
            return {'btc': 0, 'eth': 0, 'ada': 0, 'sol': 0, 'matic': 0, 'other': {}}

    async def _get_tracked_tokens_value(self, prices: dict, user_id: int = None) -> float:
        """Get total tracked native tokens value from cached data.

        Note: Excludes DeFi tokens (those with policy_id in DEFI_PROTOCOLS)
        to prevent double-counting with defi_value_usd.
        """
        try:
            from database import get_cache
            from services.defi import DEFI_PROTOCOLS

            cached = await get_cache("native_assets_all", user_id=user_id)
            if cached and 'assets' in cached:
                from database import get_tracked_tokens
                tracked_tokens = await get_tracked_tokens(user_id=user_id)
                tracked_ids = {t['asset_id'] for t in tracked_tokens}

                total_usd = 0.0
                for asset in cached['assets']:
                    if asset.get('asset_id') in tracked_ids:
                        # Skip DeFi tokens - they're counted in defi_value_usd
                        policy_id = asset.get('policy_id', '')
                        if policy_id in DEFI_PROTOCOLS:
                            continue

                        # Get price by ticker
                        ticker = asset.get('ticker') or asset.get('asset_name', '').upper()
                        if ticker:
                            price_info = prices.get(ticker.upper())
                            if price_info and price_info.get('usd'):
                                decimals = asset.get('decimals') or 0
                                raw_qty = asset.get('total_quantity_raw', 0)
                                human_qty = raw_qty / (10 ** decimals) if decimals > 0 else raw_qty
                                total_usd += human_qty * price_info['usd']
                return total_usd
            return 0.0
        except Exception as e:
            logger.debug(f"Could not get tracked tokens value: {e}")
            return 0.0

    async def _get_tracked_tokens_quantities(self, user_id: int = None) -> dict:
        """Get tracked token quantities as {ticker: amount} dict.

        Note: Excludes DeFi tokens to prevent double-counting.

        Returns:
            dict mapping token tickers to quantities
        """
        try:
            from database import get_cache
            from services.defi import DEFI_PROTOCOLS

            quantities = {}

            cached = await get_cache("native_assets_all", user_id=user_id)
            if cached and 'assets' in cached:
                from database import get_tracked_tokens
                tracked_tokens = await get_tracked_tokens(user_id=user_id)
                tracked_ids = {t['asset_id'] for t in tracked_tokens}

                for asset in cached['assets']:
                    if asset.get('asset_id') in tracked_ids:
                        # Skip DeFi tokens - they're counted in defi_value_usd
                        policy_id = asset.get('policy_id', '')
                        if policy_id in DEFI_PROTOCOLS:
                            continue

                        ticker = asset.get('ticker') or asset.get('asset_name', '').upper()
                        if ticker:
                            decimals = asset.get('decimals') or 0
                            raw_qty = asset.get('total_quantity_raw', 0)
                            human_qty = raw_qty / (10 ** decimals) if decimals > 0 else raw_qty

                            if human_qty > 0:
                                quantities[ticker.upper()] = human_qty

            return quantities

        except Exception as e:
            logger.debug(f"Could not get tracked tokens quantities: {e}")
            return {}

    async def _get_nft_value(self, ada_price: float, user_id: int = None) -> float:
        """Get total NFT value from cached data."""
        try:
            nft_svc = await self._get_nft_service()
            summary = await nft_svc.get_nft_summary(user_id=user_id)
            total_ada = summary.get('total_value_ada', 0)
            return total_ada * ada_price
        except Exception as e:
            logger.debug(f"Could not get NFT value: {e}")
            return 0.0

    async def check_and_create_snapshot(self):
        """Called on app startup - creates or updates snapshot if needed for all users."""
        # Import here to avoid circular dependency
        from database import get_all_users

        try:
            # Get all non-demo users
            users = await get_all_users()
            non_demo_users = [u for u in users if not u.get('is_demo', False)]

            for user in non_demo_users:
                user_id = user['id']
                try:
                    if await self.should_create_snapshot(user_id=user_id):
                        logger.info(f"Creating/updating portfolio snapshot for user {user_id}...")
                        result = await self.create_snapshot(user_id=user_id, force=True)
                        logger.info(f"Snapshot result for user {user_id}: {result['status']}")
                except Exception as e:
                    logger.error(f"Failed to create snapshot for user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to check/create snapshots: {e}")
        else:
            logger.info("Portfolio snapshot is up to date (less than 2 hours old)")

    async def get_history(self, days: int = 7, user_id: int = None) -> list:
        """
        Get portfolio value history for charting.

        When days=1, returns hourly snapshots for the last 24 hours.
        When days>1, returns daily snapshots (one per day).

        Includes current portfolio value as "today" if no snapshot exists
        or if today's snapshot has $0 value.

        This now recalculates exchange and tracked token values using
        historical prices for accurate historical representation.
        """
        import json

        snapshots = await get_portfolio_history(days, user_id=user_id, hourly=(days == 1))

        # Safe float conversion - handles corrupted DB values like '{}'
        def sf(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        # Convert snapshots to history format with recalculated values
        history = []
        for s in snapshots:
            # Wallet values (already using historical prices from snapshot)
            # Ensure all values are floats (database may return strings or corrupted data)
            wallet_value = (
                sf(s['ada_amount']) * sf(s['ada_price']) +
                sf(s['btc_amount']) * sf(s['btc_price']) +
                sf(s['eth_amount']) * sf(s['eth_price']) +
                sf(s.get('sol_amount')) * sf(s.get('sol_price'))
            )

            # Exchange value: prefer stored aggregate (per-asset amounts may be corrupted
            # by migration 005 column reorder). Only recalculate if no stored value.
            stored_exchange_usd = sf(s.get('exchange_value_usd'))
            if stored_exchange_usd > 0:
                exchange_value = stored_exchange_usd
            else:
                # Fallback: recalculate from per-asset amounts (only for snapshots without aggregate)
                exchange_btc = sf(s.get('exchange_btc_amount'))
                exchange_eth = sf(s.get('exchange_eth_amount'))
                exchange_ada = sf(s.get('exchange_ada_amount'))
                exchange_sol = sf(s.get('exchange_sol_amount'))
                exchange_matic = sf(s.get('exchange_matic_amount'))

                exchange_value = (
                    exchange_btc * sf(s['btc_price']) +
                    exchange_eth * sf(s['eth_price']) +
                    exchange_ada * sf(s['ada_price']) +
                    exchange_sol * sf(s.get('sol_price')) +
                    exchange_matic * sf(s.get('matic_price'))
                )

            # Recalculate tracked tokens value using historical prices
            tracked_tokens_value = 0
            try:
                tracked_tokens = json.loads(s.get('tracked_tokens_json', '{}'))
                # For now we only have major coin historical prices
                # Tracked tokens would need their own historical price data
                # Use stored value as fallback
                tracked_tokens_value = sf(s.get('tracked_tokens_value_usd'))
            except Exception:
                tracked_tokens_value = sf(s.get('tracked_tokens_value_usd'))

            # Calculate total with recalculated values
            staking_usd = sf(s.get('staking_value_usd'))
            defi_usd = sf(s.get('defi_value_usd'))
            nft_usd = sf(s.get('nft_value_usd'))
            recalculated_total = (
                wallet_value +
                staking_usd +
                defi_usd +
                exchange_value +
                nft_usd +
                tracked_tokens_value
            )

            # Sanity check: migration 005 may have corrupted per-column data via
            # SELECT * with mismatched column order. If recalculated total is wildly
            # different from stored total, prefer the stored value (calculated at
            # snapshot time before any migration corruption).
            stored_total = sf(s.get('total_value_usd'))
            if stored_total > 0 and recalculated_total > stored_total * 5:
                # Recalculated is 5x+ higher than stored — likely corrupted columns
                total_value = stored_total
            elif stored_total > 0 and recalculated_total < stored_total * 0.1:
                # Recalculated is less than 10% of stored — likely missing components
                total_value = stored_total
            else:
                total_value = recalculated_total

            # For hourly data (days=1), use snapshot_time for labels
            # For daily data (days>1), use snapshot_date
            if days == 1:
                # Parse snapshot_time and format as hour label
                snapshot_dt = datetime.fromisoformat(s['snapshot_time'])
                if snapshot_dt.tzinfo is None:
                    snapshot_dt = snapshot_dt.replace(tzinfo=CT_TIMEZONE)
                date_label = snapshot_dt.isoformat()  # Frontend will format this
            else:
                date_label = s['snapshot_date']

            history.append({
                'date': date_label,
                'value': total_value,
                'breakdown': {
                    'wallets': wallet_value,
                    'staking': staking_usd,
                    'defi': defi_usd,
                    'exchange': exchange_value,
                    'nfts': nft_usd,
                    'tracked_tokens': tracked_tokens_value
                }
            })

        # Check if we need to add/update today's value with current portfolio
        today = str(datetime.now(CT_TIMEZONE).date())
        today_in_history = any(h['date'] == today for h in history)
        today_has_zero = any(h['date'] == today and h['value'] == 0 for h in history)

        # If no today or today is $0, calculate current portfolio value
        if not today_in_history or today_has_zero:
            current_value = await self._calculate_current_portfolio_value(user_id=user_id)

            if current_value and current_value['total'] > 0:
                today_data = {
                    'date': today,
                    'value': current_value['total'],
                    'breakdown': current_value['breakdown']
                }

                if today_has_zero:
                    # Replace the $0 entry with current value
                    history = [h if h['date'] != today else today_data for h in history]
                else:
                    # Add today's data point
                    history.append(today_data)

        return history

    async def _calculate_current_portfolio_value(self, user_id: int = None) -> dict:
        """Calculate current portfolio value with all components for a specific user.

        Args:
            user_id: User ID to calculate portfolio for

        Returns:
            dict with total value and breakdown
        """
        try:
            pricing = await self._get_pricing_service()
            prices = await pricing.get_all_tracked_prices()

            ada_price = prices.get('ADA', {}).get('usd', 0)

            # Calculate wallet totals across all chains + on-chain tokens
            wallets = await get_all_wallets(user_id=user_id)

            chain_amounts = {
                'cardano': 0.0, 'bitcoin': 0.0, 'ethereum': 0.0, 'solana': 0.0,
                'polygon': 0.0, 'base': 0.0, 'algorand': 0.0, 'bsc': 0.0,
                'arbitrum': 0.0, 'avalanche': 0.0, 'tron': 0.0,
            }
            chain_price_map = {
                'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH', 'solana': 'SOL',
                'polygon': 'POL', 'base': 'ETH', 'algorand': 'ALGO', 'bsc': 'BNB',
                'arbitrum': 'ETH', 'avalanche': 'AVAX', 'tron': 'TRX',
            }
            native_assets_total_usd = 0.0

            for wallet in wallets:
                balance = await get_wallet_balance(wallet['id'])
                if balance:
                    amount = float(balance['amount'])
                    blockchain = wallet['blockchain']
                    if blockchain in chain_amounts:
                        chain_amounts[blockchain] += amount

                try:
                    from routers.portfolio import calculate_wallet_native_assets_value
                    token_value = await calculate_wallet_native_assets_value(
                        wallet['id'], wallet['blockchain'], user_id
                    )
                    native_assets_total_usd += token_value
                except Exception:
                    pass

            wallet_value = 0.0
            for chain, amount in chain_amounts.items():
                if amount > 0:
                    symbol = chain_price_map[chain]
                    price = prices.get(symbol, {}).get('usd', 0)
                    wallet_value += amount * price
            wallet_value += native_assets_total_usd

            # Get other component values for this user
            staking_value = await self._get_staking_value(prices, user_id=user_id)
            defi_value = await self._get_defi_value(prices, user_id=user_id)
            exchange_value = await self._get_exchange_value(prices, user_id=user_id)
            nft_value = await self._get_nft_value(ada_price, user_id=user_id)
            tracked_tokens_value = await self._get_tracked_tokens_value(prices, user_id=user_id)

            total = (
                wallet_value +
                staking_value +
                defi_value +
                exchange_value +
                nft_value +
                tracked_tokens_value
            )

            return {
                'total': total,
                'breakdown': {
                    'wallets': wallet_value,
                    'staking': staking_value,
                    'defi': defi_value,
                    'exchange': exchange_value,
                    'nfts': nft_value,
                    'tracked_tokens': tracked_tokens_value
                }
            }
        except Exception as e:
            logger.error(f"Error calculating current portfolio value: {e}")
            return None

    async def generate_historical_data(self, days: int = 30, user_id: int = None) -> dict:
        """
        Generate historical portfolio data for the past N days.

        Strategy:
        1. Fetch historical prices from CoinGecko (free API)
        2. Use current wallet balances as the base quantities
        3. Calculate historical values: current_quantities × historical_prices

        This provides a reasonable approximation of historical portfolio value.
        For more accuracy, transaction history reconstruction would be needed.

        Args:
            days: Number of days of history to generate (default 30)
            user_id: User ID to generate history for

        Returns:
            dict with status and count of generated snapshots
        """
        from datetime import timedelta

        logger.info(f"Generating {days} days of historical portfolio data for user {user_id}...")

        # Get pricing service and fetch historical prices
        pricing = await self._get_pricing_service()
        historical_prices = await pricing.get_historical_prices(days=days)

        if not historical_prices:
            logger.error("Could not fetch historical prices from CoinGecko")
            return {"status": "error", "message": "Could not fetch historical prices"}

        # Get current wallet balances across all chains (assumes constant holdings)
        wallets = await get_all_wallets(user_id=user_id)
        ada_amount = 0.0
        btc_amount = 0.0
        eth_amount = 0.0
        sol_amount = 0.0

        chain_amounts = {
            'cardano': 0.0, 'bitcoin': 0.0, 'ethereum': 0.0, 'solana': 0.0,
            'polygon': 0.0, 'base': 0.0, 'algorand': 0.0, 'bsc': 0.0,
            'arbitrum': 0.0, 'avalanche': 0.0, 'tron': 0.0,
        }
        chain_price_symbols = {
            'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH', 'solana': 'SOL',
            'polygon': 'POL', 'base': 'ETH', 'algorand': 'ALGO', 'bsc': 'BNB',
            'arbitrum': 'ETH', 'avalanche': 'AVAX', 'tron': 'TRX',
        }

        # Get current native token values
        native_assets_total_usd = 0.0

        for wallet in wallets:
            balance = await get_wallet_balance(wallet['id'])
            if balance:
                amount = float(balance['amount'])
                blockchain = wallet['blockchain']
                if blockchain in chain_amounts:
                    chain_amounts[blockchain] += amount
                # Legacy vars for snapshot columns
                if blockchain == 'cardano':
                    ada_amount += amount
                elif blockchain == 'bitcoin':
                    btc_amount += amount
                elif blockchain == 'ethereum':
                    eth_amount += amount
                elif blockchain == 'solana':
                    sol_amount += amount

            try:
                from routers.portfolio import calculate_wallet_native_assets_value
                token_value = await calculate_wallet_native_assets_value(
                    wallet['id'], wallet['blockchain'], user_id
                )
                native_assets_total_usd += token_value
            except Exception:
                pass

        # Get current non-wallet component values for baseline
        current_prices = await pricing.get_all_tracked_prices()
        ada_price_now = current_prices.get('ADA', {}).get('usd', 0)
        staking_value = await self._get_staking_value(current_prices, user_id=user_id)
        defi_value = await self._get_defi_value(current_prices, user_id=user_id)
        exchange_value = await self._get_exchange_value(current_prices, user_id=user_id)
        nft_value = await self._get_nft_value(ada_price_now, user_id=user_id)
        tracked_tokens_value = await self._get_tracked_tokens_value(current_prices, user_id=user_id)
        non_wallet_total = staking_value + defi_value + exchange_value + nft_value + tracked_tokens_value

        logger.info(f"Current holdings - ADA: {ada_amount:.2f}, BTC: {btc_amount:.8f}, ETH: {eth_amount:.8f}, SOL: {sol_amount:.8f}")
        logger.info(f"Native tokens: ${native_assets_total_usd:.2f}, Non-wallet components: ${non_wallet_total:.2f}")

        # Build a date -> prices lookup (use daily granularity only)
        # CoinGecko returns hourly data for 2-90 days, so extract just YYYY-MM-DD
        price_by_date = {}
        for symbol, prices_list in historical_prices.items():
            for entry in prices_list:
                # Extract just the date portion (YYYY-MM-DD) from possibly hourly timestamps
                date_key = entry['date'][:10]
                if date_key not in price_by_date:
                    price_by_date[date_key] = {}
                # Last price of the day wins (overwrites earlier hours)
                price_by_date[date_key][symbol] = entry['price']

        # Generate snapshots for each date
        snapshots_created = 0
        now_ct = datetime.now(CT_TIMEZONE)
        today_str = str(now_ct.date())

        for date_str, prices in sorted(price_by_date.items()):
            # Skip today (we want historical data, not duplicate of today)
            if date_str == today_str:
                continue

            ada_price = prices.get('ADA', 0)
            btc_price = prices.get('BTC', 0)
            eth_price = prices.get('ETH', 0)
            sol_price = prices.get('SOL', 0)

            # Skip if we don't have prices for major assets
            if ada_price == 0 and btc_price == 0 and eth_price == 0 and sol_price == 0:
                continue

            # Calculate wallet value at historical prices (all chains)
            wallet_value_usd = 0.0
            for chain, amount in chain_amounts.items():
                if amount > 0:
                    symbol = chain_price_symbols[chain]
                    price = prices.get(symbol, 0)
                    wallet_value_usd += amount * price

            # Add native token values (using current values as baseline — no historical token prices available)
            wallet_value_usd += native_assets_total_usd

            # Include non-wallet components (current values as stable baseline)
            total_value_usd = wallet_value_usd + non_wallet_total

            # Parse the date to create a timestamp
            snapshot_date = datetime.strptime(date_str, '%Y-%m-%d')
            snapshot_time = snapshot_date.replace(hour=12, minute=0, second=0)

            snapshot_data = {
                'snapshot_date': date_str,
                'snapshot_time': snapshot_time.isoformat(),
                'total_value_usd': total_value_usd,
                'ada_amount': ada_amount,
                'ada_price': ada_price,
                'btc_amount': btc_amount,
                'btc_price': btc_price,
                'eth_amount': eth_amount,
                'eth_price': eth_price,
                'sol_amount': sol_amount,
                'sol_price': sol_price,
                'staking_value_usd': staking_value,
                'defi_value_usd': defi_value,
                'exchange_value_usd': exchange_value,
                'nft_value_usd': nft_value,
                'tracked_tokens_value_usd': tracked_tokens_value,
            }

            # Save snapshot (will update if exists due to UNIQUE constraint)
            await save_portfolio_snapshot(snapshot_data, user_id=user_id)
            snapshots_created += 1
            logger.debug(f"Created snapshot for {date_str}: ${total_value_usd:,.2f}")

        logger.info(f"Generated {snapshots_created} historical snapshots for user {user_id}")

        return {
            "status": "success",
            "snapshots_created": snapshots_created,
            "days_requested": days,
            "holdings_used": {
                "ada": ada_amount,
                "btc": btc_amount,
                "eth": eth_amount,
                "sol": sol_amount
            },
            "note": "Historical data uses current holdings with historical prices. For accurate historical balances, transaction history reconstruction would be needed."
        }

    async def backfill_component_values(self, user_id: int = None) -> dict:
        """
        Backfill historical snapshots with current staking/defi/exchange/NFT values.

        This assumes these component values have been relatively stable. It updates
        existing snapshots to include non-wallet components based on current values,
        making the chart more accurate.

        Args:
            user_id: User ID to backfill snapshots for

        Returns:
            dict with status and count of updated snapshots
        """
        logger.info(f"Backfilling historical snapshots with component values for user {user_id}...")

        # Get ALL existing snapshots (hourly) for this user, not just one per day
        snapshots = await get_portfolio_history(365, user_id=user_id, hourly=True)

        # Get current component values from cache (live data)
        staking_value = 0.0
        defi_value = 0.0
        exchange_value = 0.0
        nft_value = 0.0
        tracked_tokens_value = 0.0

        try:
            pricing = await self._get_pricing_service()
            prices = await pricing.get_all_tracked_prices()
            ada_price = prices.get('ADA', {}).get('usd', 0)
            staking_value = await self._get_staking_value(prices, user_id=user_id)
            defi_value = await self._get_defi_value(prices, user_id=user_id)
            exchange_value = await self._get_exchange_value(prices, user_id=user_id)
            nft_value = await self._get_nft_value(ada_price, user_id=user_id)
            tracked_tokens_value = await self._get_tracked_tokens_value(prices, user_id=user_id)
            logger.info(f"Cache values: staking=${staking_value:.2f}, defi=${defi_value:.2f}, "
                       f"exchange=${exchange_value:.2f}, nfts=${nft_value:.2f}")
        except Exception as e:
            logger.warning(f"Cache-based helpers failed: {e}")

        # For any component still at 0, scan snapshots (newest first) for a non-zero value
        for snap in reversed(snapshots):
            if staking_value < 1:
                v = float(snap.get('staking_value_usd') or 0)
                if v >= 1:
                    staking_value = v
            if defi_value < 1:
                v = float(snap.get('defi_value_usd') or 0)
                if v >= 1:
                    defi_value = v
            if exchange_value < 1:
                v = float(snap.get('exchange_value_usd') or 0)
                if v >= 1:
                    exchange_value = v
            if nft_value < 1:
                v = float(snap.get('nft_value_usd') or 0)
                if v >= 1:
                    nft_value = v
            if tracked_tokens_value < 1:
                v = float(snap.get('tracked_tokens_value_usd') or 0)
                if v >= 1:
                    tracked_tokens_value = v
            # Stop once we have all components
            if all(v >= 1 for v in [staking_value, defi_value, exchange_value, nft_value]):
                break

        total_components = staking_value + defi_value + exchange_value + nft_value + tracked_tokens_value

        logger.info(f"Component values to backfill: staking=${staking_value:.2f}, defi=${defi_value:.2f}, "
                   f"exchange=${exchange_value:.2f}, nfts=${nft_value:.2f}, tokens=${tracked_tokens_value:.2f}")

        updated_count = 0
        for snapshot in snapshots:
            date_str = snapshot['snapshot_date']

            # Check each component individually — update any that are missing/zero
            snap_staking = float(snapshot.get('staking_value_usd') or 0)
            snap_defi = float(snapshot.get('defi_value_usd') or 0)
            snap_exchange = float(snapshot.get('exchange_value_usd') or 0)
            snap_nft = float(snapshot.get('nft_value_usd') or 0)
            snap_tokens = float(snapshot.get('tracked_tokens_value_usd') or 0)

            # Determine which components need filling
            new_staking = staking_value if snap_staking < 1 and staking_value > 0 else snap_staking
            new_defi = defi_value if snap_defi < 1 and defi_value > 0 else snap_defi
            new_exchange = exchange_value if snap_exchange < 1 and exchange_value > 0 else snap_exchange
            new_nft = nft_value if snap_nft < 1 and nft_value > 0 else snap_nft
            new_tokens = tracked_tokens_value if snap_tokens < 1 and tracked_tokens_value > 0 else snap_tokens

            # Skip if nothing changed
            if (new_staking == snap_staking and new_defi == snap_defi and
                new_exchange == snap_exchange and new_nft == snap_nft and
                new_tokens == snap_tokens):
                continue

            # Use aggregate USD values for non-wallet components (no per-asset recalculation).
            # Only wallet values change based on historical prices.
            wallet_value = (
                (snapshot['ada_amount'] or 0) * (snapshot['ada_price'] or 0) +
                (snapshot['btc_amount'] or 0) * (snapshot['btc_price'] or 0) +
                (snapshot['eth_amount'] or 0) * (snapshot['eth_price'] or 0) +
                (snapshot.get('sol_amount', 0) or 0) * (snapshot.get('sol_price', 0) or 0)
            )
            new_total = wallet_value + new_staking + new_defi + new_exchange + new_nft + new_tokens

            # Update the snapshot
            snapshot_data = {
                'snapshot_date': date_str,
                'snapshot_time': snapshot.get('snapshot_time') or f"{date_str}T12:00:00",
                'total_value_usd': new_total,
                'ada_amount': snapshot['ada_amount'],
                'ada_price': snapshot['ada_price'],
                'btc_amount': snapshot['btc_amount'],
                'btc_price': snapshot['btc_price'],
                'eth_amount': snapshot['eth_amount'],
                'eth_price': snapshot['eth_price'],
                'sol_amount': snapshot.get('sol_amount', 0) or 0,
                'sol_price': snapshot.get('sol_price', 0) or 0,
                'staking_value_usd': new_staking,
                'defi_value_usd': new_defi,
                'exchange_value_usd': new_exchange,
                'nft_value_usd': new_nft,
                'tracked_tokens_value_usd': new_tokens,
            }

            await save_portfolio_snapshot(snapshot_data, user_id=user_id)
            updated_count += 1
            logger.debug(f"Updated snapshot for {date_str}: ${new_total:,.2f}")

        logger.info(f"Backfilled {updated_count} historical snapshots")

        return {
            "status": "success",
            "snapshots_updated": updated_count,
            "component_values": {
                "staking": staking_value,
                "defi": defi_value,
                "exchange": exchange_value,
                "nfts": nft_value,
                "tracked_tokens": tracked_tokens_value
            },
            "note": "Historical snapshots now include current component values. This assumes these values have been relatively stable."
        }


    async def reset_and_regenerate(self, user_id: int, days: int = 90) -> dict:
        """
        Delete all snapshots for a user and regenerate from scratch.

        Uses historical prices from CoinGecko with current wallet balances
        and current non-wallet component values as baselines.

        Args:
            user_id: User ID to reset
            days: Number of days of history to regenerate (default 90)

        Returns:
            dict with status and details
        """
        import aiosqlite
        from config import DATABASE_PATH

        logger.info(f"Resetting all snapshots for user {user_id} and regenerating {days} days...")

        # Step 1: Delete all existing snapshots
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM portfolio_snapshots WHERE user_id = ?", (user_id,)
            )
            count_row = await cursor.fetchone()
            old_count = count_row[0] if count_row else 0

            await db.execute(
                "DELETE FROM portfolio_snapshots WHERE user_id = ?", (user_id,)
            )
            await db.commit()

        logger.info(f"Deleted {old_count} old snapshots for user {user_id}")

        # Step 2: Regenerate historical data (now uses all chains + components)
        result = await self.generate_historical_data(days=days, user_id=user_id)

        # Step 3: Create a fresh snapshot for right now
        current = await self.create_snapshot(user_id=user_id, force=True)

        return {
            "status": "success",
            "deleted": old_count,
            "regenerated": result.get('snapshots_created', 0),
            "days_requested": days,
            "current_snapshot": current.get('total_value_usd', 0),
            "note": "All snapshots deleted and regenerated with corrected calculations."
        }


# Singleton instance
snapshot_service = SnapshotService()
