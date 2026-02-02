-- Migration: Add hidden_tokens table for spam token filtering
-- This table stores tokens that users have chosen to hide from their wallets

CREATE TABLE IF NOT EXISTS hidden_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    blockchain TEXT NOT NULL,
    token_address TEXT NOT NULL,
    token_symbol TEXT,
    token_name TEXT,
    reason TEXT DEFAULT 'spam',
    hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, blockchain, token_address),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hidden_tokens_user ON hidden_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_hidden_tokens_blockchain ON hidden_tokens(user_id, blockchain);
CREATE INDEX IF NOT EXISTS idx_hidden_tokens_lookup ON hidden_tokens(user_id, blockchain, token_address);
