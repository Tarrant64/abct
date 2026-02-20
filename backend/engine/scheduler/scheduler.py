"""
Work Unit Scheduler

Assigns work units to providers based on capabilities, health, and rate limits.
Manages bulkheads (concurrency limits), token buckets, and circuit breakers.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Callable, Awaitable, Any

from engine.models import ChainId, WorkDomain, WorkStatus
from engine.providers.provider import Provider
from engine.providers.registry import ProviderRegistry
from engine.scheduler.token_bucket import TokenBucket
from engine.scheduler.circuit_breaker import CircuitBreaker
from engine import db as engine_db

logger = logging.getLogger(__name__)

# Type for stage executor functions
StageExecutor = Callable[[Dict[str, Any], Provider], Awaitable[bool]]


class WorkUnitScheduler:
    """Schedules and executes work units across providers."""

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry
        self._buckets: Dict[str, TokenBucket] = {}
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._bulkheads: Dict[str, asyncio.Semaphore] = {}
        self._executors: Dict[str, StageExecutor] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _ensure_provider_resources(self, provider: Provider):
        """Lazily create rate limiter, circuit breaker, and bulkhead for a provider."""
        if provider.name not in self._buckets:
            self._buckets[provider.name] = TokenBucket(
                rate=provider.requests_per_second,
                burst=provider.burst_size,
            )
        if provider.name not in self._bulkheads:
            self._bulkheads[provider.name] = asyncio.Semaphore(provider.max_concurrency)

    def _get_breaker(self, provider_name: str, chain: str, domain: str) -> CircuitBreaker:
        """Get or create a circuit breaker for provider+chain+domain."""
        key = f"{provider_name}:{chain}:{domain}"
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker(key)
        return self._breakers[key]

    def register_executor(self, domain: str, executor: StageExecutor):
        """Register an executor function for a work domain."""
        self._executors[domain] = executor
        logger.info(f"Registered executor for domain '{domain}'")

    async def execute_work_unit(self, work_unit: Dict[str, Any]) -> bool:
        """
        Execute a single work unit: pick provider, acquire resources, run.

        Returns True on success, False on failure.
        """
        chain = ChainId(work_unit['chain'])
        domain = WorkDomain(work_unit['domain'])
        wu_id = work_unit['id']

        # Get executor for this domain
        executor = self._executors.get(domain.value)
        if not executor:
            logger.error(f"No executor registered for domain '{domain.value}'")
            await engine_db.update_work_unit(wu_id, status='failed',
                                              error_message=f'No executor for {domain.value}')
            return False

        # Find best available provider
        provider = self.registry.get_best_candidate(chain, domain)
        if not provider:
            logger.warning(f"No provider available for {chain.value}:{domain.value}")
            await engine_db.update_work_unit(wu_id, status='retry',
                                              error_message='No provider available')
            return False

        self._ensure_provider_resources(provider)
        breaker = self._get_breaker(provider.name, chain.value, domain.value)

        if not breaker.is_available:
            # Try fallback provider
            candidates = self.registry.get_candidates(chain, domain)
            fallback = None
            for c in candidates:
                if c.name != provider.name:
                    fb_breaker = self._get_breaker(c.name, chain.value, domain.value)
                    if fb_breaker.is_available:
                        fallback = c
                        break
            if not fallback:
                logger.warning(f"All providers circuit-open for {chain.value}:{domain.value}")
                await engine_db.update_work_unit(wu_id, status='retry',
                                                  error_message='All providers circuit-open')
                return False
            provider = fallback
            self._ensure_provider_resources(provider)
            breaker = self._get_breaker(provider.name, chain.value, domain.value)

        # Mark as running
        await engine_db.update_work_unit(wu_id, status='running',
                                          assigned_provider=provider.name,
                                          started_at=time.strftime('%Y-%m-%dT%H:%M:%S'))

        # Acquire bulkhead + rate limit
        try:
            async with self._bulkheads[provider.name]:
                await self._buckets[provider.name].wait_for_token()

                start_time = time.monotonic()
                success = await executor(work_unit, provider)
                elapsed_ms = (time.monotonic() - start_time) * 1000

                if success:
                    breaker.record_success()
                    await engine_db.update_work_unit(
                        wu_id, status='completed',
                        completed_at=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    # Update health with latency
                    await engine_db.upsert_provider_health(
                        provider.name, chain.value, domain.value,
                        is_healthy=True, consecutive_failures=0,
                        avg_latency_ms=elapsed_ms,
                        last_success_at=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    return True
                else:
                    breaker.record_failure()
                    attempt = work_unit.get('attempt_count', 0) + 1
                    max_attempts = work_unit.get('max_attempts', 3)
                    new_status = 'retry' if attempt < max_attempts else 'failed'
                    await engine_db.update_work_unit(
                        wu_id, status=new_status,
                        attempt_count=attempt,
                        error_message=f'Provider {provider.name} returned failure'
                    )
                    await engine_db.upsert_provider_health(
                        provider.name, chain.value, domain.value,
                        consecutive_failures=breaker._consecutive_failures,
                        last_failure_at=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    return False

        except Exception as e:
            breaker.record_failure()
            attempt = work_unit.get('attempt_count', 0) + 1
            max_attempts = work_unit.get('max_attempts', 3)
            new_status = 'retry' if attempt < max_attempts else 'failed'
            await engine_db.update_work_unit(
                wu_id, status=new_status,
                attempt_count=attempt,
                error_message=str(e)[:500]
            )
            logger.error(f"Work unit {wu_id} failed with {provider.name}: {e}")
            # Surface permanent failures to system logs
            if new_status == 'failed':
                try:
                    from services.logging_service import get_logging_service
                    svc = get_logging_service()
                    domain = work_unit.get('domain', '?')
                    chain = work_unit.get('chain', '?')
                    await svc.error("engine", f"Work unit permanently failed: "
                                    f"{domain}/{chain} — {str(e)[:200]}")
                except Exception:
                    pass
            return False

    async def run_backfill(self, backfill_id: int, max_concurrent: int = 5):
        """
        Run all work units for a backfill, processing domains in pipeline order.

        Domains are processed in dependency order:
        index → hydrate → normalize → enrich_price → enrich_metadata
        """
        self._running = True
        domain_order = [
            WorkDomain.INDEX.value,
            WorkDomain.HYDRATE.value,
            WorkDomain.NORMALIZE.value,
            WorkDomain.ENRICH_PRICE.value,
            WorkDomain.ENRICH_METADATA.value,
        ]

        try:
            for domain in domain_order:
                if not self._running:
                    break

                while self._running:
                    # Get batch of pending work units for this domain
                    pending = await engine_db.get_pending_work_units(
                        backfill_id, domain=domain, limit=max_concurrent
                    )
                    if not pending:
                        break

                    # Execute batch concurrently
                    tasks = [
                        asyncio.create_task(self.execute_work_unit(wu))
                        for wu in pending
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Update backfill progress
                    stats = await engine_db.get_work_unit_stats(backfill_id)
                    total = sum(s.get('total', 0) for s in stats.values())
                    done = sum(s.get('done', 0) for s in stats.values())
                    failed = sum(s.get('failed', 0) for s in stats.values())
                    pct = (done / total * 100) if total > 0 else 0

                    await engine_db.update_backfill(
                        backfill_id,
                        completed_work_units=done,
                        failed_work_units=failed,
                        progress_pct=round(pct, 1)
                    )

                    # Log progress
                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"Work unit exception: {result}")

                    # Brief pause to avoid tight loop
                    await asyncio.sleep(0.1)

            # Final status update
            stats = await engine_db.get_work_unit_stats(backfill_id)
            total = sum(s.get('total', 0) for s in stats.values())
            done = sum(s.get('done', 0) for s in stats.values())
            failed = sum(s.get('failed', 0) for s in stats.values())

            if done + failed >= total:
                final_status = 'completed' if failed == 0 else 'completed'
                await engine_db.update_backfill(
                    backfill_id, status=final_status,
                    completed_work_units=done,
                    failed_work_units=failed,
                    progress_pct=100.0 if failed == 0 else round(done / total * 100, 1)
                )
                logger.info(
                    f"Backfill {backfill_id} finished: {done}/{total} completed, {failed} failed"
                )

        except Exception as e:
            logger.error(f"Backfill {backfill_id} scheduler error: {e}")
            await engine_db.update_backfill(
                backfill_id, status='failed', error_message=str(e)[:500]
            )
        finally:
            self._running = False

    def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def get_health_summary(self) -> Dict[str, Any]:
        """Get a summary of all circuit breaker states."""
        return {
            name: breaker.to_dict()
            for name, breaker in self._breakers.items()
        }
