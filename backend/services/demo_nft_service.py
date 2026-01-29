"""
Demo NFT Service - Returns fake NFT data

Provides mock NFT data for demo accounts:
- Fake NFT collections and holdings
- Mock floor prices
- Demo NFT images (uses placeholder images)
- No real NFT API calls
"""

from typing import Dict, List, Optional
from datetime import datetime
import random


class DemoNFTService:
    """Service for returning fake NFT data in demo mode."""

    def __init__(self):
        """Initialize demo NFT service with fake collections."""
        # Demo NFT collections
        self.collections = [
            {
                "policy_id": "demo_policy_001",
                "collection_name": "Demo Apes",
                "floor_price_ada": 125.50,
                "floor_price_usd": 125.50 * 1.05,
                "volume_24h": 15000,
                "volume_7d": 85000,
                "listings": 45,
                "supply": 10000,
                "holders": 3542,
                "verified": True,
                "owned_count": 3
            },
            {
                "policy_id": "demo_policy_002",
                "collection_name": "Cardano Planets",
                "floor_price_ada": 85.00,
                "floor_price_usd": 85.00 * 1.05,
                "volume_24h": 8500,
                "volume_7d": 52000,
                "listings": 32,
                "supply": 5000,
                "holders": 2150,
                "verified": True,
                "owned_count": 2
            },
            {
                "policy_id": "demo_policy_003",
                "collection_name": "Clay Nation",
                "floor_price_ada": 250.00,
                "floor_price_usd": 250.00 * 1.05,
                "volume_24h": 25000,
                "volume_7d": 145000,
                "listings": 28,
                "supply": 10000,
                "holders": 4250,
                "verified": True,
                "owned_count": 1
            },
            {
                "policy_id": "demo_policy_004",
                "collection_name": "Demo Dinos",
                "floor_price_ada": 42.50,
                "floor_price_usd": 42.50 * 1.05,
                "volume_24h": 3200,
                "volume_7d": 18500,
                "listings": 65,
                "supply": 8888,
                "holders": 2890,
                "verified": False,
                "owned_count": 4
            }
        ]

        # Demo individual NFTs
        self.nfts = [
            {
                "asset_id": "demo_asset_001",
                "policy_id": "demo_policy_001",
                "asset_name": "Demo Ape #1234",
                "collection_name": "Demo Apes",
                "image": "/static/demo-nfts/ape1.png",
                "rarity_rank": 234,
                "rarity_score": 85.5,
                "price_ada": 125.50,
                "last_sale_ada": 118.00,
                "attributes": [
                    {"trait_type": "Background", "value": "Blue"},
                    {"trait_type": "Fur", "value": "Golden"},
                    {"trait_type": "Eyes", "value": "Laser"}
                ]
            },
            {
                "asset_id": "demo_asset_002",
                "policy_id": "demo_policy_001",
                "asset_name": "Demo Ape #5678",
                "collection_name": "Demo Apes",
                "image": "/static/demo-nfts/ape2.png",
                "rarity_rank": 1523,
                "rarity_score": 45.2,
                "price_ada": 125.50,
                "last_sale_ada": 130.00,
                "attributes": [
                    {"trait_type": "Background", "value": "Purple"},
                    {"trait_type": "Fur", "value": "Brown"},
                    {"trait_type": "Eyes", "value": "Regular"}
                ]
            },
            {
                "asset_id": "demo_asset_003",
                "policy_id": "demo_policy_001",
                "asset_name": "Demo Ape #9012",
                "collection_name": "Demo Apes",
                "image": "/static/demo-nfts/ape3.png",
                "rarity_rank": 856,
                "rarity_score": 62.8,
                "price_ada": 125.50,
                "last_sale_ada": 125.00,
                "attributes": [
                    {"trait_type": "Background", "value": "Green"},
                    {"trait_type": "Fur", "value": "White"},
                    {"trait_type": "Eyes", "value": "3D"}
                ]
            },
            {
                "asset_id": "demo_asset_004",
                "policy_id": "demo_policy_002",
                "asset_name": "Planet Mars",
                "collection_name": "Cardano Planets",
                "image": "/static/demo-nfts/planet1.png",
                "rarity_rank": 45,
                "rarity_score": 92.3,
                "price_ada": 85.00,
                "last_sale_ada": 78.00,
                "attributes": [
                    {"trait_type": "Type", "value": "Rocky"},
                    {"trait_type": "Color", "value": "Red"},
                    {"trait_type": "Rings", "value": "None"}
                ]
            },
            {
                "asset_id": "demo_asset_005",
                "policy_id": "demo_policy_002",
                "asset_name": "Planet Neptune",
                "collection_name": "Cardano Planets",
                "image": "/static/demo-nfts/planet2.png",
                "rarity_rank": 156,
                "rarity_score": 78.9,
                "price_ada": 85.00,
                "last_sale_ada": 88.50,
                "attributes": [
                    {"trait_type": "Type", "value": "Gas Giant"},
                    {"trait_type": "Color", "value": "Blue"},
                    {"trait_type": "Rings", "value": "Yes"}
                ]
            },
            {
                "asset_id": "demo_asset_006",
                "policy_id": "demo_policy_003",
                "asset_name": "Clay #4567",
                "collection_name": "Clay Nation",
                "image": "/static/demo-nfts/clay1.png",
                "rarity_rank": 892,
                "rarity_score": 68.5,
                "price_ada": 250.00,
                "last_sale_ada": 245.00,
                "attributes": [
                    {"trait_type": "Background", "value": "Sky"},
                    {"trait_type": "Body", "value": "Blue Clay"},
                    {"trait_type": "Face", "value": "Happy"}
                ]
            },
            {
                "asset_id": "demo_asset_007",
                "policy_id": "demo_policy_004",
                "asset_name": "Dino #123",
                "collection_name": "Demo Dinos",
                "image": "/static/demo-nfts/dino1.png",
                "rarity_rank": 523,
                "rarity_score": 55.2,
                "price_ada": 42.50,
                "last_sale_ada": 40.00,
                "attributes": [
                    {"trait_type": "Species", "value": "T-Rex"},
                    {"trait_type": "Color", "value": "Green"},
                    {"trait_type": "Hat", "value": "Cowboy"}
                ]
            },
            {
                "asset_id": "demo_asset_008",
                "policy_id": "demo_policy_004",
                "asset_name": "Dino #456",
                "collection_name": "Demo Dinos",
                "image": "/static/demo-nfts/dino2.png",
                "rarity_rank": 1234,
                "rarity_score": 38.7,
                "price_ada": 42.50,
                "last_sale_ada": 43.00,
                "attributes": [
                    {"trait_type": "Species", "value": "Raptor"},
                    {"trait_type": "Color", "value": "Purple"},
                    {"trait_type": "Hat", "value": "None"}
                ]
            },
            {
                "asset_id": "demo_asset_009",
                "policy_id": "demo_policy_004",
                "asset_name": "Dino #789",
                "collection_name": "Demo Dinos",
                "image": "/static/demo-nfts/dino3.png",
                "rarity_rank": 856,
                "rarity_score": 48.9,
                "price_ada": 42.50,
                "last_sale_ada": 41.50,
                "attributes": [
                    {"trait_type": "Species", "value": "Stegosaurus"},
                    {"trait_type": "Color", "value": "Blue"},
                    {"trait_type": "Hat", "value": "Top Hat"}
                ]
            },
            {
                "asset_id": "demo_asset_010",
                "policy_id": "demo_policy_004",
                "asset_name": "Dino #1011",
                "collection_name": "Demo Dinos",
                "image": "/static/demo-nfts/dino4.png",
                "rarity_rank": 2345,
                "rarity_score": 25.3,
                "price_ada": 42.50,
                "last_sale_ada": 42.00,
                "attributes": [
                    {"trait_type": "Species", "value": "Triceratops"},
                    {"trait_type": "Color", "value": "Brown"},
                    {"trait_type": "Hat", "value": "Baseball Cap"}
                ]
            }
        ]

    async def get_all_nfts(self, force_refresh: bool = False) -> List[Dict]:
        """
        Get all demo NFTs.

        Args:
            force_refresh: Ignored in demo mode

        Returns:
            List of demo NFT objects with prices
        """
        ada_price_usd = 1.05  # Mock ADA price

        return [
            {
                **nft,
                "price_usd": nft["price_ada"] * ada_price_usd,
                "last_sale_usd": nft.get("last_sale_ada", 0) * ada_price_usd,
                "updated_at": datetime.now().isoformat()
            }
            for nft in self.nfts
        ]

    async def get_nft_summary(self) -> Dict:
        """
        Get summary of NFT holdings grouped by collection.

        Returns:
            Summary with collections and total values
        """
        ada_price_usd = 1.05

        collections_data = []
        total_value_ada = 0
        total_count = 0

        for collection in self.collections:
            collection_value = collection["floor_price_ada"] * collection["owned_count"]
            total_value_ada += collection_value
            total_count += collection["owned_count"]

            collections_data.append({
                **collection,
                "floor_price_usd": collection["floor_price_ada"] * ada_price_usd,
                "total_value_ada": collection_value,
                "total_value_usd": collection_value * ada_price_usd
            })

        return {
            "total_count": total_count,
            "total_value_ada": round(total_value_ada, 2),
            "total_value_usd": round(total_value_ada * ada_price_usd, 2),
            "collections": collections_data,
            "updated_at": datetime.now().isoformat()
        }

    async def get_collection_floor_price(self, policy_id: str) -> Optional[Dict]:
        """
        Get floor price for a specific collection.

        Args:
            policy_id: Policy ID of the collection

        Returns:
            Floor price data or None if not found
        """
        for collection in self.collections:
            if collection["policy_id"] == policy_id:
                return {
                    "policy_id": policy_id,
                    "collection_name": collection["collection_name"],
                    "floor_price_ada": collection["floor_price_ada"],
                    "floor_price_usd": collection["floor_price_usd"],
                    "listings": collection["listings"],
                    "volume_24h": collection["volume_24h"],
                    "updated_at": datetime.now().isoformat()
                }
        return None

    async def get_nft_details(self, asset_id: str) -> Optional[Dict]:
        """
        Get details for a specific NFT.

        Args:
            asset_id: Asset ID of the NFT

        Returns:
            NFT details or None if not found
        """
        for nft in self.nfts:
            if nft["asset_id"] == asset_id:
                return {
                    **nft,
                    "price_usd": nft["price_ada"] * 1.05,
                    "updated_at": datetime.now().isoformat()
                }
        return None

    async def get_collection_stats(self, policy_id: str) -> Optional[Dict]:
        """
        Get statistics for a collection.

        Args:
            policy_id: Policy ID of the collection

        Returns:
            Collection statistics
        """
        for collection in self.collections:
            if collection["policy_id"] == policy_id:
                # Calculate some demo stats
                return {
                    **collection,
                    "avg_price_ada": collection["floor_price_ada"] * 1.15,
                    "market_cap_ada": collection["floor_price_ada"] * collection["supply"] * 0.8,
                    "price_change_24h": round(random.uniform(-5, 10), 2),
                    "price_change_7d": round(random.uniform(-15, 25), 2),
                    "sales_24h": random.randint(5, 50),
                    "unique_buyers_24h": random.randint(3, 30),
                    "updated_at": datetime.now().isoformat()
                }
        return None


# Global instance
demo_nft_service = DemoNFTService()
