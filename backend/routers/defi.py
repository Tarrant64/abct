"""
DeFi Tracking API Endpoints

Provides endpoints for analyzing Cardano DeFi positions.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.defi import defi_service
from services.demo_defi_service import demo_defi_service
from database import get_all_wallets, get_cache, set_cache, get_username_by_user_id
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session
from config import CACHE_TTL_COLD

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/defi", tags=["defi"])

# Cache TTL in seconds - refresh daily (DeFi positions don't change that frequently)
STAKING_CACHE_TTL = CACHE_TTL_COLD  # 24 hours
DEFI_SUMMARY_CACHE_TTL = CACHE_TTL_COLD  # 24 hours


@router.get("/protocols")
async def list_supported_protocols(user_id: int = Depends(verify_session)):
    """List all supported DeFi protocols."""
    protocols = defi_service.get_supported_protocols()
    return {
        "protocols": protocols,
        "count": len(protocols)
    }


@router.get("/protocol/{protocol_name}")
async def get_protocol_info(protocol_name: str, user_id: int = Depends(verify_session)):
    """Get information about a specific DeFi protocol."""
    info = await defi_service.get_protocol_info(protocol_name)
    if not info['tokens']:
        raise HTTPException(status_code=404, detail=f"Protocol '{protocol_name}' not found")
    return info


@router.get("/wallet/{address}")
async def analyze_wallet_defi(address: str, user_id: int = Depends(verify_session)):
    """
    Analyze DeFi positions for a specific wallet address.

    Returns:
    - All DeFi protocol tokens held
    - Categorized by type (governance, LP, staking receipts, etc.)
    - Summary by protocol
    """
    result = await defi_service.analyze_wallet_defi(address)

    if not result:
        raise HTTPException(status_code=404, detail="Could not analyze wallet")

    return result


@router.get("/staking/{address}")
async def get_staking_positions(address: str, refresh: bool = False, user_id: int = Depends(verify_session)):
    """
    Get staked positions for a wallet across supported DeFi protocols.

    Currently supported:
    - Indigo Protocol (INDY staking)

    Returns tokens that are actively staked in protocol smart contracts.
    """
    cache_key = f"staking_positions_{address}"

    if not refresh:
        cached = await get_cache(cache_key)
        if cached:
            cached['from_cache'] = True
            return cached

    result = await defi_service.get_all_staking_positions(address)

    if result:
        result['from_cache'] = False
        await set_cache(cache_key, result, STAKING_CACHE_TTL)

    return result


@router.get("/staking/indigo/{address}")
async def get_indigo_staking(address: str, user_id: int = Depends(verify_session)):
    """
    Get Indigo Protocol staking positions for a specific wallet.

    Returns INDY tokens staked in Indigo governance.
    """
    result = await defi_service.get_indigo_staking(address)

    if not result:
        return {
            "protocol": "Indigo",
            "address": address,
            "positions": [],
            "total_staked_indy": 0,
            "message": "No Indigo staking positions found"
        }

    return result


@router.get("/staking/strike/{address}")
async def get_strike_staking(address: str, user_id: int = Depends(verify_session)):
    """
    Get Strike Finance staking positions for a specific wallet.

    Returns STRIKE tokens staked in Strike Finance governance.
    """
    result = await defi_service.get_strike_staking(address)

    if not result:
        return {
            "protocol": "Strike",
            "address": address,
            "positions": [],
            "total_staked_strike": 0,
            "message": "No Strike staking positions found"
        }

    return result


@router.get("/staking/liqwid/{address}")
async def get_liqwid_staking(address: str, user_id: int = Depends(verify_session)):
    """
    Get Liqwid Finance staking positions for a specific wallet.

    Returns LQ tokens staked in Liqwid governance.
    """
    result = await defi_service.get_liqwid_staking(address)

    if not result:
        return {
            "protocol": "Liqwid",
            "address": address,
            "positions": [],
            "total_staked_lq": 0,
            "message": "No Liqwid staking positions found"
        }

    return result


@router.get("/staking/surf/{address}")
async def get_surf_lending(address: str, user_id: int = Depends(verify_session)):
    """
    Get Surf Lending (Flow Lending) positions for a specific wallet.

    Returns ADA supplied to Surf Lending protocol.
    """
    result = await defi_service.get_surf_lending_positions(address)

    if not result:
        return {
            "protocol": "Surf Lending",
            "address": address,
            "positions": [],
            "total_supplied_ada": 0,
            "message": "No Surf Lending positions found"
        }

    return result


@router.get("/rewards/{address}")
async def get_pending_rewards(address: str, refresh: bool = False, user_id: int = Depends(verify_session)):
    """
    Get all pending rewards for a wallet across all DeFi protocols.

    Returns pending/claimable tokens from:
    - Indigo (INDY)
    - Strike (STRIKE)
    - Liqwid (LQ via SundaeSwap)
    - Surf Lending (SURF)
    """
    cache_key = f"defi_rewards_{address}"

    if not refresh:
        cached = await get_cache(cache_key)
        if cached:
            cached['from_cache'] = True
            return cached

    result = await defi_service.get_all_pending_rewards(address)

    if result:
        result['from_cache'] = False
        await set_cache(cache_key, result, STAKING_CACHE_TTL)

    return result


@router.get("/rewards/indigo/{address}")
async def get_indigo_rewards(address: str, user_id: int = Depends(verify_session)):
    """
    Get pending INDY rewards from Indigo Protocol.
    """
    result = await defi_service.get_indigo_pending_rewards(address)

    if not result:
        return {
            "protocol": "Indigo",
            "address": address,
            "pending_rewards": 0,
            "reward_token": "INDY",
            "message": "No pending Indigo rewards found"
        }

    return result


@router.get("/rewards/strike/{address}")
async def get_strike_rewards(address: str, user_id: int = Depends(verify_session)):
    """
    Get pending STRIKE rewards from Strike Finance.
    """
    result = await defi_service.get_strike_pending_rewards(address)

    if not result:
        return {
            "protocol": "Strike",
            "address": address,
            "pending_rewards": 0,
            "reward_token": "STRIKE",
            "message": "No pending Strike rewards found"
        }

    return result


@router.get("/rewards/liqwid/{address}")
async def get_liqwid_rewards(address: str, user_id: int = Depends(verify_session)):
    """
    Get pending LQ rewards from Liqwid Finance via SundaeSwap.
    """
    result = await defi_service.get_liqwid_pending_rewards(address)

    if not result:
        return {
            "protocol": "Liqwid",
            "address": address,
            "pending_rewards": 0,
            "reward_token": "LQ",
            "rewards_portal": "https://liqwid-rewards.sundaeswap.finance/",
            "message": "No pending Liqwid rewards found"
        }

    return result


@router.get("/summary")
async def get_defi_summary(user_id: int = Depends(verify_session), refresh: bool = False):
    """
    Get aggregated DeFi summary across all tracked wallets.

    Returns consolidated view of all DeFi positions.
    """
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo DeFi summary with anime-themed protocols
        summary = await demo_defi_service.get_defi_summary()
        summary['demo_mode'] = True
        return summary

    # Normal mode
    cache_key = f"defi_summary_{user_id}"

    if not refresh:
        cached = await get_cache(cache_key)
        if cached:
            cached['from_cache'] = True
            return cached

    wallets = await get_all_wallets(user_id=user_id)
    cardano_wallets = [w for w in wallets if w['blockchain'] == 'cardano']

    if not cardano_wallets:
        return {
            "message": "No Cardano wallets tracked",
            "total_wallets": 0,
            "defi_positions": []
        }

    # Aggregate DeFi positions across all wallets
    all_positions = {}
    protocol_totals = {}
    wallets_with_defi = 0

    logger.info(f"[DeFi Summary] Analyzing {len(cardano_wallets)} Cardano wallets for user {user_id}")

    for i, wallet in enumerate(cardano_wallets):
        result = await defi_service.analyze_wallet_defi(wallet['address'])
        logger.info(f"[DeFi Summary] Wallet {i+1}/{len(cardano_wallets)} ({wallet['address'][:20]}...): result={'has data' if result and result.get('defi_positions') else 'None/empty'}")

        if result and result['defi_positions']:
            wallets_with_defi += 1

            for pos in result['defi_positions']:
                key = f"{pos['protocol']}:{pos['asset_name']}"

                if key not in all_positions:
                    all_positions[key] = {
                        'protocol': pos['protocol'],
                        'token': pos['token'],
                        'asset_name': pos['asset_name'],
                        'type': pos['type'],
                        'type_label': pos['type_label'],
                        'decimals': pos['decimals'],
                        'quantity_raw': 0,
                        'wallet_count': 0
                    }

                all_positions[key]['quantity_raw'] += pos['quantity_raw']
                all_positions[key]['wallet_count'] += 1

                # Protocol totals
                protocol = pos['protocol']
                if protocol not in protocol_totals:
                    protocol_totals[protocol] = {
                        'protocol': protocol,
                        'position_count': 0,
                        'token_types': set()
                    }
                protocol_totals[protocol]['position_count'] += 1
                protocol_totals[protocol]['token_types'].add(pos['type'])

    # Format quantities
    for key, pos in all_positions.items():
        pos['quantity'] = pos['quantity_raw'] / (10 ** pos['decimals'])
        pos['quantity_formatted'] = f"{pos['quantity']:,.6f}".rstrip('0').rstrip('.')

    # Convert sets to lists for JSON serialization
    for proto in protocol_totals.values():
        proto['token_types'] = list(proto['token_types'])

    # Group by category
    by_category = {}
    for pos in all_positions.values():
        cat = pos['type_label']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(pos)

    result = {
        "total_wallets_analyzed": len(cardano_wallets),
        "wallets_with_defi": wallets_with_defi,
        "total_positions": len(all_positions),
        "protocols_used": list(protocol_totals.keys()),
        "protocol_summary": list(protocol_totals.values()),
        "positions_by_category": by_category,
        "all_positions": sorted(
            list(all_positions.values()),
            key=lambda x: (x['protocol'], x['token'])
        ),
        "from_cache": False
    }

    # Only cache if we got meaningful results (avoid caching failed/empty scans)
    if wallets_with_defi > 0 or len(all_positions) > 0:
        await set_cache(cache_key, result, DEFI_SUMMARY_CACHE_TTL)
    else:
        logger.warning(f"[DeFi Summary] Empty result for {len(cardano_wallets)} wallets - NOT caching (possible API failure)")
        # Try to return stale cache if available
        stale = await get_cache(cache_key)
        if stale and stale.get('wallets_with_defi', 0) > 0:
            logger.info("[DeFi Summary] Returning stale cache instead of empty result")
            stale['from_cache'] = True
            stale['stale_fallback'] = True
            return stale

    return result
