import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from config import DATABASE_PATH
from typing import Optional

# ============================================================================
# MULTI-USER CONTEXT
# ============================================================================

# Global context for current user (set by auth middleware)
_current_user_id: Optional[int] = None


def set_current_user_id(user_id: Optional[int]):
    """Set the current user ID from auth context."""
    global _current_user_id
    _current_user_id = user_id


def get_current_user_id() -> Optional[int]:
    """Get the current user ID from context.

    Returns:
        User ID if authenticated, None otherwise
    """
    return _current_user_id


async def get_user_id_by_username(username: str) -> Optional[int]:
    """Get user ID by username.

    Args:
        username: Username to look up

    Returns:
        User ID if found, None otherwise
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_username_by_user_id(user_id: int) -> Optional[str]:
    """Get username by user ID.

    Args:
        user_id: User ID to look up

    Returns:
        Username if found, None otherwise
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT username FROM users WHERE id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_all_users():
    """Get all users.

    Returns:
        List of user dictionaries
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, username, is_demo FROM users ORDER BY id"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def _check_column_exists(db, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    columns = await cursor.fetchall()
    return any(col[1] == column_name for col in columns)


async def _migrate_add_user_id_columns(db):
    """Migration: Add user_id columns to existing tables without it.

    This function handles migrating from single-user to multi-user architecture.
    It adds user_id columns to tables that need them and assigns existing records
    to the admin user.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Tables that need user_id column
    tables_needing_user_id = [
        'wallets',
        'portfolio_snapshots',
        'custom_tokens',
        'api_settings',
        'security_settings',
    ]

    # Get or create admin user
    cursor = await db.execute("SELECT id FROM users WHERE username = 'admin'")
    admin = await cursor.fetchone()

    if not admin:
        # Create admin user if it doesn't exist
        import bcrypt
        import os
        default_password = os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")
        password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

        cursor = await db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", password_hash.decode('utf-8'))
        )
        await db.commit()
        admin_id = cursor.lastrowid
        logger.info(f"Created admin user during migration (ID: {admin_id})")
    else:
        admin_id = admin[0]

    # Process each table
    for table_name in tables_needing_user_id:
        try:
            # Check if table exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if not await cursor.fetchone():
                continue  # Table doesn't exist yet

            # Check if user_id column exists
            if await _check_column_exists(db, table_name, 'user_id'):
                continue  # Already has user_id

            # Add user_id column
            logger.info(f"Adding user_id column to {table_name}")
            await db.execute(f"""
                ALTER TABLE {table_name}
                ADD COLUMN user_id INTEGER REFERENCES users(id)
            """)

            # Update existing records to admin user
            await db.execute(f"""
                UPDATE {table_name}
                SET user_id = ?
                WHERE user_id IS NULL
            """, (admin_id,))

            # Create index
            await db.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id
                ON {table_name}(user_id)
            """)

            await db.commit()
            logger.info(f"Successfully migrated {table_name}")

        except Exception as e:
            logger.warning(f"Migration warning for {table_name}: {e}")
            # Continue with other tables


async def init_db():
    """Initialize the SQLite database with required tables."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Users table (created by auth system, but ensure it exists)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_changed BOOLEAN DEFAULT 0,
                is_demo BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add is_demo column if it doesn't exist
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_demo BOOLEAN DEFAULT 0")
            await db.commit()
        except Exception:
            # Column already exists
            pass

        # Wallets table - address + blockchain + user is unique
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                address TEXT NOT NULL,
                blockchain TEXT NOT NULL,
                label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, address, blockchain)
            )
        """)

        # Create index on user_id for wallets
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallets_user_id
            ON wallets(user_id)
        """)

        # Balances table (native currency)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount TEXT NOT NULL,
                unit TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Native assets table (tokens, NFTs)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS native_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                asset_id TEXT NOT NULL,
                policy_id TEXT,
                asset_name TEXT,
                quantity TEXT NOT NULL,
                decimals INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Cache table for API responses (user-specific)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create indexes for multi-user performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_balances_user_id ON balances(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_balances_wallet_id ON balances(wallet_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_native_assets_user_id ON native_assets(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_native_assets_wallet_id ON native_assets(wallet_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_native_assets_policy_id ON native_assets(policy_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cache_user_key ON cache(user_id, key)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)")

        # Portfolio snapshots table for historical tracking (per user)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                snapshot_date DATE NOT NULL,
                snapshot_time TIMESTAMP NOT NULL,
                total_value_usd REAL NOT NULL,
                ada_amount REAL DEFAULT 0,
                ada_price REAL DEFAULT 0,
                btc_amount REAL DEFAULT 0,
                btc_price REAL DEFAULT 0,
                eth_amount REAL DEFAULT 0,
                eth_price REAL DEFAULT 0,
                staking_value_usd REAL DEFAULT 0,
                defi_value_usd REAL DEFAULT 0,
                exchange_value_usd REAL DEFAULT 0,
                nft_value_usd REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, snapshot_date)
            )
        """)

        # Create index on user_id for portfolio_snapshots
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_id
            ON portfolio_snapshots(user_id)
        """)

        # NFT collection floor prices - stores historical floor price data
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nft_floor_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id TEXT NOT NULL,
                collection_name TEXT,
                floor_price_ada REAL,
                listings INTEGER DEFAULT 0,
                supply INTEGER,
                verified INTEGER DEFAULT 0,
                source TEXT,
                fetched_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(policy_id, fetched_at)
            )
        """)

        # Index for efficient lookups
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_floor_prices_policy
            ON nft_floor_prices(policy_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_floor_prices_fetched
            ON nft_floor_prices(fetched_at)
        """)

        # Custom tokens table for manual token tracking (per user)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                policy_id TEXT NOT NULL,
                asset_name TEXT,
                ticker TEXT,
                blockchain TEXT NOT NULL,
                quantity TEXT NOT NULL,
                decimals INTEGER DEFAULT 0,
                label TEXT,
                token_name TEXT,
                price_usd REAL,
                last_price_update TIMESTAMP,
                include_in_total INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, policy_id, asset_name)
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_custom_tokens_user_id
            ON custom_tokens(user_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_custom_tokens_blockchain
            ON custom_tokens(blockchain)
        """)

        # Token metadata cache - stores decimals and other token info
        await db.execute("""
            CREATE TABLE IF NOT EXISTS token_metadata (
                asset_id TEXT PRIMARY KEY,
                policy_id TEXT,
                asset_name TEXT,
                ticker TEXT,
                name TEXT,
                decimals INTEGER DEFAULT 0,
                logo_url TEXT,
                track_for_pricing INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add track_for_pricing column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE token_metadata ADD COLUMN track_for_pricing INTEGER DEFAULT 0")
        except:
            pass  # Column already exists

        # Add Solana columns to portfolio_snapshots if they don't exist (migration)
        try:
            await db.execute("ALTER TABLE portfolio_snapshots ADD COLUMN sol_amount REAL DEFAULT 0")
        except:
            pass  # Column already exists

        try:
            await db.execute("ALTER TABLE portfolio_snapshots ADD COLUMN sol_price REAL DEFAULT 0")
        except:
            pass  # Column already exists

        # Add tracked tokens value column (migration)
        try:
            await db.execute("ALTER TABLE portfolio_snapshots ADD COLUMN tracked_tokens_value_usd REAL DEFAULT 0")
        except:
            pass  # Column already exists

        # API settings table - stores enabled APIs and their keys (system-wide)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_settings (
                api_name TEXT PRIMARY KEY,
                api_key TEXT,
                enabled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """)

        # API usage tracking table - stores API call counts per period
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT NOT NULL,
                period_start TIMESTAMP NOT NULL,
                period_end TIMESTAMP NOT NULL,
                call_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(api_name, period_start)
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_usage_api_period
            ON api_usage(api_name, period_start)
        """)

        # API rate limits table - stores custom rate limits for APIs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_rate_limits (
                api_name TEXT PRIMARY KEY,
                requests_limit INTEGER NOT NULL,
                period_seconds INTEGER NOT NULL DEFAULT 86400,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Security settings table for SSL/HTTPS configuration (system-wide)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ssl_mode TEXT DEFAULT 'http',
                cert_path TEXT,
                key_path TEXT,
                cert_type TEXT,
                cert_expires_at TIMESTAMP,
                pending_mode TEXT,
                restart_required INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """)

        # NFT Scheduler state table - tracks scheduler status (single row)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nft_scheduler_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                last_update TIMESTAMP,
                total_updates INTEGER DEFAULT 0,
                successful_updates INTEGER DEFAULT 0,
                failed_updates INTEGER DEFAULT 0,
                last_error TEXT,
                rate_limited_until TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Insert default row if not exists
        await db.execute("""
            INSERT OR IGNORE INTO nft_scheduler_state (id, enabled)
            VALUES (1, 0)
        """)

        # NFT Scheduler collections - tracks which NFT collections to monitor
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nft_scheduler_collections (
                policy_id TEXT PRIMARY KEY,
                collection_name TEXT,
                priority INTEGER DEFAULT 0,
                last_updated TIMESTAMP,
                update_count INTEGER DEFAULT 0,
                last_floor_price REAL,
                supply INTEGER,
                holders INTEGER,
                listings INTEGER,
                volume_24h REAL,
                volume_7d REAL,
                volume_30d REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_scheduler_collections_priority
            ON nft_scheduler_collections(priority DESC, last_updated ASC)
        """)

        # NFT Scheduler API calls - tracks API usage for rate limiting
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nft_scheduler_api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                policy_id TEXT,
                status_code INTEGER,
                called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_scheduler_api_calls_date
            ON nft_scheduler_api_calls(called_at)
        """)

        await db.commit()

        # ===== MIGRATION: Add user_id columns to existing tables =====
        await _migrate_add_user_id_columns(db)

async def get_db():
    """Get database connection."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def save_wallet(address: str, blockchain: str, label: str = None, user_id: int = None):
    """Save or update a wallet in the database.

    Args:
        address: Wallet address
        blockchain: Blockchain name (cardano, bitcoin, ethereum, etc.)
        label: Optional label for the wallet
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Check if wallet already exists for this user
        cursor = await db.execute(
            "SELECT id, label FROM wallets WHERE user_id = ? AND address = ? AND blockchain = ?",
            (user_id, address, blockchain)
        )
        existing = await cursor.fetchone()

        if existing:
            # Update existing wallet
            new_label = label if label else existing['label']
            await db.execute(
                "UPDATE wallets SET label = ?, updated_at = ? WHERE id = ?",
                (new_label, datetime.now(), existing['id'])
            )
        else:
            # Insert new wallet
            await db.execute(
                "INSERT INTO wallets (user_id, address, blockchain, label, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, address, blockchain, label, datetime.now())
            )
        await db.commit()

async def get_all_wallets(user_id: int = None):
    """Get all wallets for a user.

    Args:
        user_id: User ID (defaults to current user from context)

    Returns:
        List of wallet records
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM wallets WHERE user_id = ? ORDER BY blockchain, id",
                (user_id,)
            )
        else:
            # Fallback for backward compatibility during migration
            cursor = await db.execute("SELECT * FROM wallets ORDER BY blockchain, id")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_wallet_by_address(address: str, blockchain: str = None, user_id: int = None):
    """Get a wallet by its address for a specific user.

    Args:
        address: Wallet address
        blockchain: Optional blockchain filter
        user_id: User ID (defaults to current user from context)

    Returns:
        Wallet record or None
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            if blockchain:
                cursor = await db.execute(
                    "SELECT * FROM wallets WHERE user_id = ? AND address = ? AND blockchain = ?",
                    (user_id, address, blockchain)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM wallets WHERE user_id = ? AND address = ?",
                    (user_id, address)
                )
        else:
            # Fallback for backward compatibility during migration
            if blockchain:
                cursor = await db.execute(
                    "SELECT * FROM wallets WHERE address = ? AND blockchain = ?",
                    (address, blockchain)
                )
            else:
                cursor = await db.execute("SELECT * FROM wallets WHERE address = ?", (address,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_wallets_by_address(address: str):
    """Get all wallets with a given address (across all blockchains)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM wallets WHERE address = ?", (address,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def save_balance(wallet_id: int, amount: str, unit: str, user_id: int = None):
    """Save or update the balance for a wallet."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Get user_id from wallet if not provided
        if user_id is None:
            cursor = await db.execute("SELECT user_id FROM wallets WHERE id = ?", (wallet_id,))
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
            else:
                raise ValueError(f"Wallet {wallet_id} not found")

        await db.execute("""
            INSERT INTO balances (wallet_id, user_id, amount, unit, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (wallet_id, user_id, amount, unit, datetime.now()))
        await db.commit()

