"""
DeFi Tracking API Endpoints

Provides endpoints for analyzing Cardano DeFi positions.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.defi import defi_service
from services.demo_defi_service import demo_defi_service
from datetime import datetime, timedelta
from database import get_all_wallets, get_cache, set_cache, get_stale_cache, get_username_by_user_id
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session
from config import CACHE_TTL_COLD, CACHE_TTL_WARM

logger = logging.getLogger(__name__)


def parseFloat_safe(val) -> float:
    """Safely convert a value to float, returning 0 on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


router = APIRouter(prefix="/defi", tags=["defi"])


async def _resolve_scan_identity(address: str, user_id: int):
    """Stake-account-wide identity for a staking scan, partitioned so sibling
    wallet rows can never double-report the same positions.

    The stake account's payment credentials are split among its STORED wallet
    rows: every stored row matches its own credential (unchanged behavior),
    and exactly one deterministic representative row — the lowest stored
    sibling address — additionally claims the "orphan" credentials belonging
    to no stored row. The union across stored rows therefore covers the whole
    stake account exactly once, and downstream consumers that sum per-address
    caches (snapshot, summary, portfolio) stay correct.

    Returns (payment_creds, account_addresses); (None, None) means
    single-address scan — the pre-P2 behavior and the failure fallback.
    """
    try:
        context = await defi_service.resolve_wallet_context(address)
        if not context.get('resolved') or len(context.get('payment_creds') or []) <= 1:
            return None, None

        # Representative eligibility requires membership in the CHAIN-OBSERVED
        # (Koios) address set. A stored address Koios has never seen (manually
        # added, never used on-chain) cannot hold positions — and because it
        # is invisible to sibling rows' resolutions, electing it would let two
        # rows claim the same orphan credentials (drift double-count).
        koios_addresses = set(context.get('koios_addresses') or [])
        if address not in koios_addresses:
            return None, None

        wallets = await get_all_wallets(user_id=user_id)
        stored = {w['address'] for w in wallets if w.get('blockchain') == 'cardano'}
        rep_candidates = sorted(a for a in koios_addresses if a in stored)
        representative = rep_candidates[0] if rep_candidates else address
        if address != representative:
            # A different stored sibling owns the account-wide sweep
            return None, None

        # Exclude the credentials/addresses of EVERY other stored sibling in
        # the full context (including drifted, Koios-unknown ones persisted by
        # the self-append) — those rows scan their own credential themselves.
        own_cred = defi_service._get_payment_credential(address)
        stored_siblings = [
            a for a in context['addresses'] if a in stored and a != address
        ]
        other_creds = set()
        for a in stored_siblings:
            cred = defi_service._get_payment_credential(a)
            if cred and cred != own_cred:
                other_creds.add(cred)

        payment_creds = [
            c for c in context['payment_creds'] if c not in other_creds
        ]
        account_addresses = [
            a for a in context['addresses'] if a not in stored_siblings
        ]
        logger.info(
            f"[Staking] {address[:20]}... is account representative: "
            f"matching {len(payment_creds)}/{len(context['payment_creds'])} creds, "
            f"{len(account_addresses)} addresses"
        )
        return payment_creds, account_addresses

    except Exception as e:
        logger.warning(
            f"[Staking] identity resolution failed for {address[:20]}...: {e} "
            f"— falling back to single-address scan"
        )
        return None, None


_GUARD_KINDS = (
    'staked', 'v2_balance', 'v2_vault_positions', 'cdps', 'stability_pool'
)


def _data_protocol_kinds(result: dict) -> set:
    """(protocol, kind) pairs carrying position data in a staking result.

    Basis of the degraded-result guard, at PER-KIND granularity: a
    sub-source loss inside a surviving protocol (e.g. Indigo CDPs failed
    while Indigo staking succeeded) still registers as a loss instead of
    silently dropping.
    """
    pairs = set()
    for name, p in (result.get('protocols') or {}).items():
        for kind in _GUARD_KINDS:
            if p.get(kind):
                pairs.add((name, kind))
    return pairs


def _data_protocol_names(result: dict) -> set:
    """Names of protocols carrying ANY position data in a staking result."""
    return {name for name, _ in _data_protocol_kinds(result)}


def _count_data_protocols(result: dict) -> int:
    """Count of protocols carrying any position data (see _data_protocol_names)."""
    return len(_data_protocol_names(result))

