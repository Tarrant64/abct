"""
Mobile API Router - Optimized endpoints for ABCT mobile companion app.

This module provides mobile-friendly API endpoints with:
- Consolidated responses (fewer API calls)
- OHLCV chart data with multiple fallback sources
- Simplified data formats
- Proper caching and error handling
- ETag/If-None-Match conditional GETs on every endpoint (304 on match)
- Opt-in slim chart payloads (/chart/portfolio-history?slim=true)

All endpoints require authentication via verify_session.
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Request, Response
from fastapi.routing import APIRoute
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import hashlib
import httpx
import logging
import sys
import os
import asyncio
import json as json_mod
import aiosqlite

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing routers and services
from routers import portfolio, wallets, exchanges, defi, nfts
from services.pricing import pricing_service
from services.logokit_service import logokit_service
from services.token_metadata_cache import metadata_cache
from services.cardano import cardano_service
from database import (
    get_all_wallets,
    get_wallet_balance,
    get_wallet_assets,
    get_wallet_balances_bulk,
    get_wallet_asset_counts_bulk,
    get_cache,
    get_stale_cache,
    set_cache,
    get_username_by_user_id,
    get_wallet_sources,
    get_wallet_source_by_id,
)
from auth_utils import verify_session
from middleware.demo_mode import is_demo_user
from services.http_client import get_client
from config import DATABASE_PATH

def _etag_matches(if_none_match: str, etag: str) -> bool:
    """RFC 7232 weak comparison for If-None-Match: ignore W/ prefixes,
    handle comma-separated lists and the '*' wildcard."""
    for candidate in if_none_match.split(','):
        candidate = candidate.strip()
        if candidate == '*':
            return True
        if candidate.startswith('W/') or candidate.startswith('w/'):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


class _ConditionalGetRoute(APIRoute):
    """Adds ETag / If-None-Match -> 304 support to every GET in this router.

    The ETag is a hash of the response bytes FastAPI already serialized
    (no re-serialization or payload recompute), so it is stable for
    identical payloads and rotates when the payload changes. Purely
    additive: requests without If-None-Match get the same body and
    headers as before plus ETag; refresh=true always returns a full 200.
    """

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def conditional_handler(request: Request) -> Response:
            response = await original_handler(request)
            if request.method != "GET" or response.status_code != 200:
                return response
            body = getattr(response, "body", b"")
            if not body:
                return response
            etag = f'"{hashlib.sha256(body).hexdigest()[:32]}"'
            response.headers["ETag"] = etag
            # refresh=true means "give me fresh data no matter what" —
            # never short-circuit it with a 304 (mirrors FastAPI bool parsing)
            if request.query_params.get("refresh", "").lower() in ("1", "true", "yes", "on"):
                return response
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and _etag_matches(if_none_match, etag):
                return Response(status_code=304, headers={"ETag": etag})
            return response

        return conditional_handler


router = APIRouter(prefix="/api/mobile", tags=["mobile"], route_class=_ConditionalGetRoute)
logger = logging.getLogger(__name__)

# Cache TTL
MOBILE_CACHE_TTL = 120  # 2 minutes for mobile responses

# Native stake-account info (delegation/rewards) cache: changes on-chain at
# epoch cadence (days); 10 minutes keeps the mobile staking read DB-only in
# steady state so it can never queue behind scan traffic (P3-FIX3)
STAKE_ACCOUNT_INFO_TTL_S = 600
CHART_CACHE_TTL = 900  # 15 minutes for chart data

# Native coin symbol/decimals per supported blockchain (used by /wallets)
_WALLET_NATIVE_CONFIG = {
    'cardano': {'symbol': 'ADA', 'decimals': 6},
    'bitcoin': {'symbol': 'BTC', 'decimals': 8},
    'ethereum': {'symbol': 'ETH', 'decimals': 18},
    'solana': {'symbol': 'SOL', 'decimals': 9},
    'polygon': {'symbol': 'POL', 'decimals': 18},
    'base': {'symbol': 'ETH', 'decimals': 18},
    'algorand': {'symbol': 'ALGO', 'decimals': 6},
    'bsc': {'symbol': 'BNB', 'decimals': 18},
    'arbitrum': {'symbol': 'ETH', 'decimals': 18},
    'avalanche': {'symbol': 'AVAX', 'decimals': 18},
    'tron': {'symbol': 'TRX', 'decimals': 6},
    'xrp': {'symbol': 'XRP', 'decimals': 6},
    'hedera': {'symbol': 'HBAR', 'decimals': 8},
    'multiversx': {'symbol': 'EGLD', 'decimals': 18},
    'sui': {'symbol': 'SUI', 'decimals': 9},
    'aptos': {'symbol': 'APT', 'decimals': 8},
    'filecoin': {'symbol': 'FIL', 'decimals': 18},
    'litecoin': {'symbol': 'LTC', 'decimals': 8},
    'dogecoin': {'symbol': 'DOGE', 'decimals': 8},
    'zcash': {'symbol': 'ZEC', 'decimals': 8},
    'tezos': {'symbol': 'XTZ', 'decimals': 6},
    'stacks': {'symbol': 'STX', 'decimals': 6},
    'vechain': {'symbol': 'VET', 'decimals': 18},
    'cosmos': {'symbol': 'ATOM', 'decimals': 6},
    'near': {'symbol': 'NEAR', 'decimals': 24},
    'icp': {'symbol': 'ICP', 'decimals': 8},
}


# Display names for tokens not in metadata_cache (CoinGecko top 250)
_TOKEN_NAMES = {
    'INDY': 'Indigo',
    'LQ': 'Liqwid Finance',
    'STRIKE': 'Strike',
    'MIN': 'Minswap',
    'SUNDAE': 'SundaeSwap',
    'LENFI': 'Lenfi',
    'SNEK': 'Snek',
    'WMT': 'World Mobile',
    'MILK': 'MuesliSwap',
    'HUNT': 'Hunt',
    'HOSKY': 'Hosky',
    'NMKR': 'NMKR',
}


def _as_float(value, default: float = 0.0) -> float:
    """Coerce API/cache values that may arrive as str, int, float or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        if value is not None:
            logger.debug(f"_as_float: could not coerce {value!r}; using {default}")
        return default


