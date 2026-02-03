# Startup Task Throttling System

## Overview

The startup task throttling system prevents redundant API calls during frequent container restarts. It tracks when tasks last ran and enforces cooldown periods to protect API rate limits.

**Special Protection for Taptools**: Aggressive 4-hour cooldown to protect the strict 100 requests/day limit.

## Components

### 1. Database Schema (`migrations/006_startup_task_throttling.sql`)

**startup_tasks table**:
- Tracks when each task last ran
- Records run type (auto vs manual)
- Stores cooldown period in minutes

**service_rate_limits table**:
- Tracks which services are currently rate limited
- Records when rate limit will expire
- Counts how many times limit was hit

### 2. Rate Limit Tracker Service (`services/rate_limit_tracker.py`)

Core service that manages task throttling and rate limit tracking.

**Key Methods**:
```python
# Check if task should run
should_run, reason = await rate_limit_tracker.should_run_task(
    task_name='nft_floor_prices',
    service='taptools',
    cooldown_minutes=240  # 4 hours
)

# Mark task as completed
await rate_limit_tracker.mark_task_run('nft_floor_prices', 'taptools', 'auto')

# Check if service is rate limited
is_limited = await rate_limit_tracker.is_rate_limited('taptools')

# Mark service as rate limited
await rate_limit_tracker.mark_rate_limited('taptools', recovery_minutes=1440)

# Clear rate limit
await rate_limit_tracker.clear_rate_limit('taptools')
```

### 3. Cooldown Tiers

**Tier 1: CRITICAL (Taptools)**
- `nft_floor_prices`: 240 minutes (4 hours)
- `collection_metadata`: 180 minutes (3 hours)
- `bulk_operations`: 240 minutes (4 hours)
- `rate_limit_recovery`: 1440 minutes (24 hours)

**Tier 2: MODERATE**
- Alchemy, Helius, Blockfrost, NFT CDN, NMKR
- 15-60 minute cooldowns depending on operation

**Tier 3: LIGHT**
- Portfolio, Wallet, DeFi operations
- 10-30 minute cooldowns

### 4. Startup Task Integration (`main.py`)

Tasks now check throttling before execution:

```python
async def collect_nft_prices_background():
    # Check cooldown
    should_run, reason = await rate_limit_tracker.should_run_task(
        task_name='nft_floor_prices',
        service='taptools',
        cooldown_minutes=240  # 4 hours
    )

    if not should_run:
        logger.info(f"Skipping NFT prices: {reason}")
        # Still load cached data from database
        return

    # Execute task...
    result = await nft_service.collect_floor_prices_incremental(...)

    # Check if we hit rate limit
    if result['status'] == 'rate_limited':
        await rate_limit_tracker.mark_rate_limited('taptools', 1440)  # 24h
    else:
        await rate_limit_tracker.mark_task_run('nft_floor_prices', 'taptools', 'auto')
```

### 5. Admin API Endpoints (`routers/settings.py`)

**GET /settings/startup-tasks**
- View status of all tasks and rate limits
- See which tasks are in cooldown
- Check which services are rate limited

**POST /settings/startup-tasks/{service}/{task}/force**
- Reset cooldown timer for manual trigger
- Requires authentication
- Does NOT execute the task (just resets timer)

**POST /settings/rate-limits/{service}/clear**
- Manually clear rate limit status
- Use after verifying limit period has passed
- Requires authentication

**POST /settings/rate-limits/{service}/mark**
- Manually mark service as rate limited
- Prevents automatic tasks from using service
- Requires authentication

## Usage Examples

### Check Task Status

```bash
curl -X GET http://localhost:8000/settings/startup-tasks \
  -H "Cookie: session=YOUR_SESSION_TOKEN"
```

Response:
```json
{
  "tasks": [
    {
      "task_name": "nft_floor_prices",
      "service_name": "taptools",
      "last_run": "2026-02-02T10:00:00",
      "run_type": "auto",
      "cooldown_minutes": 240,
      "is_in_cooldown": 1
    }
  ],
  "rate_limits": [
    {
      "service_name": "taptools",
      "is_rate_limited": 0,
      "rate_limit_count": 0
    }
  ],
  "summary": {
    "total_tasks": 3,
    "tasks_in_cooldown": 1,
    "services_rate_limited": 0
  }
}
```

