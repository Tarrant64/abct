#!/usr/bin/env python3
"""
Create Demo Account with Fake Portfolio Data

This script creates a demo user account with realistic fake data totaling ~$1M portfolio.
Includes wallets across multiple blockchains, DeFi positions, NFTs, and 90 days of historical data.

Usage:
    cd backend
    python scripts/create_demo_account.py
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import random
import bcrypt
import aiosqlite

# Add parent directory to path to import config and database
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATABASE_PATH

# Demo account credentials
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo"

# Realistic cryptocurrency prices (approximate)
CRYPTO_PRICES = {
    "ADA": 0.95,  # Cardano
    "BTC": 55000,  # Bitcoin
    "ETH": 3000,   # Ethereum
    "SOL": 140,    # Solana
    "POL": 0.75,   # Polygon (MATIC)
}

# Realistic wallet addresses
DEMO_WALLETS = [
    # Cardano wallets (~$150k)
    {
        "address": "addr1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0p3zax2s0q7ht4xp2x5uc9w8uu8w3v5z6vwugz5uzgqpdp7zt5ewkh6xqknj6jd",
        "blockchain": "cardano",
        "label": "Cardano Main Wallet",
        "native_balance": "50000",  # 50,000 ADA
        "native_assets": [
            {
                "asset_id": "d5e6bf0500378d4f0da4e8dde6becec7621cd8cbf5cbb9b87013d4cc4d494e",
                "policy_id": "d5e6bf0500378d4f0da4e8dde6becec7621cd8cbf5cbb9b87013d4cc",
                "asset_name": "4d494e",
                "quantity": "100000",
                "decimals": 6
            },
            {
                "asset_id": "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff935574d54",
                "policy_id": "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff935",
                "asset_name": "574d54",
                "quantity": "5000",
                "decimals": 6
            }
        ]
    },
    {
        "address": "stake1uy6et9pvlul564euu3t39lvjv8fk49c5v9p8y4s8z5u5jvgkz5hp6",
        "blockchain": "cardano",
        "label": "Cardano Staking Wallet",
        "native_balance": "30000",  # 30,000 ADA staked
        "native_assets": []
    },
    {
        "address": "addr1q9f8h9j4k2l3m4n5o6p7q8r9s0t1u2v3w4x5y6z7a8b9c0d1e2f3g4h5i6j7k8",
        "blockchain": "cardano",
        "label": "Cardano Secondary Wallet",
        "native_balance": "20000",  # 20,000 ADA
        "native_assets": []
    },

    # Bitcoin wallets (~$200k)
    {
        "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0p3z",
        "blockchain": "bitcoin",
        "label": "Bitcoin Main Wallet",
        "native_balance": "2.1",  # 2.1 BTC
        "native_assets": []
    },
    {
        "address": "bc1p5d7rjq7g6rdk2yhzks9smlaqtedr4dekq08ge8ztwac72sfr9rusxg3297",
        "blockchain": "bitcoin",
        "label": "Bitcoin Cold Storage",
        "native_balance": "1.5",  # 1.5 BTC
        "native_assets": []
    },

    # Ethereum wallets (~$120k)
    {
        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1",
        "blockchain": "ethereum",
        "label": "Ethereum Main Wallet",
        "native_balance": "22",  # 22 ETH
        "native_assets": [
            {
                "asset_id": "0xdac17f958d2ee523a2206206994597c13d831ec7",
                "policy_id": "0xdac17f958d2ee523a2206206994597c13d831ec7",
                "asset_name": "USDT",
                "quantity": "10000",
                "decimals": 6
            },
            {
                "asset_id": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "policy_id": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "asset_name": "USDC",
                "quantity": "5000",
                "decimals": 6
            }
        ]
    },
    {
        "address": "0x8e7D3c7B3e4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A",
        "blockchain": "ethereum",
        "label": "Ethereum DeFi Wallet",
        "native_balance": "18",  # 18 ETH
        "native_assets": []
    },

    # Solana wallets (~$80k)
    {
        "address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
        "blockchain": "solana",
        "label": "Solana Main Wallet",
        "native_balance": "800",  # 800 SOL
        "native_assets": [
            {
                "asset_id": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "policy_id": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "asset_name": "USDC",
                "quantity": "3000",
                "decimals": 6
            }
        ]
    },
    {
        "address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        "blockchain": "solana",
        "label": "Solana NFT Wallet",
        "native_balance": "600",  # 600 SOL
        "native_assets": []
    },

    # Polygon wallet (~$30k)
    {
        "address": "0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        "blockchain": "polygon",
        "label": "Polygon Main Wallet",
        "native_balance": "40000",  # 40,000 POL
        "native_assets": []
    },

    # Base wallet (~$20k)
    {
        "address": "0x9f8e7d6c5b4a3928170e1f2d3c4b5a6978e9d0c1",
        "blockchain": "base",
        "label": "Base Main Wallet",
        "native_balance": "8",  # 8 ETH on Base
        "native_assets": []
    },
]

# NFT Collections (~$150k total)
NFT_COLLECTIONS = [
    {
        "policy_id": "40fa2aa67258b4ce7b5782f74831d46a84c59a0ff0c28262fab21728",
        "collection_name": "Clay Nation",
        "count": 15,
        "floor_price_ada": 3500,  # ~$50k total
        "blockchain": "cardano"
    },
    {
        "policy_id": "4523c5e21d409b81c95b45b0aea275b8ea1406e6cafea5583b9f8a5f",
        "collection_name": "The Ape Society",
        "count": 8,
        "floor_price_ada": 5000,  # ~$40k total
        "blockchain": "cardano"
    },
    {
        "policy_id": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d",
        "collection_name": "Bored Ape Yacht Club",
        "count": 12,
        "floor_price_ada": 2500,  # ~$30k total (simplified pricing)
        "blockchain": "ethereum"
    },
    {
        "policy_id": "solana_smb_gen2",
        "collection_name": "Solana Monkey Business",
        "count": 20,
        "floor_price_ada": 1000,  # ~$20k total
        "blockchain": "solana"
    },
]


async def create_demo_user():
    """Create the demo user in the database. Returns the user ID."""
    print(f"\n{'='*60}")
    print("Creating Demo User Account")
    print(f"{'='*60}")

    # Hash the password with bcrypt
    password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode('utf-8'), bcrypt.gensalt())

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if demo user already exists
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?",
            (DEMO_USERNAME,)
        )
        existing = await cursor.fetchone()

        if existing:
            demo_user_id = existing[0]
            print(f"⚠️  Demo user '{DEMO_USERNAME}' already exists (ID: {demo_user_id})")
            print("   Deleting existing demo data and recreating...")
            # Delete existing demo wallets and snapshots
            await db.execute("DELETE FROM wallets WHERE user_id = ?", (demo_user_id,))
            await db.execute("DELETE FROM portfolio_snapshots WHERE user_id = ?", (demo_user_id,))
            await db.execute("DELETE FROM users WHERE username = ?", (DEMO_USERNAME,))
            await db.commit()

        # Add is_demo column if it doesn't exist
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER DEFAULT 0")
            await db.commit()
        except:
            pass  # Column already exists

        # Create demo user
        cursor = await db.execute(
            """INSERT INTO users (username, password_hash, password_changed, is_demo)
               VALUES (?, ?, 1, 1)""",
            (DEMO_USERNAME, password_hash.decode('utf-8'))
        )
        demo_user_id = cursor.lastrowid
        await db.commit()

        print(f"✓ Demo user created successfully (ID: {demo_user_id})")
        print(f"  Username: {DEMO_USERNAME}")
        print(f"  Password: {DEMO_PASSWORD}")
        print(f"  Password Changed: Yes (no prompt on login)")
        print(f"  Demo Flag: Yes")

        return demo_user_id


async def create_demo_wallets(user_id):
    """Create demo wallets with balances and native assets for the specified user."""
    print(f"\n{'='*60}")
    print("Creating Demo Wallets")
    print(f"{'='*60}")

    total_value_usd = 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        for wallet_data in DEMO_WALLETS:
            address = wallet_data["address"]
            blockchain = wallet_data["blockchain"]
            label = wallet_data["label"]
            native_balance = wallet_data["native_balance"]
            native_assets = wallet_data.get("native_assets", [])

            # Check if wallet exists for this user
            cursor = await db.execute(
                "SELECT id FROM wallets WHERE address = ? AND blockchain = ? AND user_id = ?",
                (address, blockchain, user_id)
            )
            existing = await cursor.fetchone()

            if existing:
                wallet_id = existing[0]
                # Update existing wallet
                await db.execute(
                    "UPDATE wallets SET label = ?, updated_at = ? WHERE id = ?",
                    (label, datetime.now(), wallet_id)
                )
            else:
                # Insert new wallet WITH user_id
                cursor = await db.execute(
                    "INSERT INTO wallets (user_id, address, blockchain, label, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, address, blockchain, label, datetime.now(), datetime.now())
                )
                wallet_id = cursor.lastrowid

            # Clear existing balances and assets
            await db.execute("DELETE FROM balances WHERE wallet_id = ?", (wallet_id,))
            await db.execute("DELETE FROM native_assets WHERE wallet_id = ?", (wallet_id,))

            # Add native balance
            unit = blockchain.upper()
            if blockchain == "cardano":
                unit = "lovelace"
            elif blockchain in ["ethereum", "base"]:
                unit = "wei"
            elif blockchain == "polygon":
                unit = "POL"

            await db.execute(
                "INSERT INTO balances (wallet_id, amount, unit, updated_at) VALUES (?, ?, ?, ?)",
                (wallet_id, native_balance, unit, datetime.now())
            )

            # Calculate value in USD
            price = CRYPTO_PRICES.get(blockchain.upper()[:3], 0)
            if blockchain == "cardano":
                price = CRYPTO_PRICES["ADA"]
            elif blockchain in ["ethereum", "base"]:
                price = CRYPTO_PRICES["ETH"]
            elif blockchain == "polygon":
                price = CRYPTO_PRICES["POL"]
            elif blockchain == "solana":
                price = CRYPTO_PRICES["SOL"]

            balance_float = float(native_balance)
            value_usd = balance_float * price
            total_value_usd += value_usd

            # Add native assets (tokens, NFTs)
            for asset in native_assets:
                await db.execute(
                    """INSERT INTO native_assets (wallet_id, asset_id, policy_id, asset_name, quantity, decimals, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (wallet_id, asset["asset_id"], asset["policy_id"], asset["asset_name"],
                     asset["quantity"], asset.get("decimals", 0), datetime.now())
                )

            print(f"✓ {label}")
            print(f"  Address: {address[:20]}...")
            print(f"  Blockchain: {blockchain.upper()}")
            print(f"  Balance: {native_balance} {unit}")
            print(f"  Value: ${value_usd:,.2f}")
            if native_assets:
                print(f"  Native Assets: {len(native_assets)} tokens")

        await db.commit()

    print(f"\n📊 Total Wallet Value: ${total_value_usd:,.2f}")
    return total_value_usd


