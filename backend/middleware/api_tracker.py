"""
API Call Tracker Middleware

Automatically tracks API calls to external services for rate limit monitoring.
This middleware wraps HTTP clients to record usage in the database.
"""

import httpx
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import record_api_call

logger = logging.getLogger(__name__)


class TrackedAsyncClient(httpx.AsyncClient):
    """
    AsyncClient wrapper that tracks API calls for rate limit monitoring.

    Usage:
        async with TrackedAsyncClient(api_name="blockfrost") as client:
            response = await client.get(url, headers=headers)
    """

    def __init__(self, api_name: str, *args, **kwargs):
        """
        Initialize tracked client.

        Args:
            api_name: Name of the API service (e.g., "blockfrost", "alchemy")
            *args, **kwargs: Passed to httpx.AsyncClient
        """
        super().__init__(*args, **kwargs)
        self.api_name = api_name
        self._call_count = 0

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Make HTTP request and track the call.

        Only successful requests (status 2xx or 404) are counted toward rate limits.
        Authentication errors (401, 403) and server errors (5xx) are not counted.
        """
        try:
            response = await super().request(method, url, **kwargs)

            # Track successful API calls (2xx responses or 404 which means valid request)
            # Don't track auth errors (401, 403) or server errors (5xx)
            if 200 <= response.status_code < 300 or response.status_code == 404:
                try:
                    await record_api_call(self.api_name)
                    self._call_count += 1
                    logger.debug(f"Tracked {self.api_name} API call (total in session: {self._call_count})")
                except Exception as e:
                    # Don't fail the request if tracking fails
                    logger.warning(f"Failed to track API call for {self.api_name}: {e}")

            return response

        except Exception as e:
            # Re-raise the original exception
            raise


async def track_api_call(api_name: str, success: bool = True):
    """
    Manually track an API call when not using TrackedAsyncClient.

    Use this for APIs that don't use httpx or for bulk operations.

    Args:
        api_name: Name of the API service
        success: Whether to count this call (default True)

    Example:
        await track_api_call("coingecko")
    """
    if success:
        try:
            await record_api_call(api_name)
            logger.debug(f"Manually tracked {api_name} API call")
        except Exception as e:
            logger.warning(f"Failed to track API call for {api_name}: {e}")


def get_tracked_client(api_name: str, **kwargs) -> TrackedAsyncClient:
    """
    Factory function to create a tracked HTTP client.

    Args:
        api_name: Name of the API service
        **kwargs: Additional kwargs for httpx.AsyncClient (timeout, headers, etc.)

    Returns:
        TrackedAsyncClient instance

    Example:
        async with get_tracked_client("blockfrost", timeout=30.0) as client:
            response = await client.get(url, headers=headers)
    """
    return TrackedAsyncClient(api_name=api_name, **kwargs)


# Convenience functions for common APIs

def get_blockfrost_client(headers: Dict[str, str], **kwargs) -> TrackedAsyncClient:
    """Get tracked client for Blockfrost API."""
    return TrackedAsyncClient(api_name="blockfrost", headers=headers, **kwargs)


def get_alchemy_client(timeout: float = 30.0, **kwargs) -> TrackedAsyncClient:
    """Get tracked client for Alchemy API."""
    return TrackedAsyncClient(api_name="alchemy", timeout=timeout, **kwargs)


def get_helius_client(timeout: float = 30.0, **kwargs) -> TrackedAsyncClient:
    """Get tracked client for Helius API."""
    return TrackedAsyncClient(api_name="helius", timeout=timeout, **kwargs)


def get_taptools_client(headers: Dict[str, str], **kwargs) -> TrackedAsyncClient:
    """Get tracked client for TapTools API."""
    return TrackedAsyncClient(api_name="taptools", headers=headers, **kwargs)


def get_etherscan_client(timeout: float = 30.0, **kwargs) -> TrackedAsyncClient:
    """Get tracked client for Etherscan API."""
    return TrackedAsyncClient(api_name="etherscan", timeout=timeout, **kwargs)


def get_coingecko_client(headers: Optional[Dict[str, str]] = None, **kwargs) -> TrackedAsyncClient:
    """Get tracked client for CoinGecko API."""
    return TrackedAsyncClient(api_name="coingecko", headers=headers or {}, **kwargs)


def get_coinmarketcap_client(headers: Dict[str, str], **kwargs) -> TrackedAsyncClient:
    """Get tracked client for CoinMarketCap API."""
    return TrackedAsyncClient(api_name="coinmarketcap", headers=headers, **kwargs)


def get_cexplorer_client(headers: Dict[str, str], **kwargs) -> TrackedAsyncClient:
    """Get tracked client for CExplorer API."""
    return TrackedAsyncClient(api_name="cexplorer", headers=headers, **kwargs)
