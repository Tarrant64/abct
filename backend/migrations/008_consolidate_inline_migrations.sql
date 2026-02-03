-- Migration 008: Consolidate inline migrations from database.py
-- This migration adds columns that were previously added inline

-- Add is_demo column to users (if not exists)
ALTER TABLE users ADD COLUMN is_demo BOOLEAN DEFAULT 0;

-- Add track_for_pricing to token_metadata
ALTER TABLE token_metadata ADD COLUMN track_for_pricing INTEGER DEFAULT 0;

-- Add Solana columns to portfolio_snapshots  
ALTER TABLE portfolio_snapshots ADD COLUMN sol_amount REAL DEFAULT 0;
ALTER TABLE portfolio_snapshots ADD COLUMN sol_value_usd REAL DEFAULT 0;

-- Add tracked tokens value column
ALTER TABLE portfolio_snapshots ADD COLUMN tracked_tokens_value_usd REAL DEFAULT 0;

-- Add api_secret and api_passphrase to api_settings
ALTER TABLE api_settings ADD COLUMN api_secret TEXT;
ALTER TABLE api_settings ADD COLUMN api_passphrase TEXT;
