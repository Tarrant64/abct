"""
Stock Price Scheduler (WQ-0382) -- 3x/day refresh for manual stock holdings.

Mirrors services/stake_rediscovery_scheduler.py's structure (AsyncIOScheduler,
cross-process advisory lock, max_instances=1, clean shutdown) but replaces the
interval trigger with a cron trigger, because the user's spec is tied to the
US market session, not to a period: three runs a day at market open, midday
and market close (config.STOCK_REFRESH_TIMES, default "09:35,12:00,16:05" in
STOCK_MARKET_TZ=America/New_York, Monday-Friday).

- The cron fires in the MARKET timezone, so the schedule stays correct across
  both DST transitions without recomputation.
- A few minutes of offset past 9:30/16:00 so the auction prints exist when we
  read them.
- Weekends: no job. Holidays: a harmless re-fetch of the unchanged last close.
- Each cycle: get_tracked_stock_symbols() (distinct symbols across all
  users) -> stock_data_service.refresh_and_store() -> for any symbol that
  got no quote but has a tracked holding, backfill recent daily bars so the
  history table (and the frontend sparkline) still has data.
- Kill switch STOCK_SCHEDULER_ENABLED (config.py), read once at process
  start -- same model as WALLET_BGSYNC_ENABLED / STAKE_REDISCOVERY_ENABLED.
  NOTE: unlike those two, this one defaults to ON: the engine's whole cost is
  one CNBC call three times a day (plus at most 10 fallback calls), it is
  read-only against public endpoints, and the user's request explicitly set
  the default schedule ("The default schedule of refreshing ... should be 3
  times a day, market open, midday and market close", 2026-10-20).
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    STOCK_SCHEDULER_ENABLED,
    STOCK_MARKET_TZ,
    STOCK_REFRESH_TIMES,
    STOCK_SCHEDULER_LOCK_TTL_MINUTES,
)
from database import (
    get_tracked_stock_symbols,
    try_acquire_scheduler_lock,
    release_scheduler_lock,
)
from services.stock_data import stock_data_service

logger = logging.getLogger(__name__)

LOCK_NAME = "stock_price_refresh"


def parse_refresh_times(spec: str):
    """'09:35,12:00,16:05' -> [{'hour':..,'minute':..}, ...] (validated)."""
    out = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hh, mm = part.split(":", 1)
            hh, mm = int(hh), int(mm)
        except ValueError:
            logger.warning("stock_scheduler: bad refresh time %r ignored", part)
            continue
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            logger.warning("stock_scheduler: out-of-range time %r ignored", part)
            continue
        out.append({"hour": hh, "minute": mm})
    if not out:
        logger.warning("stock_scheduler: no valid times in %r, using defaults",
                       spec)
        out = [{"hour": 9, "minute": 35}, {"hour": 12, "minute": 0},
               {"hour": 16, "minute": 5}]
    return out


class StockSchedulerService:
    """Background service refreshing manual-stock prices 3x per market day."""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.enabled = STOCK_SCHEDULER_ENABLED
        self._holder = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.stats = {
            "started_at": None,
            "last_cycle_at": None,
            "last_cycle_duration_s": None,
            "total_cycles": 0,
            "lock_skipped_cycles": 0,
            "last_attempted": 0,
            "last_priced": 0,
            "last_error": None,
            "next_runs": [],
        }

    async def run_cycle(self, reason: str = "cron") -> dict:
        """One refresh pass over every distinct tracked symbol."""
        cycle_started = datetime.now()

        got_lock = await try_acquire_scheduler_lock(
            LOCK_NAME, self._holder,
            ttl_seconds=STOCK_SCHEDULER_LOCK_TTL_MINUTES * 60,
        )
        if not got_lock:
            self.stats["lock_skipped_cycles"] += 1
            logger.debug("stock_scheduler: lock held elsewhere, skipping tick")
            return {"skipped": "lock"}

        try:
            tracked = await get_tracked_stock_symbols()
            stats = await stock_data_service.refresh_and_store(tracked)
            stats["reason"] = reason

            # Symbols the live feed could not price still deserve fresh
            # daily bars: backfill from Nasdaq history (yesterday's close
            # beats a gap in the chart).
            priced = set(k for k, v in stats.get("sources", {}).items())
            for item in tracked:
                sym = item.get("symbol")
                if sym and sym not in priced:
                    try:
                        n = await stock_data_service.backfill_history(
                            sym, item.get("asset_class", "stock"), days=7)
                        if n:
                            logger.info(
                                "stock_scheduler: %s unpriced, backfilled "
                                "%d daily bars", sym, n)
                    except Exception as e:
                        logger.warning(
                            "stock_scheduler: backfill %s failed: %s", sym, e)

            duration_s = (datetime.now() - cycle_started).total_seconds()
            self.stats["total_cycles"] += 1
            self.stats["last_cycle_at"] = cycle_started.isoformat()
            self.stats["last_cycle_duration_s"] = round(duration_s, 2)
            self.stats["last_attempted"] = stats.get("attempted", 0)
            self.stats["last_priced"] = stats.get("priced", 0)
            self.stats["last_error"] = None

            logger.info(
                "stock_scheduler: cycle done reason=%s attempted=%d priced=%d "
                "sources=%s disagreements=%d duration=%.2fs",
                reason, stats.get("attempted", 0), stats.get("priced", 0),
                stats.get("sources", {}), len(stats.get("disagreements", [])),
                duration_s,
            )
            return stats
        except Exception as e:
            self.stats["last_error"] = str(e)
            logger.warning("stock_scheduler: cycle failed: %s", e)
            return {"error": str(e)}
        finally:
            try:
                await release_scheduler_lock(LOCK_NAME, self._holder)
            except Exception:
                pass

    async def start(self):
        """Start the cron scheduler, honoring the STOCK_SCHEDULER_ENABLED switch."""
        if not self.enabled:
            logger.info("Stock price scheduler disabled "
                        "(set STOCK_SCHEDULER_ENABLED=true to enable)")
            return
        if self.scheduler:
            logger.warning("Stock scheduler already running")
            return

        self.scheduler = AsyncIOScheduler(timezone=STOCK_MARKET_TZ)
        for i, t in enumerate(parse_refresh_times(STOCK_REFRESH_TIMES)):
            self.scheduler.add_job(
                self.run_cycle,
                CronTrigger(hour=t["hour"], minute=t["minute"],
                            day_of_week="mon-fri", timezone=STOCK_MARKET_TZ),
                id=f"stock_refresh_{i}",
                name=f"Stock refresh {t['hour']:02d}:{t['minute']:02d} ET",
                max_instances=1,
                # A restart at 14:00 should not immediately fire the 12:00
                # slot's job; APScheduler cron naturally queues the NEXT
                # slot, which is what we want. coalesce so a machine that was
                # off through two slots runs at most one catch-up.
                coalesce=True,
                misfire_grace_time=3600,
            )
        self.scheduler.start()
        self.stats["started_at"] = datetime.now().isoformat()
        self.stats["next_runs"] = [
            job.next_run_time.isoformat()
            for job in self.scheduler.get_jobs() if job.next_run_time
        ]
        logger.info(
            "Stock price scheduler started (times=%s tz=%s, next=%s)",
            STOCK_REFRESH_TIMES, STOCK_MARKET_TZ, self.stats["next_runs"],
        )

    async def stop(self):
        """Stop the scheduler without blocking shutdown indefinitely."""
        if self.scheduler:
            try:
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.scheduler.shutdown),
                    timeout=3.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Stock scheduler shutdown timed out after 3s, forcing")
            except Exception as e:
                logger.warning("Error during stock scheduler shutdown: %s", e)
            self.scheduler = None
            logger.info("Stock price scheduler stopped")

        try:
            await release_scheduler_lock(LOCK_NAME, self._holder)
        except Exception:
            pass


stock_scheduler = StockSchedulerService()
