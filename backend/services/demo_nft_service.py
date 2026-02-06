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
        # Demo NFT collections - MULTI-CHAIN COLLECTIONS
        self.collections = [
            # Cardano NFTs
            {
                "policy_id": "demo_policy_001",
                "collection_name": "Clay Nation",
                "blockchain": "cardano",
                "floor_price_ada": 1100.00,
                "floor_price_usd": 1100.00 * 1.05,
                "volume_24h": 25000,
                "volume_7d": 145000,
                "listings": 28,
                "supply": 10000,
                "holders": 4250,
                "verified": True,
                "owned_count": 15  # 15 clay nation images
            },
            {
                "policy_id": "demo_policy_002",
                "collection_name": "Ape Society",
                "blockchain": "cardano",
                "floor_price_ada": 1850.00,
                "floor_price_usd": 1850.00 * 1.05,
                "volume_24h": 18500,
                "volume_7d": 95000,
                "listings": 35,
                "supply": 7000,
                "holders": 3150,
                "verified": True,
                "owned_count": 8  # 8 ape society images
            },
            # Ethereum NFTs
            {
                "policy_id": "demo_policy_003",
                "collection_name": "Bored Ape Yacht Club",
                "blockchain": "ethereum",
                "floor_price_ada": 3800.00,
                "floor_price_usd": 3800.00 * 1.05,
                "volume_24h": 85000,
                "volume_7d": 425000,
                "listings": 12,
                "supply": 10000,
                "holders": 6420,
                "verified": True,
                "owned_count": 12  # 12 BAYC images
            },
            # Solana NFTs
            {
                "policy_id": "demo_policy_004",
                "collection_name": "Solana Monkey Business",
                "blockchain": "solana",
                "floor_price_ada": 1200.00,
                "floor_price_usd": 1200.00 * 1.05,
                "volume_24h": 15000,
                "volume_7d": 78000,
                "listings": 45,
                "supply": 5000,
                "holders": 2890,
                "verified": True,
                "owned_count": 20  # 20 SMB images
            },
            # Polygon NFTs
            {
                "policy_id": "demo_policy_005",
                "collection_name": "Polygon Punks",
                "blockchain": "polygon",
                "floor_price_ada": 450.00,
                "floor_price_usd": 450.00 * 1.05,
                "volume_24h": 8500,
                "volume_7d": 45000,
                "listings": 52,
                "supply": 8000,
                "holders": 3100,
                "verified": True,
                "owned_count": 5
            },
            # Base NFTs
            {
                "policy_id": "demo_policy_006",
                "collection_name": "Base Builders",
                "blockchain": "base",
                "floor_price_ada": 280.00,
                "floor_price_usd": 280.00 * 1.05,
                "volume_24h": 5200,
                "volume_7d": 28000,
                "listings": 38,
                "supply": 5000,
                "holders": 2250,
                "verified": True,
                "owned_count": 3
            },
            # Algorand NFTs
            {
                "policy_id": "demo_policy_007",
                "collection_name": "AlgoRocks",
                "blockchain": "algorand",
                "floor_price_ada": 320.00,
                "floor_price_usd": 320.00 * 1.05,
                "volume_24h": 6100,
                "volume_7d": 32000,
                "listings": 42,
                "supply": 4000,
                "holders": 1850,
                "verified": True,
                "owned_count": 4
            }
        ]

        # Demo individual NFTs - USING ACTUAL ANIME IMAGES
        self.nfts = []

        # Clay Nation (15 images) - Floor price: 1100 ADA
        for i in range(1, 16):
            self.nfts.append({
                "asset_id": f"clay_nation_{i:04d}",
                "policy_id": "demo_policy_001",
                "asset_name": f"Clay Nation #{i:04d}",
                "collection_name": "Clay Nation",
                "blockchain": "cardano",
                "image": f"/static/demo-nfts/clay-nation-{i}.svg",
                "rarity_rank": i * 50 + random.randint(1, 49),
                "rarity_score": 90 - (i * 3) + random.uniform(-5, 5),
                "price_ada": 1100.00,
                "last_sale_ada": 1100.00 * random.uniform(0.9, 1.1),
                "attributes": [
                    {"trait_type": "Background", "value": ["Sky", "Ocean", "Sunset", "Night", "Dawn"][i % 5]},
                    {"trait_type": "Body", "value": ["Blue Clay", "Red Clay", "Green Clay", "Purple Clay"][i % 4]},
                    {"trait_type": "Face", "value": ["Happy", "Surprised", "Cool", "Smiling"][i % 4]}
                ]
            })

        # Ape Society (8 images) - Floor price: 1850 ADA
        for i in range(1, 9):
            self.nfts.append({
                "asset_id": f"ape_society_{i:04d}",
                "policy_id": "demo_policy_002",
                "asset_name": f"Ape Society #{1000 + i}",
                "collection_name": "Ape Society",
                "blockchain": "cardano",
                "image": f"/static/demo-nfts/ape-society-{i}.svg",
                "rarity_rank": i * 75 + random.randint(1, 74),
                "rarity_score": 85 - (i * 4) + random.uniform(-5, 5),
                "price_ada": 1850.00,
                "last_sale_ada": 1850.00 * random.uniform(0.85, 1.15),
                "attributes": [
                    {"trait_type": "Background", "value": ["Purple", "Blue", "Green", "Orange"][i % 4]},
                    {"trait_type": "Fur", "value": ["Golden", "Brown", "White", "Black"][i % 4]},
                    {"trait_type": "Eyes", "value": ["Laser", "3D", "Regular", "Closed"][i % 4]}
                ]
            })

        # BAYC (12 images) - Floor price: 3800 ADA
        for i in range(1, 13):
            self.nfts.append({
                "asset_id": f"bayc_{i:04d}",
                "policy_id": "demo_policy_003",
                "asset_name": f"Bored Ape #{2000 + i}",
                "collection_name": "Bored Ape Yacht Club",
                "blockchain": "ethereum",
                "image": f"/static/demo-nfts/bayc-{i}.svg",
                "rarity_rank": i * 60 + random.randint(1, 59),
                "rarity_score": 95 - (i * 2.5) + random.uniform(-3, 3),
                "price_ada": 3800.00,
                "last_sale_ada": 3800.00 * random.uniform(0.9, 1.1),
                "attributes": [
                    {"trait_type": "Background", "value": ["Gray", "Blue", "Yellow", "Aquamarine"][i % 4]},
                    {"trait_type": "Fur", "value": ["Brown", "Golden Brown", "Black", "Cream"][i % 4]},
                    {"trait_type": "Eyes", "value": ["Bored", "Angry", "Sad", "Happy"][i % 4]},
                    {"trait_type": "Mouth", "value": ["Bored", "Grin", "Smile", "Phoneme"][i % 4]}
                ]
            })

        # Solana Monkey Business (20 images) - Floor price: 1200 ADA
        for i in range(1, 21):
            self.nfts.append({
                "asset_id": f"smb_{i:04d}",
                "policy_id": "demo_policy_004",
                "asset_name": f"SMB #{3000 + i}",
                "collection_name": "Solana Monkey Business",
                "blockchain": "solana",
                "image": f"/static/demo-nfts/smb-{i}.svg",
                "rarity_rank": i * 40 + random.randint(1, 39),
                "rarity_score": 80 - (i * 2) + random.uniform(-4, 4),
                "price_ada": 1200.00,
                "last_sale_ada": 1200.00 * random.uniform(0.85, 1.15),
                "attributes": [
                    {"trait_type": "Type", "value": ["Gen1", "Gen2", "Gen3"][i % 3]},
                    {"trait_type": "Background", "value": ["Blue", "Red", "Green", "Yellow", "Purple"][i % 5]},
                    {"trait_type": "Hat", "value": ["None", "Cap", "Beanie", "Crown"][i % 4]},
                    {"trait_type": "Eyes", "value": ["Normal", "Laser", "Closed", "3D"][i % 4]}
                ]
            })

        # Polygon Punks (5 images) - Floor price: 450 ADA
        for i in range(1, 6):
            self.nfts.append({
                "asset_id": f"poly_punk_{i:04d}",
                "policy_id": "demo_policy_005",
                "asset_name": f"Polygon Punk #{4000 + i}",
                "collection_name": "Polygon Punks",
                "blockchain": "polygon",
                "image": f"/static/demo-nfts/polygon-punk-{i}.svg",
                "rarity_rank": i * 100 + random.randint(1, 99),
                "rarity_score": 75 - (i * 5) + random.uniform(-3, 3),
                "price_ada": 450.00,
                "last_sale_ada": 450.00 * random.uniform(0.9, 1.1),
                "attributes": [
                    {"trait_type": "Type", "value": ["Alien", "Ape", "Zombie"][i % 3]},
                    {"trait_type": "Accessory", "value": ["None", "Glasses", "Hat"][i % 3]}
                ]
            })

        # Base Builders (6 images) - Floor price: 320 ADA
        for i in range(1, 7):
            self.nfts.append({
                "asset_id": f"base_builder_{i:04d}",
                "policy_id": "demo_policy_006",
                "asset_name": f"Base Builder #{5000 + i}",
                "collection_name": "Base Builders",
                "blockchain": "base",
                "image": f"/static/demo-nfts/base-builder-{i}.svg",
                "rarity_rank": i * 80 + random.randint(1, 79),
                "rarity_score": 70 - (i * 4) + random.uniform(-3, 3),
                "price_ada": 320.00,
                "last_sale_ada": 320.00 * random.uniform(0.9, 1.1),
                "attributes": [
                    {"trait_type": "Role", "value": ["Developer", "Designer", "Builder"][i % 3]},
                    {"trait_type": "Level", "value": ["Beginner", "Pro", "Expert"][i % 3]}
                ]
            })

        # AlgoRocks (10 images) - Floor price: 280 ADA
        for i in range(1, 11):
            self.nfts.append({
                "asset_id": f"algo_rock_{i:04d}",
                "policy_id": "demo_policy_007",
                "asset_name": f"AlgoRock #{6000 + i}",
                "collection_name": "AlgoRocks",
                "blockchain": "algorand",
                "image": f"/static/demo-nfts/algo-rock-{i}.svg",
                "rarity_rank": i * 60 + random.randint(1, 59),
                "rarity_score": 68 - (i * 3) + random.uniform(-2, 2),
                "price_ada": 280.00,
                "last_sale_ada": 280.00 * random.uniform(0.9, 1.1),
                "attributes": [
                    {"trait_type": "Type", "value": ["Granite", "Marble", "Obsidian", "Quartz"][i % 4]},
                    {"trait_type": "Color", "value": ["Gray", "White", "Black", "Pink"][i % 4]}
                ]
            })

        # Old placeholder NFTs (keeping for backwards compatibility but not used)
        self._old_nfts = [
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

    async def get_nfts_by_chain(self, blockchain: str) -> List[Dict]:
        """
        Get NFTs filtered by blockchain.

        Args:
            blockchain: Blockchain to filter by (ethereum, solana, polygon, base, algorand)

        Returns:
            List of NFTs for that blockchain
        """
        # Filter NFTs by blockchain
        chain_nfts = [nft for nft in self.nfts if nft.get("blockchain") == blockchain]

        # Add price calculations
        price_multiplier = 1.05  # Mock price
        return [
            {
                **nft,
                "price_usd": nft.get("price_ada", 0) * price_multiplier,
                "last_sale_usd": nft.get("last_sale_ada", 0) * price_multiplier,
                "updated_at": datetime.now().isoformat()
            }
            for nft in chain_nfts
        ]

    async def get_chain_nft_summary(self, blockchain: str, native_price: float = 1.0) -> Dict:
        """
        Get NFT summary for a specific blockchain.

        Args:
            blockchain: Blockchain to get summary for
            native_price: Price of native token in USD

        Returns:
            Summary with counts and values for that chain
        """
        # Get collection for this blockchain
        chain_collections = [c for c in self.collections if c.get("blockchain") == blockchain]

        if not chain_collections:
            return {
                "total_nfts": 0,
                "total_value_eth": 0,  # Using eth as generic native token
                "total_value_sol": 0,
                "total_value_matic": 0,
                "total_value_usd": 0,
                "collections": []
            }

        total_count = sum(c.get("owned_count", 0) for c in chain_collections)
        total_value_native = sum(c.get("floor_price_ada", 0) * c.get("owned_count", 0) for c in chain_collections)
        total_value_usd = total_value_native * native_price

        # Format based on expected response structure for each chain
        if blockchain == "ethereum":
            return {
                "total_nfts": total_count,
                "total_value_eth": round(total_value_native, 4),
                "total_value_usd": round(total_value_usd, 2),
                "collections": chain_collections
            }
        elif blockchain == "solana":
            return {
                "total_nfts": total_count,
                "total_value_sol": round(total_value_native, 4),
                "total_value_usd": round(total_value_usd, 2),
                "collections": chain_collections
            }
        elif blockchain == "polygon":
            return {
                "total_nfts": total_count,
                "total_value_matic": round(total_value_native, 4),
                "total_value_usd": round(total_value_usd, 2),
                "collections": chain_collections
            }
        elif blockchain == "base":
            return {
                "total_nfts": total_count,
                "total_value_eth": round(total_value_native, 4),
                "total_value_usd": round(total_value_usd, 2),
                "collections": chain_collections
            }
        elif blockchain == "algorand":
            return {
                "total_nfts": total_count,
                "total_value_algo": round(total_value_native, 4),
                "total_value_usd": round(total_value_usd, 2),
                "collections": chain_collections
            }

        return {
            "total_nfts": total_count,
            "total_value_usd": round(total_value_usd, 2),
            "collections": chain_collections
        }


# Global instance
demo_nft_service = DemoNFTService()
