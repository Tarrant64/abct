"""
Protocol Registry - Auto-discovery and aggregation of all DeFi protocol adapters.

Provides a single entry point for detecting positions across all registered protocols.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from services.defi_protocols.base_adapter import ProtocolAdapter, ProtocolPosition

logger = logging.getLogger(__name__)


class ProtocolRegistry:
    """Registry of all DeFi protocol adapters with auto-discovery."""

    def __init__(self):
        self._adapters: Dict[str, ProtocolAdapter] = {}

    def register(self, adapter: ProtocolAdapter):
        """Register a protocol adapter."""
        name = adapter.PROTOCOL_NAME
        if name in self._adapters:
            logger.warning(f"Protocol '{name}' already registered, replacing")
        self._adapters[name] = adapter
        logger.debug(f"Registered protocol adapter: {name} ({adapter.DETECTION_METHOD.value})")

    def unregister(self, name: str):
        """Remove a protocol adapter."""
        self._adapters.pop(name, None)

    def get(self, name: str) -> Optional[ProtocolAdapter]:
        """Get adapter by protocol name."""
        return self._adapters.get(name)

    def list_protocols(self, chain: str = None) -> List[dict]:
        """List all registered protocols, optionally filtered by chain."""
        protocols = []
        for adapter in self._adapters.values():
            if chain and not adapter.supports_chain(chain):
                continue
            protocols.append(adapter.info())
        return protocols

    def get_adapters_for_chain(self, chain: str) -> List[ProtocolAdapter]:
        """Get all adapters that support a specific chain."""
        return [a for a in self._adapters.values() if a.supports_chain(chain)]

    async def detect_all_positions(
        self, address: str, chain: str = None, timeout: float = 30.0
    ) -> List[ProtocolPosition]:
        """Detect positions across all registered protocols.

        Args:
            address: Wallet address to scan
            chain: Filter to specific chain (None = all chains)
            timeout: Per-adapter timeout in seconds

        Returns:
            Combined list of all detected positions
        """
        adapters = self.get_adapters_for_chain(chain) if chain else list(self._adapters.values())

        if not adapters:
            return []

        async def _safe_detect(adapter: ProtocolAdapter) -> List[ProtocolPosition]:
            try:
                return await asyncio.wait_for(
                    adapter.detect_positions(address, chain),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout detecting {adapter.PROTOCOL_NAME} positions for {address[:20]}...")
                return []
            except Exception as e:
                logger.error(f"Error detecting {adapter.PROTOCOL_NAME} positions: {e}")
                return []

        results = await asyncio.gather(*[_safe_detect(a) for a in adapters])

        all_positions = []
        for positions in results:
            all_positions.extend(positions)

        return all_positions

    async def detect_positions_by_chain(
        self, address: str, chains: List[str] = None
    ) -> Dict[str, List[ProtocolPosition]]:
        """Detect positions grouped by chain.

        Args:
            address: Wallet address
            chains: List of chains to scan (None = all)

        Returns:
            Dict mapping chain -> list of positions
        """
        if chains is None:
            chains = list(set(
                chain for adapter in self._adapters.values()
                for chain in adapter.SUPPORTED_CHAINS
            ))

        result = {}
        for chain in chains:
            positions = await self.detect_all_positions(address, chain=chain)
            if positions:
                result[chain] = positions

        return result

    @property
    def protocol_count(self) -> int:
        return len(self._adapters)

    @property
    def chain_count(self) -> int:
        chains = set()
        for adapter in self._adapters.values():
            chains.update(adapter.SUPPORTED_CHAINS)
        return len(chains)


# Singleton registry
protocol_registry = ProtocolRegistry()
