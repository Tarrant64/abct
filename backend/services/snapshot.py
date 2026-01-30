"""
Portfolio Snapshot Service - Captures portfolio value every 4 hours.

Strategy for local development app:
1. Check on app startup if today's snapshot exists and is recent
2. Create/update snapshot if none exists or if older than 4 hours
3. Also provide an API endpoint for manual snapshot creation

Snapshots are stored per-day (one per day) but updated every 4 hours
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
SNAPSHOT_INTERVAL_HOURS = 4  # Update snapshot every 4 hours


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

    async def should_create_snapshot(self) -> bool:
        """Check if we should create or update a snapshot."""
        now_ct = datetime.now(CT_TIMEZONE)
        today = str(now_ct.date())

        # Get the latest snapshot info
        latest_date = await get_latest_snapshot_date()
        latest_time = await get_latest_snapshot_time()

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

    async def create_snapshot(self, force: bool = False) -> dict:
        """
        Create or update a portfolio snapshot with current values.

        Args:
            force: If True, create/update snapshot regardless of timing

        Returns:
            dict with snapshot data
        """
        now_ct = datetime.now(CT_TIMEZONE)
        today = str(now_ct.date())

        # Check if we should create/update (unless forcing)
        if not force:
            should_update = await self.should_create_snapshot()
            if not should_update:
                logger.info(f"Snapshot for {today} is still fresh, skipping")
                return {"status": "skipped", "date": today, "reason": "still_fresh"}

        logger.info(f"Creating portfolio snapshot for {today}...")

        # Get pricing service
        pricing = await self._get_pricing_service()

        # Fetch current prices
        prices = await pricing.get_all_tracked_prices()
        ada_price = prices.get('ADA', {}).get('usd', 0)
        btc_price = prices.get('BTC', {}).get('usd', 0)
        eth_price = prices.get('ETH', {}).get('usd', 0)
        sol_price = prices.get('SOL', {}).get('usd', 0)

        # Calculate wallet totals
        wallets = await get_all_wallets()
        ada_amount = 0.0
        btc_amount = 0.0
        eth_amount = 0.0
        sol_amount = 0.0

        for wallet in wallets:
            balance = await get_wallet_balance(wallet['id'])
            if balance:
                amount = float(balance['amount'])
                if wallet['blockchain'] == 'cardano':
                    ada_amount += amount
                elif wallet['blockchain'] == 'bitcoin':
                    btc_amount += amount
                elif wallet['blockchain'] == 'ethereum':
                    eth_amount += amount
                elif wallet['blockchain'] == 'solana':
                    sol_amount += amount

        # Calculate wallet USD values
        wallet_value_usd = (
            ada_amount * ada_price +
            btc_amount * btc_price +
            eth_amount * eth_price +
            sol_amount * sol_price
        )

        # Get staking value (from cache if available)
        staking_value_usd = await self._get_staking_value(prices)

        # Get DeFi value (from cache if available)
        defi_value_usd = await self._get_defi_value(prices)

        # Get exchange value (from cache if available)
        exchange_value_usd = await self._get_exchange_value(prices)

        # Get NFT value (from cache if available)
        nft_value_usd = await self._get_nft_value(ada_price)

        # Get tracked native tokens value (from cache if available)
        tracked_tokens_value_usd = await self._get_tracked_tokens_value(prices)

        # Calculate total
        total_value_usd = (
            wallet_value_usd +
            staking_value_usd +
            defi_value_usd +
            exchange_value_usd +
            nft_value_usd +
            tracked_tokens_value_usd
        )

        # Prepare snapshot data
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
            'staking_value_usd': staking_value_usd,
            'defi_value_usd': defi_value_usd,
            'exchange_value_usd': exchange_value_usd,
            'nft_value_usd': nft_value_usd,
            'tracked_tokens_value_usd': tracked_tokens_value_usd
        }

        # Save to database
        await save_portfolio_snapshot(snapshot_data)
        logger.info(f"Portfolio snapshot saved: ${total_value_usd:,.2f}")

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

    async def _get_staking_value(self, prices: dict) -> float:
        """Get total staking value from cached data."""
        try:
            from database import get_cache
            # Try to get cached staking data
            wallets = await get_all_wallets()
            total_usd = 0.0

            for wallet in wallets:
                if wallet['blockchain'] == 'cardano':
                    cache_key = f"staking_positions_{wallet['address']}"
                    cached = await get_cache(cache_key)
                    if cached and 'positions' in cached:
                        for pos in cached['positions']:
                            amount = float(pos.get('staked_amount', 0))
                            token = pos.get('token', 'ADA')
                            price = prices.get(token, {}).get('price', 0)
                            total_usd += amount * price

            return total_usd
        except Exception as e:
            logger.debug(f"Could not get staking value: {e}")
            return 0.0

    async def _get_defi_value(self, prices: dict) -> float:
        """Get total DeFi value from cached data."""
        try:
            from database import get_cache
            cached = await get_cache("defi_summary")
            if cached and 'total_value_usd' in cached:
                return float(cached['total_value_usd'])
            return 0.0
        except Exception as e:
            logger.debug(f"Could not get DeFi value: {e}")
            return 0.0

    async def _get_exchange_value(self, prices: dict) -> float:
        """Get total exchange value from cached data."""
        try:
            from database import get_cache
            # Use the correct cache key from exchanges router
            cached = await get_cache("coinbase_portfolio")
            if cached and 'total_usd' in cached:
                return float(cached['total_usd'])
            return 0.0
        except Exception as e:
            logger.debug(f"Could not get exchange value: {e}")
            return 0.0

    async def _get_tracked_tokens_value(self, prices: dict) -> float:
        """Get total tracked native tokens value from cached data.

        Note: Excludes DeFi tokens (those with policy_id in DEFI_PROTOCOLS)
        to prevent double-counting with defi_value_usd.
        """
        try:
            from database import get_cache
            from services.defi import DEFI_PROTOCOLS

            cached = await get_cache("native_assets_all")
            if cached and 'assets' in cached:
                from database import get_tracked_tokens
                tracked_tokens = await get_tracked_tokens()
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

    async def _get_nft_value(self, ada_price: float) -> float:
        """Get total NFT value from cached data."""
        try:
            nft_svc = await self._get_nft_service()
            summary = await nft_svc.get_nft_summary()
            total_ada = summary.get('total_value_ada', 0)
            return total_ada * ada_price
        except Exception as e:
            logger.debug(f"Could not get NFT value: {e}")
            return 0.0

    async def check_and_create_snapshot(self):
        """Called on app startup - creates or updates snapshot if needed."""
        if await self.should_create_snapshot():
            logger.info("Creating/updating portfolio snapshot...")
            result = await self.create_snapshot(force=True)
            logger.info(f"Snapshot result: {result['status']}")
        else:
            logger.info("Portfolio snapshot is up to date (less than 4 hours old)")

    async def get_history(self, days: int = 7, user_id: int = None) -> list:
        """
        Get portfolio value history for charting.

        Includes current portfolio value as "today" if no snapshot exists
        or if today's snapshot has $0 value.
        """
        snapshots = await get_portfolio_history(days, user_id=user_id)

        # Convert snapshots to history format
        history = [
            {
                'date': s['snapshot_date'],
                'value': s['total_value_usd'],
                'breakdown': {
                    'wallets': (
                        s['ada_amount'] * s['ada_price'] +
                        s['btc_amount'] * s['btc_price'] +
                        s['eth_amount'] * s['eth_price'] +
                        (s.get('sol_amount', 0) or 0) * (s.get('sol_price', 0) or 0)
                    ),
                    'staking': s['staking_value_usd'],
                    'defi': s['defi_value_usd'],
                    'exchange': s['exchange_value_usd'],
                    'nfts': s['nft_value_usd'],
                    'tracked_tokens': s.get('tracked_tokens_value_usd', 0) or 0
                }
            }
            for s in snapshots
        ]

        # Check if we need to add/update today's value with current portfolio
        today = str(datetime.now(CT_TIMEZONE).date())
        today_in_history = any(h['date'] == today for h in history)
        today_has_zero = any(h['date'] == today and h['value'] == 0 for h in history)

        # If no today or today is $0, calculate current portfolio value
        if not today_in_history or today_has_zero:
            current_value = await self._calculate_current_portfolio_value()

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

    async def _calculate_current_portfolio_value(self) -> dict:
        """Calculate current portfolio value with all components."""
        try:
            pricing = await self._get_pricing_service()
            prices = await pricing.get_all_tracked_prices()

            ada_price = prices.get('ADA', {}).get('usd', 0)
            btc_price = prices.get('BTC', {}).get('usd', 0)
            eth_price = prices.get('ETH', {}).get('usd', 0)
            sol_price = prices.get('SOL', {}).get('usd', 0)

            # Calculate wallet totals
            wallets = await get_all_wallets()
            ada_amount = btc_amount = eth_amount = sol_amount = 0.0

            for wallet in wallets:
                balance = await get_wallet_balance(wallet['id'])
                if balance:
                    amount = float(balance['amount'])
                    if wallet['blockchain'] == 'cardano':
                        ada_amount += amount
                    elif wallet['blockchain'] == 'bitcoin':
                        btc_amount += amount
                    elif wallet['blockchain'] == 'ethereum':
                        eth_amount += amount
                    elif wallet['blockchain'] == 'solana':
                        sol_amount += amount

            wallet_value = (
                ada_amount * ada_price +
                btc_amount * btc_price +
                eth_amount * eth_price +
                sol_amount * sol_price
            )

            # Get other component values
            staking_value = await self._get_staking_value(prices)
            defi_value = await self._get_defi_value(prices)
            exchange_value = await self._get_exchange_value(prices)
            nft_value = await self._get_nft_value(ada_price)
            tracked_tokens_value = await self._get_tracked_tokens_value(prices)

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

    async def generate_historical_data(self, days: int = 30) -> dict:
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

        Returns:
            dict with status and count of generated snapshots
        """
        from datetime import timedelta

        logger.info(f"Generating {days} days of historical portfolio data...")

        # Get pricing service and fetch historical prices
        pricing = await self._get_pricing_service()
        historical_prices = await pricing.get_historical_prices(days)

        if not historical_prices:
            logger.error("Could not fetch historical prices from CoinGecko")
            return {"status": "error", "message": "Could not fetch historical prices"}

        # Get current wallet balances (assumes constant holdings for historical calculation)
        wallets = await get_all_wallets()
        ada_amount = 0.0
        btc_amount = 0.0
        eth_amount = 0.0

        for wallet in wallets:
            balance = await get_wallet_balance(wallet['id'])
            if balance:
                amount = float(balance['amount'])
                if wallet['blockchain'] == 'cardano':
                    ada_amount += amount
                elif wallet['blockchain'] == 'bitcoin':
                    btc_amount += amount
                elif wallet['blockchain'] == 'ethereum':
                    eth_amount += amount

        logger.info(f"Current holdings - ADA: {ada_amount:.2f}, BTC: {btc_amount:.8f}, ETH: {eth_amount:.8f}")

        # Build a date -> prices lookup
        price_by_date = {}
        for symbol, prices_list in historical_prices.items():
            for entry in prices_list:
                date = entry['date']
                if date not in price_by_date:
                    price_by_date[date] = {}
                price_by_date[date][symbol] = entry['price']

        # Generate snapshots for each date
        snapshots_created = 0
        now_ct = datetime.now(CT_TIMEZONE)

        for date_str, prices in sorted(price_by_date.items()):
            # Skip today (we want historical data, not duplicate of today)
            if date_str == str(now_ct.date()):
                continue

            ada_price = prices.get('ADA', 0)
            btc_price = prices.get('BTC', 0)
            eth_price = prices.get('ETH', 0)

            # Skip if we don't have prices for major assets
            if ada_price == 0 and btc_price == 0 and eth_price == 0:
                continue

            # Calculate wallet value at historical prices
            wallet_value_usd = (
                ada_amount * ada_price +
                btc_amount * btc_price +
                eth_amount * eth_price
            )

            # For historical data, we don't have historical staking/defi/exchange/nft data
            # So we'll set those to 0 (or could estimate based on current proportions)
            # For simplicity, assume wallet-only value for historical data
            total_value_usd = wallet_value_usd

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
                'staking_value_usd': 0,  # Historical staking data not available
                'defi_value_usd': 0,     # Historical DeFi data not available
                'exchange_value_usd': 0, # Historical exchange data not available
                'nft_value_usd': 0       # Historical NFT data not available
            }

            # Save snapshot (will update if exists due to UNIQUE constraint)
            await save_portfolio_snapshot(snapshot_data)
            snapshots_created += 1
            logger.debug(f"Created snapshot for {date_str}: ${total_value_usd:,.2f}")

        logger.info(f"Generated {snapshots_created} historical snapshots")

        return {
            "status": "success",
            "snapshots_created": snapshots_created,
            "days_requested": days,
            "holdings_used": {
                "ada": ada_amount,
                "btc": btc_amount,
                "eth": eth_amount
            },
            "note": "Historical data uses current holdings with historical prices. For accurate historical balances, transaction history reconstruction would be needed."
        }

    async def backfill_component_values(self) -> dict:
        """
        Backfill historical snapshots with current staking/defi/exchange/NFT values.

        This assumes these component values have been relatively stable. It updates
        existing snapshots to include non-wallet components based on current values,
        making the chart more accurate.

        Returns:
            dict with status and count of updated snapshots
        """
        logger.info("Backfilling historical snapshots with component values...")

        # Get current component values
        pricing = await self._get_pricing_service()
        prices = await pricing.get_all_tracked_prices()
        ada_price = prices.get('ADA', {}).get('usd', 0)

        staking_value = await self._get_staking_value(prices)
        defi_value = await self._get_defi_value(prices)
        exchange_value = await self._get_exchange_value(prices)
        nft_value = await self._get_nft_value(ada_price)
        tracked_tokens_value = await self._get_tracked_tokens_value(prices)

        total_components = staking_value + defi_value + exchange_value + nft_value + tracked_tokens_value

        logger.info(f"Component values to backfill: staking=${staking_value:.2f}, defi=${defi_value:.2f}, "
                   f"exchange=${exchange_value:.2f}, nfts=${nft_value:.2f}, tokens=${tracked_tokens_value:.2f}")

        # Get all existing snapshots
        snapshots = await get_portfolio_history(365)  # Get up to a year

        updated_count = 0
        for snapshot in snapshots:
            date_str = snapshot['snapshot_date']

            # Skip if already has component values (sum of components > 0)
            existing_components = (
                snapshot.get('staking_value_usd', 0) +
                snapshot.get('defi_value_usd', 0) +
                snapshot.get('exchange_value_usd', 0) +
                snapshot.get('nft_value_usd', 0) +
                (snapshot.get('tracked_tokens_value_usd', 0) or 0)
            )

            if existing_components > 100:  # Already has meaningful component values
                continue

            # Calculate new total
            wallet_value = (
                snapshot['ada_amount'] * snapshot['ada_price'] +
                snapshot['btc_amount'] * snapshot['btc_price'] +
                snapshot['eth_amount'] * snapshot['eth_price'] +
                (snapshot.get('sol_amount', 0) or 0) * (snapshot.get('sol_price', 0) or 0)
            )
            new_total = wallet_value + total_components

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
                'staking_value_usd': staking_value,
                'defi_value_usd': defi_value,
                'exchange_value_usd': exchange_value,
                'nft_value_usd': nft_value,
                'tracked_tokens_value_usd': tracked_tokens_value
            }

            await save_portfolio_snapshot(snapshot_data)
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


# Singleton instance
snapshot_service = SnapshotService()
