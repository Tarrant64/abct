"""
Privacy Router - ZK Privacy and privacy protocol endpoints.

Endpoints:
    GET  /privacy/stats                          - Chain-wide privacy statistics
    GET  /privacy/wallet/{wallet_id}/score        - Per-wallet privacy analysis
    GET  /privacy/wallets/summary                - Summary across all user's wallets
    POST /privacy/monero/set-balance             - Set manual XMR balance for a Monero wallet
    GET  /privacy/approvals/wallets              - List EVM wallets supporting approval checks
    GET  /privacy/approvals/wallet/{wallet_id}   - On-demand per-wallet approval analysis
    POST /privacy/scan-poisoning                 - Scan transaction history for address poisoning
    POST /privacy/scan-cardano-shield            - Scan Cardano transactions against Shield threat feed
"""

import json
import logging
import sys
import os
from datetime import datetime, timezone
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
from services.cardano_shield import cardano_shield
from services.cardano_token_registry import cardano_token_registry
from database import save_balance, clear_wallet_balances, get_cache, set_cache

router = APIRouter(prefix="/privacy", tags=["privacy"])
logger = logging.getLogger(__name__)

# Chains that have privacy relevance for the summary endpoint
PRIVACY_RELEVANT_CHAINS = {
    'zcash', 'monero', 'secret_network',
    'ethereum', 'polygon', 'arbitrum', 'bsc'
}

# Dust thresholds per chain for address poisoning detection
DUST_THRESHOLDS = {
    'ethereum': 0.001, 'polygon': 0.001, 'base': 0.001,
    'arbitrum': 0.001, 'bsc': 0.001, 'cardano': 2.0,
    'solana': 0.001, 'bitcoin': 0.00001, 'algorand': 0.001,
}

# Cardano Shield: suspicious naming pattern heuristics
SUSPICIOUS_PREFIXES = ['a', 'w']       # aSNEK, wAGENT (typosquat wrapped/alt tokens)
SUSPICIOUS_KEYWORDS = [
    'reward', 'ticket', 'airdrop', 'claim', 'free',
    'bonus', 'gift', 'prize', 'winner', 'giveaway'
]


@router.get("/stats")
async def get_privacy_stats(user_id: int = Depends(verify_session)):
    """
    Get chain-wide privacy statistics for supported privacy chains.

    Returns descriptions and network-level data (where available) for
    ZCash, Monero, and Secret Network.
    """
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
        chains_list = list(PRIVACY_RELEVANT_CHAINS)
        placeholders = ','.join('?' for _ in chains_list)
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT id, address, blockchain, label
                   FROM wallets
                   WHERE user_id = ? AND blockchain IN ({placeholders})
                   ORDER BY blockchain, id""",
                (user_id, *chains_list)
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
        chains_list = list(APPROVAL_CHAINS)
        placeholders = ','.join('?' for _ in chains_list)
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT id, address, blockchain, label
                    FROM wallets
                    WHERE user_id = ? AND blockchain IN ({placeholders})
                    ORDER BY blockchain, id""",
                (user_id, *chains_list)
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


# ── Address Poisoning Scanner ────────────────────────────────────────


def _is_lookalike(addr: str, known: str, prefix_len: int = 4, suffix_len: int = 4) -> bool:
    """Check if addr mimics known by sharing first N and last N characters."""
    if not addr or not known or addr == known:
        return False
    if len(addr) < prefix_len + suffix_len or len(known) < prefix_len + suffix_len:
        return False
    return (addr[:prefix_len] == known[:prefix_len]
            and addr[-suffix_len:] == known[-suffix_len:])


