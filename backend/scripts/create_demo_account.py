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
                "asset_name": "4d494e",  # MIN (Minswap)
                "quantity": "100000",
                "decimals": 6
            },
            {
                "asset_id": "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff935574d54",
                "policy_id": "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff935",
                "asset_name": "574d54",  # WMT (World Mobile Token)
                "quantity": "5000",
                "decimals": 6
            },
            {
                "asset_id": "f43a62fdc3965df486de8a0d32fe800963589c41b38946602a0dc53541474f",
                "policy_id": "f43a62fdc3965df486de8a0d32fe800963589c41b38946602a0dc535",
                "asset_name": "41474f",  # AGIX (SingularityNET)
                "quantity": "50000",
                "decimals": 8
            },
            {
                "asset_id": "8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61446f67",
                "policy_id": "8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61",
                "asset_name": "446f67",  # SNEK
                "quantity": "2500000",
                "decimals": 0
            },
            {
                "asset_id": "29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c6494e4459",
                "policy_id": "29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c6",
                "asset_name": "494e4459",  # INDY (Indigo)
                "quantity": "7500",
                "decimals": 6
            },
            {
                "asset_id": "0e14267a8020229adc0184dd25fa3174c3f7d6caadcb4425c70e7c04534e454b",
                "policy_id": "0e14267a8020229adc0184dd25fa3174c3f7d6caadcb4425c70e7c04",
                "asset_name": "534e454b",  # Another SNEK variant
                "quantity": "150000",
                "decimals": 0
            },
            {
                "asset_id": "682fe60c9918842b3323c43b5144bc3d52a23bd2fb81345560d73f634e4d4c4b",
                "policy_id": "682fe60c9918842b3323c43b5144bc3d52a23bd2fb81345560d73f63",
                "asset_name": "4e4d4c4b",  # NMKR (Newm)
                "quantity": "25000",
                "decimals": 6
            },
            {
                "asset_id": "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114494147",
                "policy_id": "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114",
                "asset_name": "494147",  # IAG (Iagon)
                "quantity": "80000",
                "decimals": 6
            },
            {
                "asset_id": "c6e65ba7878b2f8ea0ad39287d3e2fd256dc5c4160fc19bdf4c4d87e7447454e53",
                "policy_id": "c6e65ba7878b2f8ea0ad39287d3e2fd256dc5c4160fc19bdf4c4d87e",
                "asset_name": "7447454e53",  # GENS (Genzee)
                "quantity": "120000",
                "decimals": 0
            },
            {
                "asset_id": "804f5544c1962a40546827cab750a88404dc7108c0f588b72964754f434f5049",
                "policy_id": "804f5544c1962a40546827cab750a88404dc7108c0f588b72964754f",
                "asset_name": "434f5049",  # COPI (Cornucopias)
                "quantity": "35000",
                "decimals": 0
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
                "asset_name": "USDT",  # Tether
                "quantity": "10000",
                "decimals": 6
            },
            {
                "asset_id": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "policy_id": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "asset_name": "USDC",  # USD Coin
                "quantity": "5000",
                "decimals": 6
            },
            {
                "asset_id": "0x514910771af9ca656af840dff83e8264ecf986ca",
                "policy_id": "0x514910771af9ca656af840dff83e8264ecf986ca",
                "asset_name": "LINK",  # Chainlink
                "quantity": "250",
                "decimals": 18
            },
            {
                "asset_id": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
                "policy_id": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
                "asset_name": "UNI",  # Uniswap
                "quantity": "500",
                "decimals": 18
            },
            {
                "asset_id": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
                "policy_id": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
                "asset_name": "AAVE",  # Aave
                "quantity": "75",
                "decimals": 18
            },
            {
                "asset_id": "0x6b175474e89094c44da98b954eedeac495271d0f",
                "policy_id": "0x6b175474e89094c44da98b954eedeac495271d0f",
                "asset_name": "DAI",  # Dai Stablecoin
                "quantity": "8000",
                "decimals": 18
            },
            {
                "asset_id": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
                "policy_id": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
                "asset_name": "WBTC",  # Wrapped Bitcoin
                "quantity": "0.5",
                "decimals": 8
            },
            {
                "asset_id": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
                "policy_id": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
                "asset_name": "SHIB",  # Shiba Inu
                "quantity": "50000000",
                "decimals": 18
            },
            {
                "asset_id": "0xc00e94cb662c3520282e6f5717214004a7f26888",
                "policy_id": "0xc00e94cb662c3520282e6f5717214004a7f26888",
                "asset_name": "COMP",  # Compound
                "quantity": "30",
                "decimals": 18
            },
            {
                "asset_id": "0x0d8775f648430679a709e98d2b0cb6250d2887ef",
                "policy_id": "0x0d8775f648430679a709e98d2b0cb6250d2887ef",
                "asset_name": "BAT",  # Basic Attention Token
                "quantity": "15000",
                "decimals": 18
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
                "asset_name": "USDC",  # USD Coin
                "quantity": "3000",
                "decimals": 6
            },
            {
                "asset_id": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
                "policy_id": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
                "asset_name": "RAY",  # Raydium
                "quantity": "1200",
                "decimals": 6
            },
            {
                "asset_id": "SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKWRt",
                "policy_id": "SRMuApVNdxXokk5GT7XD5cUUgXMBCoAz2LHeuAoKWRt",
                "asset_name": "SRM",  # Serum
                "quantity": "800",
                "decimals": 6
            },
            {
                "asset_id": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
                "policy_id": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
                "asset_name": "ORCA",  # Orca
                "quantity": "2500",
                "decimals": 6
            },
            {
                "asset_id": "MNGOqteD6L8KxfxaWNJ3r5fkPYuD1kXUhqFVEKB5dVa",
                "policy_id": "MNGOqteD6L8KxfxaWNJ3r5fkPYuD1kXUhqFVEKB5dVa",
                "asset_name": "MNGO",  # Mango Markets
                "quantity": "15000",
                "decimals": 6
            },
            {
                "asset_id": "StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT",
                "policy_id": "StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT",
                "asset_name": "STEP",  # Step Finance
                "quantity": "5000",
                "decimals": 9
            },
            {
                "asset_id": "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",
                "policy_id": "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",
                "asset_name": "stSOL",  # Lido Staked SOL
                "quantity": "350",
                "decimals": 9
            },
            {
                "asset_id": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
                "policy_id": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
                "asset_name": "mSOL",  # Marinade Staked SOL
                "quantity": "280",
                "decimals": 9
            },
            {
                "asset_id": "SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp",
                "policy_id": "SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp",
                "asset_name": "SLND",  # Solend
                "quantity": "3500",
                "decimals": 6
            },
            {
                "asset_id": "Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb",
                "policy_id": "Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb",
                "asset_name": "JTO",  # Jito
                "quantity": "600",
                "decimals": 9
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
