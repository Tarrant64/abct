"""
Privacy Router - ZK Privacy and privacy protocol endpoints.

Endpoints:
    GET  /privacy/stats                          - Chain-wide privacy statistics
    GET  /privacy/wallet/{wallet_id}/score        - Per-wallet privacy analysis
    GET  /privacy/wallets/summary                - Summary across all user's wallets
    POST /privacy/monero/set-balance             - Set manual XMR balance for a Monero wallet
    GET  /privacy/approvals/wallets              - List EVM wallets supporting approval checks
    GET  /privacy/approvals/wallet/{wallet_id}   - On-demand per-wallet approval analysis
"""

import logging
import sys
import os
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_utils import verify_session
from config import DATABASE_PATH, CACHE_TTL_WARM
from services.zcash import zcash_service
from services.etherscan import etherscan_service
from services.privacy_detector import privacy_detector
from services.moralis import moralis_service
from services.approval_checker import approval_checker, CHAIN_MAP
from database import save_balance, clear_wallet_balances, get_cache, set_cache

router = APIRouter(prefix="/privacy", tags=["privacy"])
logger = logging.getLogger(__name__)

# Chains that have privacy relevance for the summary endpoint
PRIVACY_RELEVANT_CHAINS = {
    'zcash', 'monero', 'secret_network',
    'ethereum', 'polygon', 'arbitrum', 'bsc'
}


@router.get("/stats")
async def get_privacy_stats(user_id: int = Depends(verify_session)):
    """
    Get chain-wide privacy statistics for supported privacy chains.

    Returns descriptions and network-level data (where available) for
    ZCash, Monero, and Secret Network.
    """
    try:
        # Fetch ZCash shielded pool stats (best-effort, may return None)
        zcash_pool_stats = None
        try:
            zcash_pool_stats = await zcash_service.get_shielded_pool_stats()
        except Exception as e:
            logger.warning(f"Could not fetch ZCash pool stats: {e}")

        return {
            'zcash': {
                'shielded_pool_stats': zcash_pool_stats,
                'description': (
                    'ZCash uses zk-SNARKs for optional privacy via shielded (z-) addresses. '
                    'Transparent (t-) addresses are publicly visible like Bitcoin. '
                    'Funds can be shielded by sending from a t-address to a z-address.'
                ),
                'privacy_type': 'optional',
                'technology': 'zk-SNARKs (Sapling/Orchard)'
            },
            'monero': {
                'always_private': True,
                'description': (
                    'All Monero transactions are private by design using ring signatures, '
                    'stealth addresses, and RingCT. Wallet balances cannot be determined '
                    'from public data. Users must enter their balance manually.'
                ),
                'privacy_type': 'mandatory',
                'technology': 'Ring Signatures + Stealth Addresses + RingCT'
            },
            'secret_network': {
                'description': (
                    'Secret Network encrypts smart contract state using Intel SGX Trusted '
                    'Execution Environments. Wallet (SCRT) balances are public, but smart '
                    'contract interactions and SNIP-20 token balances are private.'
                ),
                'privacy_type': 'selective',
                'technology': 'Intel SGX TEE'
            }
        }
    except Exception as e:
        logger.error(f"Error fetching privacy stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch privacy statistics")


