"""
Cardano NFT Price Service Client

Client for fetching Cardano NFT floor prices from the external Cardano NFT Price Service.
Falls back to TapTools direct calls if the service is unavailable.
"""

import os
import httpx
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta

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

    def is_configured(self) -> bool:
        """Check if the Cardano NFT Price Service is configured."""
        return bool(self.service_url)

    async def is_available(self) -> bool:
        """Check if the Cardano NFT Price Service is available."""
        if not self.is_configured():
            return False

        # Cache availability check for 5 minutes
        now = datetime.utcnow()
        if self._available is not None and self._last_check:
            if now - self._last_check < self._check_interval:
                return self._available

        try:
            async with httpx.AsyncClient(timeout=NFT_PRICE_SERVICE_TIMEOUT) as client:
                response = await client.get(f"{self.service_url}/health")
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
            async with httpx.AsyncClient(timeout=NFT_PRICE_SERVICE_TIMEOUT) as client:
                response = await client.get(f"{self.service_url}/floor/{policy_id}")

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
            async with httpx.AsyncClient(timeout=NFT_PRICE_SERVICE_TIMEOUT) as client:
                # Batch into chunks of 50
                all_floors = {}
                for i in range(0, len(policy_ids), 50):
                    chunk = policy_ids[i:i + 50]
                    ids_param = ",".join(chunk)

                    response = await client.get(
                        f"{self.service_url}/floors",
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
        if not self.is_configured():
            return None

        try:
            async with httpx.AsyncClient(timeout=NFT_PRICE_SERVICE_TIMEOUT) as client:
                response = await client.get(f"{self.service_url}/status")

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
            async with httpx.AsyncClient(timeout=NFT_PRICE_SERVICE_TIMEOUT) as client:
                response = await client.post(
                    f"{self.service_url}/collections/register",
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
            async with httpx.AsyncClient(timeout=NFT_PRICE_SERVICE_TIMEOUT) as client:
                response = await client.post(
                    f"{self.service_url}/collections/register-batch",
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
