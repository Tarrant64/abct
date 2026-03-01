"""
Rate Limit Tracker Service

Manages startup task throttling and service rate limit tracking to prevent
redundant API calls during frequent container restarts.

Special protection for Taptools (Cardano NFT API) with aggressive 4-hour cooldowns.

Usage:
    from services.rate_limit_tracker import rate_limit_tracker

    # Check if task should run
    should_run, reason = await rate_limit_tracker.should_run_task(
        task_name='nft_floor_prices',
        service='taptools',
        cooldown_minutes=240  # 4 hours for Taptools
    )

    if should_run:
        # ... execute task ...
        await rate_limit_tracker.mark_task_run('nft_floor_prices', 'taptools', 'auto')
    else:
        logger.info(f"Skipping task: {reason}")
"""

import aiosqlite
from datetime import datetime, timedelta
import logging
from typing import Optional, Tuple

from config import DATABASE_PATH, BLOCKFROST_BASE_URL, BLOCKFROST_EXTERNAL_URL

logger = logging.getLogger(__name__)

# ============================================================================
# COOLDOWN CONFIGURATIONS BY SERVICE
# ============================================================================

# Tier 1: CRITICAL - Taptools (Cardano NFT API)
# Very strict rate limits ($9/mo plan = 100 requests/day)
# Aggressive protection to prevent account suspension
TAPTOOLS_COOLDOWNS = {
    'nft_floor_prices': 240,        # 4 hours between startup runs
    'collection_metadata': 180,     # 3 hours
    'bulk_operations': 240,         # 4 hours
    'rate_limit_recovery': 1440,    # 24 hours after hitting rate limit
}

# Tier 2: MODERATE - APIs with rate limits but more generous
# Blockfrost cooldowns are minimal when using self-hosted RYO (no rate limits)
_blockfrost_is_self_hosted = BLOCKFROST_BASE_URL != BLOCKFROST_EXTERNAL_URL
_blockfrost_cooldown = 2 if _blockfrost_is_self_hosted else 30

MODERATE_COOLDOWNS = {
    'alchemy': {'nft_queries': 20, 'token_queries': 15},
    'helius': {'nft_queries': 20, 'token_queries': 15},
    'coingecko': {'price_queries': 30},
    'blockfrost': {'wallet_queries': _blockfrost_cooldown, 'nft_queries': _blockfrost_cooldown},
    'nftcdn': {'metadata_queries': 60},
    'nmkr': {'metadata_queries': 60},
}

# Tier 3: LIGHT - Generous limits or no limits
LIGHT_COOLDOWNS = {
    'portfolio': {'snapshot': 30, 'cache_warm': 10},
    'wallet': {'balances': 10},
    'defi': {'staking_info': 20},
}


def get_default_cooldown(service: str, task_name: str) -> int:
    """Get default cooldown for a service/task combination."""
    # Taptools gets special treatment
    if service == 'taptools':
        return TAPTOOLS_COOLDOWNS.get(task_name, 240)  # Default 4 hours

    # Check moderate tier
    if service in MODERATE_COOLDOWNS:
        return MODERATE_COOLDOWNS[service].get(task_name, 20)  # Default 20 min

    # Check light tier
    if service in LIGHT_COOLDOWNS:
        return LIGHT_COOLDOWNS[service].get(task_name, 10)  # Default 10 min

    # Unknown service, use conservative default
    return 30


