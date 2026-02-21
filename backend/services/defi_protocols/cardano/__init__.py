"""
Cardano DeFi Protocol Adapters.

Provides adapters for 5 Cardano DeFi protocols:
- Indigo Protocol (synthetic assets, INDY staking)
- Liqwid Finance (lending/borrowing, LQ staking)
- Strike Finance (perpetuals DEX, STRIKE staking)
- Iagon (DePIN storage/compute, IAG staking)
- Surf Lending (lending/borrowing, ADA supply)

Usage:
    from services.defi_protocols.cardano import CARDANO_ADAPTERS

    for adapter_cls in CARDANO_ADAPTERS:
        adapter = adapter_cls()
        registry.register(adapter)
"""

from services.defi_protocols.cardano.indigo import IndigoAdapter
from services.defi_protocols.cardano.liqwid import LiqwidAdapter
from services.defi_protocols.cardano.strike import StrikeAdapter
from services.defi_protocols.cardano.iagon import IagonAdapter
from services.defi_protocols.cardano.surf import SurfAdapter

# All Cardano adapter classes for bulk registration
CARDANO_ADAPTERS = [
    IndigoAdapter,
    LiqwidAdapter,
    StrikeAdapter,
    IagonAdapter,
    SurfAdapter,
]

__all__ = [
    'IndigoAdapter',
    'LiqwidAdapter',
    'StrikeAdapter',
    'IagonAdapter',
    'SurfAdapter',
    'CARDANO_ADAPTERS',
]
