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
        # Demo staking positions
        self.staking_positions = [
            {
                "protocol": "Cardano Staking",
                "pool_name": "DEMO POOL",
                "pool_ticker": "DEMO",
                "staked_amount": "35000",
                "staked_amount_usd": 35000 * 1.05,  # $1.05 ADA
                "rewards_earned": "450.25",
                "rewards_earned_usd": 450.25 * 1.05,
                "apy": 4.5,
                "status": "active",
                "stake_address": "stake1u9demo_stake_address_example_1234567890",
                "epochs_staked": 45,
                "next_reward_epoch": 523
            },
            {
                "protocol": "Ethereum Staking",
                "validator": "Demo Validator",
                "staked_amount": "32",
                "staked_amount_usd": 32 * 3500,  # $3500 ETH
                "rewards_earned": "0.85",
                "rewards_earned_usd": 0.85 * 3500,
                "apy": 3.8,
                "status": "active",
                "validator_index": "123456"
            }
        ]

        # Demo lending positions
        self.lending_positions = [
            {
                "protocol": "Indigo",
                "position_type": "collateral",
                "asset": "ADA",
                "amount": "25000",
                "amount_usd": 25000 * 1.05,
                "collateral_ratio": 275,
                "liquidation_price": 0.65,
                "health_factor": 2.75,
                "debt_asset": "iUSD",
                "debt_amount": "9500",
                "debt_amount_usd": 9500,
                "apy": 0,
                "stability_fee": 2.5
            },
            {
                "protocol": "Liqwid",
                "position_type": "supply",
                "asset": "ADA",
                "amount": "10000",
                "amount_usd": 10000 * 1.05,
                "apy": 3.2,
                "rewards_earned": "85.50",
                "rewards_earned_usd": 85.50 * 1.05
            }
        ]

        # Demo liquidity positions
        self.liquidity_positions = [
            {
                "protocol": "Minswap",
                "pool": "ADA/MIN",
                "position_value_usd": 5250.75,
                "token_a": "ADA",
                "token_a_amount": "2500",
                "token_b": "MIN",
                "token_b_amount": "58350",
                "share_of_pool": 0.025,
                "apy": 12.5,
                "fees_earned_24h": 2.50,
                "fees_earned_total": 125.75,
                "impermanent_loss": -2.3
            }
        ]

        # Demo yield farming positions
        self.farming_positions = [
            {
                "protocol": "SundaeSwap",
                "farm": "ADA/SUNDAE LP Staking",
                "staked_amount_usd": 3200.50,
                "rewards_token": "SUNDAE",
                "rewards_earned": "850",
                "rewards_earned_usd": 850 * 0.012,
                "apy": 15.8,
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