async def clear_wallet_balances(wallet_id: int):
    """Clear existing balances for a wallet before refresh."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM balances WHERE wallet_id = ?", (wallet_id,))
        await db.commit()

async def save_native_assets(wallet_id: int, assets: list, user_id: int = None):
    """Save native assets for a wallet."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Get user_id from wallet if not provided
        if user_id is None:
            cursor = await db.execute("SELECT user_id FROM wallets WHERE id = ?", (wallet_id,))
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
            else:
                raise ValueError(f"Wallet {wallet_id} not found")

        # Clear existing assets
        await db.execute("DELETE FROM native_assets WHERE wallet_id = ?", (wallet_id,))

        # Insert new assets
        for asset in assets:
            await db.execute("""
                INSERT INTO native_assets (wallet_id, user_id, asset_id, policy_id, asset_name, quantity, decimals, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet_id,
                user_id,
                asset.get('asset_id', ''),
                asset.get('policy_id', ''),
                asset.get('asset_name', ''),
                asset.get('quantity', '0'),
                asset.get('decimals', 0),
                datetime.now()
            ))
        await db.commit()

async def get_wallet_assets(wallet_id: int):
    """Get all native assets for a wallet."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM native_assets WHERE wallet_id = ? ORDER BY asset_name",
            (wallet_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_wallet_balance(wallet_id: int):
    """Get the latest balance for a wallet."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM balances WHERE wallet_id = ? ORDER BY updated_at DESC LIMIT 1",
            (wallet_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_wallet_label(address: str, label: str, blockchain: str = None):
    """Update the label for a wallet.

    If blockchain is provided, updates only the wallet for that chain.
    If not, updates all wallets with that address.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if blockchain:
            await db.execute("""
                UPDATE wallets SET label = ?, updated_at = ?
                WHERE address = ? AND blockchain = ?
            """, (label, datetime.now(), address, blockchain))
        else:
            await db.execute("""
                UPDATE wallets SET label = ?, updated_at = ?
                WHERE address = ?
            """, (label, datetime.now(), address))
        await db.commit()


async def delete_wallet(wallet_id: int):
    """Delete a wallet and all its associated data."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Delete associated balances
        await db.execute("DELETE FROM balances WHERE wallet_id = ?", (wallet_id,))
        # Delete associated native assets
        await db.execute("DELETE FROM native_assets WHERE wallet_id = ?", (wallet_id,))
        # Delete the wallet
        await db.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
        await db.commit()


# Cache functions
async def get_cache(key: str, user_id: Optional[int] = None):
    """Get a value from the cache if not expired.

    Args:
        key: Cache key
        user_id: User ID for user-specific cache, None for system-wide cache
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT value, expires_at FROM cache WHERE user_id = ? AND key = ?",
                (user_id, key)
            )
        else:
            cursor = await db.execute(
                "SELECT value, expires_at FROM cache WHERE user_id IS NULL AND key = ?",
                (key,)
            )
        row = await cursor.fetchone()
        if row:
            expires_at = datetime.fromisoformat(row['expires_at'])
            if datetime.now() < expires_at:
                import json
                return json.loads(row['value'])
        return None


async def set_cache(key: str, value, ttl_seconds: int = 300, user_id: Optional[int] = None):
    """Set a value in the cache with TTL.

    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl_seconds: Time to live in seconds
        user_id: User ID for user-specific cache, None for system-wide cache
    """
    import json
    expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO cache (user_id, key, value, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET
                value = excluded.value,
                expires_at = excluded.expires_at
        """, (user_id, key, json.dumps(value), expires_at.isoformat()))
        await db.commit()


async def clear_cache(key_pattern: str = None, user_id: Optional[int] = None):
    """Clear cache entries. If pattern provided, only clear matching keys.

    Args:
        key_pattern: Optional pattern to match keys (uses LIKE)
        user_id: User ID to clear cache for, None clears system-wide cache, omit to clear all
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id is not None:
            # Clear user-specific cache
            if key_pattern:
                await db.execute("DELETE FROM cache WHERE user_id = ? AND key LIKE ?", (user_id, f"%{key_pattern}%"))
            else:
                await db.execute("DELETE FROM cache WHERE user_id = ?", (user_id,))
        elif key_pattern:
            # Clear all caches matching pattern
            await db.execute("DELETE FROM cache WHERE key LIKE ?", (f"%{key_pattern}%",))
        else:
            # Clear all caches
            await db.execute("DELETE FROM cache")
        await db.commit()


async def get_cache_status():
    """Get status of all cache entries."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT key, expires_at FROM cache ORDER BY key"
        )
        rows = await cursor.fetchall()
        now = datetime.now()
        return [
            {
                'key': row['key'],
                'expires_at': row['expires_at'],
                'expired': datetime.fromisoformat(row['expires_at']) < now
            }
            for row in rows
        ]


# Portfolio snapshot functions
async def save_portfolio_snapshot(snapshot_data: dict, user_id: int = None):
    """Save a daily portfolio snapshot for a user.

    Args:
        snapshot_data: Snapshot data dictionary
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO portfolio_snapshots (
                user_id, snapshot_date, snapshot_time, total_value_usd,
                ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price,
                sol_amount, sol_price,
                staking_value_usd, defi_value_usd, exchange_value_usd, nft_value_usd,
                tracked_tokens_value_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, snapshot_date) DO UPDATE SET
                snapshot_time = excluded.snapshot_time,
                total_value_usd = excluded.total_value_usd,
                ada_amount = excluded.ada_amount,
                ada_price = excluded.ada_price,
                btc_amount = excluded.btc_amount,
                btc_price = excluded.btc_price,
                eth_amount = excluded.eth_amount,
                eth_price = excluded.eth_price,
                sol_amount = excluded.sol_amount,
                sol_price = excluded.sol_price,
                staking_value_usd = excluded.staking_value_usd,
                defi_value_usd = excluded.defi_value_usd,
                exchange_value_usd = excluded.exchange_value_usd,
                nft_value_usd = excluded.nft_value_usd,
                tracked_tokens_value_usd = excluded.tracked_tokens_value_usd
        """, (
            user_id,
            snapshot_data['snapshot_date'],
            snapshot_data['snapshot_time'],
            snapshot_data['total_value_usd'],
            snapshot_data.get('ada_amount', 0),
            snapshot_data.get('ada_price', 0),
            snapshot_data.get('btc_amount', 0),
            snapshot_data.get('btc_price', 0),
            snapshot_data.get('eth_amount', 0),
            snapshot_data.get('eth_price', 0),
            snapshot_data.get('sol_amount', 0),
            snapshot_data.get('sol_price', 0),
            snapshot_data.get('staking_value_usd', 0),
            snapshot_data.get('defi_value_usd', 0),
            snapshot_data.get('exchange_value_usd', 0),
            snapshot_data.get('nft_value_usd', 0),
            snapshot_data.get('tracked_tokens_value_usd', 0)
        ))
        await db.commit()


async def get_portfolio_history(days: int = 7, user_id: int = None) -> list:
    """Get portfolio snapshots for a user.

    Args:
        days: Number of days of history to retrieve
        user_id: User ID (defaults to current user from context)

    Returns:
        List of snapshot records
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute("""
                SELECT snapshot_date, total_value_usd, snapshot_time,
                       ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price,
                       sol_amount, sol_price,
                       staking_value_usd, defi_value_usd, exchange_value_usd, nft_value_usd,
                       COALESCE(tracked_tokens_value_usd, 0) as tracked_tokens_value_usd
                FROM portfolio_snapshots
                WHERE user_id = ? AND snapshot_date >= date('now', ?)
                ORDER BY snapshot_date ASC
            """, (user_id, f'-{days} days'))
        else:
            # Fallback for backward compatibility
            cursor = await db.execute("""
                SELECT snapshot_date, total_value_usd, snapshot_time,
                       ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price,
                       sol_amount, sol_price,
                       staking_value_usd, defi_value_usd, exchange_value_usd, nft_value_usd,
                       COALESCE(tracked_tokens_value_usd, 0) as tracked_tokens_value_usd
                FROM portfolio_snapshots
                WHERE snapshot_date >= date('now', ?)
                ORDER BY snapshot_date ASC
            """, (f'-{days} days',))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_latest_snapshot_date(user_id: int = None) -> str:
    """Get the date of the most recent snapshot."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id is not None:
            cursor = await db.execute(
                "SELECT snapshot_date FROM portfolio_snapshots WHERE user_id = ? ORDER BY snapshot_date DESC LIMIT 1",
                (user_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT snapshot_date FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
            )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_latest_snapshot_time(user_id: int = None) -> str:
    """Get the timestamp of the most recent snapshot."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id is not None:
            cursor = await db.execute(
                "SELECT snapshot_time FROM portfolio_snapshots WHERE user_id = ? ORDER BY snapshot_date DESC LIMIT 1",
                (user_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT snapshot_time FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
            )
        row = await cursor.fetchone()
        return row[0] if row else None


# NFT floor price functions
async def save_nft_floor_price(price_data: dict):
    """Save an NFT collection floor price record."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO nft_floor_prices (
                policy_id, collection_name, floor_price_ada, listings,
                supply, verified, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            price_data['policy_id'],
            price_data.get('collection_name'),
            price_data.get('floor_price_ada'),
            price_data.get('listings', 0),
            price_data.get('supply'),
            1 if price_data.get('verified') else 0,
            price_data.get('source'),
            price_data.get('fetched_at', datetime.now().isoformat())
        ))
        await db.commit()


async def get_latest_nft_floor_price(policy_id: str) -> dict:
    """Get the most recent floor price for a collection."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM nft_floor_prices
            WHERE policy_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
        """, (policy_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_nft_floor_prices() -> list:
    """Get latest floor price for all collections."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get the most recent price for each policy_id
        cursor = await db.execute("""
            SELECT policy_id, collection_name, floor_price_ada, listings,
                   supply, verified, source, fetched_at
            FROM nft_floor_prices
            WHERE (policy_id, fetched_at) IN (
                SELECT policy_id, MAX(fetched_at)
                FROM nft_floor_prices
                GROUP BY policy_id
            )
            ORDER BY fetched_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_collections_needing_price_update(max_age_days: int = 7, limit: int = 10) -> list:
    """
    Get policy IDs that need price updates, prioritizing:
    1. Collections with no price data at all
    2. Collections with partial data (no floor price)
    3. Collections with oldest complete price data

    Args:
        max_age_days: Consider data older than this as stale
        limit: Maximum number of collections to return

    Returns:
        List of policy_ids to fetch prices for
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        needs_update = []

        # Get all unique policy_ids from native_assets (NFTs have quantity=1)
        cursor = await db.execute("""
            SELECT DISTINCT policy_id FROM native_assets
            WHERE quantity = '1' AND policy_id IS NOT NULL AND policy_id != ''
        """)
        all_policies = set(row['policy_id'] for row in await cursor.fetchall())

        # Get policy_ids that have any price data
        cursor = await db.execute("""
            SELECT DISTINCT policy_id FROM nft_floor_prices
        """)
        policies_with_data = set(row['policy_id'] for row in await cursor.fetchall())

        # Priority 1: Collections with no data at all
        no_data_policies = list(all_policies - policies_with_data)
        needs_update.extend(no_data_policies[:limit])

        # Priority 2: Collections with partial data (no floor price yet)
        if len(needs_update) < limit:
            cursor = await db.execute("""
                SELECT DISTINCT policy_id FROM nft_floor_prices
                WHERE floor_price_ada IS NULL
                AND policy_id NOT IN ({})
            """.format(','.join('?' * len(needs_update)) if needs_update else "''"),
                needs_update if needs_update else []
            )
            for row in await cursor.fetchall():
                if len(needs_update) >= limit:
                    break
                if row['policy_id'] not in needs_update:
                    needs_update.append(row['policy_id'])

        # Priority 3: Collections with oldest data (stale)
        if len(needs_update) < limit:
            cutoff_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()
            placeholders = ','.join('?' * len(needs_update)) if needs_update else "''"
            cursor = await db.execute("""
                SELECT policy_id, MAX(fetched_at) as last_fetch
                FROM nft_floor_prices
                WHERE policy_id NOT IN ({})
                AND floor_price_ada IS NOT NULL
                GROUP BY policy_id
                HAVING last_fetch < ?
                ORDER BY last_fetch ASC
                LIMIT ?
            """.format(placeholders),
                (needs_update if needs_update else []) + [cutoff_date, limit - len(needs_update)]
            )
            for row in await cursor.fetchall():
                if row['policy_id'] not in needs_update:
                    needs_update.append(row['policy_id'])

        return needs_update[:limit]


async def get_nft_price_stats() -> dict:
    """Get statistics about NFT price data coverage."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Total unique collections in portfolio
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT policy_id) as count FROM native_assets
            WHERE quantity = '1' AND policy_id IS NOT NULL AND policy_id != ''
        """)
        total_collections = (await cursor.fetchone())[0]

        # Collections with any data (even partial)
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT policy_id) as count FROM nft_floor_prices
        """)
        collections_with_data = (await cursor.fetchone())[0]

        # Collections with actual floor prices
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT policy_id) as count FROM nft_floor_prices
            WHERE floor_price_ada IS NOT NULL
        """)
        collections_with_floor_price = (await cursor.fetchone())[0]

        # Collections with recent price data (last 7 days)
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        cursor = await db.execute("""
            SELECT COUNT(DISTINCT policy_id) as count FROM nft_floor_prices
            WHERE fetched_at > ? AND floor_price_ada IS NOT NULL
        """, (cutoff,))
        collections_recent = (await cursor.fetchone())[0]

        # Oldest and newest fetch times
        cursor = await db.execute("""
            SELECT MIN(fetched_at) as oldest, MAX(fetched_at) as newest
            FROM nft_floor_prices
        """)
        row = await cursor.fetchone()

        return {
            'total_collections': total_collections,
            'collections_with_data': collections_with_data,
            'collections_with_floor_price': collections_with_floor_price,
            'collections_recent_7d': collections_recent,
            'coverage_percent': round(collections_with_floor_price / total_collections * 100, 1) if total_collections > 0 else 0,
            'oldest_fetch': row[0],
            'newest_fetch': row[1]
        }


# Custom token functions
async def add_custom_token(token_data: dict, user_id: int = None) -> int:
    """Add a custom token for a user.

    Args:
        token_data: Token data dictionary
        user_id: User ID (defaults to current user from context)

    Returns:
        Token ID
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO custom_tokens (
                user_id, policy_id, asset_name, ticker, blockchain, quantity,
                decimals, label, token_name, price_usd, last_price_update
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, policy_id, asset_name) DO UPDATE SET
                quantity = excluded.quantity,
                label = COALESCE(excluded.label, custom_tokens.label),
                token_name = COALESCE(excluded.token_name, custom_tokens.token_name),
                price_usd = COALESCE(excluded.price_usd, custom_tokens.price_usd),
                last_price_update = COALESCE(excluded.last_price_update, custom_tokens.last_price_update),
                updated_at = CURRENT_TIMESTAMP
        """, (
            user_id,
            token_data['policy_id'],
            token_data.get('asset_name', ''),
            token_data.get('ticker'),
            token_data['blockchain'],
            str(token_data['quantity']),
            token_data.get('decimals', 0),
            token_data.get('label'),
            token_data.get('token_name'),
            token_data.get('price_usd'),
            datetime.now() if token_data.get('price_usd') else None
        ))
        await db.commit()
        return cursor.lastrowid


