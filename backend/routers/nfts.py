"""
NFT Router - API endpoints for NFT data.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.nft import nft_service
from services.nft_image_service import nft_image_service
from services.ethereum_nft import ethereum_nft_service
from services.solana_nft import solana_nft_service
from services.polygon import polygon_service
from services.base import base_service
from services.pricing import pricing_service
from services.nft_price_client import nft_price_client
from services.demo_nft_service import demo_nft_service
from database import get_all_wallets, get_username_by_user_id
from middleware.auth import verify_admin
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session
from services.http_client import get_client

router = APIRouter(prefix="/nfts", tags=["nfts"])

# Logger
logger = logging.getLogger(__name__)

# Background caching tasks tracker
background_cache_tasks = {}

# Minimum USD value to display
MIN_USD_VALUE = 1.00


@router.get("")
async def get_all_nfts(user_id: int = Depends(verify_session), force_refresh: bool = False):
    """
    Get all NFTs across all Cardano wallets.
    Returns NFTs with collection data and values.
    Only includes NFTs with value >= $1.00 if they have a price.
    """
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo NFTs with anime images
        all_nfts = await demo_nft_service.get_all_nfts(force_refresh=force_refresh)

        # Calculate totals
        total_value_usd = sum(nft.get('price_usd', 0) for nft in all_nfts)

        return {
            'nfts': all_nfts,
            'total_count': len(all_nfts),
            'valued_count': len(all_nfts),
            'total_value_usd': total_value_usd,
            'ada_price': 1.05,
            'min_value_filter': MIN_USD_VALUE,
            'last_updated': all_nfts[0]['updated_at'] if all_nfts else None,
            'demo_mode': True
        }

    # Normal mode - real NFT service
    all_nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=force_refresh)

    # Get ADA price for USD conversion
    ada_price = await pricing_service.get_price('ADA')

    # Filter and enrich with USD values
    filtered_nfts = []
    total_value_usd = 0.0

    for nft in all_nfts:
        price_ada = nft.get('price_ada')

        if price_ada:
            usd_value = price_ada * ada_price
            nft['price_usd'] = usd_value

            # Only include if value >= $1.00
            if usd_value >= MIN_USD_VALUE:
                filtered_nfts.append(nft)
                total_value_usd += usd_value
        else:
            # Include NFTs without price (but mark them)
            nft['price_usd'] = None
            filtered_nfts.append(nft)

    # Sort by USD value (valued first, then unvalued)
    filtered_nfts.sort(key=lambda x: (x.get('price_usd') is None, -(x.get('price_usd') or 0)))

    return {
        'nfts': filtered_nfts,
        'total_count': len(filtered_nfts),
        'valued_count': sum(1 for n in filtered_nfts if n.get('price_usd')),
        'total_value_usd': total_value_usd,
        'ada_price': ada_price,
        'min_value_filter': MIN_USD_VALUE,
        'last_updated': nft_service.last_full_refresh.isoformat() if nft_service.last_full_refresh else None
    }


@router.get("/summary")
async def get_nft_summary(user_id: int = Depends(verify_session)):
    """
    Get a summary of all NFTs grouped by collection.
    """
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo NFT summary
        summary = await demo_nft_service.get_nft_summary()
        summary['demo_mode'] = True
        return summary

    # Normal mode - real NFT service
    summary = await nft_service.get_nft_summary(user_id=user_id)

    # Get ADA price for USD conversion
    ada_price = await pricing_service.get_price('ADA')

    # Add USD values
    summary['total_value_usd'] = summary['total_value_ada'] * ada_price
    summary['ada_price'] = ada_price

    # Sort collections by value (highest first)
    summary['collections'].sort(key=lambda x: x.get('total_value_ada', 0), reverse=True)

    # Add USD values to collections
    for collection in summary['collections']:
        collection['total_value_usd'] = collection['total_value_ada'] * ada_price
        if collection.get('floor_price_ada'):
            collection['floor_price_usd'] = collection['floor_price_ada'] * ada_price

    return summary


@router.get("/collection/{policy_id}")
async def get_collection_nfts(policy_id: str, user_id: int = Depends(verify_session)):
    """Get all NFTs for a specific collection."""
    nfts = await nft_service.get_nfts_by_collection(policy_id, user_id=user_id)

    if not nfts:
        raise HTTPException(status_code=404, detail="No NFTs found for this collection")

    # Get ADA price
    ada_price = await pricing_service.get_price('ADA')

    # Add USD values
    for nft in nfts:
        if nft.get('price_ada'):
            nft['price_usd'] = nft['price_ada'] * ada_price

    return {
        'policy_id': policy_id,
        'collection_name': nfts[0]['collection'].get('name', 'Unknown') if nfts else 'Unknown',
        'nfts': nfts,
        'count': len(nfts),
        'ada_price': ada_price
    }


@router.get("/asset/{asset_id}")
async def get_nft_details(asset_id: str, user_id: int = Depends(verify_session)):
    """Get details for a specific NFT."""
    nft = await nft_service.get_nft_by_asset_id(asset_id, user_id=user_id)

    if not nft:
        raise HTTPException(status_code=404, detail="NFT not found")

    # Get ADA price
    ada_price = await pricing_service.get_price('ADA')

    if nft.get('price_ada'):
        nft['price_usd'] = nft['price_ada'] * ada_price

    return nft


@router.post("/refresh")
async def refresh_nfts(user_id: int = Depends(verify_session)):
    """Force refresh all NFT data."""
    nft_service.clear_cache()
    all_nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=True)

    return {
        'message': f'Refreshed {len(all_nfts)} NFTs',
        'count': len(all_nfts)
    }


@router.get("/status")
async def get_nft_status():
    """Get NFT service status including API configuration."""
    return nft_service.get_status()


@router.get("/prices/status")
async def get_price_collection_status():
    """
    Get status of NFT floor price collection.
    Shows coverage stats and which collections need price updates.
    """
    return await nft_service.get_price_collection_status()


@router.post("/prices/collect", dependencies=[Depends(verify_admin)])
async def collect_floor_prices(
    batch_size: int = 5,
    max_batches: int = 5
):
    """
    Manually trigger incremental floor price collection.

    - batch_size: Number of collections to fetch per batch (default 5)
    - max_batches: Maximum batches to process (default 5)

    Prioritizes collections that have never been fetched or have the oldest data.
    Stops gracefully on rate limits.
    Requires admin authentication.
    """
    result = await nft_service.collect_floor_prices_incremental(
        batch_size=batch_size,
        max_batches=max_batches
    )
    return result


# ============================================================================
# ETHEREUM NFT ENDPOINTS
# ============================================================================

@router.get("/ethereum")
async def get_ethereum_nfts(user_id: int = Depends(verify_session), force_refresh: bool = False):
    """
    Get all NFTs across all Ethereum wallets.
    Returns NFTs with collection data, floor prices, and values.
    """
    if not await ethereum_nft_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured',
            'nfts': [],
            'total_count': 0,
            'total_value_usd': 0
        }

    all_nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=force_refresh)

    # Get ETH price for USD conversion
    eth_price = await pricing_service.get_price('ETH')

    # Calculate USD values
    total_value_usd = 0.0

    for nft in all_nfts:
        floor_price_eth = nft['collection'].get('floor_price_eth', 0) or 0
        usd_value = floor_price_eth * eth_price
        nft['floor_price_usd'] = usd_value
        total_value_usd += usd_value

    # Sort by USD value (highest first)
    all_nfts.sort(key=lambda x: x.get('floor_price_usd', 0), reverse=True)

    return {
        'configured': True,
        'nfts': all_nfts,
        'total_count': len(all_nfts),
        'valued_count': sum(1 for n in all_nfts if n.get('floor_price_usd', 0) > 0),
        'total_value_usd': total_value_usd,
        'total_value_eth': sum(n['collection'].get('floor_price_eth', 0) or 0 for n in all_nfts),
        'eth_price': eth_price,
        'last_updated': ethereum_nft_service.last_refresh.isoformat() if ethereum_nft_service.last_refresh else None
    }


@router.get("/ethereum/summary")
async def get_ethereum_nft_summary(user_id: int = Depends(verify_session)):
    """
    Get a summary of all Ethereum NFTs grouped by collection.
    """
    if not ethereum_nft_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured'
        }

    summary = await ethereum_nft_service.get_nft_summary(user_id=user_id)

    # Get ETH price for USD conversion
    eth_price = await pricing_service.get_price('ETH')

    # Add USD values
    summary['total_value_usd'] = summary['total_value_eth'] * eth_price
    summary['eth_price'] = eth_price
    summary['configured'] = True

    # Add USD values to collections
    for collection in summary['collections']:
        collection['total_value_usd'] = collection['total_value_eth'] * eth_price
        if collection.get('floor_price_eth'):
            collection['floor_price_usd'] = collection['floor_price_eth'] * eth_price

    # Sort collections by value (highest first)
    summary['collections'].sort(key=lambda x: x.get('total_value_usd', 0), reverse=True)

    return summary


@router.post("/ethereum/refresh")
async def refresh_ethereum_nfts(user_id: int = Depends(verify_session)):
    """Force refresh all Ethereum NFT data."""
    if not ethereum_nft_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured'
        }

    ethereum_nft_service.clear_cache()
    all_nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=True)

    return {
        'message': f'Refreshed {len(all_nfts)} Ethereum NFTs',
        'count': len(all_nfts)
    }


@router.get("/ethereum/status")
async def get_ethereum_nft_status():
    """Get Ethereum NFT service status including API configuration."""
    return ethereum_nft_service.get_status()


# ============================================================================
# SOLANA NFT ENDPOINTS
# ============================================================================

@router.get("/solana")
async def get_solana_nfts(user_id: int = Depends(verify_session), force_refresh: bool = False):
    """
    Get all NFTs across all Solana wallets.
    Returns NFTs including Helium hotspots, compressed NFTs, and standard Solana NFTs.
    """
    if not await solana_nft_service.is_configured():
        return {
            'configured': False,
            'message': 'Helius API key not configured. Add HELIUS_API_KEY to enable Solana NFT support.',
            'nfts': [],
            'total_count': 0,
            'total_value_usd': 0
        }

    all_nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=force_refresh)

    # Get SOL price for USD conversion
    sol_price = await pricing_service.get_price('SOL')

    # Calculate USD values (floor prices not yet implemented for Solana)
    total_value_usd = 0.0

    for nft in all_nfts:
        floor_price_sol = nft['collection'].get('floor_price_sol', 0) or 0
        usd_value = floor_price_sol * sol_price
        nft['floor_price_usd'] = usd_value
        total_value_usd += usd_value

    # Sort by collection name for now
    all_nfts.sort(key=lambda x: x['collection'].get('name', ''))

    return {
        'configured': True,
        'nfts': all_nfts,
        'total_count': len(all_nfts),
        'valued_count': sum(1 for n in all_nfts if n.get('floor_price_usd', 0) > 0),
        'total_value_usd': total_value_usd,
        'total_value_sol': sum(n['collection'].get('floor_price_sol', 0) or 0 for n in all_nfts),
        'sol_price': sol_price,
        'last_updated': solana_nft_service.last_refresh.isoformat() if solana_nft_service.last_refresh else None
    }


@router.get("/solana/summary")
async def get_solana_nft_summary(user_id: int = Depends(verify_session)):
    """
    Get a summary of all Solana NFTs grouped by collection.
    """
    if not await solana_nft_service.is_configured():
        return {
            'configured': False,
            'message': 'Helius API key not configured'
        }

    summary = await solana_nft_service.get_nft_summary(user_id=user_id)

    # Get SOL price for USD conversion
    sol_price = await pricing_service.get_price('SOL')

    # Add USD values
    summary['total_value_usd'] = summary['total_value_sol'] * sol_price
    summary['sol_price'] = sol_price
    summary['configured'] = True

    # Add USD values to collections
    for collection in summary['collections']:
        collection['total_value_usd'] = collection['total_value_sol'] * sol_price
        if collection.get('floor_price_sol'):
            collection['floor_price_usd'] = collection['floor_price_sol'] * sol_price

    # Sort collections by NFT count (highest first, since floor prices may not be available)
    summary['collections'].sort(key=lambda x: x.get('nft_count', 0), reverse=True)

    return summary


@router.post("/solana/refresh")
async def refresh_solana_nfts(user_id: int = Depends(verify_session)):
    """Force refresh all Solana NFT data."""
    if not await solana_nft_service.is_configured():
        return {
            'configured': False,
            'message': 'Helius API key not configured'
        }

    solana_nft_service.clear_cache()
    all_nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=True)

    return {
        'message': f'Refreshed {len(all_nfts)} Solana NFTs',
        'count': len(all_nfts)
    }


@router.get("/solana/status")
async def get_solana_nft_status():
    """Get Solana NFT service status including API configuration."""
    return solana_nft_service.get_status()


# ============================================================================
# POLYGON NFT ENDPOINTS
# ============================================================================

@router.get("/polygon")
async def get_polygon_nfts(user_id: int = Depends(verify_session), force_refresh: bool = False):
    """
    Get all NFTs across all Polygon wallets.
    Returns NFTs with collection data, floor prices, and values.
    """
    if not await polygon_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured. Add ALCHEMY_API_KEY to enable Polygon NFT support.',
            'nfts': [],
            'total_count': 0,
            'total_value_usd': 0
        }

    # Get all Polygon wallets
    wallets = await get_all_wallets(user_id=user_id)
    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']

    if not polygon_wallets:
        return {
            'configured': True,
            'message': 'No Polygon wallets configured',
            'nfts': [],
            'total_count': 0,
            'total_value_usd': 0
        }

    all_nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=force_refresh)

    # Get MATIC price for USD conversion
    matic_price = await pricing_service.get_price('MATIC')

    # Calculate USD values
    total_value_usd = 0.0

    for nft in all_nfts:
        floor_price_matic = nft['collection'].get('floor_price_matic', 0) or 0
        usd_value = floor_price_matic * matic_price
        nft['floor_price_usd'] = usd_value
        total_value_usd += usd_value

    # Sort by USD value (highest first)
    all_nfts.sort(key=lambda x: x.get('floor_price_usd', 0), reverse=True)

    return {
        'configured': True,
        'nfts': all_nfts,
        'total_count': len(all_nfts),
        'valued_count': sum(1 for n in all_nfts if n.get('floor_price_usd', 0) > 0),
        'total_value_usd': total_value_usd,
        'total_value_matic': sum(n['collection'].get('floor_price_matic', 0) or 0 for n in all_nfts),
        'matic_price': matic_price,
        'last_updated': polygon_service.last_nft_refresh.isoformat() if polygon_service.last_nft_refresh else None
    }


@router.get("/polygon/summary")
async def get_polygon_nft_summary(user_id: int = Depends(verify_session)):
    """
    Get a summary of all Polygon NFTs grouped by collection.
    """
    if not await polygon_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured'
        }

    # Get all Polygon wallets
    wallets = await get_all_wallets(user_id=user_id)
    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']

    summary = await polygon_service.get_nft_summary(polygon_wallets)

    # Get MATIC price for USD conversion
    matic_price = await pricing_service.get_price('MATIC')

    # Add USD values
    summary['total_value_usd'] = summary['total_value_matic'] * matic_price
    summary['matic_price'] = matic_price
    summary['configured'] = True

    # Add USD values to collections
    for collection in summary['collections']:
        collection['total_value_usd'] = collection['total_value_matic'] * matic_price
        if collection.get('floor_price_matic'):
            collection['floor_price_usd'] = collection['floor_price_matic'] * matic_price

    # Sort collections by value (highest first)
    summary['collections'].sort(key=lambda x: x.get('total_value_usd', 0), reverse=True)

    return summary


@router.post("/polygon/refresh")
async def refresh_polygon_nfts(user_id: int = Depends(verify_session)):
    """Force refresh all Polygon NFT data."""
    if not await polygon_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured'
        }

    # Get all Polygon wallets
    wallets = await get_all_wallets(user_id=user_id)
    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']

    polygon_service.clear_cache()
    all_nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=True)

    return {
        'message': f'Refreshed {len(all_nfts)} Polygon NFTs',
        'count': len(all_nfts)
    }


@router.get("/polygon/status")
async def get_polygon_nft_status():
    """Get Polygon NFT service status including API configuration."""
    return polygon_service.get_status()


# ============================================================================
# BASE NFT ENDPOINTS
# ============================================================================

@router.get("/base")
async def get_base_nfts(user_id: int = Depends(verify_session), force_refresh: bool = False):
    """
    Get all NFTs from Base wallets.
    """
    if not await base_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured for Base NFTs',
            'nfts': [],
            'total_count': 0,
            'total_value_usd': 0
        }

    # Get Base wallets
    wallets = await get_all_wallets(user_id=user_id)
    base_wallets = [w for w in wallets if w['blockchain'] == 'base']

    if not base_wallets:
        return {
            'configured': True,
            'nfts': [],
            'total_count': 0,
            'total_value_usd': 0,
            'message': 'No Base wallets found'
        }

    all_nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=force_refresh)

    # Get ETH price for value calculation
    eth_price = await pricing_service.get_price('ETH')

    # Add USD values to NFTs
    total_value_usd = 0
    for nft in all_nfts:
        floor_eth = nft['collection'].get('floor_price_eth', 0) or 0
        nft['floor_price_usd'] = floor_eth * eth_price
        total_value_usd += nft['floor_price_usd']

    return {
        'configured': True,
        'nfts': all_nfts,
        'total_count': len(all_nfts),
        'total_value_usd': total_value_usd,
        'eth_price': eth_price,
        'last_updated': base_service.last_nft_refresh.isoformat() if base_service.last_nft_refresh else None
    }


@router.get("/base/summary")
async def get_base_nft_summary(user_id: int = Depends(verify_session)):
    """Get Base NFT summary grouped by collection."""
    if not await base_service.is_configured():
        return {
            'configured': False,
            'message': 'Alchemy API key not configured'
        }

    wallets = await get_all_wallets(user_id=user_id)
    base_wallets = [w for w in wallets if w['blockchain'] == 'base']

    summary = await base_service.get_nft_summary(base_wallets)

    # Get ETH price for USD conversion
    eth_price = await pricing_service.get_price('ETH')
    total_value_usd = summary.get('total_value_eth', 0) * eth_price

    # Add USD values to collections
    for collection in summary.get('collections', []):
        collection['total_value_usd'] = collection.get('total_value_eth', 0) * eth_price

    summary['total_value_usd'] = total_value_usd
    summary['eth_price'] = eth_price
    summary['configured'] = True

    return summary


@router.post("/base/refresh")
async def refresh_base_nfts(user_id: int = Depends(verify_session)):
    """Force refresh Base NFTs from API."""
    if not await base_service.is_configured():
        return {'success': False, 'message': 'Alchemy API key not configured'}

    wallets = await get_all_wallets(user_id=user_id)
    base_wallets = [w for w in wallets if w['blockchain'] == 'base']

    base_service.clear_cache()
    all_nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=True)

    return {
        'success': True,
        'nft_count': len(all_nfts),
        'last_updated': base_service.last_nft_refresh.isoformat() if base_service.last_nft_refresh else None
    }


@router.get("/base/status")
async def get_base_nft_status():
    """Get Base NFT service status including API configuration."""
    return base_service.get_status()


# ============================================================================
# COMBINED / MULTI-CHAIN ENDPOINTS
# ============================================================================

@router.get("/all/summary")
async def get_all_chains_nft_summary(user_id: int = Depends(verify_session)):
    """
    Get a combined summary of NFTs across all chains (Cardano + Ethereum + Solana + Polygon + Base).
    Returns totals and per-chain breakdown.
    """
    # Get prices in parallel
    ada_price, eth_price, sol_price, matic_price = await asyncio.gather(
        pricing_service.get_price('ADA'),
        pricing_service.get_price('ETH'),
        pricing_service.get_price('SOL'),
        pricing_service.get_price('MATIC'),
    )
    # Base uses ETH as native token, so same price

    # Pre-fetch wallets and config checks in parallel
    wallets, eth_configured, sol_configured, poly_configured, base_configured = await asyncio.gather(
        get_all_wallets(user_id=user_id),
        ethereum_nft_service.is_configured(),
        solana_nft_service.is_configured(),
        polygon_service.is_configured(),
        base_service.is_configured(),
    )
    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
    base_wallets = [w for w in wallets if w['blockchain'] == 'base']

    # Fetch all chain summaries in parallel
    async def _summary_cardano():
        data = {'chain': 'cardano', 'total_count': 0, 'total_value_usd': 0, 'configured': True}
        try:
            s = await nft_service.get_nft_summary(user_id=user_id)
            data['total_count'] = s.get('total_nfts', 0)
            data['total_value_usd'] = s.get('total_value_ada', 0) * ada_price
        except Exception as e:
            data['error'] = str(e)
        return 'cardano', data

    async def _summary_ethereum():
        data = {'chain': 'ethereum', 'total_count': 0, 'total_value_usd': 0, 'configured': eth_configured}
        if eth_configured:
            try:
                s = await ethereum_nft_service.get_nft_summary(user_id=user_id)
                data['total_count'] = s.get('total_nfts', 0)
                data['total_value_usd'] = s.get('total_value_eth', 0) * eth_price
            except Exception as e:
                data['error'] = str(e)
        return 'ethereum', data

    async def _summary_solana():
        data = {'chain': 'solana', 'total_count': 0, 'total_value_usd': 0, 'configured': sol_configured}
        if sol_configured:
            try:
                s = await solana_nft_service.get_nft_summary(user_id=user_id)
                data['total_count'] = s.get('total_nfts', 0)
                data['total_value_usd'] = s.get('total_value_sol', 0) * sol_price
            except Exception as e:
                data['error'] = str(e)
        return 'solana', data

    async def _summary_polygon():
        data = {'chain': 'polygon', 'total_count': 0, 'total_value_usd': 0, 'configured': poly_configured}
        if poly_configured:
            try:
                s = await polygon_service.get_nft_summary(polygon_wallets)
                data['total_count'] = s.get('total_nfts', 0)
                data['total_value_usd'] = s.get('total_value_matic', 0) * matic_price
            except Exception as e:
                data['error'] = str(e)
        return 'polygon', data

    async def _summary_base():
        data = {'chain': 'base', 'total_count': 0, 'total_value_usd': 0, 'configured': base_configured}
        if base_configured:
            try:
                s = await base_service.get_nft_summary(base_wallets)
                data['total_count'] = s.get('total_nfts', 0)
                data['total_value_usd'] = s.get('total_value_eth', 0) * eth_price
            except Exception as e:
                data['error'] = str(e)
        return 'base', data

    results = await asyncio.gather(
        _summary_cardano(), _summary_ethereum(), _summary_solana(),
        _summary_polygon(), _summary_base()
    )
    chain_map = {chain: data for chain, data in results}
    cardano_data = chain_map['cardano']
    ethereum_data = chain_map['ethereum']
    solana_data = chain_map['solana']
    polygon_data = chain_map['polygon']
    base_data = chain_map['base']

    # Combined totals
    total_count = (
        cardano_data['total_count'] +
        ethereum_data['total_count'] +
        solana_data['total_count'] +
        polygon_data['total_count'] +
        base_data['total_count']
    )
    total_value_usd = (
        cardano_data['total_value_usd'] +
        ethereum_data['total_value_usd'] +
        solana_data['total_value_usd'] +
        polygon_data['total_value_usd'] +
        base_data['total_value_usd']
    )

    return {
        'total_count': total_count,
        'total_value_usd': total_value_usd,
        'chains': {
            'cardano': cardano_data,
            'ethereum': ethereum_data,
            'solana': solana_data,
            'polygon': polygon_data,
            'base': base_data
        },
        'prices': {
            'ada': ada_price,
            'eth': eth_price,
            'sol': sol_price,
            'matic': matic_price
        }
    }


@router.post("/prices/sync")
async def sync_prices_from_service(user_id: int = Depends(verify_session)):
    """
    Sync Cardano NFT floor prices from the external Cardano NFT Price Service.
    Updates local price cache with data from the dedicated price service.
    """
    if not nft_price_client.is_configured():
        return {
            'success': False,
            'message': 'Cardano NFT Price Service not configured. Set NFT_PRICE_SERVICE_URL environment variable.',
            'synced': 0
        }

    if not await nft_price_client.is_available():
        return {
            'success': False,
            'message': 'Cardano NFT Price Service is not available',
            'synced': 0
        }

    # Get all unique policy IDs from our NFTs
    all_nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
    policy_ids = list(set(nft.get('policy_id') for nft in all_nfts if nft.get('policy_id')))

    if not policy_ids:
        return {
            'success': True,
            'message': 'No NFT collections to sync',
            'synced': 0
        }

    # Fetch prices from the external service
    floor_prices = await nft_price_client.get_floor_prices(policy_ids)

    if not floor_prices:
        return {
            'success': False,
            'message': 'No prices returned from service',
            'synced': 0
        }

    # Update local cache with the fetched prices
    synced_count = 0
    for policy_id, price in floor_prices.items():
        if price is not None:
            await nft_service.update_floor_price_cache(policy_id, price)
            synced_count += 1

    # Clear and reload NFT data to use new prices
    nft_service.clear_cache()

    return {
        'success': True,
        'message': f'Synced {synced_count} Cardano floor prices',
        'synced': synced_count,
        'total_collections': len(policy_ids),
        'service_url': nft_price_client.service_url
    }


@router.get("/prices/service-status")
async def get_external_price_service_status():
    """Get status of the external Cardano NFT Price Service."""
    configured = await nft_price_client.is_configured()

    if not configured:
        return {
            'configured': False,
            'message': 'Cardano NFT Price Service URL not set'
        }

    available = await nft_price_client.is_available()
    status = await nft_price_client.get_service_status() if available else None
    service_url = await nft_price_client._get_service_url()

    return {
        'configured': True,
        'available': available,
        'service_url': service_url,
        'service_status': status
    }


# ============================================================================
# NFT IMAGE CACHING ENDPOINTS
# ============================================================================

class ImageCacheConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    max_image_size_bytes: Optional[int] = None
    generate_thumbnails: Optional[bool] = None
    thumbnail_size: Optional[int] = None
    auto_fetch_on_nft_load: Optional[bool] = None
    enabled_chains: Optional[List[str]] = None


class ImageCacheRequest(BaseModel):
    asset_id: str
    blockchain: str
    image_url: str


class BatchImageCacheRequest(BaseModel):
    nfts: List[dict]
    blockchain: str
    max_concurrent: Optional[int] = 5


@router.get("/images/config")
async def get_image_cache_config():
    """
    Get NFT image cache configuration and status.
    Returns current settings, statistics, and database info.
    """
    return await nft_image_service.get_config()


@router.post("/images/config")
async def update_image_cache_config(config: ImageCacheConfigUpdate):
    """
    Update NFT image cache configuration.
    Use 'enabled: true' to turn on image caching.
    """
    updates = {k: v for k, v in config.dict().items() if v is not None}
    if not updates:
        return await nft_image_service.get_config()

    return await nft_image_service.update_config(updates)


@router.post("/images/enable")
async def enable_image_cache():
    """Enable NFT image caching."""
    await nft_image_service.set_enabled(True)
    return {'enabled': True, 'message': 'NFT image caching enabled'}


@router.post("/images/disable")
async def disable_image_cache():
    """Disable NFT image caching."""
    await nft_image_service.set_enabled(False)
    return {'enabled': False, 'message': 'NFT image caching disabled'}


@router.get("/images/stats")
async def get_image_cache_stats():
    """Get detailed statistics about the image cache."""
    return await nft_image_service.get_stats()


@router.get("/images/{blockchain}/{asset_id}")
async def get_cached_image(blockchain: str, asset_id: str):
    """
    Get a cached NFT image.
    Returns the raw image data with appropriate content-type.
    """
    image_data, image_format = await nft_image_service.get_image(asset_id, blockchain)

    if not image_data:
        raise HTTPException(status_code=404, detail="Image not cached")

    # Map format to content-type
    content_types = {
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'svg': 'image/svg+xml'
    }
    content_type = content_types.get(image_format, 'application/octet-stream')

    return Response(
        content=image_data,
        media_type=content_type,
        headers={'Cache-Control': 'max-age=86400'}  # Cache for 1 day
    )


@router.get("/images/{blockchain}/{asset_id}/thumbnail")
async def get_cached_thumbnail(blockchain: str, asset_id: str):
    """
    Get a cached NFT thumbnail (150x150 JPEG).
    Falls back to full image if thumbnail not available.
    """
    # Try thumbnail first
    thumbnail_data, image_format = await nft_image_service.get_thumbnail(asset_id, blockchain)

    if thumbnail_data:
        return Response(
            content=thumbnail_data,
            media_type='image/jpeg',
            headers={'Cache-Control': 'max-age=86400'}
        )

    # Fall back to full image
    image_data, image_format = await nft_image_service.get_image(asset_id, blockchain)

    if not image_data:
        raise HTTPException(status_code=404, detail="Image not cached")

    content_types = {
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'svg': 'image/svg+xml'
    }
    content_type = content_types.get(image_format, 'application/octet-stream')

    return Response(
        content=image_data,
        media_type=content_type,
        headers={'Cache-Control': 'max-age=86400'}
    )


@router.get("/images/{blockchain}/{asset_id}/info")
async def get_cached_image_info(blockchain: str, asset_id: str):
    """Get metadata about a cached image (without returning the image data)."""
    from nft_image_database import get_nft_image

    image_info = await get_nft_image(asset_id, blockchain)

    if not image_info:
        raise HTTPException(status_code=404, detail="Image not found in cache")

    # Remove binary data from response
    return {
        'asset_id': image_info['asset_id'],
        'blockchain': image_info['blockchain'],
        'image_url': image_info['image_url'],
        'image_format': image_info['image_format'],
        'image_size': image_info['image_size'],
        'width': image_info['width'],
        'height': image_info['height'],
        'has_thumbnail': image_info['thumbnail_data'] is not None,
        'fetch_status': image_info['fetch_status'],
        'error_message': image_info['error_message'],
        'fetched_at': image_info['fetched_at']
    }


@router.post("/images/cache")
async def cache_single_image(request: ImageCacheRequest):
    """
    Cache a single NFT image.
    Fetches the image from the URL and stores it in the database.
    """
    result = await nft_image_service.cache_image(
        asset_id=request.asset_id,
        blockchain=request.blockchain,
        image_url=request.image_url
    )
    return result


@router.post("/images/cache/batch")
async def cache_batch_images(request: BatchImageCacheRequest):
    """
    Cache multiple NFT images in parallel.
    Each NFT dict should have 'asset_id' (or 'token_id'/'unit') and 'image_url' (or 'image') keys.
    """
    result = await nft_image_service.batch_cache_images(
        nfts=request.nfts,
        blockchain=request.blockchain,
        max_concurrent=request.max_concurrent
    )
    return result


@router.post("/images/process-pending")
async def process_pending_images(
    blockchain: Optional[str] = None,
    limit: int = 50,
    max_concurrent: int = 5
):
    """
    Process pending images in the queue.
    Fetches images that were registered but not yet downloaded.
    """
    result = await nft_image_service.process_pending(
        blockchain=blockchain,
        limit=limit,
        max_concurrent=max_concurrent
    )
    return result


@router.get("/images/pending")
async def get_pending_images(blockchain: Optional[str] = None, limit: int = 50):
    """Get list of images that are pending fetch."""
    pending = await nft_image_service.get_pending(blockchain, limit)
    return {
        'pending': pending,
        'count': len(pending)
    }


@router.delete("/images/clear")
async def clear_image_cache(blockchain: Optional[str] = None):
    """
    Clear the image cache.
    Optionally filter by blockchain to only clear images from one chain.
    """
    deleted = await nft_image_service.clear_cache(blockchain)
    return {
        'deleted': deleted,
        'message': f'Cleared {deleted} cached images' + (f' for {blockchain}' if blockchain else '')
    }


@router.get("/images/check/{blockchain}/{asset_id}")
async def check_image_cached(blockchain: str, asset_id: str):
    """Check if an NFT image is cached."""
    cached = await nft_image_service.has_image(asset_id, blockchain)
    return {
        'asset_id': asset_id,
        'blockchain': blockchain,
        'cached': cached
    }


# ============================================================================
# NFT WALL ENDPOINTS - For displaying NFTs with cached images
# ============================================================================

def _get_nft_image_url(nft: dict) -> Optional[str]:
    """Extract image URL from NFT using various key names."""
    # Check common image URL keys
    if nft.get('image'):
        return nft.get('image')
    if nft.get('image_url'):
        return nft.get('image_url')
    if nft.get('thumbnail'):
        return nft.get('thumbnail')
    # Check Alchemy media array format
    media = nft.get('media')
    if isinstance(media, list) and media:
        return media[0].get('gateway')
    return None


@router.get("/wall/status")
async def get_nft_wall_status(user_id: int = Depends(verify_session)):
    """
    Get NFT wall status showing total NFTs vs cached images per chain.
    Useful for tracking image collection progress.
    """
    # Check cache first (60 second TTL for status)
    from database import get_cache, set_cache
    status_cache_key = "nft_wall_status"
    cached_response = await get_cache(status_cache_key, user_id=user_id)
    if cached_response:
        return cached_response

    # Get image cache stats
    image_stats = await nft_image_service.get_stats()
    by_chain = image_stats.get('by_chain', {})

    # Pre-fetch wallets once (needed for polygon and base)
    wallets = await get_all_wallets(user_id=user_id)
    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
    base_wallets = [w for w in wallets if w['blockchain'] == 'base']

    # Check which chains are configured (all async, run in parallel)
    eth_configured, sol_configured, poly_configured, base_configured = await asyncio.gather(
        ethereum_nft_service.is_configured(),
        solana_nft_service.is_configured(),
        polygon_service.is_configured(),
        base_service.is_configured(),
    )

    # Helper to build chain stats from fetched NFT list
    def _chain_stats(chain_name, nfts):
        return {
            'total_nfts': len(nfts),
            'with_images': sum(1 for n in nfts if _get_nft_image_url(n)),
            'cached': by_chain.get(chain_name, {}).get('fetched', 0),
            'pending': by_chain.get(chain_name, {}).get('pending', 0),
            'failed': by_chain.get(chain_name, {}).get('failed', 0)
        }

    _empty = {'total_nfts': 0, 'with_images': 0, 'cached': 0, 'pending': 0, 'failed': 0}

    # Build parallel fetch tasks for all configured chains
    async def _fetch_cardano():
        try:
            nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
            return 'cardano', _chain_stats('cardano', nfts)
        except Exception:
            return 'cardano', _empty.copy()

    async def _fetch_ethereum():
        if not eth_configured:
            return 'ethereum', {'configured': False}
        try:
            nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
            return 'ethereum', _chain_stats('ethereum', nfts)
        except Exception:
            return 'ethereum', _empty.copy()

    async def _fetch_solana():
        if not sol_configured:
            return 'solana', {'configured': False}
        try:
            nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
            return 'solana', _chain_stats('solana', nfts)
        except Exception:
            return 'solana', _empty.copy()

    async def _fetch_polygon():
        if not poly_configured:
            return 'polygon', {'configured': False}
        try:
            nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
            return 'polygon', _chain_stats('polygon', nfts)
        except Exception:
            return 'polygon', _empty.copy()

    async def _fetch_base():
        if not base_configured:
            return 'base', {'configured': False}
        try:
            nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)
            return 'base', _chain_stats('base', nfts)
        except Exception:
            return 'base', _empty.copy()

    # Fetch all chains in parallel
    results = await asyncio.gather(
        _fetch_cardano(), _fetch_ethereum(), _fetch_solana(),
        _fetch_polygon(), _fetch_base()
    )
    chain_totals = {chain: data for chain, data in results}

    # Calculate totals
    total_nfts = sum(c.get('total_nfts', 0) for c in chain_totals.values() if isinstance(c, dict))
    total_with_images = sum(c.get('with_images', 0) for c in chain_totals.values() if isinstance(c, dict))
    total_cached = sum(c.get('cached', 0) for c in chain_totals.values() if isinstance(c, dict))

    response = {
        'enabled': await nft_image_service.is_enabled(),
        'total_nfts': total_nfts,
        'total_with_images': total_with_images,
        'total_cached': total_cached,
        'cache_percentage': round(total_cached / total_with_images * 100, 1) if total_with_images > 0 else 0,
        'by_chain': chain_totals,
        'database_size_mb': image_stats.get('database_size_mb', 0)
    }
    # Cache for 60 seconds
    await set_cache(status_cache_key, response, ttl_seconds=60, user_id=user_id)
    return response


@router.post("/wall/cache-all")
async def cache_all_nft_images(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = None,
    max_concurrent: int = 20,
    limit: int = 200,
    chain_parallelism: int = 5,
    background: bool = True
):
    """
    Cache images for all NFTs from the dashboard with parallel chain processing.
    Only caches NFTs that have image URLs and aren't already cached.

    Args:
        blockchain: Optional chain to limit caching to
        max_concurrent: Max concurrent image fetches per chain (default: 20)
        limit: Max images to cache in this batch per chain (default: 200)
        chain_parallelism: Max chains to process in parallel (default: 5)
        background: Run in background and return immediately (default: True)
    """
    chains_to_process = [blockchain] if blockchain else ['cardano', 'ethereum', 'solana', 'polygon', 'base']

    # Create semaphore for chain-level concurrency
    chain_semaphore = asyncio.Semaphore(chain_parallelism)

    async def process_chain(chain: str):
        """Process a single blockchain's NFT caching."""
        async with chain_semaphore:
            nfts_to_cache = []

            try:
                if chain == 'cardano':
                    nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)

                    # For Cardano, we need to fetch image URLs from Blockfrost metadata
                    # Only fetch for NFTs that don't already have image URLs
                    nfts_needing_images = [n for n in nfts if not _get_nft_image_url(n)]
                    if nfts_needing_images:
                        # Batch fetch image URLs (limit to avoid overwhelming the API)
                        batch_to_fetch = nfts_needing_images[:limit]
                        image_urls = await nft_service.batch_fetch_image_urls(batch_to_fetch, max_concurrent=10)

                        # Update the NFTs with fetched image URLs
                        for nft in nfts:
                            asset_id = nft.get('asset_id')
                            if asset_id in image_urls:
                                nft['image'] = image_urls[asset_id]

                    # Now collect NFTs with images
                    for nft in nfts:
                        image_url = _get_nft_image_url(nft)
                        if image_url:
                            nfts_to_cache.append({
                                'asset_id': nft.get('unit') or nft.get('asset_id'),
                                'image_url': image_url
                            })

                elif chain == 'ethereum' and ethereum_nft_service.is_configured():
                    nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
                    for nft in nfts:
                        if _get_nft_image_url(nft):
                            nfts_to_cache.append({
                                'asset_id': f"{nft.get('contract_address')}_{nft.get('token_id')}",
                                'image_url': _get_nft_image_url(nft)
                            })

                elif chain == 'solana' and await solana_nft_service.is_configured():
                    nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
                    for nft in nfts:
                        if _get_nft_image_url(nft):
                            nfts_to_cache.append({
                                'asset_id': nft.get('mint') or nft.get('asset_id'),
                                'image_url': _get_nft_image_url(nft)
                            })

                elif chain == 'polygon' and await polygon_service.is_configured():
                    wallets = await get_all_wallets(user_id=user_id)
                    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
                    nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
                    for nft in nfts:
                        if _get_nft_image_url(nft):
                            nfts_to_cache.append({
                                'asset_id': f"{nft.get('contract_address')}_{nft.get('token_id')}",
                                'image_url': _get_nft_image_url(nft)
                            })

                elif chain == 'base' and await base_service.is_configured():
                    wallets = await get_all_wallets(user_id=user_id)
                    base_wallets = [w for w in wallets if w['blockchain'] == 'base']
                    nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)
                    for nft in nfts:
                        if _get_nft_image_url(nft):
                            nfts_to_cache.append({
                                'asset_id': f"{nft.get('contract_address')}_{nft.get('token_id')}",
                                'image_url': _get_nft_image_url(nft)
                            })

                # Limit the batch size
                nfts_to_cache = nfts_to_cache[:limit]

                if nfts_to_cache:
                    logger.info(f"[{chain}] Caching {len(nfts_to_cache)} images with {max_concurrent} concurrent downloads")
                    batch_result = await nft_image_service.batch_cache_images(
                        nfts=nfts_to_cache,
                        blockchain=chain,
                        max_concurrent=max_concurrent
                    )
                    return {
                        'chain': chain,
                        'fetched': batch_result.get('fetched', 0),
                        'failed': batch_result.get('failed', 0),
                        'skipped': batch_result.get('skipped', 0)
                    }
                else:
                    return {
                        'chain': chain,
                        'fetched': 0,
                        'failed': 0,
                        'skipped': 0
                    }

            except Exception as e:
                logger.error(f"Error processing chain {chain}: {e}")
                return {
                    'chain': chain,
                    'error': str(e)
                }

    # Background task wrapper
    async def run_caching_task():
        """Execute the caching and update the task status."""
        task_id = f"{user_id}_{blockchain or 'all'}"
        try:
            background_cache_tasks[task_id] = {
                'status': 'running',
                'progress': 'Starting...',
                'user_id': user_id
            }

            # Process all chains in parallel
            logger.info(f"Starting parallel NFT caching for chains: {chains_to_process}")
            chain_results = await asyncio.gather(*[process_chain(chain) for chain in chains_to_process])

            # Aggregate results
            results = {
                'chains_processed': chain_results,
                'total_cached': sum(r.get('fetched', 0) for r in chain_results),
                'total_failed': sum(r.get('failed', 0) for r in chain_results),
                'total_skipped': sum(r.get('skipped', 0) for r in chain_results)
            }

            logger.info(f"NFT caching complete: {results['total_cached']} cached, {results['total_failed']} failed, {results['total_skipped']} skipped")

            # Update task status
            background_cache_tasks[task_id] = {
                'status': 'completed',
                'results': results,
                'user_id': user_id
            }

            return results

        except Exception as e:
            logger.error(f"Background caching error: {e}")
            background_cache_tasks[task_id] = {
                'status': 'failed',
                'error': str(e),
                'user_id': user_id
            }
            raise

    if background:
        # Start background task and return immediately
        task_id = f"{user_id}_{blockchain or 'all'}"
        asyncio.create_task(run_caching_task())
        return {
            'status': 'started',
            'message': 'Image caching started in background. You can leave this page - the process will continue.',
            'task_id': task_id,
            'background': True
        }
    else:
        # Run synchronously and wait for completion
        return await run_caching_task()


