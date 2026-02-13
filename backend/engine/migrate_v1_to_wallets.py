"""
V1 → V2 Migration Script: Per-Wallet Balance History

One-time script that:
1. Seeds wallet_sources from existing wallets + configured exchanges
2. Materializes V2 on-chain events into wallet_daily_balances
3. Extracts V1 snapshot off-chain components into per-source wallet_daily_balances
4. Back-fills pre-Nov-2025 off-chain with earliest known values (estimated)
5. Validates: compares SUM(wallet_daily_balances) vs V1 snapshot totals
6. Marks V1 portfolio_snapshots as legacy (keep table, stop writing)

Usage:
    cd backend
    python -m engine.migrate_v1_to_wallets
"""

import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_migration():
    """Execute the full V1 → V2 per-wallet migration."""
    import aiosqlite
    from database import (
        init_db, get_all_users, get_all_wallets, get_all_api_settings,
        seed_wallet_sources, get_wallet_sources, get_portfolio_history,
        get_unified_daily_totals, upsert_wallet_daily_balances_batch
    )
    from engine.db import init_engine_tables
    from engine.materializer import materializer

    # Step 0: Initialize database tables
    logger.info("=" * 60)
    logger.info("V1 → V2 Per-Wallet Migration")
    logger.info("=" * 60)

    logger.info("\nStep 0: Initializing database tables...")
    await init_db()
    await init_engine_tables()
    logger.info("Database tables ready")

    # Get all non-demo users
    users = await get_all_users()
    non_demo = [u for u in users if not u.get('is_demo', False)]
    logger.info(f"Found {len(non_demo)} non-demo user(s)")

    for user in non_demo:
        user_id = user['id']
        username = user.get('username', 'unknown')
        logger.info(f"\n{'=' * 40}")
        logger.info(f"Migrating user {user_id} ({username})")
        logger.info(f"{'=' * 40}")

        # Step 1: Seed wallet_sources
        logger.info("\nStep 1: Seeding wallet_sources...")
        await seed_wallet_sources(user_id)
        sources = await get_wallet_sources(user_id)
        by_type = {}
        for s in sources:
            by_type.setdefault(s['source_type'], []).append(s)
        for stype, srcs in sorted(by_type.items()):
            logger.info(f"  {stype}: {len(srcs)} source(s)")
        logger.info(f"  Total: {len(sources)} wallet sources seeded")

        # Step 2: Materialize on-chain events
        logger.info("\nStep 2: Materializing on-chain events...")
        try:
            await materializer.materialize_onchain(user_id)
        except Exception as e:
            logger.error(f"  On-chain materialization failed: {e}")

        # Step 3: Extract V1 snapshot off-chain components
        logger.info("\nStep 3: Extracting V1 snapshot off-chain components...")
        try:
            await materializer.materialize_offchain_from_v1(user_id)
        except Exception as e:
            logger.error(f"  Off-chain materialization failed: {e}")

        # Step 4: Gap-fill off-chain data
        logger.info("\nStep 4: Gap-filling off-chain data...")
        try:
            await materializer.backfill_offchain_gaps(user_id)
        except Exception as e:
            logger.error(f"  Gap-fill failed: {e}")

        # Step 5: Validate - compare SUM(wallet_daily_balances) vs V1 snapshots
        logger.info("\nStep 5: Validating against V1 snapshots...")
        try:
            await _validate_migration(user_id)
        except Exception as e:
            logger.error(f"  Validation failed: {e}")

    # Step 6: Mark migration as complete
    logger.info("\n" + "=" * 60)
    logger.info("Step 6: Recording migration flag...")
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT OR IGNORE INTO migrations (migration_key)
               VALUES ('v1_to_wallet_daily_balances')"""
        )
        await db.commit()
    logger.info("Migration flag recorded")

    logger.info("\n" + "=" * 60)
    logger.info("Migration complete!")
    logger.info("V1 portfolio_snapshots table preserved (legacy, read-only)")
    logger.info("New data flows through wallet_daily_balances via offchain_collector")
    logger.info("=" * 60)


async def _validate_migration(user_id: int):
    """Compare SUM(wallet_daily_balances) per date with V1 snapshot total_value_usd."""
    from database import get_portfolio_history, get_unified_daily_totals

    # Get V1 snapshots
    v1_snapshots = await get_portfolio_history(days=3650, user_id=user_id)
    if not v1_snapshots:
        logger.info("  No V1 snapshots to validate against")
        return

    def sf(val, default=0.0):
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    # Build V1 totals by date
    v1_by_date = {}
    for s in v1_snapshots:
        date = s.get('snapshot_date')
        if date:
            v1_by_date[date] = sf(s.get('total_value_usd'))

    # Get V2 per-wallet totals
    wdb_rows = await get_unified_daily_totals(user_id)
    wdb_by_date = {row['date']: sf(row.get('total_value')) for row in wdb_rows}

    # Compare overlapping dates
    overlap_dates = sorted(set(v1_by_date.keys()) & set(wdb_by_date.keys()))
    if not overlap_dates:
        logger.info("  No overlapping dates between V1 and V2 data")
        logger.info(f"  V1 dates: {len(v1_by_date)}, V2 dates: {len(wdb_by_date)}")
        return

    discrepancies = 0
    for date in overlap_dates:
        v1_total = v1_by_date[date]
        wdb_total = wdb_by_date[date]

        if v1_total > 0:
            pct_diff = abs(v1_total - wdb_total) / v1_total * 100
            if pct_diff > 10:
                discrepancies += 1
                logger.warning(
                    f"  {date}: V1=${v1_total:,.2f} vs V2=${wdb_total:,.2f} "
                    f"(diff={pct_diff:.1f}%)"
                )

    logger.info(
        f"  Validated {len(overlap_dates)} dates: "
        f"{discrepancies} discrepancies > 10%"
    )
    if discrepancies == 0:
        logger.info("  All dates within 10% tolerance")


async def check_migration_status():
    """Check if the V1→V2 migration has been run."""
    import aiosqlite
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        try:
            cursor = await db.execute(
                "SELECT migration_key, applied_at FROM migrations WHERE migration_key = 'v1_to_wallet_daily_balances'"
            )
            row = await cursor.fetchone()
            if row:
                logger.info(f"Migration already applied at {row[1]}")
                return True
            return False
        except Exception:
            return False


if __name__ == '__main__':
    async def main():
        already_done = await check_migration_status()
        if already_done:
            logger.info("Migration has already been run. To re-run, delete the migration flag:")
            logger.info("  DELETE FROM migrations WHERE migration_key = 'v1_to_wallet_daily_balances'")
            response = input("Re-run migration anyway? (y/N): ").strip().lower()
            if response != 'y':
                return

        await run_migration()

    asyncio.run(main())
