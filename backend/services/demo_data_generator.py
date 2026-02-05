"""
Demo Data Generator - Enhanced demo data for showcase purposes

Generates comprehensive fake data for demo accounts:
- $200K in stablecoins across all blockchains
- $300K in DeFi staking positions (real protocols)
- 90 days of portfolio history
- Proper logos for all assets
"""

from typing import Dict, List
from datetime import datetime, timedelta
import random


def generate_stablecoins() -> Dict[str, List[Dict]]:
    """
    Generate $200K worth of stablecoins across all blockchains.

    Distribution:
    - Cardano: $50K (USDC, USDT, DJED, IUSD)
    - Ethereum: $60K (USDC, USDT, DAI)
    - Solana: $40K (USDC, USDT)
    - Polygon: $30K (USDC, USDT, DAI)
    - Base: $20K (USDC, USDT)
    """
    return {
        "cardano": [
            {
                "name": "USD Coin",
                "ticker": "USDC",
                "quantity": "25000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 25000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDC"
            },
            {
                "name": "Tether USD",
                "ticker": "USDT",
                "quantity": "15000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 15000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDT"
            },
            {
                "name": "DJED Stablecoin",
                "ticker": "DJED",
                "quantity": "7500",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 7500.0,
                "logo": "https://logostream.dev/api/logo?symbol=DJED"
            },
            {
                "name": "Indigo USD",
                "ticker": "IUSD",
                "quantity": "2500",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 2500.0,
                "logo": "https://logostream.dev/api/logo?symbol=IUSD"
            }
        ],
        "ethereum": [
            {
                "name": "USD Coin",
                "ticker": "USDC",
                "quantity": "30000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 30000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDC"
            },
            {
                "name": "Tether USD",
                "ticker": "USDT",
                "quantity": "20000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 20000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDT"
            },
            {
                "name": "Dai Stablecoin",
                "ticker": "DAI",
                "quantity": "10000",
                "decimals": 18,
                "price_usd": 1.0,
                "value_usd": 10000.0,
                "logo": "https://logostream.dev/api/logo?symbol=DAI"
            }
        ],
        "solana": [
            {
                "name": "USD Coin",
                "ticker": "USDC",
                "quantity": "25000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 25000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDC"
            },
            {
                "name": "Tether USD",
                "ticker": "USDT",
                "quantity": "15000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 15000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDT"
            }
        ],
        "polygon": [
            {
                "name": "USD Coin",
                "ticker": "USDC",
                "quantity": "18000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 18000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDC"
            },
            {
                "name": "Tether USD",
                "ticker": "USDT",
                "quantity": "8000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 8000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDT"
            },
            {
                "name": "Dai Stablecoin",
                "ticker": "DAI",
                "quantity": "4000",
                "decimals": 18,
                "price_usd": 1.0,
                "value_usd": 4000.0,
                "logo": "https://logostream.dev/api/logo?symbol=DAI"
            }
        ],
        "base": [
            {
                "name": "USD Coin",
                "ticker": "USDC",
                "quantity": "15000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 15000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDC"
            },
            {
                "name": "Tether USD",
                "ticker": "USDT",
                "quantity": "5000",
                "decimals": 6,
                "price_usd": 1.0,
                "value_usd": 5000.0,
                "logo": "https://logostream.dev/api/logo?symbol=USDT"
            }
        ]
    }


