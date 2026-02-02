"""
Migration: Add quantity columns to portfolio_snapshots for historical recalculation

This allows historical portfolio values to be recalculated with historical prices
for exchanges and tracked tokens, not just wallet balances.
"""

import aiosqlite
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_PATH

async def column_exists(db, table_name, column_name):
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    columns = await cursor.fetchall()
    return any(col[1] == column_name for col in columns)

async def add_column_if_not_exists(db, table_name, column_name, column_def):
    """Add a column to a table if it doesn't already exist."""
    if not await column_exists(db, table_name, column_name):
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        print(f"  ✓ Added column: {column_name}")
        return True
    else:
        print(f"  - Column already exists: {column_name}")
        return False

async def migrate():
    """Add quantity columns to portfolio_snapshots table."""

    async with aiosqlite.connect(DATABASE_PATH) as db:
        print("Adding quantity columns to portfolio_snapshots...")

        columns_added = 0

        # Add exchange quantity columns for major coins
        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'exchange_btc_amount', 'REAL DEFAULT 0'):
            columns_added += 1

        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'exchange_eth_amount', 'REAL DEFAULT 0'):
            columns_added += 1

        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'exchange_ada_amount', 'REAL DEFAULT 0'):
            columns_added += 1

        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'exchange_sol_amount', 'REAL DEFAULT 0'):
            columns_added += 1

        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'exchange_matic_amount', 'REAL DEFAULT 0'):
            columns_added += 1

        # Store other exchange assets as JSON (currency: amount pairs)
        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'exchange_other_json', "TEXT DEFAULT '{}'"):
            columns_added += 1

        # Store tracked tokens as JSON (ticker: amount pairs)
        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'tracked_tokens_json', "TEXT DEFAULT '{}'"):
            columns_added += 1

        # Add sol_amount and sol_price if they don't exist (for older databases)
        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'sol_amount', 'REAL DEFAULT 0'):
            columns_added += 1

        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'sol_price', 'REAL DEFAULT 0'):
            columns_added += 1

        # Add matic price for Polygon
        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'matic_price', 'REAL DEFAULT 0'):
            columns_added += 1

        # Add tracked_tokens_value_usd column if it doesn't exist
        if await add_column_if_not_exists(db, 'portfolio_snapshots', 'tracked_tokens_value_usd', 'REAL DEFAULT 0'):
            columns_added += 1

        await db.commit()
        print(f"\n✅ Migration complete: {columns_added} new columns added to portfolio_snapshots")

if __name__ == "__main__":
    asyncio.run(migrate())
