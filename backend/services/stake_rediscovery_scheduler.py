"""
Cardano Stake-Key Address Rediscovery (ABCT-STAKE-REDISCOVERY-20260919)

Root-cause fix for the 2026-09-19 "vault" incident: ABCT tracks a fixed
list of manually-registered payment addresses, but a Cardano hardware
wallet's account is really a stake key with an open-ended, growing set of
derived payment addresses. The existing discovery flow
(routers/wallets.py's /discover + /add-multiple, ~lines 1881-2010) only
ever runs once, at add-time, on explicit user action -- nothing re-checks
for addresses the wallet derives afterward. The vault's stake key had 11
addresses on-chain; ABCT had registered 9; the missing ~20,514 ADA sat in
the 2 it never knew about.

This does not reimplement that discovery logic -- it reuses the same
primitives (cardano_service.get_addresses_from_stake,
cardano_service.get_stake_address, database.save_wallet,
routers.wallets._refresh_wallet_balance) on a daily schedule, per stake key
the user has ALREADY registered.

HARD BOUNDARY: this only ever discovers new payment addresses under stake
keys derived from a user's own already-registered wallets. It never
accepts a stake key as external input and never queries a stake key that
didn't come from resolving one of that same user's own wallet addresses --
there is no code path here that could touch another user's data or reach
out to an unregistered account.

Design mirrors services/wallet_balance_scheduler.py where it makes sense:
- AsyncIOScheduler, one job, IntervalTrigger -- but daily (see config), not
  every minute, since new-address-derivation is a low-frequency event.
- No bucket/modulo staggering: at a daily cadence there is no benefit to
  spreading work across sub-intervals the way the balance sync spreads
  across 60 one-minute ticks. The rate discipline instead comes entirely
  from strict sequential processing with a fixed per-item delay -- see the
  rate-math in the task report.
- SQLite-backed cross-process advisory lock (database.try_acquire_scheduler_lock),
  for the same reason the balance sync has one: the app ships with
  --workers 1 today, but the guard costs nothing and removes a future
  landmine if that ever changes.
- Kill switch (STAKE_REDISCOVERY_ENABLED), default off.
- Per-wallet/per-stake-key try/except -- one bad address or provider
  hiccup does not stop the cycle or skip the rest of the user's wallets.
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
    STAKE_REDISCOVERY_ENABLED,
    STAKE_REDISCOVERY_INTERVAL_HOURS,
    STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS,
    STAKE_REDISCOVERY_LOCK_TTL_MINUTES,
)
from database import (
    get_all_cardano_wallets,
    get_wallet_by_address,
    save_wallet,
    record_stake_rediscovery_addition,
    try_acquire_scheduler_lock,
    release_scheduler_lock,
)

logger = logging.getLogger(__name__)

LOCK_NAME = "stake_rediscovery"


class StakeRediscoveryService:
    """Background service that periodically re-runs stake-key address
    discovery for every already-registered Cardano wallet."""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.enabled = STAKE_REDISCOVERY_ENABLED
        self._holder = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.stats = {
            "started_at": None,
            "last_cycle_at": None,
            "last_cycle_duration_s": None,
            "total_cycles": 0,
            "lock_skipped_cycles": 0,
            "last_wallets_checked": 0,
            "last_stake_keys_checked": 0,
            "last_addresses_found": 0,
            "last_addresses_added": 0,
            "last_failed": 0,
            "last_error": None,
        }

    async def run_cycle(self):
        """One full pass: resolve every registered Cardano wallet's stake
        key, then check each distinct stake key for addresses ABCT doesn't
        know about yet, auto-adding any with on-chain history."""
        cycle_started = datetime.now()

        got_lock = await try_acquire_scheduler_lock(
            LOCK_NAME, self._holder, ttl_seconds=STAKE_REDISCOVERY_LOCK_TTL_MINUTES * 60
        )
        if not got_lock:
            self.stats["lock_skipped_cycles"] += 1
            logger.debug("stake_rediscovery: lock held elsewhere, skipping this tick")
            return

        wallets_checked = 0
        stake_keys_checked = 0
        addresses_found = 0
        addresses_added = 0
        failed = 0

        try:
            # Lazy imports for the same reason wallet_balance_scheduler.py
            # uses them: avoid import-order issues from main.py, and mirror
            # this codebase's existing cross-router-call pattern.
            from services.cardano import cardano_service
            from routers.wallets import _refresh_wallet_balance

            wallets = await get_all_cardano_wallets()

            # Phase 1: resolve each wallet's stake key, one at a time, and
            # group already-known addresses under it. This is read-only
            # bookkeeping -- no new wallets are added in this phase.
            known_by_key = {}  # (user_id, stake_address) -> set of known addresses
            key_by_wallet_user = {}  # dedup: (user_id, stake_address) seen at least once

            for i, wallet in enumerate(wallets):
                wallets_checked += 1
                address = wallet["address"]
                user_id = wallet["user_id"]
                try:
                    if address.startswith("stake1"):
                        stake_address = address
                    else:
                        stake_address = await cardano_service.get_stake_address(address)

                    if stake_address:
                        group_key = (user_id, stake_address)
                        known_by_key.setdefault(group_key, set()).add(address)
                        key_by_wallet_user[group_key] = True
                    # else: enterprise address with no stake component --
                    # nothing to group, not an error.
                except Exception as e:
                    failed += 1
                    logger.warning(
                        "stake_rediscovery: stake resolution failed for wallet %s: %s: %s",
                        wallet.get("id"), type(e).__name__, e,
                    )

                if i < len(wallets) - 1:
                    await asyncio.sleep(STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS)

            # Phase 2: for each distinct (user, stake key), check for
            # addresses under that key ABCT doesn't already know about.
            group_keys = list(key_by_wallet_user.keys())
            for i, (user_id, stake_address) in enumerate(group_keys):
                stake_keys_checked += 1
                try:
                    onchain_addresses = await cardano_service.get_addresses_from_stake(stake_address)
                    if onchain_addresses:
                        known = known_by_key.get((user_id, stake_address), set())
                        new_addresses = [a for a in onchain_addresses if a not in known]

                        for new_addr in new_addresses:
                            addresses_found += 1
                            try:
                                # Belt-and-suspenders idempotency check --
                                # save_wallet() itself is also an upsert, but
                                # this avoids an unnecessary get_address_info
                                # call (and a duplicate audit row) on a
                                # wallet already added by an earlier cycle
                                # or a concurrent user action.
                                already = await get_wallet_by_address(
                                    new_addr, "cardano", user_id=user_id
                                )
                                if already:
                                    continue

                                info = await cardano_service.get_address_info(new_addr)
                                has_history = bool(info) and (
                                    float(info.get("balance_ada", 0) or 0) > 0
                                    or len(info.get("native_assets", []) or []) > 0
                                )
                                if not has_history:
                                    continue

                                await save_wallet(
                                    new_addr, "cardano",
                                    label=f"Discovered ({stake_address[:12]}...)",
                                    user_id=user_id,
                                    is_auto_label=True,
                                )
                                saved = await get_wallet_by_address(
                                    new_addr, "cardano", user_id=user_id
                                )
                                if saved:
                                    try:
                                        await _refresh_wallet_balance(saved)
                                    except Exception as e:
                                        logger.warning(
                                            "stake_rediscovery: initial refresh failed for "
                                            "newly discovered wallet %s: %s", saved.get("id"), e,
                                        )
                                    await record_stake_rediscovery_addition(
                                        user_id, stake_address, new_addr, saved.get("id")
                                    )
                                addresses_added += 1
                                logger.info(
                                    "stake_rediscovery: added new address %s under stake key "
                                    "%s... for user %s",
                                    new_addr, stake_address[:12], user_id,
                                )
                            except Exception as e:
                                failed += 1
                                logger.warning(
                                    "stake_rediscovery: failed to process discovered address "
                                    "%s under %s...: %s: %s",
                                    new_addr, stake_address[:12], type(e).__name__, e,
                                )
                except Exception as e:
                    failed += 1
                    logger.warning(
                        "stake_rediscovery: address listing failed for stake key %s...: %s: %s",
                        stake_address[:12], type(e).__name__, e,
                    )

                if i < len(group_keys) - 1:
                    await asyncio.sleep(STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS)

            self.stats["last_error"] = None

        except Exception as e:
            logger.error("stake_rediscovery: cycle error: %s", e)
            self.stats["last_error"] = str(e)

        finally:
            await release_scheduler_lock(LOCK_NAME, self._holder)

            duration_s = (datetime.now() - cycle_started).total_seconds()
            self.stats["total_cycles"] += 1
            self.stats["last_cycle_at"] = cycle_started.isoformat()
            self.stats["last_cycle_duration_s"] = round(duration_s, 2)
            self.stats["last_wallets_checked"] = wallets_checked
            self.stats["last_stake_keys_checked"] = stake_keys_checked
            self.stats["last_addresses_found"] = addresses_found
            self.stats["last_addresses_added"] = addresses_added
            self.stats["last_failed"] = failed

            logger.info(
                "stake_rediscovery: cycle done wallets_checked=%d stake_keys_checked=%d "
                "addresses_found=%d addresses_added=%d failed=%d duration=%.2fs",
                wallets_checked, stake_keys_checked, addresses_found, addresses_added,
                failed, duration_s,
            )

    async def start(self):
        """Start the background scheduler, honoring the STAKE_REDISCOVERY_ENABLED kill switch."""
        if not self.enabled:
            logger.info(
                "Stake-key rediscovery disabled "
                "(set STAKE_REDISCOVERY_ENABLED=true to enable)"
            )
            return

        if self.scheduler:
            logger.warning("Stake rediscovery scheduler already running")
            return

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.run_cycle,
            IntervalTrigger(hours=STAKE_REDISCOVERY_INTERVAL_HOURS),
            id="stake_rediscovery",
            name="Cardano Stake-Key Address Rediscovery",
            max_instances=1,
            # Same reasoning as the balance sync: don't fire immediately on
            # boot/restart, wait for the first full interval.
            next_run_time=datetime.now() + timedelta(hours=STAKE_REDISCOVERY_INTERVAL_HOURS),
        )
        self.scheduler.start()
        self.stats["started_at"] = datetime.now().isoformat()
        logger.info(
            "Stake-key rediscovery started (interval=%dh, dispatch_delay=%.2fs)",
            STAKE_REDISCOVERY_INTERVAL_HOURS, STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS,
        )

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
                logger.warning("Stake rediscovery scheduler shutdown timed out after 3s, forcing")
            except Exception as e:
                logger.warning("Error during stake rediscovery scheduler shutdown: %s", e)
            self.scheduler = None
            logger.info("Stake-key rediscovery stopped")

        try:
            await release_scheduler_lock(LOCK_NAME, self._holder)
        except Exception:
            pass


stake_rediscovery_service = StakeRediscoveryService()
