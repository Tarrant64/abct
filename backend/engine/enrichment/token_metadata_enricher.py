"""
Token Metadata Enricher

Resolves token names, symbols, and decimals for asset IDs.
Wraps existing services for each chain.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TokenMetadataEnricher:
    """Resolves token metadata (name, symbol, decimals) for assets."""

    async def get_metadata(self, chain: str, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        Get token metadata for an asset.

        Args:
            chain: The chain name.
            asset_id: The asset identifier.

        Returns:
            Dict with name, symbol, decimals, or None.
        """
        if asset_id == "native":
            return self._native_metadata(chain)

        # Chain-specific metadata resolution
        if chain == "cardano":
            return await self._cardano_metadata(asset_id)
        elif chain in ("ethereum", "polygon", "base"):
            return await self._evm_metadata(chain, asset_id)
        elif chain == "solana":
            return await self._solana_metadata(asset_id)

        return None

    def _native_metadata(self, chain: str) -> Dict[str, Any]:
        """Return metadata for native assets."""
        natives = {
            "cardano": {"name": "Cardano", "symbol": "ADA", "decimals": 6},
            "bitcoin": {"name": "Bitcoin", "symbol": "BTC", "decimals": 8},
            "ethereum": {"name": "Ethereum", "symbol": "ETH", "decimals": 18},
            "solana": {"name": "Solana", "symbol": "SOL", "decimals": 9},
            "polygon": {"name": "Polygon", "symbol": "MATIC", "decimals": 18},
            "base": {"name": "Ethereum", "symbol": "ETH", "decimals": 18},
        }
        return natives.get(chain, {"name": "Unknown", "symbol": "???", "decimals": 0})

    async def _cardano_metadata(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Resolve Cardano native asset metadata via Blockfrost."""
        try:
            # asset_id format: "policyId.assetName"
            parts = asset_id.split(".", 1)
            if len(parts) != 2:
                return None
            unit = parts[0] + parts[1]

            from services.http_client import get_client, fetch_with_retry
            from services.api_key_manager import APIKeyManager
            from config import BLOCKFROST_BASE_URL

            keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")
            api_key = await keys.get_api_key()
            if not api_key:
                return None

            client = get_client("blockfrost", timeout=30.0)
            resp = await fetch_with_retry(
                client, "GET",
                f"{BLOCKFROST_BASE_URL}/assets/{unit}",
                headers={"project_id": api_key},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            metadata = data.get("onchain_metadata", {}) or {}
            return {
                "name": metadata.get("name", data.get("asset_name", "")),
                "symbol": metadata.get("ticker", ""),
                "decimals": data.get("metadata", {}).get("decimals", 0) if data.get("metadata") else 0,
            }
        except Exception as e:
            logger.warning(f"Cardano metadata lookup failed for {asset_id}: {e}")
            return None

    async def _evm_metadata(self, chain: str, asset_id: str) -> Optional[Dict[str, Any]]:
        """Resolve ERC-20 token metadata. Stub for Phase 3."""
        # TODO: Use Alchemy/RPC to call name(), symbol(), decimals()
        return None

    async def _solana_metadata(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Resolve SPL token metadata. Stub for Phase 4."""
        # TODO: Use Helius or Metaplex to resolve token metadata
        return None


token_metadata_enricher = TokenMetadataEnricher()
