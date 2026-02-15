"""
Live API Usage Queries

Fetches real-time usage data from APIs that expose it:
- CoinGecko: /key endpoint returns monthly call count
- CoinMarketCap: /key/info endpoint returns monthly usage
- Blockfrost: /metrics endpoint returns daily request counts
"""

import logging
from typing import Optional, Dict

from services.http_client import get_client
from database import get_api_key, get_cache, set_cache

logger = logging.getLogger(__name__)

CACHE_TTL = 600  # 10 minutes


async def get_live_usage(api_id: str) -> Optional[Dict]:
    """
    Get live usage data for an API that supports it.
    Results are cached for 10 minutes.

    Returns dict with: call_count, requests_limit, period_label, source
    Returns None if API doesn't support live queries or key not configured.
    """
    fetchers = {
        "coingecko": _fetch_coingecko_usage,
        "coinmarketcap": _fetch_cmc_usage,
        "blockfrost": _fetch_blockfrost_usage,
    }

    if api_id not in fetchers:
        return None

    # Check cache first
    cache_key = f"live_usage:{api_id}"
    cached = await get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        result = await fetchers[api_id]()
        if result:
            await set_cache(cache_key, result, ttl_seconds=CACHE_TTL)
        return result
    except Exception as e:
        logger.debug(f"Live usage query failed for {api_id}: {e}")
        return None


async def _fetch_coingecko_usage() -> Optional[Dict]:
    """
    Fetch CoinGecko Demo API usage via /key endpoint.
    Header: x-cg-demo-api-key
    """
    api_key = await get_api_key("coingecko")
    if not api_key:
        return None

    client = get_client("coingecko_usage", timeout=10.0)
    response = await client.get(
        "https://api.coingecko.com/api/v3/key",
        headers={"x-cg-demo-api-key": api_key},
        timeout=10.0
    )

    if response.status_code != 200:
        logger.debug(f"CoinGecko /key returned {response.status_code}")
        return None

    data = response.json()
    return {
        "call_count": data.get("current_total_monthly_calls", 0),
        "requests_limit": data.get("monthly_call_credit", 10000),
        "period_label": "month",
        "source": "live"
    }


async def _fetch_cmc_usage() -> Optional[Dict]:
    """
    Fetch CoinMarketCap usage via /v1/key/info endpoint.
    Header: X-CMC_PRO_API_KEY
    """
    api_key = await get_api_key("coinmarketcap")
    if not api_key:
        return None

    client = get_client("cmc_usage", timeout=10.0)
    response = await client.get(
        "https://pro-api.coinmarketcap.com/v1/key/info",
        headers={"X-CMC_PRO_API_KEY": api_key},
        timeout=10.0
    )

    if response.status_code != 200:
        logger.debug(f"CMC /key/info returned {response.status_code}")
        return None

    data = response.json()
    usage = data.get("data", {}).get("usage", {})
    current_month = usage.get("current_month", {})
    plan = data.get("data", {}).get("plan", {})

    return {
        "call_count": current_month.get("credits_used", 0),
        "requests_limit": plan.get("credit_limit_monthly", 10000),
        "period_label": "month",
        "source": "live"
    }


async def _fetch_blockfrost_usage() -> Optional[Dict]:
    """
    Fetch Blockfrost daily usage via /metrics endpoint.
    Sums today's requests from the metrics response.
    """
    api_key = await get_api_key("blockfrost")
    if not api_key:
        return None

    client = get_client("blockfrost_usage", timeout=10.0)
    response = await client.get(
        "https://cardano-mainnet.blockfrost.io/api/v0/usage/metrics",
        headers={"project_id": api_key},
        timeout=10.0
    )

    if response.status_code != 200:
        logger.debug(f"Blockfrost /usage/metrics returned {response.status_code}")
        return None

    data = response.json()
    # Blockfrost returns array of {time, calls} entries
    # Sum all calls for today's usage
    total_calls = 0
    if isinstance(data, list) and len(data) > 0:
        # Last entry is the most recent period
        last_entry = data[-1]
        total_calls = last_entry.get("calls", 0)

    return {
        "call_count": total_calls,
        "requests_limit": 50000,
        "period_label": "day",
        "source": "live"
    }