def generate_defi_positions() -> Dict[str, List[Dict]]:
    """
    Generate $300K+ in DeFi staking positions across real protocols.

    Protocols:
    - Liqwid Finance (Cardano)
    - Minswap (Cardano)
    - Aave (Ethereum, Polygon)
    - Compound (Ethereum)
    - Lido (Ethereum)
    - Marinade Finance (Solana)
    - Aerodrome (Base)
    """
    return {
        "staking": [
            {
                "protocol": "Cardano Native Staking",
                "pool_name": "BLOOM Pool",
                "pool_ticker": "BLOOM",
                "blockchain": "cardano",
                "staked_amount": "85000",
                "staked_symbol": "ADA",
                "staked_amount_usd": 85000 * 1.05,  # $89,250
                "rewards_earned": "3250.50",
                "rewards_earned_usd": 3250.50 * 1.05,
                "apy": 4.5,
                "status": "active",
                "stake_address": "stake1u9xqk7fwq8q9q9q9q9q9q9q9q9q9q9q9q9q9q9q9",
                "logo": "https://logostream.dev/api/logo?symbol=ADA"
            },
            {
                "protocol": "Lido",
                "blockchain": "ethereum",
                "staked_amount": "32.5",
                "staked_symbol": "ETH",
                "staked_amount_usd": 32.5 * 3500,  # $113,750
                "rewards_earned": "1.25",
                "rewards_earned_usd": 1.25 * 3500,
                "apy": 3.8,
                "status": "active",
                "validator": "Lido Validator Pool",
                "logo": "https://logostream.dev/api/logo?symbol=LDO"
            },
            {
                "protocol": "Marinade Finance",
                "blockchain": "solana",
                "staked_amount": "550",
                "staked_symbol": "SOL",
                "staked_amount_usd": 550 * 180,  # $99,000
                "rewards_earned": "28.75",
                "rewards_earned_usd": 28.75 * 180,
                "apy": 7.2,
                "status": "active",
                "validator": "Marinade Stake Pool",
                "logo": "https://logostream.dev/api/logo?symbol=MNDE"
            }
        ],
        "lending": [
            {
                "protocol": "Liqwid Finance",
                "blockchain": "cardano",
                "position_type": "supply",
                "asset": "ADA",
                "amount": "45000",
                "amount_usd": 45000 * 1.05,  # $47,250
                "apy": 5.2,
                "rewards_earned": "625.50",
                "rewards_earned_usd": 625.50 * 1.05,
                "logo": "https://logostream.dev/api/logo?symbol=LQ"
            },
            {
                "protocol": "Aave V3",
                "blockchain": "ethereum",
                "position_type": "supply",
                "asset": "USDC",
                "amount": "35000",
                "amount_usd": 35000.0,
                "apy": 4.8,
                "rewards_earned": "485.50",
                "rewards_earned_usd": 485.50,
                "logo": "https://logostream.dev/api/logo?symbol=AAVE"
            },
            {
                "protocol": "Compound",
                "blockchain": "ethereum",
                "position_type": "supply",
                "asset": "ETH",
                "amount": "5.5",
                "amount_usd": 5.5 * 3500,  # $19,250
                "apy": 3.2,
                "rewards_earned": "0.18",
                "rewards_earned_usd": 0.18 * 3500,
                "logo": "https://logostream.dev/api/logo?symbol=COMP"
            },
            {
                "protocol": "Aave V3",
                "blockchain": "polygon",
                "position_type": "supply",
                "asset": "USDC",
                "amount": "22000",
                "amount_usd": 22000.0,
                "apy": 6.5,
                "rewards_earned": "385.75",
                "rewards_earned_usd": 385.75,
                "logo": "https://logostream.dev/api/logo?symbol=AAVE"
            }
        ],
        "liquidity": [
            {
                "protocol": "Minswap",
                "blockchain": "cardano",
                "pool": "ADA/MIN",
                "position_value_usd": 28500.00,
                "token_a": "ADA",
                "token_a_amount": "13500",
                "token_b": "MIN",
                "token_b_amount": "300000",
                "share_of_pool": 0.12,
                "apy": 22.5,
                "fees_earned_24h": 18.50,
                "fees_earned_total": 2150.75,
                "impermanent_loss": -0.8,
                "logo": "https://logostream.dev/api/logo?symbol=MIN"
            },
            {
                "protocol": "Uniswap V3",
                "blockchain": "ethereum",
                "pool": "ETH/USDC",
                "position_value_usd": 42000.00,
                "token_a": "ETH",
                "token_a_amount": "6.0",
                "token_b": "USDC",
                "token_b_amount": "21000",
                "share_of_pool": 0.05,
                "apy": 15.8,
                "fees_earned_24h": 25.00,
                "fees_earned_total": 3250.00,
                "impermanent_loss": -1.2,
                "logo": "https://logostream.dev/api/logo?symbol=UNI"
            },
            {
                "protocol": "Aerodrome",
                "blockchain": "base",
                "pool": "ETH/USDC",
                "position_value_usd": 18000.00,
                "token_a": "ETH",
                "token_a_amount": "2.57",
                "token_b": "USDC",
                "token_b_amount": "9000",
                "share_of_pool": 0.08,
                "apy": 28.5,
                "fees_earned_24h": 12.50,
                "fees_earned_total": 950.00,
                "impermanent_loss": -0.5,
                "logo": "https://logostream.dev/api/logo?symbol=AERO"
            }
        ],
        "farming": [
            {
                "protocol": "SundaeSwap",
                "blockchain": "cardano",
                "farm": "ADA/SUNDAE LP Staking",
                "staked_amount_usd": 15000.00,
                "rewards_token": "SUNDAE",
                "rewards_earned": "18500",
                "rewards_earned_usd": 18500 * 0.025,
                "apy": 18.5,
                "status": "active",
                "logo": "https://logostream.dev/api/logo?symbol=SUNDAE"
            },
            {
                "protocol": "WingRiders",
                "blockchain": "cardano",
                "farm": "ADA/WRT LP Farming",
                "staked_amount_usd": 12500.00,
                "rewards_token": "WRT",
                "rewards_earned": "850",
                "rewards_earned_usd": 850 * 0.28,
                "apy": 16.2,
                "status": "active",
                "logo": "https://logostream.dev/api/logo?symbol=WRT"
            }
        ]
    }