# Cache TTL in seconds - refresh daily (DeFi positions don't change that frequently)
STAKING_CACHE_TTL = CACHE_TTL_COLD  # 24 hours
DEFI_SUMMARY_CACHE_TTL = CACHE_TTL_COLD  # 24 hours

# Global semaphore to limit concurrent staking scans.
# Each scan hits Blockfrost for multiple protocols. With 44+ wallets scanning
# simultaneously, 176+ concurrent Blockfrost calls cause rate limiting and timeouts,
# progressively degrading cached data on each refresh.
_staking_scan_semaphore = asyncio.Semaphore(5)


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


# In-flight background staking recomputes (server-side SWR, mirrors the
# portfolio-summary scheduler): at most one per user+address at a time
_staking_refresh_tasks: dict = {}


def _schedule_staking_refresh(address: str, user_id: int):
    """Kick off a background staking recompute after serving a stale row.

    Freshness must not depend on the user hard-pulling: the stale hit
    answers instantly and this job repopulates the cache behind it. Runs
    the normal compute path (never refresh=True semantics); concurrent
    stale hits piggyback on the in-flight task instead of stampeding.
    """
    task_key = f"{user_id}:staking_positions_{address}"
    if task_key in _staking_refresh_tasks:
        return

    async def _refresh_job():
        try:
            await _compute_staking_positions(address, user_id)
        except Exception as e:
            logger.warning(
                f"[Staking] background revalidation failed for "
                f"{address[:20]}...: {e}"
            )
        finally:
            _staking_refresh_tasks.pop(task_key, None)

    _staking_refresh_tasks[task_key] = asyncio.create_task(_refresh_job())


@router.get("/staking/{address}")
async def get_staking_positions(address: str, refresh: bool = False, user_id: int = Depends(verify_session)):
    """
    Get staked positions for a wallet across supported DeFi protocols.

    Currently supported:
    - Indigo Protocol (INDY staking)

    Returns tokens that are actively staked in protocol smart contracts.
    """
    # Demo user intercept
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await demo_defi_service.get_staking_data(address)

    cache_key = f"staking_positions_{address}"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

        # Fresh cache miss — serve the stale row for instant data and
        # revalidate in the background (server-side SWR)
        stale_data, stale_expires = await get_stale_cache(cache_key, user_id=user_id)
        if stale_data:
            _schedule_staking_refresh(address, user_id)
            cached_at = (datetime.fromisoformat(stale_expires) - timedelta(seconds=STAKING_CACHE_TTL)).isoformat()
            stale_data['from_cache'] = True
            stale_data['stale'] = True
            stale_data['cached_at'] = cached_at
            return stale_data

    return await _compute_staking_positions(address, user_id)


