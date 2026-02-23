"""
Cardano Foundation Token Registry Client

Queries the CF Token Registry API (tokens.cardano.org) to check whether Cardano
native tokens are officially registered. Registered tokens have cryptographic
proof of policy key ownership and Cardano Foundation human review.

API: https://tokens.cardano.org/metadata
- Single lookup: GET /metadata/{subject} (returns 204 for unregistered, NOT 404)
- Batch lookup: POST /metadata/query with {"subjects": [...], "properties": [...]}

Subject format: policyId + assetNameHex (lowercase, concatenated, NO dot separator)
"""

import json
import logging
from typing import Dict, List, Optional, Set

from services.http_client import get_client
from database import get_cache, set_cache
from config import CACHE_TTL_COLD

logger = logging.getLogger(__name__)

BASE_URL = "https://tokens.cardano.org/metadata"
BATCH_CHUNK_SIZE = 80
SENTINEL_NOT_REGISTERED = "__not_registered__"


class CardanoTokenRegistryService:
    """Client for the Cardano Foundation Token Registry API."""

    async def is_registered(self, subject: str) -> bool:
        """Check if a single token subject is registered. Uses cache."""
        subject = subject.lower()
        cache_key = f"cf_registry:{subject}"
        cached = await get_cache(cache_key)
        if cached is not None:
            return cached != SENTINEL_NOT_REGISTERED

        client = get_client("cardano_token_registry", timeout=10)
        try:
            resp = await client.get(f"{BASE_URL}/{subject}")
            if resp.status_code == 200:
                await set_cache(cache_key, resp.json(), CACHE_TTL_COLD)
                return True
            elif resp.status_code == 204:
                # Not registered — cache negative result
                await set_cache(cache_key, SENTINEL_NOT_REGISTERED, CACHE_TTL_COLD)
                return False
            else:
                logger.warning(f"CF Token Registry unexpected status {resp.status_code} for {subject}")
                return False
        except Exception as e:
            logger.warning(f"CF Token Registry lookup failed for {subject}: {e}")
            return False

    async def batch_check(self, subjects: List[str]) -> Dict[str, bool]:
        """
        Batch-check multiple token subjects against the registry.

        Returns {subject: True/False} for each subject.
        Queries in chunks of BATCH_CHUNK_SIZE.
        Uses cache for previously checked subjects.
        """
        if not subjects:
            return {}

        result: Dict[str, bool] = {}
        to_query: List[str] = []

        # Check cache first
        for subj in subjects:
            subj_lower = subj.lower()
            cache_key = f"cf_registry:{subj_lower}"
            cached = await get_cache(cache_key)
            if cached is not None:
                result[subj_lower] = cached != SENTINEL_NOT_REGISTERED
            else:
                to_query.append(subj_lower)

        if not to_query:
            return result

        # Batch query uncached subjects in chunks
        client = get_client("cardano_token_registry", timeout=15)
        for i in range(0, len(to_query), BATCH_CHUNK_SIZE):
            chunk = to_query[i:i + BATCH_CHUNK_SIZE]
            try:
                resp = await client.post(
                    f"{BASE_URL}/query",
                    json={
                        "subjects": chunk,
                        "properties": ["name", "ticker", "decimals"]
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Response is {"subjects": [{"subject": "...", "name": {...}, ...}, ...]}
                    found_subjects: Set[str] = set()
                    for entry in data.get("subjects", []):
                        subj = entry.get("subject", "").lower()
                        if subj:
                            found_subjects.add(subj)
                            result[subj] = True
                            await set_cache(f"cf_registry:{subj}", entry, CACHE_TTL_COLD)

                    # Mark missing ones as not registered
                    for subj in chunk:
                        if subj not in found_subjects:
                            result[subj] = False
                            await set_cache(f"cf_registry:{subj}", SENTINEL_NOT_REGISTERED, CACHE_TTL_COLD)

                    logger.debug(f"CF Registry batch: {len(found_subjects)}/{len(chunk)} registered")
                else:
                    logger.warning(f"CF Token Registry batch query returned {resp.status_code}")
                    # Mark all as unknown (don't cache)
                    for subj in chunk:
                        if subj not in result:
                            result[subj] = False

            except Exception as e:
                logger.warning(f"CF Token Registry batch query failed: {e}")
                for subj in chunk:
                    if subj not in result:
                        result[subj] = False

        return result


# Module-level singleton
cardano_token_registry = CardanoTokenRegistryService()
