"""
Demo Wallet Service - Returns fake wallet balances and data

Provides mock wallet data for demo accounts:
- Fake wallet balances across all chains
- Mock transaction histories
- No real blockchain API calls

All data is pre-defined and realistic but entirely fake.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import random


class DemoWalletService:
    """Service for returning fake wallet data in demo mode."""

    def __init__(self):
        """Initialize demo wallet service with fake data."""
        # Demo wallet addresses (fake but realistic-looking)
        # Bloated balances to target ~$1M+ total portfolio
        self.demo_wallets = {
            "cardano": [
                {
                    "address": "addr1qx2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf",
                    "label": "Cardano Main",
                    "balance": "100000.00",  # ADA
                    "balance_usd": 100000.00 * 1.05,  # ~$105K
                },
                {
                    "address": "addr1qy8kd4efdxy99gwfjfkw0gj3ljdm4ljg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg0xfjg",
                    "label": "Cardano Staking",
                    "balance": "50000.00",  # ADA
                    "balance_usd": 50000.00 * 1.05,  # ~$52.5K
                }
            ],
            "bitcoin": [
                {
                    "address": "bc1qxy2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9we",
                    "label": "BTC Cold Storage",
                    "balance": "2.10",  # BTC
                    "balance_usd": 2.10 * 98000,  # ~$205K
                },
                {
                    "address": "bc1q9h5yjdkwef7a3xmn2p4qrs6tv8u0ckjf3wejf7a",
                    "label": "BTC Hot Wallet",
                    "balance": "0.70",  # BTC
                    "balance_usd": 0.70 * 98000,  # ~$68.6K
                }
            ],
            "ethereum": [
                {
                    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb8",
                    "label": "ETH Main",
                    "balance": "15.00",  # ETH
                    "balance_usd": 15.00 * 3500,  # ~$52.5K
                },
                {
                    "address": "0x8Ba1f109551bD432803012645Ac136ddd64DBa72",
                    "label": "ETH DeFi Wallet",
                    "balance": "7.00",  # ETH
                    "balance_usd": 7.00 * 3500,  # ~$24.5K
                }
            ],
            "solana": [
                {
                    "address": "DemoSo1anaWa11etAddress123456789ABC",
                    "label": "SOL Main",
                    "balance": "500.00",  # SOL
                    "balance_usd": 500.00 * 180,  # ~$90K
                },
                {
                    "address": "Demo2So1anaStakingAddr987654321XYZ",
                    "label": "SOL Staking",
                    "balance": "300.00",  # SOL
                    "balance_usd": 300.00 * 180,  # ~$54K
                }
            ],
            "polygon": [
                {
                    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb9",
                    "label": "Polygon Main",
                    "balance": "40000.00",  # POL
                    "balance_usd": 40000.00 * 0.90,  # ~$36K
                }
            ],
            "base": [
                {
                    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEc0",
                    "label": "Base Wallet",
                    "balance": "8.00",  # ETH on Base
                    "balance_usd": 8.00 * 3500,  # ~$28K
                }
            ],
            "algorand": [
                {
                    "address": "SWOUICD7LO3MWVKLHFKADCXLF5HZPUQQFW5OIJAFZJBG4HDQH53RTTJPFE",
                    "label": "Algorand Main",
                    "balance": "25000.00",  # ALGO
                    "balance_usd": 25000.00 * 0.35,  # ~$8.75K
                }
            ]
        }

        # Demo tokens - EXTENSIVE HOLDINGS ACROSS ALL CHAINS
        self.demo_tokens = {
            "cardano": [
                # Popular Cardano tokens (20-30 tokens)
                {
                    "name": "MIN",
                    "ticker": "MIN",
                    "quantity": "15000",
                    "decimals": 0,
                    "price_usd": 0.045,
                    "value_usd": 15000 * 0.045,
                    "logo": ""
                },
                {
                    "name": "SNEK",
                    "ticker": "SNEK",
                    "quantity": "25000000",
                    "decimals": 0,
                    "price_usd": 0.0012,
                    "value_usd": 25000000 * 0.0012,
                    "logo": ""
                },
                {
                    "name": "WMT",
                    "ticker": "WMT",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 0.15,
                    "value_usd": 8000 * 0.15,
                    "logo": ""
                },
                {
                    "name": "HOSKY",
                    "ticker": "HOSKY",
                    "quantity": "50000000",
                    "decimals": 0,
                    "price_usd": 0.00001,
                    "value_usd": 50000000 * 0.00001,
                    "logo": ""
                },
                {
                    "name": "BOOK",
                    "ticker": "BOOK",
                    "quantity": "2500",
                    "decimals": 0,
                    "price_usd": 0.25,
                    "value_usd": 2500 * 0.25,
                    "logo": ""
                },
                {
                    "name": "COPI",
                    "ticker": "COPI",
                    "quantity": "12000",
                    "decimals": 0,
                    "price_usd": 0.12,
                    "value_usd": 12000 * 0.12,
                    "logo": ""
                },
                {
                    "name": "INDY",
                    "ticker": "INDY",
                    "quantity": "500",
                    "decimals": 6,
                    "price_usd": 0.85,
                    "value_usd": 500 * 0.85,
                    "logo": ""
                },
                {
                    "name": "SUNDAE",
                    "ticker": "SUNDAE",
                    "quantity": "35000",
                    "decimals": 0,
                    "price_usd": 0.025,
                    "value_usd": 35000 * 0.025,
                    "logo": ""
                },
                {
                    "name": "AGIX",
                    "ticker": "AGIX",
                    "quantity": "3000",
                    "decimals": 8,
                    "price_usd": 0.45,
                    "value_usd": 3000 * 0.45,
                    "logo": ""
                },
                {
                    "name": "NMKR",
                    "ticker": "NMKR",
                    "quantity": "5000",
                    "decimals": 0,
                    "price_usd": 0.32,
                    "value_usd": 5000 * 0.32,
                    "logo": ""
                },
                {
                    "name": "LIQWID",
                    "ticker": "C3",
                    "quantity": "8500",
                    "decimals": 0,
                    "price_usd": 0.18,
                    "value_usd": 8500 * 0.18,
                    "logo": ""
                },
                {
                    "name": "LQ",
                    "ticker": "LQ",
                    "quantity": "15000",
                    "decimals": 6,
                    "price_usd": 0.08,
                    "value_usd": 15000 * 0.08,
                    "logo": ""
                },
                {
                    "name": "DJED",
                    "ticker": "DJED",
                    "quantity": "2000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 2000 * 1.0,
                    "logo": ""
                },
                {
                    "name": "IUSD",
                    "ticker": "IUSD",
                    "quantity": "3500",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 3500 * 1.0,
                    "logo": ""
                },
                {
                    "name": "VYFI",
                    "ticker": "VYFI",
                    "quantity": "750",
                    "decimals": 6,
                    "price_usd": 2.5,
                    "value_usd": 750 * 2.5,
                    "logo": ""
                },
                {
                    "name": "OPTIM",
                    "ticker": "OPTIM",
                    "quantity": "20000",
                    "decimals": 0,
                    "price_usd": 0.05,
                    "value_usd": 20000 * 0.05,
                    "logo": ""
                },
                {
                    "name": "CLAP",
                    "ticker": "CLAP",
                    "quantity": "45000",
                    "decimals": 0,
                    "price_usd": 0.015,
                    "value_usd": 45000 * 0.015,
                    "logo": ""
                },
                {
                    "name": "MILK",
                    "ticker": "MILK",
                    "quantity": "18000",
                    "decimals": 0,
                    "price_usd": 0.022,
                    "value_usd": 18000 * 0.022,
                    "logo": ""
                },
                {
                    "name": "SOCIETY",
                    "ticker": "SOCIETY",
                    "quantity": "500",
                    "decimals": 0,
                    "price_usd": 5.5,
                    "value_usd": 500 * 5.5,
                    "logo": ""
                },
                {
                    "name": "CLAY",
                    "ticker": "CLAY",
                    "quantity": "1200",
                    "decimals": 0,
                    "price_usd": 3.2,
                    "value_usd": 1200 * 3.2,
                    "logo": ""
                },
                {
                    "name": "MYTH",
                    "ticker": "MYTH",
                    "quantity": "10000",
                    "decimals": 6,
                    "price_usd": 0.35,
                    "value_usd": 10000 * 0.35,
                    "logo": ""
                },
                {
                    "name": "REVUTO",
                    "ticker": "REVU",
                    "quantity": "25000",
                    "decimals": 6,
                    "price_usd": 0.018,
                    "value_usd": 25000 * 0.018,
                    "logo": ""
                },
                {
                    "name": "HUNT",
                    "ticker": "HUNT",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.28,
                    "value_usd": 5000 * 0.28,
                    "logo": ""
                },
                {
                    "name": "MELD",
                    "ticker": "MELD",
                    "quantity": "30000",
                    "decimals": 6,
                    "price_usd": 0.012,
                    "value_usd": 30000 * 0.012,
                    "logo": ""
                },
                {
                    "name": "AADA",
                    "ticker": "AADA",
                    "quantity": "8000",
                    "decimals": 0,
                    "price_usd": 0.055,
                    "value_usd": 8000 * 0.055,
                    "logo": ""
                }
            ],
            "ethereum": [
                # Popular Ethereum tokens (15-20 tokens)
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 5000,
                    "logo": ""
                },
                {
                    "name": "Tether USD",
                    "ticker": "USDT",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 8000,
                    "logo": ""
                },
                {
                    "name": "Dai Stablecoin",
                    "ticker": "DAI",
                    "quantity": "3500",
                    "decimals": 18,
                    "price_usd": 1.0,
                    "value_usd": 3500,
                    "logo": ""
                },
                {
                    "name": "Chainlink",
                    "ticker": "LINK",
                    "quantity": "250",
                    "decimals": 18,
                    "price_usd": 18.0,
                    "value_usd": 250 * 18.0,
                    "logo": ""
                },
                {
                    "name": "Uniswap",
                    "ticker": "UNI",
                    "quantity": "500",
                    "decimals": 18,
                    "price_usd": 8.0,
                    "value_usd": 500 * 8.0,
                    "logo": ""
                },
                {
                    "name": "Aave",
                    "ticker": "AAVE",
                    "quantity": "35",
                    "decimals": 18,
                    "price_usd": 120.0,
                    "value_usd": 35 * 120.0,
                    "logo": ""
                },
                {
                    "name": "Maker",
                    "ticker": "MKR",
                    "quantity": "2.5",
                    "decimals": 18,
                    "price_usd": 2000.0,
                    "value_usd": 2.5 * 2000.0,
                    "logo": ""
                },
                {
                    "name": "Compound",
                    "ticker": "COMP",
                    "quantity": "50",
                    "decimals": 18,
                    "price_usd": 85.0,
                    "value_usd": 50 * 85.0,
                    "logo": ""
                },
                {
                    "name": "SushiSwap",
                    "ticker": "SUSHI",
                    "quantity": "800",
                    "decimals": 18,
                    "price_usd": 1.2,
                    "value_usd": 800 * 1.2,
                    "logo": ""
                },
                {
                    "name": "Curve DAO Token",
                    "ticker": "CRV",
                    "quantity": "3000",
                    "decimals": 18,
                    "price_usd": 0.8,
                    "value_usd": 3000 * 0.8,
                    "logo": ""
                },
                {
                    "name": "1inch",
                    "ticker": "1INCH",
                    "quantity": "1500",
                    "decimals": 18,
                    "price_usd": 0.45,
                    "value_usd": 1500 * 0.45,
                    "logo": ""
                },
                {
                    "name": "Polygon",
                    "ticker": "MATIC",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 0.90,
                    "value_usd": 5000 * 0.90,
                    "logo": ""
                },
                {
                    "name": "The Graph",
                    "ticker": "GRT",
                    "quantity": "10000",
                    "decimals": 18,
                    "price_usd": 0.25,
                    "value_usd": 10000 * 0.25,
                    "logo": ""
                },
                {
                    "name": "Synthetix",
                    "ticker": "SNX",
                    "quantity": "400",
                    "decimals": 18,
                    "price_usd": 3.5,
                    "value_usd": 400 * 3.5,
                    "logo": ""
                },
                {
                    "name": "Yearn Finance",
                    "ticker": "YFI",
                    "quantity": "0.5",
                    "decimals": 18,
                    "price_usd": 8000.0,
                    "value_usd": 0.5 * 8000.0,
                    "logo": ""
                },
                {
                    "name": "Balancer",
                    "ticker": "BAL",
                    "quantity": "600",
                    "decimals": 18,
                    "price_usd": 4.2,
                    "value_usd": 600 * 4.2,
                    "logo": ""
                },
                {
                    "name": "Wrapped Bitcoin",
                    "ticker": "WBTC",
                    "quantity": "0.1",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.1 * 98000.0,
                    "logo": ""
                },
                {
                    "name": "Lido Staked Ether",
                    "ticker": "stETH",
                    "quantity": "1.5",
                    "decimals": 18,
                    "price_usd": 3500.0,
                    "value_usd": 1.5 * 3500.0,
                    "logo": ""
                },
                {
                    "name": "Rocket Pool ETH",
                    "ticker": "rETH",
                    "quantity": "0.8",
                    "decimals": 18,
                    "price_usd": 3800.0,
                    "value_usd": 0.8 * 3800.0,
                    "logo": ""
                }
            ],
            "solana": [
                # Popular Solana tokens (15-20 tokens)
                {
                    "name": "Bonk",
                    "ticker": "BONK",
                    "quantity": "50000000",
                    "decimals": 5,
                    "price_usd": 0.00001,
                    "value_usd": 50000000 * 0.00001,
                    "logo": ""
                },
                {
                    "name": "dogwifhat",
                    "ticker": "WIF",
                    "quantity": "500",
                    "decimals": 6,
                    "price_usd": 2.5,
                    "value_usd": 500 * 2.5,
                    "logo": ""
                },
                {
                    "name": "Pyth Network",
                    "ticker": "PYTH",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.45,
                    "value_usd": 5000 * 0.45,
                    "logo": ""
                },
                {
                    "name": "Jupiter",
                    "ticker": "JUP",
                    "quantity": "3000",
                    "decimals": 6,
                    "price_usd": 1.2,
                    "value_usd": 3000 * 1.2,
                    "logo": ""
                },
                {
                    "name": "Raydium",
                    "ticker": "RAY",
                    "quantity": "1500",
                    "decimals": 6,
                    "price_usd": 3.5,
                    "value_usd": 1500 * 3.5,
                    "logo": ""
                },
                {
                    "name": "Orca",
                    "ticker": "ORCA",
                    "quantity": "800",
                    "decimals": 6,
                    "price_usd": 4.2,
                    "value_usd": 800 * 4.2,
                    "logo": ""
                },
                {
                    "name": "Serum",
                    "ticker": "SRM",
                    "quantity": "2000",
                    "decimals": 6,
                    "price_usd": 0.8,
                    "value_usd": 2000 * 0.8,
                    "logo": ""
                },
                {
                    "name": "Bonfida",
                    "ticker": "FIDA",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.35,
                    "value_usd": 5000 * 0.35,
                    "logo": ""
                },
                {
                    "name": "Mango Markets",
                    "ticker": "MNGO",
                    "quantity": "20000",
                    "decimals": 6,
                    "price_usd": 0.05,
                    "value_usd": 20000 * 0.05,
                    "logo": ""
                },
                {
                    "name": "Marinade Staked SOL",
                    "ticker": "mSOL",
                    "quantity": "50",
                    "decimals": 9,
                    "price_usd": 200.0,
                    "value_usd": 50 * 200.0,
                    "logo": ""
                },
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "10000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 10000,
                    "logo": ""
                },
                {
                    "name": "Render Token",
                    "ticker": "RNDR",
                    "quantity": "400",
                    "decimals": 8,
                    "price_usd": 9.5,
                    "value_usd": 400 * 9.5,
                    "logo": ""
                },
                {
                    "name": "Helium",
                    "ticker": "HNT",
                    "quantity": "150",
                    "decimals": 8,
                    "price_usd": 8.2,
                    "value_usd": 150 * 8.2,
                    "logo": ""
                },
                {
                    "name": "Star Atlas",
                    "ticker": "ATLAS",
                    "quantity": "100000",
                    "decimals": 8,
                    "price_usd": 0.004,
                    "value_usd": 100000 * 0.004,
                    "logo": ""
                },
                {
                    "name": "Oxygen",
                    "ticker": "OXY",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 0.015,
                    "value_usd": 8000 * 0.015,
                    "logo": ""
                },
                {
                    "name": "Jito Staked SOL",
                    "ticker": "JitoSOL",
                    "quantity": "30",
                    "decimals": 9,
                    "price_usd": 205.0,
                    "value_usd": 30 * 205.0,
                    "logo": ""
                }
            ],
            "polygon": [
                # Popular Polygon tokens (10-15 tokens)
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 8000,
                    "logo": ""
                },
                {
                    "name": "Tether USD",
                    "ticker": "USDT",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 5000,
                    "logo": ""
                },
                {
                    "name": "QuickSwap",
                    "ticker": "QUICK",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 0.08,
                    "value_usd": 5000 * 0.08,
                    "logo": ""
                },
                {
                    "name": "Aavegotchi",
                    "ticker": "GHST",
                    "quantity": "2000",
                    "decimals": 18,
                    "price_usd": 1.5,
                    "value_usd": 2000 * 1.5,
                    "logo": ""
                },
                {
                    "name": "Stader MaticX",
                    "ticker": "MATICX",
                    "quantity": "3000",
                    "decimals": 18,
                    "price_usd": 1.1,
                    "value_usd": 3000 * 1.1,
                    "logo": ""
                },
                {
                    "name": "Dragon Quick",
                    "ticker": "DQUICK",
                    "quantity": "800",
                    "decimals": 18,
                    "price_usd": 0.15,
                    "value_usd": 800 * 0.15,
                    "logo": ""
                },
                {
                    "name": "Wrapped Ethereum",
                    "ticker": "WETH",
                    "quantity": "1.2",
                    "decimals": 18,
                    "price_usd": 3500.0,
                    "value_usd": 1.2 * 3500.0,
                    "logo": ""
                },
                {
                    "name": "Wrapped Bitcoin",
                    "ticker": "WBTC",
                    "quantity": "0.05",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.05 * 98000.0,
                    "logo": ""
                },
                {
                    "name": "Balancer",
                    "ticker": "BAL",
                    "quantity": "400",
                    "decimals": 18,
                    "price_usd": 4.2,
                    "value_usd": 400 * 4.2,
                    "logo": ""
                },
                {
                    "name": "Curve DAO Token",
                    "ticker": "CRV",
                    "quantity": "2000",
                    "decimals": 18,
                    "price_usd": 0.8,
                    "value_usd": 2000 * 0.8,
                    "logo": ""
                },
                {
                    "name": "SushiSwap",
                    "ticker": "SUSHI",
                    "quantity": "1000",
                    "decimals": 18,
                    "price_usd": 1.2,
                    "value_usd": 1000 * 1.2,
                    "logo": ""
                }
            ],
            "base": [
                # Popular Base tokens (10-15 tokens)
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "12000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 12000,
                    "logo": ""
                },
                {
                    "name": "Dai Stablecoin",
                    "ticker": "DAI",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 1.0,
                    "value_usd": 5000,
                    "logo": ""
                },
                {
                    "name": "Coinbase Wrapped Staked ETH",
                    "ticker": "cbETH",
                    "quantity": "0.5",
                    "decimals": 18,
                    "price_usd": 3800.0,
                    "value_usd": 0.5 * 3800.0,
                    "logo": ""
                },
                {
                    "name": "Wrapped Bitcoin",
                    "ticker": "WBTC",
                    "quantity": "0.02",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.02 * 98000.0,
                    "logo": ""
                },
                {
                    "name": "Uniswap",
                    "ticker": "UNI",
                    "quantity": "300",
                    "decimals": 18,
                    "price_usd": 8.0,
                    "value_usd": 300 * 8.0,
                    "logo": ""
                },
                {
                    "name": "Aerodrome Finance",
                    "ticker": "AERO",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 1.5,
                    "value_usd": 5000 * 1.5,
                    "logo": ""
                },
                {
                    "name": "BaseSwap",
                    "ticker": "BSWAP",
                    "quantity": "10000",
                    "decimals": 18,
                    "price_usd": 0.25,
                    "value_usd": 10000 * 0.25,
                    "logo": ""
                },
                {
                    "name": "Chainlink",
                    "ticker": "LINK",
                    "quantity": "200",
                    "decimals": 18,
                    "price_usd": 18.0,
                    "value_usd": 200 * 18.0,
                    "logo": ""
                },
                {
                    "name": "Aave",
                    "ticker": "AAVE",
                    "quantity": "20",
                    "decimals": 18,
                    "price_usd": 120.0,
                    "value_usd": 20 * 120.0,
                    "logo": ""
                }
            ],
            "algorand": [
                # Popular Algorand ASAs (10-15 tokens)
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "15000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 15000,
                    "logo": "",
                    "asset_id": "312769"
                },
                {
                    "name": "Planets",
                    "ticker": "PLANETS",
                    "quantity": "500000",
                    "decimals": 6,
                    "price_usd": 0.005,
                    "value_usd": 500000 * 0.005,
                    "logo": "",
                    "asset_id": "27165954"
                },
                {
                    "name": "Opulous",
                    "ticker": "OPUL",
                    "quantity": "25000",
                    "decimals": 10,
                    "price_usd": 0.08,
                    "value_usd": 25000 * 0.08,
                    "logo": "",
                    "asset_id": "287867876"
                },
                {
                    "name": "AlgoFi Wrapped BTC",
                    "ticker": "GOBTC",
                    "quantity": "0.005",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.005 * 98000.0,
                    "logo": "",
                    "asset_id": "386192725"
                },
                {
                    "name": "AlgoFi Wrapped ETH",
                    "ticker": "GOETH",
                    "quantity": "0.15",
                    "decimals": 8,
                    "price_usd": 3500.0,
                    "value_usd": 0.15 * 3500.0,
                    "logo": "",
                    "asset_id": "386195940"
                },
                {
                    "name": "Yieldly",
                    "ticker": "YLDY",
                    "quantity": "100000",
                    "decimals": 6,
                    "price_usd": 0.002,
                    "value_usd": 100000 * 0.002,
                    "logo": "",
                    "asset_id": "226701642"
                },
                {
                    "name": "Smile Coin",
                    "ticker": "SMILE",
                    "quantity": "50000",
                    "decimals": 6,
                    "price_usd": 0.0015,
                    "value_usd": 50000 * 0.0015,
                    "logo": "",
                    "asset_id": "300208676"
                },
                {
                    "name": "Alchemon",
                    "ticker": "ALCH",
                    "quantity": "30000",
                    "decimals": 6,
                    "price_usd": 0.01,
                    "value_usd": 30000 * 0.01,
                    "logo": "",
                    "asset_id": "310014962"
                },
                {
                    "name": "Tinyman",
                    "ticker": "TINY",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.12,
                    "value_usd": 5000 * 0.12,
                    "logo": "",
                    "asset_id": "329110405"
                },
                {
                    "name": "Cometa",
                    "ticker": "COMET",
                    "quantity": "20000",
                    "decimals": 6,
                    "price_usd": 0.008,
                    "value_usd": 20000 * 0.008,
                    "logo": "",
                    "asset_id": "348950369"
                },
                {
                    "name": "AlgoStake",
                    "ticker": "STKE",
                    "quantity": "10000",
                    "decimals": 6,
                    "price_usd": 0.035,
                    "value_usd": 10000 * 0.035,
                    "logo": "",
                    "asset_id": "511484048"
                }
            ]
        }

    async def get_all_wallets(self) -> List[Dict]:
        """
        Get all demo wallets.

        Returns:
            List of demo wallet objects
        """
        all_wallets = []
        wallet_id = 1

        for blockchain, wallets in self.demo_wallets.items():
            for wallet in wallets:
                all_wallets.append({
                    "id": wallet_id,
                    "address": wallet["address"],
                    "blockchain": blockchain,
                    "label": wallet["label"],
                    "balance": wallet["balance"],
                    "balance_usd": wallet["balance_usd"],
                    "created_at": (datetime.now() - timedelta(days=random.randint(30, 365))).isoformat(),
                    "updated_at": datetime.now().isoformat()
                })
                wallet_id += 1

        return all_wallets

    async def get_wallet_balance(self, address: str, blockchain: str) -> Optional[Dict]:
        """
        Get balance for a specific demo wallet.

        Args:
            address: Wallet address (not used, returns demo data)
            blockchain: Blockchain name

        Returns:
            Demo wallet balance data
        """
        if blockchain not in self.demo_wallets:
            return None

        wallets = self.demo_wallets[blockchain]
        if not wallets:
            return None

        # Try to find matching wallet by address, fallback to first
        wallet = next((w for w in wallets if w["address"] == address), wallets[0])

        return {
            "address": address,
            "blockchain": blockchain,
            "balance": wallet["balance"],
            "balance_usd": wallet["balance_usd"],
            "unit": self._get_native_unit(blockchain),
            "updated_at": datetime.now().isoformat()
        }

    async def get_wallet_tokens(self, address: str, blockchain: str) -> List[Dict]:
        """
        Get tokens for a specific demo wallet.

        Args:
            address: Wallet address (not used)
            blockchain: Blockchain name

        Returns:
            List of demo token holdings
        """
        if blockchain not in self.demo_tokens:
            return []

        return self.demo_tokens[blockchain]

    async def get_total_balance_usd(self) -> Dict:
        """
        Get total balance across all demo wallets in USD.

        Returns:
            Dict with total balance and breakdown by chain
        """
        total_usd = 0.0
        breakdown = {}

        for blockchain, wallets in self.demo_wallets.items():
            chain_total = sum(w["balance_usd"] for w in wallets)
            breakdown[blockchain] = chain_total
            total_usd += chain_total

        # Add token values
        token_total = 0.0
        for blockchain, tokens in self.demo_tokens.items():
            chain_token_value = sum(t["value_usd"] for t in tokens)
            breakdown[f"{blockchain}_tokens"] = chain_token_value
            token_total += chain_token_value

        total_usd += token_total

        return {
            "total_usd": round(total_usd, 2),
            "breakdown": breakdown,
            "updated_at": datetime.now().isoformat()
        }

    async def add_wallet(self, address: str, blockchain: str, label: Optional[str] = None) -> Dict:
        """
        Mock adding a wallet (does nothing in demo mode).

        Args:
            address: Wallet address
            blockchain: Blockchain name
            label: Optional label

        Returns:
            Success message
        """
        return {
            "success": True,
            "message": "Demo mode: Wallet not actually added",
            "address": address,
            "blockchain": blockchain,
            "label": label
        }

    async def refresh_wallet(self, address: str, blockchain: str) -> Dict:
        """
        Mock refreshing wallet data (returns same demo data).

        Args:
            address: Wallet address
            blockchain: Blockchain name

        Returns:
            Demo wallet data
        """
        return await self.get_wallet_balance(address, blockchain)

    def _get_native_unit(self, blockchain: str) -> str:
        """Get native currency unit for blockchain."""
        units = {
            "cardano": "ADA",
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "polygon": "POL",
            "base": "ETH",
            "algorand": "ALGO",
            "bsc": "BNB",
            "arbitrum": "ETH",
            "avalanche": "AVAX",
            "tron": "TRX",
            "xrp": "XRP",
            "hedera": "HBAR",
            "multiversx": "EGLD",
            "sui": "SUI",
            "aptos": "APT",
            "filecoin": "FIL",
            "litecoin": "LTC",
            "dogecoin": "DOGE",
            "zcash": "ZEC",
            "tezos": "XTZ",
            "stacks": "STX",
            "vechain": "VET",
            "cosmos": "ATOM",
            "near": "NEAR",
            "icp": "ICP"
        }
        return units.get(blockchain, "UNKNOWN")


# Global instance
demo_wallet_service = DemoWalletService()
