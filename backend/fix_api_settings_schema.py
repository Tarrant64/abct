#!/usr/bin/env python3
"""
Fix api_settings table schema to support multi-user properly.
Changes PRIMARY KEY from api_name to composite (user_id, api_name).
"""

import sqlite3
import sys
import os

# Get database path
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'data/portfolio.db')

def fix_api_settings_schema():
    """Fix api_settings table to have composite primary key."""
    print("Checking api_settings table schema...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Check if api_settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_settings'")
        if not cursor.fetchone():
            print("  api_settings table doesn't exist yet - will be created on first run")
            return True

        # Check current schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='api_settings'")
        current_schema = cursor.fetchone()[0]

        # Check if already has composite primary key
        if 'PRIMARY KEY (user_id, api_name)' in current_schema or 'PRIMARY KEY(user_id, api_name)' in current_schema:
            print("  ✓ Schema already correct - no migration needed")
            return True

        print("  Schema needs migration - updating...")

        # Step 1: Create new table with correct schema
        print("Creating new api_settings table...")
        cursor.execute("""
            CREATE TABLE api_settings_new (
                user_id INTEGER NOT NULL,
                api_name TEXT NOT NULL,
                api_key TEXT,
                enabled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                PRIMARY KEY (user_id, api_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Step 2: Check which columns exist in old table
        print("Checking old table schema...")
        cursor.execute("PRAGMA table_info(api_settings)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"  Found columns: {', '.join(columns)}")

        has_created_at = 'created_at' in columns
        has_updated_at = 'updated_at' in columns
        has_user_id = 'user_id' in columns

        # Step 3: Copy data from old table with appropriate defaults
        print("Copying data from old table...")

        created_clause = "created_at" if has_created_at else "CURRENT_TIMESTAMP"
        updated_clause = "updated_at" if has_updated_at else "CURRENT_TIMESTAMP"
        user_id_clause = "COALESCE(user_id, 1)" if has_user_id else "1"

        cursor.execute(f"""
            INSERT INTO api_settings_new (user_id, api_name, api_key, enabled, created_at, updated_at)
            SELECT
                {user_id_clause} as user_id,
                api_name,
                api_key,
                enabled,
                {created_clause} as created_at,
                {updated_clause} as updated_at
            FROM api_settings
        """)

        # Step 4: Drop old table
        print("Dropping old table...")
        cursor.execute("DROP TABLE api_settings")

        # Step 5: Rename new table
        print("Renaming new table...")
        cursor.execute("ALTER TABLE api_settings_new RENAME TO api_settings")

        # Step 6: Recreate index
        print("Creating index...")
        cursor.execute("""
            CREATE INDEX idx_api_settings_user_id ON api_settings(user_id)
        """)

        conn.commit()
        print("✅ api_settings table schema fixed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error fixing schema: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    success = fix_api_settings_schema()
    sys.exit(0 if success else 1)
