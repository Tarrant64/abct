import asyncio
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DATABASE_PATH

async def fix_snapshot_constraint():
    """Fix the portfolio_snapshots table UNIQUE constraint to include user_id."""
    print("Fixing portfolio_snapshots table UNIQUE constraint...")
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN TRANSACTION")
        
        try:
            # First, assign NULL snapshots to admin user
            await db.execute("UPDATE portfolio_snapshots SET user_id = 1 WHERE user_id IS NULL")
            await db.commit()
            print("✅ Assigned existing snapshots to admin user")
            
            # Create new table with correct constraint
            await db.execute("""
                CREATE TABLE portfolio_snapshots_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    snapshot_date DATE NOT NULL,
                    snapshot_time TIMESTAMP NOT NULL,
                    total_value_usd REAL NOT NULL,
                    ada_amount REAL DEFAULT 0,
                    ada_price REAL DEFAULT 0,
                    btc_amount REAL DEFAULT 0,
                    btc_price REAL DEFAULT 0,
                    eth_amount REAL DEFAULT 0,
                    eth_price REAL DEFAULT 0,
                    sol_amount REAL DEFAULT 0,
                    sol_price REAL DEFAULT 0,
                    staking_value_usd REAL DEFAULT 0,
                    defi_value_usd REAL DEFAULT 0,
                    exchange_value_usd REAL DEFAULT 0,
                    nft_value_usd REAL DEFAULT 0,
                    tracked_tokens_value_usd REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, snapshot_date)
                )
            """)
            
            # Copy data from old table
            await db.execute("""
                INSERT INTO portfolio_snapshots_new 
                SELECT * FROM portfolio_snapshots
            """)
            
            # Drop old table
            await db.execute("DROP TABLE portfolio_snapshots")
            
            # Rename new table
            await db.execute("ALTER TABLE portfolio_snapshots_new RENAME TO portfolio_snapshots")
            
            # Recreate index
            await db.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_id ON portfolio_snapshots(user_id)")
            
            await db.commit()
            print("✅ Portfolio_snapshots table constraint fixed successfully")
            
        except Exception as e:
            await db.execute("ROLLBACK")
            print(f"❌ Error: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(fix_snapshot_constraint())
