"""
Demo DeFi Service - Returns fake DeFi positions and staking data

Provides mock DeFi data for demo accounts across multiple chains:
- Cardano: Indigo, Minswap, Liqwid, SundaeSwap, Strike, WingRiders
- Ethereum: Lido, Aave, Uniswap, Compound, Curve, EigenLayer, MakerDAO
- Solana: Jupiter, Raydium, Marinade, Jito, Kamino, Orca

All data is pre-defined and realistic but entirely fake.
Returns data in the exact format the frontend expects.
"""

from typing import Dict, List
from datetime import datetime, timedelta
import random


class DemoDeFiService:
    """Service for returning fake DeFi data in demo mode."""

    def __init__(self):
        """Initialize demo DeFi service with positions matching frontend format."""
        pass

    async def get_defi_summary(self) -> Dict:
        """
        Get aggregated DeFi summary matching the real defi.py /summary format.
        Frontend reads: positions_by_category, all_positions, protocols_used, etc.
        """
        # ============================================================
        # GOVERNANCE TOKENS — Multi-chain (frontend reads pos.blockchain)
        # ============================================================
        governance_tokens = [
            # --- Cardano Governance ---
            self._pos("Indigo Protocol", "INDY", "INDY", "governance", "Governance Tokens", 500, 6, blockchain="cardano"),
            self._pos("Minswap", "MIN", "MIN", "governance", "Governance Tokens", 15000, 0, blockchain="cardano"),
            self._pos("Liqwid Finance", "LQ", "LQ", "governance", "Governance Tokens", 15000, 6, blockchain="cardano"),
            self._pos("SundaeSwap", "SUNDAE", "SUNDAE", "governance", "Governance Tokens", 35000, 0, blockchain="cardano"),
            self._pos("WingRiders", "WRT", "WRT", "governance", "Governance Tokens", 2000, 0, blockchain="cardano"),
            self._pos("Optim Finance", "OPTIM", "OPTIM", "governance", "Governance Tokens", 20000, 0, blockchain="cardano"),
            self._pos("Spectrum Finance", "SPF", "SPF", "governance", "Governance Tokens", 3000, 0, blockchain="cardano"),
            # --- Ethereum Governance ---
            self._pos("Aave", "AAVE", "AAVE", "governance", "Governance Tokens", 35, 18, blockchain="ethereum"),
            self._pos("Uniswap", "UNI", "UNI", "governance", "Governance Tokens", 500, 18, blockchain="ethereum"),
            self._pos("Compound", "COMP", "COMP", "governance", "Governance Tokens", 50, 18, blockchain="ethereum"),
            self._pos("Curve DAO", "CRV", "CRV", "governance", "Governance Tokens", 3000, 18, blockchain="ethereum"),
            self._pos("Lido DAO", "LDO", "LDO", "governance", "Governance Tokens", 800, 18, blockchain="ethereum"),
            self._pos("MakerDAO", "MKR", "MKR", "governance", "Governance Tokens", 2.5, 18, blockchain="ethereum"),
            self._pos("ENS Domains", "ENS", "ENS", "governance", "Governance Tokens", 120, 18, blockchain="ethereum"),
            # --- Solana Governance ---
            self._pos("Jupiter", "JUP", "JUP", "governance", "Governance Tokens", 3000, 6, blockchain="solana"),
            self._pos("Raydium", "RAY", "RAY", "governance", "Governance Tokens", 1500, 6, blockchain="solana"),
            self._pos("Marinade", "MNDE", "MNDE", "governance", "Governance Tokens", 5000, 9, blockchain="solana"),
            self._pos("Jito", "JTO", "JTO", "governance", "Governance Tokens", 250, 9, blockchain="solana"),
            self._pos("Orca", "ORCA", "ORCA", "governance", "Governance Tokens", 800, 6, blockchain="solana"),
        ]

        # ============================================================
        # STABLECOINS — Cardano on-chain (ETH/SOL come via /portfolio/assets)
        # ============================================================
        stablecoins = [
            self._pos("Indigo Protocol", "iUSD", "iUSD", "stablecoin", "Stablecoins", 3500, 6, blockchain="cardano"),
            self._pos("DJED", "DJED", "DJED", "stablecoin", "Stablecoins", 2000, 6, blockchain="cardano"),
            self._pos("Circle", "USDC", "USDC", "stablecoin", "Stablecoins", 5000, 6, blockchain="cardano"),
        ]

        # ============================================================
        # LP TOKENS — Multi-chain (rendered as chips, no chain badge)
        # ============================================================
        lp_tokens = [
            # Cardano LPs
            self._pos("Minswap", "MIN/ADA LP", "MIN/ADA LP", "lp", "Liquidity Pool Tokens", 85000, 0),
            self._pos("SundaeSwap", "SUNDAE/ADA LP", "SUNDAE/ADA LP", "lp", "Liquidity Pool Tokens", 42000, 0),
            self._pos("Minswap", "INDY/ADA LP", "INDY/ADA LP", "lp", "Liquidity Pool Tokens", 28000, 0),
            # Ethereum LPs
            self._pos("Uniswap V3", "ETH/USDC LP", "ETH/USDC LP", "lp", "Liquidity Pool Tokens", 1250, 18),
            self._pos("Curve", "3pool LP", "3pool LP", "lp", "Liquidity Pool Tokens", 8500, 18),
            self._pos("Balancer", "wETH/wstETH LP", "wETH/wstETH LP", "lp", "Liquidity Pool Tokens", 420, 18),
            # Solana LPs
            self._pos("Raydium", "SOL/USDC LP", "SOL/USDC LP", "lp", "Liquidity Pool Tokens", 15000, 6),
            self._pos("Orca", "JUP/SOL LP", "JUP/SOL LP", "lp", "Liquidity Pool Tokens", 6200, 6),
        ]

        # ============================================================
        # LIQUID STAKING — Multi-chain (frontend reads pos.blockchain)
        # ============================================================
        liquid_staking = [
            # Cardano
            self._pos("Liqwid Finance", "qADA", "qADA", "liquid_staking", "Liquid Staking", 18000, 6, blockchain="cardano"),
            # Ethereum
            self._pos("Lido", "stETH", "stETH", "liquid_staking", "Liquid Staking", 1.5, 18, blockchain="ethereum"),
            self._pos("Rocket Pool", "rETH", "rETH", "liquid_staking", "Liquid Staking", 0.8, 18, blockchain="ethereum"),
            # Solana
            self._pos("Marinade", "mSOL", "mSOL", "liquid_staking", "Liquid Staking", 50, 9, blockchain="solana"),
            self._pos("Jito", "JitoSOL", "JitoSOL", "liquid_staking", "Liquid Staking", 30, 9, blockchain="solana"),
        ]

        # ============================================================
        # SYNTHETIC ASSETS
        # ============================================================
        synthetic_assets = [
            # Cardano (Indigo)
            self._pos("Indigo Protocol", "iBTC", "iBTC", "synthetic", "Synthetic Assets", 0.05, 8, blockchain="cardano"),
            self._pos("Indigo Protocol", "iETH", "iETH", "synthetic", "Synthetic Assets", 0.15, 18, blockchain="cardano"),
            # Ethereum (Synthetix)
            self._pos("Synthetix", "sUSD", "sUSD", "synthetic", "Synthetic Assets", 2500, 18, blockchain="ethereum"),
        ]

        # ============================================================
        # STAKING RECEIPTS
        # ============================================================
        staking_receipts = [
            self._pos("Indigo Protocol", "sINDY", "sINDY", "staking_receipt", "Staking Receipts", 500, 6),
            self._pos("Strike Finance", "sSTRIKE", "sSTRIKE", "staking_receipt", "Staking Receipts", 10000, 0),
            self._pos("EigenLayer", "eETH", "eETH", "staking_receipt", "Staking Receipts", 0.5, 18),
        ]

        positions_by_category = {
            "Governance Tokens": governance_tokens,
            "Stablecoins": stablecoins,
            "Liquidity Pool Tokens": lp_tokens,
            "Liquid Staking": liquid_staking,
            "Synthetic Assets": synthetic_assets,
            "Staking Receipts": staking_receipts,
        }

        all_positions = []
        for positions in positions_by_category.values():
            all_positions.extend(positions)

        protocols_used = list(set(p["protocol"] for p in all_positions))

        protocol_summary = []
        proto_map = {}
        for pos in all_positions:
            proto = pos["protocol"]
            if proto not in proto_map:
                proto_map[proto] = {"protocol": proto, "position_count": 0, "token_types": set()}
            proto_map[proto]["position_count"] += 1
            proto_map[proto]["token_types"].add(pos["type"])
        for proto in proto_map.values():
            proto["token_types"] = list(proto["token_types"])
            protocol_summary.append(proto)

        return {
            "total_wallets_analyzed": 2,
            "wallets_with_defi": 2,
            "total_positions": len(all_positions),
            "protocols_used": protocols_used,
            "protocol_summary": protocol_summary,
            "positions_by_category": positions_by_category,
            "all_positions": sorted(all_positions, key=lambda x: (x["protocol"], x["token"])),
            "from_cache": False,
        }

    def _pos(self, protocol: str, token: str, asset_name: str,
             pos_type: str, type_label: str, quantity: float,
             decimals: int, blockchain: str = "cardano") -> Dict:
        """Build a position object matching the real defi_service format."""
        # Store quantity as human-readable, compute raw from decimals
        quantity_raw = int(quantity * (10 ** decimals)) if decimals > 0 else int(quantity)
        return {
            "protocol": protocol,
            "token": token,
            "asset_name": asset_name,
            "type": pos_type,
            "type_label": type_label,
            "decimals": decimals,
            "quantity_raw": quantity_raw,
            "quantity": quantity,
            "quantity_formatted": f"{quantity:,.6f}".rstrip("0").rstrip("."),
            "wallet_count": 1,
            "blockchain": blockchain,
        }

    async def get_staking_data(self, address: str) -> Dict:
        """
        Return demo staking data matching the real /defi/staking/{address} format.
        Includes Cardano, Ethereum, and Solana staking protocols.

        Frontend reads: protocols[name].staked (array), pending_indy, pending_ada,
        pending_rewards, reward_token, reward_tokens, apy, rewards_url, blockchain.
        """
        return {
            "address": address,
            "protocols": {
                # --- Cardano Staking Protocols ---
                "Indigo": {
                    "blockchain": "cardano",
                    "staked": [{
                        "token": "INDY",
                        "amount": 500.0,
                        "amount_formatted": "500.000000",
                        "positions": 2,
                        "logo_url": "https://logostream.dev/api/logo?symbol=INDY",
                    }],
                    "pending_indy": 12.5,
                    "pending_ada": 85.0,
                    "reward_tokens": ["INDY", "ADA"],
                    "rewards_url": "https://app.indigoprotocol.io/earn",
                    "total_positions": 2,
                },
                "Strike": {
                    "blockchain": "cardano",
                    "staked": [{
                        "token": "STRIKE",
                        "amount": 10000.0,
                        "amount_formatted": "10,000.000000",
                        "positions": 1,
                        "logo_url": "https://logostream.dev/api/logo?symbol=STRIKE",
                    }],
                    "pending_rewards": 250.0,
                    "accumulated_rewards": 1200.0,
                    "reward_token": "STRIKE",
                    "rewards_url": "https://app.strikefinance.org/perpetuals/ada",
                    "total_positions": 1,
                },
                "Liqwid": {
                    "blockchain": "cardano",
                    "staked": [{
                        "token": "LQ",
                        "amount": 15000.0,
                        "amount_formatted": "15,000.000000",
                        "positions": 1,
                        "logo_url": "https://logostream.dev/api/logo?symbol=LQ",
                    }],
                    "pending_rewards": 500.0,
                    "reward_token": "LQ",
                    "claimed_rewards": 2500.0,
                    "total_earned": 3000.0,
                    "rewards_url": "https://liqwid-rewards.sundaeswap.finance/",
                    "total_positions": 1,
                },
                # --- Ethereum Staking Protocols ---
                "Aave": {
                    "blockchain": "ethereum",
                    "staked": [{
                        "token": "AAVE",
                        "amount": 18.0,
                        "amount_formatted": "18.000000",
                        "positions": 1,
                        "logo_url": "https://logostream.dev/api/logo?symbol=AAVE",
                    }],
                    "pending_rewards": 0.85,
                    "reward_token": "AAVE",
                    "apy": 4.6,
                    "rewards_url": "https://app.aave.com/staking/",
                    "total_positions": 1,
                },
                "EigenLayer": {
                    "blockchain": "ethereum",
                    "staked": [{
                        "token": "EIGEN",
                        "amount": 1200.0,
                        "amount_formatted": "1,200.000000",
                        "positions": 1,
                        "logo_url": "https://logostream.dev/api/logo?symbol=EIGEN",
                    }],
                    "pending_rewards": 45.0,
                    "reward_token": "EIGEN",
                    "apy": 8.2,
                    "rewards_url": "https://app.eigenlayer.xyz/",
                    "total_positions": 1,
                },
                # --- Solana Staking Protocols ---
                "Jupiter": {
                    "blockchain": "solana",
                    "staked": [{
                        "token": "JUP",
                        "amount": 5000.0,
                        "amount_formatted": "5,000.000000",
                        "positions": 1,
                        "logo_url": "https://logostream.dev/api/logo?symbol=JUP",
                    }],
                    "pending_rewards": 120.0,
                    "reward_token": "JUP",
                    "apy": 6.5,
                    "rewards_url": "https://vote.jup.ag/",
                    "total_positions": 1,
                },
                "Kamino": {
                    "blockchain": "solana",
                    "staked": [{
                        "token": "KMNO",
                        "amount": 8000.0,
                        "amount_formatted": "8,000.000000",
                        "positions": 1,
                        "logo_url": "https://logostream.dev/api/logo?symbol=KMNO",
                    }],
                    "pending_rewards": 200.0,
                    "reward_token": "KMNO",
                    "apy": 12.3,
                    "rewards_url": "https://app.kamino.finance/",
                    "total_positions": 1,
                },
            },
            "total_positions": 9,
            "total_pending_rewards": {
                "INDY": 12.5,
                "ADA": 85.0,
                "STRIKE": 250.0,
                "LQ": 500.0,
                "AAVE": 0.85,
                "EIGEN": 45.0,
                "JUP": 120.0,
                "KMNO": 200.0,
            },
        }

    def get_governance_info(self, address: str) -> Dict:
        """
        Return demo governance info matching the real cardano_service format.
        Frontend reads: pool.pool_id, pool.name, pool.ticker
        """
        return {
            "has_stake_key": True,
            "stake_address": "stake1u9demo_stake_address_example_1234567890",
            "pool": {
                "pool_id": "pool1demo000000000000000000000000000000000000000000000000",
                "name": "ABCT Demo Pool",
                "ticker": "DEMO",
                "homepage": "https://example.com",
                "description": "Demo staking pool for ABCT showcase",
            },
            "drep": {
                "drep_id": "drep1demo0000000000000000000000000000000000000000000",
                "type": "abstain",
            },
            "rewards": {
                "total_earned": "1250.50",
                "withdrawable": "42.75",
                "withdrawable_lovelace": "42750000",
            },
        }

    async def get_rewards_history(self, days: int = 30) -> List[Dict]:
        """Get demo rewards history across all chains."""
        history = []
        base_daily_reward = 18.50

        for i in range(days):
            date = datetime.now() - timedelta(days=days - i - 1)
            daily_reward = base_daily_reward * (0.9 + random.random() * 0.2)

            history.append({
                "date": date.date().isoformat(),
                "rewards_usd": round(daily_reward, 2),
                "ada_rewards": round(daily_reward * 0.4 / 1.05, 2),
                "eth_rewards": round(daily_reward * 0.35 / 3500, 6),
                "sol_rewards": round(daily_reward * 0.25 / 180, 4),
                "protocol_breakdown": {
                    "Cardano Staking": round(daily_reward * 0.25, 2),
                    "Lido (stETH)": round(daily_reward * 0.20, 2),
                    "Aave": round(daily_reward * 0.10, 2),
                    "EigenLayer": round(daily_reward * 0.10, 2),
                    "Liqwid": round(daily_reward * 0.08, 2),
                    "Jupiter": round(daily_reward * 0.10, 2),
                    "Marinade": round(daily_reward * 0.07, 2),
                    "Kamino": round(daily_reward * 0.05, 2),
                    "Minswap LP": round(daily_reward * 0.05, 2),
                },
            })

        return history


# Global instance
demo_defi_service = DemoDeFiService()
