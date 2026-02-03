-- Transaction History Table
-- Stores normalized transaction data from all blockchains

CREATE TABLE IF NOT EXISTS transaction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_id INTEGER NOT NULL,
    blockchain TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    tx_time TIMESTAMP NOT NULL,
    direction TEXT NOT NULL,  -- 'sent' or 'received'
    amount TEXT,
    token_symbol TEXT,
    token_name TEXT,
    from_address TEXT,
    to_address TEXT,
    fee TEXT,
    status TEXT DEFAULT 'confirmed',
    metadata TEXT,  -- JSON with chain-specific details
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, blockchain, tx_hash),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tx_history_user ON transaction_history(user_id);
CREATE INDEX IF NOT EXISTS idx_tx_history_time ON transaction_history(tx_time DESC);
CREATE INDEX IF NOT EXISTS idx_tx_history_blockchain ON transaction_history(blockchain);
CREATE INDEX IF NOT EXISTS idx_tx_history_direction ON transaction_history(direction);
CREATE INDEX IF NOT EXISTS idx_tx_history_hash ON transaction_history(tx_hash);
CREATE INDEX IF NOT EXISTS idx_tx_history_wallet ON transaction_history(wallet_id);