async def _scan_address_poisoning(user_id: int) -> dict:
    """Scan all user transaction history for address poisoning patterns."""
    ROW_CAP = 50_000

    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row

        # 1. Get all user wallets
        cursor = await db.execute(
            "SELECT id, address, blockchain, label FROM wallets WHERE user_id = ?",
            (user_id,)
        )
        wallets = [dict(r) for r in await cursor.fetchall()]

        if not wallets:
            return {
                'wallets_scanned': 0,
                'transactions_analyzed': 0,
                'suspicious_count': 0,
                'high_confidence': [],
                'medium_confidence': [],
                'low_confidence': [],
                'report_text': _build_report([], [], [], 0, 0, 0),
                'scan_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
            }

        wallet_map = {}  # id -> {address, blockchain, label}
        own_addresses = set()  # user's own wallet addresses (lowercased)
        for w in wallets:
            wallet_map[w['id']] = w
            own_addresses.add(w['address'].lower())

        wallet_ids = [w['id'] for w in wallets]
        placeholders = ','.join('?' for _ in wallet_ids)

        # 2. Query V1 transaction_history
        cursor = await db.execute(
            f"""SELECT wallet_id, blockchain, tx_hash, tx_time, direction,
                       amount, token_symbol, from_address, to_address
                FROM transaction_history
                WHERE user_id = ?
                ORDER BY tx_time DESC
                LIMIT ?""",
            (user_id, ROW_CAP)
        )
        v1_rows = [dict(r) for r in await cursor.fetchall()]

        # 3. Query V2 engine_events
        cursor = await db.execute(
            f"""SELECT chain, tx_id, direction, amount, asset_id,
                       counterparty, block_time, account_id
                FROM engine_events
                WHERE user_id = ?
                ORDER BY block_time DESC
                LIMIT ?""",
            (user_id, ROW_CAP)
        )
        v2_rows = [dict(r) for r in await cursor.fetchall()]

    # 4. Build "known good" address book — addresses user has SENT to
    known_good = set(own_addresses)
    for row in v1_rows:
        if row.get('direction') == 'sent' and row.get('to_address'):
            known_good.add(row['to_address'].lower())
    for row in v2_rows:
        if row.get('direction') == 'out' and row.get('counterparty'):
            known_good.add(row['counterparty'].lower())

    # 5. Normalize incoming transactions from both sources, dedup by tx_hash
    seen_hashes = set()
    incoming_txs = []

    for row in v1_rows:
        if row.get('direction') != 'received':
            continue
        tx_hash = (row.get('tx_hash') or '').lower()
        if tx_hash in seen_hashes:
            continue
        seen_hashes.add(tx_hash)
        sender = (row.get('from_address') or '').lower()
        if not sender:
            continue
        try:
            amount = float(row.get('amount') or 0)
        except (ValueError, TypeError):
            amount = 0
        wallet = wallet_map.get(row.get('wallet_id'), {})
        incoming_txs.append({
            'tx_hash': row.get('tx_hash', ''),
            'sender': sender,
            'amount': amount,
            'token': row.get('token_symbol') or '',
            'blockchain': row.get('blockchain') or '',
            'tx_time': row.get('tx_time') or '',
            'wallet_label': wallet.get('label') or '',
            'wallet_address': wallet.get('address') or '',
        })

    for row in v2_rows:
        if row.get('direction') != 'in':
            continue
        tx_hash = (row.get('tx_id') or '').lower()
        if tx_hash in seen_hashes:
            continue
        seen_hashes.add(tx_hash)
        sender = (row.get('counterparty') or '').lower()
        if not sender:
            continue
        try:
            amount = float(row.get('amount') or 0)
        except (ValueError, TypeError):
            amount = 0
        chain = row.get('chain') or ''
        asset_id = row.get('asset_id') or ''
        token = chain.upper() if asset_id == 'native' else asset_id
        # Resolve wallet label from account_id
        account_id = (row.get('account_id') or '').lower()
        wallet_label = ''
        wallet_address = ''
        for w in wallets:
            if w['address'].lower() == account_id:
                wallet_label = w.get('label') or ''
                wallet_address = w['address']
                break
        bt = row.get('block_time')
        tx_time = datetime.fromtimestamp(bt, tz=timezone.utc).strftime('%Y-%m-%d %H:%M') if bt else ''
        incoming_txs.append({
            'tx_hash': row.get('tx_id', ''),
            'sender': sender,
            'amount': amount,
            'token': token,
            'blockchain': chain,
            'tx_time': tx_time,
            'wallet_label': wallet_label,
            'wallet_address': wallet_address,
        })

    # 6. Detect suspicious transactions
    high_confidence = []
    medium_confidence = []
    low_confidence = []

    for tx in incoming_txs:
        sender = tx['sender']

        # Skip if sender is in known_good
        if sender in known_good:
            continue

        chain = tx['blockchain']
        dust_threshold = DUST_THRESHOLDS.get(chain, 0.001)
        amount = tx['amount']

        is_dust = 0 < amount < dust_threshold
        is_zero = amount == 0

        # Check lookalike against all known_good addresses
        mimics = None
        for kg in known_good:
            if _is_lookalike(sender, kg):
                mimics = kg
                break

        if not is_dust and not is_zero and not mimics:
            continue

        entry = {
            'wallet_label': tx['wallet_label'],
            'wallet_address': tx['wallet_address'],
            'chain': chain,
            'tx_time': tx['tx_time'],
            'tx_hash': tx['tx_hash'],
            'sender': tx['sender'],
            'amount': tx['amount'],
            'token': tx['token'],
            'mimics': mimics,
        }

        if mimics and (is_dust or is_zero):
            entry['reason'] = 'Lookalike + ' + ('Zero-value' if is_zero else 'Dust')
            high_confidence.append(entry)
        elif mimics:
            entry['reason'] = 'Lookalike address'
            medium_confidence.append(entry)
        elif is_zero:
            entry['reason'] = 'Zero-value transfer'
            medium_confidence.append(entry)
        elif is_dust:
            entry['reason'] = 'Dust from unknown sender'
            low_confidence.append(entry)

    total_suspicious = len(high_confidence) + len(medium_confidence) + len(low_confidence)
    total_txs = len(incoming_txs) + len([r for r in v1_rows if r.get('direction') == 'sent']) + len([r for r in v2_rows if r.get('direction') == 'out'])

    report = _build_report(
        high_confidence, medium_confidence, low_confidence,
        len(wallets), total_txs, total_suspicious
    )

    return {
        'wallets_scanned': len(wallets),
        'transactions_analyzed': total_txs,
        'suspicious_count': total_suspicious,
        'high_confidence': high_confidence,
        'medium_confidence': medium_confidence,
        'low_confidence': low_confidence,
        'report_text': report,
        'scan_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }


def _build_report(high, medium, low, wallets_count, tx_count, suspicious_count) -> str:
    """Build plaintext report for address poisoning scan."""
    lines = []
    lines.append('=== ABCT Address Poisoning Scan Report ===')
    lines.append(f'Date: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    lines.append(f'Wallets scanned: {wallets_count}')
    lines.append(f'Transactions analyzed: {tx_count:,}')
    lines.append(f'Suspicious items found: {suspicious_count}')
    lines.append('')

    def _format_entries(entries, label):
        lines.append(f'--- {label} ---')
        lines.append('')
        if not entries:
            lines.append('  (none)')
            lines.append('')
            return
        for i, e in enumerate(entries, 1):
            lines.append(f'[{i}] {e.get("reason", "Suspicious")}')
            if e.get('wallet_label') or e.get('wallet_address'):
                addr_short = e['wallet_address']
                if len(addr_short) > 12:
                    addr_short = addr_short[:6] + '...' + addr_short[-4:]
                label = e.get('wallet_label') or 'Unnamed'
                lines.append(f'    Wallet: {label} ({addr_short})')
            lines.append(f'    Chain: {e.get("chain", "unknown")}')
            if e.get('tx_time'):
                lines.append(f'    Date: {e["tx_time"]}')
            if e.get('tx_hash'):
                tx_display = e['tx_hash']
                if len(tx_display) > 16:
                    tx_display = tx_display[:10] + '...'
                lines.append(f'    TX: {tx_display}')
            lines.append(f'    From: {e.get("sender", "unknown")}')
            amt = e.get('amount', 0)
            token = e.get('token', '')
            lines.append(f'    Amount: {amt} {token}')
            if e.get('mimics'):
                lines.append(f'    Mimics: {e["mimics"]}')
                lines.append(f'    WARNING: This address matches the first 4 and last 4 characters of an address you have sent funds to.')
            lines.append('')

    _format_entries(high, 'HIGH CONFIDENCE')
    _format_entries(medium, 'MEDIUM CONFIDENCE')
    _format_entries(low, 'LOW CONFIDENCE')

    lines.append('=== End of Report ===')
    return '\n'.join(lines)


@router.post("/scan-poisoning")
async def scan_address_poisoning(user_id: int = Depends(verify_session)):
    """
    Scan all user transaction history for address poisoning attempts.

    Analyzes V1 transaction_history and V2 engine_events locally (no external
    API calls) to detect dust attacks, zero-value transfers, and lookalike
    addresses that mimic addresses the user has previously sent funds to.
    """
    try:
        result = await _scan_address_poisoning(user_id)
        return result
    except Exception as e:
        logger.error(f"Error scanning for address poisoning for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to run address poisoning scan")


# ── Cardano Shield Transaction Scanner ──────────────────────────────


def _check_suspicious_name(name: str) -> Optional[str]:
    """Check if a token name matches suspicious patterns. Returns reason or None."""
    if not name:
        return None
    name_lower = name.lower()

    # Check suspicious keyword matches
    for kw in SUSPICIOUS_KEYWORDS:
        if kw in name_lower:
            return f'Suspicious keyword "{kw}" in token name'

    # Check prefix typosquat (e.g., aSNEK mimicking SNEK)
    for prefix in SUSPICIOUS_PREFIXES:
        if name.startswith(prefix) and len(name) > 1 and name[1].isupper():
            return f'Possible typosquat prefix "{prefix}" (e.g., {name} vs {name[1:]})'

    return None


def _extract_sender(raw_data: dict, own_addresses: set) -> Optional[str]:
    """Extract sender address from Blockfrost raw transaction data.

    Cardano engine_events have NULL counterparty, so we look at the inputs
    array in the raw Blockfrost tx data and pick the first input address
    that isn't one of the user's own wallets.
    """
    if not raw_data:
        return None
    inputs = raw_data.get('inputs', [])
    for inp in inputs:
        addr = inp.get('address', '')
        if addr and addr.lower() not in own_addresses:
            return addr
    # If all inputs are own addresses, return the first input anyway
    if inputs:
        return inputs[0].get('address', '')
    return None


def _build_shield_report(
    high: list, medium: list, low: list,
    wallets_count: int, tx_count: int, suspicious_count: int,
    registry_stats: dict
) -> str:
    """Build plaintext report for Cardano Shield scan."""
    lines = []
    lines.append('=== ABCT Cardano Shield Scan Report ===')
    lines.append('Powered by Cardano Shield (Apache 2.0) by AdaBox.io')
    lines.append('Enhanced for retrospective analysis by ABCT')
    lines.append('')
    lines.append(f'Date: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    lines.append(f'Cardano wallets scanned: {wallets_count}')
    lines.append(f'Transactions analyzed: {tx_count:,}')
    lines.append(f'Suspicious items found: {suspicious_count}')
    lines.append('')
    lines.append(f'CF Token Registry: {registry_stats.get("registered", 0)} registered, '
                 f'{registry_stats.get("unregistered", 0)} unregistered out of '
                 f'{registry_stats.get("total_checked", 0)} unique tokens checked')
    shield_stats = cardano_shield.get_threat_feed_stats()
    lines.append(f'Shield Feed: {shield_stats.get("blacklisted_policies", 0)} blacklisted policies, '
                 f'{shield_stats.get("whitelisted_addresses", 0)} whitelisted addresses')
    lines.append('')

    def _format_entries(entries, label):
        lines.append(f'--- {label} ---')
        lines.append('')
        if not entries:
            lines.append('  (none)')
            lines.append('')
            return
        for i, e in enumerate(entries, 1):
            lines.append(f'[{i}] {e.get("reason", "Suspicious")}')
            if e.get('wallet_label') or e.get('wallet_address'):
                addr_short = e.get('wallet_address', '')
                if len(addr_short) > 16:
                    addr_short = addr_short[:8] + '...' + addr_short[-6:]
                wlabel = e.get('wallet_label') or 'Unnamed'
                lines.append(f'    Wallet: {wlabel} ({addr_short})')
            if e.get('tx_time'):
                lines.append(f'    Date: {e["tx_time"]}')
            if e.get('tx_id'):
                tx_display = e['tx_id']
                if len(tx_display) > 16:
                    tx_display = tx_display[:10] + '...'
                lines.append(f'    TX: {tx_display}')
            if e.get('sender'):
                sender = e['sender']
                if len(sender) > 20:
                    sender = sender[:10] + '...' + sender[-6:]
                lines.append(f'    From: {sender}')
            if e.get('token_name'):
                lines.append(f'    Token: {e["token_name"]}')
            if e.get('policy_id'):
                pid = e['policy_id']
                if len(pid) > 16:
                    pid = pid[:10] + '...' + pid[-6:]
                lines.append(f'    Policy: {pid}')
            if e.get('blacklist_match'):
                lines.append(f'    Shield Match: {e["blacklist_match"]}')
            if e.get('cf_registered') is not None:
                lines.append(f'    CF Registered: {"Yes" if e["cf_registered"] else "No"}')
            lines.append('')

    _format_entries(high, 'HIGH RISK — Blacklisted by Cardano Shield')
    _format_entries(medium, 'MEDIUM RISK — Suspicious pattern + unregistered')
    _format_entries(low, 'LOW RISK — Unregistered token from unknown sender')

    lines.append('=== End of Report ===')
    return '\n'.join(lines)


async def _scan_cardano_shield(user_id: int) -> dict:
    """Scan Cardano transaction history against Shield threat feed + CF Token Registry."""
    ROW_CAP = 50_000

    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row

        # 1. Get Cardano wallets
        cursor = await db.execute(
            "SELECT id, address, blockchain, label FROM wallets WHERE user_id = ? AND blockchain = 'cardano'",
            (user_id,)
        )
        wallets = [dict(r) for r in await cursor.fetchall()]

        if not wallets:
            return {
                'wallets_scanned': 0,
                'transactions_analyzed': 0,
                'suspicious_count': 0,
                'report_text': _build_shield_report([], [], [], 0, 0, 0, {}),
                'scan_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
            }

        own_addresses = set()
        wallet_map = {}
        for w in wallets:
            own_addresses.add(w['address'].lower())
            wallet_map[w['address'].lower()] = w

        # 2. Query engine_events for Cardano
        cursor = await db.execute(
            """SELECT chain, tx_id, direction, amount, asset_id,
                      counterparty, block_time, account_id, event_type
               FROM engine_events
               WHERE user_id = ? AND chain = 'cardano'
               ORDER BY block_time DESC
               LIMIT ?""",
            (user_id, ROW_CAP)
        )
        events = [dict(r) for r in await cursor.fetchall()]

    # 3. Collect incoming token events and their tx_ids for raw data lookup
    incoming_events = []
    tx_ids_needed = set()
    for ev in events:
        if ev.get('direction') != 'in':
            continue
        asset_id = ev.get('asset_id', '')
        if asset_id == 'native':
            continue  # Skip ADA transfers
        incoming_events.append(ev)
        tx_ids_needed.add(ev['tx_id'])

    # 4. Batch-fetch engine_tx_raw for sender extraction
    from engine.db import get_tx_raw_batch
    tx_raw_map = await get_tx_raw_batch('cardano', list(tx_ids_needed))

    # 5. Extract unique policy IDs and build CF registry subjects
    policy_id_set = set()
    subject_map = {}  # subject -> (policy_id, asset_name_hex)
    for ev in incoming_events:
        asset_id = ev.get('asset_id', '')
        if '.' in asset_id:
            parts = asset_id.split('.', 1)
            policy_id = parts[0]
            asset_name_hex = parts[1] if len(parts) > 1 else ''
        else:
            # asset_id might be just the policy ID with no asset name
            policy_id = asset_id
            asset_name_hex = ''

        if len(policy_id) == 56 and all(c in '0123456789abcdef' for c in policy_id.lower()):
            policy_id_set.add(policy_id.lower())
            subject = (policy_id + asset_name_hex).lower()
            subject_map[subject] = (policy_id.lower(), asset_name_hex.lower())

    # 6. Cross-reference policy IDs against Shield blacklist (sync, O(1))
    blacklisted_pids = {}
    for pid in policy_id_set:
        match = cardano_shield.check_policy_id(pid)
        if match:
            blacklisted_pids[pid] = match

    # 7. Batch-query CF Token Registry
    subjects_list = list(subject_map.keys())
    registry_results = {}
    if subjects_list:
        registry_results = await cardano_token_registry.batch_check(subjects_list)

    registry_stats = {
        'total_checked': len(subjects_list),
        'registered': sum(1 for v in registry_results.values() if v),
        'unregistered': sum(1 for v in registry_results.values() if not v),
    }

    # 8. Score each incoming token event
    high_confidence = []
    medium_confidence = []
    low_confidence = []

    for ev in incoming_events:
        asset_id = ev.get('asset_id', '')
        if '.' in asset_id:
            parts = asset_id.split('.', 1)
            policy_id = parts[0].lower()
            asset_name_hex = parts[1].lower() if len(parts) > 1 else ''
        else:
            policy_id = asset_id.lower()
            asset_name_hex = ''

        if len(policy_id) != 56:
            continue

        subject = policy_id + asset_name_hex
        is_cf_registered = registry_results.get(subject, False)

        # Decode asset name for display
        try:
            token_name = bytes.fromhex(asset_name_hex).decode('utf-8') if asset_name_hex else ''
        except (ValueError, UnicodeDecodeError):
            token_name = asset_name_hex

        # Extract sender from raw tx data
        raw_data = tx_raw_map.get(ev['tx_id'])
        sender = _extract_sender(raw_data, own_addresses)

        # Check if sender is whitelisted (DEX/marketplace)
        sender_whitelisted = False
        if sender:
            wl_label = cardano_shield.check_address(sender)
            if wl_label:
                sender_whitelisted = True

        # Resolve wallet info
        account_id = (ev.get('account_id') or '').lower()
        wallet_info = wallet_map.get(account_id, {})

        bt = ev.get('block_time')
        tx_time = datetime.fromtimestamp(bt, tz=timezone.utc).strftime('%Y-%m-%d %H:%M') if bt else ''

        entry = {
            'wallet_label': wallet_info.get('label', ''),
            'wallet_address': wallet_info.get('address', ''),
            'tx_id': ev.get('tx_id', ''),
            'tx_time': tx_time,
            'sender': sender or '',
            'token_name': token_name,
            'policy_id': policy_id,
            'cf_registered': is_cf_registered,
        }

        # HIGH: Policy ID in Shield blacklist
        if policy_id in blacklisted_pids:
            entry['reason'] = f'Blacklisted token: {blacklisted_pids[policy_id]}'
            entry['blacklist_match'] = blacklisted_pids[policy_id]
            high_confidence.append(entry)
            continue

        # Skip if CF-registered or sender is whitelisted
        if is_cf_registered or sender_whitelisted:
            continue

        # MEDIUM: Suspicious naming pattern + NOT in CF registry
        name_suspicion = _check_suspicious_name(token_name)
        if name_suspicion:
            entry['reason'] = name_suspicion
            medium_confidence.append(entry)
            continue

        # LOW: Not in CF registry + sender not whitelisted
        if not is_cf_registered and not sender_whitelisted:
            entry['reason'] = 'Unregistered token from unknown sender'
            low_confidence.append(entry)

    total_suspicious = len(high_confidence) + len(medium_confidence) + len(low_confidence)

    report = _build_shield_report(
        high_confidence, medium_confidence, low_confidence,
        len(wallets), len(events), total_suspicious,
        registry_stats
    )

    return {
        'wallets_scanned': len(wallets),
        'transactions_analyzed': len(events),
        'suspicious_count': total_suspicious,
        'report_text': report,
        'scan_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }


@router.post("/scan-cardano-shield")
async def scan_cardano_shield(user_id: int = Depends(verify_session)):
    """
    Scan Cardano transaction history against the Cardano Shield threat feed.

    Cross-references incoming token events with the Cardano Shield blacklist
    (370+ scam token policy IDs) and the Cardano Foundation Token Registry
    (7,800+ verified tokens) to identify potentially malicious tokens.
    """
    try:
        result = await _scan_cardano_shield(user_id)
        return result
    except Exception as e:
        logger.error(f"Error running Cardano Shield scan for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to run Cardano Shield scan")


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
        await save_balance(wallet_id, f"{amount_xmr:.12f}", 'XMR')

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