async def get_all_custom_tokens(user_id: int = None) -> list:
    """Get all custom tokens for a user.

    Args:
        user_id: User ID (defaults to current user from context)

    Returns:
        List of custom token records
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute("""
                SELECT * FROM custom_tokens
                WHERE user_id = ?
                ORDER BY blockchain, token_name, ticker
            """, (user_id,))
        else:
            # Fallback for backward compatibility
            cursor = await db.execute("""
                SELECT * FROM custom_tokens
                ORDER BY blockchain, token_name, ticker
            """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_custom_token_by_id(token_id: int, user_id: int = None) -> dict:
    """Get a custom token by ID for a user.

    Args:
        token_id: Token ID
        user_id: User ID (defaults to current user from context)

    Returns:
        Token record or None
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM custom_tokens WHERE id = ? AND user_id = ?",
                (token_id, user_id)
            )
        else:
            # Fallback for backward compatibility
            cursor = await db.execute(
                "SELECT * FROM custom_tokens WHERE id = ?",
                (token_id,)
            )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_custom_token_by_policy(policy_id: str, asset_name: str = '', user_id: int = None) -> dict:
    """Get a custom token by policy ID and asset name for a user.

    Args:
        policy_id: Token policy ID
        asset_name: Token asset name
        user_id: User ID (defaults to current user from context)

    Returns:
        Token record or None
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM custom_tokens WHERE user_id = ? AND policy_id = ? AND asset_name = ?",
                (user_id, policy_id, asset_name)
            )
        else:
            # Fallback for backward compatibility
            cursor = await db.execute(
                "SELECT * FROM custom_tokens WHERE policy_id = ? AND asset_name = ?",
                (policy_id, asset_name)
            )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_custom_token(token_id: int, updates: dict):
    """Update a custom token."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        set_clauses = []
        values = []
        for key, value in updates.items():
            if key in ['quantity', 'label', 'token_name', 'price_usd', 'ticker', 'include_in_total']:
                set_clauses.append(f"{key} = ?")
                values.append(value)

        if 'price_usd' in updates:
            set_clauses.append("last_price_update = ?")
            values.append(datetime.now())

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(token_id)

        await db.execute(f"""
            UPDATE custom_tokens
            SET {', '.join(set_clauses)}
            WHERE id = ?
        """, values)
        await db.commit()


