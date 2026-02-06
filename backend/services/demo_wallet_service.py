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
        self.demo_wallets = {
            "cardano": [
                {
                    "address": "addr1qx2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf",
                    "label": "Demo Main Wallet",
                    "balance": "42500.50",  # ADA
                    "balance_usd": 42500.50 * 1.05,  # Assume $1.05 ADA
                }
            ],
            "bitcoin": [
                {
                    "address": "bc1qxy2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9we",
                    "label": "Demo BTC Wallet",
                    "balance": "0.25",  # BTC
                    "balance_usd": 0.25 * 98000,  # Assume $98k BTC
                }
            ],
            "ethereum": [
                {
                    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb8",
                    "label": "Demo ETH Wallet",
                    "balance": "5.75",  # ETH
                    "balance_usd": 5.75 * 3500,  # Assume $3500 ETH
                }
            ],
            "solana": [
                {
                    "address": "DemoSo1anaWa11etAddress123456789ABC",
                    "label": "Demo SOL Wallet",
                    "balance": "125.50",  # SOL
                    "balance_usd": 125.50 * 180,  # Assume $180 SOL
                }
            ],
            "polygon": [
                {
                    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb9",
                    "label": "Demo Polygon Wallet",
                    "balance": "500.25",  # MATIC/POL
                    "balance_usd": 500.25 * 0.90,  # Assume $0.90 POL
                }
            ],
            "base": [
                {
                    "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEc0",
                    "label": "Demo Base Wallet",
                    "balance": "2.50",  # ETH on Base
                    "balance_usd": 2.50 * 3500,  # Assume $3500 ETH
                }
            ],
            "algorand": [
                {
                    "address": "SWOUICD7LO3MWVKLHFKADCXLF5HZPUQQFW5OIJAFZJBG4HDQH53RTTJPFE",
                    "label": "Demo Algorand Wallet",
                    "balance": "8500.00",  # ALGO
                    "balance_usd": 8500.00 * 0.35,  # Assume $0.35 ALGO
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
                    "logo": "https://logostream.dev/api/logo?symbol=MIN"
                },
                {
                    "name": "SNEK",
                    "ticker": "SNEK",
                    "quantity": "25000000",
                    "decimals": 0,
                    "price_usd": 0.0012,
                    "value_usd": 25000000 * 0.0012,
                    "logo": "https://logostream.dev/api/logo?symbol=SNEK"
                },
                {
                    "name": "WMT",
                    "ticker": "WMT",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 0.15,
                    "value_usd": 8000 * 0.15,
                    "logo": "https://logostream.dev/api/logo?symbol=WMT"
                },
                {
                    "name": "HOSKY",
                    "ticker": "HOSKY",
                    "quantity": "50000000",
                    "decimals": 0,
                    "price_usd": 0.00001,
                    "value_usd": 50000000 * 0.00001,
                    "logo": "https://logostream.dev/api/logo?symbol=HOSKY"
                },
                {
                    "name": "BOOK",
                    "ticker": "BOOK",
                    "quantity": "2500",
                    "decimals": 0,
                    "price_usd": 0.25,
                    "value_usd": 2500 * 0.25,
                    "logo": "https://logostream.dev/api/logo?symbol=BOOK"
                },
                {
                    "name": "COPI",
                    "ticker": "COPI",
                    "quantity": "12000",
                    "decimals": 0,
                    "price_usd": 0.12,
                    "value_usd": 12000 * 0.12,
                    "logo": "https://logostream.dev/api/logo?symbol=COPI"
                },
                {
                    "name": "INDY",
                    "ticker": "INDY",
                    "quantity": "500",
                    "decimals": 6,
                    "price_usd": 0.85,
                    "value_usd": 500 * 0.85,
                    "logo": "https://logostream.dev/api/logo?symbol=INDY"
                },
                {
                    "name": "SUNDAE",
                    "ticker": "SUNDAE",
                    "quantity": "35000",
                    "decimals": 0,
                    "price_usd": 0.025,
                    "value_usd": 35000 * 0.025,
                    "logo": "https://logostream.dev/api/logo?symbol=SUNDAE"
                },
                {
                    "name": "AGIX",
                    "ticker": "AGIX",
                    "quantity": "3000",
                    "decimals": 8,
                    "price_usd": 0.45,
                    "value_usd": 3000 * 0.45,
                    "logo": "https://logostream.dev/api/logo?symbol=AGIX"
                },
                {
                    "name": "NMKR",
                    "ticker": "NMKR",
                    "quantity": "5000",
                    "decimals": 0,
                    "price_usd": 0.32,
                    "value_usd": 5000 * 0.32,
                    "logo": "https://logostream.dev/api/logo?symbol=NMKR"
                },
                {
                    "name": "CHARLI3",
                    "ticker": "C3",
                    "quantity": "8500",
                    "decimals": 0,
                    "price_usd": 0.18,
                    "value_usd": 8500 * 0.18,
                    "logo": "https://logostream.dev/api/logo?symbol=C3"
                },
                {
                    "name": "LQ",
                    "ticker": "LQ",
                    "quantity": "15000",
                    "decimals": 6,
                    "price_usd": 0.08,
                    "value_usd": 15000 * 0.08,
                    "logo": "https://logostream.dev/api/logo?symbol=LQ"
                },
                {
                    "name": "DJED",
                    "ticker": "DJED",
                    "quantity": "2000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 2000 * 1.0,
                    "logo": "https://logostream.dev/api/logo?symbol=DJED"
                },
                {
                    "name": "IUSD",
                    "ticker": "IUSD",
                    "quantity": "3500",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 3500 * 1.0,
                    "logo": "https://logostream.dev/api/logo?symbol=IUSD"
                },
                {
                    "name": "VYFI",
                    "ticker": "VYFI",
                    "quantity": "750",
                    "decimals": 6,
                    "price_usd": 2.5,
                    "value_usd": 750 * 2.5,
                    "logo": "https://logostream.dev/api/logo?symbol=VYFI"
                },
                {
                    "name": "OPTIM",
                    "ticker": "OPTIM",
                    "quantity": "20000",
                    "decimals": 0,
                    "price_usd": 0.05,
                    "value_usd": 20000 * 0.05,
                    "logo": "https://logostream.dev/api/logo?symbol=OPTIM"
                },
                {
                    "name": "CLAP",
                    "ticker": "CLAP",
                    "quantity": "45000",
                    "decimals": 0,
                    "price_usd": 0.015,
                    "value_usd": 45000 * 0.015,
                    "logo": "https://logostream.dev/api/logo?symbol=CLAP"
                },
                {
                    "name": "MILK",
                    "ticker": "MILK",
                    "quantity": "18000",
                    "decimals": 0,
                    "price_usd": 0.022,
                    "value_usd": 18000 * 0.022,
                    "logo": "https://logostream.dev/api/logo?symbol=MILK"
                },
                {
                    "name": "SOCIETY",
                    "ticker": "SOCIETY",
                    "quantity": "500",
                    "decimals": 0,
                    "price_usd": 5.5,
                    "value_usd": 500 * 5.5,
                    "logo": "https://logostream.dev/api/logo?symbol=SOCIETY"
                },
                {
                    "name": "CLAY",
                    "ticker": "CLAY",
                    "quantity": "1200",
                    "decimals": 0,
                    "price_usd": 3.2,
                    "value_usd": 1200 * 3.2,
                    "logo": "https://logostream.dev/api/logo?symbol=CLAY"
                },
                {
                    "name": "MYTH",
                    "ticker": "MYTH",
                    "quantity": "10000",
                    "decimals": 6,
                    "price_usd": 0.35,
                    "value_usd": 10000 * 0.35,
                    "logo": "https://logostream.dev/api/logo?symbol=MYTH"
                },
                {
                    "name": "REVUTO",
                    "ticker": "REVU",
                    "quantity": "25000",
                    "decimals": 6,
                    "price_usd": 0.018,
                    "value_usd": 25000 * 0.018,
                    "logo": "https://logostream.dev/api/logo?symbol=REVU"
                },
                {
                    "name": "HUNT",
                    "ticker": "HUNT",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.28,
                    "value_usd": 5000 * 0.28,
                    "logo": "https://logostream.dev/api/logo?symbol=HUNT"
                },
                {
                    "name": "MELD",
                    "ticker": "MELD",
                    "quantity": "30000",
                    "decimals": 6,
                    "price_usd": 0.012,
                    "value_usd": 30000 * 0.012,
                    "logo": "https://logostream.dev/api/logo?symbol=MELD"
                },
                {
                    "name": "AADA",
                    "ticker": "AADA",
                    "quantity": "8000",
                    "decimals": 0,
                    "price_usd": 0.055,
                    "value_usd": 8000 * 0.055,
                    "logo": "https://logostream.dev/api/logo?symbol=AADA"
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
                    "logo": "https://logostream.dev/api/logo?symbol=USDC"
                },
                {
                    "name": "Tether USD",
                    "ticker": "USDT",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 8000,
                    "logo": "https://logostream.dev/api/logo?symbol=USDT"
                },
                {
                    "name": "Dai Stablecoin",
                    "ticker": "DAI",
                    "quantity": "3500",
                    "decimals": 18,
                    "price_usd": 1.0,
                    "value_usd": 3500,
                    "logo": "https://logostream.dev/api/logo?symbol=DAI"
                },
                {
                    "name": "Chainlink",
                    "ticker": "LINK",
                    "quantity": "250",
                    "decimals": 18,
                    "price_usd": 18.0,
                    "value_usd": 250 * 18.0,
                    "logo": "https://logostream.dev/api/logo?symbol=LINK"
                },
                {
                    "name": "Uniswap",
                    "ticker": "UNI",
                    "quantity": "500",
                    "decimals": 18,
                    "price_usd": 8.0,
                    "value_usd": 500 * 8.0,
                    "logo": "https://logostream.dev/api/logo?symbol=UNI"
                },
                {
                    "name": "Aave",
                    "ticker": "AAVE",
                    "quantity": "35",
                    "decimals": 18,
                    "price_usd": 120.0,
                    "value_usd": 35 * 120.0,
                    "logo": "https://logostream.dev/api/logo?symbol=AAVE"
                },
                {
                    "name": "Maker",
                    "ticker": "MKR",
                    "quantity": "2.5",
                    "decimals": 18,
                    "price_usd": 2000.0,
                    "value_usd": 2.5 * 2000.0,
                    "logo": "https://logostream.dev/api/logo?symbol=MKR"
                },
                {
                    "name": "Compound",
                    "ticker": "COMP",
                    "quantity": "50",
                    "decimals": 18,
                    "price_usd": 85.0,
                    "value_usd": 50 * 85.0,
                    "logo": "https://logostream.dev/api/logo?symbol=COMP"
                },
                {
                    "name": "SushiSwap",
                    "ticker": "SUSHI",
                    "quantity": "800",
                    "decimals": 18,
                    "price_usd": 1.2,
                    "value_usd": 800 * 1.2,
                    "logo": "https://logostream.dev/api/logo?symbol=SUSHI"
                },
                {
                    "name": "Curve DAO Token",
                    "ticker": "CRV",
                    "quantity": "3000",
                    "decimals": 18,
                    "price_usd": 0.8,
                    "value_usd": 3000 * 0.8,
                    "logo": "https://logostream.dev/api/logo?symbol=CRV"
                },
                {
                    "name": "1inch",
                    "ticker": "1INCH",
                    "quantity": "1500",
                    "decimals": 18,
                    "price_usd": 0.45,
                    "value_usd": 1500 * 0.45,
                    "logo": "https://logostream.dev/api/logo?symbol=1INCH"
                },
                {
                    "name": "Polygon",
                    "ticker": "MATIC",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 0.90,
                    "value_usd": 5000 * 0.90,
                    "logo": "https://logostream.dev/api/logo?symbol=MATIC"
                },
                {
                    "name": "The Graph",
                    "ticker": "GRT",
                    "quantity": "10000",
                    "decimals": 18,
                    "price_usd": 0.25,
                    "value_usd": 10000 * 0.25,
                    "logo": "https://logostream.dev/api/logo?symbol=GRT"
                },
                {
                    "name": "Synthetix",
                    "ticker": "SNX",
                    "quantity": "400",
                    "decimals": 18,
                    "price_usd": 3.5,
                    "value_usd": 400 * 3.5,
                    "logo": "https://logostream.dev/api/logo?symbol=SNX"
                },
                {
                    "name": "Yearn Finance",
                    "ticker": "YFI",
                    "quantity": "0.5",
                    "decimals": 18,
                    "price_usd": 8000.0,
                    "value_usd": 0.5 * 8000.0,
                    "logo": "https://logostream.dev/api/logo?symbol=YFI"
                },
                {
                    "name": "Balancer",
                    "ticker": "BAL",
                    "quantity": "600",
                    "decimals": 18,
                    "price_usd": 4.2,
                    "value_usd": 600 * 4.2,
                    "logo": "https://logostream.dev/api/logo?symbol=BAL"
                },
                {
                    "name": "Wrapped Bitcoin",
                    "ticker": "WBTC",
                    "quantity": "0.1",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.1 * 98000.0,
                    "logo": "https://logostream.dev/api/logo?symbol=WBTC"
                },
                {
                    "name": "Lido Staked Ether",
                    "ticker": "stETH",
                    "quantity": "1.5",
                    "decimals": 18,
                    "price_usd": 3500.0,
                    "value_usd": 1.5 * 3500.0,
                    "logo": "https://logostream.dev/api/logo?symbol=STETH"
                },
                {
                    "name": "Rocket Pool ETH",
                    "ticker": "rETH",
                    "quantity": "0.8",
                    "decimals": 18,
                    "price_usd": 3800.0,
                    "value_usd": 0.8 * 3800.0,
                    "logo": "https://logostream.dev/api/logo?symbol=RETH"
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
                    "logo": "https://logostream.dev/api/logo?symbol=BONK"
                },
                {
                    "name": "dogwifhat",
                    "ticker": "WIF",
                    "quantity": "500",
                    "decimals": 6,
                    "price_usd": 2.5,
                    "value_usd": 500 * 2.5,
                    "logo": "https://logostream.dev/api/logo?symbol=WIF"
                },
                {
                    "name": "Pyth Network",
                    "ticker": "PYTH",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.45,
                    "value_usd": 5000 * 0.45,
                    "logo": "https://logostream.dev/api/logo?symbol=PYTH"
                },
                {
                    "name": "Jupiter",
                    "ticker": "JUP",
                    "quantity": "3000",
                    "decimals": 6,
                    "price_usd": 1.2,
                    "value_usd": 3000 * 1.2,
                    "logo": "https://logostream.dev/api/logo?symbol=JUP"
                },
                {
                    "name": "Raydium",
                    "ticker": "RAY",
                    "quantity": "1500",
                    "decimals": 6,
                    "price_usd": 3.5,
                    "value_usd": 1500 * 3.5,
                    "logo": "https://logostream.dev/api/logo?symbol=RAY"
                },
                {
                    "name": "Orca",
                    "ticker": "ORCA",
                    "quantity": "800",
                    "decimals": 6,
                    "price_usd": 4.2,
                    "value_usd": 800 * 4.2,
                    "logo": "https://logostream.dev/api/logo?symbol=ORCA"
                },
                {
                    "name": "Serum",
                    "ticker": "SRM",
                    "quantity": "2000",
                    "decimals": 6,
                    "price_usd": 0.8,
                    "value_usd": 2000 * 0.8,
                    "logo": "https://logostream.dev/api/logo?symbol=SRM"
                },
                {
                    "name": "Bonfida",
                    "ticker": "FIDA",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.35,
                    "value_usd": 5000 * 0.35,
                    "logo": "https://logostream.dev/api/logo?symbol=FIDA"
                },
                {
                    "name": "Mango Markets",
                    "ticker": "MNGO",
                    "quantity": "20000",
                    "decimals": 6,
                    "price_usd": 0.05,
                    "value_usd": 20000 * 0.05,
                    "logo": "https://logostream.dev/api/logo?symbol=MNGO"
                },
                {
                    "name": "Marinade Staked SOL",
                    "ticker": "mSOL",
                    "quantity": "50",
                    "decimals": 9,
                    "price_usd": 200.0,
                    "value_usd": 50 * 200.0,
                    "logo": "https://logostream.dev/api/logo?symbol=MSOL"
                },
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "10000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 10000,
                    "logo": "https://logostream.dev/api/logo?symbol=USDC"
                },
                {
                    "name": "Render Token",
                    "ticker": "RNDR",
                    "quantity": "400",
                    "decimals": 8,
                    "price_usd": 9.5,
                    "value_usd": 400 * 9.5,
                    "logo": "https://logostream.dev/api/logo?symbol=RNDR"
                },
                {
                    "name": "Helium",
                    "ticker": "HNT",
                    "quantity": "150",
                    "decimals": 8,
                    "price_usd": 8.2,
                    "value_usd": 150 * 8.2,
                    "logo": "https://logostream.dev/api/logo?symbol=HNT"
                },
                {
                    "name": "Star Atlas",
                    "ticker": "ATLAS",
                    "quantity": "100000",
                    "decimals": 8,
                    "price_usd": 0.004,
                    "value_usd": 100000 * 0.004,
                    "logo": "https://logostream.dev/api/logo?symbol=ATLAS"
                },
                {
                    "name": "Oxygen",
                    "ticker": "OXY",
                    "quantity": "8000",
                    "decimals": 6,
                    "price_usd": 0.015,
                    "value_usd": 8000 * 0.015,
                    "logo": "https://logostream.dev/api/logo?symbol=OXY"
                },
                {
                    "name": "Jito Staked SOL",
                    "ticker": "JitoSOL",
                    "quantity": "30",
                    "decimals": 9,
                    "price_usd": 205.0,
                    "value_usd": 30 * 205.0,
                    "logo": "https://logostream.dev/api/logo?symbol=JITOSOL"
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
                    "logo": "https://logostream.dev/api/logo?symbol=USDC"
                },
                {
                    "name": "Tether USD",
                    "ticker": "USDT",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 5000,
                    "logo": "https://logostream.dev/api/logo?symbol=USDT"
                },
                {
                    "name": "QuickSwap",
                    "ticker": "QUICK",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 0.08,
                    "value_usd": 5000 * 0.08,
                    "logo": "https://logostream.dev/api/logo?symbol=QUICK"
                },
                {
                    "name": "Aavegotchi",
                    "ticker": "GHST",
                    "quantity": "2000",
                    "decimals": 18,
                    "price_usd": 1.5,
                    "value_usd": 2000 * 1.5,
                    "logo": "https://logostream.dev/api/logo?symbol=GHST"
                },
                {
                    "name": "Stader MaticX",
                    "ticker": "MATICX",
                    "quantity": "3000",
                    "decimals": 18,
                    "price_usd": 1.1,
                    "value_usd": 3000 * 1.1,
                    "logo": "https://logostream.dev/api/logo?symbol=MATICX"
                },
                {
                    "name": "Dragon Quick",
                    "ticker": "DQUICK",
                    "quantity": "800",
                    "decimals": 18,
                    "price_usd": 0.15,
                    "value_usd": 800 * 0.15,
                    "logo": "https://logostream.dev/api/logo?symbol=DQUICK"
                },
                {
                    "name": "Wrapped Ethereum",
                    "ticker": "WETH",
                    "quantity": "1.2",
                    "decimals": 18,
                    "price_usd": 3500.0,
                    "value_usd": 1.2 * 3500.0,
                    "logo": "https://logostream.dev/api/logo?symbol=WETH"
                },
                {
                    "name": "Wrapped Bitcoin",
                    "ticker": "WBTC",
                    "quantity": "0.05",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.05 * 98000.0,
                    "logo": "https://logostream.dev/api/logo?symbol=WBTC"
                },
                {
                    "name": "Balancer",
                    "ticker": "BAL",
                    "quantity": "400",
                    "decimals": 18,
                    "price_usd": 4.2,
                    "value_usd": 400 * 4.2,
                    "logo": "https://logostream.dev/api/logo?symbol=BAL"
                },
                {
                    "name": "Curve DAO Token",
                    "ticker": "CRV",
                    "quantity": "2000",
                    "decimals": 18,
                    "price_usd": 0.8,
                    "value_usd": 2000 * 0.8,
                    "logo": "https://logostream.dev/api/logo?symbol=CRV"
                },
                {
                    "name": "SushiSwap",
                    "ticker": "SUSHI",
                    "quantity": "1000",
                    "decimals": 18,
                    "price_usd": 1.2,
                    "value_usd": 1000 * 1.2,
                    "logo": "https://logostream.dev/api/logo?symbol=SUSHI"
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
                    "logo": "https://logostream.dev/api/logo?symbol=USDC"
                },
                {
                    "name": "Dai Stablecoin",
                    "ticker": "DAI",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 1.0,
                    "value_usd": 5000,
                    "logo": "https://logostream.dev/api/logo?symbol=DAI"
                },
                {
                    "name": "Coinbase Wrapped Staked ETH",
                    "ticker": "cbETH",
                    "quantity": "0.5",
                    "decimals": 18,
                    "price_usd": 3800.0,
                    "value_usd": 0.5 * 3800.0,
                    "logo": "https://logostream.dev/api/logo?symbol=CBETH"
                },
                {
                    "name": "Wrapped Bitcoin",
                    "ticker": "WBTC",
                    "quantity": "0.02",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.02 * 98000.0,
                    "logo": "https://logostream.dev/api/logo?symbol=WBTC"
                },
                {
                    "name": "Uniswap",
                    "ticker": "UNI",
                    "quantity": "300",
                    "decimals": 18,
                    "price_usd": 8.0,
                    "value_usd": 300 * 8.0,
                    "logo": "https://logostream.dev/api/logo?symbol=UNI"
                },
                {
                    "name": "Aerodrome Finance",
                    "ticker": "AERO",
                    "quantity": "5000",
                    "decimals": 18,
                    "price_usd": 1.5,
                    "value_usd": 5000 * 1.5,
                    "logo": "https://logostream.dev/api/logo?symbol=AERO"
                },
                {
                    "name": "BaseSwap",
                    "ticker": "BSWAP",
                    "quantity": "10000",
                    "decimals": 18,
                    "price_usd": 0.25,
                    "value_usd": 10000 * 0.25,
                    "logo": "https://logostream.dev/api/logo?symbol=BSWAP"
                },
                {
                    "name": "Chainlink",
                    "ticker": "LINK",
                    "quantity": "200",
                    "decimals": 18,
                    "price_usd": 18.0,
                    "value_usd": 200 * 18.0,
                    "logo": "https://logostream.dev/api/logo?symbol=LINK"
                },
                {
                    "name": "Aave",
                    "ticker": "AAVE",
                    "quantity": "20",
                    "decimals": 18,
                    "price_usd": 120.0,
                    "value_usd": 20 * 120.0,
                    "logo": "https://logostream.dev/api/logo?symbol=AAVE"
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
                    "logo": "https://logostream.dev/api/logo?symbol=USDC",
                    "asset_id": "312769"
                },
                {
                    "name": "Planets",
                    "ticker": "PLANETS",
                    "quantity": "500000",
                    "decimals": 6,
                    "price_usd": 0.005,
                    "value_usd": 500000 * 0.005,
                    "logo": "https://logostream.dev/api/logo?symbol=PLANETS",
                    "asset_id": "27165954"
                },
                {
                    "name": "Opulous",
                    "ticker": "OPUL",
                    "quantity": "25000",
                    "decimals": 10,
                    "price_usd": 0.08,
                    "value_usd": 25000 * 0.08,
                    "logo": "https://logostream.dev/api/logo?symbol=OPUL",
                    "asset_id": "287867876"
                },
                {
                    "name": "AlgoFi Wrapped BTC",
                    "ticker": "GOBTC",
                    "quantity": "0.005",
                    "decimals": 8,
                    "price_usd": 98000.0,
                    "value_usd": 0.005 * 98000.0,
                    "logo": "https://logostream.dev/api/logo?symbol=GOBTC",
                    "asset_id": "386192725"
                },
                {
                    "name": "AlgoFi Wrapped ETH",
                    "ticker": "GOETH",
                    "quantity": "0.15",
                    "decimals": 8,
                    "price_usd": 3500.0,
                    "value_usd": 0.15 * 3500.0,
                    "logo": "https://logostream.dev/api/logo?symbol=GOETH",
                    "asset_id": "386195940"
                },
                {
                    "name": "Yieldly",
                    "ticker": "YLDY",
                    "quantity": "100000",
                    "decimals": 6,
                    "price_usd": 0.002,
                    "value_usd": 100000 * 0.002,
                    "logo": "https://logostream.dev/api/logo?symbol=YLDY",
                    "asset_id": "226701642"
                },
                {
                    "name": "Smile Coin",
                    "ticker": "SMILE",
                    "quantity": "50000",
                    "decimals": 6,
                    "price_usd": 0.0015,
                    "value_usd": 50000 * 0.0015,
                    "logo": "https://logostream.dev/api/logo?symbol=SMILE",
                    "asset_id": "300208676"
                },
                {
                    "name": "Alchemon",
                    "ticker": "ALCH",
                    "quantity": "30000",
                    "decimals": 6,
                    "price_usd": 0.01,
                    "value_usd": 30000 * 0.01,
                    "logo": "https://logostream.dev/api/logo?symbol=ALCH",
                    "asset_id": "310014962"
                },
                {
                    "name": "Tinyman",
                    "ticker": "TINY",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 0.12,
                    "value_usd": 5000 * 0.12,
                    "logo": "https://logostream.dev/api/logo?symbol=TINY",
                    "asset_id": "329110405"
                },
                {
                    "name": "Cometa",
                    "ticker": "COMET",
                    "quantity": "20000",
                    "decimals": 6,
                    "price_usd": 0.008,
                    "value_usd": 20000 * 0.008,
                    "logo": "https://logostream.dev/api/logo?symbol=COMET",
                    "asset_id": "348950369"
                },
                {
                    "name": "AlgoStake",
                    "ticker": "STKE",
                    "quantity": "10000",
                    "decimals": 6,
                    "price_usd": 0.035,
                    "value_usd": 10000 * 0.035,
                    "logo": "https://logostream.dev/api/logo?symbol=STKE",
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

        wallet = wallets[0]  # Return first demo wallet for blockchain

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
            "algorand": "ALGO"
        }
        return units.get(blockchain, "UNKNOWN")


# Global instance
demo_wallet_service = DemoWalletService()
