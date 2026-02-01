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
    print("Fixing api_settings table schema...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
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

        # Step 2: Copy data from old table
        print("Copying data from old table...")
        cursor.execute("""
            INSERT INTO api_settings_new (user_id, api_name, api_key, enabled, created_at, updated_at)
            SELECT
                COALESCE(user_id, 1) as user_id,
                api_name,
                api_key,
                enabled,
                created_at,
                updated_at
            FROM api_settings
        """)

        # Step 3: Drop old table
        print("Dropping old table...")
        cursor.execute("DROP TABLE api_settings")

        # Step 4: Rename new table
        print("Renaming new table...")
        cursor.execute("ALTER TABLE api_settings_new RENAME TO api_settings")

        # Step 5: Recreate index
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