async def _resolve_token_info(symbol: str) -> tuple[str, str]:
    """Look up proper display name and image URL for a token symbol.

    Fallback chain: metadata_cache → CoinGecko /coins/{id} → LogoKit.
    Always returns full external URLs safe for both web and mobile clients.
    """
    from services.pricing import ASSET_TO_COINGECKO

    meta = await metadata_cache.get_metadata(symbol)
    name = (meta.get('name') if meta else None) or _TOKEN_NAMES.get(symbol.upper()) or symbol.capitalize()
    image_url = (meta.get('image_url') if meta else None)

    # Fallback: direct CoinGecko lookup for tokens with known CG IDs
    if not image_url:
        cg_id = ASSET_TO_COINGECKO.get(symbol.upper())
        if cg_id:
            try:
                client = get_client("coingecko", timeout=10.0)
                resp = await client.get(
                    f"https://api.coingecko.com/api/v3/coins/{cg_id}",
                    params={"localization": "false", "tickers": "false",
                            "market_data": "false", "community_data": "false",
                            "developer_data": "false"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    img = data.get('image', {})
                    cg_image = img.get('small') or img.get('large') or img.get('thumb')
                    if cg_image:
                        image_url = cg_image
                        await metadata_cache.upsert_metadata(symbol, {
                            'coingecko_id': cg_id,
                            'name': data.get('name') or name,
                            'image_url': cg_image,
                        })
            except Exception as e:
                logger.debug(f"CoinGecko image fallback failed for {symbol}: {e}")

    if not image_url:
        image_url = logokit_service.get_crypto_logo_url(symbol, size=64)

    return name, image_url

# Exchange display info
EXCHANGE_INFO = {
    "coinbase": {
        "display_name": "Coinbase",
        "logo_url": "https://www.coinbase.com/favicon.ico"
    },
    "binance": {
        "display_name": "Binance.com",
        "logo_url": "https://public.bnbstatic.com/static/images/common/favicon.ico"
    },
    "binance_us": {
        "display_name": "Binance.US",
        "logo_url": "https://public.bnbstatic.com/static/images/common/favicon.ico"
    },
    "okx": {
        "display_name": "OKX",
        "logo_url": "https://static.okx.com/cdn/assets/imgs/MjAyMTQ/5C7F82ADE3C3FC61.png"
    },
    "bitget": {
        "display_name": "Bitget",
        "logo_url": "https://www.bitget.com/favicon.ico"
    },
    "gate": {
        "display_name": "Gate.io",
        "logo_url": "https://www.gate.io/favicon.ico"
    },
    "kucoin": {
        "display_name": "KuCoin",
        "logo_url": "https://www.kucoin.com/favicon.ico"
    }
}

# CoinGecko ID mapping for OHLCV data — use the comprehensive map from pricing.py
# (the old SYMBOL_TO_COINGECKO only had 11 tokens, causing "chart unavailable" for
# AVAX, HNT, NIGHT, MATIC, and all other non-top-10 tokens)
from services.pricing import ASSET_TO_COINGECKO as SYMBOL_TO_COINGECKO

SOURCE_TYPE_ORDER = ["on_chain", "exchange", "staking", "defi", "nft"]

SOURCE_GROUP_DISPLAY = {
    "on_chain": "Self-Custody Wallets",
    "exchange": "Exchanges",
    "staking": "Staking",
    "defi": "DeFi",
    "nft": "NFTs",
}

CHAIN_ICON_URLS = {
    "cardano": "https://cryptologos.cc/logos/cardano-ada-logo.png",
    "bitcoin": "https://cryptologos.cc/logos/bitcoin-btc-logo.png",
    "ethereum": "https://cryptologos.cc/logos/ethereum-eth-logo.png",
    "solana": "https://cryptologos.cc/logos/solana-sol-logo.png",
    "polygon": "https://cryptologos.cc/logos/polygon-matic-logo.png",
    "base": "https://avatars.githubusercontent.com/u/108554348?s=32",
    "algorand": "https://cryptologos.cc/logos/algorand-algo-logo.png",
    "bsc": "https://cryptologos.cc/logos/bnb-bnb-logo.png",
    "arbitrum": "https://avatars.githubusercontent.com/u/119917794?s=32",
    "avalanche": "https://cryptologos.cc/logos/avalanche-avax-logo.png",
    "tron": "https://cryptologos.cc/logos/tron-trx-logo.png",
    "xrp": "https://cryptologos.cc/logos/xrp-xrp-logo.png",
    "hedera": "https://cryptologos.cc/logos/hedera-hbar-logo.png",
    "multiversx": "https://cryptologos.cc/logos/multiversx-egld-logo.png",
    "sui": "https://cryptologos.cc/logos/sui-sui-logo.png",
    "aptos": "https://cryptologos.cc/logos/aptos-apt-logo.png",
    "filecoin": "https://cryptologos.cc/logos/filecoin-fil-logo.png",
    "litecoin": "https://cryptologos.cc/logos/litecoin-ltc-logo.png",
    "dogecoin": "https://cryptologos.cc/logos/dogecoin-doge-logo.png",
    "zcash": "https://cryptologos.cc/logos/zcash-zec-logo.png",
    "tezos": "https://cryptologos.cc/logos/tezos-xtz-logo.png",
    "stacks": "https://cryptologos.cc/logos/stacks-stx-logo.png",
    "vechain": "https://cryptologos.cc/logos/vechain-vet-logo.png",
    "cosmos": "https://cryptologos.cc/logos/cosmos-atom-logo.png",
    "near": "https://cryptologos.cc/logos/near-protocol-near-logo.png",
    "icp": "https://cryptologos.cc/logos/internet-computer-icp-logo.png",
}


async def _fetch_asset_sparklines(symbols: list, max_points: int = 24) -> dict:
    """Fetch 7-day sparkline price data from CoinGecko for a list of symbols.

    Returns dict mapping symbol -> {sparkline_7d, sparkline_24h, cg_image_url}.
    When max_points=0, only fetches images (no sparkline data) for lighter payload.
    """
    from services.pricing import ASSET_TO_COINGECKO
    from services.http_client import get_client

    symbol_to_id = {}
    for sym in symbols:
        cg_id = ASSET_TO_COINGECKO.get(sym)
        if cg_id:
            symbol_to_id[sym] = cg_id

    if not symbol_to_id:
        return {}

    try:
        client = get_client("coingecko", timeout=30.0)
        params = {
            "vs_currency": "usd",
            "ids": ",".join(set(symbol_to_id.values())),
            "sparkline": "true" if max_points > 0 else "false",
            "per_page": 250,
            "page": 1
        }
        response = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params=params
        )
        if response.status_code != 200:
            return {}

        sparklines = {}
        for coin in response.json():
            raw = coin.get('sparkline_in_7d', {}).get('price', [])
            # Use small (120px) image instead of large (250px) — much faster on watchOS
            cg_image_url = (coin.get('image', '') or '').replace('/large/', '/small/')
            if not raw:
                # Still capture the image URL even without sparkline data
                for sym, cg_id in symbol_to_id.items():
                    if cg_id == coin['id']:
                        sparklines[sym] = {
                            'sparkline_7d': [],
                            'sparkline_24h': [],
                            'cg_image_url': cg_image_url,
                        }
                continue
            # Downsample full range to max_points for 7D
            step = max(1, len(raw) // max_points)
            sampled_7d = raw[::step]
            # Last 24 hourly points for 24H chart (CoinGecko returns ~168 hourly points)
            sampled_24h = raw[-24:] if len(raw) >= 24 else raw
            for sym, cg_id in symbol_to_id.items():
                if cg_id == coin['id']:
                    sparklines[sym] = {
                        'sparkline_7d': [round(v, 2) for v in sampled_7d],
                        'sparkline_24h': [round(v, 2) for v in sampled_24h],
                        'cg_image_url': cg_image_url,
                    }
        return sparklines
    except Exception as e:
        logger.debug(f"Failed to fetch asset sparklines: {e}")
        return {}


def _map_mobile_range_to_portfolio_range(range_value: str) -> str:
    range_map = {"24h": "24h", "7d": "1w", "4w": "1m", "3m": "3m", "1y": "1y", "all": "all"}
    return range_map.get(range_value, "1w")


def _compute_chart_coverage(data: list) -> dict:
    """Compute coverage stats from chart data points."""
    if not data:
        return {"oldest_date": None, "newest_date": None, "total_days": 0}
    dates = [p['date'] for p in data]
    return {"oldest_date": min(dates), "newest_date": max(dates), "total_days": len(dates)}


def _compute_value_summary(values: List[float]) -> Dict[str, float]:
    if not values:
        return {
            "starting_value": 0,
            "ending_value": 0,
            "change_usd": 0,
            "change_percent": 0,
            "highest_value": 0,
            "lowest_value": 0,
        }
    starting_value = values[0]
    ending_value = values[-1]
    change_usd = ending_value - starting_value
    change_percent = (change_usd / starting_value * 100) if starting_value > 0 else 0
    return {
        "starting_value": round(starting_value, 2),
        "ending_value": round(ending_value, 2),
        "change_usd": round(change_usd, 2),
        "change_percent": round(change_percent, 2),
        "highest_value": round(max(values), 2),
        "lowest_value": round(min(values), 2),
    }


def _source_icon_url(source: Dict) -> str:
    source_type = (source.get("source_type") or "").lower()
    if source_type == "exchange":
        exchange_info = EXCHANGE_INFO.get((source.get("source_key") or "").lower(), {})
        return exchange_info.get("logo_url", "")
    if source_type == "on_chain":
        chain = (source.get("chain") or "").lower()
        return CHAIN_ICON_URLS.get(chain, "")
    if source_type == "staking":
        return "https://img.icons8.com/fluency/96/lock-2.png"
    if source_type == "defi":
        return "https://img.icons8.com/fluency/96/combo-chart.png"
    if source_type == "nft":
        return "https://img.icons8.com/fluency/96/picture.png"
    return ""


def _group_sources_for_mobile(sources: List[Dict]) -> List[Dict]:
    grouped = {source_type: [] for source_type in SOURCE_TYPE_ORDER}
    for source in sources:
        source_type = source.get("source_type")
        if source_type not in grouped:
            continue
        grouped[source_type].append(source)

    result = []
    for source_type in SOURCE_TYPE_ORDER:
        items = grouped[source_type]
        items.sort(key=lambda item: item.get("latest_value_usd", 0), reverse=True)
        result.append({
            "source_type": source_type,
            "display_name": SOURCE_GROUP_DISPLAY[source_type],
            "count": len(items),
            "sources": items,
        })
    return result


async def _get_latest_source_values(user_id: int) -> Dict[int, Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                ws.id AS source_id,
                COALESCE(latest.value_usd, 0) AS latest_value_usd,
                latest.date AS latest_date
            FROM wallet_sources ws
            LEFT JOIN (
                SELECT wdb.source_id, wdb.value_usd, wdb.date
                FROM wallet_daily_balances wdb
                JOIN (
                    SELECT source_id, MAX(date) AS max_date
                    FROM wallet_daily_balances
                    WHERE user_id = ?
                    GROUP BY source_id
                ) m
                    ON wdb.source_id = m.source_id
                   AND wdb.date = m.max_date
                WHERE wdb.user_id = ?
            ) latest
                ON latest.source_id = ws.id
            WHERE ws.user_id = ? AND ws.is_active = 1
            """,
            (user_id, user_id, user_id),
        )
        rows = await cursor.fetchall()
        return {
            row["source_id"]: {
                "latest_value_usd": float(row["latest_value_usd"] or 0),
                "latest_date": row["latest_date"],
            }
            for row in rows
        }


def _build_demo_wallet_sources() -> List[Dict]:
    return [
        {
            "id": 101,
            "source_type": "on_chain",
            "source_key": "addr1q9x...demo",
            "chain": "cardano",
            "label": "Main Cardano Wallet",
            "wallet_id": 1,
            "is_active": 1,
            "latest_value_usd": 18124.56,
            "latest_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "icon_url": CHAIN_ICON_URLS["cardano"],
        },
        {
            "id": 201,
            "source_type": "exchange",
            "source_key": "coinbase",
            "chain": None,
            "label": "Coinbase",
            "wallet_id": None,
            "is_active": 1,
            "latest_value_usd": 6921.44,
            "latest_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "icon_url": EXCHANGE_INFO["coinbase"]["logo_url"],
        },
        {
            "id": 301,
            "source_type": "staking",
            "source_key": "staking:addr1q9x...demo",
            "chain": "cardano",
            "label": "Cardano Staking",
            "wallet_id": None,
            "is_active": 1,
            "latest_value_usd": 2482.11,
            "latest_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "icon_url": "https://img.icons8.com/fluency/96/lock-2.png",
        },
        {
            "id": 401,
            "source_type": "defi",
            "source_key": "defi:addr1q9x...demo",
            "chain": "cardano",
            "label": "DeFi Positions",
            "wallet_id": None,
            "is_active": 1,
            "latest_value_usd": 1142.38,
            "latest_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "icon_url": "https://img.icons8.com/fluency/96/combo-chart.png",
        },
        {
            "id": 501,
            "source_type": "nft",
            "source_key": "nft:all",
            "chain": None,
            "label": "NFT Portfolio",
            "wallet_id": None,
            "is_active": 1,
            "latest_value_usd": 612.77,
            "latest_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "icon_url": "https://img.icons8.com/fluency/96/picture.png",
        },
    ]


@router.get("/portfolio/instant")
async def get_mobile_portfolio_instant(user_id: int = Depends(verify_session)):
    """
    Instant portfolio total for mobile — reads from portfolio_positions table.

    Returns total + breakdown + top holdings with no API calls.
    Mobile app can call this for immediate display, then call
    /mobile/portfolio/summary for full details.
    """
    from routers.portfolio import get_portfolio_instant
    return await get_portfolio_instant(user_id=user_id)


def _summary_cache_key(user_id: int, include_sparklines: bool) -> str:
    """Cache key for /portfolio/summary, partitioned by response variant (SEC-A1).

    include_sparklines changes the payload shape, so each variant must get its
    own cache row — otherwise a background SWR recompute triggered by one
    variant would overwrite the other within the TTL. Every key construction
    (fresh hit, stale/SWR lookup, refresh-task dedupe, cache write) must go
    through this helper.
    """
    variant = "sparklines" if include_sparklines else "nosparklines"
    return f"mobile_portfolio_summary_{user_id}_{variant}"


# In-flight background summary recomputes, keyed by cache key (SWR stampede guard)
_summary_refresh_tasks: Dict[str, asyncio.Task] = {}


def _schedule_summary_refresh(cache_key: str, user_id: int, include_sparklines: bool):
    """Kick off a background recompute of the portfolio summary (server-side SWR).

    At most one recompute per cache key runs at a time; concurrent stale
    hits piggyback on the in-flight task instead of stampeding upstream APIs.
    """
    if cache_key in _summary_refresh_tasks:
        return

    async def _refresh_job():
        try:
            await _compute_mobile_portfolio_summary(
                user_id, refresh=False, include_sparklines=include_sparklines)
        except Exception as e:
            logger.warning(f"Background summary refresh failed for user {user_id}: {e}")
        finally:
            _summary_refresh_tasks.pop(cache_key, None)

    _summary_refresh_tasks[cache_key] = asyncio.create_task(_refresh_job())


@router.get("/portfolio/summary")
async def get_mobile_portfolio_summary(
    user_id: int = Depends(verify_session),
    refresh: bool = Query(False, description="Force refresh from blockchain APIs"),
    include_sparklines: bool = Query(True, description="Include sparkline data (disable for faster initial load)")
):
    """
    Get complete portfolio overview for mobile dashboard.

    Consolidates:
    - Self-custody wallets (all blockchains)
    - Exchange balances
    - NFT valuations
    - DeFi/staking positions

    Returns mobile-optimized format with percentages and totals.
    """
    cache_key = _summary_cache_key(user_id, include_sparklines)

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return cached
        # Stale-while-revalidate: on cache expiry serve the previous payload
        # immediately and recompute in the background. refresh=true and
        # first-ever requests (no cache row) still compute synchronously.
        stale, _ = await get_stale_cache(cache_key, user_id=user_id)
        if stale is not None:
            _schedule_summary_refresh(cache_key, user_id, include_sparklines)
            return stale

    return await _compute_mobile_portfolio_summary(user_id, refresh, include_sparklines)


async def _compute_mobile_portfolio_summary(user_id: int, refresh: bool, include_sparklines: bool):
    """Build the full summary payload and write it to the cache.

    Internal lookups are batched for latency, but values, ordering, and key
    order are unchanged — the payload must stay byte-identical for identical
    data (response shape is frozen).
    """
    cache_key = _summary_cache_key(user_id, include_sparklines)

    # Fetch all data in parallel (including snapshot for staking/defi/tracked tokens)
    portfolio_data, exchange_summary, nft_summary, defi_summary, snapshot_totals = await asyncio.gather(
        portfolio.get_portfolio_summary(user_id=user_id, refresh=refresh),
        exchanges.get_all_exchanges_summary(user_id=user_id),
        nfts.get_all_chains_nft_summary(user_id=user_id),
        defi.get_defi_summary(user_id=user_id),
        # refresh must propagate: the phone's hard pull has to recompute the
        # staking/DeFi buckets too, not serve the 5-minute totals row (D2)
        portfolio.get_portfolio_totals(user_id=user_id, refresh=refresh),
        return_exceptions=True
    )

    # Handle errors gracefully
    if isinstance(portfolio_data, Exception):
        logger.warning(f"Portfolio data fetch failed: {portfolio_data}")
        portfolio_data = {}
    if isinstance(exchange_summary, Exception):
        logger.warning(f"Exchange summary fetch failed: {exchange_summary}")
        exchange_summary = {"total_usd": 0}
    if isinstance(nft_summary, Exception):
        logger.warning(f"NFT summary fetch failed: {nft_summary}")
        nft_summary = {"total_value_usd": 0, "chains": {}}
    if isinstance(defi_summary, Exception):
        logger.warning(f"DeFi summary fetch failed: {defi_summary}")
        defi_summary = {"all_positions": []}
    if isinstance(snapshot_totals, Exception):
        logger.warning(f"Snapshot totals fetch failed: {snapshot_totals}")
        snapshot_totals = {"staking_usd": 0, "defi_usd": 0, "tracked_tokens_usd": 0}

    # Calculate self-custody value
    self_custody_value = 0.0
    native_totals = {}
    blockchain_summaries = []

    # Get prices for native coins
    all_prices = await pricing_service.get_all_tracked_prices()

    # All blockchains supported by portfolio summary (must match portfolio.py)
    symbol_map = {
        'cardano': ('ADA', 'total_ada'),
        'bitcoin': ('BTC', 'total_btc'),
        'ethereum': ('ETH', 'total_eth'),
        'solana': ('SOL', 'total_sol'),
        'polygon': ('MATIC', 'total_matic'),
        'base': ('ETH', 'total_eth'),
        'algorand': ('ALGO', 'total_algo'),
        'bsc': ('BNB', 'total_bnb'),
        'arbitrum': ('ETH', 'total_eth'),
        'avalanche': ('AVAX', 'total_avax'),
        'tron': ('TRX', 'total_trx'),
        'xrp': ('XRP', 'total_xrp'),
        'hedera': ('HBAR', 'total_hbar'),
        'multiversx': ('EGLD', 'total_egld'),
        'sui': ('SUI', 'total_sui'),
        'aptos': ('APT', 'total_apt'),
        'filecoin': ('FIL', 'total_fil'),
        'litecoin': ('LTC', 'total_ltc'),
        'dogecoin': ('DOGE', 'total_doge'),
        'zcash': ('ZEC', 'total_zec'),
        'tezos': ('XTZ', 'total_xtz'),
        'stacks': ('STX', 'total_stx'),
        'vechain': ('VET', 'total_vet'),
        'cosmos': ('ATOM', 'total_atom'),
        'near': ('NEAR', 'total_near'),
        'icp': ('ICP', 'total_icp'),
    }

    for blockchain in symbol_map:
        chain_data = portfolio_data.get(blockchain, {})
        if not chain_data or chain_data.get('wallet_count', 0) == 0:
            continue

        symbol, amount_key = symbol_map[blockchain]
        native_amount = chain_data.get(amount_key, 0)

        # Get price and calculate value
        price_data = all_prices.get(symbol, {})
        price_usd = price_data.get('usd', 0)
        native_coin_value = native_amount * price_usd
        native_tokens_value = chain_data.get('native_assets_value_usd', 0)

        # self_custody_value tracks native coin value only (tokens are in tracked_tokens)
        # Per-chain display includes both for full picture
        display_value = native_coin_value + native_tokens_value
        self_custody_value += native_coin_value

        if display_value > 0 or native_coin_value > 0:
            native_totals[symbol.lower()] = native_amount

            blockchain_summaries.append({
                "name": blockchain,
                "symbol": symbol,
                "value_usd": round(display_value, 2),
                "native_coin_value_usd": round(native_coin_value, 2),
                "native_tokens_value_usd": round(native_tokens_value, 2),
                "native_amount": round(native_amount, 8),
                "native_price_usd": round(price_usd, 2),
                "price_change_24h": round(price_data.get('usd_24h_change', 0) or 0, 2),
                "wallet_count": chain_data.get('wallet_count', 0),
                "percentage": 0,  # Calculated later
                "image_url": "",  # populated below from metadata_cache
            })

    # Batch-populate image_url from metadata_cache (fast SQLite, no CoinGecko calls);
    # one concurrent lookup per unique symbol instead of one await per chain
    unique_chain_syms = list(dict.fromkeys(bs['symbol'] for bs in blockchain_summaries))
    chain_metas = dict(zip(unique_chain_syms, await asyncio.gather(
        *[metadata_cache.get_metadata(s) for s in unique_chain_syms])))
    for bs in blockchain_summaries:
        sym = bs['symbol']
        meta = chain_metas.get(sym)
        bs['image_url'] = (meta.get('image_url') if meta else None) or logokit_service.get_crypto_logo_url(sym, size=64)

    # Get component values
    exchanges_value = exchange_summary.get('total_usd', 0)
    nfts_value = nft_summary.get('total_value_usd', 0)

    # Staking/DeFi/tracked tokens/custom tokens from live computation (matches web dashboard)
    staking_value = snapshot_totals.get('staking_usd', 0) or 0
    defi_value = snapshot_totals.get('defi_usd', 0) or 0
    tracked_tokens_value = snapshot_totals.get('tracked_tokens_usd', 0) or 0
    custom_tokens_value = snapshot_totals.get('custom_tokens_usd', 0) or 0

    # Calculate total (matches web: coins + tracked tokens + custom tokens + staking + defi + exchanges + NFTs)
    total_value_usd = (self_custody_value + tracked_tokens_value + custom_tokens_value +
                       exchanges_value + nfts_value + staking_value + defi_value)

    # Calculate percentages
    for blockchain_summary in blockchain_summaries:
        blockchain_summary['percentage'] = round(
            (blockchain_summary['value_usd'] / total_value_usd * 100) if total_value_usd > 0 else 0,
            1
        )

    # Sort by value descending
    blockchain_summaries.sort(key=lambda x: x['value_usd'], reverse=True)

    # Build top_holdings: aggregate by symbol (combine same-symbol across chains + staking)
    symbol_agg = {}
    for bs in blockchain_summaries:
        sym = bs['symbol']
        if sym in symbol_agg:
            symbol_agg[sym]['value_usd'] += bs['value_usd']
            symbol_agg[sym]['native_amount'] += bs['native_amount']
            symbol_agg[sym]['wallet_count'] += bs['wallet_count']
        else:
            symbol_agg[sym] = {
                "name": bs['name'],
                "symbol": sym,
                "value_usd": bs['value_usd'],
                "native_amount": bs['native_amount'],
                "native_price_usd": bs['native_price_usd'],
                "price_change_24h": bs['price_change_24h'],
                "wallet_count": bs['wallet_count'],
                "percentage": 0,
                "image_url": bs['image_url'],
            }

    # Merge native tokens (IAG, STRIKE, etc.) into top_holdings
    # Place BEFORE staking merge so staking amounts ADD to native amounts
    try:
        native_assets_data = await portfolio.get_all_native_assets(user_id=user_id)
        # Two passes so the per-token name/image resolutions run concurrently:
        # first apply the original skip rules (blank ticker, already counted,
        # first-occurrence-wins, zero value) to pick the tokens to add, then
        # resolve all of them in one gather and insert in the same order
        native_pending = []
        native_seen = set()
        for asset in native_assets_data.get('valuable_assets', []):
            ticker = (asset.get('ticker') or asset.get('asset_name', '')).upper()
            if not ticker or ticker in symbol_agg or ticker in native_seen:
                continue  # Already counted (L1 chain)
            price_data = all_prices.get(ticker, {})
            price_usd = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
            val = float(asset.get('value_usd', 0)) or (float(asset.get('total_quantity', 0)) * price_usd)
            if val <= 0:
                continue
            native_seen.add(ticker)
            native_pending.append((ticker, asset, price_data, price_usd, val))
        native_infos = await asyncio.gather(
            *[_resolve_token_info(t) for t, _, _, _, _ in native_pending])
        for (ticker, asset, price_data, price_usd, val), (token_name, token_image) in zip(native_pending, native_infos):
            symbol_agg[ticker] = {
                "name": token_name,
                "symbol": ticker,
                "value_usd": val,
                "native_amount": float(asset.get('total_quantity', 0)),
                "native_price_usd": round(price_usd, 2),
                "price_change_24h": round((price_data.get('usd_24h_change', 0) or 0) if isinstance(price_data, dict) else 0, 2),
                "wallet_count": asset.get('wallet_count', 0),
                "percentage": 0,
                "image_url": token_image,
            }
    except Exception as e:
        logger.debug(f"Could not merge native tokens for top holdings: {e}")

    # Merge staking positions into top_holdings (per-token breakdown).
    # iter_staking_token_values is the shared valuation for EVERY position
    # kind (staked arrays, Strike V2 balance/vaults, Indigo CDPs at NET
    # equity, stability pools, pending rewards) so this figure agrees with
    # the Staking tab. Unpriced entries add their amount but 0 USD.
    has_unpriced_staking = False
    try:
        from services.defi import iter_staking_token_values
        all_wallets = await get_all_wallets(user_id=user_id)
        cardano_addrs = [w['address'] for w in all_wallets if w['blockchain'] == 'cardano']
        if cardano_addrs:
            # Call staking endpoint (not just cache read) so data is fetched
            # when caches are empty — ensures staked tokens appear in top_holdings
            staking_caches = await asyncio.gather(*[
                defi.get_staking_positions(addr, refresh=False, user_id=user_id)
                for addr in cardano_addrs
            ], return_exceptions=True)

            # One valuation pass; entries carried so token-info pre-resolve
            # and the aggregation loop below see the identical set
            staking_entries = []
            for cached in staking_caches:
                if isinstance(cached, (Exception, BaseException)) or not cached or not isinstance(cached, dict) or not cached.get('protocols'):
                    continue
                for protocol_name, protocol_data in cached['protocols'].items():
                    staking_entries.extend(
                        iter_staking_token_values(protocol_data, all_prices)
                    )

            # Pre-resolve name/image for tokens this merge will introduce,
            # so the aggregation loop never awaits per row
            staking_new_tokens = []
            for entry in staking_entries:
                token = entry['token']
                if token not in symbol_agg and token not in staking_new_tokens:
                    staking_new_tokens.append(token)
            staking_infos = dict(zip(staking_new_tokens, await asyncio.gather(
                *[_resolve_token_info(t) for t in staking_new_tokens])))

            for entry in staking_entries:
                token = entry['token']
                amount = entry['amount']
                val = entry['usd']
                if not entry['priced']:
                    has_unpriced_staking = True
                price_data = all_prices.get(token, {})
                price_usd = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                # Entries whose USD is not amount x market (CDP net equity,
                # unpriced) would skew any implied per-token price derived
                # from value/amount — tag the token's value basis as mixed so
                # consumers keep using native_price_usd (market) instead
                value_consistent = (
                    price_usd > 0 and abs(val - amount * price_usd) < 1e-9
                )
                if token in symbol_agg:
                    symbol_agg[token]['value_usd'] += val
                    symbol_agg[token]['native_amount'] += amount
                    if not value_consistent:
                        symbol_agg[token]['value_basis'] = 'mixed'
                else:
                    token_name, token_image = staking_infos[token]
                    symbol_agg[token] = {
                        "name": token_name,
                        "symbol": token,
                        "value_usd": val,
                        "native_amount": amount,
                        "native_price_usd": round(price_usd, 2),
                        "price_change_24h": round((price_data.get('usd_24h_change', 0) or 0) if isinstance(price_data, dict) else 0, 2),
                        "wallet_count": 0,
                        "percentage": 0,
                        "image_url": token_image,
                    }
                    if not value_consistent:
                        symbol_agg[token]['value_basis'] = 'mixed'
    except Exception as e:
        logger.debug(f"Could not aggregate staking for top holdings: {e}")

    # Merge exchange assets into top_holdings (so exchange-staked SOL etc. appear in totals)
    try:
        exchange_names = ['coinbase', 'binance', 'binance_us', 'okx', 'bitget', 'gate', 'kucoin']
        exchange_caches = await asyncio.gather(*[
            get_cache(f"{name}_portfolio", user_id=user_id) for name in exchange_names
        ])
        # Same two-pass pattern as the staking merge: pre-resolve currencies
        # that will be newly added, then run the original loop without awaits
        exchange_new_currencies = []
        for exc_data in exchange_caches:
            if not exc_data or not exc_data.get('assets'):
                continue
            for asset in exc_data['assets']:
                currency = (asset.get('currency') or '').upper()
                if not currency or currency == 'USD':
                    continue
                if float(asset.get('balance', 0)) <= 0:
                    continue
                if currency not in symbol_agg and currency not in exchange_new_currencies:
                    exchange_new_currencies.append(currency)
        exchange_infos = dict(zip(exchange_new_currencies, await asyncio.gather(
            *[_resolve_token_info(c) for c in exchange_new_currencies])))
        for exc_data in exchange_caches:
            if not exc_data or not exc_data.get('assets'):
                continue
            for asset in exc_data['assets']:
                currency = (asset.get('currency') or '').upper()
                if not currency or currency == 'USD':
                    continue
                balance = float(asset.get('balance', 0))
                price = float(asset.get('price', 0))
                if balance <= 0:
                    continue
                val = balance * price
                if currency in symbol_agg:
                    symbol_agg[currency]['value_usd'] += val
                    symbol_agg[currency]['native_amount'] += balance
                else:
                    exc_name, exc_image = exchange_infos[currency]
                    symbol_agg[currency] = {
                        "name": exc_name,
                        "symbol": currency,
                        "value_usd": val,
                        "native_amount": balance,
                        "native_price_usd": round(price, 2),
                        "price_change_24h": 0,
                        "wallet_count": 0,
                        "percentage": 0,
                        "image_url": exc_image,
                    }
    except Exception as e:
        logger.debug(f"Could not aggregate exchange assets for top holdings: {e}")

    # Recompute staking value from now-populated caches.
    # The staking fetches above populate caches that get_portfolio_totals
    # couldn't see (it ran in parallel before caches existed).
    try:
        from services.offchain_helpers import get_staking_value
        live_staking = await get_staking_value(all_prices, user_id=user_id)
        if live_staking > staking_value:
            staking_value = live_staking
            total_value_usd = (self_custody_value + tracked_tokens_value + custom_tokens_value +
                               exchanges_value + nfts_value + staking_value + defi_value)
            # Recalculate blockchain percentages with updated total
            for bs in blockchain_summaries:
                bs['percentage'] = round(
                    (bs['value_usd'] / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
    except Exception as e:
        logger.debug(f"Could not recompute staking value: {e}")

    # Finalize top_holdings
    top_holdings = list(symbol_agg.values())
    for h in top_holdings:
        h['value_usd'] = round(h['value_usd'], 2)
        h['native_amount'] = round(h['native_amount'], 8)
        h['percentage'] = round((h['value_usd'] / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
    # Ensure every entry has an image_url via metadata_cache → logokit fallback
    # (one concurrent lookup per missing symbol; symbols are unique here)
    missing_image_syms = [h['symbol'] for h in top_holdings if not h.get('image_url')]
    if missing_image_syms:
        fallback_metas = dict(zip(missing_image_syms, await asyncio.gather(
            *[metadata_cache.get_metadata(s) for s in missing_image_syms])))
        for h in top_holdings:
            if not h.get('image_url'):
                meta = fallback_metas.get(h['symbol'])
                h['image_url'] = (meta.get('image_url') if meta else None) or logokit_service.get_crypto_logo_url(h['symbol'], size=64)
    top_holdings.sort(key=lambda x: x['value_usd'], reverse=True)

    # Fetch 7-day sparkline data + CoinGecko images for top holdings (for watchOS)
    # Sparklines for top 8 (heavy data), images for all (lightweight)
    # Skipped when include_sparklines=false for faster initial mobile load
    if include_sparklines:
        all_symbols = [h['symbol'] for h in top_holdings]
        top_symbols = all_symbols[:8]
        remaining_symbols = all_symbols[8:]
        try:
            # Fetch sparklines + images for top 8 (single CoinGecko call)
            sparklines = await _fetch_asset_sparklines(top_symbols)
            for h in top_holdings[:8]:
                asset_data = sparklines.get(h['symbol'], {})
                h['sparkline_7d'] = asset_data.get('sparkline_7d', [])
                h['sparkline_24h'] = asset_data.get('sparkline_24h', [])
                cg_url = asset_data.get('cg_image_url', '')
                if cg_url:
                    h['watch_image_url'] = cg_url

            # Fetch images for remaining holdings (no sparkline needed)
            if remaining_symbols:
                extra_images = await _fetch_asset_sparklines(remaining_symbols, max_points=0)
                for h in top_holdings[8:]:
                    asset_data = extra_images.get(h['symbol'], {})
                    cg_url = asset_data.get('cg_image_url', '')
                    if cg_url:
                        h['watch_image_url'] = cg_url
        except Exception as e:
            logger.debug(f"Could not fetch sparklines for top holdings: {e}")

    result = {
        "total_value_usd": round(total_value_usd, 2),
        "total_native": native_totals,
        "breakdown": {
            "self_custody": {
                "value_usd": round(self_custody_value, 2),
                "percentage": round((self_custody_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            },
            "exchanges": {
                "value_usd": round(exchanges_value, 2),
                "percentage": round((exchanges_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            },
            "nfts": {
                "value_usd": round(nfts_value, 2),
                "percentage": round((nfts_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            },
            "staking": {
                "value_usd": round(staking_value, 2),
                "percentage": round((staking_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            },
            "defi": {
                "value_usd": round(defi_value, 2),
                "percentage": round((defi_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            },
            "tracked_tokens": {
                "value_usd": round(tracked_tokens_value, 2),
                "percentage": round((tracked_tokens_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            },
            "custom_tokens": {
                "value_usd": round(custom_tokens_value, 2),
                "percentage": round((custom_tokens_value / total_value_usd * 100) if total_value_usd > 0 else 0, 1)
            }
        },
        "blockchains": blockchain_summaries,
        "top_holdings": top_holdings[:8],
        # True when some staking position's value could not be computed from
        # a real price — its amount is counted, its USD contribution is 0
        "has_unpriced": has_unpriced_staking,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False
    }

    await set_cache(cache_key, result, MOBILE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/wallets")
async def get_mobile_wallets(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = Query(None, description="Filter by blockchain"),
    include_balances: bool = Query(True, description="Include current balances"),
    refresh: bool = Query(False, description="Force refresh balances from blockchain APIs")
):
    """
    Get simplified wallet list for mobile.

    Returns wallets with basic info and balance summaries.
    Does not include full token/NFT lists (use wallet detail endpoint for that).
    """
    # Demo mode: return fake wallets from demo_wallet_service
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        from services.demo_wallet_service import demo_wallet_service
        demo_wallets = await demo_wallet_service.get_all_wallets()
        mobile_wallets = []
        total_value = 0.0
        for w in demo_wallets:
            bc = w['blockchain']
            if blockchain and bc != blockchain:
                continue
            tokens = await demo_wallet_service.get_wallet_tokens(w['address'], bc)
            usd_val = w.get('balance_usd', 0)
            total_value += usd_val
            wallet_data = {
                "id": w['id'],
                "blockchain": bc,
                "address": w['address'],
                "label": w.get('label'),
                "created_at": w.get('created_at'),
            }
            if include_balances:
                wallet_data['balance'] = {
                    "native": round(float(w.get('balance', 0)), 8),
                    "native_symbol": demo_wallet_service._get_native_unit(bc),
                    "usd_value": round(usd_val, 2),
                    "last_updated": datetime.utcnow().isoformat() + "Z",
                }
                wallet_data['token_count'] = len(tokens)
                wallet_data['nft_count'] = 0
            mobile_wallets.append(wallet_data)
        return {
            "total_wallets": len(mobile_wallets),
            "wallets": mobile_wallets,
            "total_value_usd": round(total_value, 2),
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    # Cache per user + query params; refresh=True bypasses the read but
    # still repopulates the cache below so subsequent reads get fresh data
    cache_key = f"mobile_wallets_{user_id}_{blockchain or 'all'}_{include_balances}"
    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return cached

    all_wallets = await get_all_wallets(user_id=user_id)

    # When refresh=True, re-fetch balances from blockchain APIs before reading
    if refresh and all_wallets:
        from routers.wallets import _refresh_wallet_balance
        semaphore = asyncio.Semaphore(5)

        async def _refresh_limited(w):
            async with semaphore:
                try:
                    return await _refresh_wallet_balance(w)
                except Exception as e:
                    logger.warning(f"Wallet refresh failed for {w['address'][:20]}: {e}")
                    return {'success': False}

        # Filter to requested blockchain if specified
        to_refresh = [w for w in all_wallets if not blockchain or w['blockchain'] == blockchain]
        await asyncio.gather(*[_refresh_limited(w) for w in to_refresh], return_exceptions=True)

    # Get prices for value calculations
    all_prices = await pricing_service.get_all_tracked_prices()

    filtered_wallets = [
        w for w in all_wallets
        if not blockchain or w['blockchain'] == blockchain
    ]

    # Batch the per-wallet DB lookups (was a sequential N+1: two awaited
    # queries per wallet); two grouped queries run concurrently instead
    balances_by_id = {}
    asset_counts_by_id = {}
    if include_balances and filtered_wallets:
        wallet_ids = [w['id'] for w in filtered_wallets]
        balances_by_id, asset_counts_by_id = await asyncio.gather(
            get_wallet_balances_bulk(wallet_ids),
            get_wallet_asset_counts_bulk(wallet_ids),
        )

    mobile_wallets = []
    total_value_usd = 0.0

    for wallet in filtered_wallets:
        wallet_data = {
            "id": wallet['id'],
            "blockchain": wallet['blockchain'],
            "address": wallet['address'],
            "label": wallet.get('label'),
            "created_at": wallet.get('created_at')
        }

        if include_balances:
            balance_info = balances_by_id.get(wallet['id'])

            # Get native balance
            native_balance = float(balance_info.get('amount', 0)) if balance_info else 0

            config = _WALLET_NATIVE_CONFIG.get(wallet['blockchain'], {'symbol': 'UNKNOWN', 'decimals': 0})
            symbol = config['symbol']

            # Get price
            price_data = all_prices.get(symbol, {})
            price_usd = price_data.get('usd', 0)

            # Calculate USD value
            usd_value = native_balance * price_usd

            wallet_data['balance'] = {
                "native": round(native_balance, 8),
                "native_symbol": symbol,
                "usd_value": round(usd_value, 2),
                "last_updated": datetime.utcnow().isoformat() + "Z"
            }
            wallet_data['token_count'] = asset_counts_by_id.get(wallet['id'], 0)
            wallet_data['nft_count'] = 0  # TODO: Add NFT count when needed

            total_value_usd += usd_value

        mobile_wallets.append(wallet_data)

    result = {
        "total_wallets": len(mobile_wallets),
        "wallets": mobile_wallets,
        "total_value_usd": round(total_value_usd, 2),
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }

    await set_cache(cache_key, result, MOBILE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/wallets/{wallet_id}")
async def get_mobile_wallet_detail(
    wallet_id: int,
    user_id: int = Depends(verify_session)
):
    """
    Get detailed wallet information including tokens and NFTs.

    Mobile-optimized format with all data needed for wallet detail view.
    """
    # Demo mode: return fake wallet detail
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        from services.demo_wallet_service import demo_wallet_service
        demo_wallets = await demo_wallet_service.get_all_wallets()
        wallet = next((w for w in demo_wallets if w['id'] == wallet_id), None)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        bc = wallet['blockchain']
        tokens_raw = await demo_wallet_service.get_wallet_tokens(wallet['address'], bc)
        tokens = []
        for t in tokens_raw:
            if t.get('value_usd', 0) > 0:
                tokens.append({
                    "symbol": t.get('ticker', 'UNKNOWN')[:10],
                    "name": t.get('name', 'Unknown'),
                    "quantity": round(float(t.get('quantity', 0)), 6),
                    "price_usd": round(t.get('price_usd', 0), 6),
                    "value_usd": round(t.get('value_usd', 0), 2),
                    "logo_url": t.get('logo', ''),
                })
        return {
            "id": wallet_id,
            "blockchain": bc,
            "address": wallet['address'],
            "label": wallet.get('label'),
            "balance": {
                "native": round(float(wallet.get('balance', 0)), 8),
                "native_symbol": demo_wallet_service._get_native_unit(bc),
                "usd_value": round(wallet.get('balance_usd', 0), 2),
            },
            "tokens": tokens,
            "nfts": [],
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    # Get wallet assets (includes pricing info)
    assets_data = await wallets.get_wallet_assets_by_id(wallet_id, user_id=user_id)

    # Get wallet info
    all_wallets = await get_all_wallets(user_id=user_id)
    wallet = next((w for w in all_wallets if w['id'] == wallet_id), None)

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    balance_info = await get_wallet_balance(wallet_id)
    native_balance = float(balance_info.get('amount', 0)) if balance_info else 0

    # Get price for native coin
    blockchain_symbols = {
        'cardano': 'ADA',
        'bitcoin': 'BTC',
        'ethereum': 'ETH',
        'solana': 'SOL',
        'polygon': 'POL',
        'base': 'ETH',
        'algorand': 'ALGO',
        'bsc': 'BNB',
        'arbitrum': 'ETH',
        'avalanche': 'AVAX',
        'tron': 'TRX',
        'xrp': 'XRP',
        'hedera': 'HBAR',
        'multiversx': 'EGLD',
        'sui': 'SUI',
        'aptos': 'APT',
        'filecoin': 'FIL',
        'litecoin': 'LTC',
        'dogecoin': 'DOGE',
        'zcash': 'ZEC',
        'tezos': 'XTZ',
        'stacks': 'STX',
        'vechain': 'VET',
        'cosmos': 'ATOM',
        'near': 'NEAR',
        'icp': 'ICP',
    }

    symbol = blockchain_symbols.get(wallet['blockchain'], 'UNKNOWN')
    all_prices = await pricing_service.get_all_tracked_prices()
    price_data = all_prices.get(symbol, {})
    price_usd = price_data.get('usd', 0)

    # Format tokens
    tokens = []
    for asset in assets_data.get('assets', []):
        if asset.get('total_value_usd', 0) > 0:
            tokens.append({
                "symbol": asset.get('ticker', asset.get('asset_name', 'Unknown'))[:10],
                "name": asset.get('token_name', asset.get('asset_name', 'Unknown')),
                "quantity": round(asset.get('actual_quantity', 0), 6),
                "price_native": round(asset.get('price_native', 0), 8) if asset.get('price_native') else None,
                "price_usd": round(asset.get('price_usd', 0), 6) if asset.get('price_usd') else None,
                "value_usd": round(asset.get('total_value_usd', 0), 2),
                "logo_url": logokit_service.get_crypto_logo_url(asset.get('ticker', 'UNKNOWN'), size=32)
            })

    return {
        "id": wallet_id,
        "blockchain": wallet['blockchain'],
        "address": wallet['address'],
        "label": wallet.get('label'),
        "balance": {
            "native": round(native_balance, 8),
            "native_symbol": symbol,
            "usd_value": round(native_balance * price_usd, 2)
        },
        "tokens": tokens,
        "nfts": [],  # TODO: Add NFT list when needed
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/exchanges/summary")
async def get_mobile_exchanges_summary(
    user_id: int = Depends(verify_session),
    refresh: bool = Query(False, description="Force refresh from exchange APIs")
):
    """
    Get exchange summary with mobile-friendly format.

    Adds display names, logos, and last sync timestamps.
    """
    summary = await exchanges.get_all_exchanges_summary(user_id=user_id)

    mobile_exchanges = []

    for exchange in summary.get('exchanges', []):
        exchange_name = exchange.get('name', '').lower().replace('.', '_').replace(' ', '_')

        # Get display info
        info = EXCHANGE_INFO.get(exchange_name, {
            "display_name": exchange.get('name', 'Unknown'),
            "logo_url": ""
        })

        mobile_exchanges.append({
            "name": exchange_name,
            "display_name": info['display_name'],
            "configured": exchange.get('status') == 'connected',
            "value_usd": round(exchange.get('total_usd', 0), 2),
            "asset_count": exchange.get('asset_count', 0),
            "logo_url": info['logo_url'],
            "last_sync": datetime.utcnow().isoformat() + "Z"
        })

    return {
        "total_exchanges": len(mobile_exchanges),
        "total_value_usd": round(summary.get('total_usd', 0), 2),
        "exchanges": mobile_exchanges,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False
    }


@router.get("/exchanges/{exchange_name}")
async def get_mobile_exchange_detail(
    exchange_name: str,
    user_id: int = Depends(verify_session),
    refresh: bool = Query(False, description="Force refresh from exchange API")
):
    """
    Get detailed holdings for a specific exchange.

    Mobile-optimized wrapper for existing exchange endpoints.
    """
    # Map exchange name to endpoint
    exchange_map = {
        'coinbase': exchanges.get_coinbase_portfolio,
        'binance': exchanges.get_binance_portfolio,
        'binance_us': exchanges.get_binance_us_portfolio,
        'okx': exchanges.get_okx_portfolio,
        'bitget': exchanges.get_bitget_portfolio,
        'gate': exchanges.get_gate_portfolio,
        'kucoin': exchanges.get_kucoin_portfolio,
    }

    get_func = exchange_map.get(exchange_name)
    if not get_func:
        raise HTTPException(status_code=404, detail=f"Exchange '{exchange_name}' not supported")

    try:
        data = await get_func(user_id=user_id, refresh=refresh)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch {exchange_name} data: {str(e)}")

    # Get display info
    info = EXCHANGE_INFO.get(exchange_name, {
        "display_name": exchange_name.title(),
        "logo_url": ""
    })

    # Format assets
    mobile_assets = []
    for asset in data.get('assets', []):
        mobile_assets.append({
            "symbol": asset.get('currency', 'Unknown'),
            "name": asset.get('currency', 'Unknown'),
            "balance": round(asset.get('balance', 0), 8),
            "usd_value": round(asset.get('usd_value', 0), 2),
            "usd_price": round(asset.get('price', 0), 6),
            "change_24h": 0,  # Not available from exchanges
            "logo_url": logokit_service.get_crypto_logo_url(asset.get('currency', 'UNKNOWN'), size=32)
        })

    return {
        "exchange": exchange_name,
        "display_name": info['display_name'],
        "configured": data.get('configured', False),
        "total_usd": round(data.get('total_usd', 0), 2),
        "asset_count": len(mobile_assets),
        "assets": mobile_assets,
        "last_sync": datetime.utcnow().isoformat() + "Z",
        "from_cache": data.get('from_cache', False),
        "cache_age_seconds": 0  # TODO: Calculate from cache timestamp
    }


async def _map_staking_protocol_positions(
    protocol_name: str,
    protocol_data: dict,
    all_prices: dict,
    ada_price: float,
) -> tuple[list, float, float, bool]:
    """Map one protocol's cached staking entry to mobile position dicts.

    Renders every position kind the aggregator produces — the `staked` token
    arrays plus Strike V2 trading balance / vault deposits and Indigo CDPs /
    stability-pool deposits. All amount/USD/priced math comes from
    services.defi.iter_staking_token_values, the single valuation used by
    every screen, so totals agree by construction; this function only adds
    display fields. Unpriced positions keep their amount visible but carry
    priced=false and contribute 0 to USD totals; CDP USD is NET equity
    (collateral minus minted debt), with the gross figures in the detail
    fields.

    Returns (positions, staked_usd_total, rewards_usd_total, has_unpriced).
    """
    from services.defi import iter_staking_token_values

    positions = []
    staked_usd_total = 0.0
    rewards_usd_total = 0.0
    has_unpriced = False

    logo_cache: dict = {}

    async def _logo(symbol: str) -> str:
        if symbol not in logo_cache:
            _, logo_cache[symbol] = await _resolve_token_info(symbol)
        return logo_cache[symbol]

    for entry in iter_staking_token_values(protocol_data, all_prices):
        kind = entry['kind']
        if kind == 'reward':
            rewards_usd_total += entry['usd']
            continue

        raw = entry.get('raw') or {}
        if not entry['priced']:
            has_unpriced = True
        staked_usd_total += entry['usd']

        position = {
            "blockchain": "cardano",
            "protocol": protocol_name,
            "staked_amount": round(entry['amount'], 6),
            "staked_symbol": entry['token'],
            "staked_usd": round(entry['usd'], 2),
            "rewards_amount": 0,
            "rewards_usd": 0,
            "apy": 0,
            "active": True,
            "logo_url": await _logo(entry['token']),
        }
        if not entry['priced']:
            position["priced"] = False

        if kind == 'trading_balance':
            position["position_kind"] = "trading_balance"
            position["pool_name"] = f"{protocol_name} V2 Trading Account"
        elif kind == 'vault':
            position.update({
                "position_kind": "vault",
                "pool_name": raw.get('vault_name') or f"{protocol_name} Vault",
                "vault_id": raw.get('vault_id', ''),
                "shares": _as_float(raw.get('shares', 0)),
                "share_price": _as_float(raw.get('share_price', 0)),
                # False when the vaults lookup couldn't supply a real share
                # price and value_ada fell back to share_price=1 — the value
                # is a floor, not a market valuation
                "priced": entry['priced'],
                "share_price_source": raw.get('share_price_source', 'vaults_api'),
            })
        elif kind == 'cdp':
            asset = raw.get('asset', 'iUSD')
            position.update({
                "position_kind": "cdp",
                "pool_name": f"{protocol_name} CDP ({asset})",
                # Gross breakdown; staked_usd above is NET equity
                "minted_asset": asset,
                "minted_amount": _as_float(raw.get('minted_amount', 0)),
                "collateral_ada": _as_float(raw.get('collateral_ada', 0)),
            })
        elif kind == 'stability_pool':
            asset = raw.get('asset', 'iUSD')
            position.update({
                "position_kind": "stability_pool",
                "pool_name": f"{protocol_name} Stability Pool ({asset})",
                "staked_symbol": asset,
            })
            position["logo_url"] = await _logo(asset)

        positions.append(position)

    return positions, staked_usd_total, rewards_usd_total, has_unpriced


@router.get("/defi/staking")
async def get_mobile_defi_staking(refresh: bool = Query(False), user_id: int = Depends(verify_session)):
    """
    Get consolidated staking positions and rewards.

    Includes Cardano staking and DeFi protocol positions.
    """
    # Get Cardano wallets for staking info
    all_wallets = await get_all_wallets(user_id=user_id)
    cardano_wallets = [w for w in all_wallets if w['blockchain'] == 'cardano']

    positions = []
    total_staked_usd = 0.0
    total_rewards_usd = 0.0
    has_unpriced = False
    refreshing = False
    data_as_of = None

    # Get prices
    all_prices = await pricing_service.get_all_tracked_prices()
    ada_price = all_prices.get('ADA', {}).get('usd', 0)

    # Add Cardano native-delegation positions.
    # P3-FIX3 (deploy-6 repro): this section used to make ~2 SEQUENTIAL
    # Blockfrost calls per wallet on EVERY read; each call individually
    # queued behind in-flight scan traffic in the shared pacing bucket, so
    # plain reads took 4.4s healthy and 60s+ during rescans. Now: stake
    # addresses are derived LOCALLY (bech32, zero API calls; API only as a
    # per-wallet fallback), account info is fetched in PARALLEL, and the
    # result is cached (10 min TTL) so steady-state reads are DB-only.
    from services.cardano import _derive_stake_key_local

    async def _stake_address_cached(wallet):
        """address -> stake address: local bech32 derivation (free), else a
        long-TTL cached API lookup. The mapping is immutable, so negative
        results are cached too — a malformed wallet row must not cost a
        paced Blockfrost call on every read."""
        address = wallet['address']
        try:
            local = _derive_stake_key_local(address)
        except Exception:
            local = None
        if local:
            return local
        cache_key = f"stake_address_{address}"
        row = await get_cache(cache_key)
        if row is not None:
            return row.get('stake_address') or None
        try:
            resolved = await cardano_service.get_stake_address(address)
        except Exception as e:
            logger.warning(f"Could not get stake address for wallet {wallet['id']}: {e}")
            return None
        await set_cache(cache_key, {'stake_address': resolved or ''}, 86400)
        return resolved

    resolved_stakes = await asyncio.gather(
        *[_stake_address_cached(w) for w in cardano_wallets],
        return_exceptions=True,
    )
    stake_addresses = []
    seen_stake_addresses = set()
    for stake_address in resolved_stakes:
        if isinstance(stake_address, (Exception, BaseException)) or not stake_address:
            continue
        if stake_address not in seen_stake_addresses:
            seen_stake_addresses.add(stake_address)
            stake_addresses.append(stake_address)

    async def _account_info_cached(stake_address: str):
        cache_key = f"stake_account_info_{stake_address}"
        cached_info = await get_cache(cache_key)
        if cached_info:
            return stake_address, cached_info
        info = await cardano_service.get_stake_account_info(stake_address)
        if info:
            info = {k: v for k, v in info.items() if k != '_raw'}
            await set_cache(cache_key, info, STAKE_ACCOUNT_INFO_TTL_S)
        return stake_address, info

    account_infos = await asyncio.gather(
        *[_account_info_cached(s) for s in stake_addresses],
        return_exceptions=True,
    )

    for entry in account_infos:
        if isinstance(entry, (Exception, BaseException)):
            logger.warning(f"Could not get staking info: {entry}")
            continue
        stake_address, account_info = entry
        try:
            delegated_ada = _as_float(account_info.get('controlled_ada', 0)) if account_info else 0.0
            if account_info and delegated_ada > 0:
                delegated_usd = delegated_ada * ada_price
                rewards_ada = _as_float(account_info.get('withdrawable_ada', 0))
                rewards_usd = rewards_ada * ada_price

                total_staked_usd += delegated_usd
                total_rewards_usd += rewards_usd

                positions.append({
                    "blockchain": "cardano",
                    "stake_key": stake_address,
                    "pool_id": account_info.get('pool_id', 'Unknown'),
                    "pool_name": account_info.get('pool_name', 'Unknown'),
                    "pool_ticker": account_info.get('pool_ticker', ''),
                    "delegated_amount": round(delegated_ada, 2),
                    "delegated_usd": round(delegated_usd, 2),
                    "rewards_lifetime": round(rewards_ada, 2),
                    "rewards_usd": round(rewards_usd, 2),
                    "apy": 4.5,  # Approximate Cardano APY
                    "active": True,
                    "logo_url": logokit_service.get_crypto_logo_url("ADA", size=32)
                })
        except Exception as e:
            logger.warning(f"Could not get staking info for {stake_address[:20]}: {e}")

    # Get actual staking positions (tokens locked in smart contracts)
    # Use defi.get_staking_positions() which reads cache if warm, fetches from
    # Blockfrost if cold — ensures Strike/Indigo/etc appear without dashboard refresh
    if cardano_wallets:
        staking_caches = await asyncio.gather(*[
            defi.get_staking_positions(wallet['address'], refresh=refresh, user_id=user_id)
            for wallet in cardano_wallets
        ], return_exceptions=True)

        for cached in staking_caches:
            try:
                if isinstance(cached, (Exception, BaseException)) or not cached or not isinstance(cached, dict):
                    continue
                if cached.get('refreshing'):
                    refreshing = True
                wallet_as_of = cached.get('cached_at') or cached.get('data_as_of')
                if wallet_as_of and (data_as_of is None or wallet_as_of < data_as_of):
                    data_as_of = wallet_as_of  # oldest wallet's data age
                if not cached.get('protocols'):
                    continue
                for protocol_name, protocol_data in cached['protocols'].items():
                    proto_positions, staked_usd, rewards_usd, proto_unpriced = (
                        await _map_staking_protocol_positions(
                            protocol_name, protocol_data, all_prices, ada_price
                        )
                    )
                    positions.extend(proto_positions)
                    total_staked_usd += staked_usd
                    total_rewards_usd += rewards_usd
                    has_unpriced = has_unpriced or proto_unpriced
            except Exception as e:
                logger.warning(f"Could not process staking positions: {e}")

    return {
        "total_staked_usd": round(total_staked_usd, 2),
        "total_rewards_usd": round(total_rewards_usd, 2),
        "positions": positions,
        # True when some position's USD value could not be computed from a
        # real price — its amount is shown but it contributes 0 to totals
        "has_unpriced": has_unpriced,
        # Async refresh contract: hard pulls answer promptly with current
        # best data; refreshing=true means a background rescan is running
        # and the app's revalidation picks up the fresh result on its own
        "refreshing": refreshing,
        "data_as_of": data_as_of,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/nfts/summary")
async def get_mobile_nfts_summary(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = Query(None, description="Filter by blockchain")
):
    """
    Get NFT collection summary for mobile.

    Mobile-optimized wrapper with totals and collection grouping.
    """
    try:
        summary = await nfts.get_nft_summary(user_id=user_id)
    except Exception as e:
        logger.warning(f"Mobile NFT summary failed: {e}")
        return {
            "total_nfts": 0,
            "total_collections": 0,
            "total_floor_value_usd": 0,
            "collections": [],
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "error": str(e)
        }

    # Filter by blockchain if specified
    collections = summary.get('collections', [])
    if blockchain:
        collections = [c for c in collections if c.get('blockchain') == blockchain]

    # Format for mobile
    mobile_collections = []
    for collection in collections:
        floor_native = collection.get('floor_price_ada') or 0
        floor_usd = collection.get('floor_price_usd') or 0
        total_usd = collection.get('total_value_usd') or 0
        chain = collection.get('blockchain', 'cardano')

        # Get collection image: try collection-level image_url (EVM chains),
        # then fall back to first NFT's image or thumbnail endpoint
        logo_url = collection.get('image_url', '')
        if not logo_url:
            nft_list = collection.get('nfts', [])
            if nft_list:
                first_nft = nft_list[0]
                # Use direct image URL if available
                logo_url = first_nft.get('image') or first_nft.get('image_url', '')
                # If still empty, build thumbnail URL from asset_id
                if not logo_url:
                    asset_id = first_nft.get('asset_id', '')
                    if asset_id:
                        logo_url = f"/nfts/images/{chain}/{asset_id}/thumbnail"

        # Build individual NFT list with image URLs
        nft_items = []
        for nft in collection.get('nfts', []):
            asset_id = nft.get('asset_id', '')
            nft_image = nft.get('image') or nft.get('image_url', '')
            if not nft_image and asset_id:
                nft_image = f"/nfts/images/{chain}/{asset_id}/thumbnail"
            nft_items.append({
                "asset_id": asset_id,
                "name": nft.get('name', 'Unknown'),
                "image_url": nft_image,
            })

        mobile_collections.append({
            "name": collection.get('name', 'Unknown'),
            "blockchain": chain,
            "nft_count": collection.get('count', 0),
            "floor_price_native": round(floor_native, 2),
            "floor_price_usd": round(floor_usd, 2),
            "total_floor_value_usd": round(total_usd, 2),
            "logo_url": logo_url,
            "policy_id": collection.get('policy_id', ''),
            "nfts": nft_items,
        })

    return {
        "total_nfts": sum(c['nft_count'] for c in mobile_collections),
        "total_collections": len(mobile_collections),
        "total_floor_value_usd": round(sum(c['total_floor_value_usd'] for c in mobile_collections), 2),
        "collections": mobile_collections,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/wallet-sources")
async def get_mobile_wallet_sources(
    user_id: int = Depends(verify_session),
):
    """
    List wallet sources grouped by source type with latest USD value for mobile UI.
    """
    cache_key = f"mobile_wallet_sources_{user_id}"

    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        return cached

    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        demo_sources = _build_demo_wallet_sources()
        result = {
            "total_sources": len(demo_sources),
            "groups": _group_sources_for_mobile(demo_sources),
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
        await set_cache(cache_key, result, MOBILE_CACHE_TTL, user_id=user_id)
        return result

    sources = await get_wallet_sources(user_id=user_id, active_only=True)
    latest_values = await _get_latest_source_values(user_id)

    mobile_sources = []
    for source in sources:
        latest = latest_values.get(source["id"], {})
        mobile_sources.append({
            "id": source["id"],
            "source_type": source["source_type"],
            "source_key": source["source_key"],
            "chain": source.get("chain"),
            "label": source.get("label"),
            "wallet_id": source.get("wallet_id"),
            "is_active": bool(source.get("is_active", 1)),
            "latest_value_usd": round(float(latest.get("latest_value_usd", 0) or 0), 2),
            "latest_date": latest.get("latest_date"),
            "icon_url": _source_icon_url(source),
        })

    result = {
        "total_sources": len(mobile_sources),
        "groups": _group_sources_for_mobile(mobile_sources),
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    await set_cache(cache_key, result, MOBILE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/wallet-sources/{source_id}/chart")
async def get_mobile_wallet_source_chart(
    source_id: int,
    user_id: int = Depends(verify_session),
    range: str = Query("7d", description="Time range: 24h, 7d, 4w, 3m, 1y, all"),
):
    """
    Get per-wallet/source historical chart for mobile drill-down.
    """
    cache_key = f"mobile_wallet_source_chart_{user_id}_{source_id}_{range}"

    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        return cached

    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        demo_sources = _build_demo_wallet_sources()
        source = next((s for s in demo_sources if s["id"] == source_id), None)
        if not source:
            raise HTTPException(status_code=404, detail="Wallet source not found")

        range_days = {"7d": 7, "4w": 28, "3m": 90, "1y": 365, "all": 365}
        days = range_days.get(range, 7)
        base_value = source.get("latest_value_usd", 0) or 0

        data = []
        for i in range(days):
            day = datetime.utcnow() - timedelta(days=days - i - 1)
            daily_value = base_value * (0.9 + (i / max(days, 1)) * 0.2)
            data.append({
                "timestamp": day.strftime("%Y-%m-%d"),
                "value_usd": round(daily_value, 2),
                "metadata": {},
            })

        summary = _compute_value_summary([row["value_usd"] for row in data])
        result = {
            "source": {
                "id": source["id"],
                "source_type": source["source_type"],
                "source_key": source["source_key"],
                "chain": source.get("chain"),
                "label": source.get("label"),
                "icon_url": source.get("icon_url", ""),
            },
            "range": range,
            "data_points": len(data),
            "chart_data": data,
            "summary": summary,
            "coverage": _compute_chart_coverage([{"date": d["timestamp"]} for d in data]),
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }
        await set_cache(cache_key, result, CHART_CACHE_TTL, user_id=user_id)
        return result

    source = await get_wallet_source_by_id(source_id)
    if not source or source.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Wallet source not found")

    mapped_range = _map_mobile_range_to_portfolio_range(range)
    wallet_chart = await portfolio.get_wallet_chart(
        source_id=source_id,
        user_id=user_id,
        range=mapped_range,
    )

    data = wallet_chart.get("data", [])
    chart_data = []
    for row in data:
        metadata = row.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json_mod.loads(metadata)
            except (ValueError, TypeError):
                metadata = {}
        elif not isinstance(metadata, dict):
            metadata = {}

        chart_data.append({
            "timestamp": row.get("date"),
            "value_usd": round(float(row.get("value_usd") or 0), 2),
            "metadata": metadata,
        })

    summary = _compute_value_summary([row["value_usd"] for row in chart_data])

    result = {
        "source": {
            "id": source["id"],
            "source_type": source["source_type"],
            "source_key": source["source_key"],
            "chain": source.get("chain"),
            "label": source.get("label"),
            "icon_url": _source_icon_url(source),
        },
        "range": range,
        "mapped_range": mapped_range,
        "data_points": len(chart_data),
        "chart_data": chart_data,
        "summary": summary,
        "coverage": wallet_chart.get("coverage") or {
            "oldest_date": None,
            "newest_date": None,
            "total_days": 0,
        },
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    await set_cache(cache_key, result, CHART_CACHE_TTL, user_id=user_id)
    return result


@router.get("/portfolio/breakdown-history")
async def get_mobile_portfolio_breakdown_history(
    user_id: int = Depends(verify_session),
    range: str = Query("7d", description="Time range: 24h, 7d, 4w, 3m, 1y, all"),
):
    """
    Stacked composition history by source type for mobile area charts.
    """
    cache_key = f"mobile_breakdown_history_{user_id}_{range}"

    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        return cached

    mapped_range = _map_mobile_range_to_portfolio_range(range)
    unified = await portfolio.get_unified_chart(user_id=user_id, range=mapped_range)
    points = unified.get("data", [])

    chart_data = []
    for point in points:
        components = (point.get("breakdown") or {}).get("components", {})
        chart_data.append({
            "timestamp": point.get("date"),
            "total_value_usd": round(float(point.get("total_value") or 0), 2),
            "on_chain_value_usd": round(float(point.get("on_chain_value") or 0), 2),
            "off_chain_value_usd": round(float(point.get("off_chain_value") or 0), 2),
            "components": {
                "wallets": round(float(components.get("wallets") or 0), 2),
                "exchanges": round(float(components.get("exchange") or 0), 2),
                "staking": round(float(components.get("staking") or 0), 2),
                "defi": round(float(components.get("defi") or 0), 2),
                "nfts": round(float(components.get("nfts") or 0), 2),
                "tracked_tokens": round(float(components.get("tracked_tokens") or 0), 2),
            },
        })

    result = {
        "range": range,
        "mapped_range": mapped_range,
        "data_points": len(chart_data),
        "chart_data": chart_data,
        "coverage": unified.get("coverage") or {
            "oldest_date": None,
            "newest_date": None,
            "total_days": 0,
        },
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    await set_cache(cache_key, result, CHART_CACHE_TTL, user_id=user_id)
    return result


@router.get("/chart/portfolio-history")
async def get_mobile_portfolio_history(
    user_id: int = Depends(verify_session),
    range: str = Query("7d", description="Time range: 24h, 7d, 4w, 3m, 1y, all"),
    interval: Optional[str] = Query(None, description="Data interval: hourly, daily (auto if not specified)"),
    slim: bool = Query(False, description="Omit per-point breakdown/on-chain/off-chain fields (~4x smaller payload)")
):
    """
    Get historical portfolio value for charts.

    Mobile-optimized format compatible with chart libraries.
    Uses the unified chart endpoint for complete on-chain + off-chain data.

    Slim contract (slim=true): every chart_data point is exactly
    {"timestamp", "total_value_usd"}; the top-level "range", "interval",
    "data_points", "summary" (all six fields), and "last_updated" keys are
    unchanged and guaranteed. Default (slim=false) is byte-identical to the
    pre-slim response, including per-point "on_chain_value_usd",
    "off_chain_value_usd", and the six-component "breakdown".
    """
    try:
        # 24h range uses dedicated hourly endpoint
        if range == "24h":
            unified_data = await portfolio.get_24h_hourly_chart(user_id=user_id, refresh=False)
        else:
            # Map mobile ranges to unified endpoint ranges
            range_map = {"7d": "1w", "4w": "1m", "3m": "3m", "1y": "1y", "all": "all"}
            unified_range = range_map.get(range, "1w")

            # Call unified chart endpoint
            unified_data = await portfolio.get_unified_chart(user_id=user_id, range=unified_range)

        data_points = unified_data.get('data', [])
        if data_points:
            values = [(point.get('total_value') or 0) for point in data_points]
            starting_value = values[0] if values else 0
            ending_value = values[-1] if values else 0
            change_usd = ending_value - starting_value
            change_percent = (change_usd / starting_value * 100) if starting_value > 0 else 0

            summary = {
                "starting_value": round(starting_value, 2),
                "ending_value": round(ending_value, 2),
                "change_usd": round(change_usd, 2),
                "change_percent": round(change_percent, 2),
                "highest_value": round(max(values), 2),
                "lowest_value": round(min(values), 2)
            }
        else:
            summary = {
                "starting_value": 0, "ending_value": 0,
                "change_usd": 0, "change_percent": 0,
                "highest_value": 0, "lowest_value": 0
            }

        # Format chart data for mobile chart libs
        chart_data = []
        if slim:
            # Mobile plots only the total line; skip the breakdown fields
            # (~4x payload). See the slim contract in the docstring.
            for point in data_points:
                chart_data.append({
                    "timestamp": point.get('date', ''),
                    "total_value_usd": round(point.get('total_value') or 0, 2),
                })
        else:
            for point in data_points:
                components = (point.get('breakdown') or {}).get('components', {})
                chart_data.append({
                    "timestamp": point.get('date', ''),
                    "total_value_usd": round(point.get('total_value') or 0, 2),
                    "on_chain_value_usd": round(point.get('on_chain_value') or 0, 2),
                    "off_chain_value_usd": round(point.get('off_chain_value') or 0, 2),
                    "breakdown": {
                        "wallets": round(components.get('wallets') or 0, 2),
                        "staking": round(components.get('staking') or 0, 2),
                        "defi": round(components.get('defi') or 0, 2),
                        "exchanges": round(components.get('exchange') or 0, 2),
                        "nfts": round(components.get('nfts') or 0, 2),
                        "tracked_tokens": round(components.get('tracked_tokens') or 0, 2),
                    }
                })

        return {
            "range": range,
            "interval": interval or "daily",
            "data_points": len(chart_data),
            "chart_data": chart_data,
            "summary": summary,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        logger.error(f"Mobile portfolio history failed: {e}", exc_info=True)
        return {
            "range": range,
            "interval": interval or "daily",
            "data_points": 0,
            "chart_data": [],
            "summary": {
                "starting_value": 0, "ending_value": 0,
                "change_usd": 0, "change_percent": 0,
                "highest_value": 0, "lowest_value": 0
            },
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "error": str(e)
        }


async def fetch_ohlcv_coingecko(symbol: str, days: int) -> Optional[List[List]]:
    """
    Fetch OHLCV data from CoinGecko API.

    Args:
        symbol: Cryptocurrency symbol (BTC, ETH, etc.)
        days: Number of days of history (1, 7, 30, 90, 365)

    Returns:
        List of OHLCV data points or None if failed
    """
    coin_id = SYMBOL_TO_COINGECKO.get(symbol.upper())

    # Fallback: resolve via CoinGecko search / engine DB / CoinPaprika
    if not coin_id:
        try:
            from services.pricing import resolve_coingecko_id
            coin_id = await resolve_coingecko_id(symbol.upper())
        except Exception as e:
            logger.debug(f"resolve_coingecko_id failed for {symbol}: {e}")

    if not coin_id:
        logger.info(f"No CoinGecko ID found for {symbol}, skipping CoinGecko OHLCV")
        return None

    try:
        client = get_client("coingecko", timeout=30.0)
        response = await client.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
            params={
                "vs_currency": "usd",
                "days": days
            }
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"CoinGecko OHLCV error {response.status_code} for {symbol} (id={coin_id})")
            return None
    except Exception as e:
        logger.error(f"CoinGecko OHLCV fetch error for {symbol}: {e}")
        return None


async def fetch_ohlcv_binance(symbol: str, limit: int = 168, interval: str = "1h") -> Optional[List[Dict]]:
    """
    Fetch OHLCV data from Binance public API.

    Args:
        symbol: Cryptocurrency symbol (BTC, ETH, etc.)
        limit: Number of candlesticks (max 1000)
        interval: Candle interval (1h, 1d, etc.)

    Returns:
        List of OHLCV data points or None if failed
    """
    try:
        # Binance uses BTCUSDT format
        pair = f"{symbol.upper()}USDT"

        client = get_client("binance_public", timeout=30.0)

        response = await client.get(
            "https://api.binance.com/api/v3/klines",
            params={
                "symbol": pair,
                "interval": interval,
                "limit": limit
            }
        )

        if response.status_code == 200:
            data = response.json()
            # Transform Binance format to our format
            # Binance format: [timestamp, open, high, low, close, volume, ...]
            ohlcv = []
            for candle in data:
                ohlcv.append({
                    "timestamp": int(candle[0]) // 1000,  # Convert ms to seconds
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
                })
            return ohlcv
        else:
            logger.warning(f"Binance OHLCV error {response.status_code} for {symbol}")
            return None
    except Exception as e:
        logger.error(f"Binance OHLCV fetch error for {symbol}: {e}")
        return None


async def fetch_ohlcv_coinbase(symbol: str, period: str = "week") -> Optional[List[Dict]]:
    """
    Fetch historic rates from Coinbase public API.

    Args:
        symbol: Cryptocurrency symbol (BTC, ETH, etc.)
        period: Time period (day, week, month, year)

    Returns:
        List of price data points or None if failed
    """
    try:
        client = get_client("coinbase_public", timeout=30.0)
        response = await client.get(
            f"https://api.coinbase.com/v2/prices/{symbol.upper()}-USD/historic",
            params={
                "period": period
            }
        )

        if response.status_code == 200:
            data = response.json()
            prices = data.get('data', {}).get('prices', [])

            # Transform to OHLCV format (Coinbase only has close prices)
            ohlcv = []
            for price_point in prices:
                timestamp = int(datetime.fromisoformat(price_point['time'].replace('Z', '+00:00')).timestamp())
                price = float(price_point['price'])
                ohlcv.append({
                    "timestamp": timestamp,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0  # Not available
                })
            return ohlcv
        else:
            logger.warning(f"Coinbase historic error {response.status_code} for {symbol}")
            return None
    except Exception as e:
        logger.error(f"Coinbase historic fetch error for {symbol}: {e}")
        return None


@router.get("/chart/price/{symbol}")
async def get_mobile_price_chart(
    symbol: str,
    user_id: int = Depends(verify_session),
    range: str = Query("7d", description="Time range: 1h, 24h, 7d, 30d, 90d, 1y, all"),
    interval: Optional[str] = Query(None, description="Interval: 1m, 5m, 15m, 1h, 4h, 1d")
):
    """
    Get OHLCV price history for a specific cryptocurrency.

    Uses multiple fallback sources:
    1. CoinGecko (free, no auth, OHLC data)
    2. Binance (free, public API, full OHLCV)
    3. Coinbase (free, historic prices)

    Returns TradingView-compatible OHLCV format.
    """
    cache_key = f"mobile_price_chart_{symbol}_{range}"

    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        return cached

    symbol = symbol.upper()

    # Map range to days
    range_to_days = {
        "1h": 1,
        "24h": 1,
        "1d": 1,
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "1y": 365,
        "all": 365
    }
    days = range_to_days.get(range, 7)

    # Source tracking for logging
    chart_source = None
    formatted_data = []

    # 1. Try CoinGecko first (has OHLC data)
    ohlcv_data = await fetch_ohlcv_coingecko(symbol, days)

    if ohlcv_data:
        # CoinGecko format: [timestamp_ms, open, high, low, close]
        for candle in ohlcv_data:
            formatted_data.append({
                "timestamp": int(candle[0]) // 1000,  # Convert ms to seconds
                "open": round(candle[1], 6),
                "high": round(candle[2], 6),
                "low": round(candle[3], 6),
                "close": round(candle[4], 6),
                "volume": 0  # CoinGecko OHLC doesn't include volume
            })
        chart_source = "CoinGecko"
        logger.info(f"Fetched {len(formatted_data)} OHLCV points from CoinGecko for {symbol}")

    # 2. Try Charli3 for Cardano native tokens
    if not formatted_data:
        from services.pricing import CARDANO_TOKEN_POLICIES
        if symbol.upper() in CARDANO_TOKEN_POLICIES:
            logger.info(f"CoinGecko failed, trying Charli3 for Cardano token {symbol}")
            try:
                from services.charli3 import charli3_service
                if await charli3_service.is_configured():
                    now_ts = int(datetime.utcnow().timestamp())
                    from_ts = now_ts - (days * 86400)
                    resolution = "1d" if days > 7 else "60min"
                    candles = await charli3_service.get_ohlcv_history(
                        symbol, resolution=resolution, from_ts=from_ts, to_ts=now_ts
                    )
                    if candles:
                        for candle in candles:
                            formatted_data.append({
                                "timestamp": int(candle['time']),
                                "open": round(float(candle.get('open', 0)), 6),
                                "high": round(float(candle.get('high', 0)), 6),
                                "low": round(float(candle.get('low', 0)), 6),
                                "close": round(float(candle.get('close', 0)), 6),
                                "volume": float(candle.get('volume', 0))
                            })
                        chart_source = "Charli3"
                        logger.info(f"Fetched {len(formatted_data)} OHLCV points from Charli3 for {symbol}")
            except Exception as e:
                logger.warning(f"Charli3 OHLCV fetch failed for {symbol}: {e}")

    # 3. Try DefiLlama (free, unlimited, no auth needed)
    if not formatted_data:
        logger.info(f"Trying DefiLlama for {symbol}")
        try:
            cg_id = SYMBOL_TO_COINGECKO.get(symbol.upper())
            if not cg_id:
                from services.pricing import resolve_coingecko_id
                cg_id = await resolve_coingecko_id(symbol.upper())
            if cg_id:
                dl_client = get_client("defilama", timeout=15.0)
                now_ts = int(datetime.utcnow().timestamp())
                from_ts = now_ts - (days * 86400)
                period = "1d" if days > 7 else "1h"
                span = days if period == "1d" else days * 24
                dl_resp = await dl_client.get(
                    f"https://coins.llama.fi/chart/coingecko:{cg_id}",
                    params={"start": from_ts, "span": span, "period": period}
                )
                if dl_resp.status_code == 200:
                    dl_data = dl_resp.json()
                    coin_key = f"coingecko:{cg_id}"
                    prices = dl_data.get('coins', {}).get(coin_key, {}).get('prices', [])
                    if prices:
                        for entry in prices:
                            ts = entry.get('timestamp', 0)
                            price = float(entry.get('price', 0))
                            formatted_data.append({
                                "timestamp": ts,
                                "open": round(price, 6),
                                "high": round(price, 6),
                                "low": round(price, 6),
                                "close": round(price, 6),
                                "volume": 0
                            })
                        chart_source = "DefiLlama"
                        logger.info(f"Fetched {len(formatted_data)} points from DefiLlama for {symbol}")
        except Exception as e:
            logger.warning(f"DefiLlama chart fetch failed for {symbol}: {e}")

    # 4. Fallback to Binance
    if not formatted_data:
        logger.info(f"Trying Binance for {symbol}")
        binance_interval = "1d" if days >= 90 else "1h"
        limit_map = {
            "1h": 12,
            "24h": 24,
            "1d": 24,
            "7d": 168,
            "30d": 720,
            "90d": 90,
            "1y": 365,
            "all": 365
        }
        limit = limit_map.get(range, 168)
        formatted_data = await fetch_ohlcv_binance(symbol, limit, interval=binance_interval)
        if formatted_data:
            chart_source = "Binance"
            logger.info(f"Fetched {len(formatted_data)} OHLCV points from Binance for {symbol}")

    # 5. Final fallback to Coinbase
    if not formatted_data:
        logger.info(f"Trying Coinbase for {symbol}")
        coinbase_period_map = {
            "1h": "day", "24h": "day", "1d": "day",
            "7d": "week", "30d": "month",
            "90d": "year", "1y": "year", "all": "year"
        }
        coinbase_period = coinbase_period_map.get(range, "week")
        formatted_data = await fetch_ohlcv_coinbase(symbol, period=coinbase_period)
        if formatted_data:
            chart_source = "Coinbase"
            logger.info(f"Fetched {len(formatted_data)} points from Coinbase for {symbol}")

    if not formatted_data:
        logger.warning(f"All chart sources exhausted for {symbol} (CoinGecko, Charli3, DefiLlama, Binance, Coinbase)")
        raise HTTPException(
            status_code=404,
            detail=f"No price chart data available for {symbol}. "
                   f"Tried: CoinGecko, Charli3, DefiLlama, Binance, Coinbase. "
                   f"Token may not have market data on any supported source."
        )

    # Get current price and 24h change
    all_prices = await pricing_service.get_all_tracked_prices()
    price_data = all_prices.get(symbol, {})
    current_price = price_data.get('usd', formatted_data[-1]['close'] if formatted_data else 0)
    change_24h = price_data.get('usd_24h_change', 0)

    result = {
        "symbol": symbol,
        "range": range,
        "interval": interval or "1h",
        "data_points": len(formatted_data),
        "ohlcv_data": formatted_data,
        "current_price": round(current_price, 6),
        "change_24h": round(change_24h, 2),
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }

    await set_cache(cache_key, result, CHART_CACHE_TTL, user_id=user_id)
    return result


@router.get("/asset/{symbol}/wallet-breakdown")
async def get_asset_wallet_breakdown(
    symbol: str,
    user_id: int = Depends(verify_session),
):
    """
    Per-wallet/source breakdown for a single token.

    Gathers data from L1 chain wallets, native tokens, exchanges, staking,
    and DeFi positions, then returns each source with allocation percentages.
    """
    symbol = symbol.upper()
    cache_key = f"mobile_wallet_breakdown_{user_id}_{symbol}"

    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        return cached

    all_prices = await pricing_service.get_all_tracked_prices()
    price_info = all_prices.get(symbol, {})
    current_price = price_info.get('usd', 0)

    # Symbol → blockchain mapping (reverse of symbol_map)
    symbol_to_chains = {
        'ADA': ['cardano'], 'BTC': ['bitcoin'], 'ETH': ['ethereum', 'base', 'arbitrum'],
        'SOL': ['solana'], 'MATIC': ['polygon'], 'POL': ['polygon'],
        'ALGO': ['algorand'], 'BNB': ['bsc'], 'AVAX': ['avalanche'],
        'TRX': ['tron'], 'XRP': ['xrp'], 'HBAR': ['hedera'],
        'EGLD': ['multiversx'], 'SUI': ['sui'], 'APT': ['aptos'],
        'FIL': ['filecoin'], 'LTC': ['litecoin'], 'DOGE': ['dogecoin'],
        'ZEC': ['zcash'], 'XTZ': ['tezos'], 'STX': ['stacks'],
        'VET': ['vechain'], 'ATOM': ['cosmos'], 'NEAR': ['near'],
        'ICP': ['icp'],
    }

    sources = []

    # Read directly from cache — do NOT call route handlers (they use Depends() injection)
    portfolio_summary, native_assets_data = await asyncio.gather(
        get_cache(f"portfolio_summary_{user_id}", user_id=user_id),
        get_cache("native_assets_all", user_id=user_id),
    )
    if not portfolio_summary:
        portfolio_summary = {}
        logger.warning(f"Wallet breakdown: no cached portfolio_summary for user {user_id}")
    if not native_assets_data:
        native_assets_data = {}

    # 1. L1 chain wallets — read per-wallet data from portfolio summary
    l1_chains = symbol_to_chains.get(symbol, [])
    for chain in l1_chains:
        chain_data = portfolio_summary.get(chain, {})
        logger.debug(f"Wallet breakdown {symbol}: chain={chain}, wallets={len(chain_data.get('wallets', []))}")
        for w in chain_data.get('wallets', []):
            amount = float(w.get('balance', 0))
            if amount <= 0:
                continue
            sources.append({
                'source_type': 'wallet',
                'label': w.get('label') or f"{chain.title()} Wallet",
                'address': w.get('address', ''),
                'blockchain': chain,
                'amount': amount,
                'value_usd': round(amount * current_price, 2),
                'last_synced': w.get('updated_at') or (datetime.utcnow().isoformat() + 'Z'),
            })

    # 2. Native tokens (ERC-20, SPL, Cardano native) — per-wallet data
    if not l1_chains:
        try:
            for asset in native_assets_data.get('valuable_assets', []):
                ticker = (asset.get('ticker') or asset.get('asset_name', '')).upper()
                if ticker != symbol:
                    continue
                for wallet_entry in asset.get('wallets', []):
                    amount = float(wallet_entry.get('quantity', 0))
                    if amount <= 0:
                        continue
                    sources.append({
                        'source_type': 'wallet',
                        'label': wallet_entry.get('label') or 'Wallet',
                        'address': wallet_entry.get('address', ''),
                        'blockchain': wallet_entry.get('blockchain', ''),
                        'amount': amount,
                        'value_usd': round(amount * current_price, 2),
                        'last_synced': datetime.utcnow().isoformat() + 'Z',
                    })
        except Exception as e:
            logger.debug(f"Native token breakdown failed for {symbol}: {e}")

    # 3. Exchange assets
    exchange_names = ['coinbase', 'binance', 'binance_us', 'okx', 'bitget', 'gate', 'kucoin']
    exchange_caches = await asyncio.gather(*[
        get_cache(f"{name}_portfolio", user_id=user_id) for name in exchange_names
    ])
    for name, exc_data in zip(exchange_names, exchange_caches):
        if not exc_data or not exc_data.get('assets'):
            continue
        for asset in exc_data['assets']:
            currency = (asset.get('currency') or '').upper()
            if currency != symbol:
                continue
            amount = float(asset.get('balance', 0))
            if amount <= 0:
                continue
            info = EXCHANGE_INFO.get(name, {})
            sources.append({
                'source_type': 'exchange',
                'label': info.get('display_name', name.title()),
                'amount': amount,
                'value_usd': round(amount * current_price, 2),
                'last_synced': datetime.utcnow().isoformat() + 'Z',
            })

    # 4. Staking positions — every kind, via the shared valuation so the
    # drill-down matches the Staking tab and summary figures
    from services.defi import iter_staking_token_values
    _KIND_LABELS = {
        'staked': 'Staked in {p}',
        'trading_balance': '{p} V2 Trading Account',
        'vault': '{p} Vault',
        'cdp': '{p} CDP (net of debt)',
        'stability_pool': '{p} Stability Pool',
        'reward': '{p} pending rewards',
    }
    cardano_wallet_entries = portfolio_summary.get('cardano', {}).get('wallets', [])
    staking_caches = await asyncio.gather(*[
        get_cache(f"staking_positions_{w['address']}", user_id=user_id) for w in cardano_wallet_entries
    ], return_exceptions=True)
    for w, cached_staking in zip(cardano_wallet_entries, staking_caches):
        if isinstance(cached_staking, Exception) or not cached_staking or not isinstance(cached_staking, dict):
            continue
        for protocol_name, protocol_data in (cached_staking.get('protocols') or {}).items():
            for entry in iter_staking_token_values(protocol_data, all_prices):
                if entry['token'] != symbol:
                    continue
                source = {
                    'source_type': 'staking',
                    'label': _KIND_LABELS.get(entry['kind'], 'Staked in {p}').format(p=protocol_name),
                    'address': w['address'],
                    'blockchain': 'cardano',
                    'amount': entry['amount'],
                    'value_usd': round(entry['usd'], 2),
                }
                if not entry['priced']:
                    source['priced'] = False
                sources.append(source)

    # 5. DeFi positions
    defi_data = await get_cache(f"defi_summary_{user_id}")
    if defi_data and defi_data.get('all_positions'):
        for pos in defi_data['all_positions']:
            token = (pos.get('token') or '').upper()
            if token != symbol:
                continue
            amount = float(pos.get('quantity', 0))
            if amount <= 0:
                continue
            sources.append({
                'source_type': 'defi',
                'label': pos.get('protocol', 'DeFi'),
                'amount': amount,
                'value_usd': round(amount * current_price, 2),
            })

    # Calculate totals and allocation percentages
    total_amount = sum(s['amount'] for s in sources)
    total_value = round(total_amount * current_price, 2)

    # Sort by value descending
    sources.sort(key=lambda s: s['value_usd'], reverse=True)

    for s in sources:
        s['amount'] = round(s['amount'], 8)
        s['allocation_pct'] = round(
            (s['amount'] / total_amount * 100) if total_amount > 0 else 0, 1
        )

    # Debug: include diagnostics when no sources found
    debug_info = None
    if not sources:
        chains_checked = l1_chains
        chain_keys = list(portfolio_summary.keys()) if portfolio_summary else []
        wallet_counts = {}
        for c in chains_checked:
            cd = portfolio_summary.get(c, {})
            ws = cd.get('wallets', [])
            wallet_counts[c] = {
                'count': len(ws),
                'balances': [w.get('balance', 'MISSING') for w in ws[:5]],
                'keys': list(ws[0].keys()) if ws else [],
            }
        debug_info = {
            'chains_checked': chains_checked,
            'portfolio_summary_keys': chain_keys[:10],
            'portfolio_summary_type': type(portfolio_summary).__name__,
            'has_cache': portfolio_summary is not None and len(portfolio_summary) > 0,
            'wallet_counts': wallet_counts,
        }
        logger.warning(f"Wallet breakdown empty for {symbol}: {debug_info}")

    result = {
        'symbol': symbol,
        'current_price_usd': round(current_price, 6),
        'total_amount': round(total_amount, 8),
        'total_value_usd': total_value,
        'sources': sources,
    }
    await set_cache(cache_key, result, MOBILE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/status")
async def get_mobile_api_status():
    """
    Get mobile API health and system status.

    No authentication required for health check.
    """
    import time
    from config import DATABASE_PATH

    # Check database
    db_status = "connected" if DATABASE_PATH.exists() else "error"

    return {
        "status": "healthy",
        "version": "1.0.0",
        "build": str(int(time.time())),
        "uptime_seconds": 0,  # TODO: Calculate actual uptime
        "services": {
            "database": db_status,
            "blockchain_apis": "operational",
            "exchange_apis": "operational",
            "price_feeds": "operational"
        },
        "rate_limits": {
            "requests_per_minute": 60,
            "requests_remaining": 60
        },
        "server_time": datetime.utcnow().isoformat() + "Z"
    }
