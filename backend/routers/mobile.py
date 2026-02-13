"""
Mobile API Router - Optimized endpoints for ABCT mobile companion app.

This module provides mobile-friendly API endpoints with:
- Consolidated responses (fewer API calls)
- OHLCV chart data with multiple fallback sources
- Simplified data formats
- Proper caching and error handling

All endpoints require authentication via verify_session.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict
from datetime import datetime, timedelta
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
from services.cardano import cardano_service
from database import (
    get_all_wallets,
    get_wallet_balance,
    get_wallet_assets,
    get_cache,
    set_cache,
    get_username_by_user_id,
    get_wallet_sources,
    get_wallet_source_by_id,
)
from auth_utils import verify_session
from middleware.demo_mode import is_demo_user
from services.http_client import get_client
from config import DATABASE_PATH

router = APIRouter(prefix="/api/mobile", tags=["mobile"])
logger = logging.getLogger(__name__)

# Cache TTL
MOBILE_CACHE_TTL = 120  # 2 minutes for mobile responses
CHART_CACHE_TTL = 900  # 15 minutes for chart data

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

# CoinGecko ID mapping for OHLCV data
SYMBOL_TO_COINGECKO = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'ADA': 'cardano',
    'SOL': 'solana',
    'MATIC': 'polygon-ecosystem-token',
    'POL': 'polygon-ecosystem-token',
    'DOGE': 'dogecoin',
    'XRP': 'ripple',
    'DOT': 'polkadot',
    'USDC': 'usd-coin',
    'USDT': 'tether',
}

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
    "base": "https://cryptologos.cc/logos/base-base-logo.png",
    "algorand": "https://cryptologos.cc/logos/algorand-algo-logo.png",
    "bsc": "https://cryptologos.cc/logos/bnb-bnb-logo.png",
    "arbitrum": "https://cryptologos.cc/logos/arbitrum-arb-logo.png",
    "avalanche": "https://cryptologos.cc/logos/avalanche-avax-logo.png",
    "tron": "https://cryptologos.cc/logos/tron-trx-logo.png",
}


def _map_mobile_range_to_portfolio_range(range_value: str) -> str:
    range_map = {"7d": "1w", "4w": "1m", "3m": "3m", "1y": "1y", "all": "all"}
    return range_map.get(range_value, "1w")


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


@router.get("/portfolio/summary")
async def get_mobile_portfolio_summary(
    user_id: int = Depends(verify_session),
    refresh: bool = Query(False, description="Force refresh from blockchain APIs")
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
    cache_key = f"mobile_portfolio_summary_{user_id}"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return cached

    # Fetch all data in parallel (including snapshot for staking/defi/tracked tokens)
    portfolio_data, exchange_summary, nft_summary, defi_summary, snapshot_totals = await asyncio.gather(
        portfolio.get_portfolio_summary(user_id=user_id, refresh=refresh),
        exchanges.get_all_exchanges_summary(user_id=user_id),
        nfts.get_nft_summary(user_id=user_id),
        defi.get_defi_summary(user_id=user_id),
        portfolio.get_portfolio_totals(user_id=user_id),
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
        nft_summary = {"total_value_usd": 0, "collections": []}
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

    # All blockchains supported by portfolio summary
    symbol_map = {
        'cardano': ('ADA', 'total_ada'),
        'bitcoin': ('BTC', 'total_btc'),
        'ethereum': ('ETH', 'total_eth'),
        'solana': ('SOL', 'total_sol'),
        'polygon': ('POL', 'total_matic'),
        'base': ('ETH', 'total_eth'),
        'algorand': ('ALGO', 'total_algo'),
        'bsc': ('BNB', 'total_bnb'),
        'arbitrum': ('ETH', 'total_eth'),
        'avalanche': ('AVAX', 'total_avax'),
        'tron': ('TRX', 'total_trx'),
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
        value_usd = native_amount * price_usd

        # Add native assets value (tokens)
        value_usd += chain_data.get('native_assets_value_usd', 0)

        if value_usd > 0:
            self_custody_value += value_usd
            native_totals[symbol.lower()] = native_amount

            blockchain_summaries.append({
                "name": blockchain,
                "symbol": symbol,
                "value_usd": round(value_usd, 2),
                "native_amount": round(native_amount, 8),
                "native_price_usd": round(price_usd, 2),
                "wallet_count": chain_data.get('wallet_count', 0),
                "percentage": 0  # Calculated later
            })

    # Get component values
    exchanges_value = exchange_summary.get('total_usd', 0)
    nfts_value = nft_summary.get('total_value_usd', 0)

    # Staking/DeFi/tracked tokens from latest snapshot (matches web dashboard logic)
    staking_value = snapshot_totals.get('staking_usd', 0) or 0
    defi_value = snapshot_totals.get('defi_usd', 0) or 0
    tracked_tokens_value = snapshot_totals.get('tracked_tokens_usd', 0) or 0

    # Calculate total
    total_value_usd = self_custody_value + exchanges_value + nfts_value + staking_value + defi_value + tracked_tokens_value

    # Calculate percentages
    for blockchain_summary in blockchain_summaries:
        blockchain_summary['percentage'] = round(
            (blockchain_summary['value_usd'] / total_value_usd * 100) if total_value_usd > 0 else 0,
            1
        )

    # Sort by value descending
    blockchain_summaries.sort(key=lambda x: x['value_usd'], reverse=True)

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
            }
        },
        "blockchains": blockchain_summaries,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False
    }

    await set_cache(cache_key, result, MOBILE_CACHE_TTL, user_id=user_id)
    return result


@router.get("/wallets")
async def get_mobile_wallets(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = Query(None, description="Filter by blockchain"),
    include_balances: bool = Query(True, description="Include current balances")
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

    all_wallets = await get_all_wallets(user_id=user_id)

    # Get prices for value calculations
    all_prices = await pricing_service.get_all_tracked_prices()

    mobile_wallets = []
    total_value_usd = 0.0

    for wallet in all_wallets:
        # Filter by blockchain if specified
        if blockchain and wallet['blockchain'] != blockchain:
            continue

        wallet_data = {
            "id": wallet['id'],
            "blockchain": wallet['blockchain'],
            "address": wallet['address'],
            "label": wallet.get('label'),
            "created_at": wallet.get('created_at')
        }

        if include_balances:
            balance_info = await get_wallet_balance(wallet['id'])
            assets = await get_wallet_assets(wallet['id'])

            # Get native balance
            native_balance = float(balance_info.get('amount', 0)) if balance_info else 0

            # Map blockchain to symbol and decimals
            blockchain_config = {
                'cardano': {'symbol': 'ADA', 'decimals': 6},
                'bitcoin': {'symbol': 'BTC', 'decimals': 8},
                'ethereum': {'symbol': 'ETH', 'decimals': 18},
                'solana': {'symbol': 'SOL', 'decimals': 9},
                'polygon': {'symbol': 'POL', 'decimals': 18},
                'base': {'symbol': 'ETH', 'decimals': 18}
            }

            config = blockchain_config.get(wallet['blockchain'], {'symbol': 'UNKNOWN', 'decimals': 0})
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
            wallet_data['token_count'] = len(assets)
            wallet_data['nft_count'] = 0  # TODO: Add NFT count when needed

            total_value_usd += usd_value

        mobile_wallets.append(wallet_data)

    return {
        "total_wallets": len(mobile_wallets),
        "wallets": mobile_wallets,
        "total_value_usd": round(total_value_usd, 2),
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }


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
        'base': 'ETH'
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
                "logo_url": f"https://img.logokit.com/crypto/{asset.get('ticker', 'UNKNOWN')}?size=32"
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
            "logo_url": f"https://img.logokit.com/crypto/{asset.get('currency', 'UNKNOWN')}?size=32"
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


@router.get("/defi/staking")
async def get_mobile_defi_staking(user_id: int = Depends(verify_session)):
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

    # Get prices
    all_prices = await pricing_service.get_all_tracked_prices()
    ada_price = all_prices.get('ADA', {}).get('usd', 0)

    # Track unique stake addresses to avoid duplicates
    seen_stake_addresses = set()

    # Add Cardano staking positions (if any)
    for wallet in cardano_wallets:
        try:
            # Get stake address
            stake_address = await cardano_service.get_stake_address(wallet['address'])
            if stake_address and stake_address not in seen_stake_addresses:
                seen_stake_addresses.add(stake_address)

                # Get account info
                account_info = await cardano_service.get_stake_account_info(stake_address)
                if account_info and account_info.get('controlled_ada', 0) > 0:
                    delegated_ada = account_info.get('controlled_ada', 0)
                    delegated_usd = delegated_ada * ada_price
                    rewards_ada = account_info.get('withdrawable_ada', 0)
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
                        "active": True
                    })
        except Exception as e:
            logger.warning(f"Could not get staking info for wallet {wallet['id']}: {e}")

    # Get DeFi summary for protocol positions
    defi_data = await defi.get_defi_summary(user_id=user_id)

    # Add DeFi protocol staking positions
    for position in defi_data.get('all_positions', []):
        # Only include staking-type positions
        if position.get('type') in ['staking', 'governance']:
            quantity = position.get('quantity', 0)
            token = position.get('token', 'Unknown')

            # Try to get token price
            token_price_data = all_prices.get(token.upper(), {})
            token_price_usd = token_price_data.get('usd', 0)
            staked_usd = quantity * token_price_usd

            if staked_usd > 0:
                total_staked_usd += staked_usd

                positions.append({
                    "blockchain": "cardano",
                    "protocol": position.get('protocol', 'Unknown'),
                    "staked_amount": round(quantity, 6),
                    "staked_symbol": token,
                    "staked_usd": round(staked_usd, 2),
                    "rewards_amount": 0,  # Not available in DeFi summary
                    "rewards_usd": 0,
                    "apy": 0,  # Not available in DeFi summary
                    "active": True
                })

    return {
        "total_staked_usd": round(total_staked_usd, 2),
        "total_rewards_usd": round(total_rewards_usd, 2),
        "positions": positions,
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
    range: str = Query("7d", description="Time range: 7d, 4w, 3m, 1y, all"),
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
    range: str = Query("7d", description="Time range: 7d, 4w, 3m, 1y, all"),
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
    range: str = Query("7d", description="Time range: 7d, 4w, 3m, 1y, all"),
    interval: Optional[str] = Query(None, description="Data interval: hourly, daily (auto if not specified)")
):
    """
    Get historical portfolio value for charts.

    Mobile-optimized format compatible with chart libraries.
    Uses the unified chart endpoint for complete on-chain + off-chain data.
    """
    try:
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
    if not coin_id:
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
            logger.warning(f"CoinGecko OHLCV error {response.status_code} for {symbol}")
            return None
    except Exception as e:
        logger.error(f"CoinGecko OHLCV fetch error for {symbol}: {e}")
        return None


async def fetch_ohlcv_binance(symbol: str, limit: int = 168) -> Optional[List[Dict]]:
    """
    Fetch OHLCV data from Binance public API.

    Args:
        symbol: Cryptocurrency symbol (BTC, ETH, etc.)
        limit: Number of candlesticks (max 1000)

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
                "interval": "1h",
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


