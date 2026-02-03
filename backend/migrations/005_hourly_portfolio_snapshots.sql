-- Migration: Allow hourly portfolio snapshots
-- Changes UNIQUE constraint from (user_id, snapshot_date) to (user_id, snapshot_time)
-- This allows multiple snapshots per day for hourly tracking

-- Check if migration is needed by seeing if we can query the table
-- If this migration has already run, skip it
SELECT CASE
    WHEN EXISTS (
        SELECT 1 FROM sqlite_master
        WHERE type='index'
        AND name='idx_portfolio_snapshots_time'
    )
    THEN 'SKIP_MIGRATION'
    ELSE 'RUN_MIGRATION'
END;

-- SQLite doesn't support ALTER CONSTRAINT, so we need to recreate the table
-- Create new table with all current columns plus the new UNIQUE constraint

CREATE TABLE IF NOT EXISTS portfolio_snapshots_new (
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
    sol_amount REAL DEFAULT 0,
    sol_price REAL DEFAULT 0,
    matic_price REAL DEFAULT 0,
    tracked_tokens_value_usd REAL DEFAULT 0,
    exchange_btc_amount REAL DEFAULT 0,
    exchange_eth_amount REAL DEFAULT 0,
    exchange_ada_amount REAL DEFAULT 0,
    exchange_sol_amount REAL DEFAULT 0,
    exchange_matic_amount REAL DEFAULT 0,
    exchange_other_json TEXT DEFAULT '{}',
    tracked_tokens_json TEXT DEFAULT '{}',
    UNIQUE(user_id, snapshot_time)
);

-- Copy existing data using explicit column names to handle different schemas
INSERT OR IGNORE INTO portfolio_snapshots_new (
    id, user_id, snapshot_date, snapshot_time, total_value_usd,
    ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price,
    staking_value_usd, defi_value_usd, exchange_value_usd, nft_value_usd, created_at,
    sol_amount, sol_price, matic_price, tracked_tokens_value_usd,
    exchange_btc_amount, exchange_eth_amount, exchange_ada_amount,
    exchange_sol_amount, exchange_matic_amount, exchange_other_json, tracked_tokens_json
)
SELECT
    id, user_id, snapshot_date, snapshot_time, total_value_usd,
    ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price,
    staking_value_usd, defi_value_usd, exchange_value_usd, nft_value_usd, created_at,
    COALESCE(sol_amount, 0), COALESCE(sol_price, 0), COALESCE(matic_price, 0), COALESCE(tracked_tokens_value_usd, 0),
    COALESCE(exchange_btc_amount, 0), COALESCE(exchange_eth_amount, 0), COALESCE(exchange_ada_amount, 0),
    COALESCE(exchange_sol_amount, 0), COALESCE(exchange_matic_amount, 0),
    COALESCE(exchange_other_json, '{}'), COALESCE(tracked_tokens_json, '{}')
FROM portfolio_snapshots;

-- Drop old table
DROP TABLE portfolio_snapshots;

-- Rename new table
ALTER TABLE portfolio_snapshots_new RENAME TO portfolio_snapshots;

-- Recreate index
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_id ON portfolio_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time ON portfolio_snapshots(snapshot_time);
