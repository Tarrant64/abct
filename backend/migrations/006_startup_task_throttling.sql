-- Migration: Add startup task throttling and rate limit tracking
-- Prevents redundant API calls during frequent container restarts
-- Special protection for Taptools NFT API with aggressive cooldowns

-- Track when startup tasks last ran to avoid redundant execution
CREATE TABLE IF NOT EXISTS startup_tasks (
    task_name TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    last_run TIMESTAMP NOT NULL,
    run_type TEXT DEFAULT 'auto',  -- 'auto' (startup) or 'manual' (user triggered)
    cooldown_minutes INTEGER DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_startup_tasks_service ON startup_tasks(service_name);
CREATE INDEX IF NOT EXISTS idx_startup_tasks_last_run ON startup_tasks(last_run);

-- Track rate limit status per service for recovery management
CREATE TABLE IF NOT EXISTS service_rate_limits (
    service_name TEXT PRIMARY KEY,
    is_rate_limited INTEGER DEFAULT 0,  -- Boolean: 0 = normal, 1 = rate limited
    rate_limited_until TIMESTAMP,       -- When rate limit will be cleared
    rate_limit_count INTEGER DEFAULT 0, -- How many times we've hit the limit
    last_rate_limit TIMESTAMP,          -- When we last hit the limit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_service_rate_limits_status ON service_rate_limits(is_rate_limited);
CREATE INDEX IF NOT EXISTS idx_service_rate_limits_until ON service_rate_limits(rate_limited_until);
