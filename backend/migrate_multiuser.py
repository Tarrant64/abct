"""
Multi-User Database Migration Script

This script migrates the ABCT database from single-user to multi-user architecture by:
1. Creating the users table if it doesn't exist
2. Ensuring admin user exists
3. Adding user_id columns to all data tables
4. Setting existing records to admin user
5. Creating foreign key constraints and indexes

Usage:
    python migrate_multiuser.py
"""

import asyncio
import aiosqlite
import bcrypt
import os
from datetime import datetime
from pathlib import Path
from config import DATABASE_PATH

# Tables that need user_id column
USER_DATA_TABLES = [
    'wallets',
    'portfolio_snapshots',
    'custom_tokens',
    'api_settings',
    'security_settings',
]


async def create_users_table(db):
    """Create users table if it doesn't exist."""
    print("Creating users table...")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_changed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()
    print("✓ Users table created")


async def ensure_admin_user(db):
    """Ensure admin user exists and return admin user ID."""
    print("\nChecking for admin user...")

    # Check if admin exists
    cursor = await db.execute("SELECT id, username FROM users WHERE username = 'admin'")
    admin = await cursor.fetchone()

    if admin:
        admin_id = admin[0]
        print(f"✓ Admin user found (ID: {admin_id})")
        return admin_id

    # Create admin user
    print("Creating admin user...")
    default_password = os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")
    password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

    cursor = await db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        ("admin", password_hash.decode('utf-8'))
    )
    await db.commit()
    admin_id = cursor.lastrowid

    print(f"✓ Admin user created (ID: {admin_id})")
    print(f"  Username: admin")
    print(f"  Password: {default_password}")
    return admin_id


async def check_column_exists(db, table_name, column_name):
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    columns = await cursor.fetchall()
    return any(col[1] == column_name for col in columns)


async def add_user_id_column(db, table_name, admin_id):
    """Add user_id column to a table if it doesn't exist."""
    print(f"\nProcessing table: {table_name}")

    # Check if table exists
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    if not await cursor.fetchone():
        print(f"  ⊗ Table '{table_name}' does not exist - skipping")
        return False

    # Check if user_id column already exists
    if await check_column_exists(db, table_name, 'user_id'):
        print(f"  ℹ Column 'user_id' already exists in {table_name}")
        return True

    # Add user_id column
    print(f"  + Adding user_id column to {table_name}...")
    await db.execute(f"""
        ALTER TABLE {table_name}
        ADD COLUMN user_id INTEGER REFERENCES users(id)
    """)
    await db.commit()

    # Update existing records to point to admin user
    cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = (await cursor.fetchone())[0]

    if count > 0:
        print(f"  ↻ Updating {count} existing records to admin user...")
        await db.execute(f"""
            UPDATE {table_name}
            SET user_id = ?
            WHERE user_id IS NULL
        """, (admin_id,))
        await db.commit()
        print(f"  ✓ Updated {count} records")
    else:
        print(f"  ℹ No existing records to update")

    # Create index on user_id
    index_name = f"idx_{table_name}_user_id"
    print(f"  + Creating index: {index_name}...")
    try:
        await db.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name}(user_id)
        """)
        await db.commit()
        print(f"  ✓ Index created")
    except Exception as e:
        print(f"  ⚠ Index creation warning: {e}")

    return True


async def verify_migration(db, admin_id):
    """Verify the migration was successful."""
    print("\n" + "="*60)
    print("MIGRATION VERIFICATION")
    print("="*60)

    all_ok = True

    for table_name in USER_DATA_TABLES:
        # Check if table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        if not await cursor.fetchone():
            print(f"✗ Table '{table_name}' does not exist")
            continue

        # Check if user_id column exists
        if not await check_column_exists(db, table_name, 'user_id'):
            print(f"✗ {table_name}: user_id column missing")
            all_ok = False
            continue

        # Check record counts
        cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_count = (await cursor.fetchone())[0]

        cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name} WHERE user_id = ?", (admin_id,))
        admin_count = (await cursor.fetchone())[0]

        cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name} WHERE user_id IS NULL")
        null_count = (await cursor.fetchone())[0]

        if null_count > 0:
            print(f"⚠ {table_name}: {null_count}/{total_count} records have NULL user_id")
            all_ok = False
        else:
            print(f"✓ {table_name}: {admin_count}/{total_count} records assigned to admin")

    return all_ok


async def main():
    """Main migration function."""
    print("="*60)
    print("ABCT MULTI-USER DATABASE MIGRATION")
    print("="*60)
    print(f"Database: {DATABASE_PATH}")
    print()

    # Ensure database directory exists
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Step 1: Create users table
        await create_users_table(db)

        # Step 2: Ensure admin user exists
        admin_id = await ensure_admin_user(db)

        # Step 3: Add user_id columns to all tables
        print("\n" + "="*60)
        print("ADDING USER_ID COLUMNS")
        print("="*60)

        success_count = 0
        for table_name in USER_DATA_TABLES:
            if await add_user_id_column(db, table_name, admin_id):
                success_count += 1

        print(f"\n✓ Processed {success_count}/{len(USER_DATA_TABLES)} tables")

        # Step 4: Verify migration
        if await verify_migration(db, admin_id):
            print("\n" + "="*60)
            print("✓ MIGRATION COMPLETED SUCCESSFULLY")
            print("="*60)
            print(f"\nAdmin user ID: {admin_id}")
            print(f"Tables migrated: {success_count}")
            print("\nNext steps:")
            print("1. Database schema is now multi-user ready")
            print("2. All existing data is assigned to admin user")
            print("3. New records will require user_id to be set")
        else:
            print("\n" + "="*60)
            print("⚠ MIGRATION COMPLETED WITH WARNINGS")
            print("="*60)
            print("\nSome tables may need manual review.")


if __name__ == "__main__":
    asyncio.run(main())
