"""
Cardano Shield Threat Feed Service

Fetches and caches blacklist/whitelist data from the Cardano Shield open-source
project (Apache 2.0, by AdaBox.io). Provides O(1) lookups for policy IDs and
addresses against known scam/malicious entries, plus whitelisted DEX/marketplace
contract addresses.

GitHub: https://github.com/adabox-aio/cardano-shield
License: Apache 2.0 (attribution required)
"""

import json
import logging
from typing import Dict, Optional, Tuple

from services.http_client import get_client
from database import get_cache, set_cache
from config import CACHE_TTL_COLD

logger = logging.getLogger(__name__)

BLACKLIST_URL = "https://raw.githubusercontent.com/adabox-aio/cardano-shield/main/config/blacklist.json"
WHITELIST_URL = "https://raw.githubusercontent.com/adabox-aio/cardano-shield/main/config/whitelist.json"

CACHE_KEY_BLACKLIST = "cardano_shield:blacklist"
CACHE_KEY_WHITELIST = "cardano_shield:whitelist"


class CardanoShieldService:
    """Singleton service for Cardano Shield threat intelligence lookups."""

    def __init__(self):
        # Inverted blacklist: {policy_id_lower: token_name}
        self._blacklisted_policies: Dict[str, str] = {}
        # Blacklisted stake addresses: {stake_addr_lower: token_name}
        self._blacklisted_stakes: Dict[str, str] = {}
        # Whitelisted addresses: {address_lower: label}
        self._whitelisted_addresses: Dict[str, str] = {}
        self._initialized = False

    async def initialize(self):
        """Load threat feed data from cache or GitHub."""
        try:
            await self._load_blacklist()
            await self._load_whitelist()
            self._initialized = True
            logger.info(
                f"Cardano Shield initialized: {len(self._blacklisted_policies)} blacklisted policies, "
                f"{len(self._blacklisted_stakes)} blacklisted stakes, "
                f"{len(self._whitelisted_addresses)} whitelisted addresses"
            )
        except Exception as e:
            logger.warning(f"Cardano Shield initialization failed: {e}")

    async def _load_blacklist(self):
        """Fetch blacklist from cache or GitHub raw URL."""
        cached = await get_cache(CACHE_KEY_BLACKLIST)
        if cached is not None:
            data = cached
        else:
            client = get_client("cardano_shield", timeout=15)
            resp = await client.get(BLACKLIST_URL)
            if resp.status_code != 200:
                logger.warning(f"Cardano Shield blacklist fetch failed: HTTP {resp.status_code}")
                return
            data = resp.json()
            await set_cache(CACHE_KEY_BLACKLIST, data, CACHE_TTL_COLD)

        # blacklist.json structure: {"tokens": {"TokenName": "policyId", ...}, "stake_addresses": {"TokenName": "stake1...", ...}}
        tokens = data.get("tokens", {})
        for token_name, policy_id in tokens.items():
            if policy_id:
                self._blacklisted_policies[policy_id.lower()] = token_name

        stakes = data.get("stake_addresses", {})
        for token_name, stake_addr in stakes.items():
            if stake_addr:
                self._blacklisted_stakes[stake_addr.lower()] = token_name

    async def _load_whitelist(self):
        """Fetch whitelist from cache or GitHub raw URL."""
        cached = await get_cache(CACHE_KEY_WHITELIST)
        if cached is not None:
            data = cached
        else:
            client = get_client("cardano_shield", timeout=15)
            resp = await client.get(WHITELIST_URL)
            if resp.status_code != 200:
                logger.warning(f"Cardano Shield whitelist fetch failed: HTTP {resp.status_code}")
                return
            data = resp.json()
            await set_cache(CACHE_KEY_WHITELIST, data, CACHE_TTL_COLD)

        # whitelist.json structure: {"addresses": {"Label": "addr1...", ...}}
        addresses = data.get("addresses", {})
        for label, addr in addresses.items():
            if addr:
                self._whitelisted_addresses[addr.lower()] = label

    async def _refresh_feed(self):
        """Re-fetch threat feed data (called periodically)."""
        self._blacklisted_policies.clear()
        self._blacklisted_stakes.clear()
        self._whitelisted_addresses.clear()
        # Clear cache so we fetch fresh data
        await set_cache(CACHE_KEY_BLACKLIST, None, 0)
        await set_cache(CACHE_KEY_WHITELIST, None, 0)
        await self.initialize()

    def check_policy_id(self, policy_id: str) -> Optional[str]:
        """Check if a policy ID is blacklisted. Returns token name or None."""
        return self._blacklisted_policies.get(policy_id.lower())

    def check_address(self, address: str) -> Optional[str]:
        """Check if an address is whitelisted. Returns label or None."""
        return self._whitelisted_addresses.get(address.lower())

    def is_stake_blacklisted(self, stake_addr: str) -> Optional[str]:
        """Check if a stake address is blacklisted. Returns token name or None."""
        return self._blacklisted_stakes.get(stake_addr.lower())

    def get_threat_feed_stats(self) -> dict:
        """Return summary statistics about the loaded threat feed."""
        return {
            "initialized": self._initialized,
            "blacklisted_policies": len(self._blacklisted_policies),
            "blacklisted_stakes": len(self._blacklisted_stakes),
            "whitelisted_addresses": len(self._whitelisted_addresses),
        }


# Module-level singleton
cardano_shield = CardanoShieldService()
