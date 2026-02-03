-- Migration 008: Consolidate inline migrations from database.py
-- NOTE: This migration is a placeholder for documentation purposes.
-- The columns listed below were previously added via inline ALTER TABLE
-- statements in database.py's init_db() function. They already exist in
-- production databases, so this migration does nothing.
--
-- This serves as historical documentation of what was added inline:
-- - users.is_demo (BOOLEAN DEFAULT 0)
-- - token_metadata.track_for_pricing (INTEGER DEFAULT 0)
-- - portfolio_snapshots.sol_amount (REAL DEFAULT 0)
-- - portfolio_snapshots.sol_value_usd (REAL DEFAULT 0)
-- - portfolio_snapshots.tracked_tokens_value_usd (REAL DEFAULT 0)
-- - api_settings.api_secret (TEXT)
-- - api_settings.api_passphrase (TEXT)
--
-- Future migrations should use this migrations/ folder instead of inline ALTER TABLE.

SELECT 1; -- No-op migration for tracking purposes
