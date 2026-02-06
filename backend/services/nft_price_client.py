"""
Cardano NFT Price Service Client

Client for fetching Cardano NFT floor prices from the external Cardano NFT Price Service.
Falls back to TapTools direct calls if the service is unavailable.
"""

import os
import sys
import httpx
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta

# Import database functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_api_key
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Configuration
NFT_PRICE_SERVICE_URL = os.getenv("NFT_PRICE_SERVICE_URL", "")
NFT_PRICE_SERVICE_TIMEOUT = 10.0  # seconds


class NFTPriceClient:
    """Client for the external Cardano NFT Floor Price Service."""

    def __init__(self):
        self.service_url = NFT_PRICE_SERVICE_URL
        self._available = None
        self._last_check = None
        self._check_interval = timedelta(minutes=5)
        self._cached_api_url = None
        self._api_url_cache_time = None
        self._api_url_cache_ttl = timedelta(minutes=1)  # Cache API URL for 1 minute

    async def _get_service_url(self) -> str:
        """Get the service URL from database or environment variable.

        Checks in this order:
        1. Database API setting (if recently added via UI)
        2. Environment variable (if set in .env)
        3. Cached value
        """
        # Check cache first
        now = datetime.utcnow()
        if self._cached_api_url and self._api_url_cache_time:
            if now - self._api_url_cache_time < self._api_url_cache_ttl:
                return self._cached_api_url

        # Try database first (allows runtime updates via UI)
        try:
            db_url = await get_api_key('nft_price_service', user_id=1)  # Default to admin user
            if db_url:
                self._cached_api_url = db_url
                self._api_url_cache_time = now
                return db_url
        except Exception as e:
            logger.debug(f"Could not fetch API URL from database: {e}")

        # Fall back to environment variable
        if NFT_PRICE_SERVICE_URL:
            self._cached_api_url = NFT_PRICE_SERVICE_URL
            self._api_url_cache_time = now
            return NFT_PRICE_SERVICE_URL

        return ""

    async def is_configured(self) -> bool:
        """Check if the Cardano NFT Price Service is configured."""
        url = await self._get_service_url()
        return bool(url)

    async def is_available(self) -> bool:
        """Check if the Cardano NFT Price Service is available."""
        if not await self.is_configured():
            return False

        # Cache availability check for 5 minutes
        now = datetime.utcnow()
        if self._available is not None and self._last_check:
            if now - self._last_check < self._check_interval:
                return self._available

        try:
            service_url = await self._get_service_url()
            client = get_client("nft_price_service", timeout=10.0)
            response = await client.get(f"{service_url}/health")
            self._available = response.status_code == 200
            self._last_check = now
            return self._available
        except Exception as e:
            logger.warning(f"Cardano NFT Price Service unavailable: {e}")
            self._available = False
            self._last_check = now
            return False

    async def get_floor_price(self, policy_id: str) -> Optional[float]:
        """Get floor price for a single collection."""
        if not await self.is_available():
            return None

        try:
            service_url = await self._get_service_url()
            client = get_client("nft_price_service", timeout=10.0)
            response = await client.get(f"{service_url}/floor/{policy_id}")

            if response.status_code != 200:
                return None

            data = response.json()
            if data.get("found"):
                return data.get("floor_price")
            return None

        except Exception as e:
            logger.error(f"Error fetching floor price from service: {e}")
            return None

    async def get_floor_prices(self, policy_ids: List[str]) -> Dict[str, float]:
        """Get floor prices for multiple collections at once."""
        if not await self.is_available():
            return {}

        if not policy_ids:
            return {}

        try:
            service_url = await self._get_service_url()
            client = get_client("nft_price_service", timeout=10.0)
            # Batch into chunks of 50
            all_floors = {}
            for i in range(0, len(policy_ids), 50):
                chunk = policy_ids[i:i + 50]
                ids_param = ",".join(chunk)

                response = await client.get(
                    f"{service_url}/floors",
                    params={"policy_ids": ids_param}
                )

                if response.status_code == 200:
                    data = response.json()
                    for policy_id, info in data.get("floors", {}).items():
                        if info.get("floor_price") is not None:
                            all_floors[policy_id] = info["floor_price"]

            return all_floors

        except Exception as e:
            logger.error(f"Error fetching floor prices from service: {e}")
            return {}

    async def get_service_status(self) -> Optional[Dict]:
        """Get status of the Cardano NFT Price Service."""
        if not await self.is_configured():
            return None

        try:
            service_url = await self._get_service_url()
            client = get_client("nft_price_service", timeout=10.0)
            response = await client.get(f"{service_url}/status")

            if response.status_code == 200:
                return response.json()
            return None

        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return None

    async def register_collection(self, policy_id: str, name: str = None, priority: int = 0) -> bool:
        """Register a Cardano collection with the Cardano NFT Price Service."""
        if not await self.is_available():
            return False

        try:
            service_url = await self._get_service_url()
            client = get_client("nft_price_service", timeout=10.0)
            response = await client.post(
                f"{service_url}/collections/register",
                params={
                    "policy_id": policy_id,
                    "name": name,
                    "priority": priority
                }
            )
            return response.status_code == 200

        except Exception as e:
            logger.error(f"Error registering collection: {e}")
            return False

    async def register_collections_batch(self, collections: List[Dict]) -> int:
        """Register multiple collections at once."""
        if not await self.is_available():
            return 0

        try:
            service_url = await self._get_service_url()
            client = get_client("nft_price_service", timeout=10.0)
            response = await client.post(
                f"{service_url}/collections/register-batch",
                json=collections
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("registered", 0)
            return 0

        except Exception as e:
            logger.error(f"Error registering collections batch: {e}")
            return 0


# Singleton instance
nft_price_client = NFTPriceClient()
