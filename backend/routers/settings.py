"""
Settings Router - API Key Management

Provides endpoints for managing API keys and their enabled status.
API keys are stored in the database and can override environment variables.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_all_api_settings, get_api_setting, save_api_setting, delete_api_setting,
    update_api_enabled_status, get_api_key,
    get_api_usage, get_all_api_usage, get_api_rate_limit, save_api_rate_limit,
    delete_api_rate_limit, get_all_api_rate_limits
)
from auth_utils import verify_session

router = APIRouter(prefix="/settings", tags=["settings"])

# API Registry - defines all supported APIs with metadata
# Default rate limits are for free tiers; users can customize via the UI
API_REGISTRY = {
    # Cardano APIs
    "blockfrost": {
        "name": "Blockfrost",
        "category": "cardano",
        "description": "Primary Cardano blockchain API for wallet balances, transactions, and staking info",
        "required": True,
        "docs_url": "https://blockfrost.io/",
        "env_var": "BLOCKFROST_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 50,000 requests/day, 10 requests/sec, burst of 500 requests",
        "default_limit": 50000,  # 50k requests per day on free tier
        "default_period": 86400,
        "period_label": "day"
    },
    "taptools": {
        "name": "TapTools",
        "category": "cardano",
        "description": "Cardano NFT floor prices and token analytics",
        "required": False,
        "docs_url": "https://www.taptools.io/",
        "env_var": "TAPTOOLS_API_KEY",
        "pricing": "paid",
        "pricing_note": "$9/mo plan: 100 requests/day",
        "default_limit": 100,  # $9/mo plan limit
        "default_period": 86400,
        "period_label": "day"
    },
    "cexplorer": {
        "name": "CExplorer",
        "category": "cardano",
        "description": "Cardano staking and DeFi data",
        "required": False,
        "docs_url": "https://cexplorer.io/",
        "env_var": "CEXPLORER_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier available, limits not documented",
        "default_limit": None,  # Not documented
        "default_period": 86400,
        "period_label": "day"
    },
    "maestro": {
        "name": "Maestro",
        "category": "cardano",
        "description": "Alternative Cardano API for redundancy",
        "required": False,
        "docs_url": "https://www.gomaestro.org/",
        "env_var": "MAESTRO_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 500,000 credits/mo (credits vary per call)",
        "default_limit": None,  # Credits vary per call type
        "default_period": 86400,
        "period_label": "day"
    },

    # EVM APIs (Ethereum, Polygon, Base)
    "alchemy": {
        "name": "Alchemy",
        "category": "evm",
        "description": "Ethereum, Polygon, and Base wallet data, NFTs, and token balances",
        "required": False,
        "docs_url": "https://www.alchemy.com/",
        "env_var": "ALCHEMY_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 30M compute units/mo (~1.8M simple requests)",
        "default_limit": 60000,  # ~30M CU / 30 days = 1M CU/day = ~60k simple requests/day (conservative)
        "default_period": 86400,
        "period_label": "day"
    },
    "etherscan": {
        "name": "Etherscan",
        "category": "evm",
        "description": "Ethereum blockchain explorer API for transaction data",
        "required": False,
        "docs_url": "https://etherscan.io/apis",
        "env_var": "ETHERSCAN_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 3 calls/sec OR 100,000 calls/day",
        "default_limit": 100000,  # 100k calls per day
        "default_period": 86400,
        "period_label": "day"
    },
    "beaconchain": {
        "name": "Beaconchain",
        "category": "evm",
        "description": "Ethereum staking and validator data",
        "required": False,
        "docs_url": "https://beaconcha.in/",
        "env_var": "BEACONCHAIN_API_KEY",
        "pricing": "freemium",
        "pricing_note": "Free tier limited; Premium from $5/mo",
        "default_limit": None,  # Not clearly documented
        "default_period": 86400,
        "period_label": "day"
    },

    # Solana APIs
    "helius": {
        "name": "Helius",
        "category": "solana",
        "description": "Solana wallet balances, tokens, and NFTs",
        "required": False,
        "docs_url": "https://helius.xyz/",
        "env_var": "HELIUS_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 1M credits/mo, 10 RPS rate limit",
        "default_limit": 33333,  # ~1M credits / 30 days = 33k credits/day
        "default_period": 86400,
        "period_label": "day"
    },

    # Pricing APIs
    "coingecko": {
        "name": "CoinGecko",
        "category": "pricing",
        "description": "Cryptocurrency price data (works without key, key increases limits)",
        "required": False,
        "docs_url": "https://www.coingecko.com/en/api",
        "pricing": "free",
        "pricing_note": "Demo API (free): 30 calls/min, 10,000 calls/month",
        "env_var": "COINGECKO_API_KEY",
        "default_limit": 333,  # 10k/month ≈ 333/day
        "default_period": 86400,
        "period_label": "day"
    },
    "coinmarketcap": {
        "name": "CoinMarketCap",
        "category": "pricing",
        "description": "Alternative cryptocurrency price data",
        "required": False,
        "docs_url": "https://coinmarketcap.com/api/",
        "env_var": "CMC_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 10,000 calls/mo",
        "default_limit": 333,  # ~10k/month = 333/day
        "default_period": 86400,
        "period_label": "day"
    },

    # Data & Analytics APIs
    "thegraph": {
        "name": "The Graph",
        "category": "analytics",
        "description": "Decentralized protocol for indexing and querying blockchain data",
        "required": False,
        "docs_url": "https://thegraph.com/studio/apikeys/",
        "env_var": "GRAPH_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 100,000 queries/mo",
        "default_limit": 3333,  # ~100k/month = 3333/day
        "default_period": 86400,
        "period_label": "day"
    },
    "dune": {
        "name": "Dune Analytics",
        "category": "analytics",
        "description": "Blockchain analytics and SQL queries",
        "required": False,
        "docs_url": "https://dune.com/settings/api",
        "env_var": "DUNE_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 1,000 queries/mo",
        "default_limit": 33,  # ~1k/month = 33/day
        "default_period": 86400,
        "period_label": "day"
    },

    # Service APIs
    "logokit": {
        "name": "LogoKit",
        "category": "services",
        "description": "Logo and icon service for crypto tokens and brands",
        "required": False,
        "docs_url": "https://logokit.com/",
        "env_var": "LOGOKIT_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier available",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day"
    },

    # Exchange APIs
    "coinbase": {
        "name": "Coinbase",
        "category": "exchanges",
        "description": "Track Coinbase exchange balances (requires cdp_api_key.json file)",
        "required": False,
        "docs_url": "https://coinbase.com/settings/api",
        "env_var": "COINBASE_CONFIGURED",  # Special handling for file-based config
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day"
    },
    "binance": {
        "name": "Binance.com",
        "category": "exchanges",
        "description": "Track Binance.com exchange balances",
        "required": False,
        "docs_url": "https://www.binance.com/en/my/settings/api-management",
        "env_var": "BINANCE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_secret": True  # Also needs BINANCE_API_SECRET
    },
    "binance_us": {
        "name": "Binance.US",
        "category": "exchanges",
        "description": "Track Binance.US exchange balances",
        "required": False,
        "docs_url": "https://www.binance.us/en/usercenter/settings/api-management",
        "env_var": "BINANCE_US_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_secret": True  # Also needs BINANCE_US_API_SECRET
    },
    "okx": {
        "name": "OKX",
        "category": "exchanges",
        "description": "Track OKX exchange balances",
        "required": False,
        "docs_url": "https://www.okx.com/account/my-api",
        "env_var": "OKX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_secret": True,  # Also needs OKX_API_SECRET
        "requires_passphrase": True  # Also needs OKX_API_PASSPHRASE
    },
    "bitget": {
        "name": "Bitget",
        "category": "exchanges",
        "description": "Track Bitget exchange balances",
        "required": False,
        "docs_url": "https://www.bitget.com/en/account/newapi",
        "env_var": "BITGET_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_secret": True,  # Also needs BITGET_API_SECRET
        "requires_passphrase": True  # Also needs BITGET_API_PASSPHRASE
    },
    "gate": {
        "name": "Gate.io",
        "category": "exchanges",
        "description": "Track Gate.io exchange balances",
        "required": False,
        "docs_url": "https://www.gate.io/myaccount/apiv4keys",
        "env_var": "GATE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_secret": True  # Also needs GATE_API_SECRET
    },
    "kucoin": {
        "name": "KuCoin",
        "category": "exchanges",
        "description": "Track KuCoin exchange balances",
        "required": False,
        "docs_url": "https://www.kucoin.com/account/api",
        "env_var": "KUCOIN_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_secret": True,  # Also needs KUCOIN_API_SECRET
        "requires_passphrase": True  # Also needs KUCOIN_API_PASSPHRASE
    },
}

# Category labels for grouping
CATEGORIES = {
    "cardano": {
        "name": "Cardano",
        "description": "APIs for Cardano blockchain data",
        "icon": "ADA"
    },
    "evm": {
        "name": "EVM Chains",
        "description": "APIs for Ethereum, Polygon, and Base",
        "icon": "ETH"
    },
    "solana": {
        "name": "Solana",
        "description": "APIs for Solana blockchain data",
        "icon": "SOL"
    },
    "pricing": {
        "name": "Pricing",
        "description": "Cryptocurrency price data providers",
        "icon": "$"
    },
    "analytics": {
        "name": "Data & Analytics",
        "description": "Blockchain analytics and data indexing",
        "icon": "📊"
    },
    "services": {
        "name": "Services",
        "description": "Supporting services for crypto tracking",
        "icon": "🛠️"
    },
    "exchanges": {
        "name": "Exchanges",
        "description": "Cryptocurrency exchange integrations",
        "icon": "🏦"
    }
}


class APIKeyUpdate(BaseModel):
    api_key: str
    api_secret: Optional[str] = None  # For exchange APIs
    api_passphrase: Optional[str] = None  # For some exchange APIs (OKX, Bitget, KuCoin)


class APIEnabledUpdate(BaseModel):
    enabled: bool


@router.get("/apis")
async def list_apis():
    """
    List all supported APIs with their current status.
    Returns APIs grouped by category with enabled/configured status.
    """
    # Get saved settings from database
    saved_settings = await get_all_api_settings()
    saved_map = {s['api_name']: s for s in saved_settings}

    # Build response with all APIs
    apis_by_category = {}

    for api_id, api_info in API_REGISTRY.items():
        category = api_info['category']
        if category not in apis_by_category:
            apis_by_category[category] = {
                **CATEGORIES.get(category, {"name": category, "description": "", "icon": ""}),
                "apis": []
            }

        # Check if enabled in database or has env var
        saved = saved_map.get(api_id)
        env_key = os.getenv(api_info['env_var'], "")

        # Determine status
        if saved:
            enabled = bool(saved.get('enabled'))
            has_key = bool(saved.get('api_key'))
            source = "database"
        elif env_key:
            enabled = True
            has_key = True
            source = "environment"
        else:
            enabled = False
            has_key = False
            source = None

        apis_by_category[category]["apis"].append({
            "id": api_id,
            "name": api_info['name'],
            "description": api_info['description'],
            "required": api_info['required'],
            "docs_url": api_info['docs_url'],
            "enabled": enabled,
            "configured": has_key,
            "source": source
        })

    return {
        "categories": apis_by_category,
        "total_apis": len(API_REGISTRY),
        "configured_count": sum(1 for c in apis_by_category.values() for a in c['apis'] if a['configured'])
    }


@router.get("/apis/{api_id}")
async def get_api_status(api_id: str):
    """Get status of a specific API."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    api_info = API_REGISTRY[api_id]
    saved = await get_api_setting(api_id)
    env_key = os.getenv(api_info['env_var'], "")

    if saved:
        enabled = bool(saved.get('enabled'))
        has_key = bool(saved.get('api_key'))
        # Mask the key for display
        key_preview = saved['api_key'][:4] + "..." + saved['api_key'][-4:] if saved.get('api_key') and len(saved['api_key']) > 8 else "****"
        source = "database"
    elif env_key:
        enabled = True
        has_key = True
        key_preview = env_key[:4] + "..." + env_key[-4:] if len(env_key) > 8 else "****"
        source = "environment"
    else:
        enabled = False
        has_key = False
        key_preview = None
        source = None

    return {
        "id": api_id,
        **api_info,
        "enabled": enabled,
        "configured": has_key,
        "key_preview": key_preview,
        "source": source
    }