async def delete_custom_token(token_id: int):
    """Delete a custom token."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM custom_tokens WHERE id = ?", (token_id,))
        await db.commit()


async def update_custom_token_prices(prices: dict):
    """Update prices for all custom tokens that have matching tickers."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        for ticker, price in prices.items():
            await db.execute("""
                UPDATE custom_tokens
                SET price_usd = ?, last_price_update = ?
                WHERE UPPER(ticker) = UPPER(?)
            """, (price, datetime.now(), ticker))
        await db.commit()


# ============================================================================
# TOKEN METADATA FUNCTIONS
# ============================================================================

async def get_token_metadata(asset_id: str) -> dict:
    """Get cached token metadata by asset_id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM token_metadata WHERE asset_id = ?",
            (asset_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def save_token_metadata(metadata: dict):
    """Save or update token metadata."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO token_metadata (asset_id, policy_id, asset_name, ticker, name, decimals, logo_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                policy_id = excluded.policy_id,
                asset_name = excluded.asset_name,
                ticker = COALESCE(excluded.ticker, token_metadata.ticker),
                name = COALESCE(excluded.name, token_metadata.name),
                decimals = excluded.decimals,
                logo_url = COALESCE(excluded.logo_url, token_metadata.logo_url),
                updated_at = excluded.updated_at
        """, (
            metadata.get('asset_id'),
            metadata.get('policy_id'),
            metadata.get('asset_name'),
            metadata.get('ticker'),
            metadata.get('name'),
            metadata.get('decimals', 0),
            metadata.get('logo_url'),
            datetime.now()
        ))
        await db.commit()


async def get_all_token_metadata() -> list:
    """Get all cached token metadata."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM token_metadata")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def toggle_token_tracking(asset_id: str, track: bool) -> bool:
    """Toggle whether a token should be tracked for pricing."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if token exists in metadata
        cursor = await db.execute(
            "SELECT asset_id FROM token_metadata WHERE asset_id = ?",
            (asset_id,)
        )
        exists = await cursor.fetchone()

        if exists:
            await db.execute(
                "UPDATE token_metadata SET track_for_pricing = ?, updated_at = ? WHERE asset_id = ?",
                (1 if track else 0, datetime.now(), asset_id)
            )
        else:
            # Create entry with just the asset_id and tracking flag
            await db.execute(
                "INSERT INTO token_metadata (asset_id, track_for_pricing, updated_at) VALUES (?, ?, ?)",
                (asset_id, 1 if track else 0, datetime.now())
            )
        await db.commit()
        return True


async def get_tracked_tokens() -> list:
    """Get all tokens that are marked for tracking."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM token_metadata WHERE track_for_pricing = 1"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_native_asset_decimals(asset_id: str, decimals: int):
    """Update decimals for a native asset in all wallet records."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE native_assets SET decimals = ? WHERE asset_id = ?",
            (decimals, asset_id)
        )
        await db.commit()


# ============ API Settings Functions ============

async def get_api_setting(api_name: str, user_id: int = None) -> dict:
    """Get API setting by name for a user.

    Args:
        api_name: API name
        user_id: User ID (defaults to current user from context)

    Returns:
        API setting record or None
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM api_settings WHERE user_id = ? AND api_name = ?",
                (user_id, api_name)
            )
        else:
            # Fallback for backward compatibility
            cursor = await db.execute(
                "SELECT * FROM api_settings WHERE api_name = ?",
                (api_name,)
            )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_api_settings(user_id: int = None) -> list:
    """Get all API settings for a user.

    Args:
        user_id: User ID (defaults to current user from context)

    Returns:
        List of API setting records
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM api_settings WHERE user_id = ?",
                (user_id,)
            )
        else:
            # Fallback for backward compatibility
            cursor = await db.execute("SELECT * FROM api_settings")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def save_api_setting(api_name: str, api_key: str, enabled: bool = True, user_id: int = None):
    """Save or update an API setting for a user.

    Args:
        api_name: API name
        api_key: API key
        enabled: Whether the API is enabled
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO api_settings (user_id, api_name, api_key, enabled, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, api_name) DO UPDATE SET
                api_key = excluded.api_key,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
        """, (user_id, api_name, api_key, 1 if enabled else 0, datetime.now()))
        await db.commit()


async def delete_api_setting(api_name: str, user_id: int = None):
    """Disable an API and clear its key for a user.

    Args:
        api_name: API name
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO api_settings (user_id, api_name, api_key, enabled, updated_at)
            VALUES (?, ?, NULL, 0, ?)
            ON CONFLICT(user_id, api_name) DO UPDATE SET
                api_key = NULL,
                enabled = 0,
                updated_at = excluded.updated_at
        """, (user_id, api_name, datetime.now()))
        await db.commit()


async def get_api_key(api_name: str, user_id: int = None) -> str:
    """Get API key if enabled for a user.

    Args:
        api_name: API name
        user_id: User ID (defaults to current user from context)

    Returns:
        API key or empty string
    """
    setting = await get_api_setting(api_name, user_id)
    if setting and setting.get('enabled') and setting.get('api_key'):
        return setting['api_key']
    return ""


# ============ Security Settings Functions ============

async def get_security_settings(user_id: int = None) -> dict:
    """Get security settings for a user.

    Args:
        user_id: User ID (defaults to current user from context)

    Returns:
        Security settings record
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM security_settings WHERE user_id = ?",
                (user_id,)
            )
        else:
            # Fallback for backward compatibility - get first record
            cursor = await db.execute(
                "SELECT * FROM security_settings LIMIT 1"
            )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        # Return defaults if no row exists
        return {
            'user_id': user_id,
            'ssl_mode': 'http',
            'cert_path': None,
            'key_path': None,
            'cert_type': None,
            'cert_expires_at': None,
            'pending_mode': None,
            'restart_required': 0,
            'updated_at': None
        }


