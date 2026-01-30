#!/usr/bin/env python3
"""
Database Migration Script: Single-User to Multi-User Schema
============================================================

This script migrates an existing ABCT database from single-user to multi-user schema.

Usage:
    python migrate_to_multiuser.py [--db-path /path/to/portfolio.db]

What it does:
1. Creates users table if it doesn't exist
2. Creates sessions table if it doesn't exist
3. Creates password_reset table if it doesn't exist
4. Adds user_id column to existing tables that need it
5. Creates a default admin user
6. Assigns all existing data to the default user

IMPORTANT: This script will backup your database before making changes.
"""

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime
import shutil
import bcrypt

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "portfolio.db"


def backup_database(db_path: Path) -> Path:
    """Create a backup of the database before migration."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"portfolio_backup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"✓ Database backed up to: {backup_path}")
    return backup_path


def check_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def check_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def migrate_database(db_path: Path):
    """Perform the database migration."""

    if not db_path.exists():
        print(f"✗ Database not found at: {db_path}")
        print("  If this is a new installation, the database will be created automatically.")
        return

    print(f"\n{'='*60}")
    print("ABCT Database Migration: Single-User → Multi-User")
    print(f"{'='*60}\n")
    print(f"Database: {db_path}")

    # Create backup
    backup_path = backup_database(db_path)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        print("\n📋 Checking database schema...\n")

        # Step 1: Create users table
        if not check_table_exists(conn, 'users'):
            print("Creating users table...")
            cursor.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_demo INTEGER DEFAULT 0,
                    password_changed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✓ Users table created")
        else:
            print("✓ Users table already exists")

        # Step 2: Create sessions table
        if not check_table_exists(conn, 'sessions'):
            print("Creating sessions table...")
            cursor.execute("""
                CREATE TABLE sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    is_demo INTEGER DEFAULT 0,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX idx_sessions_user_id ON sessions(user_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_sessions_expires_at ON sessions(expires_at)
            """)
            print("✓ Sessions table created")
        else:
            print("✓ Sessions table already exists")

        # Step 3: Create password_reset table
        if not check_table_exists(conn, 'password_reset'):
            print("Creating password_reset table...")
            cursor.execute("""
                CREATE TABLE password_reset (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reset_code TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            print("✓ Password reset table created")
        else:
            print("✓ Password reset table already exists")

        # Step 4: Create default admin user if no users exist
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]

        if user_count == 0:
            print("\nCreating default admin user...")
            username = "admin"
            password = "admin"
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            cursor.execute(
                """INSERT INTO users (username, password_hash, is_demo, password_changed)
                   VALUES (?, ?, 0, 0)""",
                (username, password_hash)
            )
            admin_user_id = cursor.lastrowid
            print(f"✓ Default admin user created (username: {username}, password: {password})")
            print(f"  ⚠️  IMPORTANT: Change the password after first login!")
        else:
            print(f"\n✓ Found {user_count} existing user(s)")
            # Get first user as default
            cursor.execute("SELECT id, username FROM users LIMIT 1")
            row = cursor.fetchone()
            admin_user_id = row[0]
            print(f"  Using user '{row[1]}' (ID: {admin_user_id}) for existing data")

        # Step 5: Add user_id to tables that need it
        tables_to_migrate = [
            'wallets',
            'balances',
            'native_assets',
            'portfolio_snapshots',
            'custom_tokens',
            'api_settings',
            'security_settings'
        ]

        print("\n📊 Migrating tables to add user_id column...\n")

        for table in tables_to_migrate:
            if not check_table_exists(conn, table):
                print(f"  ⊙ {table}: Table doesn't exist yet (will be created on startup)")
                continue

            if check_column_exists(conn, table, 'user_id'):
                print(f"  ✓ {table}: Already has user_id column")
                continue

            print(f"  → {table}: Adding user_id column...")

            # Add user_id column
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")

            # Update all rows to use the default user
            cursor.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))

            row_count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"    ✓ Added user_id to {row_count} row(s)")

        # Commit all changes
        conn.commit()

        print(f"\n{'='*60}")
        print("✅ Migration completed successfully!")
        print(f"{'='*60}\n")
        print(f"Backup saved at: {backup_path}")
        print("\nLogin credentials:")
        print(f"  Username: admin (or your existing username)")
        print(f"  Password: admin (or your existing password)")
        print("\n⚠️  If using Docker, restart your container now.\n")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print(f"\nRestoring from backup...")
        conn.close()
        shutil.copy2(backup_path, db_path)
        print(f"✓ Database restored from backup")
        sys.exit(1)
    finally:
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate ABCT database from single-user to multi-user schema"
    )
    parser.add_argument(
        '--db-path',
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to database file (default: {DEFAULT_DB_PATH})"
    )

    args = parser.parse_args()

    migrate_database(args.db_path)


if __name__ == "__main__":
    main()