### Force Task Refresh

```bash
curl -X POST http://localhost:8000/settings/startup-tasks/taptools/nft_floor_prices/force \
  -H "Cookie: session=YOUR_SESSION_TOKEN"
```

Response:
```json
{
  "message": "Task cooldown reset for taptools/nft_floor_prices",
  "service": "taptools",
  "task": "nft_floor_prices",
  "run_type": "manual",
  "note": "Cooldown timer reset. Trigger the actual task via its respective API endpoint."
}
```

### Clear Rate Limit

```bash
curl -X POST http://localhost:8000/settings/rate-limits/taptools/clear \
  -H "Cookie: session=YOUR_SESSION_TOKEN"
```

Response:
```json
{
  "message": "Rate limit cleared for service 'taptools'",
  "service": "taptools",
  "note": "Service can now be used for API calls. Use with caution to avoid hitting limits again."
}
```

## How It Works

### On Container Startup

1. Database initialized (includes new tables)
2. Startup tasks check throttling:
   - Portfolio snapshot: 30 minute cooldown
   - Cache warm: 10 minute cooldown
   - NFT floor prices: 240 minute cooldown (Taptools)

3. If cooldown active:
   - Task is skipped
   - Reason logged
   - Cached data loaded from database

4. If cooldown expired:
   - Task executes
   - Success: Mark task as run
   - Rate limited: Mark service as blocked

### Periodic Tasks (Every 4 Hours)

- Periodic tasks are SEPARATE from startup throttling
- They run on their own schedule
- Not affected by startup cooldowns
- Still subject to rate limit checks

### Manual Triggers

- User can force tasks via API
- Bypasses cooldown checks
- Still blocked if service is rate limited
- Resets cooldown timer after execution

## Benefits

1. **Protects Taptools API**: 4-hour cooldown prevents rapid restarts from burning through 100 daily requests
2. **Reduces Redundant Calls**: Portfolio snapshots only created once per 30 minutes
3. **Rate Limit Recovery**: Automatic 24-hour blocking after hitting Taptools limit
4. **Manual Override**: Admin can force refresh when needed
5. **Visibility**: Clear status dashboard shows what's running and what's blocked

## Important Notes

### Taptools Priority

Taptools ($9/mo plan) has the strictest limits:
- 100 requests per day
- Single collection query = 1 request
- Batch operations = multiple requests
- Account suspension risk if exceeded

The 4-hour startup cooldown means:
- Max 6 automatic runs per day
- Each run can fetch 10 collections (2 batches × 5 collections)
- Total: ~60 collections per day
- Leaves headroom for manual refreshes

### Periodic vs Startup Tasks

**Startup Tasks** (throttled):
- Run once on container start
- Subject to cooldown
- Skipped if run recently

**Periodic Tasks** (not throttled):
- Run every 4 hours on schedule
- Independent of startup
- Still respect rate limits

### Database Growth

The `startup_tasks` table is small (one row per task).
The `service_rate_limits` table is tiny (one row per service).

No automatic cleanup needed - these tables are self-maintaining.

## Troubleshooting

### Task Never Runs

**Check cooldown status**:
```bash
curl http://localhost:8000/settings/startup-tasks
```

**Force run**:
```bash
curl -X POST http://localhost:8000/settings/startup-tasks/{service}/{task}/force
```

### Service Rate Limited

**Check rate limit status**:
```bash
curl http://localhost:8000/settings/startup-tasks
```

**Clear rate limit** (if verified safe):
```bash
curl -X POST http://localhost:8000/settings/rate-limits/{service}/clear
```

### Taptools Not Updating

1. Check if rate limited
2. Check last run time (should be 4+ hours ago)
3. Force run if needed
4. Verify API key is valid
5. Check Taptools account usage

## Future Enhancements

Potential improvements:
- Web UI for task management
- Configurable cooldowns per user
- Email alerts on rate limits
- Automatic rate limit detection from API responses
- Task scheduling dashboard
