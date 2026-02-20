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
from engine.indexing.alchemy_evm_indexer import AlchemyEvmIndexer
from engine.indexing.ankr_evm_indexer import AnkrEvmIndexer
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


async def _syslog(level: str, msg: str, exc: Exception = None, **extra):
    """Write to the system logs page (LoggingService)."""
    try:
        from services.logging_service import get_logging_service
        svc = get_logging_service()
        if level == "error":
            await svc.error("engine", msg, exc_info=exc, **extra)
        elif level == "warning":
            await svc.warning("engine", msg, exc_info=exc, **extra)
        elif level == "info":
            await svc.info("engine", msg, **extra)
        else:
            await svc.debug("engine", msg, **extra)
    except Exception:
        pass


class BackfillOrchestrator:
    """Coordinates the full ingestion pipeline."""

    def __init__(self):
        self.registry: Optional[ProviderRegistry] = None
        self.scheduler: Optional[WorkUnitScheduler] = None
        self._running_backfills: Dict[int, asyncio.Task] = {}
        self._active_run_ids: Dict[int, int] = {}  # backfill_id -> run_id
        self._auto_collect_tasks: Dict[int, asyncio.Task] = {}  # user_id -> task

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

        # Register indexers (keyed by provider name for multi-provider dispatch)
        self._indexers = {
            "blockfrost": {ChainId.CARDANO: CardanoIndexer()},
            "blockstream": {ChainId.BITCOIN: BitcoinIndexer()},
            "etherscan": {
                ChainId.ETHEREUM: EvmIndexer(ChainId.ETHEREUM),
                ChainId.POLYGON: EvmIndexer(ChainId.POLYGON),
                ChainId.BASE: EvmIndexer(ChainId.BASE),
            },
            "alchemy": {
                ChainId.ETHEREUM: AlchemyEvmIndexer(ChainId.ETHEREUM),
                ChainId.POLYGON: AlchemyEvmIndexer(ChainId.POLYGON),
                ChainId.BASE: AlchemyEvmIndexer(ChainId.BASE),
            },
            "ankr": {
                ChainId.ETHEREUM: AnkrEvmIndexer(ChainId.ETHEREUM),
                ChainId.POLYGON: AnkrEvmIndexer(ChainId.POLYGON),
                ChainId.BASE: AnkrEvmIndexer(ChainId.BASE),
            },
            "helius": {ChainId.SOLANA: SolanaIndexer()},
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
        Create a backfill plan with resume/checkpoint logic.

        1. If a backfill is already running, return its ID.
        2. If a failed/cancelled backfill has pending work, resume it.
        3. Otherwise create a new (incremental) backfill.

        Returns the backfill_id.
        """
        chains = [c.value for c in request.chains]
        domains = [d.value for d in request.domains]

        # 1. Already running? Return existing backfill ID
        running = await engine_db.get_latest_backfill_by_status(user_id, ['planning', 'running'])
        if running:
            logger.info(f"Backfill {running['id']} already running for user {user_id}, reusing")
            return running['id']

        # 2. Failed/cancelled with pending work? Resume it
        resumable = await engine_db.get_latest_backfill_by_status(user_id, ['failed', 'cancelled'])
        if resumable:
            pending = await engine_db.count_pending_work_units(resumable['id'])
            if pending > 0:
                requeued = await engine_db.requeue_failed_work_units(resumable['id'])
                await engine_db.update_backfill(resumable['id'], status='running')
                logger.info(f"Resuming backfill {resumable['id']}: {pending} pending, {requeued} requeued")
                return resumable['id']

        # 3. Create new backfill (incremental if prior completed backfill exists)
        has_prior = await engine_db.get_latest_backfill_by_status(user_id, ['completed'])

        backfill_id = await engine_db.create_backfill(
            user_id=user_id,
            chains=chains,
            domains=domains,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        logger.info(f"Created backfill {backfill_id} for user {user_id}: "
                     f"chains={chains}, domains={domains}, incremental={has_prior is not None}")

        # Stage A: Expand wallets into account subjects
        try:
            from database import get_all_wallets
            wallets = await get_all_wallets(user_id=user_id)

            # Filter by wallet_ids if specified
            if request.wallet_ids:
                wallets = [w for w in wallets if w.get('id') in request.wallet_ids]

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
                        # Incremental: use latest indexed block_time as cursor_start
                        cursor_start = request.start_date
                        if has_prior:
                            latest_time = await engine_db.get_latest_indexed_block_time(
                                user_id, subject['chain'], subject['account_id']
                            )
                            if latest_time:
                                cursor_start = datetime.utcfromtimestamp(latest_time).isoformat()

                        work_units.append({
                            'backfill_id': backfill_id,
                            'user_id': user_id,
                            'chain': subject['chain'],
                            'account_id': subject['account_id'],
                            'domain': domain,
                            'cursor_start': cursor_start,
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
            await _syslog("error", f"Backfill {backfill_id} planning failed: {e}", exc=e)
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
        run_id = self._active_run_ids.get(backfill_id)
        try:
            user_id = backfill['user_id']
            chains = backfill['chains']
            domains = backfill['domains']

            # Phase 1: Run index work units
            if "index" in domains:
                await _syslog("info", f"Backfill {backfill_id}: starting INDEX phase (chains={chains})")
                logger.info(f"Backfill {backfill_id}: starting INDEX phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=5)

                # Report index results
                idx_stats = await engine_db.get_work_unit_stats(backfill_id)
                idx_info = idx_stats.get('index', {})
                await _syslog("info", f"Backfill {backfill_id}: INDEX done — "
                              f"{idx_info.get('done', 0)} ok, {idx_info.get('failed', 0)} failed")

                # After indexing, generate hydrate work units from discovered tx IDs
                if "hydrate" in domains:
                    await self._generate_hydrate_work_units(backfill_id, user_id, chains)

            # Phase 2: Run hydrate work units
            if "hydrate" in domains:
                await _syslog("info", f"Backfill {backfill_id}: starting HYDRATE phase")
                logger.info(f"Backfill {backfill_id}: starting HYDRATE phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=5)

                hyd_stats = await engine_db.get_work_unit_stats(backfill_id)
                hyd_info = hyd_stats.get('hydrate', {})
                await _syslog("info", f"Backfill {backfill_id}: HYDRATE done — "
                              f"{hyd_info.get('done', 0)} ok, {hyd_info.get('failed', 0)} failed")

                # After hydration, generate normalize work units
                if "normalize" in domains:
                    await self._generate_normalize_work_units(backfill_id, user_id, chains)

            # Phase 3: Run normalize work units
            if "normalize" in domains:
                await _syslog("info", f"Backfill {backfill_id}: starting NORMALIZE phase")
                logger.info(f"Backfill {backfill_id}: starting NORMALIZE phase")
                await self.scheduler.run_backfill(backfill_id, max_concurrent=10)

                norm_stats = await engine_db.get_work_unit_stats(backfill_id)
                norm_info = norm_stats.get('normalize', {})
                await _syslog("info", f"Backfill {backfill_id}: NORMALIZE done — "
                              f"{norm_info.get('done', 0)} ok, {norm_info.get('failed', 0)} failed")

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

            # Auto-materialize into wallet_daily_balances
            try:
                from engine.materializer import materializer
                logger.info(f"Backfill {backfill_id}: auto-materializing to wallet_daily_balances...")
                await materializer.materialize_onchain(user_id)
                logger.info(f"Backfill {backfill_id}: materialization complete")
            except Exception as e:
                logger.warning(f"Backfill {backfill_id}: auto-materialize failed: {e}")

            # Count total events for summary
            event_count = await engine_db.get_event_count(user_id)

            final_status = 'completed'
            await engine_db.update_backfill(
                backfill_id,
                status=final_status,
                completed_work_units=done,
                failed_work_units=failed,
                progress_pct=100.0 if total == 0 else round(done / total * 100, 1),
            )

            # Update scheduler run record
            if run_id:
                summary = json.dumps({
                    'total_work_units': total,
                    'completed': done,
                    'failed': failed,
                    'events_total': event_count,
                })
                await engine_db.update_scheduler_run(run_id, status='completed', summary=summary)

            await _syslog("info", f"Backfill {backfill_id} completed: {done}/{total} work units done, "
                          f"{failed} failed, {event_count} total events")
            logger.info(f"Backfill {backfill_id} completed: {done}/{total} done, {failed} failed")

        except Exception as e:
            await _syslog("error", f"Backfill {backfill_id} pipeline error: {e}", exc=e)
            logger.error(f"Backfill {backfill_id} pipeline error: {e}")
            await engine_db.update_backfill(
                backfill_id, status='failed', error_message=str(e)[:500]
            )
            if run_id:
                await engine_db.update_scheduler_run(
                    run_id, status='failed', error_message=str(e)[:500]
                )
        finally:
            self._running_backfills.pop(backfill_id, None)
            self._active_run_ids.pop(backfill_id, None)

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
        """Generate price enrichment work units from events.

        Creates one work unit per unique (chain, asset_id, date) combination.
        Skips asset/date pairs that already have prices in engine_price_history.

        For Cardano NFTs: deduplicates by policy_id since all NFTs in the same
        collection share the same floor price, dramatically reducing API calls.
        """
        # First, ensure Cardano NFTs are properly marked from V1 data
        if "cardano" in chains:
            marked = await engine_db.mark_cardano_nfts_from_v1()
            if marked:
                logger.info(f"Backfill {backfill_id}: marked {marked} Cardano assets as NFTs from V1 data")
                # Clear token_info_cache so updated is_nft flags are picked up
                price_enricher._token_info_cache.clear()

        units = []
        for chain in chains:
            events = await engine_db.get_events(user_id, chain=chain, limit=100000)

            # Collect unique (asset_id, date) combinations
            asset_dates_seen: set = set()
            all_dates: set = set()
            for evt in events:
                if not evt.get('block_time'):
                    continue
                dt = datetime.utcfromtimestamp(evt['block_time'])
                date_str = dt.strftime('%Y-%m-%d')
                asset_id = evt['asset_id']
                key = (asset_id, date_str)
                if key not in asset_dates_seen:
                    asset_dates_seen.add(key)
                    all_dates.add(date_str)

            # Bulk-check which prices already exist to skip them
            existing_prices = await engine_db.get_existing_price_keys(
                chain, sorted(all_dates)
            )

            # For Cardano: batch NFTs by policy_id
            if chain == "cardano":
                nft_policy_dates: Dict[tuple, list] = {}  # {(policy_id, date): [asset_ids]}

                for asset_id, date_str in asset_dates_seen:
                    price_key = f"{chain}:{asset_id}"
                    if (price_key, date_str) in existing_prices:
                        continue

                    # Check if this asset is a known NFT
                    if '.' in asset_id:
                        token_info = await engine_db.get_token_info(chain, asset_id)
                        if token_info and token_info.get('is_nft'):
                            policy_id = asset_id.split('.')[0]
                            key = (policy_id, date_str)
                            if key not in nft_policy_dates:
                                nft_policy_dates[key] = []
                            nft_policy_dates[key].append(asset_id)
                            continue

                    # Non-NFT: create individual work unit
                    units.append({
                        'backfill_id': backfill_id,
                        'user_id': user_id,
                        'chain': chain,
                        'account_id': asset_id,
                        'domain': 'enrich_price',
                        'cursor_start': date_str,
                        'cursor_end': date_str,
                    })

                # Create batched NFT work units: one per (policy_id, date)
                for (policy_id, date_str), asset_ids in nft_policy_dates.items():
                    units.append({
                        'backfill_id': backfill_id,
                        'user_id': user_id,
                        'chain': chain,
                        'account_id': policy_id,
                        'domain': 'enrich_price',
                        'cursor_start': date_str,
                        'cursor_end': json.dumps(asset_ids),
                    })

                if nft_policy_dates:
                    nft_count = sum(len(aids) for aids in nft_policy_dates.values())
                    logger.info(f"Backfill {backfill_id}: batched {nft_count} Cardano NFTs into "
                               f"{len(nft_policy_dates)} policy_id work units")
            else:
                # Non-Cardano chains: standard per-asset work units
                for asset_id, date_str in asset_dates_seen:
                    price_key = f"{chain}:{asset_id}"
                    if (price_key, date_str) in existing_prices:
                        continue
                    units.append({
                        'backfill_id': backfill_id,
                        'user_id': user_id,
                        'chain': chain,
                        'account_id': asset_id,
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
            logger.info(f"Backfill {backfill_id}: generated {len(units)} enrich work units (skipped already-priced)")

    # =========================================================================
    # Stage Executors (called by the scheduler)
    # =========================================================================

    async def _execute_index(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute an indexing work unit using the provider-keyed indexer."""
        chain = ChainId(work_unit['chain'])

        # Provider-keyed dispatch
        indexer = None
        provider_indexers = self._indexers.get(provider.name, {})
        if isinstance(provider_indexers, dict):
            indexer = provider_indexers.get(chain)

        # Fallback: scan all providers for one that has this chain
        if not indexer:
            for prov_name, prov_indexers in self._indexers.items():
                if isinstance(prov_indexers, dict) and chain in prov_indexers:
                    indexer = prov_indexers[chain]
                    logger.info(f"INDEX fallback: {provider.name} -> {prov_name} for {chain.value}")
                    break

        if not indexer:
            await _syslog("warning", f"No indexer for chain {work_unit['chain']}")
            return False

        await _syslog("debug", f"Indexing {chain.value}:{work_unit['account_id'][:12]}... "
                      f"via {provider.name}")

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

        if entries:
            await _syslog("info", f"Indexed {len(entries)} txs for "
                          f"{work_unit['chain']}:{work_unit['account_id'][:12]}...")
        else:
            await _syslog("warning", f"Indexed 0 txs for "
                          f"{work_unit['chain']}:{work_unit['account_id'][:12]}... "
                          f"(API may have returned empty)")
        return True

    async def _execute_hydrate(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute a hydration work unit."""
        chain = ChainId(work_unit['chain'])
        hydrator = self._hydrators.get(chain)
        if not hydrator:
            await _syslog("warning", f"No hydrator for chain {work_unit['chain']}")
            return False

        tx_id = work_unit['account_id']  # For hydrate, account_id holds the tx_id

        # Check if already hydrated (pre-hydration from indexer)
        existing = await engine_db.get_tx_raw(chain.value, tx_id)
        if existing:
            return True

        raw_data = await hydrator.hydrate(tx_id)
        if raw_data is None:
            await _syslog("warning", f"Hydration returned None for {chain.value}:{tx_id[:16]}... "
                          f"(RPC unavailable?)")
            return False

        await engine_db.upsert_tx_raw(chain.value, tx_id, raw_data, provider.name)
        return True

    async def _execute_normalize(self, work_unit: Dict, provider: Provider) -> bool:
        """Execute a normalization work unit."""
        chain = ChainId(work_unit['chain'])
        normalizer = self._normalizers.get(chain)
        if not normalizer:
            await _syslog("warning", f"No normalizer for chain {work_unit['chain']}")
            return False

        tx_id = work_unit.get('cursor_start', '')
        account_id = work_unit['account_id']

        # Get raw transaction data
        raw = await engine_db.get_tx_raw(chain.value, tx_id)
        if not raw:
            await _syslog("warning", f"No raw data for normalize: {chain.value}:{tx_id[:16]}...")
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
        """Execute a price enrichment work unit.

        account_id contains the asset_id (e.g. 'native', contract address, policy_id.asset_name).
        cursor_start contains the date string.
        cursor_end contains the date string for normal assets, or a JSON array of
        asset_ids for batched Cardano NFT work units.
        """
        chain = work_unit['chain']
        asset_id = work_unit['account_id']
        date = work_unit.get('cursor_start', '')
        cursor_end = work_unit.get('cursor_end', '')

        # Check for batched Cardano NFT work unit (cursor_end is JSON array of asset_ids)
        if chain == "cardano" and cursor_end and cursor_end.startswith('['):
            try:
                nft_asset_ids = json.loads(cursor_end)
            except (json.JSONDecodeError, TypeError):
                nft_asset_ids = None

            if nft_asset_ids:
                # asset_id is the policy_id for batched NFT units
                policy_id = asset_id
                # Build a synthetic asset_id for fetch_nft_floor_price
                floor_usd = await price_enricher.fetch_nft_floor_price(chain, f"{policy_id}.nft")
                if floor_usd and floor_usd > 0:
                    for nft_aid in nft_asset_ids:
                        price_key = f"{chain}:{nft_aid}"
                        await engine_db.upsert_price(price_key, date, floor_usd, "nft_floor")
                    logger.debug(f"Priced {len(nft_asset_ids)} NFTs for policy {policy_id[:16]}... at ${floor_usd:.2f}")
                    return True
                return False

        # Resolve token info first (populates is_nft flag in cache)
        token_info = await price_enricher.resolve_token_info(chain, asset_id)

        # Handle individual NFT floor prices
        if token_info and token_info.get('is_nft'):
            policy_id = asset_id.split('.')[0] if '.' in asset_id else asset_id
            floor_usd = await price_enricher.fetch_nft_floor_price(chain, asset_id)
            if floor_usd and floor_usd > 0:
                price_key = f"{chain}:{asset_id}"
                await engine_db.upsert_price(price_key, date, floor_usd, "nft_floor")
                return True
            return False

        price = await price_enricher.enrich_date(asset_id, chain, date)
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

    def set_run_id(self, backfill_id: int, run_id: int):
        """Associate a scheduler run with a backfill for logging."""
        self._active_run_ids[backfill_id] = run_id

    async def cancel_backfill(self, backfill_id: int):
        """Cancel a running backfill."""
        task = self._running_backfills.get(backfill_id)
        if task and not task.done():
            task.cancel()
            self._running_backfills.pop(backfill_id, None)

        # Also mark the associated run as failed
        run_id = self._active_run_ids.pop(backfill_id, None)
        if run_id:
            await engine_db.update_scheduler_run(run_id, status='failed', error_message='cancelled')

        await engine_db.cancel_backfill_work_units(backfill_id)
        await engine_db.update_backfill(backfill_id, status='cancelled')
        logger.info(f"Backfill {backfill_id} cancelled")

    # =========================================================================
    # Auto-collect scheduler
    # =========================================================================

    async def start_auto_collect(self, user_id: int, interval_hours: int):
        """Start (or restart) the periodic V2 engine collection for a user."""
        await self.stop_auto_collect(user_id)

        async def _auto_collect_loop():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)
                    logger.info(f"Auto-collect triggered for user {user_id}")

                    request = BackfillRequest(
                        chains=list(ChainId),
                        domains=[WorkDomain.INDEX, WorkDomain.HYDRATE,
                                 WorkDomain.NORMALIZE, WorkDomain.ENRICH_PRICE],
                    )
                    backfill_id = await self.plan_backfill(user_id, request)

                    run_id = await engine_db.create_scheduler_run(
                        user_id, backfill_id, 'scheduled'
                    )
                    self.set_run_id(backfill_id, run_id)

                    await self.run_backfill(backfill_id)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Auto-collect error for user {user_id}: {e}")
                    await asyncio.sleep(3600)  # Wait 1h before retrying on error

        task = asyncio.create_task(_auto_collect_loop())
        self._auto_collect_tasks[user_id] = task
        logger.info(f"V2 auto-collect started for user {user_id}, interval={interval_hours}h")

    async def stop_auto_collect(self, user_id: int):
        """Stop the periodic V2 engine collection for a user."""
        task = self._auto_collect_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"V2 auto-collect stopped for user {user_id}")

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

        # Load token info for decimals
        all_token_info = await engine_db.get_all_token_info()
        token_info_map = {(t['chain'], t['asset_id']): t for t in all_token_info}

        native_divisors = {
            "cardano": 1_000_000,      # lovelace → ADA
            "bitcoin": 100_000_000,     # satoshi → BTC
            "ethereum": 10**18,         # wei → ETH
            "solana": 1_000_000_000,    # lamports → SOL
            "polygon": 10**18,          # wei → MATIC
            "base": 10**18,             # wei → ETH
        }

        holdings = []
        total_value = 0.0
        for (chain, asset_id), balance in balances.items():
            if balance <= 0:
                continue

            price_key = f"{chain}:{asset_id}"
            price = price_map.get(price_key, 0.0)

            if asset_id == "native":
                divisor = native_divisors.get(chain, 1)
            else:
                token_info = token_info_map.get((chain, asset_id))
                if token_info:
                    decimals = token_info.get('decimals', 0) or 0
                    divisor = 10 ** decimals if decimals > 0 else 1
                else:
                    divisor = 1
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

        if range_str == '24h':
            return await self._get_hourly_history_data(user_id)

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

        # Native asset divisors
        native_divisors = {
            "cardano": 1_000_000,
            "bitcoin": 100_000_000,
            "ethereum": 10**18,
            "solana": 1_000_000_000,
            "polygon": 10**18,
            "base": 10**18,
        }

        # Load all token info for divisor/decimals lookup
        all_token_info = await engine_db.get_all_token_info()
        token_info_cache = {(t['chain'], t['asset_id']): t for t in all_token_info}

        # Collect all unique price keys from snapshots
        all_price_keys = set()
        for snapshot in filled.values():
            for (chain, asset_id) in snapshot.keys():
                all_price_keys.add(f"{chain}:{asset_id}")

        # Batch-load prices for all keys
        price_cache: Dict[str, Dict[str, float]] = {}  # {date: {price_key: price}}
        for price_key in all_price_keys:
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
                if raw_balance <= 0:
                    continue

                if asset_id == "native":
                    divisor = native_divisors.get(chain, 1)
                else:
                    token_info = token_info_cache.get((chain, asset_id))
                    if not token_info:
                        continue  # skip unknown tokens
                    if token_info.get('is_nft'):
                        # NFTs: use floor price if available, count as 1 unit
                        price_key = f"{chain}:{asset_id}"
                        nft_price = date_prices.get(price_key, 0.0)
                        if nft_price > 0:
                            total_value += nft_price
                            chain_values[chain] = chain_values.get(chain, 0) + round(nft_price, 2)
                        continue
                    decimals = token_info.get('decimals', 0) or 0
                    divisor = 10 ** decimals if decimals > 0 else 1

                human_balance = raw_balance / divisor if divisor > 0 else raw_balance
                price_key = f"{chain}:{asset_id}"
                price = date_prices.get(price_key, 0.0)
                if price <= 0:
                    continue  # skip tokens we couldn't price
                value = human_balance * price
                total_value += value
                chain_values[chain] = chain_values.get(chain, 0) + round(value, 2)

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

    async def _get_hourly_history_data(self, user_id: int) -> Dict:
        """Generate hourly history data for the 24h chart view."""
        from datetime import timedelta

        end_date = datetime.utcnow()
        end_ts = int(end_date.timestamp())

        # Replay ALL events to get current balances
        all_events = await engine_db.get_events(user_id, max_time=end_ts, limit=500000)
        if not all_events:
            return {'data': [], 'coverage': {'oldest_date': None, 'newest_date': None, 'total_days': 0}}

        # Build current balance snapshot
        balances: Dict[tuple, int] = {}
        for evt in all_events:
            if not evt.get('block_time'):
                continue
            amount = int(evt['amount'])
            key = (evt['chain'], evt['asset_id'])
            if evt['direction'] == 'in':
                balances[key] = balances.get(key, 0) + amount
            elif evt['direction'] == 'out':
                balances[key] = balances.get(key, 0) - amount

        native_divisors = {
            "cardano": 1_000_000,
            "bitcoin": 100_000_000,
            "ethereum": 10**18,
            "solana": 1_000_000_000,
            "polygon": 10**18,
            "base": 10**18,
        }

        # Load token info for non-native
        all_token_info = await engine_db.get_all_token_info()
        token_info_cache = {(t['chain'], t['asset_id']): t for t in all_token_info}

        # Collect unique price keys from balances
        price_keys = set()
        for (chain, asset_id) in balances.keys():
            if balances[(chain, asset_id)] > 0:
                price_keys.add((chain, asset_id))

        # Fetch hourly prices for each asset
        hourly_prices: Dict[str, Dict[str, float]] = {}  # {price_key: {datetime_str: price}}
        for chain, asset_id in price_keys:
            price_key = f"{chain}:{asset_id}"
            if asset_id == "native":
                prices = await price_enricher.fetch_hourly_prices(asset_id, chain, hours=25)
                hourly_prices[price_key] = prices
            else:
                token_info = token_info_cache.get((chain, asset_id))
                if token_info and not token_info.get('is_nft') and token_info.get('defillama_key'):
                    prices = await price_enricher.fetch_hourly_prices(asset_id, chain, hours=25)
                    hourly_prices[price_key] = prices

        # Collect all hourly timestamps across all assets
        all_hours = set()
        for prices in hourly_prices.values():
            all_hours.update(prices.keys())

        if not all_hours:
            return {'data': [], 'coverage': {'oldest_date': None, 'newest_date': None, 'total_days': 0}}

        # Build hourly output
        data = []
        for dt_str in sorted(all_hours):
            total_value = 0.0
            chain_values = {}

            for (chain, asset_id), raw_balance in balances.items():
                if raw_balance <= 0:
                    continue

                price_key = f"{chain}:{asset_id}"
                price = hourly_prices.get(price_key, {}).get(dt_str, 0.0)
                if price <= 0:
                    continue

                if asset_id == "native":
                    divisor = native_divisors.get(chain, 1)
                else:
                    token_info = token_info_cache.get((chain, asset_id))
                    if not token_info or token_info.get('is_nft'):
                        continue
                    decimals = token_info.get('decimals', 0) or 0
                    divisor = 10 ** decimals if decimals > 0 else 1

                human_balance = raw_balance / divisor if divisor > 0 else raw_balance
                value = human_balance * price
                total_value += value
                chain_values[chain] = chain_values.get(chain, 0) + round(value, 2)

            data.append({
                'date': dt_str,
                'value': round(total_value, 2),
                'chains': chain_values,
            })

        dates = [d['date'] for d in data]
        return {
            'data': data,
            'coverage': {
                'oldest_date': min(dates) if dates else None,
                'newest_date': max(dates) if dates else None,
                'total_days': 1,
            }
        }


# Singleton instance
backfill_orchestrator = BackfillOrchestrator()
