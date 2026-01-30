import asyncio
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DATABASE_PATH

async def fix_snapshots_proper():
    """Properly fix the portfolio_snapshots table."""
    print("Fixing portfolio_snapshots table properly...")
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN TRANSACTION")
        
        try:
            # Drop the broken table
            await db.execute("DROP TABLE IF EXISTS portfolio_snapshots")
            
            # Create table with correct schema
            await db.execute("""
                CREATE TABLE portfolio_snapshots (
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
            
            # Create index
            await db.execute("CREATE INDEX idx_portfolio_snapshots_user_id ON portfolio_snapshots(user_id)")
            
            await db.commit()
            print("✅ Portfolio_snapshots table recreated successfully")
            print("   Note: Historical data has been cleared. Run create_demo_account.py to regenerate.")
            
        except Exception as e:
            await db.execute("ROLLBACK")
            print(f"❌ Error: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(fix_snapshots_proper())
