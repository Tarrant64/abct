"""
Provider dataclass — represents a data source that can fulfill work units.
"""

from dataclasses import dataclass, field
from typing import Set
from engine.models import ChainId, WorkDomain


@dataclass
class Provider:
    """A registered data provider."""
    name: str
    chains: Set[ChainId]
    domains: Set[WorkDomain]
    priority: int = 50          # higher = preferred
    max_concurrency: int = 3    # bulkhead semaphore size
    requests_per_second: float = 5.0  # token bucket refill rate
    burst_size: int = 10        # token bucket max capacity

    # Chains this provider must NEVER serve (enforced at registry level)
    excluded_chains: Set[ChainId] = field(default_factory=set)

    def can_serve(self, chain: ChainId, domain: WorkDomain) -> bool:
        """Check if this provider can serve a given chain+domain."""
        if chain in self.excluded_chains:
            return False
        return chain in self.chains and domain in self.domains
