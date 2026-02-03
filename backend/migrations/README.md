# Database Migrations

## Overview

This directory contains SQL migration files that update the database schema over time. Migrations are run automatically on application startup.

## Migration Naming Convention

```
XXX_description.sql
```

- `XXX` = 3-digit version number (e.g., `004`, `005`, `006`)
- `description` = Snake_case description (e.g., `add_hidden_tokens`)

**Examples:**
- `004_add_hidden_tokens.sql`
- `005_hourly_portfolio_snapshots.sql`
- `007_transaction_history.sql`

## Migration Tracking

The `schema_migrations` table tracks which migrations have been applied:

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT,
    execution_time_ms INTEGER
);
```

## Running Migrations

### Automatic (Production)
Migrations run automatically when the Docker container starts:

```bash
docker-compose up -d
# Migrations run via docker-entrypoint.sh before app starts
```

### Manual (Development)

**Run pending migrations:**
```bash
cd backend
python3 run_migrations.py
```

**Check migration status:**
```bash
python3 run_migrations.py --check
```

**Output example:**
```
================================================================================
DATABASE MIGRATION STATUS
================================================================================

✓ Applied Migrations (5):
  [004] 004_add_hidden_tokens.sql
        add hidden tokens
        Applied: 2026-01-15 10:30:45 (125ms)
  [005] 005_hourly_portfolio_snapshots.sql
        hourly portfolio snapshots
        Applied: 2026-01-20 14:22:10 (340ms)
  ...

⚠ Pending Migrations (1):
  [008] 008_consolidate_inline_migrations.sql
        consolidate inline migrations
```

## Creating New Migrations

### Step 1: Create Migration File

```bash
cd backend/migrations
touch 009_my_new_feature.sql
```

### Step 2: Write SQL

```sql
-- Migration 009: My New Feature
-- Description: Add new column to track something

-- Add new column
ALTER TABLE wallets ADD COLUMN my_column TEXT DEFAULT '';

-- Create index if needed
CREATE INDEX IF NOT EXISTS idx_wallets_my_column ON wallets(my_column);
```

### Step 3: Test Migration

```bash
# Check what would run
python3 run_migrations.py --check

# Run migration
python3 run_migrations.py
```

### Step 4: Verify

```bash
# Check migration was applied
python3 run_migrations.py --check

# Or check database directly
sqlite3 data/portfolio.db "SELECT * FROM schema_migrations ORDER BY version"
```

## Best Practices

### ✅ DO:
- **Number sequentially** - Use next available number
- **Be descriptive** - Filename should explain what it does
- **Test first** - Test on development database before production
- **Use IF NOT EXISTS** - Make migrations idempotent when possible
- **One logical change per migration** - Easier to debug
- **Add comments** - Explain why, not just what

**Example:**
```sql
-- Migration 010: Add Exchange Integration
-- Allows tracking exchange balances alongside wallet balances

CREATE TABLE IF NOT EXISTS exchange_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    exchange_name TEXT NOT NULL,
    api_key TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### ❌ DON'T:
- **Skip numbers** - Always use sequential numbers
- **Modify existing migrations** - Create new migration instead
- **Use transactions** - Each migration file is atomic
- **Drop columns in SQLite** - Use migration to create new table instead
- **Hardcode data** - Use parameters or separate data scripts

## Rolling Back Migrations

**SQLite limitations:** No native rollback support.

**Options:**

1. **Backup and Restore** (Recommended):
```bash
# Before migration
cp data/portfolio.db data/portfolio.db.backup

# If migration fails, restore
cp data/portfolio.db.backup data/portfolio.db
```

2. **Create Reverse Migration**:
```sql
-- If you added a column:
-- 011_revert_my_feature.sql
ALTER TABLE wallets DROP COLUMN my_column;  -- SQLite 3.35.0+
```

## Testing Migrations

Run migration tests:

```bash
cd ABCT
pytest tests/test_migrations.py -v
```

Tests verify:
- Migration tracking table creation
- Pending migration detection
- Duplicate prevention
- Data preservation
- Checksum calculation

## Troubleshooting

### Migration Failed
```bash
# Check error in logs
docker-compose logs backend

# Check migration status
python3 run_migrations.py --check

# Restore from backup
cp data/portfolio.db.backup data/portfolio.db
```

### Migration Stuck
```bash
# Check if migration is locked
sqlite3 data/portfolio.db "PRAGMA busy_timeout"

# Force unlock (careful!)
rm data/portfolio.db-journal
```

### Duplicate Migration Error
```bash
# Check what's applied
python3 run_migrations.py --check

# If incorrectly marked as applied, remove from tracking:
sqlite3 data/portfolio.db "DELETE FROM schema_migrations WHERE version = XXX"
```

## Migration History

| Version | Description | Date | Notes |
|---------|-------------|------|-------|
| 004 | Add hidden tokens | 2026-01-15 | Token hiding feature |
| 005 | Hourly snapshots | 2026-01-20 | Changed from daily |
| 006 | Startup throttling | 2026-02-02 | Cooldown tracking |
| 007 | Transaction history | 2026-02-02 | Transaction table |
| 008 | Consolidate inline | 2026-02-02 | Clean up inline migrations |

## Docker Integration

The `docker-entrypoint.sh` script runs migrations on container startup:

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
python3 run_migrations.py

if [ $? -ne 0 ]; then
    echo "ERROR: Database migration failed!"
    exit 1
fi

echo "Starting application..."
exec "$@"
```

This ensures:
- ✅ Database is always up-to-date
- ✅ Migrations run before app starts
- ✅ Failed migrations prevent app startup (safety)
- ✅ Works with Docker Compose and Kubernetes

## Future Enhancements

Potential improvements:
- [ ] Migration rollback support
- [ ] Dry-run mode (show SQL without executing)
- [ ] Migration dependencies
- [ ] Data migrations (separate from schema)
- [ ] Migration templates
- [ ] Integration with CI/CD
