"""
Wallet Balance Background Sync (ABCT-BGSYNC-20260919)

Keeps on-chain wallet quantities current without a user pressing refresh --
the actual fix for the original user complaint (ABCT-BACKEND-QTYCACHE-20260918:
quantities looked frozen because nothing ever refreshed the underlying
balances/native_assets rows on a schedule; ABCT-BALANCE-ATOMIC-20260919 made
the write path safe to run continuously; this is what actually runs it).

Design, mirrors the existing NFTSchedulerService pattern (services/nft_scheduler.py)
where it makes sense, and diverges where the two jobs' constraints differ:

- One AsyncIOScheduler job on a 1-minute IntervalTrigger. Each tick handles
  exactly one "bucket": wallets where (wallet_id % WALLET_BGSYNC_BUCKET_COUNT)
  equals the current bucket. With BUCKET_COUNT=60 this staggers ~1/60th of
  all wallets per minute, so every wallet is due about once per hour, and a
  cycle never has to touch "every wallet" at once.
- Wallets whose balances row was updated more recently than
  WALLET_BGSYNC_SKIP_RECENT_MINUTES are skipped -- avoids redoing work a user
  (or a prior cycle) already did.
- Within a cycle, wallets are refreshed strictly ONE AT A TIME with a fixed
  minimum delay between them (WALLET_BGSYNC_DISPATCH_DELAY_SECONDS). This is
  a hard, provider-latency-independent ceiling on how often this scheduler
  *starts* a new wallet's refresh -- see the rate-math in the task report.
  It is deliberately not concurrent: unlike the manual bulk-refresh endpoint
  (routers/wallets.py's Semaphore(5)), this job runs unattended and
  continuously, so it trades cycle wall-clock time for a much simpler,
  provable rate guarantee.
- A per-wallet failure is caught, logged, and does not stop the cycle.
- Cross-process advisory lock (database.try_acquire_scheduler_lock): guards
  against duplicate concurrent cycles if this ever runs under more than one
  worker process sharing the DB file. The app currently ships with
  `--workers 1` (abct-docker/supervisord.conf), so this is not an active
  scenario today, but the lock costs nothing when there's only one worker
  and means nobody has to remember this constraint if that ever changes.
  AsyncIOScheduler's own max_instances=1 additionally guards against a slow
  cycle overlapping the next one *within* one process.
- Kill switch: WALLET_BGSYNC_ENABLED (config.py), defaults to False. Read
  once at process start (same model as NFT_SCHEDULER_ENABLED) -- flipping it
  requires a container restart, which is an acceptable trade for keeping
  this simple; there is no admin-API live-toggle for this job.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import (
    WALLET_BGSYNC_ENABLED,
    WALLET_BGSYNC_BUCKET_COUNT,
    WALLET_BGSYNC_SKIP_RECENT_MINUTES,
    WALLET_BGSYNC_DISPATCH_DELAY_SECONDS,
    WALLET_BGSYNC_LOCK_TTL_MINUTES,
)
from database import (
    get_wallets_due_for_bgsync,
    count_wallets_in_bucket,
    try_acquire_scheduler_lock,
    release_scheduler_lock,
)

logger = logging.getLogger(__name__)

LOCK_NAME = "wallet_balance_bgsync"


class WalletBalanceSchedulerService:
    """Background service that periodically refreshes on-chain wallet balances."""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.enabled = WALLET_BGSYNC_ENABLED
        # Unique per process instance -- identifies this holder in the
        # cross-process lock table. Not just os.getpid(): a fast process
        # restart could reuse a PID before the previous holder's lease
        # expires, and we want a genuinely fresh identity every start.
        self._holder = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.stats = {
            "started_at": None,
            "last_cycle_at": None,
            "last_cycle_duration_s": None,
            "total_cycles": 0,
            "lock_skipped_cycles": 0,
            "last_attempted": 0,
            "last_succeeded": 0,
            "last_skipped_recent": 0,
            "last_failed": 0,
            "last_error": None,
        }

    async def run_cycle(self):
        """One scheduler tick: refresh the current minute's wallet bucket."""
        cycle_started = datetime.now()

        got_lock = await try_acquire_scheduler_lock(
            LOCK_NAME, self._holder, ttl_seconds=WALLET_BGSYNC_LOCK_TTL_MINUTES * 60
        )
        if not got_lock:
            # Another process already holds the lock for this window --
            # this is the expected steady state whenever this ever runs
            # under more than one worker. Not an error.
            self.stats["lock_skipped_cycles"] += 1
            logger.debug("wallet_balance_bgsync: lock held elsewhere, skipping this tick")
            return

        attempted = 0
        succeeded = 0
        failed = 0
        skipped_recent = 0

        try:
            bucket = cycle_started.minute % WALLET_BGSYNC_BUCKET_COUNT
            total_in_bucket, wallets = await asyncio.gather(
                count_wallets_in_bucket(bucket, WALLET_BGSYNC_BUCKET_COUNT),
                get_wallets_due_for_bgsync(
                    bucket=bucket,
                    bucket_count=WALLET_BGSYNC_BUCKET_COUNT,
                    skip_recent_minutes=WALLET_BGSYNC_SKIP_RECENT_MINUTES,
                ),
            )
            skipped_recent = total_in_bucket - len(wallets)

            # Lazy import: routers.wallets is a heavy module (imports every
            # chain service) and importing it eagerly at module load time
            # here would risk import-order issues from main.py; this mirrors
            # how this codebase already does cross-router calls elsewhere
            # (e.g. routers/portfolio.py importing from routers/exchanges).
            from routers.wallets import _refresh_wallet_balance

            for i, wallet in enumerate(wallets):
                attempted += 1
                try:
                    result = await _refresh_wallet_balance(wallet)
                    if result and result.get("success"):
                        succeeded += 1
                    else:
                        failed += 1
                        error_type = (result or {}).get("error_type", "UnknownError")
                        error_msg = (result or {}).get("error", "no result")
                        logger.warning(
                            "wallet_balance_bgsync: wallet %s refresh failed: %s: %s",
                            wallet.get("id"), error_type, error_msg,
                        )
                except Exception as e:
                    # Belt-and-suspenders: _refresh_wallet_balance already
                    # catches its own exceptions internally and returns
                    # {'success': False, ...}, but this loop must survive
                    # even if that ever changes or a malformed wallet row
                    # raises before entering that try block.
                    failed += 1
                    logger.warning(
                        "wallet_balance_bgsync: wallet %s raised during refresh: %s: %s",
                        wallet.get("id"), type(e).__name__, e,
                    )

                # Hard rate ceiling: wait before starting the NEXT wallet,
                # not after the last one.
                if i < len(wallets) - 1:
                    await asyncio.sleep(WALLET_BGSYNC_DISPATCH_DELAY_SECONDS)

            self.stats["last_error"] = None

        except Exception as e:
            logger.error("wallet_balance_bgsync: cycle error: %s", e)
            self.stats["last_error"] = str(e)

        finally:
            await release_scheduler_lock(LOCK_NAME, self._holder)

            duration_s = (datetime.now() - cycle_started).total_seconds()
            self.stats["total_cycles"] += 1
            self.stats["last_cycle_at"] = cycle_started.isoformat()
            self.stats["last_cycle_duration_s"] = round(duration_s, 2)
            self.stats["last_attempted"] = attempted
            self.stats["last_succeeded"] = succeeded
            self.stats["last_skipped_recent"] = skipped_recent
            self.stats["last_failed"] = failed

            # One summary line per cycle -- not per-wallet -- so the user
            # can tell from logs whether this is working.
            logger.info(
                "wallet_balance_bgsync: cycle done bucket=%s attempted=%d succeeded=%d "
                "skipped_recent=%d failed=%d duration=%.2fs",
                cycle_started.minute % WALLET_BGSYNC_BUCKET_COUNT,
                attempted, succeeded, skipped_recent, failed, duration_s,
            )

    async def start(self):
        """Start the background scheduler, honoring the WALLET_BGSYNC_ENABLED kill switch."""
        if not self.enabled:
            logger.info(
                "Wallet balance background sync disabled "
                "(set WALLET_BGSYNC_ENABLED=true to enable)"
            )
            return

        if self.scheduler:
            logger.warning("Wallet balance scheduler already running")
            return

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.run_cycle,
            IntervalTrigger(minutes=1),
            id="wallet_balance_bgsync",
            name="Wallet Balance Background Sync",
            max_instances=1,  # in-process overlap guard; the DB lock covers cross-process
            # Align the first run to the next whole-minute boundary rather
            # than firing immediately on startup -- avoids doing any sync
            # work in the first moments after a container boots/restarts.
            next_run_time=self._next_minute_boundary(),
        )
        self.scheduler.start()
        self.stats["started_at"] = datetime.now().isoformat()
        logger.info(
            "Wallet balance background sync started (bucket_count=%d, "
            "skip_recent_minutes=%d, dispatch_delay=%.2fs)",
            WALLET_BGSYNC_BUCKET_COUNT, WALLET_BGSYNC_SKIP_RECENT_MINUTES,
            WALLET_BGSYNC_DISPATCH_DELAY_SECONDS,
        )

    @staticmethod
    def _next_minute_boundary() -> datetime:
        now = datetime.now()
        return now.replace(second=0, microsecond=0) + timedelta(minutes=1)

    async def stop(self):
        """Stop the background scheduler without blocking shutdown indefinitely."""
        if self.scheduler:
            try:
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.scheduler.shutdown),
                    timeout=3.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Wallet balance scheduler shutdown timed out after 3s, forcing")
            except Exception as e:
                logger.warning("Error during wallet balance scheduler shutdown: %s", e)
            self.scheduler = None
            logger.info("Wallet balance background sync stopped")

        # Best-effort: release the lock if we're still holding it (e.g. a
        # cycle was interrupted mid-flight). Harmless no-op otherwise.
        try:
            await release_scheduler_lock(LOCK_NAME, self._holder)
        except Exception:
            pass


wallet_balance_scheduler = WalletBalanceSchedulerService()
