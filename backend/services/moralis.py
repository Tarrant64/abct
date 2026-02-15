"""
Moralis Spam Detection Service

Provides spam token detection for EVM and Solana chains.
"""

import httpx
import logging
from typing import List, Dict, Optional
from services.http_client import get_client

logger = logging.getLogger(__name__)

MORALIS_API_BASE = "https://deep-index.moralis.io/api/v2.2"


class MoralisService:
    """Service for detecting spam tokens using Moralis API."""

    def __init__(self):
        self.api_key = None

    async def _get_api_key(self) -> Optional[str]:
        """Get Moralis API key from database or environment."""
        if self.api_key:
            return self.api_key

        # Try to load from database first
        try:
            from routers.settings import get_effective_api_key
            self.api_key = await get_effective_api_key('moralis')
            return self.api_key
        except Exception as e:
            logger.error(f"Error loading Moralis API key: {e}")
            return None

    async def is_configured(self) -> bool:
        """Check if Moralis API key is configured."""
        api_key = await self._get_api_key()
        return bool(api_key)

    async def check_evm_token_spam(self, token_address: str, chain: str = "eth") -> Dict:
        """
        Check if an EVM token is spam.

        Args:
            token_address: Token contract address
            chain: Chain name (eth, polygon, bsc, etc.)

        Returns:
            Dictionary with spam detection results
        """
        api_key = await self._get_api_key()
        if not api_key:
            return {"error": "Moralis API key not configured"}

        headers = {
            "Accept": "application/json",
            "X-API-Key": api_key
        }

        try:
            client = get_client("moralis", timeout=15.0)
            response = await client.get(
                f"{MORALIS_API_BASE}/erc20/metadata",
                params={
                    "chain": chain,
                    "addresses": [token_address]
                },
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    token_data = data[0]
                    return {
                        "address": token_address,
                        "is_spam": token_data.get("possible_spam", False),
                        "name": token_data.get("name"),
                        "symbol": token_data.get("symbol"),
                        "decimals": token_data.get("decimals")
                    }

            return {"error": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"Error checking token spam for {token_address}: {e}")
            return {"error": str(e)}

    async def scan_wallet_tokens(self, wallet_address: str, chain: str = "eth") -> List[Dict]:
        """
        Scan all tokens in a wallet for spam.

        Args:
            wallet_address: Wallet address to scan
            chain: Chain name (eth, polygon, base, etc.)

        Returns:
            List of spam tokens found
        """
        api_key = await self._get_api_key()
        if not api_key:
            return []

        headers = {
            "Accept": "application/json",
            "X-API-Key": api_key
        }

        try:
            client = get_client("moralis", timeout=30.0)
            response = await client.get(
                f"{MORALIS_API_BASE}/{wallet_address}/erc20",
                params={"chain": chain},
                headers=headers
            )

            if response.status_code == 200:
                tokens = response.json()
                spam_tokens = []

                for token in tokens:
                    if token.get("possible_spam", False):
                        spam_tokens.append({
                            "address": token.get("token_address"),
                            "name": token.get("name"),
                            "symbol": token.get("symbol"),
                            "balance": token.get("balance"),
                            "decimals": token.get("decimals"),
                            "chain": chain
                        })

                return spam_tokens

            logger.error(f"Moralis API error: {response.status_code}")
            return []

        except Exception as e:
            logger.error(f"Error scanning wallet {wallet_address}: {e}")
            return []

    async def resolve_ens_domain(self, domain: str) -> Optional[str]:
        """
        Resolve an ENS domain name to an Ethereum address.

        Args:
            domain: ENS domain name (e.g., 'vitalik.eth')

        Returns:
            Ethereum address string or None
        """
        api_key = await self._get_api_key()
        if not api_key:
            return None

        # Check cache
        try:
            from database import get_cache, set_cache
            from config import CACHE_TTL_PERSISTENT
            cache_key = f"ens:domain:{domain}"
            cached = await get_cache(cache_key)
            if cached:
                return cached
        except Exception:
            pass

        headers = {
            "Accept": "application/json",
            "X-API-Key": api_key
        }

        try:
            client = get_client("moralis", timeout=15.0)
            response = await client.get(
                f"{MORALIS_API_BASE}/resolve/ens/{domain}",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                address = data.get("address")
                if address:
                    try:
                        await set_cache(cache_key, address, CACHE_TTL_PERSISTENT)
                    except Exception:
                        pass
                    return address

        except Exception as e:
            logger.error(f"Error resolving ENS domain {domain}: {e}")

        return None

    async def resolve_address_to_ens(self, address: str) -> Optional[str]:
        """
        Reverse-resolve an Ethereum address to an ENS domain name.

        Args:
            address: Ethereum address (0x...)

        Returns:
            ENS domain string or None
        """
        api_key = await self._get_api_key()
        if not api_key:
            return None

        # Check cache
        try:
            from database import get_cache, set_cache
            from config import CACHE_TTL_PERSISTENT
            cache_key = f"ens:reverse:{address.lower()}"
            cached = await get_cache(cache_key)
            if cached:
                return cached
        except Exception:
            pass

        headers = {
            "Accept": "application/json",
            "X-API-Key": api_key
        }

        try:
            client = get_client("moralis", timeout=15.0)
            response = await client.get(
                f"{MORALIS_API_BASE}/resolve/{address}/reverse",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                ens_name = data.get("name")
                if ens_name:
                    try:
                        await set_cache(cache_key, ens_name, CACHE_TTL_PERSISTENT)
                    except Exception:
                        pass
                    return ens_name

        except Exception as e:
            logger.error(f"Error resolving address to ENS {address}: {e}")

        return None

    async def scan_solana_wallet(self, wallet_address: str) -> List[Dict]:
        """
        Scan Solana wallet tokens for spam.

        Args:
            wallet_address: Solana wallet address

        Returns:
            List of spam tokens found
        """
        api_key = await self._get_api_key()
        if not api_key:
            return []

        headers = {
            "Accept": "application/json",
            "X-API-Key": api_key
        }

        try:
            client = get_client("moralis", timeout=30.0)
            response = await client.get(
                f"{MORALIS_API_BASE}/solana/account/{wallet_address}/tokens",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                tokens = data.get("tokens", [])
                spam_tokens = []

                for token in tokens:
                    if token.get("possible_spam", False):
                        spam_tokens.append({
                            "address": token.get("mint"),
                            "name": token.get("name"),
                            "symbol": token.get("symbol"),
                            "balance": token.get("amount"),
                            "decimals": token.get("decimals"),
                            "chain": "solana"
                        })

                return spam_tokens

            logger.error(f"Moralis Solana API error: {response.status_code}")
            return []

        except Exception as e:
            logger.error(f"Error scanning Solana wallet {wallet_address}: {e}")
            return []


# Singleton instance
moralis_service = MoralisService()