@router.put("/apis/{api_id}")
async def enable_api(api_id: str, data: APIKeyUpdate, user_id: int = Depends(verify_session)):
    """Enable an API and save its key. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    api_key = data.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    # Get optional secret and passphrase (for exchange APIs)
    api_secret = data.api_secret.strip() if data.api_secret else None
    api_passphrase = data.api_passphrase.strip() if data.api_passphrase else None

    await save_api_setting(api_id, api_key, enabled=True, user_id=user_id,
                          api_secret=api_secret, api_passphrase=api_passphrase)

    return {
        "message": f"{API_REGISTRY[api_id]['name']} API enabled",
        "api_id": api_id,
        "enabled": True
    }


@router.patch("/apis/{api_id}/enabled")
async def toggle_api_enabled(api_id: str, data: APIEnabledUpdate, user_id: int = Depends(verify_session)):
    """Toggle API enabled/disabled status without changing the key. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    success = await update_api_enabled_status(api_id, data.enabled, user_id=user_id)

    if not success:
        raise HTTPException(status_code=400, detail="API key not configured. Please save an API key first.")

    return {
        "message": f"{API_REGISTRY[api_id]['name']} API {'enabled' if data.enabled else 'disabled'}",
        "api_id": api_id,
        "enabled": data.enabled
    }


