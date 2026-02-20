"""
Provider Registry — manages provider capabilities, health, and scoring.

Scoring: score = priority * health_factor * quota_factor
CoinStats exclusion for Cardano is enforced here.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from engine.models import ChainId, WorkDomain
from engine.providers.provider import Provider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry of all data providers with health-aware selection."""

    def __init__(self):
        self._providers: Dict[str, Provider] = {}
        self._health_cache: Dict[str, dict] = {}  # "name:chain:domain" -> health data

    def register(self, provider: Provider):
        """Register a provider."""
        self._providers[provider.name] = provider
        logger.info(
            f"Registered provider '{provider.name}': "
            f"chains={[c.value for c in provider.chains]}, "
            f"domains={[d.value for d in provider.domains]}, "
            f"priority={provider.priority}"
        )

    def get_provider(self, name: str) -> Optional[Provider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def get_candidates(self, chain: ChainId, domain: WorkDomain) -> List[Provider]:
        """Get all providers that can serve a chain+domain, sorted by score (best first)."""
        candidates = []
        for provider in self._providers.values():
            if provider.can_serve(chain, domain):
                candidates.append(provider)

        # Sort by score (descending)
        candidates.sort(key=lambda p: self._score(p, chain, domain), reverse=True)
        return candidates

    def get_best_candidate(self, chain: ChainId, domain: WorkDomain) -> Optional[Provider]:
        """Get the best available provider for a chain+domain."""
        candidates = self.get_candidates(chain, domain)
        for candidate in candidates:
            health_key = f"{candidate.name}:{chain.value}:{domain.value}"
            health = self._health_cache.get(health_key, {})
            # Skip providers with open circuit breakers
            circuit_until = health.get('circuit_open_until')
            if circuit_until and datetime.fromisoformat(circuit_until) > datetime.utcnow():
                continue
            return candidate
        return None

    def update_health(self, provider_name: str, chain: str, domain: str, health_data: dict):
        """Update cached health data for a provider."""
        key = f"{provider_name}:{chain}:{domain}"
        self._health_cache[key] = health_data

    def _score(self, provider: Provider, chain: ChainId, domain: WorkDomain) -> float:
        """Calculate provider score for ranking."""
        health_key = f"{provider.name}:{chain.value}:{domain.value}"
        health = self._health_cache.get(health_key, {})

        # Base priority
        score = float(provider.priority)

        # Health factor: reduce score for unhealthy providers
        if not health.get('is_healthy', True):
            score *= 0.1

        # Quota factor: boost providers with more remaining quota
        quota = health.get('quota_remaining')
        if quota is not None and quota <= 0:
            score *= 0.01  # Near-zero for exhausted quota

        # Latency factor: slight preference for faster providers
        latency = health.get('avg_latency_ms', 0)
        if latency > 0:
            # Normalize: 100ms = 1.0, 1000ms = 0.9, 5000ms = 0.5
            latency_factor = max(0.5, 1.0 - (latency - 100) / 10000)
            score *= latency_factor

        return score

    def list_providers(self) -> List[Dict]:
        """List all registered providers with their capabilities."""
        result = []
        for p in self._providers.values():
            result.append({
                'name': p.name,
                'chains': [c.value for c in p.chains],
                'domains': [d.value for d in p.domains],
                'excluded_chains': [c.value for c in p.excluded_chains],
                'priority': p.priority,
                'max_concurrency': p.max_concurrency,
                'requests_per_second': p.requests_per_second,
            })
        return result


def create_default_registry() -> ProviderRegistry:
    """Create the registry with all known providers."""
    registry = ProviderRegistry()

    # --- Cardano ---
    registry.register(Provider(
        name="blockfrost",
        chains={ChainId.CARDANO},
        domains={WorkDomain.INDEX, WorkDomain.HYDRATE},
        priority=60,
        max_concurrency=5,
        requests_per_second=10.0,
        burst_size=20,
    ))
    registry.register(Provider(
        name="cexplorer",
        chains={ChainId.CARDANO},
        domains={WorkDomain.INDEX},
        priority=30,
        max_concurrency=2,
        requests_per_second=2.0,
        burst_size=5,
    ))
    registry.register(Provider(
        name="taptools",
        chains={ChainId.CARDANO},
        domains={WorkDomain.ENRICH_METADATA},
        priority=50,
        max_concurrency=1,
        requests_per_second=0.5,  # Very strict rate limit
        burst_size=2,
    ))

    # --- Bitcoin ---
    registry.register(Provider(
        name="blockstream",
        chains={ChainId.BITCOIN},
        domains={WorkDomain.INDEX, WorkDomain.HYDRATE},
        priority=60,
        max_concurrency=3,
        requests_per_second=5.0,
        burst_size=10,
    ))

    # --- EVM Chains ---
    evm_chains = {ChainId.ETHEREUM, ChainId.POLYGON, ChainId.BASE}
    registry.register(Provider(
        name="etherscan",
        chains=evm_chains,
        domains={WorkDomain.INDEX},
        priority=60,
        max_concurrency=3,
        requests_per_second=5.0,
        burst_size=10,
    ))
    registry.register(Provider(
        name="alchemy",
        chains=evm_chains,
        domains={WorkDomain.INDEX, WorkDomain.HYDRATE},
        priority=70,
        max_concurrency=5,
        requests_per_second=10.0,
        burst_size=20,
    ))
    registry.register(Provider(
        name="ankr",
        chains=evm_chains,
        domains={WorkDomain.INDEX},
        priority=40,
        max_concurrency=2,
        requests_per_second=3.0,
        burst_size=5,
    ))
    registry.register(Provider(
        name="public_rpc_evm",
        chains=evm_chains,
        domains={WorkDomain.HYDRATE},
        priority=20,
        max_concurrency=2,
        requests_per_second=2.0,
        burst_size=5,
    ))

    # --- Solana ---
    registry.register(Provider(
        name="helius",
        chains={ChainId.SOLANA},
        domains={WorkDomain.INDEX, WorkDomain.HYDRATE},
        priority=60,
        max_concurrency=5,
        requests_per_second=10.0,
        burst_size=20,
    ))
    registry.register(Provider(
        name="public_rpc_solana",
        chains={ChainId.SOLANA},
        domains={WorkDomain.HYDRATE},
        priority=20,
        max_concurrency=2,
        requests_per_second=2.0,
        burst_size=5,
    ))

    # --- CoinStats (NOT Cardano) ---
    registry.register(Provider(
        name="coinstats",
        chains={ChainId.BITCOIN, ChainId.ETHEREUM, ChainId.SOLANA, ChainId.POLYGON, ChainId.BASE},
        domains={WorkDomain.INDEX, WorkDomain.HYDRATE},
        priority=40,
        max_concurrency=3,
        requests_per_second=5.0,
        burst_size=10,
        excluded_chains={ChainId.CARDANO},  # NEVER serve Cardano
    ))

    # --- Pricing Providers (all chains) ---
    all_chains = {ChainId.CARDANO, ChainId.BITCOIN, ChainId.ETHEREUM,
                  ChainId.SOLANA, ChainId.POLYGON, ChainId.BASE}
    registry.register(Provider(
        name="coingecko",
        chains=all_chains,
        domains={WorkDomain.ENRICH_PRICE},
        priority=60,
        max_concurrency=2,
        requests_per_second=2.0,  # Free tier limit
        burst_size=5,
    ))
    registry.register(Provider(
        name="cmc",
        chains=all_chains,
        domains={WorkDomain.ENRICH_PRICE},
        priority=40,
        max_concurrency=2,
        requests_per_second=3.0,
        burst_size=5,
    ))
    registry.register(Provider(
        name="defillama",
        chains=all_chains,
        domains={WorkDomain.ENRICH_PRICE},
        priority=35,
        max_concurrency=3,
        requests_per_second=5.0,
        burst_size=10,
    ))

    return registry