async def save_security_settings(
    ssl_mode: str,
    cert_path: str = None,
    key_path: str = None,
    cert_type: str = None,
    cert_expires_at: str = None,
    user_id: int = None
):
    """Save security settings for a user.

    Args:
        ssl_mode: SSL mode (http, https_self_signed, https_letsencrypt)
        cert_path: Path to certificate file
        key_path: Path to key file
        cert_type: Certificate type
        cert_expires_at: Certificate expiration timestamp
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO security_settings (user_id, ssl_mode, cert_path, key_path, cert_type, cert_expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                ssl_mode = excluded.ssl_mode,
                cert_path = excluded.cert_path,
                key_path = excluded.key_path,
                cert_type = excluded.cert_type,
                cert_expires_at = excluded.cert_expires_at,
                pending_mode = NULL,
                restart_required = 0,
                updated_at = excluded.updated_at
        """, (user_id, ssl_mode, cert_path, key_path, cert_type, cert_expires_at, datetime.now()))
        await db.commit()


async def set_pending_mode(pending_mode: str, user_id: int = None):
    """Set pending mode change for a user (requires restart to take effect).

    Args:
        pending_mode: Pending SSL mode
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE security_settings
            SET pending_mode = ?, restart_required = 1, updated_at = ?
            WHERE user_id = ?
        """, (pending_mode, datetime.now(), user_id))
        await db.commit()