def generate_portfolio_history(days: int = 90) -> List[Dict]:
    """
    Generate fake portfolio history for charts.

    Creates realistic-looking portfolio value progression over time
    with some volatility and general upward trend.

    Args:
        days: Number of days of history (default 90)

    Returns:
        List of daily portfolio snapshots
    """
    history = []

    # Starting portfolio value
    starting_value = 450000.0  # $450K
    current_value = starting_value

    # Target ending value (show growth)
    ending_value = 650000.0  # $650K

    # Calculate daily growth rate for smooth trend
    daily_growth_rate = (ending_value / starting_value) ** (1 / days) - 1

    for i in range(days):
        date = datetime.now() - timedelta(days=days - i - 1)

        # Apply growth trend
        current_value *= (1 + daily_growth_rate)

        # Add realistic volatility (+/- 5%)
        volatility = random.uniform(-0.05, 0.05)
        daily_value = current_value * (1 + volatility)

        # Calculate breakdown (realistic proportions)
        ada_value = daily_value * 0.28
        btc_value = daily_value * 0.18
        eth_value = daily_value * 0.22
        sol_value = daily_value * 0.15
        matic_value = daily_value * 0.05
        algo_value = daily_value * 0.02
        stablecoins_value = daily_value * 0.10  # $200K in stablecoins

        history.append({
            "snapshot_date": date.date().isoformat(),
            "total_value_usd": round(daily_value, 2),
            "self_custody_value_usd": round(daily_value * 0.65, 2),
            "exchange_value_usd": round(daily_value * 0.20, 2),
            "nft_value_usd": round(daily_value * 0.08, 2),
            "defi_value_usd": round(daily_value * 0.07, 2),
            "native_values": {
                "ada": round(ada_value / 1.05, 2),  # Convert USD to ADA
                "btc": round(btc_value / 98000, 8),
                "eth": round(eth_value / 3500, 6),
                "sol": round(sol_value / 180, 4),
                "matic": round(matic_value / 0.90, 2),
                "algo": round(algo_value / 0.35, 2)
            },
            "blockchain_breakdown": {
                "cardano": round(ada_value, 2),
                "bitcoin": round(btc_value, 2),
                "ethereum": round(eth_value, 2),
                "solana": round(sol_value, 2),
                "polygon": round(matic_value, 2),
                "algorand": round(algo_value, 2)
            }
        })

    return history


def get_blockchain_logos() -> Dict[str, str]:
    """
    Get logo URLs for all supported blockchains.

    Returns:
        Dict mapping blockchain name to logo URL
    """
    return {
        "cardano": "https://logostream.dev/api/logo?symbol=ADA",
        "bitcoin": "https://logostream.dev/api/logo?symbol=BTC",
        "ethereum": "https://logostream.dev/api/logo?symbol=ETH",
        "solana": "https://logostream.dev/api/logo?symbol=SOL",
        "polygon": "https://logostream.dev/api/logo?symbol=MATIC",
        "base": "https://logostream.dev/api/logo?symbol=ETH",  # Base uses ETH
        "algorand": "https://logostream.dev/api/logo?symbol=ALGO"
    }


def get_total_demo_value() -> Dict[str, float]:
    """
    Calculate total demo portfolio value across all categories.

    Returns:
        Dict with breakdown of total values
    """
    stablecoins = generate_stablecoins()
    defi = generate_defi_positions()

    # Calculate stablecoin total
    stablecoin_total = sum(
        sum(token["value_usd"] for token in tokens)
        for tokens in stablecoins.values()
    )

    # Calculate DeFi total
    staking_total = sum(pos["staked_amount_usd"] for pos in defi["staking"])
    lending_total = sum(pos["amount_usd"] for pos in defi["lending"])
    liquidity_total = sum(pos["position_value_usd"] for pos in defi["liquidity"])
    farming_total = sum(pos["staked_amount_usd"] for pos in defi["farming"])

    defi_total = staking_total + lending_total + liquidity_total + farming_total

    return {
        "stablecoins_total_usd": round(stablecoin_total, 2),
        "defi_total_usd": round(defi_total, 2),
        "staking_usd": round(staking_total, 2),
        "lending_usd": round(lending_total, 2),
        "liquidity_usd": round(liquidity_total, 2),
        "farming_usd": round(farming_total, 2)
    }


# Module test
if __name__ == "__main__":
    print("=== Demo Data Generator Test ===\n")

    totals = get_total_demo_value()
    print(f"Stablecoins Total: ${totals['stablecoins_total_usd']:,.2f}")
    print(f"DeFi Total: ${totals['defi_total_usd']:,.2f}")
    print(f"  - Staking: ${totals['staking_usd']:,.2f}")
    print(f"  - Lending: ${totals['lending_usd']:,.2f}")
    print(f"  - Liquidity: ${totals['liquidity_usd']:,.2f}")
    print(f"  - Farming: ${totals['farming_usd']:,.2f}")

    print(f"\nPortfolio History: {len(generate_portfolio_history())} days generated")
    print(f"Blockchain Logos: {len(get_blockchain_logos())} chains configured")

    print("\n✓ Demo data generator ready!")
