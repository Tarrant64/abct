#!/usr/bin/env python3
"""
Backfill Portfolio History Script

Generates 90 days of historical portfolio snapshots using simulated price variations.
Since we don't have historical pricing data APIs for free, we'll use the current
portfolio structure and apply realistic price variations to create historical data.
"""

import sys
import os
import asyncio
import aiosqlite
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import random

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (
    get_all_wallets,
    get_wallet_balance
)
from config import DATABASE_PATH
from services.pricing import pricing_service

CT_TIMEZONE = ZoneInfo("America/Chicago")


def generate_price_variation(current_price: float, days_ago: int) -> float:
    """
    Generate realistic price variation for historical data.

    Uses a combination of:
    - Random walk (daily volatility)
    - Trend component (slight upward bias to match crypto markets)
    - Seasonal variation

    Args:
        current_price: Current price of the asset
        days_ago: Number of days in the past

    Returns:
        Simulated historical price
    """
    if current_price == 0:
        return 0

    # Start from current price and walk backwards
    price = current_price

    # Apply random walk backwards (each day has 2-5% volatility)
    for _ in range(days_ago):
        daily_change = random.uniform(-0.05, 0.05)  # -5% to +5%

        # Add slight downward bias for going back in time (crypto tends to trend up)
        trend = -0.001  # -0.1% per day average

        # Add some mean reversion
        deviation = (price - current_price) / current_price
        reversion = -deviation * 0.1

        total_change = daily_change + trend + reversion
        price *= (1 + total_change)

    # Ensure price doesn't go negative or absurdly low
    return max(price, current_price * 0.3)  # No less than 30% of current


async def get_current_portfolio_state(user_id: int):
    """Get current portfolio holdings and all component values."""
    import httpx
    from routers.portfolio import calculate_wallet_native_assets_value
    from services.nft import nft_service

    # Get wallet holdings
    wallets = await get_all_wallets(user_id=user_id)

    portfolio = {
        'ada_amount': 0.0,
        'btc_amount': 0.0,
        'eth_amount': 0.0,
        'sol_amount': 0.0,
        'wallets': wallets,
        # Current USD values for historical snapshots
        'staking_value_usd': 0.0,
        'defi_value_usd': 0.0,
        'exchange_value_usd': 0.0,
        'nft_value_usd': 0.0,
        'tracked_tokens_value_usd': 0.0
    }

    for wallet in wallets:
        balance_info = await get_wallet_balance(wallet['id'])
        balance = float(balance_info['amount']) if balance_info else 0.0

        blockchain = wallet['blockchain']
        if blockchain == 'cardano':
            portfolio['ada_amount'] += balance
        elif blockchain == 'bitcoin':
            portfolio['btc_amount'] += balance
        elif blockchain == 'ethereum' or blockchain == 'base':
            portfolio['eth_amount'] += balance
        elif blockchain == 'solana':
            portfolio['sol_amount'] += balance
        # Note: Polygon not tracked in snapshots currently

    # Fetch current component values using the same functions as the snapshot service
    print(f"\n   Calculating native assets (tracked tokens) value...")
    try:
        # Calculate native assets value per wallet (uses TapTools pricing)
        for wallet in wallets:
            value = await calculate_wallet_native_assets_value(wallet['id'], wallet['blockchain'], user_id)
            if value > 0:
                portfolio['tracked_tokens_value_usd'] += value
                print(f"     Wallet {wallet['id']} ({wallet['blockchain']}): ${value:,.2f}")
    except Exception as e:
        print(f"   Warning: Error calculating native assets value: {e}")

    # Get NFT value using NFT service
    print(f"\n   Calculating NFT value...")
    try:
        nft_summary = await nft_service.get_nft_summary(user_id=user_id)
        nft_value_ada = nft_summary.get('total_value_ada', 0)
        ada_price = await pricing_service.get_price('ADA')
        portfolio['nft_value_usd'] = nft_value_ada * ada_price
        print(f"     {nft_summary.get('total_nfts', 0)} NFTs = {nft_value_ada:,.2f} ADA = ${portfolio['nft_value_usd']:,.2f}")
    except Exception as e:
        print(f"   Warning: Error calculating NFT value: {e}")

    # Check for cached exchange/staking/defi values
    try:
        from database import get_cache

        # Exchange value
        coinbase = await get_cache('coinbase_portfolio', user_id=user_id)
        if coinbase:
            portfolio['exchange_value_usd'] = float(coinbase.get('total_usd', 0))
            print(f"\n   Exchange (Coinbase): ${portfolio['exchange_value_usd']:,.2f}")

        # DeFi value
        defi = await get_cache('defi_summary', user_id=user_id)
        if defi:
            portfolio['defi_value_usd'] = float(defi.get('total_value_usd', 0))
            print(f"   DeFi: ${portfolio['defi_value_usd']:,.2f}")
    except Exception as e:
        print(f"   Warning: Error fetching cached values: {e}")

    return portfolio


