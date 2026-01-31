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

router = APIRouter(prefix="/nfts", tags=["nfts"])

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
    if not ethereum_nft_service.is_configured():
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
    if not solana_nft_service.is_configured():
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
    if not solana_nft_service.is_configured():
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
    if not solana_nft_service.is_configured():
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
    if not polygon_service.is_configured():
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
    if not polygon_service.is_configured():
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
    if not polygon_service.is_configured():
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
    if not base_service.is_configured():
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
    if not base_service.is_configured():
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
    if not base_service.is_configured():
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
    # Get prices
    ada_price = await pricing_service.get_price('ADA')
    eth_price = await pricing_service.get_price('ETH')
    sol_price = await pricing_service.get_price('SOL')
    matic_price = await pricing_service.get_price('MATIC')
    # Base uses ETH as native token, so same price

    # Cardano summary
    cardano_data = {
        'chain': 'cardano',
        'total_count': 0,
        'total_value_usd': 0,
        'configured': True
    }
    try:
        cardano_summary = await nft_service.get_nft_summary(user_id=user_id)
        cardano_data['total_count'] = cardano_summary.get('total_nfts', 0)
        cardano_data['total_value_usd'] = cardano_summary.get('total_value_ada', 0) * ada_price
    except Exception as e:
        cardano_data['error'] = str(e)

    # Ethereum summary
    ethereum_data = {
        'chain': 'ethereum',
        'total_count': 0,
        'total_value_usd': 0,
        'configured': ethereum_nft_service.is_configured()
    }
    if ethereum_data['configured']:
        try:
            eth_summary = await ethereum_nft_service.get_nft_summary(user_id=user_id)
            ethereum_data['total_count'] = eth_summary.get('total_nfts', 0)
            ethereum_data['total_value_usd'] = eth_summary.get('total_value_eth', 0) * eth_price
        except Exception as e:
            ethereum_data['error'] = str(e)

    # Solana summary
    solana_data = {
        'chain': 'solana',
        'total_count': 0,
        'total_value_usd': 0,
        'configured': solana_nft_service.is_configured()
    }
    if solana_data['configured']:
        try:
            sol_summary = await solana_nft_service.get_nft_summary(user_id=user_id)
            solana_data['total_count'] = sol_summary.get('total_nfts', 0)
            solana_data['total_value_usd'] = sol_summary.get('total_value_sol', 0) * sol_price
        except Exception as e:
            solana_data['error'] = str(e)

    # Polygon summary
    polygon_data = {
        'chain': 'polygon',
        'total_count': 0,
        'total_value_usd': 0,
        'configured': polygon_service.is_configured()
    }
    if polygon_data['configured']:
        try:
            wallets = await get_all_wallets(user_id=user_id)
            polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
            polygon_summary = await polygon_service.get_nft_summary(polygon_wallets)
            polygon_data['total_count'] = polygon_summary.get('total_nfts', 0)
            polygon_data['total_value_usd'] = polygon_summary.get('total_value_matic', 0) * matic_price
        except Exception as e:
            polygon_data['error'] = str(e)

    # Base summary (uses ETH as native token)
    base_data = {
        'chain': 'base',
        'total_count': 0,
        'total_value_usd': 0,
        'configured': base_service.is_configured()
    }
    if base_data['configured']:
        try:
            wallets = await get_all_wallets(user_id=user_id)
            base_wallets = [w for w in wallets if w['blockchain'] == 'base']
            base_summary = await base_service.get_nft_summary(base_wallets)
            base_data['total_count'] = base_summary.get('total_nfts', 0)
            base_data['total_value_usd'] = base_summary.get('total_value_eth', 0) * eth_price
        except Exception as e:
            base_data['error'] = str(e)

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
    configured = nft_price_client.is_configured()

    if not configured:
        return {
            'configured': False,
            'message': 'Cardano NFT Price Service URL not set'
        }

    available = await nft_price_client.is_available()
    status = await nft_price_client.get_service_status() if available else None

    return {
        'configured': True,
        'available': available,
        'service_url': nft_price_client.service_url,
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
    # Get image cache stats
    image_stats = await nft_image_service.get_stats()
    by_chain = image_stats.get('by_chain', {})

    # Get total NFT counts per chain from the dashboard
    chain_totals = {}

    # Cardano
    try:
        cardano_nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
        chain_totals['cardano'] = {
            'total_nfts': len(cardano_nfts),
            'with_images': sum(1 for n in cardano_nfts if _get_nft_image_url(n)),
            'cached': by_chain.get('cardano', {}).get('fetched', 0),
            'pending': by_chain.get('cardano', {}).get('pending', 0),
            'failed': by_chain.get('cardano', {}).get('failed', 0)
        }
    except Exception:
        chain_totals['cardano'] = {'total_nfts': 0, 'with_images': 0, 'cached': 0, 'pending': 0, 'failed': 0}

    # Ethereum
    if ethereum_nft_service.is_configured():
        try:
            eth_nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
            chain_totals['ethereum'] = {
                'total_nfts': len(eth_nfts),
                'with_images': sum(1 for n in eth_nfts if _get_nft_image_url(n)),
                'cached': by_chain.get('ethereum', {}).get('fetched', 0),
                'pending': by_chain.get('ethereum', {}).get('pending', 0),
                'failed': by_chain.get('ethereum', {}).get('failed', 0)
            }
        except Exception:
            chain_totals['ethereum'] = {'total_nfts': 0, 'with_images': 0, 'cached': 0, 'pending': 0, 'failed': 0}
    else:
        chain_totals['ethereum'] = {'configured': False}

    # Solana
    if solana_nft_service.is_configured():
        try:
            sol_nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
            chain_totals['solana'] = {
                'total_nfts': len(sol_nfts),
                'with_images': sum(1 for n in sol_nfts if _get_nft_image_url(n)),
                'cached': by_chain.get('solana', {}).get('fetched', 0),
                'pending': by_chain.get('solana', {}).get('pending', 0),
                'failed': by_chain.get('solana', {}).get('failed', 0)
            }
        except Exception:
            chain_totals['solana'] = {'total_nfts': 0, 'with_images': 0, 'cached': 0, 'pending': 0, 'failed': 0}
    else:
        chain_totals['solana'] = {'configured': False}

    # Polygon
    if polygon_service.is_configured():
        try:
            wallets = await get_all_wallets(user_id=user_id)
            polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
            poly_nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
            chain_totals['polygon'] = {
                'total_nfts': len(poly_nfts),
                'with_images': sum(1 for n in poly_nfts if _get_nft_image_url(n)),
                'cached': by_chain.get('polygon', {}).get('fetched', 0),
                'pending': by_chain.get('polygon', {}).get('pending', 0),
                'failed': by_chain.get('polygon', {}).get('failed', 0)
            }
        except Exception:
            chain_totals['polygon'] = {'total_nfts': 0, 'with_images': 0, 'cached': 0, 'pending': 0, 'failed': 0}
    else:
        chain_totals['polygon'] = {'configured': False}

    # Base
    if base_service.is_configured():
        try:
            wallets = await get_all_wallets(user_id=user_id)
            base_wallets = [w for w in wallets if w['blockchain'] == 'base']
            base_nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)
            chain_totals['base'] = {
                'total_nfts': len(base_nfts),
                'with_images': sum(1 for n in base_nfts if _get_nft_image_url(n)),
                'cached': by_chain.get('base', {}).get('fetched', 0),
                'pending': by_chain.get('base', {}).get('pending', 0),
                'failed': by_chain.get('base', {}).get('failed', 0)
            }
        except Exception:
            chain_totals['base'] = {'total_nfts': 0, 'with_images': 0, 'cached': 0, 'pending': 0, 'failed': 0}
    else:
        chain_totals['base'] = {'configured': False}

    # Calculate totals
    total_nfts = sum(c.get('total_nfts', 0) for c in chain_totals.values() if isinstance(c, dict))
    total_with_images = sum(c.get('with_images', 0) for c in chain_totals.values() if isinstance(c, dict))
    total_cached = sum(c.get('cached', 0) for c in chain_totals.values() if isinstance(c, dict))

    return {
        'enabled': await nft_image_service.is_enabled(),
        'total_nfts': total_nfts,
        'total_with_images': total_with_images,
        'total_cached': total_cached,
        'cache_percentage': round(total_cached / total_with_images * 100, 1) if total_with_images > 0 else 0,
        'by_chain': chain_totals,
        'database_size_mb': image_stats.get('database_size_mb', 0)
    }