@router.delete("/apis/{api_id}")
async def disable_api(api_id: str, user_id: int = Depends(verify_session)):
    """Disable an API and clear its saved key. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    await delete_api_setting(api_id, user_id=user_id)

    return {
        "message": f"{API_REGISTRY[api_id]['name']} API disabled",
        "api_id": api_id,
        "enabled": False
    }


@router.get("/apis/{api_id}/test")
async def test_api(api_id: str):
    """Test if an API key is valid by making a simple request."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    # Get the effective API key (database or env)
    api_key = await get_effective_api_key(api_id)
    if not api_key:
        return {
            "api_id": api_id,
            "success": False,
            "error": "No API key configured"
        }

    # Test based on API type
    try:
        if api_id == "blockfrost":
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://cardano-mainnet.blockfrost.io/api/v0/health",
                    headers={"project_id": api_key},
                    timeout=10.0
                )
                success = response.status_code == 200
                error = None if success else f"Status {response.status_code}"

        elif api_id == "alchemy":
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://eth-mainnet.g.alchemy.com/v2/{api_key}",
                    timeout=10.0
                )
                success = response.status_code == 200
                error = None if success else f"Status {response.status_code}"

        elif api_id == "helius":
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.helius.xyz/v0/addresses/11111111111111111111111111111111/balances?api-key={api_key}",
                    timeout=10.0
                )
                success = response.status_code == 200
                error = None if success else f"Status {response.status_code}"

        else:
            # Generic - just confirm we have a key
            return {
                "api_id": api_id,
                "success": True,
                "message": "API key is configured (test not implemented for this API)"
            }

        return {
            "api_id": api_id,
            "success": success,
            "error": error
        }

    except Exception as e:
        return {
            "api_id": api_id,
            "success": False,
            "error": str(e)
        }


