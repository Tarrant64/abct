"""Solana DeFi Protocol Adapters.

Importing this package registers all adapters with the global protocol_registry.
"""

# SPL token balance adapters (import triggers registration at module level)
from services.defi_protocols.solana.marinade import MarinadeAdapter
from services.defi_protocols.solana.jito import JitoAdapter
from services.defi_protocols.solana.blazestake import BlazeStakeAdapter
from services.defi_protocols.solana.sanctum import SanctumAdapter
from services.defi_protocols.solana.solend import SolendAdapter
from services.defi_protocols.solana.kamino import KaminoAdapter
from services.defi_protocols.solana.tulip import TulipAdapter

# Program account adapters
from services.defi_protocols.solana.raydium import RaydiumAdapter
from services.defi_protocols.solana.orca import OrcaAdapter
from services.defi_protocols.solana.marginfi import MarginfiAdapter
from services.defi_protocols.solana.jupiter_perps import JupiterPerpsAdapter
from services.defi_protocols.solana.drift import DriftAdapter
from services.defi_protocols.solana.meteora import MeteoraAdapter
from services.defi_protocols.solana.lifinity import LifinityAdapter
from services.defi_protocols.solana.phoenix import PhoenixAdapter

SOLANA_ADAPTERS = [
    MarinadeAdapter,
    JitoAdapter,
    BlazeStakeAdapter,
    SanctumAdapter,
    SolendAdapter,
    KaminoAdapter,
    TulipAdapter,
    RaydiumAdapter,
    OrcaAdapter,
    MarginfiAdapter,
    JupiterPerpsAdapter,
    DriftAdapter,
    MeteoraAdapter,
    LifinityAdapter,
    PhoenixAdapter,
]

__all__ = [
    "MarinadeAdapter",
    "JitoAdapter",
    "BlazeStakeAdapter",
    "SanctumAdapter",
    "SolendAdapter",
    "KaminoAdapter",
    "TulipAdapter",
    "RaydiumAdapter",
    "OrcaAdapter",
    "MarginfiAdapter",
    "JupiterPerpsAdapter",
    "DriftAdapter",
    "MeteoraAdapter",
    "LifinityAdapter",
    "PhoenixAdapter",
    "SOLANA_ADAPTERS",
]
