"""EVM DeFi Protocol Adapters.

Importing this package auto-registers all EVM adapters with the protocol_registry.
"""

# Token balance adapters (Lido, Rocket Pool, Frax, cbETH, Yearn, Beefy, etc.)
from services.defi_protocols.evm import token_balance_adapters  # noqa: F401

# Smart contract adapters — original set
from services.defi_protocols.evm import aave_v3  # noqa: F401
from services.defi_protocols.evm import compound_v3  # noqa: F401
from services.defi_protocols.evm import spark  # noqa: F401
from services.defi_protocols.evm import maker  # noqa: F401
from services.defi_protocols.evm import morpho  # noqa: F401
from services.defi_protocols.evm import gmx  # noqa: F401
from services.defi_protocols.evm import eigenlayer  # noqa: F401
from services.defi_protocols.evm import curve  # noqa: F401
from services.defi_protocols.evm import balancer  # noqa: F401
from services.defi_protocols.evm import uniswap_v3_lp  # noqa: F401

# Smart contract adapters — Phase 3 expansion
from services.defi_protocols.evm import pendle  # noqa: F401
from services.defi_protocols.evm import aerodrome  # noqa: F401
from services.defi_protocols.evm import velodrome  # noqa: F401
from services.defi_protocols.evm import stargate  # noqa: F401
from services.defi_protocols.evm import radiant  # noqa: F401
from services.defi_protocols.evm import benqi  # noqa: F401
from services.defi_protocols.evm import sushiswap  # noqa: F401
from services.defi_protocols.evm import synthetix  # noqa: F401
from services.defi_protocols.evm import liquity  # noqa: F401
from services.defi_protocols.evm import camelot  # noqa: F401
from services.defi_protocols.evm import abracadabra  # noqa: F401
from services.defi_protocols.evm import pancakeswap  # noqa: F401
