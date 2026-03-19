"""
Cardano DeFi Protocol Adapters.

Provides adapters for 13 Cardano DeFi protocols:
- Indigo Protocol (synthetic assets, INDY staking)
- Liqwid Finance (lending/borrowing, LQ staking)
- Strike Finance (perpetuals DEX, STRIKE staking)
- Iagon (DePIN storage/compute, IAG staking)
- Surf Lending (lending/borrowing, ADA supply)
- Minswap (DEX, LP positions)
- SundaeSwap (DEX V3, LP positions)
- WingRiders (DEX, LP positions)
- Splash (DEX ex-Spectrum, LP positions)
- Djed (stablecoin protocol, DJED/SHEN yield vault)
- FluidTokens (P2P lending, ADA supply via UTXO scan)
- Lenfi (lending ex-Aada, receipt token detection)
- MuesliSwap (DEX, LP positions)

Importing this package auto-registers all Cardano adapters with the protocol_registry.
"""

from services.defi_protocols.cardano.indigo import IndigoAdapter
from services.defi_protocols.cardano.liqwid import LiqwidAdapter
from services.defi_protocols.cardano.strike import StrikeAdapter
from services.defi_protocols.cardano.iagon import IagonAdapter
from services.defi_protocols.cardano.surf import SurfAdapter
from services.defi_protocols.cardano.minswap import MinswapAdapter
from services.defi_protocols.cardano.sundaeswap import SundaeSwapAdapter
from services.defi_protocols.cardano.wingriders import WingRidersAdapter
from services.defi_protocols.cardano.splash import SplashAdapter
from services.defi_protocols.cardano.djed import DjedAdapter
from services.defi_protocols.cardano.fluidtokens import FluidTokensAdapter
from services.defi_protocols.cardano.lenfi import LenfiAdapter
from services.defi_protocols.cardano.muesliswap import MuesliSwapAdapter
from services.defi_protocols.registry import protocol_registry

# All Cardano adapter classes for bulk registration
CARDANO_ADAPTERS = [
    IndigoAdapter,
    LiqwidAdapter,
    StrikeAdapter,
    IagonAdapter,
    SurfAdapter,
    MinswapAdapter,
    SundaeSwapAdapter,
    WingRidersAdapter,
    SplashAdapter,
    DjedAdapter,
    FluidTokensAdapter,
    LenfiAdapter,
    MuesliSwapAdapter,
]

# Auto-register all Cardano adapters with the global protocol registry
for _adapter_cls in CARDANO_ADAPTERS:
    protocol_registry.register(_adapter_cls())

__all__ = [
    'IndigoAdapter',
    'LiqwidAdapter',
    'StrikeAdapter',
    'IagonAdapter',
    'SurfAdapter',
    'MinswapAdapter',
    'SundaeSwapAdapter',
    'WingRidersAdapter',
    'SplashAdapter',
    'DjedAdapter',
    'FluidTokensAdapter',
    'LenfiAdapter',
    'MuesliSwapAdapter',
    'CARDANO_ADAPTERS',
]