async def get_effective_api_key(api_id: str) -> str:
    """
    Get the effective API key for an API.
    Checks database first, falls back to environment variable.
    """
    if api_id not in API_REGISTRY:
        return ""

    # Check database first
    db_key = await get_api_key(api_id)
    if db_key:
        return db_key

    # Fall back to environment variable
    env_var = API_REGISTRY[api_id]['env_var']
    return os.getenv(env_var, "")


# ============ API Utilization Tracking ============

class RateLimitUpdate(BaseModel):
    requests_limit: int
    period_seconds: Optional[int] = 86400


@router.get("/api-utilization")
async def get_api_utilization():
    """
    Get API utilization data for all configured APIs.
    Returns usage counts, limits, and utilization percentages.
    """
    from datetime import datetime, timedelta

    # Get current usage for all APIs
    usage_data = await get_all_api_usage()
    usage_map = {u['api_name']: u for u in usage_data}

    # Get custom rate limits
    custom_limits = await get_all_api_rate_limits()
    limits_map = {l['api_name']: l for l in custom_limits}

    # Get saved API settings to know which are configured
    saved_settings = await get_all_api_settings()
    saved_map = {s['api_name']: s for s in saved_settings}

    utilization = []

    for api_id, api_info in API_REGISTRY.items():
        # Check if configured (has key in db or env)
        saved = saved_map.get(api_id)
        env_key = os.getenv(api_info['env_var'], "")
        is_configured = bool((saved and saved.get('api_key')) or env_key)

        # Get usage data
        usage = usage_map.get(api_id, {})
        call_count = usage.get('call_count', 0)

        # Get rate limit (custom or default)
        custom_limit = limits_map.get(api_id)
        if custom_limit:
            requests_limit = custom_limit['requests_limit']
            period_seconds = custom_limit['period_seconds']
        else:
            requests_limit = api_info.get('default_limit')  # May be None
            period_seconds = api_info.get('default_period', 86400)

        # Calculate utilization percentage (None if limit unknown)
        if requests_limit is not None and requests_limit > 0:
            utilization_pct = min(100, round((call_count / requests_limit) * 100, 1))
        else:
            utilization_pct = None  # Unknown limit

        # Calculate time until reset
        now = datetime.now()
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(seconds=period_seconds)
        seconds_until_reset = max(0, (period_end - now).total_seconds())

        # Format reset time
        hours_until_reset = int(seconds_until_reset // 3600)
        minutes_until_reset = int((seconds_until_reset % 3600) // 60)
        if hours_until_reset > 0:
            reset_text = f"{hours_until_reset}h {minutes_until_reset}m"
        else:
            reset_text = f"{minutes_until_reset}m"

        utilization.append({
            "api_id": api_id,
            "name": api_info['name'],
            "category": api_info['category'],
            "configured": is_configured,
            "call_count": call_count,
            "requests_limit": requests_limit,
            "utilization_pct": utilization_pct,
            "period_label": api_info.get('period_label', 'day'),
            "reset_in": reset_text,
            "seconds_until_reset": int(seconds_until_reset),
            "has_custom_limit": custom_limit is not None,
            "pricing": api_info.get('pricing', 'free')
        })

    # Sort by utilization (highest first, None last), then by name
    utilization.sort(key=lambda x: (-(x['utilization_pct'] or -1), x['name']))

    return {
        "utilization": utilization,
        "summary": {
            "total_apis": len(API_REGISTRY),
            "configured_count": sum(1 for u in utilization if u['configured']),
            "high_utilization_count": sum(1 for u in utilization if u['utilization_pct'] is not None and u['utilization_pct'] >= 80),
            "total_calls_today": sum(u['call_count'] for u in utilization)
        }
    }


@router.get("/api-utilization/{api_id}")
async def get_single_api_utilization(api_id: str):
    """Get utilization data for a specific API."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    from datetime import datetime, timedelta

    api_info = API_REGISTRY[api_id]

    # Get usage
    usage = await get_api_usage(api_id)
    call_count = usage.get('call_count', 0)

    # Get rate limit
    custom_limit = await get_api_rate_limit(api_id)
    if custom_limit:
        requests_limit = custom_limit['requests_limit']
        period_seconds = custom_limit['period_seconds']
    else:
        requests_limit = api_info.get('default_limit')  # May be None
        period_seconds = api_info.get('default_period', 86400)

    # Calculate utilization (None if limit unknown)
    if requests_limit is not None and requests_limit > 0:
        utilization_pct = min(100, round((call_count / requests_limit) * 100, 1))
    else:
        utilization_pct = None

    # Calculate reset time
    now = datetime.now()
    period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(seconds=period_seconds)
    seconds_until_reset = max(0, (period_end - now).total_seconds())

    hours_until_reset = int(seconds_until_reset // 3600)
    minutes_until_reset = int((seconds_until_reset % 3600) // 60)
    reset_text = f"{hours_until_reset}h {minutes_until_reset}m" if hours_until_reset > 0 else f"{minutes_until_reset}m"

    return {
        "api_id": api_id,
        "name": api_info['name'],
        "call_count": call_count,
        "requests_limit": requests_limit,
        "utilization_pct": utilization_pct,
        "period_label": api_info.get('period_label', 'day'),
        "reset_in": reset_text,
        "seconds_until_reset": int(seconds_until_reset),
        "has_custom_limit": custom_limit is not None,
        "default_limit": api_info.get('default_limit')
    }


@router.put("/api-utilization/{api_id}/limit")
async def update_api_rate_limit(api_id: str, data: RateLimitUpdate, user_id: int = Depends(verify_session)):
    """Update custom rate limit for an API. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    if data.requests_limit <= 0:
        raise HTTPException(status_code=400, detail="Rate limit must be positive")

    await save_api_rate_limit(api_id, data.requests_limit, data.period_seconds)

    return {
        "message": f"Rate limit updated for {API_REGISTRY[api_id]['name']}",
        "api_id": api_id,
        "requests_limit": data.requests_limit,
        "period_seconds": data.period_seconds
    }


@router.delete("/api-utilization/{api_id}/limit")
async def reset_api_rate_limit(api_id: str, user_id: int = Depends(verify_session)):
    """Reset rate limit to default for an API. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    await delete_api_rate_limit(api_id)

    return {
        "message": f"Rate limit reset to default for {API_REGISTRY[api_id]['name']}",
        "api_id": api_id,
        "default_limit": API_REGISTRY[api_id].get('default_limit', 1000)
    }
