import asyncio
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DATABASE_PATH

async def fix_wallet_constraint():
    """Fix the wallets table UNIQUE constraint to include user_id."""
    print("Fixing wallets table UNIQUE constraint...")
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Start transaction
        await db.execute("BEGIN TRANSACTION")
        
        try:
            # Create new table with correct constraint
            await db.execute("""
                CREATE TABLE wallets_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    address TEXT NOT NULL,
                    blockchain TEXT NOT NULL,
                    label TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, address, blockchain)
                )
            """)
            
            # Copy data from old table
            await db.execute("""
                INSERT INTO wallets_new (id, user_id, address, blockchain, label, created_at, updated_at)
                SELECT id, user_id, address, blockchain, label, created_at, updated_at FROM wallets
            """)
            
            # Drop old table
            await db.execute("DROP TABLE wallets")
            
            # Rename new table
            await db.execute("ALTER TABLE wallets_new RENAME TO wallets")
            
            # Recreate index
            await db.execute("CREATE INDEX IF NOT EXISTS idx_wallets_user_id ON wallets(user_id)")
            
            # Commit transaction
            await db.commit()
            print("✅ Wallets table constraint fixed successfully")
            
        except Exception as e:
            await db.execute("ROLLBACK")
            print(f"❌ Error: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(fix_wallet_constraint())