@router.get("/wall/cache-status")
async def get_cache_task_status(user_id: int = Depends(verify_session), blockchain: Optional[str] = None):
    """Check the status of a background caching task."""
    task_id = f"{user_id}_{blockchain or 'all'}"

    if task_id not in background_cache_tasks:
        return {'status': 'not_found', 'message': 'No caching task found'}

    task = background_cache_tasks[task_id]

    # Verify user owns this task
    if task.get('user_id') != user_id:
        raise HTTPException(403, "Not authorized to view this task")

    return task


@router.get("/wall/nfts")
async def get_nfts_with_images(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = None,
    group_by_collection: bool = False
):
    """
    Get all NFTs that have cached images for the NFT Wall display.
    Only returns NFTs from the dashboard (non-spam) that have successfully cached images.

    Args:
        blockchain: Optional chain filter. If not provided, returns all chains.
        group_by_collection: If True, groups NFTs by collection with count badges.
    """
    # Check cache first (30 second TTL for wall display)
    from database import get_cache, set_cache
    cache_key = f"nft_wall_{blockchain or 'all'}_{group_by_collection}"
    cached_response = await get_cache(cache_key, user_id=user_id)
    if cached_response:
        return cached_response

    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo NFTs for wall display
        demo_nfts = await demo_nft_service.get_all_nfts(force_refresh=False)

        # Map collections to blockchains for variety
        collection_chain_map = {
            'Clay Nation': ('cardano', 'ADA', 0.33),
            'Ape Society': ('ethereum', 'ETH', 2700),
            'Bored Ape Yacht Club': ('ethereum', 'ETH', 2700),
            'Solana Monkey Business': ('solana', 'SOL', 115)
        }

        # Format for wall display with mixed blockchains
        formatted_nfts = []
        for nft in demo_nfts:
            collection = nft['collection_name']
            blockchain, symbol, price_conversion = collection_chain_map.get(collection, ('cardano', 'ADA', 0.33))

            # Convert ADA price to native currency
            floor_price = nft['price_ada']
            if blockchain == 'ethereum':
                floor_price = floor_price * 0.33 / 2700  # Convert ADA to ETH
            elif blockchain == 'solana':
                floor_price = floor_price * 0.33 / 115   # Convert ADA to SOL

            formatted_nfts.append({
                'asset_id': nft['asset_id'],
                'blockchain': blockchain,
                'name': nft['asset_name'],
                'collection': collection,
                'image_url': nft['image'],  # SVG path
                'thumbnail_url': nft['image'],  # Same for demo
                'floor_price': floor_price,
                'floor_price_usd': nft['price_ada'] * 0.33,  # Keep USD consistent
                'native_symbol': symbol,
                'image_info': {
                    'format': 'svg',
                    'width': 400,
                    'height': 400
                }
            })

        # Group by chain for summary (simple counts like normal mode)
        by_chain = {}
        for nft in formatted_nfts:
            chain = nft['blockchain']
            by_chain[chain] = by_chain.get(chain, 0) + 1

        prices = {
            'ada': 0.33,
            'eth': 2700,
            'sol': 115,
            'matic': 0.11
        }

        response = {
            'nfts': formatted_nfts,
            'total_count': len(formatted_nfts),
            'by_chain': by_chain,
            'prices': prices,
            'demo_mode': True
        }
        # Cache demo mode response for 5 minutes
        await set_cache(cache_key, response, ttl_seconds=300, user_id=user_id)
        return response

    # Normal mode for real users
    from nft_image_database import get_nft_image_db

    chains_to_fetch = [blockchain] if blockchain else ['cardano', 'ethereum', 'solana', 'polygon', 'base']

    # Get cached image asset IDs for quick lookup
    import aiosqlite
    from config import NFT_IMAGE_DB_PATH
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        cursor = await db.execute("""
            SELECT asset_id, blockchain, image_format, width, height
            FROM nft_images
            WHERE fetch_status = 'fetched' AND image_data IS NOT NULL
        """)
        rows = await cursor.fetchall()
        cached_images = {}
        for row in rows:
            key = f"{row[1]}:{row[0]}"  # blockchain:asset_id
            cached_images[key] = {
                'format': row[2],
                'width': row[3],
                'height': row[4]
            }

    # Get prices in parallel
    price_ada, price_eth, price_sol, price_matic = await asyncio.gather(
        pricing_service.get_price('ADA'),
        pricing_service.get_price('ETH'),
        pricing_service.get_price('SOL'),
        pricing_service.get_price('MATIC'),
    )
    prices = {'ada': price_ada, 'eth': price_eth, 'sol': price_sol, 'matic': price_matic}

    # Pre-fetch wallets once (needed for polygon/base)
    wallets = await get_all_wallets(user_id=user_id)
    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
    base_wallets = [w for w in wallets if w['blockchain'] == 'base']

    # Check configured status for async services
    eth_configured = ethereum_nft_service.is_configured()  # sync
    sol_configured, poly_configured, base_configured = await asyncio.gather(
        solana_nft_service.is_configured(),
        polygon_service.is_configured(),
        base_service.is_configured(),
    )

    # Per-chain fetch helpers that return a list of formatted NFTs
    async def _wall_cardano():
        nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
        result = []
        for nft in nfts:
            asset_id = nft.get('unit') or nft.get('asset_id')
            key = f"cardano:{asset_id}"
            if key in cached_images:
                policy_id = asset_id[:56] if len(asset_id) >= 56 else asset_id
                result.append({
                    'asset_id': asset_id, 'blockchain': 'cardano',
                    'name': nft.get('name', 'Unknown'),
                    'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                    'policy_id': policy_id, 'collection_id': policy_id,
                    'image_url': f"/nfts/images/cardano/{asset_id}",
                    'thumbnail_url': f"/nfts/images/cardano/{asset_id}/thumbnail",
                    'floor_price': nft.get('price_ada'),
                    'floor_price_usd': (nft.get('price_ada') or 0) * prices['ada'],
                    'native_symbol': 'ADA', 'image_info': cached_images[key]
                })
        return result

    async def _wall_ethereum():
        if not eth_configured:
            return []
        nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
        result = []
        for nft in nfts:
            asset_id = f"{nft.get('contract_address')}_{nft.get('token_id')}"
            key = f"ethereum:{asset_id}"
            if key in cached_images:
                floor_eth = nft.get('collection', {}).get('floor_price_eth', 0) or 0
                result.append({
                    'asset_id': asset_id, 'blockchain': 'ethereum',
                    'name': nft.get('name', 'Unknown'),
                    'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                    'collection_id': nft.get('contract_address'),
                    'image_url': f"/nfts/images/ethereum/{asset_id}",
                    'thumbnail_url': f"/nfts/images/ethereum/{asset_id}/thumbnail",
                    'floor_price': floor_eth, 'floor_price_usd': floor_eth * prices['eth'],
                    'native_symbol': 'ETH', 'image_info': cached_images[key]
                })
        return result

    async def _wall_solana():
        if not sol_configured:
            return []
        nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
        result = []
        for nft in nfts:
            asset_id = nft.get('mint') or nft.get('asset_id')
            key = f"solana:{asset_id}"
            if key in cached_images:
                floor_sol = nft.get('collection', {}).get('floor_price_sol', 0) or 0
                result.append({
                    'asset_id': asset_id, 'blockchain': 'solana',
                    'name': nft.get('name', 'Unknown'),
                    'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                    'image_url': f"/nfts/images/solana/{asset_id}",
                    'thumbnail_url': f"/nfts/images/solana/{asset_id}/thumbnail",
                    'floor_price': floor_sol, 'floor_price_usd': floor_sol * prices['sol'],
                    'native_symbol': 'SOL', 'image_info': cached_images[key]
                })
        return result

    async def _wall_polygon():
        if not poly_configured:
            return []
        nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
        result = []
        for nft in nfts:
            asset_id = f"{nft.get('contract_address')}_{nft.get('token_id')}"
            key = f"polygon:{asset_id}"
            if key in cached_images:
                floor_matic = nft.get('collection', {}).get('floor_price_matic', 0) or 0
                result.append({
                    'asset_id': asset_id, 'blockchain': 'polygon',
                    'name': nft.get('name', 'Unknown'),
                    'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                    'image_url': f"/nfts/images/polygon/{asset_id}",
                    'thumbnail_url': f"/nfts/images/polygon/{asset_id}/thumbnail",
                    'floor_price': floor_matic, 'floor_price_usd': floor_matic * prices['matic'],
                    'native_symbol': 'POL', 'image_info': cached_images[key]
                })
        return result

    async def _wall_base():
        if not base_configured:
            return []
        nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)
        result = []
        for nft in nfts:
            asset_id = f"{nft.get('contract_address')}_{nft.get('token_id')}"
            key = f"base:{asset_id}"
            if key in cached_images:
                floor_eth = nft.get('collection', {}).get('floor_price_eth', 0) or 0
                result.append({
                    'asset_id': asset_id, 'blockchain': 'base',
                    'name': nft.get('name', 'Unknown'),
                    'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                    'image_url': f"/nfts/images/base/{asset_id}",
                    'thumbnail_url': f"/nfts/images/base/{asset_id}/thumbnail",
                    'floor_price': floor_eth, 'floor_price_usd': floor_eth * prices['eth'],
                    'native_symbol': 'ETH', 'image_info': cached_images[key]
                })
        return result

    # Map chain names to fetch functions
    _chain_fetchers = {
        'cardano': _wall_cardano, 'ethereum': _wall_ethereum, 'solana': _wall_solana,
        'polygon': _wall_polygon, 'base': _wall_base,
    }

    # Fetch requested chains in parallel
    async def _safe_fetch(chain):
        try:
            return await _chain_fetchers[chain]()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Error fetching {chain} NFTs for wall: {e}")
            return []

    chain_results = await asyncio.gather(*[_safe_fetch(c) for c in chains_to_fetch])
    all_nfts = []
    for result in chain_results:
        all_nfts.extend(result)

    # Sort by value (highest first)
    all_nfts.sort(key=lambda x: x.get('floor_price_usd', 0), reverse=True)

    # Group by chain for summary
    by_chain = {}
    for nft in all_nfts:
        chain = nft['blockchain']
        if chain not in by_chain:
            by_chain[chain] = 0
        by_chain[chain] += 1

    # Group by collection if requested
    if group_by_collection:
        from collections import defaultdict

        collections = defaultdict(list)

        for nft in all_nfts:
            # Determine collection ID based on blockchain
            if nft['blockchain'] == 'cardano':
                # For Cardano, extract policy_id from the asset_id
                # Cardano asset_id format: policy_id (56 chars) + asset_name_hex
                # Policy ID is always the first 56 characters
                asset_id = nft['asset_id']
                policy_id = asset_id[:56] if len(asset_id) >= 56 else asset_id
                collection_key = f"{nft['blockchain']}:{policy_id}"
            elif nft['blockchain'] in ['ethereum', 'polygon', 'base']:
                # For EVM chains, extract contract address from asset_id (format: contract_tokenId)
                parts = nft['asset_id'].split('_')
                contract_address = parts[0] if parts else nft['asset_id']
                collection_key = f"{nft['blockchain']}:{contract_address}"
            else:  # solana
                # Use collection name for solana (no consistent collection ID format)
                collection_key = f"{nft['blockchain']}:{nft['collection']}"

            collections[collection_key].append(nft)

        # Convert to grouped format
        grouped_nfts = []
        for collection_key, nfts in collections.items():
            # Use the first NFT as the representative
            first_nft = nfts[0]

            # Extract collection ID from collection_key (format: blockchain:collection_id)
            parts = collection_key.split(':', 1)
            collection_id = parts[1] if len(parts) > 1 else collection_key

            grouped_nfts.append({
                'collection_key': collection_key,
                'blockchain': first_nft['blockchain'],
                'collection_name': first_nft['collection'],
                'collection_id': collection_id,  # Include the policy_id or contract address
                'count': len(nfts),
                'total_floor_price_usd': sum(n.get('floor_price_usd', 0) for n in nfts),
                'representative_nft': first_nft,
                'asset_ids': [n['asset_id'] for n in nfts]
            })

        # Sort grouped by total value
        grouped_nfts.sort(key=lambda x: x['total_floor_price_usd'], reverse=True)

        response = {
            'nfts': all_nfts,
            'grouped_nfts': grouped_nfts,
            'total_count': len(all_nfts),
            'collection_count': len(grouped_nfts),
            'by_chain': by_chain,
            'prices': prices,
            'grouped': True
        }
        # Cache for 5 minutes (NFT data changes slowly)
        await set_cache(cache_key, response, ttl_seconds=300, user_id=user_id)
        return response

    response = {
        'nfts': all_nfts,
        'total_count': len(all_nfts),
        'by_chain': by_chain,
        'prices': prices,
        'grouped': False
    }
    # Cache for 5 minutes (NFT data changes slowly)
    await set_cache(cache_key, response, ttl_seconds=300, user_id=user_id)
    return response


