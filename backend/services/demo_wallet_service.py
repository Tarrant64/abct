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
            ]
        }

        # Demo tokens
        self.demo_tokens = {
            "cardano": [
                {
                    "name": "MIN",
                    "ticker": "MIN",
                    "quantity": "15000",
                    "decimals": 0,
                    "price_usd": 0.045,
                    "value_usd": 15000 * 0.045
                },
                {
                    "name": "SNEK",
                    "ticker": "SNEK",
                    "quantity": "25000000",
                    "decimals": 0,
                    "price_usd": 0.0012,
                    "value_usd": 25000000 * 0.0012
                },
                {
                    "name": "INDY",
                    "ticker": "INDY",
                    "quantity": "500",
                    "decimals": 0,
                    "price_usd": 0.85,
                    "value_usd": 500 * 0.85
                }
            ],
            "ethereum": [
                {
                    "name": "USD Coin",
                    "ticker": "USDC",
                    "quantity": "5000",
                    "decimals": 6,
                    "price_usd": 1.0,
                    "value_usd": 5000
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
            "base": "ETH"
        }
        return units.get(blockchain, "UNKNOWN")


# Global instance
demo_wallet_service = DemoWalletService()