async def backfill_snapshots(user_id: int, days: int = 90):
    """
    Backfill historical portfolio snapshots.

    Args:
        user_id: User ID to backfill data for
        days: Number of days to backfill (default: 90)
    """
    print(f"🔄 Starting backfill of {days} days of portfolio history for user {user_id}...")

    # Get current prices
    print("📊 Fetching current prices...")
    current_prices = {
        'ADA': await pricing_service.get_price('ADA'),
        'BTC': await pricing_service.get_price('BTC'),
        'ETH': await pricing_service.get_price('ETH'),
        'SOL': await pricing_service.get_price('SOL')
    }

    print(f"   Current prices: ADA=${current_prices['ADA']:.3f}, BTC=${current_prices['BTC']:,.0f}, ETH=${current_prices['ETH']:,.0f}")

    # Get current portfolio amounts
    print("💼 Fetching current portfolio holdings...")
    portfolio = await get_current_portfolio_state(user_id)

    print(f"   Holdings: {portfolio['ada_amount']:.2f} ADA, {portfolio['btc_amount']:.8f} BTC, {portfolio['eth_amount']:.4f} ETH")

    print(f"💰 Fetching current component values...")
    print(f"   Staking: ${portfolio['staking_value_usd']:,.2f}")
    print(f"   DeFi: ${portfolio['defi_value_usd']:,.2f}")
    print(f"   Exchanges: ${portfolio['exchange_value_usd']:,.2f}")
    print(f"   NFTs: ${portfolio['nft_value_usd']:,.2f}")
    print(f"   Tracked Tokens: ${portfolio['tracked_tokens_value_usd']:,.2f}")

    total_components = (
        portfolio['staking_value_usd'] +
        portfolio['defi_value_usd'] +
        portfolio['exchange_value_usd'] +
        portfolio['nft_value_usd'] +
        portfolio['tracked_tokens_value_usd']
    )
    print(f"   Total Components Value: ${total_components:,.2f}")
    print(f"   (These values will be used consistently across all historical snapshots)")

    # Get existing snapshots to avoid duplicates
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT snapshot_date FROM portfolio_snapshots WHERE user_id = ?",
            (user_id,)
        )
        existing_dates = {row[0] for row in await cursor.fetchall()}

    print(f"   Found {len(existing_dates)} existing snapshots, will skip those dates")

    # Generate snapshots for each day
    snapshots_created = 0
    now_ct = datetime.now(CT_TIMEZONE)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        for day_offset in range(days):
            # Calculate snapshot date (going backwards from today)
            snapshot_dt = now_ct - timedelta(days=day_offset)
            snapshot_date = str(snapshot_dt.date())

            # Skip if snapshot already exists
            if snapshot_date in existing_dates:
                continue

            # Set snapshot time to noon CT for consistency
            snapshot_time = snapshot_dt.replace(hour=12, minute=0, second=0, microsecond=0)

            # Generate historical prices
            historical_prices = {
                'ADA': generate_price_variation(current_prices['ADA'], day_offset),
                'BTC': generate_price_variation(current_prices['BTC'], day_offset),
                'ETH': generate_price_variation(current_prices['ETH'], day_offset),
                'SOL': generate_price_variation(current_prices['SOL'], day_offset)
            }

            # Calculate portfolio value at historical prices (native coins)
            native_coins_value = (
                portfolio['ada_amount'] * historical_prices['ADA'] +
                portfolio['btc_amount'] * historical_prices['BTC'] +
                portfolio['eth_amount'] * historical_prices['ETH'] +
                portfolio['sol_amount'] * historical_prices['SOL']
            )

            # Use current values for all components (we don't have historical data for these)
            # These values remain constant across all historical snapshots
            staking_value = portfolio['staking_value_usd']
            defi_value = portfolio['defi_value_usd']
            exchange_value = portfolio['exchange_value_usd']
            nft_value = portfolio['nft_value_usd']
            tracked_tokens_value = portfolio['tracked_tokens_value_usd']

            # Calculate total portfolio value (all components)
            total_value_usd = (
                native_coins_value +
                staking_value +
                defi_value +
                exchange_value +
                nft_value +
                tracked_tokens_value
            )

            # Insert snapshot
            await db.execute("""
                INSERT OR REPLACE INTO portfolio_snapshots (
                    user_id, snapshot_date, snapshot_time,
                    total_value_usd,
                    ada_amount, ada_price,
                    btc_amount, btc_price,
                    eth_amount, eth_price,
                    sol_amount, sol_price,
                    staking_value_usd, defi_value_usd,
                    exchange_value_usd, nft_value_usd,
                    tracked_tokens_value_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, snapshot_date, snapshot_time.isoformat(),
                total_value_usd,
                portfolio['ada_amount'], historical_prices['ADA'],
                portfolio['btc_amount'], historical_prices['BTC'],
                portfolio['eth_amount'], historical_prices['ETH'],
                portfolio['sol_amount'], historical_prices['SOL'],
                staking_value, defi_value,
                exchange_value, nft_value,
                tracked_tokens_value
            ))

            snapshots_created += 1

            # Progress indicator
            if snapshots_created % 10 == 0:
                print(f"   ✓ Created {snapshots_created} snapshots...")

        await db.commit()

    print(f"\n✅ Backfill complete! Created {snapshots_created} new snapshots")
    print(f"   Total snapshots for user {user_id}: {len(existing_dates) + snapshots_created}")

    # Show sample data
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT snapshot_date, total_value_usd
            FROM portfolio_snapshots
            WHERE user_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 5
        """, (user_id,))
        rows = await cursor.fetchall()

        print("\n📈 Most recent snapshots:")
        for date, value in rows:
            print(f"   {date}: ${value:,.2f}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Backfill portfolio history snapshots')
    parser.add_argument('--user-id', type=int, default=1, help='User ID to backfill (default: 1)')
    parser.add_argument('--days', type=int, default=90, help='Number of days to backfill (default: 90)')

    args = parser.parse_args()

    print("=" * 60)
    print("Portfolio History Backfill Script")
    print("=" * 60)
    print()

    try:
        await backfill_snapshots(args.user_id, args.days)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n" + "=" * 60)
    print("🎉 Backfill completed successfully!")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
