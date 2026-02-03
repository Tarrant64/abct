-- Migration: Allow hourly portfolio snapshots
-- Changes UNIQUE constraint from (user_id, snapshot_date) to (user_id, snapshot_time)
-- This allows multiple snapshots per day for hourly tracking

-- Check if migration is needed (if old constraint exists)
-- SQLite doesn't support ALTER CONSTRAINT, so we need to recreate the table

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
    sol_amount REAL DEFAULT 0,
    sol_price REAL DEFAULT 0,
    matic_amount REAL DEFAULT 0,
    matic_price REAL DEFAULT 0,
    staking_value_usd REAL DEFAULT 0,
    defi_value_usd REAL DEFAULT 0,
    exchange_value_usd REAL DEFAULT 0,
    nft_value_usd REAL DEFAULT 0,
    tracked_tokens_value_usd REAL DEFAULT 0,
    exchange_btc_amount REAL DEFAULT 0,
    exchange_eth_amount REAL DEFAULT 0,
    exchange_ada_amount REAL DEFAULT 0,
    exchange_sol_amount REAL DEFAULT 0,
    exchange_matic_amount REAL DEFAULT 0,
    exchange_other_json TEXT DEFAULT '{}',
    tracked_tokens_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, snapshot_time)
);

-- Copy existing data (handles both old and new column sets)
INSERT OR IGNORE INTO portfolio_snapshots_new
SELECT * FROM portfolio_snapshots;

-- Drop old table
DROP TABLE portfolio_snapshots;

-- Rename new table
ALTER TABLE portfolio_snapshots_new RENAME TO portfolio_snapshots;

-- Recreate index
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_user_id ON portfolio_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time ON portfolio_snapshots(snapshot_time);
