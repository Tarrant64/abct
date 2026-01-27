"""
NFT Floor Price Background Scheduler

Continuously fetches Cardano NFT floor prices in the background using APScheduler.
Designed to work around TapTools API rate limits (100 calls/day) by spreading updates across 24 hours.

Strategy:
- Runs every NFT_UPDATE_INTERVAL_MINUTES (default: 15 minutes)
- Updates NFT_CALLS_PER_UPDATE collections per run (default: 1 = 96/day max)
- Prioritizes high-value collections and stale data
- Persists all state to database for graceful restarts
- Integrates with existing NFT service for API calls

Key Features:
- Progress tracking: Restarts pick up exactly where they left off
- Rate limit management: Respects TapTools 100/day limit with safety buffer
- Priority system: High-value or user-owned collections updated first
- Automatic collection discovery: Learns from NFTs in user wallets
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import (
    DATABASE_PATH,
    NFT_UPDATE_INTERVAL_MINUTES,
    NFT_CALLS_PER_UPDATE,
    NFT_MAX_DAILY_CALLS,
    TAPTOOLS_API_KEY
)
from database import get_db
from services.nft import nft_service

logger = logging.getLogger(__name__)


class NFTSchedulerService:
    """Background service for continuously updating NFT floor prices."""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.enabled = False
        self.stats = {
            "started_at": None,
            "last_update": None,
            "total_updates": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "last_error": None,
            "rate_limited_until": None
        }

    async def initialize(self):
        """Initialize scheduler and load state from database."""
        try:
            db = await get_db()

            # Load scheduler state
            cursor = await db.execute("""
                SELECT enabled, started_at, last_update, total_updates,
                       successful_updates, failed_updates, last_error, rate_limited_until
                FROM nft_scheduler_state WHERE id = 1
            """)
            row = await cursor.fetchone()

            if row:
                self.stats = {
                    "started_at": row["started_at"],
                    "last_update": row["last_update"],
                    "total_updates": row["total_updates"] or 0,
                    "successful_updates": row["successful_updates"] or 0,
                    "failed_updates": row["failed_updates"] or 0,
                    "last_error": row["last_error"],
                    "rate_limited_until": row["rate_limited_until"]
                }
                self.enabled = bool(row["enabled"])

            await db.close()
            logger.info(f"NFT Scheduler initialized. Enabled: {self.enabled}")

        except Exception as e:
            logger.error(f"Failed to initialize NFT scheduler: {e}")

    async def save_state(self):
        """Persist current scheduler state to database."""
        try:
            db = await get_db()
            await db.execute("""
                UPDATE nft_scheduler_state
                SET last_update = ?,
                    total_updates = ?,
                    successful_updates = ?,
                    failed_updates = ?,
                    last_error = ?,
                    rate_limited_until = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                self.stats["last_update"],
                self.stats["total_updates"],
                self.stats["successful_updates"],
                self.stats["failed_updates"],
                self.stats["last_error"],
                self.stats["rate_limited_until"]
            ))
            await db.commit()
            await db.close()
        except Exception as e:
            logger.error(f"Failed to save scheduler state: {e}")

    async def get_api_calls_today(self) -> int:
        """Count API calls made today for rate limiting."""
        try:
            db = await get_db()
            today = datetime.utcnow().strftime("%Y-%m-%d")
            cursor = await db.execute("""
                SELECT COUNT(*) as count FROM nft_scheduler_api_calls
                WHERE called_at >= ?
            """, (f"{today} 00:00:00",))
            row = await cursor.fetchone()
            count = row["count"] if row else 0
            await db.close()
            return count
        except Exception as e:
            logger.error(f"Error counting API calls: {e}")
            return 0

    async def log_api_call(self, endpoint: str, policy_id: str, status_code: int):
        """Log an API call for rate limit tracking."""
        try:
            db = await get_db()
            await db.execute("""
                INSERT INTO nft_scheduler_api_calls (endpoint, policy_id, status_code, called_at)
                VALUES (?, ?, ?, ?)
            """, (endpoint, policy_id, status_code, datetime.utcnow().isoformat()))
            await db.commit()
            await db.close()
        except Exception as e:
            logger.error(f"Error logging API call: {e}")

    async def get_next_collection_to_update(self) -> Optional[Dict]:
        """Get the next collection that needs updating based on priority and staleness."""
        try:
            db = await get_db()

            # Get collection that:
            # 1. Hasn't been updated in last hour OR never updated
            # 2. Prioritize by: priority DESC, then oldest update first
            cursor = await db.execute("""
                SELECT policy_id, collection_name, priority, last_updated
                FROM nft_scheduler_collections
                WHERE last_updated IS NULL
                   OR last_updated < datetime('now', '-1 hour')
                ORDER BY priority DESC, last_updated ASC
                LIMIT 1
            """)
            row = await cursor.fetchone()
            await db.close()

            if row:
                return {
                    "policy_id": row["policy_id"],
                    "collection_name": row["collection_name"],
                    "priority": row["priority"],
                    "last_updated": row["last_updated"]
                }
            return None

        except Exception as e:
            logger.error(f"Error getting next collection: {e}")
            return None

    async def update_collection_data(self, policy_id: str, data: Dict):
        """Update collection data in database after successful fetch."""
        try:
            db = await get_db()
            now = datetime.utcnow().isoformat()

            # Update scheduler collections table
            await db.execute("""
                UPDATE nft_scheduler_collections
                SET collection_name = COALESCE(?, collection_name),
                    last_floor_price = ?,
                    supply = ?,
                    holders = ?,
                    listings = ?,
                    volume_24h = ?,
                    volume_7d = ?,
                    volume_30d = ?,
                    last_updated = ?,
                    update_count = update_count + 1
                WHERE policy_id = ?
            """, (
                data.get("name"),
                data.get("floor_price_ada"),
                data.get("supply"),
                data.get("holders"),
                data.get("listings"),
                data.get("volume_24h"),
                data.get("volume_7d"),
                data.get("volume_30d"),
                now,
                policy_id
            ))

            # Also update main nft_floor_prices table for ABCT to use
            if data.get("floor_price_ada"):
                await db.execute("""
                    INSERT INTO nft_floor_prices
                        (policy_id, collection_name, floor_price_ada, listings, supply, source, fetched_at)
                    VALUES (?, ?, ?, ?, ?, 'scheduler', ?)
                    ON CONFLICT(policy_id, fetched_at) DO UPDATE SET
                        floor_price_ada = excluded.floor_price_ada,
                        listings = excluded.listings,
                        supply = excluded.supply
                """, (
                    policy_id,
                    data.get("name"),
                    data.get("floor_price_ada"),
                    data.get("listings"),
                    data.get("supply"),
                    now
                ))

            await db.commit()
            await db.close()

            logger.info(f"Updated {data.get('name', policy_id[:12])}: {data.get('floor_price_ada', 0)} ADA")

        except Exception as e:
            logger.error(f"Error updating collection data: {e}")

    async def fetch_and_update_collection(self, policy_id: str) -> bool:
        """Fetch floor price for a collection and update database."""
        try:
            # Check if we have TapTools API key
            if not TAPTOOLS_API_KEY:
                logger.warning("TapTools API key not configured, skipping NFT scheduler")
                return False

            # Use existing NFT service to fetch data (respects rate limits)
            floor_data = await nft_service.fetch_floor_price(policy_id)

            # Log the API call
            await self.log_api_call("taptools/collection", policy_id, 200 if floor_data else 400)

            if floor_data:
                # Update database with new data
                await self.update_collection_data(policy_id, floor_data)
                return True
            else:
                logger.warning(f"No floor data returned for {policy_id[:12]}")
                return False

        except Exception as e:
            logger.error(f"Error fetching collection {policy_id[:12]}: {e}")
            return False

    async def scheduled_update(self):
        """Scheduled task to update collection prices."""
        self.stats["total_updates"] += 1

        try:
            # Check if rate limited
            if self.stats.get("rate_limited_until"):
                reset_time = datetime.fromisoformat(self.stats["rate_limited_until"])
                if datetime.utcnow() < reset_time:
                    logger.info(f"Rate limited until {reset_time}")
                    return
                else:
                    # Rate limit expired, clear it
                    self.stats["rate_limited_until"] = None

            # Check daily API call count
            calls_today = await self.get_api_calls_today()
            if calls_today >= NFT_MAX_DAILY_CALLS:
                logger.warning(f"Daily rate limit reached: {calls_today}/{NFT_MAX_DAILY_CALLS} calls")
                # Set rate limited until midnight UTC tomorrow
                self.stats["rate_limited_until"] = (
                    datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                ).isoformat()
                await self.save_state()
                return

            # Update NFT_CALLS_PER_UPDATE collections
            updated_count = 0
            for _ in range(NFT_CALLS_PER_UPDATE):
                # Check rate limit again after each call
                calls_today = await self.get_api_calls_today()
                if calls_today >= NFT_MAX_DAILY_CALLS:
                    break

                # Get next collection to update
                collection = await self.get_next_collection_to_update()
                if not collection:
                    logger.info("No collections need updating")
                    break

                # Fetch and update
                success = await self.fetch_and_update_collection(collection["policy_id"])

                if success:
                    self.stats["successful_updates"] += 1
                    updated_count += 1
                else:
                    self.stats["failed_updates"] += 1

                # Small delay between calls to be respectful
                await asyncio.sleep(0.5)

            self.stats["last_update"] = datetime.utcnow().isoformat()
            self.stats["last_error"] = None

            if updated_count > 0:
                logger.info(f"Updated {updated_count} collection(s). Total today: {await self.get_api_calls_today()}/{NFT_MAX_DAILY_CALLS}")

        except Exception as e:
            logger.error(f"Scheduled update error: {e}")
            self.stats["last_error"] = str(e)
            self.stats["failed_updates"] += 1

        finally:
            # Always save state after update attempt
            await self.save_state()

    async def start(self):
        """Start the background scheduler."""
        if not self.enabled:
            logger.info("NFT Scheduler not enabled")
            return

        if self.scheduler:
            logger.warning("Scheduler already running")
            return

        try:
            # Create and start scheduler
            self.scheduler = AsyncIOScheduler()
            self.scheduler.add_job(
                self.scheduled_update,
                IntervalTrigger(minutes=NFT_UPDATE_INTERVAL_MINUTES),
                id="nft_price_update",
                name="NFT Floor Price Update",
                max_instances=1  # Prevent overlapping runs
            )
            self.scheduler.start()

            # Update started_at timestamp
            self.stats["started_at"] = datetime.utcnow().isoformat()

            # Save state
            db = await get_db()
            await db.execute("""
                UPDATE nft_scheduler_state
                SET started_at = ?, enabled = 1
                WHERE id = 1
            """, (self.stats["started_at"],))
            await db.commit()
            await db.close()

            logger.info(f"NFT Scheduler started. Update interval: {NFT_UPDATE_INTERVAL_MINUTES} minutes")

        except Exception as e:
            logger.error(f"Failed to start NFT scheduler: {e}")
            self.enabled = False

    async def stop(self):
        """Stop the background scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            self.scheduler = None
            logger.info("NFT Scheduler stopped")

        # Save final state
        await self.save_state()

    async def enable(self):
        """Enable the scheduler and start it."""
        self.enabled = True

        # Update database
        db = await get_db()
        await db.execute("UPDATE nft_scheduler_state SET enabled = 1 WHERE id = 1")
        await db.commit()
        await db.close()

        await self.start()
        logger.info("NFT Scheduler enabled")

    async def disable(self):
        """Disable the scheduler and stop it."""
        self.enabled = False

        # Update database
        db = await get_db()
        await db.execute("UPDATE nft_scheduler_state SET enabled = 0 WHERE id = 1")
        await db.commit()
        await db.close()

        await self.stop()
        logger.info("NFT Scheduler disabled")

    async def register_collection(self, policy_id: str, name: str = None, priority: int = 0):
        """Register a new collection to track."""
        try:
            db = await get_db()

            # Insert or update collection
            await db.execute("""
                INSERT INTO nft_scheduler_collections (policy_id, collection_name, priority, last_updated)
                VALUES (?, ?, ?, datetime('now', '-2 hours'))
                ON CONFLICT(policy_id) DO UPDATE SET
                    collection_name = COALESCE(excluded.collection_name, nft_scheduler_collections.collection_name),
                    priority = excluded.priority
            """, (policy_id, name, priority))

            await db.commit()
            await db.close()

            logger.info(f"Registered collection {name or policy_id[:12]} with priority {priority}")

        except Exception as e:
            logger.error(f"Error registering collection: {e}")

    async def get_status(self) -> Dict:
        """Get detailed scheduler status."""
        try:
            db = await get_db()

            # Get API calls today
            calls_today = await self.get_api_calls_today()

            # Get collection counts
            cursor = await db.execute("SELECT COUNT(*) as count FROM nft_scheduler_collections")
            row = await cursor.fetchone()
            collections_total = row["count"] if row else 0

            cursor = await db.execute("""
                SELECT COUNT(*) as count FROM nft_scheduler_collections
                WHERE last_updated >= datetime('now', '-24 hours')
            """)
            row = await cursor.fetchone()
            collections_updated_24h = row["count"] if row else 0

            cursor = await db.execute("""
                SELECT COUNT(*) as count FROM nft_scheduler_collections
                WHERE last_updated IS NULL OR last_updated < datetime('now', '-1 hour')
            """)
            row = await cursor.fetchone()
            collections_stale = row["count"] if row else 0

            # Get next run time
            next_run = None
            if self.scheduler and self.enabled:
                job = self.scheduler.get_job("nft_price_update")
                if job and job.next_run_time:
                    next_run = job.next_run_time.isoformat()

            await db.close()

            return {
                "enabled": self.enabled,
                "running": self.scheduler is not None,
                "next_run": next_run,
                "update_interval_minutes": NFT_UPDATE_INTERVAL_MINUTES,
                "calls_per_update": NFT_CALLS_PER_UPDATE,
                "api_calls_today": calls_today,
                "api_calls_remaining": NFT_MAX_DAILY_CALLS - calls_today,
                "api_calls_limit": NFT_MAX_DAILY_CALLS,
                "collections_total": collections_total,
                "collections_updated_24h": collections_updated_24h,
                "collections_stale": collections_stale,
                "taptools_configured": bool(TAPTOOLS_API_KEY),
                **self.stats
            }

        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {"enabled": False, "error": str(e)}


# Global instance
nft_scheduler = NFTSchedulerService()
