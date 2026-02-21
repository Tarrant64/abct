"""
DeFi Protocol Adapters Package

Provides a unified interface for detecting and querying DeFi positions
across multiple chains and protocols.

Usage:
    from services.defi_protocols.registry import protocol_registry

    # Detect all positions for an address
    positions = await protocol_registry.detect_all_positions(address, chain='ethereum')

    # List supported protocols
    protocols = protocol_registry.list_protocols()
"""

from services.defi_protocols.base_adapter import ProtocolAdapter, ProtocolPosition
from services.defi_protocols.registry import protocol_registry

__all__ = ['ProtocolAdapter', 'ProtocolPosition', 'protocol_registry']