@router.get("/wallet/{wallet_id}/score")
async def get_wallet_privacy_score(wallet_id: int, user_id: int = Depends(verify_session)):
    """
    Get a privacy analysis score for a specific wallet.

    - ZCash wallets: analyzes shielding history via Blockchair
    - Ethereum/Polygon/Arbitrum/BSC wallets: checks Railgun interaction via Etherscan
    - Monero wallets: always score 100 (fully private by design)
    - Secret Network wallets: score 50 (balance public, contracts private)
    - All other chains: score 0 (no privacy features)
    """
    # Look up the wallet and verify it belongs to the current user
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, address, blockchain, user_id FROM wallets WHERE id = ?",
            (wallet_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet = dict(row)
    if wallet['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this wallet")

    address = wallet['address']
    blockchain = wallet['blockchain']

    try:
        if blockchain == 'zcash':
            result = await zcash_service.get_privacy_score(address)
            return result

        elif blockchain in ('ethereum', 'polygon', 'arbitrum', 'bsc'):
            result = await privacy_detector.detect_evm_privacy_usage(address, blockchain, etherscan_service)
            return result

        elif blockchain == 'monero':
            return {
                'address': address,
                'blockchain': 'monero',
                'privacy_score': 100,
                'has_privacy_usage': True,
                'protocol_interactions': ['ring_signatures', 'stealth_addresses', 'ringct'],
                'description': 'Monero is fully private by design.',
                'recommendation': 'Monero provides the strongest privacy guarantees of any major cryptocurrency.'
            }

        elif blockchain == 'secret_network':
            return {
                'address': address,
                'blockchain': 'secret_network',
                'privacy_score': 50,
                'has_privacy_usage': True,
                'protocol_interactions': ['sgx_tee'],
                'description': 'SCRT wallet balance is public, but contract interactions are encrypted.',
                'recommendation': (
                    'Use SNIP-20 tokens and Secret dApps to keep your DeFi activity private. '
                    'Your SCRT balance is visible on-chain.'
                )
            }

        else:
            return {
                'address': address,
                'blockchain': blockchain,
                'privacy_score': 0,
                'has_privacy_usage': False,
                'protocol_interactions': [],
                'description': 'No privacy features detected for this chain.',
                'recommendation': (
                    'This blockchain does not have native privacy features. '
                    'Consider using privacy-preserving tools or chains for sensitive transactions.'
                )
            }

    except Exception as e:
        logger.error(f"Error computing privacy score for wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute privacy score")


@router.get("/wallets/summary")
async def get_wallets_privacy_summary(user_id: int = Depends(verify_session)):
    """
    Get a privacy summary across all user's wallets.

    Returns a list of wallets on privacy-relevant chains with their scores.
    Lightweight: returns stored metadata + static scores without making
    external API calls (use /wallet/{id}/score for detailed on-demand analysis).
    """
    try:
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, address, blockchain, label
                   FROM wallets
                   WHERE user_id = ? AND blockchain IN
                   ('zcash', 'monero', 'secret_network', 'ethereum', 'polygon', 'arbitrum', 'bsc')
                   ORDER BY blockchain, id""",
                (user_id,)
            )
            rows = await cursor.fetchall()

        wallets = [dict(row) for row in rows]

        result = []
        for wallet in wallets:
            blockchain = wallet['blockchain']

            # Static scores for clearly-defined chains
            if blockchain == 'monero':
                score = 100
                description = 'Fully private by design (ring signatures + stealth addresses + RingCT)'
            elif blockchain == 'secret_network':
                score = 50
                description = 'Balance is public; smart contract interactions are encrypted via SGX'
            elif blockchain == 'zcash':
                score = None  # Requires on-demand analysis
                description = 'Privacy depends on use of shielded (z-address) transactions'
            else:
                score = None  # Requires on-demand analysis via Etherscan
                description = f'Privacy depends on interaction with privacy protocols (e.g. Railgun)'

            result.append({
                'wallet_id': wallet['id'],
                'address': wallet['address'],
                'blockchain': blockchain,
                'label': wallet.get('label'),
                'static_privacy_score': score,
                'description': description,
                'detail_endpoint': f'/privacy/wallet/{wallet["id"]}/score'
            })

        return {
            'wallets': result,
            'total': len(result),
            'note': (
                'static_privacy_score is null for chains requiring on-demand analysis. '
                'Use the detail_endpoint for a full per-wallet score.'
            )
        }

    except Exception as e:
        logger.error(f"Error fetching wallets privacy summary for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch privacy summary")


# ── Token Approval Security ──────────────────────────────────────────

# EVM chains that support Moralis approval checks
APPROVAL_CHAINS = set(CHAIN_MAP.keys())


@router.get("/approvals/wallets")
async def get_approval_wallets(user_id: int = Depends(verify_session)):
    """
    List EVM wallets that support token approval checks.

    Lightweight — no external API calls. Returns wallet metadata only.
    """
    try:
        placeholders = ','.join(f"'{c}'" for c in APPROVAL_CHAINS)
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT id, address, blockchain, label
                    FROM wallets
                    WHERE user_id = ? AND blockchain IN ({placeholders})
                    ORDER BY blockchain, id""",
                (user_id,)
            )
            rows = await cursor.fetchall()

        wallets = []
        for row in rows:
            w = dict(row)
            wallets.append({
                'wallet_id': w['id'],
                'address': w['address'],
                'blockchain': w['blockchain'],
                'label': w.get('label'),
            })

        return {'wallets': wallets, 'total': len(wallets)}

    except Exception as e:
        logger.error(f"Error listing approval wallets for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list wallets")


@router.get("/approvals/wallet/{wallet_id}")
async def get_wallet_approvals(wallet_id: int, user_id: int = Depends(verify_session)):
    """
    Fetch token approvals for a specific EVM wallet via Moralis.

    Results are cached for 1 hour (CACHE_TTL_WARM).
    Requires a Moralis API key to be configured.
    """
    # Look up the wallet and verify ownership
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, address, blockchain, user_id FROM wallets WHERE id = ?",
            (wallet_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet = dict(row)
    if wallet['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this wallet")

    blockchain = wallet['blockchain']
    if blockchain not in APPROVAL_CHAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Token approval checks are not supported for {blockchain}"
        )

    # Check Moralis API key
    api_key = await moralis_service._get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Moralis API key not configured. Add it in Settings > API Keys."
        )

    # Check cache
    cache_key = f"approvals:{blockchain}:{wallet['address'].lower()}"
    cached = await get_cache(cache_key, user_id=user_id)
    if cached is not None:
        return cached

    # Fetch from Moralis
    result = await approval_checker.fetch_approvals(wallet['address'], blockchain, api_key)

    if 'error' in result and not result['approvals']:
        raise HTTPException(status_code=502, detail=result['error'])

    response = {
        'wallet_id': wallet_id,
        'address': wallet['address'],
        'blockchain': blockchain,
        **result,
    }

    # Cache successful results
    await set_cache(cache_key, response, CACHE_TTL_WARM, user_id=user_id)

    return response


class MoneroBalanceUpdate(BaseModel):
    wallet_id: int
    balance: float


@router.post("/monero/set-balance")
async def set_monero_balance(
    data: MoneroBalanceUpdate,
    user_id: int = Depends(verify_session)
):
    """
    Set manual XMR balance for a Monero wallet.

    Since Monero is fully private, balances cannot be fetched from public APIs.
    This endpoint allows users to manually record their XMR holdings.
    """
    wallet_id = data.wallet_id
    amount_xmr = data.balance

    if amount_xmr < 0:
        raise HTTPException(status_code=400, detail="Balance cannot be negative")

    # Verify the wallet exists and belongs to the current user
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, address, blockchain, user_id FROM wallets WHERE id = ?",
            (wallet_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet = dict(row)
    if wallet['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this wallet")

    if wallet['blockchain'] != 'monero':
        raise HTTPException(
            status_code=400,
            detail=f"Wallet is not a Monero wallet (blockchain: {wallet['blockchain']})"
        )

    try:
        await clear_wallet_balances(wallet_id)
        await save_balance(wallet_id, str(amount_xmr), 'XMR')

        return {
            'success': True,
            'wallet_id': wallet_id,
            'address': wallet['address'],
            'balance_xmr': amount_xmr,
            'message': f'Monero balance updated to {amount_xmr} XMR'
        }
    except Exception as e:
        logger.error(f"Error setting Monero balance for wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update balance")