async def _compute_staking_positions(address: str, user_id: int):
    """Full staking recompute for one address: identity resolution, scan,
    downgrade guard, cache write. Shared by the route (cold/refresh path)
    and the background stale-hit revalidation."""
    cache_key = f"staking_positions_{address}"

    # Fetch previous result for protocol-level merge on timeout
    previous_result = None
    stale_data, stale_expires = await get_stale_cache(cache_key, user_id=user_id)
    if stale_data and stale_data.get('protocols'):
        previous_result = stale_data

    # Stake-account-wide identity (multi-credential matching), partitioned
    # across stored sibling rows to prevent double counting
    payment_creds, account_addresses = await _resolve_scan_identity(address, user_id)

    # Limit concurrent staking scans to prevent Blockfrost overload
    async with _staking_scan_semaphore:
        result = await defi_service.get_all_staking_positions(
            address,
            previous_result=previous_result,
            payment_creds=payment_creds,
            account_addresses=account_addresses,
        )

    if result:
        result['from_cache'] = False
        result['cached_at'] = datetime.now().isoformat()

        # Don't overwrite cache with a degraded result (fewer protocols with data).
        # This prevents progressive data loss when Blockfrost is overloaded.
        # Baseline falls back to the stale (expired) row when no fresh row
        # exists, so staleness stays monotonic: a degraded recompute after a
        # TTL expiry or cache purge can never displace better last-good data.
        existing = await get_cache(cache_key, user_id=user_id)
        baseline = existing
        baseline_is_stale = False
        if baseline is None and stale_data and stale_data.get('protocols'):
            baseline = stale_data
            baseline_is_stale = True
        # A scan-scope change (identity partition grew or shrank — e.g. the
        # user stored a sibling address as its own wallet, moving a
        # credential out of this row's claim) legitimately changes how much
        # data this row reports. Comparing across scopes would wedge the old
        # over-scoped row forever, double-counting against the new sibling
        # row — so the guard re-baselines instead of refusing.
        _default_scope = {'payment_creds': 1, 'addresses': 1}
        scope_changed = bool(baseline) and (
            (baseline.get('account_scan') or _default_scope)
            != (result.get('account_scan') or _default_scope)
        )
        if scope_changed:
            logger.info(
                f"[Staking] scan scope changed for {address[:20]}... "
                f"({baseline.get('account_scan')} -> {result.get('account_scan')}) "
                f"— accepting result without downgrade guard"
            )
        if baseline and not scope_changed:
            # Per-(protocol, kind) comparison: refuse if any position kind
            # that had data in the baseline is MISSING from the result
            # WITHOUT the protocol having positively confirmed it is empty.
            # This catches sub-source losses inside surviving protocols
            # (CDPs failed while staking succeeded). A confirmed empty is a
            # legitimate shrink (genuine protocol exit) and must display; a
            # failed/timed-out fetch must not erase last-good data.
            baseline_pairs = _data_protocol_kinds(baseline)
            result_pairs = _data_protocol_kinds(result)
            confirmed = set(result.get('confirmed_empty') or [])
            lost = {
                pair for pair in baseline_pairs - result_pairs
                if pair[0] not in confirmed
            }
            if lost:
                logger.warning(
                    f"[Staking] Skipping cache update for {address[:20]}... — "
                    f"result lost {sorted(lost)} without confirmed exit "
                    f"(confirmed empty {sorted(confirmed)})"
                    f"{' (stale baseline)' if baseline_is_stale else ''}"
                )
                # Return the existing better cache instead
                baseline['from_cache'] = True
                if baseline_is_stale:
                    baseline['stale'] = True
                return baseline

        await set_cache(cache_key, result, STAKING_CACHE_TTL, user_id=user_id)

        # Fire-and-forget: write staking positions to portfolio_positions
        # (shared valuation over every position kind; this writer never
        # included pending rewards — preserved)
        try:
            from database import upsert_portfolio_positions_batch
            from services.defi import staking_portfolio_rows
            from services.pricing import pricing_service as _pp_pricing
            _pp_prices = await _pp_pricing.get_all_tracked_prices()
            pp_rows = staking_portfolio_rows(
                user_id, result.get('protocols'), _pp_prices,
                include_rewards=False,
            )
            if pp_rows:
                await upsert_portfolio_positions_batch(pp_rows)
        except Exception as e:
            logger.debug(f"Portfolio positions staking write failed: {e}")

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


@router.get("/indigo/cdps/{address}")
async def get_indigo_cdps(address: str, user_id: int = Depends(verify_session)):
    """
    Get Indigo Protocol CDP (loan) positions for a specific wallet.

    Returns collateral (ADA), minted iAssets, and collateral ratios.
    """
    result = await defi_service.get_indigo_cdps(address)

    if not result:
        return {
            "protocol": "Indigo",
            "address": address,
            "cdps": [],
            "total_collateral_ada": 0,
            "cdp_count": 0,
            "message": "No Indigo CDP positions found"
        }

    return result


