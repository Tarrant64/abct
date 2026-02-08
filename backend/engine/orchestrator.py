"""
Backfill Orchestrator

The top-level coordinator for the V2 ingestion engine.
Manages the full pipeline: expand → index → hydrate → normalize → enrich.

Usage:
    from engine.orchestrator import backfill_orchestrator
    await backfill_orchestrator.initialize()
    backfill_id = await backfill_orchestrator.plan_backfill(user_id, chains, domains)
    await backfill_orchestrator.run_backfill(backfill_id)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from engine.models import (
    ChainId, WorkDomain, WorkStatus, BackfillStatus,
    BackfillRequest, BackfillStatusResponse,
)
from engine import db as engine_db
from engine.providers.registry import ProviderRegistry, create_default_registry
from engine.providers.provider import Provider
from engine.scheduler.scheduler import WorkUnitScheduler

# Stage implementations
from engine.expansion.cardano_expander import CardanoExpander
from engine.expansion.bitcoin_expander import BitcoinExpander
from engine.expansion.evm_expander import EvmExpander
from engine.expansion.solana_expander import SolanaExpander

from engine.indexing.cardano_indexer import CardanoIndexer
from engine.indexing.bitcoin_indexer import BitcoinIndexer
from engine.indexing.evm_indexer import EvmIndexer
from engine.indexing.solana_indexer import SolanaIndexer

from engine.hydration.cardano_hydrator import CardanoHydrator
from engine.hydration.bitcoin_hydrator import BitcoinHydrator
from engine.hydration.evm_hydrator import EvmHydrator
from engine.hydration.solana_hydrator import SolanaHydrator

from engine.normalization.cardano_normalizer import CardanoNormalizer
from engine.normalization.bitcoin_normalizer import BitcoinNormalizer
from engine.normalization.evm_normalizer import EvmNormalizer
from engine.normalization.solana_normalizer import SolanaNormalizer

from engine.enrichment.price_enricher import price_enricher

logger = logging.getLogger(__name__)


class BackfillOrchestrator:
    """Coordinates the full ingestion pipeline."""

    def __init__(self):
        self.registry: Optional[ProviderRegistry] = None
        self.scheduler: Optional[WorkUnitScheduler] = None
        self._running_backfills: Dict[int, asyncio.Task] = {}

        # Stage instances by chain
        self._expanders = {}
        self._indexers = {}
        self._hydrators = {}
        self._normalizers = {}

    async def initialize(self):
        """Set up the registry, scheduler, and stage instances."""
        self.registry = create_default_registry()
        self.scheduler = WorkUnitScheduler(self.registry)

        # Register expanders
        self._expanders = {
            ChainId.CARDANO: CardanoExpander(),
            ChainId.BITCOIN: BitcoinExpander(),
            ChainId.ETHEREUM: EvmExpander(ChainId.ETHEREUM),
            ChainId.POLYGON: EvmExpander(ChainId.POLYGON),
            ChainId.BASE: EvmExpander(ChainId.BASE),
            ChainId.SOLANA: SolanaExpander(),
        }

        # Register indexers
        self._indexers = {
            ChainId.CARDANO: CardanoIndexer(),
            ChainId.BITCOIN: BitcoinIndexer(),
            ChainId.ETHEREUM: EvmIndexer(ChainId.ETHEREUM),
            ChainId.POLYGON: EvmIndexer(ChainId.POLYGON),
            ChainId.BASE: EvmIndexer(ChainId.BASE),
            ChainId.SOLANA: SolanaIndexer(),
        }

        # Register hydrators
        self._hydrators = {
            ChainId.CARDANO: CardanoHydrator(),
            ChainId.BITCOIN: BitcoinHydrator(),
            ChainId.ETHEREUM: EvmHydrator(ChainId.ETHEREUM),
            ChainId.POLYGON: EvmHydrator(ChainId.POLYGON),
            ChainId.BASE: EvmHydrator(ChainId.BASE),
            ChainId.SOLANA: SolanaHydrator(),
        }

        # Register normalizers
        self._normalizers = {
            ChainId.CARDANO: CardanoNormalizer(),
            ChainId.BITCOIN: BitcoinNormalizer(),
            ChainId.ETHEREUM: EvmNormalizer(ChainId.ETHEREUM),
            ChainId.POLYGON: EvmNormalizer(ChainId.POLYGON),
            ChainId.BASE: EvmNormalizer(ChainId.BASE),
            ChainId.SOLANA: SolanaNormalizer(),
        }

        # Register executors with the scheduler
        self.scheduler.register_executor("index", self._execute_index)
        self.scheduler.register_executor("hydrate", self._execute_hydrate)
        self.scheduler.register_executor("normalize", self._execute_normalize)
        self.scheduler.register_executor("enrich_price", self._execute_enrich_price)

        logger.info("Backfill orchestrator initialized")

    async def plan_backfill(self, user_id: int, request: BackfillRequest) -> int:
        """
        Create a backfill plan: expand wallets → generate work units.

        Returns the backfill_id.
        """
        chains = [c.value for c in request.chains]
        domains = [d.value for d in request.domains]

        backfill_id = await engine_db.create_backfill(
            user_id=user_id,
            chains=chains,
            domains=domains,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        logger.info(f"Created backfill {backfill_id} for user {user_id}: "
                     f"chains={chains}, domains={domains}")

        # Stage A: Expand wallets into account subjects
        try:
            from database import get_all_wallets
            wallets = await get_all_wallets(user_id=user_id)

            total_subjects = 0
            for wallet in wallets:
                blockchain = wallet.get('blockchain', '').lower()
                if blockchain not in chains:
                    continue

                address = wallet.get('address', '')
                wallet_id = wallet.get('id', 0)
                chain_id = ChainId(blockchain)

                expander = self._expanders.get(chain_id)
                if not expander:
                    continue

                subjects = await expander.expand(user_id, wallet_id, address)
                for subject in subjects:
                    await engine_db.upsert_account_subject(
                        user_id=subject.user_id,
                        wallet_id=subject.wallet_id,
                        chain=subject.chain.value,
                        account_id=subject.account_id,
                        account_type=subject.account_type.value,
                        parent_account_id=subject.parent_account_id,
                    )
                total_subjects += len(subjects)

            logger.info(f"Backfill {backfill_id}: expanded {total_subjects} account subjects")

            # Generate work units for each subject × domain
            work_units = []
            subjects = await engine_db.get_account_subjects(user_id)
            for subject in subjects:
                if subject['chain'] not in chains:
                    continue

                for domain in domains:
                    # Index work units are per-account
                    if domain == "index":
                        work_units.append({
                            'backfill_id': backfill_id,
                            'user_id': user_id,
                            'chain': subject['chain'],
                            'account_id': subject['account_id'],
                            'domain': domain,
                            'cursor_start': request.start_date,
                            'cursor_end': request.end_date,
                        })
                    # Hydrate/normalize/enrich work units are generated downstream
                    # after indexing completes, based on discovered tx IDs

            await engine_db.create_work_units_batch(work_units)

            await engine_db.update_backfill(
                backfill_id,
                status='running',
                total_work_units=len(work_units),
            )

            logger.info(f"Backfill {backfill_id}: created {len(work_units)} initial work units")

        except Exception as e:
            logger.error(f"Backfill {backfill_id} planning failed: {e}")
            await engine_db.update_backfill(
                backfill_id, status='failed', error_message=str(e)[:500]
            )

        return backfill_id

    async def run_backfill(self, backfill_id: int):
        """Start executing a backfill in the background."""
        backfill = await engine_db.get_backfill(backfill_id)
        if not backfill:
            raise ValueError(f"Backfill {backfill_id} not found")

        if backfill_id in self._running_backfills:
            raise ValueError(f"Backfill {backfill_id} is already running")

        task = asyncio.create_task(self._run_backfill_pipeline(backfill_id, backfill))
        self._running_backfills[backfill_id] = task

    async def _run_backfill_pipeline(self, backfill_id: int, backfill: Dict):
        """Execute the full pipeline for a backfill."""
        try:
            user_id = backfill['user_id']
            chains = backfill['chains']
            domains = backfill['domains']

            # Phase 1: Run index work units
            if "index" in domains:
                logger.info(f"Backfill {backfill_id}: starting INDEX phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=5)

                # After indexing, generate hydrate work units from discovered tx IDs
                if "hydrate" in domains:
                    await self._generate_hydrate_work_units(backfill_id, user_id, chains)

            # Phase 2: Run hydrate work units
            if "hydrate" in domains:
                logger.info(f"Backfill {backfill_id}: starting HYDRATE phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=5)

                # After hydration, generate normalize work units
                if "normalize" in domains:
                    await self._generate_normalize_work_units(backfill_id, user_id, chains)

            # Phase 3: Run normalize work units
            if "normalize" in domains:
                logger.info(f"Backfill {backfill_id}: starting NORMALIZE phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=10)

                # After normalization, generate enrich work units
                if "enrich_price" in domains:
                    await self._generate_enrich_work_units(backfill_id, user_id, chains)

            # Phase 4: Run enrichment work units
            if "enrich_price" in domains:
                logger.info(f"Backfill {backfill_id}: starting ENRICH phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=3)

            # Final status
            stats = await engine_db.get_work_unit_stats(backfill_id)
            total = sum(s.get('total', 0) for s in stats.values())
            done = sum(s.get('done', 0) for s in stats.values())
            failed = sum(s.get('failed', 0) for s in stats.values())

            final_status = 'completed'
            await engine_db.update_backfill(
                backfill_id,
                status=final_status,
                completed_work_units=done,
                failed_work_units=failed,
                progress_pct=100.0 if total == 0 else round(done / total * 100, 1),
            )
            logger.info(f"Backfill {backfill_id} completed: {done}/{total} done, {failed} failed")

        except Exception as e:
            logger.error(f"Backfill {backfill_id} pipeline error: {e}")
            await engine_db.update_backfill(
                backfill_id, status='failed', error_message=str(e)[:500]
            )
        finally:
            self._running_backfills.pop(backfill_id, None)

    async def _generate_hydrate_work_units(self, backfill_id: int, user_id: int, chains: list):
        """Generate hydrate work units from indexed tx IDs."""
        units = []
        for chain in chains:
            tx_ids = await engine_db.get_unhydrated_tx_ids(chain, limit=10000)
            subjects = await engine_db.get_account_subjects(user_id, chain=chain)

            # Get unique accounts that need hydration
            for tx_id in tx_ids:
                units.append({
                    'backfill_id': backfill_id,
                    'user_id': user_id,
                    'chain': chain,
                    'account_id': tx_id,  # For hydrate, account_id holds the tx_id
                    'domain': 'hydrate',
                    'cursor_start': None,
                    'cursor_end': None,
                })

        if units:
            await engine_db.create_work_units_batch(units)
            # Update total count
            backfill = await engine_db.get_backfill(backfill_id)
            if backfill:
                await engine_db.update_backfill(
                    backfill_id,
                    total_work_units=backfill['total_work_units'] + len(units)
                )
            logger.info(f"Backfill {backfill_id}: generated {len(units)} hydrate work units")

    async def _generate_normalize_work_units(self, backfill_id: int, user_id: int, chains: list):
        """Generate normalize work units from hydrated txs."""
        units = []
        for chain in chains:
            subjects = await engine_db.get_account_subjects(user_id, chain=chain)
            for subject in subjects:
                tx_ids = await engine_db.get_tx_ids_for_account(chain, subject['account_id'])
                for tx_id in tx_ids:
                    units.append({
                        'backfill_id': backfill_id,
                        'user_id': user_id,
                        'chain': chain,
                        'account_id': subject['account_id'],
                        'domain': 'normalize',
                        'cursor_start': tx_id,  # tx_id as cursor for normalize
                        'cursor_end': None,
                    })

        if units:
            await engine_db.create_work_units_batch(units)
            backfill = await engine_db.get_backfill(backfill_id)
            if backfill:
                await engine_db.update_backfill(
                    backfill_id,
                    total_work_units=backfill['total_work_units'] + len(units)
                )
            logger.info(f"Backfill {backfill_id}: generated {len(units)} normalize work units")

    async def _generate_enrich_work_units(self, backfill_id: int, user_id: int, chains: list):
        """Generate price enrichment work units from events."""
        units = []
        for chain in chains:
            events = await engine_db.get_events(user_id, chain=chain, limit=10000)
            dates_seen = set()
            for evt in events:
                if evt.get('block_time'):
                    dt = datetime.utcfromtimestamp(evt['block_time'])
                    date_str = dt.strftime('%Y-%m-%d')
                    if date_str not in dates_seen:
                        dates_seen.add(date_str)
                        units.append({
                            'backfill_id': backfill_id,
                            'user_id': user_id,
                            'chain': chain,
                            'account_id': 'native',  # Price enrichment is per-asset
                            'domain': 'enrich_price',
                            'cursor_start': date_str,
                            'cursor_end': date_str,
                        })

        if units:
            await engine_db.create_work_units_batch(units)
            backfill = await engine_db.get_backfill(backfill_id)
            if backfill:
                await engine_db.update_backfill(
                    backfill_id,
                    total_work_units=backfill['total_work_units'] + len(units)
                )
            logger.info(f"Backfill {backfill_id}: generated {len(units)} enrich work units")

    # =========================================================================
    # Stage Executors (called by the scheduler)
    # =========================================================================

    async def _execute_index(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute an indexing work unit."""
        chain = ChainId(work_unit['chain'])
        indexer = self._indexers.get(chain)
        if not indexer:
            return False

        entries = await indexer.index(
            user_id=work_unit['user_id'],
            account_id=work_unit['account_id'],
            cursor_start=work_unit.get('cursor_start'),
            cursor_end=work_unit.get('cursor_end'),
        )

        # Store results
        batch = []
        for entry in entries:
            batch.append({
                'user_id': entry.user_id,
                'chain': entry.chain.value,
                'account_id': entry.account_id,
                'tx_id': entry.tx_id,
                'block_height': entry.block_height,
                'block_time': entry.block_time,
            })
        await engine_db.upsert_tx_index_batch(batch)

        logger.debug(f"Indexed {len(entries)} txs for {work_unit['chain']}:{work_unit['account_id'][:12]}...")
        return True

    async def _execute_hydrate(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute a hydration work unit."""
        chain = ChainId(work_unit['chain'])
        hydrator = self._hydrators.get(chain)
        if not hydrator:
            return False

        tx_id = work_unit['account_id']  # For hydrate, account_id holds the tx_id

        # Check if already hydrated
        existing = await engine_db.get_tx_raw(chain.value, tx_id)
        if existing:
            return True

        raw_data = await hydrator.hydrate(tx_id)
        if raw_data is None:
            return False

        await engine_db.upsert_tx_raw(chain.value, tx_id, raw_data, provider.name)
        return True

    async def _execute_normalize(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute a normalization work unit."""
        chain = ChainId(work_unit['chain'])
        normalizer = self._normalizers.get(chain)
        if not normalizer:
            return False

        tx_id = work_unit.get('cursor_start', '')
        account_id = work_unit['account_id']

        # Get raw transaction data
        raw = await engine_db.get_tx_raw(chain.value, tx_id)
        if not raw:
            return False

        events = await normalizer.normalize(
            user_id=work_unit['user_id'],
            account_id=account_id,
            raw_data=raw['raw_data'],
        )

        # Store events
        batch = []
        for evt in events:
            batch.append({
                'user_id': evt.user_id,
                'chain': evt.chain.value,
                'event_type': evt.event_type.value,
                'tx_id': evt.tx_id,
                'event_index': evt.event_index,
                'account_id': evt.account_id,
                'direction': evt.direction,
                'asset_id': evt.asset_id,
                'amount': evt.amount,
                'counterparty': evt.counterparty,
                'fee': evt.fee,
                'block_height': evt.block_height,
                'block_time': evt.block_time,
                'metadata': evt.metadata,
            })
        await engine_db.upsert_events_batch(batch)
        return True

    async def _execute_enrich_price(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute a price enrichment work unit."""
        chain = work_unit['chain']
        date = work_unit.get('cursor_start', '')

        price = await price_enricher.enrich_date("native", chain, date)
        return price is not None

    # =========================================================================
    # Status & Query APIs
    # =========================================================================

    async def get_status(self, backfill_id: int) -> Optional[BackfillStatusResponse]:
        """Get the current status of a backfill."""
        backfill = await engine_db.get_backfill(backfill_id)
        if not backfill:
            return None

        stats = await engine_db.get_work_unit_stats(backfill_id)
        error_count = sum(s.get('failed', 0) for s in stats.values())

        return BackfillStatusResponse(
            backfill_id=backfill_id,
            status=BackfillStatus(backfill['status']),
            progress_pct=backfill['progress_pct'],
            stages=stats,
            error_count=error_count,
            created_at=backfill.get('created_at'),
            updated_at=backfill.get('updated_at'),
        )

    async def cancel_backfill(self, backfill_id: int):
        """Cancel a running backfill."""
        task = self._running_backfills.get(backfill_id)
        if task and not task.done():
            task.cancel()
            self._running_backfills.pop(backfill_id, None)

        await engine_db.cancel_backfill_work_units(backfill_id)
        await engine_db.update_backfill(backfill_id, status='cancelled')
        logger.info(f"Backfill {backfill_id} cancelled")

    async def get_gaps(self, user_id: int) -> List[Dict]:
        """Analyze coverage gaps in ingested data."""
        from database import get_all_wallets

        gaps = []
        wallets = await get_all_wallets(user_id=user_id)

        for wallet in wallets:
            chain = wallet.get('blockchain', '').lower()
            address = wallet.get('address', '')
            wallet_id = wallet.get('id', 0)

            # Check if we have account subjects
            subjects = await engine_db.get_account_subjects(user_id, chain=chain)
            subject_addrs = {s['account_id'] for s in subjects}

            if address not in subject_addrs:
                # No expansion done yet
                gaps.append({
                    'wallet_id': wallet_id,
                    'chain': chain,
                    'missing_ranges': [{'from': 'never_indexed', 'to': 'now'}],
                })
                continue

            # Check event coverage
            event_count = await engine_db.get_event_count(user_id, chain=chain)
            if event_count == 0:
                gaps.append({
                    'wallet_id': wallet_id,
                    'chain': chain,
                    'missing_ranges': [{'from': 'no_events', 'to': 'now'}],
                })

        return gaps

    async def compute_snapshot(self, user_id: int, at_time: Optional[str] = None) -> Dict:
        """
        Compute portfolio snapshot from canonical events.

        Replays all in/out events to compute running balances,
        then prices them at the given time.
        """
        max_time = None
        if at_time:
            dt = datetime.fromisoformat(at_time)
            max_time = int(dt.timestamp())

        events = await engine_db.get_events(user_id, max_time=max_time, limit=100000)

        # Replay events to compute balances: {(chain, asset_id): balance}
        balances: Dict[tuple, int] = {}
        for evt in events:
            key = (evt['chain'], evt['asset_id'])
            amount = int(evt['amount'])
            if evt['direction'] == 'in':
                balances[key] = balances.get(key, 0) + amount
            elif evt['direction'] == 'out':
                balances[key] = balances.get(key, 0) - amount

        # Build holdings with prices
        date_str = at_time[:10] if at_time else datetime.utcnow().strftime('%Y-%m-%d')
        price_map = await engine_db.get_prices_for_date(date_str)

        holdings = []
        total_value = 0.0
        for (chain, asset_id), balance in balances.items():
            if balance <= 0:
                continue

            price_key = f"{chain}:{asset_id}"
            price = price_map.get(price_key, 0.0)

            # Apply decimals for native assets
            divisors = {
                "cardano": 1_000_000,      # lovelace → ADA
                "bitcoin": 100_000_000,     # satoshi → BTC
                "ethereum": 10**18,         # wei → ETH
                "solana": 1_000_000_000,    # lamports → SOL
                "polygon": 10**18,          # wei → MATIC
                "base": 10**18,             # wei → ETH
            }
            divisor = divisors.get(chain, 1) if asset_id == "native" else 1
            human_amount = balance / divisor

            value = human_amount * price
            total_value += value

            holdings.append({
                'chain': chain,
                'asset': asset_id,
                'amount': str(human_amount),
                'value_usd': round(value, 2) if price > 0 else None,
            })

        return {
            'at_time': at_time or datetime.utcnow().isoformat(),
            'total_value_usd': round(total_value, 2),
            'holdings': holdings,
        }

    async def get_history_data(self, user_id: int, range_str: str = "1y") -> Dict:
        """
        Generate history data in the same format as /balance-history/data.

        Replays all events from genesis to compute accurate running balances,
        fills daily gaps, and prices each day using cached engine_price_history.
        """
        from datetime import timedelta

        range_map = {
            '24h': 1, '1w': 7, '2w': 14, '1m': 30, '3m': 90,
            '6m': 180, '1y': 365, '2y': 730, 'all': 3650,
        }
        days = range_map.get(range_str, 365)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        end_ts = int(end_date.timestamp())
        start_date_str = start_date.strftime('%Y-%m-%d')

        # Replay ALL events from genesis for accurate running balances
        all_events = await engine_db.get_events(user_id, max_time=end_ts, limit=500000)

        if not all_events:
            return {'data': [], 'coverage': {'oldest_date': None, 'newest_date': None, 'total_days': 0}}

        # Build running balance per (chain, asset_id), snapshot at date boundaries
        balances: Dict[tuple, int] = {}
        daily_snapshots: Dict[str, Dict[tuple, int]] = {}
        current_date = None

        for evt in all_events:
            if not evt.get('block_time'):
                continue

            evt_date = datetime.utcfromtimestamp(evt['block_time']).strftime('%Y-%m-%d')

            # When date changes, record end-of-previous-day snapshot
            if evt_date != current_date:
                if current_date is not None and current_date >= start_date_str:
                    daily_snapshots[current_date] = dict(balances)
                current_date = evt_date

            amount = int(evt['amount'])
            key = (evt['chain'], evt['asset_id'])
            if evt['direction'] == 'in':
                balances[key] = balances.get(key, 0) + amount
            elif evt['direction'] == 'out':
                balances[key] = balances.get(key, 0) - amount

        # Record final date's snapshot
        if current_date and current_date >= start_date_str:
            daily_snapshots[current_date] = dict(balances)

        if not daily_snapshots:
            return {'data': [], 'coverage': {'oldest_date': None, 'newest_date': None, 'total_days': 0}}

        # Fill daily gaps: carry forward balances for days without transactions
        sorted_dates = sorted(daily_snapshots.keys())
        first_date = datetime.strptime(max(sorted_dates[0], start_date_str), '%Y-%m-%d')
        last_date = min(datetime.strptime(sorted_dates[-1], '%Y-%m-%d'), end_date)

        filled: Dict[str, Dict[tuple, int]] = {}
        current = first_date
        last_snapshot: Dict[tuple, int] = {}
        while current <= last_date:
            d = current.strftime('%Y-%m-%d')
            if d in daily_snapshots:
                last_snapshot = daily_snapshots[d]
            filled[d] = last_snapshot
            current += timedelta(days=1)

        # Pre-load all prices by chain (6 queries max, not 730)
        divisors = {
            "cardano": 1_000_000,
            "bitcoin": 100_000_000,
            "ethereum": 10**18,
            "solana": 1_000_000_000,
            "polygon": 10**18,
            "base": 10**18,
        }
        chains_in_data = set()
        for snapshot in filled.values():
            for (chain, asset_id) in snapshot.keys():
                if asset_id == "native":
                    chains_in_data.add(chain)

        price_cache: Dict[str, Dict[str, float]] = {}  # {date: {price_key: price}}
        for chain in chains_in_data:
            price_key = f"{chain}:native"
            prices = await engine_db.get_prices(price_key)
            for p in prices:
                if p['date'] not in price_cache:
                    price_cache[p['date']] = {}
                price_cache[p['date']][price_key] = p['price_usd']

        # Build output
        data = []
        for date_str in sorted(filled.keys()):
            snapshot = filled[date_str]
            date_prices = price_cache.get(date_str, {})

            total_value = 0.0
            chain_values = {}
            for (chain, asset_id), raw_balance in snapshot.items():
                if raw_balance <= 0 or asset_id != "native":
                    continue
                divisor = divisors.get(chain, 1)
                human_balance = raw_balance / divisor
                price_key = f"{chain}:{asset_id}"
                price = date_prices.get(price_key, 0.0)
                value = human_balance * price
                total_value += value
                chain_values[chain] = round(value, 2)

            data.append({
                'date': date_str,
                'value': round(total_value, 2),
                'chains': chain_values,
            })

        dates = [d['date'] for d in data]
        return {
            'data': data,
            'coverage': {
                'oldest_date': min(dates) if dates else None,
                'newest_date': max(dates) if dates else None,
                'total_days': len(dates),
            }
        }


# Singleton instance
backfill_orchestrator = BackfillOrchestrator()
