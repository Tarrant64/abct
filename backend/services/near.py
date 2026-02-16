"""
NEAR Protocol Blockchain Service

Fetches NEAR wallet balances via the NEAR RPC (free, no API key required)
and token/NFT data via the NearBlocks API.

Usage:
    from services.near import near_service

    info = await near_service.get_address_info("alice.near")
    nfts = await near_service.get_all_nfts(["alice.near"], user_id=1)
"""

import httpx
from typing import Optional, List
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

# NEAR RPC endpoint (free, no key required)
RPC_URL = "https://rpc.mainnet.near.org"

# NearBlocks public API for tokens and NFTs
NEARBLOCKS_API = "https://api.nearblocks.io/v1"

# 1 NEAR = 10^24 yoctoNEAR
YOCTO_NEAR_DECIMALS = 24
YOCTO_NEAR_DIVISOR = 10 ** YOCTO_NEAR_DECIMALS


class NEARService:
    """Service for fetching NEAR Protocol wallet data."""

    def __init__(self):
        self.rpc_url = RPC_URL
        self.nearblocks_api = NEARBLOCKS_API

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including NEAR balance and token holdings.

        Uses the NEAR JSON-RPC view_account query for native balance
        and NearBlocks API for fungible token balances.

        Args:
            address: NEAR account ID (e.g. "alice.near" or hex address)

        Returns:
            Dict with address, balance_near, locked_near, tokens, etc.
            None on error.
        """
        try:
            client = get_client("near_rpc", timeout=30.0)

            # Fetch native NEAR balance via JSON-RPC
            response = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "query",
                    "params": {
                        "request_type": "view_account",
                        "finality": "final",
                        "account_id": address
                    }
                },
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"NEAR RPC error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Check for JSON-RPC error response
            if "error" in data:
                error_msg = data["error"]
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("data", error_msg.get("message", str(error_msg)))
                logger.error(f"NEAR RPC error for {address}: {error_msg}")
                return None

            result = data.get("result", {})
            amount_yocto = int(result.get("amount", "0"))
            locked_yocto = int(result.get("locked", "0"))

            balance_near = amount_yocto / YOCTO_NEAR_DIVISOR
            locked_near = locked_yocto / YOCTO_NEAR_DIVISOR

            # Fetch fungible token balances from NearBlocks
            tokens = await self._get_token_balances(address)

            return {
                "address": address,
                "balance_near": f"{balance_near:.8f}",
                "balance_yocto": str(amount_yocto),
                "locked_near": f"{locked_near:.8f}",
                "locked_yocto": str(locked_yocto),
                "storage_usage": result.get("storage_usage", 0),
                "block_height": result.get("block_height"),
                "tokens": tokens or [],
                "blockchain": "near",
                "source": "near_rpc"
            }

        except httpx.TimeoutException:
            logger.error(f"NEAR RPC timeout for address {address}")
            return None
        except Exception as e:
            logger.error(f"NEAR RPC error for {address}: {e}")
            return None

    async def _get_token_balances(self, address: str) -> Optional[list]:
        """
        Fetch fungible token balances for a NEAR account via NearBlocks API.

        Args:
            address: NEAR account ID

        Returns:
            List of token dicts with contract, name, symbol, balance, decimals.
            None on error.
        """
        try:
            client = get_client("near_rpc", timeout=30.0)
            response = await client.get(
                f"{self.nearblocks_api}/account/{address}/tokens",
                timeout=30.0
            )

            if response.status_code != 200:
                logger.warning(f"NearBlocks token API error: {response.status_code}")
                return None

            data = response.json()
            token_list = data.get("tokens", data) if isinstance(data, dict) else data

            if not isinstance(token_list, list):
                return []

            tokens = []
            for token in token_list:
                contract = token.get("contract", "")
                name = token.get("name", "Unknown")
                symbol = token.get("symbol", "")
                amount = token.get("amount", "0")
                decimals = int(token.get("decimals", 0))

                # Convert raw amount to human-readable balance
                if decimals > 0 and amount:
                    try:
                        balance = int(amount) / (10 ** decimals)
                    except (ValueError, TypeError):
                        balance = 0.0
                else:
                    try:
                        balance = float(amount)
                    except (ValueError, TypeError):
                        balance = 0.0

                tokens.append({
                    "contract": contract,
                    "name": name,
                    "symbol": symbol,
                    "balance": f"{balance:.8f}",
                    "balance_raw": str(amount),
                    "decimals": decimals,
                    "icon": token.get("icon", ""),
                })

            return tokens

        except httpx.TimeoutException:
            logger.warning(f"NearBlocks token API timeout for {address}")
            return None
        except Exception as e:
            logger.warning(f"NearBlocks token API error for {address}: {e}")
            return None

    async def get_all_nfts(self, addresses: List[str], user_id: int = None) -> List[dict]:
        """
        Fetch all NFTs across the given NEAR addresses via NearBlocks API.

        Args:
            addresses: List of NEAR account IDs
            user_id: Optional user ID for cache scoping

        Returns:
            List of NFT dicts with standard fields.
        """
        all_nfts = []
        seen_ids = set()

        for address in addresses:
            nfts = await self._get_nfts_for_address(address)
            if not nfts:
                continue

            for nft in nfts:
                # Build a unique ID from contract + token_id
                contract = nft.get("contract", "")
                token_id = nft.get("token_id", "")
                unique_id = f"{contract}:{token_id}"

                if unique_id in seen_ids:
                    continue
                seen_ids.add(unique_id)

                nft_data = {
                    "asset_id": unique_id,
                    "name": nft.get("title", nft.get("metadata", {}).get("title", "Unknown")),
                    "collection": nft.get("nft", {}).get("name", contract),
                    "contract_address": contract,
                    "token_id": token_id,
                    "description": nft.get("description", nft.get("metadata", {}).get("description", "")),
                    "image": nft.get("media", nft.get("metadata", {}).get("media", "")),
                    "owner": address,
                    "blockchain": "near",
                    "source": "nearblocks",
                }
                all_nfts.append(nft_data)

        logger.info(f"Fetched {len(all_nfts)} NEAR NFTs across {len(addresses)} address(es)")
        return all_nfts

    async def _get_nfts_for_address(self, address: str) -> Optional[list]:
        """
        Fetch NFTs for a single NEAR address via NearBlocks API.

        Args:
            address: NEAR account ID

        Returns:
            List of raw NFT data from NearBlocks, or None on error.
        """
        try:
            client = get_client("near_rpc", timeout=30.0)
            response = await client.get(
                f"{self.nearblocks_api}/account/{address}/nft-tokens",
                timeout=30.0
            )

            if response.status_code != 200:
                logger.warning(f"NearBlocks NFT API error for {address}: {response.status_code}")
                return None

            data = response.json()
            nft_list = data.get("tokens", data) if isinstance(data, dict) else data

            if not isinstance(nft_list, list):
                return []

            return nft_list

        except httpx.TimeoutException:
            logger.warning(f"NearBlocks NFT API timeout for {address}")
            return None
        except Exception as e:
            logger.warning(f"NearBlocks NFT API error for {address}: {e}")
            return None


# Singleton instance
near_service = NEARService()