@router.get("/indigo/stability-pool/{address}")
async def get_indigo_stability_pool(address: str, user_id: int = Depends(verify_session)):
    """
    Get Indigo Protocol Stability Pool positions for a specific wallet.

    Returns iAsset deposits in stability pools.
    """
    result = await defi_service.get_indigo_stability_pool(address)

    if not result:
        return {
            "protocol": "Indigo",
            "address": address,
            "stability_pool": [],
            "pool_count": 0,
            "message": "No Indigo Stability Pool positions found"
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
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    result = await defi_service.get_all_pending_rewards(address)

    if result:
        result['from_cache'] = False
        await set_cache(cache_key, result, STAKING_CACHE_TTL, user_id=user_id)

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


@router.get("/uniswap-positions/{address}")
async def get_uniswap_positions(address: str, user_id: int = Depends(verify_session)):
    """
    Get Uniswap V3 LP positions for an Ethereum address.

    Returns active liquidity positions with token pairs and fee tiers.
    """
    try:
        from services.graph import graph_service
        if not graph_service.is_configured():
            return {"success": False, "configured": False, "message": "The Graph API key not configured"}

        positions = await graph_service.get_lp_positions(address)
        return {
            "success": True,
            "address": address,
            "positions": positions,
            "count": len(positions),
            "protocol": "Uniswap V3"
        }
    except Exception as e:
        logger.error(f"Error fetching Uniswap positions for {address}: {e}")
        return {"success": False, "error": str(e)}


@router.get("/helium/{address}")
async def get_helium_rewards(address: str, refresh: bool = False, user_id: int = Depends(verify_session)):
    """Get Helium hotspot rewards for a Solana wallet address."""
    from services.helium import get_helium_staking

    cache_key = f"helium_rewards_{address}"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    result = await get_helium_staking(address)

    if not result:
        return {
            "protocols": {},
            "address": address,
            "message": "No Helium rewards found"
        }

    result['from_cache'] = False
    await set_cache(cache_key, result, CACHE_TTL_WARM, user_id=user_id)
    return result


@router.get("/iagon/{address}")
async def get_iagon_staking_data(address: str, refresh: bool = False, user_id: int = Depends(verify_session)):
    """Get Iagon staking positions for a Cardano wallet address."""
    cache_key = f"iagon_staking_{address}"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    iagon = await defi_service.get_iagon_staking(address)

    if not iagon:
        return {"protocols": {}, "address": address, "message": "No Iagon staking found"}

    logo_url = await defi_service._get_token_logo_url('IAG')

    result = {
        "protocols": {
            "Iagon": {
                "staked": [{
                    "token": "IAG",
                    "amount": iagon['total_staked_iag'],
                    "positions": iagon['position_count'],
                    "logo_url": logo_url
                }],
                "reward_token": "IAG",
                "rewards_url": "https://iagon.com/staking",
                "category": "depin",
                "blockchain": "cardano",
                "total_positions": iagon['position_count'],
            }
        }
    }

    result['from_cache'] = False
    await set_cache(cache_key, result, CACHE_TTL_WARM, user_id=user_id)
    return result


@router.get("/iagon/debug/{address}")
async def debug_iagon_staking(address: str, user_id: int = Depends(verify_session)):
    """Debug endpoint to test Iagon staking scan with verbose output."""
    from services.defi import (
        IAGON_ALL_STAKING_ADDRESSES, IAGON_STAKING_CONTRACT_ADDRESSES,
        IAGON_IAG_ASSET, IAGON_OLD_STAKING_ADDRESS,
        IAGON_OPERATOR_STAKING_ADDRESS, IAGON_DELEGATED_STAKING_ADDRESS,
        IAGON_BATCHER_ADDRESS
    )
    from services.http_client import blockfrost_fetch
    from config import BLOCKFROST_API_KEY

    headers = {"project_id": BLOCKFROST_API_KEY}

    # Check scan state cache
    scan_state = await get_cache(f"iagon_scan_state_{address}")

    # Fetch first 2 pages of transactions to sample
    sample_txs = []
    iag_related_txs = []
    for page in [1, 2]:
        resp = await blockfrost_fetch(
            f"/addresses/{address}/transactions",
            headers=headers,
            params={"count": 100, "page": page, "order": "desc"},
            timeout=15.0
        )
        if resp.status_code == 200:
            sample_txs.extend(resp.json())
        else:
            break

    # Check a sample of recent txs for IAG involvement with detailed flow info
    sem = asyncio.Semaphore(5)
    async def check_tx(tx):
        async with sem:
            r = await blockfrost_fetch(f"/txs/{tx['tx_hash']}/utxos", headers=headers, timeout=15.0)
            if r.status_code != 200:
                return None
            data = r.json()
            has_iag = False
            hits_contract = False
            user_sends = 0
            user_receives = 0
            staking_sends = 0
            staking_receives = 0
            batcher_sends = 0
            batcher_receives = 0

            for inp in data.get('inputs', []):
                for amt in inp.get('amount', []):
                    if amt['unit'] == IAGON_IAG_ASSET:
                        has_iag = True
                        qty = int(amt['quantity']) / 1_000_000
                        if inp['address'] == address:
                            user_sends += qty
                        elif inp['address'] in IAGON_STAKING_CONTRACT_ADDRESSES:
                            staking_sends += qty
                        elif inp['address'] == IAGON_BATCHER_ADDRESS:
                            batcher_sends += qty
                if inp['address'] in IAGON_ALL_STAKING_ADDRESSES:
                    hits_contract = True

            for out in data.get('outputs', []):
                for amt in out.get('amount', []):
                    if amt['unit'] == IAGON_IAG_ASSET:
                        has_iag = True
                        qty = int(amt['quantity']) / 1_000_000
                        if out['address'] == address:
                            user_receives += qty
                        elif out['address'] in IAGON_STAKING_CONTRACT_ADDRESSES:
                            staking_receives += qty
                        elif out['address'] == IAGON_BATCHER_ADDRESS:
                            batcher_receives += qty
                if out['address'] in IAGON_ALL_STAKING_ADDRESSES:
                    hits_contract = True

            if has_iag or hits_contract:
                net_staking = staking_receives - staking_sends
                net_batcher = batcher_receives - batcher_sends
                # Classify: staking contract flow = deposit/withdrawal, batcher-only = reward
                if net_staking > 0.001:
                    tx_type = "deposit"
                elif net_staking < -0.001:
                    tx_type = "withdrawal"
                elif net_batcher < -0.001 and user_receives > 0:
                    tx_type = "reward_claim"
                else:
                    tx_type = "neutral"
                return {
                    'tx_hash': tx['tx_hash'],
                    'block_height': tx.get('block_height'),
                    'type': tx_type,
                    'user_sends_iag': round(user_sends, 6),
                    'user_receives_iag': round(user_receives, 6),
                    'staking_net': round(net_staking, 6),
                    'batcher_net': round(net_batcher, 6),
                }
            return None

    # Check up to 20 most recent txs
    checks = await asyncio.gather(*[check_tx(tx) for tx in sample_txs[:20]], return_exceptions=True)
    for c in checks:
        if c and not isinstance(c, Exception):
            iag_related_txs.append(c)

    # Run the actual staking scan
    staking_result = await defi_service.get_iagon_staking(address)

    return {
        "address": address,
        "staking_addresses": {
            "old": IAGON_OLD_STAKING_ADDRESS,
            "operator": IAGON_OPERATOR_STAKING_ADDRESS,
            "delegated": IAGON_DELEGATED_STAKING_ADDRESS,
            "batcher": IAGON_BATCHER_ADDRESS
        },
        "iag_asset_id": IAGON_IAG_ASSET,
        "scan_state_cached": scan_state,
        "total_txs_sampled": len(sample_txs),
        "iag_related_txs_in_sample": iag_related_txs,
        "staking_result": staking_result
    }


@router.get("/chainlink/{address}")
async def get_chainlink_staking_positions(address: str, user_id: int = Depends(verify_session)):
    """
    Get Chainlink staking positions for an Ethereum address.
    Reads staked LINK and pending rewards from Chainlink Staking v0.2.
    """
    from services.defi import get_chainlink_staking

    result = await get_chainlink_staking(address)

    if not result:
        return {
            "protocol": "Chainlink Staking",
            "address": address,
            "staked_link": 0,
            "pending_rewards_link": 0,
            "message": "No Chainlink staking positions found"
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
        cached = await get_cache(cache_key, user_id=user_id)
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

    logger.info(f"[DeFi Summary] Analyzing {len(cardano_wallets)} Cardano wallets for user {user_id} (parallel)")

    # Fetch all wallet DeFi data in parallel
    wallet_results = await asyncio.gather(*[
        defi_service.analyze_wallet_defi(w['address']) for w in cardano_wallets
    ], return_exceptions=True)

    for i, (wallet, result) in enumerate(zip(cardano_wallets, wallet_results)):
        if isinstance(result, Exception):
            logger.error(f"[DeFi Summary] Wallet {i+1}/{len(cardano_wallets)} ({wallet['address'][:20]}...): error={result}")
            continue

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
                        'wallet_count': 0,
                        'logo_url': pos.get('logo_url'),
                        # LP valuation fields
                        'value_usd': 0.0,
                        'value_ada': 0.0,
                        'pair_name': pos.get('pair_name', ''),
                        'pool_share_pct': 0.0,
                        'underlying_tokens': [],
                    }

                all_positions[key]['quantity_raw'] += pos['quantity_raw']
                all_positions[key]['wallet_count'] += 1
                # Preserve logo_url from any wallet that has it
                if pos.get('logo_url') and not all_positions[key].get('logo_url'):
                    all_positions[key]['logo_url'] = pos['logo_url']

                # Accumulate LP valuation data across wallets
                if pos.get('value_usd'):
                    all_positions[key]['value_usd'] += float(pos['value_usd'])
                    all_positions[key]['value_ada'] += float(pos.get('value_ada', 0))
                    all_positions[key]['pool_share_pct'] += float(pos.get('pool_share_pct', 0))
                    if pos.get('pair_name'):
                        all_positions[key]['pair_name'] = pos['pair_name']
                    if pos.get('underlying_tokens'):
                        existing = all_positions[key]['underlying_tokens']
                        incoming = pos['underlying_tokens']
                        if not existing:
                            all_positions[key]['underlying_tokens'] = [
                                dict(t) for t in incoming
                            ]
                        else:
                            for i, tok in enumerate(incoming):
                                if i < len(existing):
                                    existing[i]['amount'] = round(
                                        existing[i].get('amount', 0) + tok.get('amount', 0), 6
                                    )
                                    existing[i]['value_usd'] = round(
                                        existing[i].get('value_usd', 0) + tok.get('value_usd', 0), 2
                                    )

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
        await set_cache(cache_key, result, DEFI_SUMMARY_CACHE_TTL, user_id=user_id)

        # Fire-and-forget: write DeFi positions to portfolio_positions
        try:
            from database import upsert_portfolio_positions_batch
            from services.pricing import pricing_service as _pp_pricing
            _pp_prices = await _pp_pricing.get_all_tracked_prices()
            pp_rows = []
            for pos in result.get('all_positions', []):
                token = (pos.get('token') or '').upper()
                qty = float(pos.get('quantity', 0))
                if not token or qty <= 0:
                    continue
                p = _pp_prices.get(token, {})
                price = p.get('usd', 0) if isinstance(p, dict) else 0
                # LP/liquidity positions have no market price but a pre-computed value_usd.
                # Store as quantity=value_usd, price=1.0 so /portfolio/instant values them correctly.
                pre_valued_usd = float(pos.get('value_usd', 0))
                if price <= 0 and pre_valued_usd > 0:
                    pp_rows.append({
                        'user_id': user_id, 'symbol': token, 'quantity': pre_valued_usd,
                        'source_type': 'defi', 'source_detail': pos.get('protocol', '').lower(),
                        'chain': 'cardano', 'last_price_usd': 1.0,
                    })
                else:
                    pp_rows.append({
                        'user_id': user_id, 'symbol': token, 'quantity': qty,
                        'source_type': 'defi', 'source_detail': pos.get('protocol', '').lower(),
                        'chain': 'cardano', 'last_price_usd': price,
                    })
            if pp_rows:
                # Clear stale DeFi rows before re-inserting; prevents accumulation
                # of positions from protocols no longer detected.
                from database import clear_portfolio_positions
                await clear_portfolio_positions(user_id, source_type='defi')
                await upsert_portfolio_positions_batch(pp_rows)
        except Exception as e:
            logger.debug(f"Portfolio positions DeFi write failed: {e}")
    else:
        logger.warning(f"[DeFi Summary] Empty result for {len(cardano_wallets)} wallets - NOT caching (possible API failure)")
        # Try to return stale cache if available
        stale = await get_cache(cache_key, user_id=user_id)
        if stale and stale.get('wallets_with_defi', 0) > 0:
            logger.info("[DeFi Summary] Returning stale cache instead of empty result")
            stale['from_cache'] = True
            stale['stale_fallback'] = True
            return stale

    return result


# ============================================================================
# Multi-chain DeFi Position Detection (via Protocol Registry)
# ============================================================================

from services.defi_protocols.registry import protocol_registry


@router.get("/positions/{chain}/{address}")
async def get_defi_positions_by_chain(chain: str, address: str, user_id: int = Depends(verify_session)):
    """Get all DeFi positions for an address on a specific chain."""
    positions = await protocol_registry.detect_all_positions(address, chain=chain)
    return {
        "chain": chain,
        "address": address,
        "positions": [p.to_dict() for p in positions],
        "position_count": len(positions),
        "protocols_scanned": len(protocol_registry.get_adapters_for_chain(chain)),
    }


@router.get("/detect/{address}")
async def get_all_defi_positions(address: str, user_id: int = Depends(verify_session)):
    """Get all DeFi positions across all chains for an address."""
    positions_by_chain = await protocol_registry.detect_positions_by_chain(address)
    all_positions = []
    chain_summary = {}
    for chain, positions in positions_by_chain.items():
        chain_positions = [p.to_dict() for p in positions]
        all_positions.extend(chain_positions)
        chain_summary[chain] = len(chain_positions)
    return {
        "address": address,
        "positions": all_positions,
        "total_positions": len(all_positions),
        "chains": chain_summary,
        "total_protocols": protocol_registry.protocol_count,
    }


# ============================================================================
# Lending Position Detection
# ============================================================================

@router.get("/lending/{address}")
async def get_lending_positions(address: str, user_id: int = Depends(verify_session)):
    """Get all lending/borrowing positions for a specific wallet address.

    Returns supply and borrow positions from Cardano lending protocols:
    - Liqwid Finance (qToken supply positions)
    - Lenfi (receipt token supply + loan NFT borrows)
    - Surf Lending (API-based supply + borrow)

    Returns positions with type lending_supply or lending_borrow.
    """
    positions = await protocol_registry.detect_all_positions(address, chain="cardano")

    lending_positions = [
        p.to_dict() for p in positions
        if p.position_type in ("lending_supply", "lending_borrow")
    ]

    supply_positions = [p for p in lending_positions if p['position_type'] == 'lending_supply']
    borrow_positions = [p for p in lending_positions if p['position_type'] == 'lending_borrow']

    return {
        "address": address,
        "lending_positions": lending_positions,
        "supply_count": len(supply_positions),
        "borrow_count": len(borrow_positions),
        "total_positions": len(lending_positions),
    }


@router.get("/lending-summary")
async def get_lending_summary(user_id: int = Depends(verify_session), refresh: bool = False):
    """Get aggregated lending summary across all tracked wallets (Cardano + Solana).

    Returns consolidated view of all lending supply, borrow, perpetual, and LP positions
    from Cardano and Solana DeFi protocols.
    """
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"lending_positions": [], "supply_count": 0, "borrow_count": 0, "perp_positions": [], "lp_positions": []}

    cache_key = f"lending_summary_{user_id}"

    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    wallets = await get_all_wallets(user_id=user_id)
    cardano_wallets = [w for w in wallets if w['blockchain'] == 'cardano']
    solana_wallets = [w for w in wallets if w['blockchain'] == 'solana']

    # EVM wallets: ethereum, polygon, arbitrum, base, avalanche, optimism
    EVM_CHAINS = {'ethereum', 'polygon', 'arbitrum', 'base', 'avalanche', 'optimism'}
    evm_wallets = [w for w in wallets if w['blockchain'] in EVM_CHAINS]

    if not cardano_wallets and not solana_wallets and not evm_wallets:
        return {
            "lending_positions": [],
            "supply_count": 0,
            "borrow_count": 0,
            "perp_positions": [],
            "lp_positions": [],
            "total_wallets": 0,
        }

    total_wallets = len(cardano_wallets) + len(solana_wallets) + len(evm_wallets)
    logger.info(f"[Lending] Scanning {len(cardano_wallets)} Cardano + {len(solana_wallets)} Solana + {len(evm_wallets)} EVM wallets for DeFi positions")

    # Position types we care about
    DEFI_POSITION_TYPES = (
        "lending_supply", "lending_borrow",
        "perpetuals",
        "lp_position", "concentrated_lp",
        "cdp", "yield_vault",
    )

    # Scan all wallets in parallel
    async def scan_wallet(wallet, chain):
        try:
            positions = await asyncio.wait_for(
                protocol_registry.detect_all_positions(wallet['address'], chain=chain),
                timeout=30.0
            )
            return [
                p.to_dict() for p in positions
                if p.position_type in DEFI_POSITION_TYPES
            ]
        except asyncio.TimeoutError:
            logger.warning(f"[Lending] Timeout scanning {chain}/{wallet['address'][:20]}...")
            return []
        except Exception as e:
            logger.error(f"[Lending] Error scanning {chain}/{wallet['address'][:20]}...: {e}")
            return []

    # Gather Cardano, Solana, and EVM results in parallel
    scan_tasks = []
    for w in cardano_wallets:
        scan_tasks.append(scan_wallet(w, "cardano"))
    for w in solana_wallets:
        scan_tasks.append(scan_wallet(w, "solana"))
    for w in evm_wallets:
        scan_tasks.append(scan_wallet(w, w['blockchain']))

    results = await asyncio.gather(*scan_tasks)

    # Aggregate positions by protocol + token + type
    aggregated = {}
    all_positions = []

    for wallet_positions in results:
        for pos in wallet_positions:
            all_positions.append(pos)
            key = f"{pos['protocol']}:{pos['token_symbol']}:{pos['position_type']}"
            if key not in aggregated:
                aggregated[key] = {
                    'protocol': pos['protocol'],
                    'chain': pos.get('chain', 'cardano'),
                    'token_symbol': pos['token_symbol'],
                    'token_name': pos.get('token_name', ''),
                    'position_type': pos['position_type'],
                    'amount': 0,
                    'value_usd': 0,
                    'apy': pos.get('apy'),
                    'pending_rewards': 0,
                    'reward_token': pos.get('reward_token'),
                    'wallet_count': 0,
                    'extra': pos.get('extra', {}),
                    'underlying_tokens': pos.get('underlying_tokens', []),
                }
            aggregated[key]['amount'] += pos.get('amount', 0)
            aggregated[key]['value_usd'] += pos.get('value_usd', 0)
            aggregated[key]['wallet_count'] += 1
            # Accumulate rewards
            if pos.get('pending_rewards'):
                aggregated[key]['pending_rewards'] += parseFloat_safe(pos['pending_rewards'])
            if pos.get('reward_token') and not aggregated[key].get('reward_token'):
                aggregated[key]['reward_token'] = pos['reward_token']
            # Preserve APY if available
            if pos.get('apy') and not aggregated[key]['apy']:
                aggregated[key]['apy'] = pos['apy']
            # Preserve extra fields like health_factor, pnl, side, vault data
            if pos.get('extra'):
                for field in ('health_factor', 'pnl', 'side', 'leverage', 'entry_price',
                              'collateral_usd', 'size_usd', 'in_range', 'pair',
                              'underlying_token', 'source', 'aggregate',
                              'vault_type', 'collateral_token', 'collateral_amount',
                              'debt_dai', 'collateral_ratio',
                              'pool_name', 'gauge_address',
                              'fee_tier', 'fee_tier_label', 'current_tick',
                              'tick_lower', 'tick_upper', 'token0_symbol', 'token1_symbol',
                              'token0_amount', 'token1_amount', 'uncollected_fees'):
                    if field in pos['extra'] and field not in aggregated[key]['extra']:
                        aggregated[key]['extra'][field] = pos['extra'][field]
            # Preserve underlying tokens (use the first non-empty one)
            if pos.get('underlying_tokens') and not aggregated[key]['underlying_tokens']:
                aggregated[key]['underlying_tokens'] = pos['underlying_tokens']

    supply_list = [p for p in aggregated.values() if p['position_type'] == 'lending_supply']
    borrow_list = [p for p in aggregated.values() if p['position_type'] == 'lending_borrow']
    perp_list = [p for p in aggregated.values() if p['position_type'] == 'perpetuals']
    lp_list = [p for p in aggregated.values() if p['position_type'] in ('lp_position', 'concentrated_lp')]
    cdp_list = [p for p in aggregated.values() if p['position_type'] == 'cdp']
    vault_list = [p for p in aggregated.values() if p['position_type'] == 'yield_vault']

    result = {
        "lending_positions": list(aggregated.values()),
        "supply_positions": supply_list,
        "borrow_positions": borrow_list,
        "perp_positions": perp_list,
        "lp_positions": lp_list,
        "cdp_positions": cdp_list,
        "vault_positions": vault_list,
        "supply_count": len(supply_list),
        "borrow_count": len(borrow_list),
        "perp_count": len(perp_list),
        "lp_count": len(lp_list),
        "cdp_count": len(cdp_list),
        "vault_count": len(vault_list),
        "total_positions": len(aggregated),
        "total_wallets_scanned": total_wallets,
        "from_cache": False,
    }

    if aggregated:
        await set_cache(cache_key, result, STAKING_CACHE_TTL, user_id=user_id)

    return result
