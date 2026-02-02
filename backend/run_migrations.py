#!/usr/bin/env python3
"""
Run all pending database migrations.
Applies SQL migrations from backend/migrations/ directory in order.
"""

import sqlite3
import sys
import os
from pathlib import Path

# Get database path
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'data/portfolio.db')
MIGRATIONS_DIR = Path(__file__).parent / 'migrations'

def get_applied_migrations(cursor):
    """Get list of applied migrations from database."""
    # Create migrations tracking table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_name TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("SELECT migration_name FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}

def apply_migration(cursor, migration_file):
    """Apply a single SQL migration file."""
    print(f"  Applying: {migration_file.name}")

    with open(migration_file, 'r') as f:
        sql = f.read()

    # Execute all statements in the migration
    cursor.executescript(sql)

    # Record migration as applied
    cursor.execute(
        "INSERT INTO schema_migrations (migration_name) VALUES (?)",
        (migration_file.name,)
    )

def run_migrations():
    """Run all pending migrations."""
    print("🔄 Running database migrations...")
    print(f"Database: {DATABASE_PATH}")
    print(f"Migrations: {MIGRATIONS_DIR}")

    if not MIGRATIONS_DIR.exists():
        print("  ⚠️  No migrations directory found")
        return True

    # Get all SQL migration files
    migration_files = sorted(MIGRATIONS_DIR.glob('*.sql'))

    if not migration_files:
        print("  ℹ️  No SQL migrations found")
        return True

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Get already applied migrations
        applied = get_applied_migrations(cursor)

        # Apply pending migrations
        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            print("  ✅ All migrations already applied")
            return True

        print(f"  Found {len(pending)} pending migration(s)")

        for migration_file in pending:
            apply_migration(cursor, migration_file)

        conn.commit()
        print(f"✅ Successfully applied {len(pending)} migration(s)")
        return True

    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
