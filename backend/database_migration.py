#!/usr/bin/env python3
"""
ABCT Database Migration Script
Migrates from old schema (portfolio.db + nft_images.db) to new secure multi-user schema
"""

import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
OLD_PORTFOLIO_DB = DATA_DIR / "portfolio.db"
OLD_NFT_IMAGES_DB = DATA_DIR / "nft_images.db"
NEW_DB = DATA_DIR / "abct.db"
BACKUP_DIR = DATA_DIR / "migration_backups"

# Create backup directory
BACKUP_DIR.mkdir(exist_ok=True)

class DatabaseMigration:
    def __init__(self):
        self.old_portfolio_conn = None
        self.old_nft_conn = None
        self.new_conn = None

    def backup_databases(self):
        """Create backups of current databases"""
        print("📦 Creating backups...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if OLD_PORTFOLIO_DB.exists():
            backup_path = BACKUP_DIR / f"portfolio_{timestamp}.db"
            shutil.copy2(OLD_PORTFOLIO_DB, backup_path)
            print(f"  ✅ Backed up portfolio.db → {backup_path}")

        if OLD_NFT_IMAGES_DB.exists():
            backup_path = BACKUP_DIR / f"nft_images_{timestamp}.db"
            shutil.copy2(OLD_NFT_IMAGES_DB, backup_path)
            print(f"  ✅ Backed up nft_images.db → {backup_path}")

    def connect_databases(self):
        """Connect to old and new databases"""
        print("\n🔌 Connecting to databases...")
        self.old_portfolio_conn = sqlite3.connect(OLD_PORTFOLIO_DB)
        self.old_portfolio_conn.row_factory = sqlite3.Row
        print("  ✅ Connected to old portfolio.db")

        if OLD_NFT_IMAGES_DB.exists():
            self.old_nft_conn = sqlite3.connect(OLD_NFT_IMAGES_DB)
            self.old_nft_conn.row_factory = sqlite3.Row
            print("  ✅ Connected to old nft_images.db")

        self.new_conn = sqlite3.connect(NEW_DB)
        self.new_conn.execute("PRAGMA foreign_keys = ON")
        print("  ✅ Created new abct.db")

    def create_new_schema(self):
        """Create new database schema"""
        print("\n🏗️  Creating new schema...")

        cursor = self.new_conn.cursor()

        # Users table (unchanged structure, just cleaner)
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_demo INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX idx_users_username ON users(username)")
        print("  ✅ Created users table")

        # Wallets table (add updated_at if missing)
        cursor.execute("""
            CREATE TABLE wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                blockchain TEXT NOT NULL,
                label TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, address, blockchain),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX idx_wallets_user_id ON wallets(user_id)")
        cursor.execute("CREATE INDEX idx_wallets_blockchain ON wallets(blockchain)")
        print("  ✅ Created wallets table")

        # Balances table (ADD user_id)
        cursor.execute("""
            CREATE TABLE balances (
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
        cursor.execute("CREATE INDEX idx_balances_wallet_id ON balances(wallet_id)")
        cursor.execute("CREATE INDEX idx_balances_user_id ON balances(user_id)")
        print("  ✅ Created balances table")

        # Native assets table (ADD user_id)
        cursor.execute("""
            CREATE TABLE native_assets (
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
        cursor.execute("CREATE INDEX idx_native_assets_wallet_id ON native_assets(wallet_id)")
        cursor.execute("CREATE INDEX idx_native_assets_user_id ON native_assets(user_id)")
        cursor.execute("CREATE INDEX idx_native_assets_policy_id ON native_assets(policy_id)")
        cursor.execute("CREATE INDEX idx_native_assets_asset_id ON native_assets(asset_id)")
        print("  ✅ Created native_assets table")

        # NFT images table (ADD user_id, MOVED from nft_images.db)
        cursor.execute("""
            CREATE TABLE nft_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                asset_id TEXT NOT NULL,
                blockchain TEXT NOT NULL,
                image_url TEXT,
                image_data BLOB,
                image_format TEXT,
                image_size INTEGER,
                width INTEGER,
                height INTEGER,
                thumbnail_data BLOB,
                fetch_status TEXT DEFAULT 'pending',
                error_message TEXT,
                fetched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, asset_id, blockchain),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX idx_nft_images_user_id ON nft_images(user_id)")
        cursor.execute("CREATE INDEX idx_nft_images_blockchain ON nft_images(blockchain)")
        cursor.execute("CREATE INDEX idx_nft_images_status ON nft_images(fetch_status)")
        print("  ✅ Created nft_images table")

        # Cache table (ADD user_id, REDESIGNED)
        cursor.execute("""
            CREATE TABLE cache (
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
        cursor.execute("CREATE INDEX idx_cache_user_key ON cache(user_id, key)")
        cursor.execute("CREATE INDEX idx_cache_expires ON cache(expires_at)")
        print("  ✅ Created cache table")

        # Custom tokens table (already has user_id, add timestamps)
        cursor.execute("""
            CREATE TABLE custom_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, policy_id, asset_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX idx_custom_tokens_user_id ON custom_tokens(user_id)")
        cursor.execute("CREATE INDEX idx_custom_tokens_blockchain ON custom_tokens(blockchain)")
        print("  ✅ Created custom_tokens table")

        # Portfolio snapshots table (already has user_id)
        cursor.execute("""
            CREATE TABLE portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, snapshot_date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX idx_portfolio_snapshots_user_id ON portfolio_snapshots(user_id)")
        cursor.execute("CREATE INDEX idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date)")
        print("  ✅ Created portfolio_snapshots table")

        # Sessions table (already has user_id)
        cursor.execute("""
            CREATE TABLE sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                is_demo INTEGER DEFAULT 0,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX idx_sessions_user_id ON sessions(user_id)")
        cursor.execute("CREATE INDEX idx_sessions_expires ON sessions(expires_at)")
        print("  ✅ Created sessions table")

        # System-wide tables (no user_id)
        cursor.execute("""
            CREATE TABLE api_settings (
                api_name TEXT PRIMARY KEY,
                api_key TEXT,
                enabled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """)
        print("  ✅ Created api_settings table")

        cursor.execute("""
            CREATE TABLE security_settings (
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
        print("  ✅ Created security_settings table")

        cursor.execute("""
            CREATE TABLE nft_floor_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id TEXT NOT NULL,
                collection_name TEXT,
                floor_price_ada REAL,
                listings INTEGER DEFAULT 0,
                supply INTEGER,
                verified INTEGER DEFAULT 0,
                source TEXT,
                fetched_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(policy_id, fetched_at)
            )
        """)
        cursor.execute("CREATE INDEX idx_nft_floor_prices_policy ON nft_floor_prices(policy_id)")
        cursor.execute("CREATE INDEX idx_nft_floor_prices_fetched ON nft_floor_prices(fetched_at)")
        print("  ✅ Created nft_floor_prices table")

        cursor.execute("""
            CREATE TABLE token_metadata (
                asset_id TEXT PRIMARY KEY,
                policy_id TEXT,
                asset_name TEXT,
                ticker TEXT,
                name TEXT,
                decimals INTEGER DEFAULT 0,
                logo_url TEXT,
                track_for_pricing INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX idx_token_metadata_policy ON token_metadata(policy_id)")
        cursor.execute("CREATE INDEX idx_token_metadata_ticker ON token_metadata(ticker)")
        print("  ✅ Created token_metadata table")

        # NFT scheduler tables
        cursor.execute("""
            CREATE TABLE nft_scheduler_state (
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

        cursor.execute("""
            CREATE TABLE nft_scheduler_collections (
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
        cursor.execute("CREATE INDEX idx_nft_scheduler_collections_priority ON nft_scheduler_collections(priority DESC, last_updated ASC)")

        cursor.execute("""
            CREATE TABLE nft_scheduler_api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                policy_id TEXT,
                status_code INTEGER,
                called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX idx_nft_scheduler_api_calls_date ON nft_scheduler_api_calls(called_at)")
        print("  ✅ Created NFT scheduler tables")

        # API usage and rate limits
        cursor.execute("""
            CREATE TABLE api_usage (
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
        cursor.execute("CREATE INDEX idx_api_usage_api_period ON api_usage(api_name, period_start)")

        cursor.execute("""
            CREATE TABLE api_rate_limits (
                api_name TEXT PRIMARY KEY,
                requests_limit INTEGER NOT NULL,
                period_seconds INTEGER NOT NULL DEFAULT 86400,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✅ Created API tracking tables")

        self.new_conn.commit()
        print("\n✅ Schema creation complete!")

    def migrate_data(self):
        """Migrate data from old databases to new schema"""
        print("\n📊 Migrating data...")

        old_cur = self.old_portfolio_conn.cursor()
        new_cur = self.new_conn.cursor()

        # 1. Migrate users (unchanged)
        print("\n  Migrating users...")
        old_cur.execute("SELECT * FROM users")
        users = old_cur.fetchall()
        for user in users:
            new_cur.execute("""
                INSERT INTO users (id, username, password_hash, is_demo, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (
                user['id'],
                user['username'],
                user['password_hash'],
                user['is_demo'] if 'is_demo' in user.keys() else 0,
                user['created_at'] if 'created_at' in user.keys() else datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
        print(f"    ✅ Migrated {len(users)} users")

        # 2. Migrate wallets
        print("  Migrating wallets...")
        old_cur.execute("SELECT * FROM wallets")
        wallets = old_cur.fetchall()
        for wallet in wallets:
            new_cur.execute("""
                INSERT INTO wallets (id, user_id, address, blockchain, label, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                wallet['id'],
                wallet['user_id'],
                wallet['address'],
                wallet['blockchain'],
                wallet['label'] if 'label' in wallet.keys() else None,
                wallet['created_at'] if 'created_at' in wallet.keys() else datetime.now().isoformat(),
                wallet['updated_at'] if 'updated_at' in wallet.keys() else datetime.now().isoformat()
            ))
        print(f"    ✅ Migrated {len(wallets)} wallets")

        # Create wallet_id to user_id mapping for later
        wallet_to_user = {}
        for wallet in wallets:
            wallet_to_user[wallet['id']] = wallet['user_id']

        # 3. Migrate balances (ADD user_id from wallet)
        print("  Migrating balances...")
        old_cur.execute("SELECT * FROM balances")
        balances = old_cur.fetchall()
        migrated_balances = 0
        for balance in balances:
            wallet_id = balance['wallet_id']
            if wallet_id in wallet_to_user:
                user_id = wallet_to_user[wallet_id]
                new_cur.execute("""
                    INSERT INTO balances (wallet_id, user_id, amount, unit, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    wallet_id,
                    user_id,
                    balance['amount'],
                    balance['unit'],
                    balance['updated_at'] if 'updated_at' in balance.keys() else datetime.now().isoformat(),
                    balance['updated_at'] if 'updated_at' in balance.keys() else datetime.now().isoformat()
                ))
                migrated_balances += 1
        print(f"    ✅ Migrated {migrated_balances} balances")

        # 4. Migrate native_assets (ADD user_id from wallet)
        print("  Migrating native_assets...")
        old_cur.execute("SELECT * FROM native_assets")
        assets = old_cur.fetchall()
        migrated_assets = 0
        for asset in assets:
            wallet_id = asset['wallet_id']
            if wallet_id in wallet_to_user:
                user_id = wallet_to_user[wallet_id]
                new_cur.execute("""
                    INSERT INTO native_assets (wallet_id, user_id, asset_id, policy_id, asset_name, quantity, decimals, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wallet_id,
                    user_id,
                    asset['asset_id'],
                    asset['policy_id'] if 'policy_id' in asset.keys() else None,
                    asset['asset_name'] if 'asset_name' in asset.keys() else None,
                    asset['quantity'],
                    asset['decimals'] if 'decimals' in asset.keys() else 0,
                    asset['updated_at'] if 'updated_at' in asset.keys() else datetime.now().isoformat(),
                    asset['updated_at'] if 'updated_at' in asset.keys() else datetime.now().isoformat()
                ))
                migrated_assets += 1
        print(f"    ✅ Migrated {migrated_assets} native assets")

        # 5. Migrate NFT images (ADD user_id based on asset ownership)
        print("  Migrating NFT images...")
        migrated_nft_images = 0
        if self.old_nft_conn:
            nft_cur = self.old_nft_conn.cursor()
            nft_cur.execute("SELECT * FROM nft_images")
            nft_images = nft_cur.fetchall()

            # Build asset_id to user_id mapping from native_assets
            asset_to_user = {}
            for asset in assets:
                if asset['wallet_id'] in wallet_to_user:
                    asset_to_user[asset['asset_id']] = wallet_to_user[asset['wallet_id']]

            for nft_image in nft_images:
                asset_id = nft_image['asset_id']
                # Find which user owns this asset
                user_id = asset_to_user.get(asset_id)

                if user_id:  # Only migrate if we can determine ownership
                    new_cur.execute("""
                        INSERT INTO nft_images (
                            user_id, asset_id, blockchain, image_url, image_data, image_format,
                            image_size, width, height, thumbnail_data, fetch_status, error_message,
                            fetched_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        asset_id,
                        nft_image['blockchain'],
                        nft_image['image_url'] if 'image_url' in nft_image.keys() else None,
                        nft_image['image_data'] if 'image_data' in nft_image.keys() else None,
                        nft_image['image_format'] if 'image_format' in nft_image.keys() else None,
                        nft_image['image_size'] if 'image_size' in nft_image.keys() else None,
                        nft_image['width'] if 'width' in nft_image.keys() else None,
                        nft_image['height'] if 'height' in nft_image.keys() else None,
                        nft_image['thumbnail_data'] if 'thumbnail_data' in nft_image.keys() else None,
                        nft_image['fetch_status'] if 'fetch_status' in nft_image.keys() else 'pending',
                        nft_image['error_message'] if 'error_message' in nft_image.keys() else None,
                        nft_image['fetched_at'] if 'fetched_at' in nft_image.keys() else None,
                        nft_image['created_at'] if 'created_at' in nft_image.keys() else datetime.now().isoformat(),
                        nft_image['updated_at'] if 'updated_at' in nft_image.keys() else datetime.now().isoformat()
                    ))
                    migrated_nft_images += 1
            print(f"    ✅ Migrated {migrated_nft_images} NFT images")
        else:
            print(f"    ⏭️  No nft_images.db found, skipping")

        # 6. Migrate cache (SKIP - will be rebuilt, avoid old shared cache)
        print("  Migrating cache...")
        print(f"    ⏭️  Skipping cache migration (will be rebuilt per-user)")

        # 7. Migrate custom_tokens (already has user_id)
        print("  Migrating custom_tokens...")
        try:
            old_cur.execute("SELECT * FROM custom_tokens")
            custom_tokens = old_cur.fetchall()
            for token in custom_tokens:
                new_cur.execute("""
                    INSERT INTO custom_tokens (
                        user_id, policy_id, asset_name, ticker, blockchain, quantity, decimals,
                        label, token_name, price_usd, last_price_update, include_in_total, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    token['user_id'],
                    token['policy_id'],
                    token['asset_name'] if 'asset_name' in token.keys() else None,
                    token['ticker'] if 'ticker' in token.keys() else None,
                    token['blockchain'],
                    token['quantity'],
                    token['decimals'] if 'decimals' in token.keys() else 0,
                    token['label'] if 'label' in token.keys() else None,
                    token['token_name'] if 'token_name' in token.keys() else None,
                    token['price_usd'] if 'price_usd' in token.keys() else None,
                    token['last_price_update'] if 'last_price_update' in token.keys() else None,
                    token['include_in_total'] if 'include_in_total' in token.keys() else 1,
                    token['created_at'] if 'created_at' in token.keys() else datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(custom_tokens)} custom tokens")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No custom_tokens table found, skipping")

        # 8. Migrate portfolio_snapshots (already has user_id)
        print("  Migrating portfolio_snapshots...")
        try:
            old_cur.execute("SELECT * FROM portfolio_snapshots")
            snapshots = old_cur.fetchall()
            for snapshot in snapshots:
                new_cur.execute("""
                    INSERT INTO portfolio_snapshots (
                        user_id, snapshot_date, snapshot_time, total_value_usd,
                        ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price,
                        sol_amount, sol_price, staking_value_usd, defi_value_usd,
                        exchange_value_usd, nft_value_usd, tracked_tokens_value_usd, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    snapshot['user_id'],
                    snapshot['snapshot_date'],
                    snapshot['snapshot_time'],
                    snapshot['total_value_usd'],
                    snapshot['ada_amount'] if 'ada_amount' in snapshot.keys() else 0,
                    snapshot['ada_price'] if 'ada_price' in snapshot.keys() else 0,
                    snapshot['btc_amount'] if 'btc_amount' in snapshot.keys() else 0,
                    snapshot['btc_price'] if 'btc_price' in snapshot.keys() else 0,
                    snapshot['eth_amount'] if 'eth_amount' in snapshot.keys() else 0,
                    snapshot['eth_price'] if 'eth_price' in snapshot.keys() else 0,
                    snapshot['sol_amount'] if 'sol_amount' in snapshot.keys() else 0,
                    snapshot['sol_price'] if 'sol_price' in snapshot.keys() else 0,
                    snapshot['staking_value_usd'] if 'staking_value_usd' in snapshot.keys() else 0,
                    snapshot['defi_value_usd'] if 'defi_value_usd' in snapshot.keys() else 0,
                    snapshot['exchange_value_usd'] if 'exchange_value_usd' in snapshot.keys() else 0,
                    snapshot['nft_value_usd'] if 'nft_value_usd' in snapshot.keys() else 0,
                    snapshot['tracked_tokens_value_usd'] if 'tracked_tokens_value_usd' in snapshot.keys() else 0,
                    snapshot['created_at'] if 'created_at' in snapshot.keys() else datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(snapshots)} portfolio snapshots")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No portfolio_snapshots table found, skipping")

        # 9. Migrate sessions (already has user_id)
        print("  Migrating sessions...")
        try:
            old_cur.execute("SELECT * FROM sessions")
            sessions = old_cur.fetchall()
            for session in sessions:
                new_cur.execute("""
                    INSERT INTO sessions (token, user_id, username, is_demo, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session['token'],
                    session['user_id'],
                    session['username'],
                    session['is_demo'] if 'is_demo' in session.keys() else 0,
                    session['expires_at'],
                    session['created_at'] if 'created_at' in session.keys() else datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(sessions)} sessions")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No sessions table found, skipping")

        # 10. Migrate system-wide tables (no user_id)
        print("  Migrating system tables...")

        # api_settings (REMOVE user_id)
        try:
            old_cur.execute("SELECT api_name, api_key, enabled FROM api_settings")
            api_settings = old_cur.fetchall()
            for setting in api_settings:
                new_cur.execute("""
                    INSERT INTO api_settings (api_name, api_key, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    setting['api_name'],
                    setting['api_key'] if 'api_key' in setting.keys() else None,
                    setting['enabled'] if 'enabled' in setting.keys() else 0,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(api_settings)} API settings")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No api_settings table found, skipping")

        # security_settings (REMOVE user_id)
        try:
            old_cur.execute("SELECT * FROM security_settings WHERE id = 1")
            security_setting = old_cur.fetchone()
            if security_setting:
                new_cur.execute("""
                    INSERT INTO security_settings (
                        id, ssl_mode, cert_path, key_path, cert_type, cert_expires_at,
                        pending_mode, restart_required, created_at, updated_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    security_setting['ssl_mode'] if 'ssl_mode' in security_setting.keys() else 'http',
                    security_setting['cert_path'] if 'cert_path' in security_setting.keys() else None,
                    security_setting['key_path'] if 'key_path' in security_setting.keys() else None,
                    security_setting['cert_type'] if 'cert_type' in security_setting.keys() else None,
                    security_setting['cert_expires_at'] if 'cert_expires_at' in security_setting.keys() else None,
                    security_setting['pending_mode'] if 'pending_mode' in security_setting.keys() else None,
                    security_setting['restart_required'] if 'restart_required' in security_setting.keys() else 0,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                print(f"    ✅ Migrated security settings")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No security_settings table found, skipping")

        # nft_floor_prices
        try:
            old_cur.execute("SELECT * FROM nft_floor_prices")
            floor_prices = old_cur.fetchall()
            for price in floor_prices:
                new_cur.execute("""
                    INSERT INTO nft_floor_prices (
                        policy_id, collection_name, floor_price_ada, listings, supply,
                        verified, source, fetched_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    price['policy_id'],
                    price['collection_name'] if 'collection_name' in price.keys() else None,
                    price['floor_price_ada'] if 'floor_price_ada' in price.keys() else None,
                    price['listings'] if 'listings' in price.keys() else 0,
                    price['supply'] if 'supply' in price.keys() else None,
                    price['verified'] if 'verified' in price.keys() else 0,
                    price['source'] if 'source' in price.keys() else None,
                    price['fetched_at'],
                    price['created_at'] if 'created_at' in price.keys() else datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(floor_prices)} NFT floor prices")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No nft_floor_prices table found, skipping")

        # token_metadata
        try:
            old_cur.execute("SELECT * FROM token_metadata")
            tokens = old_cur.fetchall()
            for token in tokens:
                new_cur.execute("""
                    INSERT INTO token_metadata (
                        asset_id, policy_id, asset_name, ticker, name, decimals,
                        logo_url, track_for_pricing, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    token['asset_id'],
                    token['policy_id'] if 'policy_id' in token.keys() else None,
                    token['asset_name'] if 'asset_name' in token.keys() else None,
                    token['ticker'] if 'ticker' in token.keys() else None,
                    token['name'] if 'name' in token.keys() else None,
                    token['decimals'] if 'decimals' in token.keys() else 0,
                    token['logo_url'] if 'logo_url' in token.keys() else None,
                    token['track_for_pricing'] if 'track_for_pricing' in token.keys() else 0,
                    token['updated_at'] if 'updated_at' in token.keys() else datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(tokens)} token metadata")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No token_metadata table found, skipping")

        # NFT scheduler tables
        try:
            old_cur.execute("SELECT * FROM nft_scheduler_state WHERE id = 1")
            scheduler_state = old_cur.fetchone()
            if scheduler_state:
                new_cur.execute("""
                    INSERT INTO nft_scheduler_state (
                        id, enabled, started_at, last_update, total_updates,
                        successful_updates, failed_updates, last_error, rate_limited_until, updated_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    scheduler_state['enabled'] if 'enabled' in scheduler_state.keys() else 0,
                    scheduler_state['started_at'] if 'started_at' in scheduler_state.keys() else None,
                    scheduler_state['last_update'] if 'last_update' in scheduler_state.keys() else None,
                    scheduler_state['total_updates'] if 'total_updates' in scheduler_state.keys() else 0,
                    scheduler_state['successful_updates'] if 'successful_updates' in scheduler_state.keys() else 0,
                    scheduler_state['failed_updates'] if 'failed_updates' in scheduler_state.keys() else 0,
                    scheduler_state['last_error'] if 'last_error' in scheduler_state.keys() else None,
                    scheduler_state['rate_limited_until'] if 'rate_limited_until' in scheduler_state.keys() else None,
                    scheduler_state['updated_at'] if 'updated_at' in scheduler_state.keys() else datetime.now().isoformat()
                ))
                print(f"    ✅ Migrated NFT scheduler state")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No nft_scheduler_state table found, skipping")

        try:
            old_cur.execute("SELECT * FROM nft_scheduler_collections")
            collections = old_cur.fetchall()
            for collection in collections:
                new_cur.execute("""
                    INSERT INTO nft_scheduler_collections (
                        policy_id, collection_name, priority, last_updated, update_count,
                        last_floor_price, supply, holders, listings, volume_24h, volume_7d, volume_30d, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    collection['policy_id'],
                    collection['collection_name'] if 'collection_name' in collection.keys() else None,
                    collection['priority'] if 'priority' in collection.keys() else 0,
                    collection['last_updated'] if 'last_updated' in collection.keys() else None,
                    collection['update_count'] if 'update_count' in collection.keys() else 0,
                    collection['last_floor_price'] if 'last_floor_price' in collection.keys() else None,
                    collection['supply'] if 'supply' in collection.keys() else None,
                    collection['holders'] if 'holders' in collection.keys() else None,
                    collection['listings'] if 'listings' in collection.keys() else None,
                    collection['volume_24h'] if 'volume_24h' in collection.keys() else None,
                    collection['volume_7d'] if 'volume_7d' in collection.keys() else None,
                    collection['volume_30d'] if 'volume_30d' in collection.keys() else None,
                    collection['created_at'] if 'created_at' in collection.keys() else datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(collections)} NFT scheduler collections")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No nft_scheduler_collections table found, skipping")

        # API usage and rate limits
        try:
            old_cur.execute("SELECT * FROM api_usage")
            api_usage = old_cur.fetchall()
            for usage in api_usage:
                new_cur.execute("""
                    INSERT INTO api_usage (api_name, period_start, period_end, call_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    usage['api_name'],
                    usage['period_start'],
                    usage['period_end'],
                    usage['call_count'] if 'call_count' in usage.keys() else 0,
                    usage['created_at'] if 'created_at' in usage.keys() else datetime.now().isoformat(),
                    usage['updated_at'] if 'updated_at' in usage.keys() else datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(api_usage)} API usage records")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No api_usage table found, skipping")

        try:
            old_cur.execute("SELECT * FROM api_rate_limits")
            rate_limits = old_cur.fetchall()
            for limit in rate_limits:
                new_cur.execute("""
                    INSERT INTO api_rate_limits (api_name, requests_limit, period_seconds, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    limit['api_name'],
                    limit['requests_limit'],
                    limit['period_seconds'] if 'period_seconds' in limit.keys() else 86400,
                    limit['updated_at'] if 'updated_at' in limit.keys() else datetime.now().isoformat()
                ))
            print(f"    ✅ Migrated {len(rate_limits)} API rate limits")
        except sqlite3.OperationalError:
            print(f"    ⏭️  No api_rate_limits table found, skipping")

        self.new_conn.commit()
        print("\n✅ Data migration complete!")

    def verify_migration(self):
        """Verify migration was successful"""
        print("\n🔍 Verifying migration...")

        cursor = self.new_conn.cursor()

        # Check row counts
        tables = [
            'users', 'wallets', 'balances', 'native_assets', 'nft_images',
            'custom_tokens', 'portfolio_snapshots', 'sessions',
            'api_settings', 'nft_floor_prices', 'token_metadata'
        ]

        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  ✅ {table}: {count} rows")
            except sqlite3.OperationalError:
                print(f"  ⚠️  {table}: table not found")

        # Verify user_id constraints
        cursor.execute("SELECT COUNT(*) FROM wallets WHERE user_id IS NULL")
        if cursor.fetchone()[0] == 0:
            print("  ✅ All wallets have user_id")
        else:
            print("  ❌ Some wallets missing user_id")

        cursor.execute("SELECT COUNT(*) FROM balances WHERE user_id IS NULL")
        if cursor.fetchone()[0] == 0:
            print("  ✅ All balances have user_id")
        else:
            print("  ❌ Some balances missing user_id")

        cursor.execute("SELECT COUNT(*) FROM native_assets WHERE user_id IS NULL")
        if cursor.fetchone()[0] == 0:
            print("  ✅ All native_assets have user_id")
        else:
            print("  ❌ Some native_assets missing user_id")

        cursor.execute("SELECT COUNT(*) FROM nft_images WHERE user_id IS NULL")
        if cursor.fetchone()[0] == 0:
            print("  ✅ All nft_images have user_id")
        else:
            print("  ❌ Some nft_images missing user_id")

        print("\n✅ Verification complete!")

    def cleanup(self):
        """Close connections"""
        if self.old_portfolio_conn:
            self.old_portfolio_conn.close()
        if self.old_nft_conn:
            self.old_nft_conn.close()
        if self.new_conn:
            self.new_conn.close()
        print("\n✅ Database connections closed")

    def run(self):
        """Run the complete migration"""
        print("=" * 60)
        print("ABCT Database Migration")
        print("=" * 60)

        try:
            self.backup_databases()
            self.connect_databases()
            self.create_new_schema()
            self.migrate_data()
            self.verify_migration()
            self.cleanup()

            print("\n" + "=" * 60)
            print("✅ MIGRATION SUCCESSFUL!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Stop the backend server")
            print("2. Rename databases:")
            print("   mv data/portfolio.db data/portfolio.db.old")
            print("   mv data/nft_images.db data/nft_images.db.old")
            print("   mv data/abct.db data/portfolio.db")
            print("3. Update backend services (see DATABASE_MIGRATION_PLAN.md)")
            print("4. Restart backend server")
            print("5. Test all functionality")
            print("6. Delete old databases after 7-day verification")

        except Exception as e:
            print(f"\n❌ MIGRATION FAILED: {e}")
            import traceback
            traceback.print_exc()
            self.cleanup()
            return False

        return True

if __name__ == "__main__":
    migration = DatabaseMigration()
    success = migration.run()
    exit(0 if success else 1)