async def clear_pending_mode(user_id: int = None):
    """Clear pending mode after restart for a user.

    Args:
        user_id: User ID (defaults to current user from context)
    """
    if user_id is None:
        user_id = get_current_user_id()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE security_settings
            SET pending_mode = NULL, restart_required = 0, updated_at = ?
            WHERE user_id = ?
        """, (datetime.now(), user_id))
        await db.commit()


# ============ API Usage Tracking Functions ============

async def record_api_call(api_name: str, period_seconds: int = 86400):
    """
    Record an API call for usage tracking.
    Groups calls into periods (default: daily).
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.now()
        # Calculate period start (beginning of current period)
        period_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) if period_seconds == 86400 else now.replace(
            minute=0, second=0, microsecond=0
        ) if period_seconds == 3600 else now.replace(second=0, microsecond=0)

        period_end = period_start + timedelta(seconds=period_seconds)

        # Try to update existing record, insert if not exists
        await db.execute("""
            INSERT INTO api_usage (api_name, period_start, period_end, call_count, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(api_name, period_start) DO UPDATE SET
                call_count = call_count + 1,
                updated_at = excluded.updated_at
        """, (api_name, period_start.isoformat(), period_end.isoformat(), now.isoformat()))
        await db.commit()


async def get_api_usage(api_name: str, period_seconds: int = 86400) -> dict:
    """
    Get current API usage for the current period.
    Returns usage data with call count and period info.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now()

        # Calculate current period start
        period_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) if period_seconds == 86400 else now.replace(
            minute=0, second=0, microsecond=0
        ) if period_seconds == 3600 else now.replace(second=0, microsecond=0)

        cursor = await db.execute("""
            SELECT * FROM api_usage
            WHERE api_name = ? AND period_start = ?
        """, (api_name, period_start.isoformat()))
        row = await cursor.fetchone()

        if row:
            return {
                'api_name': row['api_name'],
                'call_count': row['call_count'],
                'period_start': row['period_start'],
                'period_end': row['period_end']
            }
        return {
            'api_name': api_name,
            'call_count': 0,
            'period_start': period_start.isoformat(),
            'period_end': (period_start + timedelta(seconds=period_seconds)).isoformat()
        }


async def get_all_api_usage() -> list:
    """Get current period usage for all APIs."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now()
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        cursor = await db.execute("""
            SELECT * FROM api_usage
            WHERE period_start = ?
            ORDER BY api_name
        """, (period_start.isoformat(),))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_api_rate_limit(api_name: str) -> dict:
    """Get custom rate limit for an API."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM api_rate_limits WHERE api_name = ?",
            (api_name,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def save_api_rate_limit(api_name: str, requests_limit: int, period_seconds: int = 86400):
    """Save or update custom rate limit for an API."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO api_rate_limits (api_name, requests_limit, period_seconds, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(api_name) DO UPDATE SET
                requests_limit = excluded.requests_limit,
                period_seconds = excluded.period_seconds,
                updated_at = excluded.updated_at
        """, (api_name, requests_limit, period_seconds, datetime.now()))
        await db.commit()


async def delete_api_rate_limit(api_name: str):
    """Delete custom rate limit for an API (reverts to default)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM api_rate_limits WHERE api_name = ?", (api_name,))
        await db.commit()


