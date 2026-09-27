"""
BTC Karma Bitcoin Staking Tracking

BTC Karma (https://staking.btckarma.io) is a "bridgeless" Bitcoin staking
protocol whose rewards (KARMA) are paid on Cardano. A stake is a normal
Bitcoin transaction, so the staked amount is read straight from the Bitcoin
chain through the public, keyless Esplora API (mempool.space, blockstream.info
fallback). No BTC Karma account, session or signature is needed.

On-chain shape of a stake (observed on mainnet, 2026-09):
- inputs are spent from the user's own Bitcoin address;
- one P2WSH output locks the staked sats in a per-stake vault script
  (the script itself is only revealed when the vault is spent);
- one OP_RETURN output carries  b"CB|" + hex(blake2b-512(cardano_address))
  where cardano_address is the bech32 Cardano reward address the user
  verified with CIP-8. This binds the BTC stake to the Cardano wallet.

A vault output that is still unspent is an active stake. Once the user
unstakes, the vault is spent and the position drops out on its own.

Not available from public data: unlock time, lock-script version and KARMA
reward balances. Those live only in BTC Karma's own backend (session-bound
Next.js server actions), so they are deliberately not queried here.
"""

import hashlib
import logging
import re
from typing import Dict, Iterable, List, Optional

from config import BLOCKSTREAM_BASE_URL, MEMPOOL_BASE_URL
from services.http_client import get_client
from services.logokit_service import logokit_service

logger = logging.getLogger(__name__)

PROTOCOL_NAME = 'BTC Karma'
STAKING_URL = 'https://staking.btckarma.io'
REWARD_TOKEN = 'KARMA'
OP_RETURN_TAG = b'CB|'
SATS_PER_BTC = 100_000_000

# Esplora-compatible APIs, tried in order.
ESPLORA_BASE_URLS = (MEMPOOL_BASE_URL, BLOCKSTREAM_BASE_URL)
REQUEST_TIMEOUT = 15.0
# /address/{a}/txs returns 25 confirmed txs per page; a staking wallet is
# low-traffic, so 4 pages (100 txs) is plenty and bounds the call count.
MAX_TX_PAGES = 4

# Mainnet only: bech32/bech32m (lowercase) or base58 P2PKH/P2SH.
_BTC_ADDRESS_RE = re.compile(
    r'^(bc1[02-9ac-hj-np-z]{11,71}|[13][1-9A-HJ-NP-Za-km-z]{25,34})$'
)
_TXID_RE = re.compile(r'^[0-9a-f]{64}$')


class BtcKarmaUnavailable(Exception):
    """Raised when no Esplora API could answer."""


def is_valid_btc_address(address: str) -> bool:
    """Format check before an address is placed in an API URL path."""
    return bool(address) and bool(_BTC_ADDRESS_RE.match(address))


def cardano_binding_hash(cardano_address: str) -> str:
    """The commitment BTC Karma writes after 'CB|' for a Cardano address."""
    return hashlib.blake2b(cardano_address.encode('utf-8'), digest_size=64).hexdigest()


def parse_op_return(scriptpubkey_hex: str) -> Optional[bytes]:
    """Return the pushed data of an OP_RETURN script, or None."""
    try:
        script = bytes.fromhex(scriptpubkey_hex or '')
    except ValueError:
        return None
    if len(script) < 2 or script[0] != 0x6a:
        return None
    op = script[1]
    if 1 <= op <= 75:
        start, length = 2, op
    elif op == 0x4c and len(script) >= 3:  # OP_PUSHDATA1
        start, length = 3, script[2]
    elif op == 0x4d and len(script) >= 4:  # OP_PUSHDATA2
        start, length = 4, int.from_bytes(script[2:4], 'little')
    else:
        return None
    data = script[start:start + length]
    return data if len(data) == length else None


def find_stake_outputs(txs: Iterable[dict], address: str) -> List[dict]:
    """Pick BTC Karma stake vault outputs out of an address's transactions.

    A stake tx spends from `address`, carries a 'CB|' OP_RETURN and pays a
    P2WSH vault. Spent/unspent status is checked separately.
    """
    stakes = []
    for tx in txs:
        vins = tx.get('vin') or []
        if not any((vin.get('prevout') or {}).get('scriptpubkey_address') == address for vin in vins):
            continue

        commitment = None
        for out in tx.get('vout') or []:
            if out.get('scriptpubkey_type') != 'op_return':
                continue
            data = parse_op_return(out.get('scriptpubkey', ''))
            if data and data.startswith(OP_RETURN_TAG):
                commitment = data[len(OP_RETURN_TAG):].decode('ascii', errors='replace').lower()
                break
        if commitment is None:
            continue

        status = tx.get('status') or {}
        for vout_index, out in enumerate(tx.get('vout') or []):
            if out.get('scriptpubkey_type') != 'v0_p2wsh':
                continue
            if out.get('scriptpubkey_address') == address:
                continue
            stakes.append({
                'txid': tx.get('txid'),
                'vout': vout_index,
                'sats': int(out.get('value') or 0),
                'vault_address': out.get('scriptpubkey_address'),
                'cardano_commitment': commitment,
                'confirmed': bool(status.get('confirmed')),
                'block_height': status.get('block_height'),
                'block_time': status.get('block_time'),
            })
    return stakes