@router.post("/wall/cache-all")
async def cache_all_nft_images(
    user_id: int = Depends(verify_session),
    blockchain: Optional[str] = None,
    max_concurrent: int = 20,
    limit: int = 200,
    chain_parallelism: int = 5
):
    """
    Cache images for all NFTs from the dashboard with parallel chain processing.
    Only caches NFTs that have image URLs and aren't already cached.

    Args:
        blockchain: Optional chain to limit caching to
        max_concurrent: Max concurrent image fetches per chain (default: 20)
        limit: Max images to cache in this batch per chain (default: 200)
        chain_parallelism: Max chains to process in parallel (default: 5)
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

                elif chain == 'solana' and solana_nft_service.is_configured():
                    nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
                    for nft in nfts:
                        if _get_nft_image_url(nft):
                            nfts_to_cache.append({
                                'asset_id': nft.get('mint') or nft.get('asset_id'),
                                'image_url': _get_nft_image_url(nft)
                            })

                elif chain == 'polygon' and polygon_service.is_configured():
                    wallets = await get_all_wallets(user_id=user_id)
                    polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
                    nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
                    for nft in nfts:
                        if _get_nft_image_url(nft):
                            nfts_to_cache.append({
                                'asset_id': f"{nft.get('contract_address')}_{nft.get('token_id')}",
                                'image_url': _get_nft_image_url(nft)
                            })

                elif chain == 'base' and base_service.is_configured():
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

    return results


@router.get("/wall/nfts")
async def get_nfts_with_images(user_id: int = Depends(verify_session), blockchain: Optional[str] = None):
    """
    Get all NFTs that have cached images for the NFT Wall display.
    Only returns NFTs from the dashboard (non-spam) that have successfully cached images.

    Args:
        blockchain: Optional chain filter. If not provided, returns all chains.
    """
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

        return {
            'nfts': formatted_nfts,
            'total_count': len(formatted_nfts),
            'by_chain': by_chain,
            'prices': prices,
            'demo_mode': True
        }

    # Normal mode for real users
    from nft_image_database import get_nft_image_db

    all_nfts = []
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

    # Get prices
    prices = {
        'ada': await pricing_service.get_price('ADA'),
        'eth': await pricing_service.get_price('ETH'),
        'sol': await pricing_service.get_price('SOL'),
        'matic': await pricing_service.get_price('MATIC')
    }

    for chain in chains_to_fetch:
        try:
            chain_nfts = []

            if chain == 'cardano':
                nfts = await nft_service.get_all_nfts(user_id=user_id, force_refresh=False)
                for nft in nfts:
                    asset_id = nft.get('unit') or nft.get('asset_id')
                    key = f"cardano:{asset_id}"
                    if key in cached_images:
                        chain_nfts.append({
                            'asset_id': asset_id,
                            'blockchain': 'cardano',
                            'name': nft.get('name', 'Unknown'),
                            'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                            'image_url': f"/nfts/images/cardano/{asset_id}",
                            'thumbnail_url': f"/nfts/images/cardano/{asset_id}/thumbnail",
                            'floor_price': nft.get('price_ada'),
                            'floor_price_usd': (nft.get('price_ada') or 0) * prices['ada'],
                            'native_symbol': 'ADA',
                            'image_info': cached_images[key]
                        })

            elif chain == 'ethereum' and ethereum_nft_service.is_configured():
                nfts = await ethereum_nft_service.get_all_ethereum_nfts(user_id=user_id, force_refresh=False)
                for nft in nfts:
                    asset_id = f"{nft.get('contract_address')}_{nft.get('token_id')}"
                    key = f"ethereum:{asset_id}"
                    if key in cached_images:
                        floor_eth = nft.get('collection', {}).get('floor_price_eth', 0) or 0
                        chain_nfts.append({
                            'asset_id': asset_id,
                            'blockchain': 'ethereum',
                            'name': nft.get('name', 'Unknown'),
                            'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                            'image_url': f"/nfts/images/ethereum/{asset_id}",
                            'thumbnail_url': f"/nfts/images/ethereum/{asset_id}/thumbnail",
                            'floor_price': floor_eth,
                            'floor_price_usd': floor_eth * prices['eth'],
                            'native_symbol': 'ETH',
                            'image_info': cached_images[key]
                        })

            elif chain == 'solana' and solana_nft_service.is_configured():
                nfts = await solana_nft_service.get_all_solana_nfts(user_id=user_id, force_refresh=False)
                for nft in nfts:
                    asset_id = nft.get('mint') or nft.get('asset_id')
                    key = f"solana:{asset_id}"
                    if key in cached_images:
                        floor_sol = nft.get('collection', {}).get('floor_price_sol', 0) or 0
                        chain_nfts.append({
                            'asset_id': asset_id,
                            'blockchain': 'solana',
                            'name': nft.get('name', 'Unknown'),
                            'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                            'image_url': f"/nfts/images/solana/{asset_id}",
                            'thumbnail_url': f"/nfts/images/solana/{asset_id}/thumbnail",
                            'floor_price': floor_sol,
                            'floor_price_usd': floor_sol * prices['sol'],
                            'native_symbol': 'SOL',
                            'image_info': cached_images[key]
                        })

            elif chain == 'polygon' and polygon_service.is_configured():
                wallets = await get_all_wallets(user_id=user_id)
                polygon_wallets = [w for w in wallets if w['blockchain'] == 'polygon']
                nfts = await polygon_service.get_all_polygon_nfts(polygon_wallets, force_refresh=False)
                for nft in nfts:
                    asset_id = f"{nft.get('contract_address')}_{nft.get('token_id')}"
                    key = f"polygon:{asset_id}"
                    if key in cached_images:
                        floor_matic = nft.get('collection', {}).get('floor_price_matic', 0) or 0
                        chain_nfts.append({
                            'asset_id': asset_id,
                            'blockchain': 'polygon',
                            'name': nft.get('name', 'Unknown'),
                            'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                            'image_url': f"/nfts/images/polygon/{asset_id}",
                            'thumbnail_url': f"/nfts/images/polygon/{asset_id}/thumbnail",
                            'floor_price': floor_matic,
                            'floor_price_usd': floor_matic * prices['matic'],
                            'native_symbol': 'POL',
                            'image_info': cached_images[key]
                        })

            elif chain == 'base' and base_service.is_configured():
                wallets = await get_all_wallets(user_id=user_id)
                base_wallets = [w for w in wallets if w['blockchain'] == 'base']
                nfts = await base_service.get_all_base_nfts(base_wallets, force_refresh=False)
                for nft in nfts:
                    asset_id = f"{nft.get('contract_address')}_{nft.get('token_id')}"
                    key = f"base:{asset_id}"
                    if key in cached_images:
                        floor_eth = nft.get('collection', {}).get('floor_price_eth', 0) or 0
                        chain_nfts.append({
                            'asset_id': asset_id,
                            'blockchain': 'base',
                            'name': nft.get('name', 'Unknown'),
                            'collection': nft.get('collection', {}).get('name', 'Unknown Collection'),
                            'image_url': f"/nfts/images/base/{asset_id}",
                            'thumbnail_url': f"/nfts/images/base/{asset_id}/thumbnail",
                            'floor_price': floor_eth,
                            'floor_price_usd': floor_eth * prices['eth'],
                            'native_symbol': 'ETH',
                            'image_info': cached_images[key]
                        })

            all_nfts.extend(chain_nfts)

        except Exception as e:
            # Log error but continue with other chains
            import logging
            logging.getLogger(__name__).warning(f"Error fetching {chain} NFTs for wall: {e}")

    # Sort by value (highest first)
    all_nfts.sort(key=lambda x: x.get('floor_price_usd', 0), reverse=True)

    # Group by chain for summary
    by_chain = {}
    for nft in all_nfts:
        chain = nft['blockchain']
        if chain not in by_chain:
            by_chain[chain] = 0
        by_chain[chain] += 1

    return {
        'nfts': all_nfts,
        'total_count': len(all_nfts),
        'by_chain': by_chain,
        'prices': prices
    }
