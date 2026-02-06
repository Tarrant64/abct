"""
Logostream Service - Fetches crypto token/coin logos via Logostream API.

Documentation: https://logostream.dev/documentation
Free tier: 100 requests/month, rate limit 10 requests/minute
"""

import httpx
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)


class LogostreamService(APIKeyManager):
    """Service for fetching token/coin logos from Logostream API."""

    def __init__(self):
        super().__init__(api_name='logostream', env_var='LOGOSTREAM_API_KEY')
        self.base_url = "https://logostream.dev/api"
        self._logo_cache: Dict[str, str] = {}  # symbol -> logo_url
        self._cache_ttl = timedelta(days=7)  # Logos don't change often
        self._cache_timestamps: Dict[str, datetime] = {}

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    async def get_token_logo(self, symbol: str, chain: str = None) -> Optional[str]:
        """
        Get logo URL for a token by symbol and optional chain.

        Args:
            symbol: Token symbol (e.g., 'BTC', 'ETH', 'USDC')
            chain: Optional blockchain filter (e.g., 'ethereum', 'cardano', 'solana')

        Returns:
            Logo URL or None if not found
        """
        if not symbol:
            return None

        if not await self.is_configured():
            logger.debug("Logostream API key not configured")
            return None

        # Check cache
        cache_key = f"{symbol.upper()}_{chain}" if chain else symbol.upper()
        if cache_key in self._logo_cache:
            cached_time = self._cache_timestamps.get(cache_key)
            if cached_time and (datetime.now() - cached_time) < self._cache_ttl:
                return self._logo_cache[cache_key]

        try:
            client = get_client("logostream", timeout=10.0)
            params = {
                "apikey": await self.get_api_key(),
                "symbol": symbol.upper()
            }

            if chain:
                params["chain"] = chain.lower()

            response = await client.get(
                f"{self.base_url}/logo",
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                logo_url = data.get('logo_url') or data.get('url')

                if logo_url:
                    # Cache the result
                    self._logo_cache[cache_key] = logo_url
                    self._cache_timestamps[cache_key] = datetime.now()
                    return logo_url

            elif response.status_code == 429:
                logger.warning("Logostream rate limited")
            elif response.status_code != 404:
                logger.warning(f"Logostream API error: {response.status_code}")

        except Exception as e:
            logger.debug(f"Error fetching logo from Logostream for {symbol}: {e}")

        return None

    async def search_token(self, query: str) -> list:
        """
        Search for tokens by name or symbol.

        Args:
            query: Search query (name or symbol)

        Returns:
            List of matching tokens with metadata
        """
        if not query or not await self.is_configured():
            return []

        try:
            client = get_client("logostream", timeout=10.0)
            response = await client.get(
                f"{self.base_url}/search",
                params={
                    "apikey": await self.get_api_key(),
                    "q": query
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])

        except Exception as e:
            logger.debug(f"Error searching Logostream for {query}: {e}")

        return []

    def clear_cache(self):
        """Clear the logo cache."""
        self._logo_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Logostream cache cleared")


# Singleton instance
logostream_service = LogostreamService()