async def _esplora_get(path: str):
    """GET an Esplora path, falling back across providers. Returns parsed JSON."""
    client = get_client('btc_karma_esplora', timeout=REQUEST_TIMEOUT)
    last_error = None
    for base_url in ESPLORA_BASE_URLS:
        try:
            resp = await client.get(f"{base_url}{path}", timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            last_error = f"{base_url} HTTP {resp.status_code}"
        except Exception as e:
            last_error = f"{base_url} {type(e).__name__}: {e}"
        logger.warning(f"[BTC Karma] Esplora request failed: {last_error}")
    raise BtcKarmaUnavailable(last_error or 'no Esplora provider answered')


async def _fetch_address_txs(address: str) -> List[dict]:
    """All transactions for an address (mempool + up to MAX_TX_PAGES confirmed pages)."""
    txs = list(await _esplora_get(f"/address/{address}/txs"))
    confirmed = [t for t in txs if (t.get('status') or {}).get('confirmed')]
    pages = 1
    while len(confirmed) >= 25 * pages and pages < MAX_TX_PAGES:
        last_txid = confirmed[-1].get('txid', '')
        if not _TXID_RE.match(last_txid):
            break
        page = await _esplora_get(f"/address/{address}/txs/chain/{last_txid}")
        if not page:
            break
        txs.extend(page)
        confirmed.extend(page)
        pages += 1
    return txs


async def _is_unspent(txid: str, vout: int) -> bool:
    if not _TXID_RE.match(txid or ''):
        return False
    data = await _esplora_get(f"/tx/{txid}/outspend/{int(vout)}")
    return not data.get('spent', False)


def _short(address: str) -> str:
    return f"{address[:12]}...{address[-6:]}" if len(address) > 24 else address


async def get_btc_karma_staking(
    btc_address: str, cardano_wallets: Optional[List[dict]] = None
) -> Optional[Dict]:
    """Active BTC Karma stakes funded from `btc_address`.

    `cardano_wallets` are the user's tracked Cardano wallets ({address, label});
    a stake whose OP_RETURN commitment matches one of them is labelled with it.

    Returns a protocol dict in the /defi/staking shape, or None when the
    address has no active stake. Raises BtcKarmaUnavailable on API failure
    and ValueError on a malformed address.
    """
    if not is_valid_btc_address(btc_address):
        raise ValueError('invalid Bitcoin address')

    txs = await _fetch_address_txs(btc_address)
    candidates = find_stake_outputs(txs, btc_address)

    active = []
    for stake in candidates:
        if await _is_unspent(stake['txid'], stake['vout']):
            active.append(stake)

    if not active:
        return None

    bindings = {}
    for wallet in cardano_wallets or []:
        addr = wallet.get('address') or ''
        if addr:
            bindings[cardano_binding_hash(addr)] = wallet.get('label') or _short(addr)

    positions = []
    bound_to = []
    for stake in active:
        label = bindings.get(stake['cardano_commitment'])
        if label and label not in bound_to:
            bound_to.append(label)
        positions.append({
            'txid': stake['txid'],
            'vout': stake['vout'],
            'amount_btc': stake['sats'] / SATS_PER_BTC,
            'sats': stake['sats'],
            'vault_address': stake['vault_address'],
            'confirmed': stake['confirmed'],
            'block_time': stake['block_time'],
            'cardano_wallet': label,
        })

    total_sats = sum(s['sats'] for s in active)
    if bound_to:
        note = 'KARMA rewards to ' + ', '.join(bound_to)
    else:
        note = 'KARMA rewards to an untracked Cardano wallet'

    return {
        'protocols': {
            PROTOCOL_NAME: {
                'staked': [{
                    'token': 'BTC',
                    'amount': total_sats / SATS_PER_BTC,
                    'positions': len(active),
                    'logo_url': logokit_service.get_crypto_logo_url('BTC', size=32),
                }],
                'reward_token': REWARD_TOKEN,
                'rewards_url': STAKING_URL,
                'blockchain': 'bitcoin',
                'category': 'staking',
                'note': note,
                'total_positions': len(active),
                'stake_positions': positions,
                'source': 'bitcoin-chain',
            }
        }
    }
