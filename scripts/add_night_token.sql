-- Add NIGHT token to ABCT database for Midnight Network support
-- Run this to enable NIGHT token tracking for Cardano wallets
-- Usage: sqlite3 /path/to/abct.db < add_night_token.sql

INSERT OR IGNORE INTO token_metadata (
    asset_id,
    policy_id,
    asset_name,
    ticker,
    name,
    decimals,
    logo_url,
    track_for_pricing,
    updated_at
) VALUES (
    '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854',
    '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa',
    '4e49474854',
    'NIGHT',
    'Midnight Network Token',
    6,
    NULL,
    1,
    CURRENT_TIMESTAMP
);

-- Verify the insert
SELECT
    ticker,
    name,
    decimals,
    track_for_pricing,
    'Inserted successfully' as status
FROM token_metadata
WHERE asset_id = '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854';
