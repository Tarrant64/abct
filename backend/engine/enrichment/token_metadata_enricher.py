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
        """Resolve Cardano native asset metadata.
        Triple fallback: SQL → Blockfrost RYO → Blockfrost.io"""
        try:
            # asset_id format: "policyId.assetName"
            parts = asset_id.split(".", 1)
            if len(parts) != 2:
                return None
            unit = parts[0] + parts[1]
            policy_id = parts[0]
            asset_name_hex = parts[1]

            from services.cardano_query import cardano_query

            async def _sql():
                from services.cardano_db import query_one
                row = await query_one("""
                    SELECT
                        encode(ma.policy, 'hex') AS policy_id,
                        encode(ma.name, 'hex') AS asset_name_hex,
                        ma.fingerprint
                    FROM multi_asset ma
                    WHERE encode(ma.policy, 'hex') = $1
                      AND encode(ma.name, 'hex') = $2
                """, policy_id, asset_name_hex)
                if row is None:
                    raise ValueError("Asset not found in DB Sync")
                # Try to decode asset name as human-readable
                try:
                    name = bytes.fromhex(asset_name_hex).decode('utf-8')
                except (ValueError, UnicodeDecodeError):
                    name = asset_name_hex
                return {
                    "name": name,
                    "symbol": "",
                    "decimals": 0,
                }

            async def _blockfrost():
                from services.http_client import blockfrost_fetch
                from services.api_key_manager import APIKeyManager

                keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")
                api_key = await keys.get_api_key()
                if not api_key:
                    raise ValueError("No Blockfrost API key")

                resp = await blockfrost_fetch(
                    f"/assets/{unit}",
                    headers={"project_id": api_key},
                    timeout=30.0
                )
                if resp.status_code != 200:
                    raise ValueError(f"Blockfrost returned {resp.status_code}")

                data = resp.json()
                metadata = data.get("onchain_metadata", {}) or {}
                return {
                    "name": metadata.get("name", data.get("asset_name", "")),
                    "symbol": metadata.get("ticker", ""),
                    "decimals": data.get("metadata", {}).get("decimals", 0) if data.get("metadata") else 0,
                }

            return await cardano_query(
                sql_fn=_sql,
                blockfrost_fn=_blockfrost,
                operation=f"asset_metadata({asset_id[:30]}...)",
            )
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
