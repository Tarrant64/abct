"""
Demo DeFi Service - Returns fake DeFi positions and staking data

Provides mock DeFi data for demo accounts:
- Fake staking positions and rewards
- Mock lending/borrowing positions
- Fake APY/APR data
- No real DeFi protocol API calls
"""

from typing import Dict, List
from datetime import datetime, timedelta
import random


class DemoDeFiService:
    """Service for returning fake DeFi data in demo mode."""

    def __init__(self):
        """Initialize demo DeFi service with fake positions."""
        # Demo staking positions - ANIME THEMED
        self.staking_positions = [
            {
                "protocol": "Cardano Staking",
                "pool_name": "DEMO POOL",
                "pool_ticker": "DEMO",
                "staked_amount": "100000",
                "staked_amount_usd": 100000 * 1.05,  # $105,000 (ADA at $1.05)
                "rewards_earned": "1250.50",
                "rewards_earned_usd": 1250.50 * 1.05,
                "apy": 4.2,
                "status": "active",
                "stake_address": "stake1u9demo_stake_address_example_1234567890",
                "epochs_staked": 45,
                "next_reward_epoch": 523
            },
            {
                "protocol": "Ethereum Staking",
                "validator": "Demo Validator",
                "staked_amount": "12",
                "staked_amount_usd": 12 * 3000,  # $36,000 (ETH at $3000)
                "rewards_earned": "0.42",
                "rewards_earned_usd": 0.42 * 3000,
                "apy": 3.8,
                "status": "active",
                "validator_index": "123456"
            },
            {
                "protocol": "Solana Staking",
                "validator": "Anime Validator",
                "staked_amount": "300",
                "staked_amount_usd": 300 * 140,  # $42,000 (SOL at $140)
                "rewards_earned": "15.75",
                "rewards_earned_usd": 15.75 * 140,
                "apy": 7.1,
                "status": "active",
                "validator_address": "SoL1anaDemo1Validator123456789ABC"
            }
        ]

        # Demo lending positions - ANIME THEMED
        self.lending_positions = [
            {
                "protocol": "Kawaii Lending",
                "position_type": "supply",
                "asset": "ADA",
                "amount": "33333",
                "amount_usd": 33333 * 1.05,  # $35,000
                "apy": 5.5,
                "rewards_earned": "425.50",
                "rewards_earned_usd": 425.50 * 1.05
            }
        ]

        # Demo liquidity positions - ANIME THEMED
        self.liquidity_positions = [
            {
                "protocol": "Senpai Swap",
                "pool": "ADA/ANIME",
                "position_value_usd": 45000.00,
                "token_a": "ADA",
                "token_a_amount": "21429",
                "token_b": "ANIME",
                "token_b_amount": "500000",
                "share_of_pool": 0.085,
                "apy": 18.5,
                "fees_earned_24h": 12.50,
                "fees_earned_total": 1250.75,
                "impermanent_loss": -1.2
            }
        ]

        # Demo yield farming positions - ANIME THEMED
        self.farming_positions = [
            {
                "protocol": "Otaku Vault",
                "farm": "Anime Yield Farm",
                "staked_amount_usd": 40000.00,
                "rewards_token": "OTAKU",
                "rewards_earned": "2500",
                "rewards_earned_usd": 2500 * 0.025,
                "apy": 22.5,
                "status": "active"
            },
            {
                "protocol": "Manga Money Market",
                "farm": "Staking Rewards",
                "staked_amount_usd": 30000.00,
                "rewards_token": "MANGA",
                "rewards_earned": "1800",
                "rewards_earned_usd": 1800 * 0.032,
                "apy": 16.8,
                "status": "active"
            }
        ]

    async def get_all_staking_positions(self) -> List[Dict]:
        """
        Get all demo staking positions.

        Returns:
            List of demo staking position objects
        """
        return [
            {
                **pos,
                "updated_at": datetime.now().isoformat()
            }
            for pos in self.staking_positions
        ]

    async def get_staking_summary(self) -> Dict:
        """
        Get summary of all staking positions.

        Returns:
            Summary with total staked value and rewards
        """
        total_staked = sum(pos["staked_amount_usd"] for pos in self.staking_positions)
        total_rewards = sum(pos["rewards_earned_usd"] for pos in self.staking_positions)
        avg_apy = sum(pos["apy"] for pos in self.staking_positions) / len(self.staking_positions)

        return {
            "total_staked_usd": round(total_staked, 2),
            "total_rewards_usd": round(total_rewards, 2),
            "average_apy": round(avg_apy, 2),
            "active_positions": len(self.staking_positions),
            "updated_at": datetime.now().isoformat()
        }

    async def get_all_lending_positions(self) -> List[Dict]:
        """
        Get all demo lending/borrowing positions.

        Returns:
            List of demo lending position objects
        """
        return [
            {
                **pos,
                "updated_at": datetime.now().isoformat()
            }
            for pos in self.lending_positions
        ]

    async def get_lending_summary(self) -> Dict:
        """
        Get summary of all lending positions.

        Returns:
            Summary with total supplied, borrowed, and net value
        """
        total_supplied = sum(
            pos["amount_usd"] for pos in self.lending_positions
            if pos["position_type"] == "supply"
        )
        total_borrowed = sum(
            pos.get("debt_amount_usd", 0) for pos in self.lending_positions
            if pos["position_type"] == "collateral"
        )
        net_value = total_supplied - total_borrowed

        return {
            "total_supplied_usd": round(total_supplied, 2),
            "total_borrowed_usd": round(total_borrowed, 2),
            "net_value_usd": round(net_value, 2),
            "active_positions": len(self.lending_positions),
            "updated_at": datetime.now().isoformat()
        }

    async def get_all_liquidity_positions(self) -> List[Dict]:
        """
        Get all demo liquidity pool positions.

        Returns:
            List of demo LP position objects
        """
        return [
            {
                **pos,
                "updated_at": datetime.now().isoformat()
            }
            for pos in self.liquidity_positions
        ]

    async def get_all_farming_positions(self) -> List[Dict]:
        """
        Get all demo yield farming positions.

        Returns:
            List of demo farming position objects
        """
        return [
            {
                **pos,
                "updated_at": datetime.now().isoformat()
            }
            for pos in self.farming_positions
        ]

    async def get_defi_summary(self) -> Dict:
        """
        Get overall DeFi portfolio summary.

        Returns:
            Summary of all DeFi positions with total value
        """
        staking_summary = await self.get_staking_summary()
        lending_summary = await self.get_lending_summary()

        liquidity_value = sum(pos["position_value_usd"] for pos in self.liquidity_positions)
        farming_value = sum(pos["staked_amount_usd"] for pos in self.farming_positions)

        total_defi_value = (
            staking_summary["total_staked_usd"] +
            lending_summary["net_value_usd"] +
            liquidity_value +
            farming_value
        )

        return {
            "total_defi_value_usd": round(total_defi_value, 2),
            "staking_value_usd": staking_summary["total_staked_usd"],
            "lending_value_usd": lending_summary["net_value_usd"],
            "liquidity_value_usd": round(liquidity_value, 2),
            "farming_value_usd": round(farming_value, 2),
            "total_positions": (
                len(self.staking_positions) +
                len(self.lending_positions) +
                len(self.liquidity_positions) +
                len(self.farming_positions)
            ),
            "staking_positions": await self.get_all_staking_positions(),
            "lending_positions": await self.get_all_lending_positions(),
            "liquidity_positions": await self.get_all_liquidity_positions(),
            "farming_positions": await self.get_all_farming_positions(),
            "updated_at": datetime.now().isoformat()
        }

    async def get_rewards_history(self, days: int = 30) -> List[Dict]:
        """
        Get demo rewards history.

        Args:
            days: Number of days of history to return

        Returns:
            List of daily reward entries
        """
        history = []
        base_daily_reward = 12.50  # Base daily reward in USD

        for i in range(days):
            date = datetime.now() - timedelta(days=days - i - 1)
            # Add some randomness to make it look realistic
            daily_reward = base_daily_reward * (0.9 + random.random() * 0.2)

            history.append({
                "date": date.date().isoformat(),
                "rewards_usd": round(daily_reward, 2),
                "ada_rewards": round(daily_reward / 1.05, 2),
                "eth_rewards": round(daily_reward * 0.1 / 3500, 4),
                "protocol_breakdown": {
                    "Cardano Staking": round(daily_reward * 0.6, 2),
                    "Ethereum Staking": round(daily_reward * 0.25, 2),
                    "Liqwid": round(daily_reward * 0.1, 2),
                    "Minswap": round(daily_reward * 0.05, 2)
                }
            })

        return history


# Global instance
demo_defi_service = DemoDeFiService()