async def get_all_api_rate_limits() -> list:
    """Get all custom rate limits."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM api_rate_limits")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def cleanup_old_api_usage(days_to_keep: int = 30):
    """Remove API usage records older than specified days."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cutoff = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        await db.execute(
            "DELETE FROM api_usage WHERE period_end < ?",
            (cutoff,)
        )
        await db.commit()


# ============================================================================
# SESSION MANAGEMENT (Database-backed sessions for multi-process safety)
# ============================================================================

async def create_session(token: str, username: str, user_id: int, is_demo: bool, expires_minutes: int = 480):
    """
    Create a new session in the database.

    Args:
        token: Session token
        username: Username
        user_id: User ID
        is_demo: Whether this is a demo account
        expires_minutes: Session expiration time in minutes
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        expires = datetime.utcnow() + timedelta(minutes=expires_minutes)
        await db.execute(
            """INSERT OR REPLACE INTO sessions
               (token, username, user_id, is_demo, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (token, username, user_id, is_demo, expires.isoformat(), datetime.utcnow().isoformat())
        )
        await db.commit()


async def get_session(token: str) -> Optional[dict]:
    """
    Get session data from database.

    Args:
        token: Session token

    Returns:
        Session dict with username, user_id, is_demo, expires_at or None if not found
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE token = ?",
            (token,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)


async def delete_session(token: str):
    """Delete a session from the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await db.commit()


async def cleanup_expired_sessions():
    """Remove expired sessions from the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        now = datetime.utcnow().isoformat()
        await db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        await db.commit()
