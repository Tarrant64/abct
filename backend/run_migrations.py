#!/usr/bin/env python3
"""
Database Migration Runner

Runs SQL migration files in order and tracks which migrations have been applied.
Prevents running the same migration twice and ensures migrations run in sequence.

Usage:
    python run_migrations.py              # Run all pending migrations
    python run_migrations.py --check      # Check migration status
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "portfolio.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def init_migration_tracking(conn):
    """Create migration tracking table if it doesn't exist."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checksum TEXT,
            execution_time_ms INTEGER
        )
    """)

    conn.commit()
    logger.info("Migration tracking table initialized")


def get_applied_migrations(conn):
    """Get list of migrations that have already been applied."""
    cursor = conn.cursor()
    cursor.execute("SELECT version, filename FROM schema_migrations ORDER BY version")
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_pending_migrations(conn):
    """Get list of migrations that need to be applied."""
    applied = get_applied_migrations(conn)

    # Find all .sql files in migrations directory
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    pending = []
    for filepath in migration_files:
        # Extract version number from filename (e.g., "004_add_hidden_tokens.sql" -> 4)
        filename = filepath.name
        try:
            version = int(filename.split('_')[0])
        except (ValueError, IndexError):
            logger.warning(f"Skipping file with invalid format: {filename}")
            continue

        if version not in applied:
            pending.append((version, filepath))

    return sorted(pending, key=lambda x: x[0])


def calculate_checksum(filepath):
    """Calculate simple checksum of migration file."""
    import hashlib
    return hashlib.md5(filepath.read_bytes()).hexdigest()


def extract_description(filepath):
    """Extract description from migration filename."""
    # "004_add_hidden_tokens.sql" -> "add hidden tokens"
    name = filepath.stem  # Remove .sql
    parts = name.split('_', 1)
    if len(parts) == 2:
        return parts[1].replace('_', ' ')
    return name


def run_migration(conn, version, filepath):
    """Run a single migration file."""
    logger.info(f"Running migration {version}: {filepath.name}")

    start_time = datetime.now()

    try:
        # Read migration SQL
        sql = filepath.read_text()

        # Execute migration
        cursor = conn.cursor()
        cursor.executescript(sql)

        # Record migration
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

        cursor.execute("""
            INSERT INTO schema_migrations
            (version, filename, description, checksum, execution_time_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (
            version,
            filepath.name,
            extract_description(filepath),
            calculate_checksum(filepath),
            execution_time
        ))

        conn.commit()

        logger.info(f"✓ Migration {version} completed in {execution_time}ms")
        return True

    except Exception as e:
        logger.error(f"✗ Migration {version} failed: {e}")
        conn.rollback()
        return False


def run_all_migrations():
    """Run all pending migrations."""
    logger.info("=" * 80)
    logger.info("Starting Database Migration")
    logger.info("=" * 80)

    # Ensure migrations directory exists
    if not MIGRATIONS_DIR.exists():
        logger.error(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return False

    # Ensure database directory exists
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(DATABASE_PATH)

    try:
        # Initialize migration tracking
        init_migration_tracking(conn)

        # Get pending migrations
        pending = get_pending_migrations(conn)

        if not pending:
            logger.info("No pending migrations. Database is up to date.")
            logger.info("=" * 80)
            return True

        logger.info(f"Found {len(pending)} pending migration(s)")

        # Run each migration
        success_count = 0
        for version, filepath in pending:
            if run_migration(conn, version, filepath):
                success_count += 1
            else:
                logger.error("Migration failed. Stopping migration process.")
                break

        logger.info("=" * 80)
        logger.info(f"Migration complete: {success_count}/{len(pending)} migrations applied")
        logger.info("=" * 80)

        return success_count == len(pending)

    except Exception as e:
        logger.error(f"Migration process failed: {e}")
        return False

    finally:
        conn.close()


def check_migration_status():
    """Check current migration status."""
    logger.info("Checking migration status...")

    conn = sqlite3.connect(DATABASE_PATH)

    try:
        init_migration_tracking(conn)

        applied = get_applied_migrations(conn)
        pending = get_pending_migrations(conn)

        print("\n" + "=" * 80)
        print("DATABASE MIGRATION STATUS")
        print("=" * 80)

        if applied:
            print(f"\n✓ Applied Migrations ({len(applied)}):")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT version, filename, description, applied_at, execution_time_ms
                FROM schema_migrations
                ORDER BY version
            """)
            for row in cursor.fetchall():
                version, filename, desc, applied_at, exec_time = row
                print(f"  [{version:03d}] {filename}")
                print(f"        {desc}")
                print(f"        Applied: {applied_at} ({exec_time}ms)")
        else:
            print("\n✓ No migrations applied yet")

        if pending:
            print(f"\n⚠ Pending Migrations ({len(pending)}):")
            for version, filepath in pending:
                print(f"  [{version:03d}] {filepath.name}")
                print(f"        {extract_description(filepath)}")
        else:
            print("\n✓ No pending migrations. Database is up to date.")

        print("\n" + "=" * 80)

    finally:
        conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Database Migration Runner')
    parser.add_argument('--check', action='store_true', help='Check migration status')

    args = parser.parse_args()

    if args.check:
        check_migration_status()
    else:
        # Run migrations
        success = run_all_migrations()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
