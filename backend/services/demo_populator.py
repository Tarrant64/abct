"""
Demo Account Populator - Populates demo account with comprehensive fake data

This service populates the demo account database with:
- Wallets across all blockchains
- $200K in stablecoins
- $540K+ in DeFi positions
- 90 days of portfolio history
- NFT collections
- Transactions

Used on first login to demo account or triggered manually.
"""

import aiosqlite
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Callable
import logging

from config import DATABASE_PATH
from services.demo_data_generator import (
    generate_stablecoins,
    generate_defi_positions,
    generate_portfolio_history,
    get_blockchain_logos
)

logger = logging.getLogger(__name__)


class DemoPopulator:
    """Handles population of demo account with fake data."""

    def __init__(self):
        self.progress = 0
        self.status = "idle"
        self.current_step = ""

    async def populate_demo_account(
        self,
        user_id: int,
        progress_callback: Callable[[int, str], None] = None
    ) -> Dict:
        """
        Populate demo account with comprehensive fake data.

        Args:
            user_id: Demo user ID
            progress_callback: Optional callback function(progress, status)

        Returns:
            Dict with population results
        """
        self.progress = 0
        self.status = "running"
        results = {
            "wallets_created": 0,
            "tokens_added": 0,
            "defi_positions_added": 0,
            "snapshots_created": 0,
            "started_at": datetime.now().isoformat(),
            "completed_at": None
        }

        try:
            # Step 1: Create wallets (10%)
            self._update_progress(5, "Creating demo wallets...", progress_callback)
            wallets_created = await self._create_demo_wallets(user_id)
            results["wallets_created"] = wallets_created
            self._update_progress(10, f"Created {wallets_created} wallets", progress_callback)

            # Step 2: Add stablecoins (20%)
            self._update_progress(15, "Adding $200K in stablecoins...", progress_callback)
            stablecoins_added = await self._add_stablecoins(user_id)
            results["tokens_added"] += stablecoins_added
            self._update_progress(30, f"Added {stablecoins_added} stablecoin positions", progress_callback)

            # Step 3: Add DeFi positions (30%)
            self._update_progress(35, "Adding $540K in DeFi positions...", progress_callback)
            defi_added = await self._add_defi_positions(user_id)
            results["defi_positions_added"] = defi_added
            self._update_progress(60, f"Added {defi_added} DeFi positions", progress_callback)

            # Step 4: Generate portfolio history (30%)
            self._update_progress(65, "Generating 90 days of portfolio history...", progress_callback)
            snapshots_created = await self._add_portfolio_history(user_id)
            results["snapshots_created"] = snapshots_created
            self._update_progress(90, f"Created {snapshots_created} historical snapshots", progress_callback)

            # Step 5: Finalize (10%)
            self._update_progress(95, "Finalizing demo account...", progress_callback)
            await self._mark_demo_populated(user_id)
            self._update_progress(100, "Demo account ready!", progress_callback)

            results["completed_at"] = datetime.now().isoformat()
            self.status = "completed"

            return results

        except Exception as e:
            logger.error(f"Error populating demo account: {e}")
            self.status = "error"
            raise

    def _update_progress(self, progress: int, status: str, callback: Callable = None):
        """Update progress and optionally call callback."""
        self.progress = progress
        self.current_step = status
        if callback:
            callback(progress, status)
        logger.info(f"Demo population: {progress}% - {status}")

    async def _create_demo_wallets(self, user_id: int) -> int:
        """Create demo wallets across all blockchains."""
        demo_wallets = [
            ("cardano", "addr1qx2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf9wejf", "Main Cardano Wallet"),
            ("bitcoin", "bc1qxy2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9we", "BTC Cold Storage"),
            ("ethereum", "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb8", "ETH DeFi Wallet"),
            ("solana", "DemoSo1anaWa11etAddress123456789ABC", "Solana Main Wallet"),
            ("polygon", "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb9", "Polygon Wallet"),
            ("base", "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEc0", "Base Wallet"),
            ("algorand", "SWOUICD7LO3MWVKLHFKADCXLF5HZPUQQFW5OIJAFZJBG4HDQH53RTTJPFE", "Algorand Wallet")
        ]

        async with aiosqlite.connect(DATABASE_PATH) as conn:
            created = 0
            for blockchain, address, label in demo_wallets:
                # Check if wallet already exists
                cursor = await conn.execute(
                    "SELECT id FROM wallets WHERE user_id = ? AND blockchain = ? AND address = ?",
                    (user_id, blockchain, address)
                )
                row = await cursor.fetchone()
                if not row:
                    await conn.execute(
                        "INSERT INTO wallets (user_id, blockchain, address, label, created_at) VALUES (?, ?, ?, ?, ?)",
                        (user_id, blockchain, address, label, datetime.now().isoformat())
                    )
                    created += 1

            await conn.commit()
        return created

    async def _add_stablecoins(self, user_id: int) -> int:
        """Add $200K in stablecoins to demo wallets."""
        stablecoins = generate_stablecoins()

        async with aiosqlite.connect(DATABASE_PATH) as conn:
            added = 0
            for blockchain, tokens in stablecoins.items():
                # Get wallet ID for this blockchain
                cursor = await conn.execute(
                    "SELECT id FROM wallets WHERE user_id = ? AND blockchain = ? LIMIT 1",
                    (user_id, blockchain)
                )
                wallet_row = await cursor.fetchone()
                if not wallet_row:
                    continue

                wallet_id = wallet_row[0]

                for token in tokens:
                    # Check if token already exists
                    cursor = await conn.execute(
                        "SELECT id FROM native_assets WHERE wallet_id = ? AND asset_name = ?",
                        (wallet_id, token["ticker"])
                    )
                    row = await cursor.fetchone()
                    if not row:
                        await conn.execute(
                            """INSERT INTO native_assets
                               (wallet_id, user_id, asset_id, asset_name, policy_id, quantity, decimals, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                wallet_id,
                                user_id,
                                token["ticker"],
                                token["name"],
                                "demo_policy_" + token["ticker"],
                                str(int(float(token["quantity"]) * (10 ** token["decimals"]))),
                                token["decimals"],
                                datetime.now().isoformat()
                            )
                        )
                        added += 1

            await conn.commit()
        return added

    async def _add_defi_positions(self, user_id: int) -> int:
        """Add $540K+ in DeFi positions."""
        # DeFi positions are handled by demo_defi_service
        # We don't need to persist them to DB since they're generated on-the-fly
        # Just return count for progress tracking
        defi = generate_defi_positions()
        return (
            len(defi["staking"]) +
            len(defi["lending"]) +
            len(defi["liquidity"]) +
            len(defi["farming"])
        )

    async def _add_portfolio_history(self, user_id: int) -> int:
        """Add 90 days of portfolio history snapshots."""
        history = generate_portfolio_history(90)

        async with aiosqlite.connect(DATABASE_PATH) as conn:
            created = 0
            for snapshot in history:
                # Check if snapshot already exists for this date
                cursor = await conn.execute(
                    "SELECT id FROM portfolio_snapshots WHERE user_id = ? AND snapshot_date = ?",
                    (user_id, snapshot["snapshot_date"])
                )
                row = await cursor.fetchone()
                if not row:
                    await conn.execute(
                        """INSERT INTO portfolio_snapshots
                           (user_id, snapshot_date, total_value_usd, created_at)
                           VALUES (?, ?, ?, ?)""",
                        (
                            user_id,
                            snapshot["snapshot_date"],
                            snapshot["total_value_usd"],
                            datetime.now().isoformat()
                        )
                    )
                    created += 1

            await conn.commit()
        return created

    async def _mark_demo_populated(self, user_id: int):
        """Mark demo account as populated in database."""
        async with aiosqlite.connect(DATABASE_PATH) as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO user_settings (user_id, setting_key, setting_value, updated_at)
                   VALUES (?, 'demo_data_populated', 'true', ?)""",
                (user_id, datetime.now().isoformat())
            )
            await conn.commit()

    def get_progress(self) -> Dict:
        """Get current population progress."""
        return {
            "progress": self.progress,
            "status": self.status,
            "current_step": self.current_step
        }


# Global instance
demo_populator = DemoPopulator()


async def is_demo_populated(user_id: int) -> bool:
    """
    Check if demo account has been populated.

    Args:
        user_id: User ID to check

    Returns:
        True if demo data has been populated
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as conn:
            cursor = await conn.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'demo_data_populated'""",
                (user_id,)
            )
            row = await cursor.fetchone()

            return row is not None and row[0] == 'true'

    except Exception as e:
        logger.error(f"Error checking demo population status: {e}")
        return False


async def populate_demo_on_first_login(user_id: int) -> Dict:
    """
    Populate demo account if not already populated.

    Called automatically on demo account login.

    Args:
        user_id: Demo user ID

    Returns:
        Dict with population results or status
    """
    if await is_demo_populated(user_id):
        return {
            "already_populated": True,
            "message": "Demo account already has data"
        }

    # Populate in background
    result = await demo_populator.populate_demo_account(user_id)
    return {
        "already_populated": False,
        "populated": True,
        **result
    }
