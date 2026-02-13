"""
Off-Chain Collector Service

Periodically collects off-chain balances (exchanges, staking, DeFi, NFTs)
and writes them to wallet_daily_balances. Replaces the V1 monolithic snapshot
for off-chain data collection.

Runs every 2 hours (same cadence as old V1 snapshot).
Reuses existing service methods from snapshot.py.
"""

import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CT_TIMEZONE = ZoneInfo("America/Chicago")
COLLECTION_INTERVAL_HOURS = 2


class OffchainCollector:
    """Collects off-chain balances and writes per-source daily rows."""

    def __init__(self):
        self._task: asyncio.Task = None
        self._pricing_service = None
        self._nft_service = None

    async def _get_pricing_service(self):
        if self._pricing_service is None:
            from services.pricing import pricing_service
            self._pricing_service = pricing_service
        return self._pricing_service

    async def _get_nft_service(self):
        if self._nft_service is None:
            from services.nft import nft_service
            self._nft_service = nft_service
        return self._nft_service

    async def collect_for_user(self, user_id: int):
        """Collect all off-chain balances for a user and write to wallet_daily_balances."""
        from database import (
            get_wallet_sources, upsert_wallet_daily_balance,
            get_all_wallets, get_cache
        )
        from services.offchain_helpers import (
            get_staking_value, get_defi_value, get_nft_value, get_exchange_value
        )

        today = datetime.now(CT_TIMEZONE).strftime('%Y-%m-%d')
        pricing = await self._get_pricing_service()
        prices = await pricing.get_all_tracked_prices()
        ada_price = prices.get('ADA', {}).get('usd', 0)

        # --- Exchanges ---
        exchange_sources = await get_wallet_sources(user_id, source_type='exchange')
        for source in exchange_sources:
            try:
                exchange_name = source['source_key']
                cache_key = f"{exchange_name}_portfolio"
                cached = await get_cache(cache_key, user_id=user_id)
                value_usd = 0.0
                if cached and 'total_usd' in cached:
                    value_usd = float(cached['total_usd'])
                elif cached and 'assets' in cached:
                    # Calculate from assets
                    for asset in cached['assets']:
                        currency = asset.get('currency', '').upper()
                        balance = float(asset.get('balance', 0))
                        if balance > 0:
                            p = prices.get(currency, {})
                            price = p.get('usd', 0) if isinstance(p, dict) else 0
                            value_usd += balance * price

                await upsert_wallet_daily_balance(
                    user_id=user_id,
                    source_id=source['id'],
                    date=today,
                    value_usd=round(value_usd, 2),
                    metadata=json.dumps({'source': 'live', 'exchange': exchange_name}),
                )
                logger.debug(f"Offchain collector: {exchange_name} = ${value_usd:,.2f}")
            except Exception as e:
                logger.warning(f"Offchain collector: exchange {source['source_key']} failed: {e}")

        # --- Staking ---
        staking_sources = await get_wallet_sources(user_id, source_type='staking')
        if staking_sources:
            staking_total = await get_staking_value(prices, user_id=user_id)
            if staking_total > 0 and staking_sources:
                per_source = staking_total / len(staking_sources)
                for source in staking_sources:
                    try:
                        await upsert_wallet_daily_balance(
                            user_id=user_id,
                            source_id=source['id'],
                            date=today,
                            value_usd=round(per_source, 2),
                            metadata=json.dumps({'source': 'live'}),
                        )
                    except Exception as e:
                        logger.warning(f"Offchain collector: staking {source['source_key']} failed: {e}")
                logger.debug(f"Offchain collector: staking total = ${staking_total:,.2f}")

        # --- DeFi ---
        defi_sources = await get_wallet_sources(user_id, source_type='defi')
        if defi_sources:
            defi_total = await get_defi_value(prices, user_id=user_id)
            if defi_total > 0 and defi_sources:
                per_source = defi_total / len(defi_sources)
                for source in defi_sources:
                    try:
                        await upsert_wallet_daily_balance(
                            user_id=user_id,
                            source_id=source['id'],
                            date=today,
                            value_usd=round(per_source, 2),
                            metadata=json.dumps({'source': 'live'}),
                        )
                    except Exception as e:
                        logger.warning(f"Offchain collector: defi {source['source_key']} failed: {e}")
                logger.debug(f"Offchain collector: DeFi total = ${defi_total:,.2f}")

        # --- NFTs ---
        nft_sources = await get_wallet_sources(user_id, source_type='nft')
        if nft_sources:
            nft_total = await get_nft_value(ada_price, user_id=user_id)
            if nft_total > 0:
                try:
                    await upsert_wallet_daily_balance(
                        user_id=user_id,
                        source_id=nft_sources[0]['id'],
                        date=today,
                        value_usd=round(nft_total, 2),
                        metadata=json.dumps({'source': 'live'}),
                    )
                except Exception as e:
                    logger.warning(f"Offchain collector: NFT failed: {e}")
                logger.debug(f"Offchain collector: NFT total = ${nft_total:,.2f}")

        logger.info(f"Offchain collector: Completed collection for user {user_id}")

    async def collect_all_users(self):
        """Collect off-chain balances for all non-demo users."""
        from database import get_all_users, seed_wallet_sources

        users = await get_all_users()
        non_demo = [u for u in users if not u.get('is_demo', False)]

        for user in non_demo:
            user_id = user['id']
            try:
                # Ensure sources are seeded
                await seed_wallet_sources(user_id)
                await self.collect_for_user(user_id)
            except Exception as e:
                logger.error(f"Offchain collector: Failed for user {user_id}: {e}")

    async def start_periodic(self):
        """Start the periodic collection loop (replaces V1 periodic_snapshot_task for off-chain)."""
        self._task = asyncio.current_task() or asyncio.ensure_future(self._run_loop())

    async def _run_loop(self):
        """Background loop: collect off-chain every COLLECTION_INTERVAL_HOURS."""
        from services.logging_service import get_logging_service
        log_service = get_logging_service()

        while True:
            try:
                await asyncio.sleep(COLLECTION_INTERVAL_HOURS * 3600)
                logger.info("Offchain collector: Starting periodic collection...")
                await log_service.info("offchain_collector", "Starting periodic off-chain collection")
                await self.collect_all_users()
                logger.info("Offchain collector: Periodic collection complete")
                await log_service.info("offchain_collector", "Periodic off-chain collection complete")
            except Exception as e:
                logger.error(f"Offchain collector: Periodic collection error: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error


# Singleton
offchain_collector = OffchainCollector()
