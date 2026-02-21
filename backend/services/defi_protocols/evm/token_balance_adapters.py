"""
Token Balance DeFi Adapters - Data-driven detection of DeFi positions
by checking ERC-20 receipt token balances.

Uses a registry mapping protocol -> token -> chain -> contract address.
A generic TokenBalanceAdapter checks balances for all tokens and creates
ProtocolPosition entries for non-zero balances.
"""

import asyncio
import logging
from typing import List, Optional
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token Registry
#
# Structure:
#   PROTOCOL_NAME -> {
#       "url": "https://...",
#       "tokens": {
#           TOKEN_SYMBOL -> {
#               CHAIN: CONTRACT_ADDRESS (checksummed),
#               "decimals": int,
#               "position_type": PositionType,
#           }
#       }
#   }
#
# Addresses verified against CoinGecko, Etherscan, and protocol docs.
# ---------------------------------------------------------------------------

TOKEN_REGISTRY = {
    # -----------------------------------------------------------------------
    # Liquid Staking Derivatives (LSDs)
    # -----------------------------------------------------------------------
    "Lido": {
        "url": "https://lido.fi",
        "tokens": {
            "stETH": {
                "ethereum": "0xae7ab96520DE3A18E5e111B5EaAb7831c399e269",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
            "wstETH": {
                "ethereum": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
                "arbitrum": "0x5979D7b546E38E414F7E9822514be443A4800529",
                "optimism": "0x1F32b1c2345538c0c6f582fCB022739c4A194Ebb",
                "polygon": "0x03b54A6e9a984069379fae1a4fC4dBAE93B3bCCD",
                "base": "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Rocket Pool": {
        "url": "https://rocketpool.net",
        "tokens": {
            "rETH": {
                "ethereum": "0xae78736Cd615f374D3085123A210448E74Fc6393",
                "arbitrum": "0xEC70Dcb4A1EFa46b8F2D97C310C9c4790ba5ffA8",
                "optimism": "0x9Bcef72be871e61ED4fBbc7630889bEE758eb81D",
                "polygon": "0x0266F4F08D82372CF0FcbCCc0Ff74309089c74d1",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Frax": {
        "url": "https://frax.finance",
        "tokens": {
            "sfrxETH": {
                "ethereum": "0xac3E018457B222d93114458476f3E3416Abbe38F",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
            "frxETH": {
                "ethereum": "0x5E8422345238F34275888049021821E8E08CAa1f",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Coinbase": {
        "url": "https://www.coinbase.com/cbeth",
        "tokens": {
            "cbETH": {
                "ethereum": "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704",
                "base": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Mantle": {
        "url": "https://www.mantle.xyz/meth",
        "tokens": {
            "mETH": {
                "ethereum": "0xd5F7838F5C461fefF7FE49ea5ebaF7728bB0ADfa",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "EtherFi": {
        "url": "https://www.ether.fi",
        "tokens": {
            "weETH": {
                "ethereum": "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee",
                "arbitrum": "0x35751007a407ca6FEFfE80b3cB397736D2cf4dbe",
                "base": "0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
            "eETH": {
                "ethereum": "0x35fA164735182de50811E8e2E824cFb9B6118ac2",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "StakeWise": {
        "url": "https://stakewise.io",
        "tokens": {
            "osETH": {
                "ethereum": "0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Swell": {
        "url": "https://www.swellnetwork.io",
        "tokens": {
            "swETH": {
                "ethereum": "0xf951E335afb289353dc249e82926178EaC7DEd78",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
            "rswETH": {
                "ethereum": "0xFAe103DC9cf190eD75350761e95403b7b8aFa6c0",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Kelp": {
        "url": "https://kelpdao.xyz",
        "tokens": {
            "rsETH": {
                "ethereum": "0xA1290d69c65A6Fe4DF752f95823fae25cB99e5A7",
                "decimals": 18,
                "position_type": PositionType.RESTAKING,
            },
        },
    },
    "Stader": {
        "url": "https://www.staderlabs.com",
        "tokens": {
            "ETHx": {
                "ethereum": "0xA35b1B31Ce002FBF2058D22F30f95D405200A15b",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Ankr": {
        "url": "https://www.ankr.com/staking",
        "tokens": {
            "ankrETH": {
                "ethereum": "0xE95A203B1a91a908F9B9CE46459d101078c2c3cb",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },
    "Origin Protocol": {
        "url": "https://www.oeth.com",
        "tokens": {
            "OETH": {
                "ethereum": "0x856c4Efb76C1D1AE02e20CEB03A2A6a08b0b8dC3",
                "decimals": 18,
                "position_type": PositionType.YIELD_VAULT,
            },
        },
    },
    "Binance Staked ETH": {
        "url": "https://www.binance.com/en/wbeth",
        "tokens": {
            "WBETH": {
                "ethereum": "0xa2E3356610840b74FA337866d52bBcECA66A7cEB",
                "bsc": "0xa2E3356610840b74FA337866d52bBcECA66A7cEB",
                "decimals": 18,
                "position_type": PositionType.LIQUID_STAKING,
            },
        },
    },

    # -----------------------------------------------------------------------
    # Yield / Vault Protocols
    # -----------------------------------------------------------------------
    "Convex Finance": {
        "url": "https://www.convexfinance.com",
        "tokens": {
            "cvxCRV": {
                "ethereum": "0x62B9c7356A2Dc64a1969e19C23e4f579F9810Aa7",
                "decimals": 18,
                "position_type": PositionType.STAKING,
            },
            "CVX": {
                "ethereum": "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B",
                "decimals": 18,
                "position_type": PositionType.GOVERNANCE,
            },
        },
    },

    # -----------------------------------------------------------------------
    # Restaking Protocols
    # -----------------------------------------------------------------------
    "Puffer Finance": {
        "url": "https://www.puffer.fi",
        "tokens": {
            "pufETH": {
                "ethereum": "0xD9A442856C234a39a81a089C06451EBAa4306a72",
                "decimals": 18,
                "position_type": PositionType.RESTAKING,
            },
        },
    },
    "Renzo": {
        "url": "https://www.renzoprotocol.com",
        "tokens": {
            "ezETH": {
                "ethereum": "0xbf5495Efe5DB9ce00f80364C8B423567e58d2110",
                "arbitrum": "0x2416092f143378750bb29b79eD961ab195CcEea5",
                "base": "0x2416092f143378750bb29b79eD961ab195CcEea5",
                "decimals": 18,
                "position_type": PositionType.RESTAKING,
            },
        },
    },

    # -----------------------------------------------------------------------
    # Stablecoins / RWA Yield
    # -----------------------------------------------------------------------
    "Ethena": {
        "url": "https://ethena.fi",
        "tokens": {
            "sUSDe": {
                "ethereum": "0x9D39A5DE30e57443BfF2A8307A4256c8797A3497",
                "decimals": 18,
                "position_type": PositionType.YIELD_VAULT,
            },
            "USDe": {
                "ethereum": "0x4c9EDD5852cd905f086C759E8383e09bff1E68B3",
                "decimals": 18,
                "position_type": PositionType.YIELD_VAULT,
            },
        },
    },
    "MountainProtocol": {
        "url": "https://mountainprotocol.com",
        "tokens": {
            "USDM": {
                "ethereum": "0x59D9356E565Ab3A36dD77763Fc0d87fEaf85508C",
                "decimals": 18,
                "position_type": PositionType.YIELD_VAULT,
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Generic Token Balance Adapter
# ---------------------------------------------------------------------------

class TokenBalanceAdapter(BaseEVMAdapter):
    """Generic adapter that detects DeFi positions by checking ERC-20 token balances.

    Instantiated once per protocol from TOKEN_REGISTRY entries.
    """

    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE

    def __init__(self, protocol_name: str, protocol_url: str, tokens_config: dict):
        self.PROTOCOL_NAME = protocol_name
        self.PROTOCOL_URL = protocol_url
        self._tokens = tokens_config
        # Derive supported chains from all chain keys in the tokens config
        chains = set()
        for token_info in tokens_config.values():
            chains.update(
                k for k in token_info.keys() if k not in ("decimals", "position_type")
            )
        self.SUPPORTED_CHAINS = sorted(chains)

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect positions by checking ERC-20 balance for each registered token."""
        positions = []
        tasks = []

        for token_symbol, token_info in self._tokens.items():
            decimals = token_info.get("decimals", 18)
            position_type = token_info.get("position_type", PositionType.LIQUID_STAKING)

            chains_to_check = (
                [chain]
                if chain
                else [c for c in token_info if c not in ("decimals", "position_type")]
            )

            for c in chains_to_check:
                contract = token_info.get(c)
                if not contract:
                    continue
                tasks.append((token_symbol, decimals, position_type, c, contract))

        if not tasks:
            return positions

        # Fan out balance checks in parallel
        async def _check_balance(token_symbol, decimals, position_type, c, contract):
            try:
                raw_balance = await self._get_erc20_balance(c, contract, address)
                if raw_balance and raw_balance > 0:
                    amount = raw_balance / (10 ** decimals)
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=position_type,
                        token_symbol=token_symbol,
                        amount=amount,
                        contract_address=contract,
                    )
            except Exception as e:
                logger.debug(
                    f"Error checking {self.PROTOCOL_NAME}/{token_symbol} on {c}: {e}"
                )
            return None

        results = await asyncio.gather(
            *[_check_balance(*t) for t in tasks], return_exceptions=True
        )

        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


# ---------------------------------------------------------------------------
# Register all token-balance adapters from the registry
# ---------------------------------------------------------------------------

def register_token_balance_adapters():
    """Instantiate and register all token balance adapters."""
    from services.defi_protocols.registry import protocol_registry

    for protocol_name, config in TOKEN_REGISTRY.items():
        adapter = TokenBalanceAdapter(
            protocol_name=protocol_name,
            protocol_url=config.get("url", ""),
            tokens_config=config["tokens"],
        )
        protocol_registry.register(adapter)
    logger.info(
        f"Registered {len(TOKEN_REGISTRY)} token-balance DeFi adapters"
    )


# Auto-register on import
register_token_balance_adapters()