@router.get("/wall/details/{blockchain}/{asset_id}")
async def get_nft_wall_details(
    blockchain: str,
    asset_id: str,
    user_id: int = Depends(verify_session)
):
    """
    Get detailed NFT metadata for NFT Wall display.

    Returns:
        - Full NFT metadata (from nftcdn/nmkr for Cardano, Alchemy for Ethereum, etc.)
        - Collection information
        - Wallet owner
        - Other NFTs from same collection owned by user
        - Links to blockchain explorer
    """
    from services.nftcdn import nftcdn_service
    from services.nmkr import nmkr_service

    # Normalize blockchain
    blockchain = blockchain.lower()

    # Get basic NFT info first
    nft_data = None
    collection_id = None
    metadata = {}

    try:
        if blockchain == 'cardano':
            # Get NFT from service
            nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
            nft_data = next((n for n in nfts if (n.get('unit') or n.get('asset_id')) == asset_id), None)

            if not nft_data:
                raise HTTPException(status_code=404, detail="NFT not found")

            # Extract policy_id from asset_id (first 56 chars)
            # Cardano asset format: policy_id (56 hex chars) + asset_name_hex
            policy_id = asset_id[:56] if len(asset_id) >= 56 else asset_id
            asset_name_hex = asset_id[56:] if len(asset_id) > 56 else ''

            # Use policy_id as collection_id for grouping
            collection_id = policy_id

            logger.info(f"Cardano NFT details - asset_id: {asset_id[:20]}..., policy_id: {policy_id[:20]}..., asset_name_hex: {asset_name_hex[:20] if asset_name_hex else 'empty'}")

            # Try nftcdn
            logger.info(f"Fetching metadata from NFTCDN - policy: {policy_id[:20]}..., asset_name: {asset_name_hex[:20] if asset_name_hex else 'empty'}")
            nftcdn_metadata = await nftcdn_service.get_nft_metadata(policy_id, asset_name_hex)
            if nftcdn_metadata:
                metadata = nftcdn_metadata
                logger.info(f"✓ Got metadata from NFTCDN for {asset_id[:20]}... (keys: {list(nftcdn_metadata.keys())})")
            else:
                logger.info(f"NFTCDN returned None, trying NMKR...")
                # Fallback to nmkr
                nmkr_metadata = await nmkr_service.get_nft_metadata(policy_id, asset_name_hex)
                if nmkr_metadata:
                    metadata = nmkr_metadata
                    logger.info(f"✓ Got metadata from NMKR for {asset_id[:20]}... (keys: {list(nmkr_metadata.keys())})")
                else:
                    logger.warning(f"No metadata from NFTCDN or NMKR for {asset_id[:20]}..., trying Blockfrost...")
                    # Final fallback to Blockfrost for onchain metadata
                    try:
                        from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
                        import httpx
                        client = get_client("blockfrost", timeout=30.0)
                        response = await client.get(
                            f"{BLOCKFROST_BASE_URL}/assets/{asset_id}",
                            headers={'project_id': BLOCKFROST_API_KEY}
                        )
                        if response.status_code == 200:
                            blockfrost_data = response.json()
                            metadata = blockfrost_data  # This includes onchain_metadata
                            logger.info(f"✓ Got metadata from Blockfrost for {asset_id[:20]}...")
                        else:
                            logger.warning(f"Blockfrost returned {response.status_code} for {asset_id[:20]}...")
                    except Exception as e:
                        logger.error(f"Error fetching from Blockfrost: {e}")

        elif blockchain == 'ethereum':
            nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
            # asset_id format: "contract_address_tokenId"
            parts = asset_id.split('_')
            if len(parts) >= 2:
                contract_addr = parts[0]
                token_id = '_'.join(parts[1:])  # Handle token IDs with underscores
                nft_data = next((n for n in nfts if n.get('contract_address') == contract_addr and str(n.get('token_id')) == token_id), None)
                collection_id = contract_addr

            if not nft_data:
                raise HTTPException(status_code=404, detail="NFT not found")

            # Ethereum NFTs from Alchemy already have rich metadata
            metadata = nft_data.get('metadata', {})

        elif blockchain == 'solana':
            nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
            nft_data = next((n for n in nfts if (n.get('mint') or n.get('asset_id')) == asset_id), None)

            if not nft_data:
                raise HTTPException(status_code=404, detail="NFT not found")

            collection_id = nft_data.get('collection', {}).get('family') or nft_data.get('collection', {}).get('name')
            metadata = nft_data.get('metadata', {})

        elif blockchain == 'polygon':
            wallets = await get_all_wallets(user_id=user_id)
            polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
            nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)

            parts = asset_id.split('_')
            if len(parts) >= 2:
                contract_addr = parts[0]
                token_id = '_'.join(parts[1:])
                nft_data = next((n for n in nfts if n.get('contract_address') == contract_addr and str(n.get('token_id')) == token_id), None)
                collection_id = contract_addr

            if not nft_data:
                raise HTTPException(status_code=404, detail="NFT not found")

            metadata = nft_data.get('metadata', {})

        elif blockchain == 'base':
            wallets = await get_all_wallets(user_id=user_id)
            base_wallets = [w for w in wallets if w['blockchain'] == 'base']
            nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)

            parts = asset_id.split('_')
            if len(parts) >= 2:
                contract_addr = parts[0]
                token_id = '_'.join(parts[1:])
                nft_data = next((n for n in nfts if n.get('contract_address') == contract_addr and str(n.get('token_id')) == token_id), None)
                collection_id = contract_addr

            if not nft_data:
                raise HTTPException(status_code=404, detail="NFT not found")

            metadata = nft_data.get('metadata', {})

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported blockchain: {blockchain}")

        # Get wallet owner
        wallet_address = nft_data.get('wallet_address', 'Unknown')
        wallet_name = None

        wallets = await get_all_wallets(user_id=user_id)
        wallet = next((w for w in wallets if w['address'] == wallet_address), None)
        if wallet:
            wallet_name = wallet.get('name', wallet_address)

        # Get collection siblings (other NFTs from same collection)
        collection_siblings = []

        if blockchain == 'cardano' and collection_id:
            all_nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
            ada_price = await pricing_service.get_price('ADA')

            # Match siblings by policy_id (first 56 chars of asset_id)
            for n in all_nfts:
                n_asset_id = n.get('unit') or n.get('asset_id')
                if not n_asset_id:
                    continue

                # Extract policy_id from this NFT's asset_id
                n_policy_id = n_asset_id[:56] if len(n_asset_id) >= 56 else n_asset_id

                # Match by policy_id and exclude current NFT
                if n_policy_id == collection_id and n_asset_id != asset_id:
                    collection_siblings.append({
                        'asset_id': n_asset_id,
                        'name': n.get('name', 'Unknown'),
                        'image_url': f"/nfts/images/cardano/{n_asset_id}/thumbnail",
                        'floor_price_ada': n.get('price_ada'),
                        'floor_price_usd': (n.get('price_ada') or 0) * ada_price
                    })

            logger.info(f"Found {len(collection_siblings)} siblings for policy {collection_id[:16]}...")
        elif blockchain in ['ethereum', 'polygon', 'base'] and collection_id:
            # For EVM chains, collection_id is the contract address
            if blockchain == 'ethereum':
                all_nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
                price_key = 'eth'
            elif blockchain == 'polygon':
                wallets = await get_all_wallets(user_id=user_id)
                polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
                all_nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
                price_key = 'matic'
            else:  # base
                wallets = await get_all_wallets(user_id=user_id)
                base_wallets = [w for w in wallets if w['blockchain'] == 'base']
                all_nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)
                price_key = 'eth'

            prices = {
                'eth': await pricing_service.get_price('ETH'),
                'matic': await pricing_service.get_price('MATIC')
            }

            collection_siblings = []
            for n in all_nfts:
                if n.get('contract_address') == collection_id:
                    sibling_asset_id = f"{n.get('contract_address')}_{n.get('token_id')}"
                    if sibling_asset_id != asset_id:
                        floor_price_native = n.get('collection', {}).get(f'floor_price_{price_key}', 0) or 0
                        collection_siblings.append({
                            'asset_id': sibling_asset_id,
                            'name': n.get('name', 'Unknown'),
                            'image_url': f"/nfts/images/{blockchain}/{sibling_asset_id}/thumbnail",
                            f'floor_price_{price_key}': floor_price_native,
                            'floor_price_usd': floor_price_native * prices.get(price_key, 0)
                        })
        elif blockchain == 'solana' and collection_id:
            all_nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
            sol_price = await pricing_service.get_price('SOL')
            collection_siblings = []
            for n in all_nfts:
                n_collection_id = n.get('collection', {}).get('family') or n.get('collection', {}).get('name')
                if n_collection_id == collection_id:
                    sibling_asset_id = n.get('mint') or n.get('asset_id')
                    if sibling_asset_id != asset_id:
                        floor_price_sol = n.get('collection', {}).get('floor_price_sol', 0) or 0
                        collection_siblings.append({
                            'asset_id': sibling_asset_id,
                            'name': n.get('name', 'Unknown'),
                            'image_url': f"/nfts/images/solana/{sibling_asset_id}/thumbnail",
                            'floor_price_sol': floor_price_sol,
                            'floor_price_usd': floor_price_sol * sol_price
                        })

        # Build explorer link
        explorer_link = None
        if blockchain == 'cardano':
            explorer_link = f"https://cardanoscan.io/token/{asset_id}"
        elif blockchain == 'ethereum':
            parts = asset_id.split('_')
            if len(parts) >= 2:
                explorer_link = f"https://etherscan.io/nft/{parts[0]}/{parts[1]}"
        elif blockchain == 'solana':
            explorer_link = f"https://solscan.io/token/{asset_id}"
        elif blockchain == 'polygon':
            parts = asset_id.split('_')
            if len(parts) >= 2:
                explorer_link = f"https://polygonscan.com/nft/{parts[0]}/{parts[1]}"
        elif blockchain == 'base':
            parts = asset_id.split('_')
            if len(parts) >= 2:
                explorer_link = f"https://basescan.org/nft/{parts[0]}/{parts[1]}"

        # Extract metadata using universal metadata extractor
        from services.metadata_extractor import metadata_extractor

        unified_metadata = None
        if metadata:
            source = 'nftcdn' if blockchain == 'cardano' else blockchain
            unified_metadata = metadata_extractor.extract_unified_metadata(metadata, source)
            logger.info(f"Extracted unified metadata: collection={unified_metadata['collection_name']}, nft_name={unified_metadata['nft_name']}, edition={unified_metadata['edition_info']}, attributes={len(unified_metadata['attributes'])}")

        # Get image URLs
        high_res_image_url = None
        thumbnail_url = f"/nfts/images/{blockchain}/{asset_id}/thumbnail"

        if unified_metadata and unified_metadata['image_url']:
            high_res_image_url = unified_metadata['image_url']
            logger.info(f"✓ High-res image URL from metadata extractor: {high_res_image_url[:100]}")
        elif blockchain == 'cardano':
            logger.warning(f"No high-res image found in metadata for {asset_id[:20]}..., using cached image")

        # Use high-res image if available, otherwise fall back to cached image
        image_url = high_res_image_url if high_res_image_url else f"/nfts/images/{blockchain}/{asset_id}"

        # Extract attributes and edition info from unified metadata
        attributes = unified_metadata['attributes'] if unified_metadata else metadata.get('attributes', [])
        edition_info = unified_metadata['edition_info'] if unified_metadata else None
        creator = unified_metadata['creator'] if unified_metadata else None

        # IMPORTANT: Use extracted collection name and NFT name from metadata, not from nft_data
        extracted_collection_name = unified_metadata['collection_name'] if unified_metadata else None
        collection_name = extracted_collection_name or nft_data.get('collection', {}).get('name', 'Unknown Collection')

        extracted_nft_name = unified_metadata['nft_name'] if unified_metadata else None

        # Fallback to nft_data, but decode hex if needed
        fallback_name = nft_data.get('name', 'Unknown')
        if fallback_name and fallback_name != 'Unknown':
            # Check if name is hex-encoded (all hex chars and even length)
            if len(fallback_name) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in fallback_name):
                try:
                    decoded_name = bytes.fromhex(fallback_name).decode('utf-8', errors='ignore')
                    if decoded_name and decoded_name.isprintable():
                        fallback_name = decoded_name
                        logger.info(f"Decoded hex NFT name: {fallback_name}")
                except:
                    pass

        # For Book.io NFTs, prefer collection name as NFT name if no good NFT name found
        # (since asset names like "Macbeth0514" aren't user-friendly)
        nft_name = extracted_nft_name or fallback_name
        if nft_name == fallback_name and extracted_collection_name:
            # If we only have the decoded asset name and we know the collection, use collection name
            nft_name = extracted_collection_name

        return {
            'asset_id': asset_id,
            'blockchain': blockchain,
            'name': nft_name,  # Use extracted NFT name!
            'description': metadata.get('description', nft_data.get('description', '')),
            'image_url': image_url,
            'thumbnail_url': thumbnail_url,
            'high_res_available': high_res_image_url is not None,  # Flag for frontend
            'collection': {
                'id': collection_id,
                'name': collection_name,  # Use extracted collection name!
                'description': nft_data.get('collection', {}).get('description', ''),
                'floor_price': nft_data.get('price_ada') if blockchain == 'cardano' else nft_data.get('collection', {}).get(f'floor_price_{price_key if blockchain != "cardano" else "ada"}', 0)
            },
            'attributes': attributes,
            'properties': metadata.get('properties', {}),
            'edition_info': edition_info,  # NEW: Edition/rarity information
            'creator': creator,  # NEW: Creator/author information
            'metadata': metadata,
            'wallet': {
                'address': wallet_address,
                'name': wallet_name or wallet_address
            },
            'collection_siblings': collection_siblings[:12],  # Limit to 12 siblings
            'collection_total_count': len(collection_siblings) + 1,  # +1 for the current NFT
            'explorer_link': explorer_link
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting NFT details for {blockchain}:{asset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