class RateLimitTracker:
    """Manages startup task throttling and rate limit tracking."""

    def __init__(self):
        self.db_path = DATABASE_PATH

    async def should_run_task(
        self,
        task_name: str,
        service: str,
        cooldown_minutes: Optional[int] = None,
        force: bool = False
    ) -> Tuple[bool, str]:
        """
        Check if a startup task should run based on cooldown and rate limits.

        Args:
            task_name: Name of the task (e.g., 'nft_floor_prices')
            service: Service name (e.g., 'taptools', 'portfolio')
            cooldown_minutes: Custom cooldown in minutes (optional)
            force: If True, bypass all cooldowns (manual trigger)

        Returns:
            Tuple of (should_run: bool, reason: str)
        """
        # Manual triggers always bypass cooldowns
        if force:
            return True, "Manual trigger (bypassing cooldown)"

        # Check if service is currently rate limited
        if await self.is_rate_limited(service):
            recovery_time = await self._get_rate_limit_recovery_time(service)
            return False, f"Service {service} is rate limited until {recovery_time}"

        # Get cooldown period
        if cooldown_minutes is None:
            cooldown_minutes = get_default_cooldown(service, task_name)

        # Check last run time
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT last_run, run_type, cooldown_minutes FROM startup_tasks WHERE task_name = ?",
                (task_name,)
            )
            row = await cursor.fetchone()

            if not row:
                # Task never run before, safe to run
                return True, "Task never run before"

            last_run = datetime.fromisoformat(row['last_run'])
            time_since_run = datetime.now() - last_run
            cooldown_delta = timedelta(minutes=cooldown_minutes)

            if time_since_run < cooldown_delta:
                time_remaining = cooldown_delta - time_since_run
                minutes_remaining = int(time_remaining.total_seconds() / 60)
                return False, f"Cooldown active ({minutes_remaining} minutes remaining of {cooldown_minutes} minute cooldown)"

            # Cooldown expired, safe to run
            return True, f"Cooldown expired (last run {int(time_since_run.total_seconds() / 60)} minutes ago)"

    async def mark_task_run(
        self,
        task_name: str,
        service: str,
        run_type: str = 'auto',
        cooldown_minutes: Optional[int] = None
    ):
        """
        Record that a task has run successfully.

        Args:
            task_name: Name of the task
            service: Service name
            run_type: 'auto' (startup) or 'manual' (user triggered)
            cooldown_minutes: Cooldown period in minutes (optional)
        """
        if cooldown_minutes is None:
            cooldown_minutes = get_default_cooldown(service, task_name)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO startup_tasks (task_name, service_name, last_run, run_type, cooldown_minutes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_name) DO UPDATE SET
                    last_run = excluded.last_run,
                    run_type = excluded.run_type,
                    cooldown_minutes = excluded.cooldown_minutes,
                    updated_at = excluded.updated_at
            """, (
                task_name,
                service,
                datetime.now().isoformat(),
                run_type,
                cooldown_minutes,
                datetime.now().isoformat()
            ))
            await db.commit()

        logger.info(f"Marked task '{task_name}' as run ({run_type}) with {cooldown_minutes} minute cooldown")

    async def is_rate_limited(self, service: str) -> bool:
        """
        Check if a service is currently rate limited.

        Args:
            service: Service name

        Returns:
            True if service is rate limited, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT is_rate_limited, rate_limited_until FROM service_rate_limits WHERE service_name = ?",
                (service,)
            )
            row = await cursor.fetchone()

            if not row or not row['is_rate_limited']:
                return False

            # Check if rate limit has expired
            if row['rate_limited_until']:
                recovery_time = datetime.fromisoformat(row['rate_limited_until'])
                if datetime.now() >= recovery_time:
                    # Rate limit expired, clear it automatically
                    await self.clear_rate_limit(service)
                    return False

            return True

    async def _get_rate_limit_recovery_time(self, service: str) -> Optional[str]:
        """Get the timestamp when rate limit will be cleared."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT rate_limited_until FROM service_rate_limits WHERE service_name = ?",
                (service,)
            )
            row = await cursor.fetchone()
            return row['rate_limited_until'] if row else None

    async def mark_rate_limited(
        self,
        service: str,
        recovery_minutes: Optional[int] = None
    ):
        """
        Mark a service as rate limited.

        Args:
            service: Service name
            recovery_minutes: How long until rate limit clears (default: service-specific)
        """
        # Use service-specific recovery times
        if recovery_minutes is None:
            if service == 'taptools':
                recovery_minutes = TAPTOOLS_COOLDOWNS['rate_limit_recovery']  # 24 hours
            else:
                recovery_minutes = 60  # Default 1 hour

        recovery_time = datetime.now() + timedelta(minutes=recovery_minutes)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO service_rate_limits (
                    service_name, is_rate_limited, rate_limited_until,
                    rate_limit_count, last_rate_limit, updated_at
                )
                VALUES (?, 1, ?, COALESCE((SELECT rate_limit_count FROM service_rate_limits WHERE service_name = ?), 0) + 1, ?, ?)
                ON CONFLICT(service_name) DO UPDATE SET
                    is_rate_limited = 1,
                    rate_limited_until = excluded.rate_limited_until,
                    rate_limit_count = rate_limit_count + 1,
                    last_rate_limit = excluded.last_rate_limit,
                    updated_at = excluded.updated_at
            """, (
                service,
                recovery_time.isoformat(),
                service,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            await db.commit()

        logger.warning(
            f"Service '{service}' marked as rate limited until {recovery_time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"({recovery_minutes} minutes)"
        )

    async def clear_rate_limit(self, service: str):
        """
        Clear rate limit status for a service (manual recovery or automatic expiration).

        Args:
            service: Service name
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE service_rate_limits
                SET is_rate_limited = 0,
                    rate_limited_until = NULL,
                    updated_at = ?
                WHERE service_name = ?
            """, (datetime.now().isoformat(), service))
            await db.commit()

        logger.info(f"Rate limit cleared for service '{service}'")

    async def get_all_task_status(self) -> list:
        """Get status of all tracked tasks."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT
                    task_name,
                    service_name,
                    last_run,
                    run_type,
                    cooldown_minutes,
                    CASE
                        WHEN datetime(last_run, '+' || cooldown_minutes || ' minutes') > datetime('now')
                        THEN 1 ELSE 0
                    END as is_in_cooldown
                FROM startup_tasks
                ORDER BY last_run DESC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_rate_limit_status(self) -> list:
        """Get rate limit status for all services."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT
                    service_name,
                    is_rate_limited,
                    rate_limited_until,
                    rate_limit_count,
                    last_rate_limit
                FROM service_rate_limits
                ORDER BY service_name
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# Singleton instance
rate_limit_tracker = RateLimitTracker()