async def create_demo_nfts(user_id):
    """Create demo NFT collections with floor prices for the specified user."""
    print(f"\n{'='*60}")
    print("Creating Demo NFT Collections")
    print(f"{'='*60}")

    total_nft_value_usd = 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Get a Cardano wallet for NFT ownership (from demo user's wallets only)
        cursor = await db.execute(
            "SELECT id FROM wallets WHERE blockchain = 'cardano' AND user_id = ? LIMIT 1",
            (user_id,)
        )
        cardano_wallet = await cursor.fetchone()

        if not cardano_wallet:
            print(f"⚠️  No Cardano wallet found for user {user_id}, skipping NFT creation")
            return 0

        wallet_id = cardano_wallet[0]

        for collection in NFT_COLLECTIONS:
            policy_id = collection["policy_id"]
            collection_name = collection["collection_name"]
            count = collection["count"]
            floor_price_ada = collection["floor_price_ada"]

            # Add NFTs to native_assets (quantity=1 for NFTs)
            for i in range(count):
                asset_name = f"{collection_name}_{i+1:04d}"
                asset_id = f"{policy_id}{asset_name}"

                await db.execute(
                    """INSERT OR REPLACE INTO native_assets (wallet_id, asset_id, policy_id, asset_name, quantity, decimals, updated_at)
                       VALUES (?, ?, ?, ?, '1', 0, ?)""",
                    (wallet_id, asset_id, policy_id, asset_name, datetime.now())
                )

            # Add floor price data
            floor_price_usd = floor_price_ada * CRYPTO_PRICES["ADA"]
            collection_value = floor_price_usd * count
            total_nft_value_usd += collection_value

            await db.execute(
                """INSERT OR REPLACE INTO nft_floor_prices
                   (policy_id, collection_name, floor_price_ada, listings, supply, verified, source, fetched_at)
                   VALUES (?, ?, ?, ?, ?, 1, 'demo', ?)""",
                (policy_id, collection_name, floor_price_ada, 50, count * 10, datetime.now())
            )

            print(f"✓ {collection_name}")
            print(f"  Count: {count} NFTs")
            print(f"  Floor Price: {floor_price_ada:,.0f} ADA (${floor_price_usd:,.2f})")
            print(f"  Total Value: ${collection_value:,.2f}")

        await db.commit()

    print(f"\n🖼️  Total NFT Value: ${total_nft_value_usd:,.2f}")
    return total_nft_value_usd


async def create_historical_data(user_id, wallet_value: float, nft_value: float):
    """Generate 90 days of historical portfolio snapshots for the specified user."""
    print(f"\n{'='*60}")
    print("Generating Historical Portfolio Data (90 days)")
    print(f"{'='*60}")

    # DeFi and Exchange values (~$250k)
    defi_base = 150000  # DeFi positions
    exchange_base = 100000  # Exchange holdings
    staking_base = 30000  # Staking rewards

    # Target values
    final_total = wallet_value + nft_value + defi_base + exchange_base + staking_base
    initial_total = final_total * 0.85  # Start at 85% of final value

    print(f"Initial Portfolio Value: ${initial_total:,.2f}")
    print(f"Final Portfolio Value: ${final_total:,.2f}")
    print(f"Growth: ${final_total - initial_total:,.2f} ({((final_total/initial_total - 1) * 100):.1f}%)")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Clear existing snapshots for THIS user only
        await db.execute("DELETE FROM portfolio_snapshots WHERE user_id = ?", (user_id,))

        # Generate 90 days of data
        for days_ago in range(90, -1, -1):
            snapshot_date = (datetime.now() - timedelta(days=days_ago)).date()
            snapshot_time = datetime.now() - timedelta(days=days_ago)

            # Calculate progressive growth with realistic fluctuations
            progress = 1 - (days_ago / 90)
            trend_value = initial_total + (final_total - initial_total) * progress

            # Add daily volatility (±3%)
            daily_volatility = random.uniform(-0.03, 0.03)
            total_value = trend_value * (1 + daily_volatility)

            # Calculate asset amounts based on current prices
            ada_amount = (wallet_value * 0.15) / CRYPTO_PRICES["ADA"]  # 15% in ADA
            btc_amount = (wallet_value * 0.20) / CRYPTO_PRICES["BTC"]  # 20% in BTC
            eth_amount = (wallet_value * 0.12) / CRYPTO_PRICES["ETH"]  # 12% in ETH
            sol_amount = (wallet_value * 0.08) / CRYPTO_PRICES["SOL"]  # 8% in SOL

            # Add slight variations to crypto amounts
            ada_amount *= (1 + random.uniform(-0.02, 0.02))
            btc_amount *= (1 + random.uniform(-0.02, 0.02))
            eth_amount *= (1 + random.uniform(-0.02, 0.02))
            sol_amount *= (1 + random.uniform(-0.02, 0.02))

            # Vary DeFi, staking, exchange values
            defi_value = defi_base * (1 + random.uniform(-0.05, 0.05))
            staking_value = staking_base * (1 + random.uniform(-0.02, 0.02))
            exchange_value = exchange_base * (1 + random.uniform(-0.04, 0.04))
            nft_value_day = nft_value * (1 + random.uniform(-0.03, 0.03))

            # Insert snapshot with user_id
            await db.execute(
                """INSERT INTO portfolio_snapshots
                   (user_id, snapshot_date, snapshot_time, total_value_usd,
                    ada_amount, ada_price, btc_amount, btc_price, eth_amount, eth_price, sol_amount, sol_price,
                    staking_value_usd, defi_value_usd, exchange_value_usd, nft_value_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, snapshot_date, snapshot_time.isoformat(), total_value,
                 ada_amount, CRYPTO_PRICES["ADA"],
                 btc_amount, CRYPTO_PRICES["BTC"],
                 eth_amount, CRYPTO_PRICES["ETH"],
                 sol_amount, CRYPTO_PRICES["SOL"],
                 staking_value, defi_value, exchange_value, nft_value_day)
            )

        await db.commit()

    print(f"✓ Generated 90 daily snapshots")
    print(f"  Date Range: {(datetime.now() - timedelta(days=90)).date()} to {datetime.now().date()}")
    print(f"  Includes realistic volatility and growth trends")


async def main():
    """Main function to create demo account with all data."""
    print("\n" + "="*60)
    print("ABCT Demo Account Creation Script")
    print("="*60)

    # Check if database exists
    if not DATABASE_PATH.exists():
        print(f"\n❌ Error: Database not found at {DATABASE_PATH}")
        print("   Please run the main application first to initialize the database.")
        return

    print(f"\n📁 Database: {DATABASE_PATH}")

    try:
        # Create demo user and get the user ID
        demo_user_id = await create_demo_user()

        # Create demo wallets for this user
        wallet_value = await create_demo_wallets(demo_user_id)

        # Create demo NFTs for this user
        nft_value = await create_demo_nfts(demo_user_id)

        # Create historical data for this user
        await create_historical_data(demo_user_id, wallet_value, nft_value)

        # Summary
        print(f"\n{'='*60}")
        print("✅ Demo Account Created Successfully!")
        print(f"{'='*60}")
        print(f"\n📊 Portfolio Summary:")
        print(f"   Wallets: ${wallet_value:,.2f}")
        print(f"   NFTs: ${nft_value:,.2f}")
        print(f"   DeFi Positions: ~$150,000")
        print(f"   Exchange Holdings: ~$100,000")
        print(f"   Staking Rewards: ~$30,000")
        print(f"   {'─'*40}")
        print(f"   Total Portfolio: ~$1,000,000")

        print(f"\n🔐 Login Credentials:")
        print(f"   Username: {DEMO_USERNAME}")
        print(f"   Password: {DEMO_PASSWORD}")

        print(f"\n📈 Features:")
        print(f"   • 11 wallets across 6 blockchains")
        print(f"   • 55 NFTs across 4 collections")
        print(f"   • 90 days of historical data")
        print(f"   • Realistic portfolio growth trend")
        print(f"   • No password change prompt on login")

        print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"\n❌ Error creating demo account: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
