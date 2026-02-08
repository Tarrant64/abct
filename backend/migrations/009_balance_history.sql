-- Migration 009: Balance History Tables
-- Stores real on-chain historical balance data reconstructed from blockchain APIs.
-- Separate from v1 portfolio_snapshots which are estimated from current holdings.

CREATE TABLE IF NOT EXISTS balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_id INTEGER NOT NULL,
    blockchain TEXT NOT NULL,
    balance_date DATE NOT NULL,
    native_amount REAL NOT NULL DEFAULT 0,
    native_symbol TEXT NOT NULL,
    native_price_usd REAL DEFAULT 0,
    native_value_usd REAL DEFAULT 0,
    token_value_usd REAL DEFAULT 0,
    total_value_usd REAL DEFAULT 0,
    data_source TEXT DEFAULT 'chain',
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, wallet_id, balance_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bh_user_date ON balance_history(user_id, balance_date DESC);
CREATE INDEX IF NOT EXISTS idx_bh_wallet_date ON balance_history(wallet_id, balance_date);

CREATE TABLE IF NOT EXISTS balance_history_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_id INTEGER,
    blockchain TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    step TEXT DEFAULT '',
    total_items INTEGER DEFAULT 0,
    processed_items INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