async def fetch_ohlcv_coinbase(symbol: str) -> Optional[List[Dict]]:
    """
    Fetch historic rates from Coinbase public API.

    Args:
        symbol: Cryptocurrency symbol (BTC, ETH, etc.)

    Returns:
        List of price data points or None if failed
    """
    try:
        client = get_client("coinbase_public", timeout=30.0)
        response = await client.get(
            f"https://api.coinbase.com/v2/prices/{symbol.upper()}-USD/historic",
            params={
                "period": "week"
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
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "1y": 365,
        "all": 365
    }
    days = range_to_days.get(range, 7)

    # Try CoinGecko first (has OHLC data)
    ohlcv_data = await fetch_ohlcv_coingecko(symbol, days)

    if ohlcv_data:
        # CoinGecko format: [timestamp_ms, open, high, low, close]
        formatted_data = []
        for candle in ohlcv_data:
            formatted_data.append({
                "timestamp": int(candle[0]) // 1000,  # Convert ms to seconds
                "open": round(candle[1], 6),
                "high": round(candle[2], 6),
                "low": round(candle[3], 6),
                "close": round(candle[4], 6),
                "volume": 0  # CoinGecko OHLC doesn't include volume
            })

        logger.info(f"Fetched {len(formatted_data)} OHLCV points from CoinGecko for {symbol}")
    else:
        # Fallback to Binance
        logger.info(f"CoinGecko failed, trying Binance for {symbol}")

        # Calculate limit based on range
        limit_map = {
            "1h": 12,
            "24h": 24,
            "7d": 168,
            "30d": 720,
            "90d": 1000,
            "1y": 1000
        }
        limit = limit_map.get(range, 168)

        formatted_data = await fetch_ohlcv_binance(symbol, limit)

        if formatted_data:
            logger.info(f"Fetched {len(formatted_data)} OHLCV points from Binance for {symbol}")
        else:
            # Final fallback to Coinbase
            logger.info(f"Binance failed, trying Coinbase for {symbol}")
            formatted_data = await fetch_ohlcv_coinbase(symbol)

            if formatted_data:
                logger.info(f"Fetched {len(formatted_data)} points from Coinbase for {symbol}")
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"No OHLCV data available for {symbol}. Symbol may not be supported."
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
