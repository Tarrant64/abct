"""
Materializer: Computes wallet_daily_balances from existing data sources.

On-chain: Replays engine_events per wallet, prices using engine_price_history.
Off-chain: Extracts V1 snapshot components into per-source daily rows.

Usage:
    from engine.materializer import materializer
    await materializer.materialize_onchain(user_id)
    await materializer.materialize_offchain_from_v1(user_id)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import aiosqlite
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Materializer:
    """Computes wallet_daily_balances rows from V2 engine events and V1 snapshots."""

    async def materialize_onchain(self, user_id: int):
        """Build wallet_daily_balances for all on-chain wallet sources from engine_events.

        For each on-chain wallet source:
        1. Find corresponding account_id(s) in engine_account_subjects
        2. Replay engine_events for those accounts
        3. Build daily running balances per (asset_id)
        4. Price each asset using engine_price_history
        5. Write wallet_daily_balances rows
        """
        from engine import db as engine_db
        from database import get_wallet_sources, upsert_wallet_daily_balances_batch

        sources = await get_wallet_sources(user_id, source_type='on_chain')
        if not sources:
            logger.warning(f"Materializer: No on-chain wallet_sources for user {user_id} — run seed_wallet_sources first")
            return

        # Load all account subjects for this user
        account_subjects = await engine_db.get_account_subjects(user_id)
        logger.info(f"Materializer: {len(sources)} on-chain sources, {len(account_subjects)} account subjects")

        # Map wallet_id -> list of account_ids
        wallet_accounts: Dict[int, List[str]] = {}
        account_chains: Dict[str, str] = {}
        for subj in account_subjects:
            wid = subj['wallet_id']
            if wid not in wallet_accounts:
                wallet_accounts[wid] = []
            wallet_accounts[wid].append(subj['account_id'])
            account_chains[subj['account_id']] = subj['chain']

        # Log wallet_id matching diagnostics
        matched = sum(1 for s in sources if s.get('wallet_id') and s['wallet_id'] in wallet_accounts)
        unmatched = [s['source_key'][:30] for s in sources if not s.get('wallet_id') or s['wallet_id'] not in wallet_accounts]
        logger.info(f"Materializer: {matched}/{len(sources)} sources matched account_subjects"
                     f"{f' (unmatched: {unmatched[:5]})' if unmatched else ''}")

        # Load all events for replay
        all_events = await engine_db.get_events(user_id, limit=500000)
        if not all_events:
            logger.warning(f"Materializer: No engine_events for user {user_id} — run a backfill first")
            return

        logger.info(f"Materializer: Replaying {len(all_events)} engine events")

        # Load token info for decimals
        all_token_info = await engine_db.get_all_token_info()
        token_info_cache = {(t['chain'], t['asset_id']): t for t in all_token_info}

        # Native asset divisors
        native_divisors = {
            "cardano": 1_000_000,
            "bitcoin": 100_000_000,
            "ethereum": 10**18,
            "solana": 1_000_000_000,
            "polygon": 10**18,
            "base": 10**18,
        }

        total_rows = 0

        for source in sources:
            wallet_id = source.get('wallet_id')
            if not wallet_id or wallet_id not in wallet_accounts:
                continue

            source_account_ids = set(wallet_accounts[wallet_id])

            # Filter events for this wallet's accounts
            wallet_events = [
                evt for evt in all_events
                if evt.get('account_id') in source_account_ids
            ]

            if not wallet_events:
                logger.debug(f"Materializer: source {source['id']} ({source['source_key'][:20]}) — 0 events, skipping")
                continue

            logger.info(f"Materializer: source {source['id']} ({source['source_key'][:20]}) — {len(wallet_events)} events")

            # Replay events → build daily running balances
            balances: Dict[tuple, int] = {}  # (chain, asset_id) -> raw_amount
            daily_snapshots: Dict[str, Dict[tuple, int]] = {}
            current_date = None

            for evt in wallet_events:
                if not evt.get('block_time'):
                    continue

                evt_date = datetime.utcfromtimestamp(evt['block_time']).strftime('%Y-%m-%d')

                if evt_date != current_date:
                    if current_date is not None:
                        daily_snapshots[current_date] = dict(balances)
                    current_date = evt_date

                amount = int(evt['amount'])
                key = (evt['chain'], evt['asset_id'])
                if evt['direction'] == 'in':
                    balances[key] = balances.get(key, 0) + amount
                elif evt['direction'] == 'out':
                    balances[key] = balances.get(key, 0) - amount

            # Record final date
            if current_date is not None:
                daily_snapshots[current_date] = dict(balances)

            if not daily_snapshots:
                continue

            # Fill gaps (carry forward)
            sorted_dates = sorted(daily_snapshots.keys())
            first_date = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            last_date = datetime.strptime(sorted_dates[-1], '%Y-%m-%d')

            filled: Dict[str, Dict[tuple, int]] = {}
            current = first_date
            last_snapshot: Dict[tuple, int] = {}
            while current <= last_date:
                d = current.strftime('%Y-%m-%d')
                if d in daily_snapshots:
                    last_snapshot = daily_snapshots[d]
                filled[d] = last_snapshot
                current += timedelta(days=1)

            # Collect price keys for batch loading
            all_price_keys = set()
            for snapshot in filled.values():
                for (chain, asset_id) in snapshot.keys():
                    all_price_keys.add(f"{chain}:{asset_id}")

            # Load prices
            price_cache: Dict[str, Dict[str, float]] = {}
            total_prices_loaded = 0
            for price_key in all_price_keys:
                prices = await engine_db.get_prices(price_key)
                total_prices_loaded += len(prices)
                for p in prices:
                    if p['date'] not in price_cache:
                        price_cache[p['date']] = {}
                    price_cache[p['date']][price_key] = p['price_usd']

            logger.info(f"Materializer: source {source['id']} — {len(all_price_keys)} price keys, "
                         f"{total_prices_loaded} price rows loaded, {len(filled)} dates to fill")

            # Build daily balance rows
            batch_rows = []
            for date_str in sorted(filled.keys()):
                snapshot = filled[date_str]
                date_prices = price_cache.get(date_str, {})

                total_value = 0.0
                assets_detail = {}

                for (chain, asset_id), raw_balance in snapshot.items():
                    if raw_balance <= 0:
                        continue

                    if asset_id == "native":
                        divisor = native_divisors.get(chain, 1)
                    else:
                        tinfo = token_info_cache.get((chain, asset_id))
                        if not tinfo:
                            continue
                        if tinfo.get('is_nft'):
                            price_key = f"{chain}:{asset_id}"
                            nft_price = date_prices.get(price_key, 0.0)
                            if nft_price > 0:
                                total_value += nft_price
                            continue
                        decimals = tinfo.get('decimals', 0) or 0
                        divisor = 10 ** decimals if decimals > 0 else 1

                    human_balance = raw_balance / divisor if divisor > 0 else raw_balance
                    price_key = f"{chain}:{asset_id}"
                    price = date_prices.get(price_key, 0.0)
                    if price <= 0:
                        continue
                    value = human_balance * price
                    total_value += value

                    symbol = asset_id if asset_id == "native" else (
                        token_info_cache.get((chain, asset_id), {}).get('symbol') or asset_id[:16]
                    )
                    assets_detail[f"{chain}:{symbol}"] = {
                        'qty': round(human_balance, 8),
                        'price': round(price, 4),
                        'usd': round(value, 2),
                    }

                batch_rows.append({
                    'user_id': user_id,
                    'source_id': source['id'],
                    'date': date_str,
                    'value_usd': round(total_value, 2),
                    'metadata': json.dumps({'assets': assets_detail}) if assets_detail else None,
                })

            if batch_rows:
                await upsert_wallet_daily_balances_batch(batch_rows)
                total_rows += len(batch_rows)
                logger.info(
                    f"Materializer: Wrote {len(batch_rows)} on-chain rows for source "
                    f"{source['id']} ({source['source_key'][:20]}...)"
                )

        logger.info(f"Materializer: Wrote {total_rows} total on-chain daily balance rows for user {user_id}")

    async def materialize_offchain_from_v1(self, user_id: int):
        """Extract V1 snapshot off-chain components into per-source wallet_daily_balances.

        For each V1 portfolio_snapshot row:
        - exchange_value_usd -> exchange source(s)
        - staking_value_usd -> staking source(s)
        - defi_value_usd -> defi source(s)
        - nft_value_usd -> nft source
        """
        from database import (
            get_wallet_sources, upsert_wallet_daily_balances_batch,
            get_portfolio_history
        )

        # Get V1 snapshots (all history)
        snapshots = await get_portfolio_history(days=3650, user_id=user_id)
        if not snapshots:
            logger.info(f"Materializer: No V1 snapshots for user {user_id}")
            return

        # Get sources by type
        exchange_sources = await get_wallet_sources(user_id, source_type='exchange')
        staking_sources = await get_wallet_sources(user_id, source_type='staking')
        defi_sources = await get_wallet_sources(user_id, source_type='defi')
        nft_sources = await get_wallet_sources(user_id, source_type='nft')

        def sf(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        batch_rows = []

        for s in snapshots:
            date = s.get('snapshot_date')
            if not date:
                continue

            # Exchange: distribute evenly across exchange sources (or use first)
            exchange_usd = sf(s.get('exchange_value_usd'))
            if exchange_usd > 0 and exchange_sources:
                per_exchange = exchange_usd / len(exchange_sources)
                for src in exchange_sources:
                    batch_rows.append({
                        'user_id': user_id,
                        'source_id': src['id'],
                        'date': date,
                        'value_usd': round(per_exchange, 2),
                        'metadata': json.dumps({'source': 'v1_snapshot'}),
                    })

            # Staking: distribute evenly across staking sources
            staking_usd = sf(s.get('staking_value_usd'))
            if staking_usd > 0 and staking_sources:
                per_staking = staking_usd / len(staking_sources)
                for src in staking_sources:
                    batch_rows.append({
                        'user_id': user_id,
                        'source_id': src['id'],
                        'date': date,
                        'value_usd': round(per_staking, 2),
                        'metadata': json.dumps({'source': 'v1_snapshot'}),
                    })

            # DeFi: distribute evenly
            defi_usd = sf(s.get('defi_value_usd'))
            if defi_usd > 0 and defi_sources:
                per_defi = defi_usd / len(defi_sources)
                for src in defi_sources:
                    batch_rows.append({
                        'user_id': user_id,
                        'source_id': src['id'],
                        'date': date,
                        'value_usd': round(per_defi, 2),
                        'metadata': json.dumps({'source': 'v1_snapshot'}),
                    })

            # NFT: single aggregate source
            nft_usd = sf(s.get('nft_value_usd'))
            if nft_usd > 0 and nft_sources:
                batch_rows.append({
                    'user_id': user_id,
                    'source_id': nft_sources[0]['id'],
                    'date': date,
                    'value_usd': round(nft_usd, 2),
                    'metadata': json.dumps({'source': 'v1_snapshot'}),
                })

        if batch_rows:
            await upsert_wallet_daily_balances_batch(batch_rows)
            logger.info(
                f"Materializer: Wrote {len(batch_rows)} off-chain rows from V1 snapshots "
                f"for user {user_id}"
            )
        else:
            logger.info(f"Materializer: No off-chain data to materialize for user {user_id}")

    async def backfill_offchain_gaps(self, user_id: int):
        """Fill gaps in off-chain data by carrying forward last known values.

        For dates where V2 on-chain data exists but no off-chain row:
        - Carry forward the last known off-chain value for each source
        - For dates before earliest V1 snapshot: use earliest known values (marked estimated)
        """
        from database import (
            get_wallet_sources, get_wallet_daily_balances,
            upsert_wallet_daily_balances_batch
        )

        # Get all existing daily balances
        all_balances = await get_wallet_daily_balances(user_id)
        if not all_balances:
            return

        # Find all dates and per-source existing dates
        all_dates = sorted(set(b['date'] for b in all_balances))
        if not all_dates:
            return

        # Get off-chain sources
        offchain_types = ('exchange', 'staking', 'defi', 'nft')
        offchain_sources = await get_wallet_sources(user_id)
        offchain_sources = [s for s in offchain_sources if s['source_type'] in offchain_types]

        if not offchain_sources:
            return

        # Build existing data map: (source_id, date) -> value_usd
        existing = {}
        for b in all_balances:
            existing[(b['source_id'], b['date'])] = b['value_usd']

        batch_rows = []
        for source in offchain_sources:
            sid = source['id']
            last_value = 0.0
            earliest_value = None

            # Find earliest known value for this source
            for date in all_dates:
                if (sid, date) in existing:
                    earliest_value = existing[(sid, date)]
                    break

            # Forward-fill through all dates
            last_value = earliest_value or 0.0
            for date in all_dates:
                if (sid, date) in existing:
                    last_value = existing[(sid, date)]
                else:
                    # Gap: carry forward
                    is_estimated = earliest_value is not None and date < all_dates[0]
                    batch_rows.append({
                        'user_id': user_id,
                        'source_id': sid,
                        'date': date,
                        'value_usd': round(last_value, 2),
                        'metadata': json.dumps({
                            'source': 'gap_fill',
                            'estimated': is_estimated
                        }),
                    })

        if batch_rows:
            await upsert_wallet_daily_balances_batch(batch_rows)
            logger.info(
                f"Materializer: Gap-filled {len(batch_rows)} off-chain rows for user {user_id}"
            )

    async def materialize_onchain_from_v1_balance_history(self, user_id: int):
        """Migrate V1 balance_history on-chain data into wallet_daily_balances.

        Reads the V1 balance_history table (per-wallet, per-date, per-blockchain rows)
        and writes them as on_chain source rows in wallet_daily_balances. This is the
        bridge for when engine_events has no data but V1 collected on-chain history.
        """
        import aiosqlite
        from database import (
            get_wallet_sources, upsert_wallet_daily_balances_batch,
        )

        # Get on-chain wallet_sources
        sources = await get_wallet_sources(user_id, source_type='on_chain')
        if not sources:
            logger.info(f"Materializer: No on-chain wallet_sources for user {user_id} — cannot migrate V1 balance_history")
            return

        # Build wallet_id -> source_id map
        wallet_to_source: Dict[int, int] = {}
        for s in sources:
            wid = s.get('wallet_id')
            if wid:
                wallet_to_source[wid] = s['id']

        if not wallet_to_source:
            logger.warning(f"Materializer: No on-chain sources have wallet_id set for user {user_id}")
            return

        # Read V1 balance_history rows
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT wallet_id, blockchain, balance_date, total_value_usd,
                       native_amount, native_symbol, native_price_usd,
                       native_value_usd, token_value_usd
                FROM balance_history
                WHERE user_id = ? AND total_value_usd > 0
                ORDER BY balance_date ASC
            """, (user_id,))
            v1_rows = [dict(r) for r in await cursor.fetchall()]

        if not v1_rows:
            logger.info(f"Materializer: No V1 balance_history rows for user {user_id}")
            return

        logger.info(f"Materializer: Migrating {len(v1_rows)} V1 balance_history rows for user {user_id}")

        batch_rows = []
        skipped = 0
        for row in v1_rows:
            source_id = wallet_to_source.get(row['wallet_id'])
            if not source_id:
                skipped += 1
                continue

            batch_rows.append({
                'user_id': user_id,
                'source_id': source_id,
                'date': row['balance_date'],
                'value_usd': round(float(row['total_value_usd']), 2),
                'metadata': json.dumps({
                    'source': 'v1_balance_history',
                    'blockchain': row['blockchain'],
                    'native_amount': row.get('native_amount'),
                    'native_symbol': row.get('native_symbol'),
                    'native_price_usd': row.get('native_price_usd'),
                }),
            })

        if batch_rows:
            await upsert_wallet_daily_balances_batch(batch_rows)
            logger.info(
                f"Materializer: Wrote {len(batch_rows)} on-chain rows from V1 balance_history "
                f"for user {user_id} (skipped {skipped} unmapped wallets)"
            )
        else:
            logger.info(f"Materializer: No V1 rows mapped to wallet_sources for user {user_id} "
                         f"(skipped {skipped})")


# Singleton
materializer = Materializer()
