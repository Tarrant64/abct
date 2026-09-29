"""
EVM cross-chain balance/token fan-out (ABCT-EVM-FANOUT-2026-09-28).

Same root cause as the NFT fan-out in services/alchemy_nft_utils.py, applied
to native balances (ETH/MATIC/ETH-on-Base) and ERC-20 tokens instead of NFTs:
wallets are stored one-row-per-(address, blockchain), and a bare 0x address
is always filed as 'ethereum' (utils/address.detect_blockchain). Before this
fix, /portfolio/summary only ever asked Polygon/Base about addresses whose
OWN row already said 'polygon'/'base', so a real Polygon/Base holder stored
as 'ethereum' contributed $0 to those chains' totals.

Design constraints (see ABCT-EVM-FANOUT-2026-09-28 task report for the full
reasoning):

- No DB schema change, no data migration. Results are cached under the
  existing generic key-value cache table (database.get_cache/set_cache,
  the same mechanism the Polygon/Base/Ethereum NFT services already use),
  never written into `balances` / `native_assets` -- those tables stay
  exactly one row per real wallet_id and are owned by the wallet_balance
  background scheduler / manual refresh flow (routers/wallets.py). This
  fan-out only ever ADDS derived totals on top of that in the in-memory
  portfolio summary response.
- No double counting: an address already explicitly registered on a given
  target chain (a real DB wallet row for that chain) is never fanned into
  that chain a second time -- see `_fanout_candidates`.
- Alchemy free-tier budget: results are cached for EVM_FANOUT_CACHE_TTL
  (1 hour) and invalidated early only when the EVM wallet set actually
  changes (wallet_fingerprint), not on every /portfolio/summary request
  (which itself is only computed once per its own ~20 minute cache TTL).
  Per-chain services' own get_address_info()/get_address_balance() add a
  further 5-10 minute in-memory cache on individual addresses.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from database import get_cache, set_cache
from services.alchemy_nft_utils import (
    EVM_ADDRESS_CHAINS, EVM_FANOUT_TARGET_CHAINS, evm_fanout_wallets, wallet_fingerprint,
)
from services.pricing import pricing_service

logger = logging.getLogger(__name__)

EVM_FANOUT_CACHE_KEY = "evm_balance_fanout_v1"
EVM_FANOUT_CACHE_TTL = 3600  # 1 hour -- bounds Alchemy calls independent of /portfolio/summary's own (shorter) cache TTL
EVM_FANOUT_CONCURRENCY = 5   # matches the existing manual bulk-refresh Semaphore(5) in routers/wallets.py

# Native unit priced via pricing_service.get_price() for each target chain.
# Base's native asset is ETH (it is an Ethereum L2); MATIC/POL uses the same
# 'MATIC' ticker the rest of the app prices Polygon with (see routers/nfts.py).
NATIVE_SYMBOL = {'ethereum': 'ETH', 'polygon': 'MATIC', 'base': 'ETH'}


def _fanout_candidates(wallets: List[dict]) -> List[dict]:
    """(address, target_chain) pairs that are NOT already an explicit DB row.

    An EVM-family wallet (see EVM_ADDRESS_CHAINS) is a fan-out candidate for
    a target chain only when that exact (address, target_chain) combination
    has no real wallet row -- that is what prevents double counting when,
    e.g., the same address is registered as both 'ethereum' and 'polygon'.
    """
    registered = {
        (w['address'].lower(), w['blockchain'])
        for w in wallets
        if w.get('blockchain') in EVM_FANOUT_TARGET_CHAINS and w.get('address')
    }
    candidates = []
    for w in evm_fanout_wallets(wallets):
        addr_lower = w['address'].lower()
        for target in EVM_FANOUT_TARGET_CHAINS:
            if (addr_lower, target) in registered:
                continue
            candidates.append({
                'address': w['address'],
                'target_chain': target,
                'source_wallet_id': w.get('id'),
            })
    return candidates


async def _price_tokens(tokens: List[dict]) -> float:
    """Best-effort ticker-based USD pricing for a list of ERC-20 balances.

    Same "ticker match or contribute $0, never raise" approach as
    routers/portfolio.py's calculate_wallet_native_assets_value.
    """
    total = 0.0
    for t in tokens or []:
        symbol = (t.get('symbol') or '').upper()
        balance = t.get('balance') or 0
        if not symbol or not balance:
            continue
        try:
            price = await pricing_service.get_price(symbol)
            if price and price > 0:
                total += balance * price
        except Exception:
            pass
    return total


async def _fetch_one(candidate: dict, semaphore: asyncio.Semaphore) -> Optional[dict]:
    target = candidate['target_chain']
    address = candidate['address']

    async with semaphore:
        try:
            if target == 'ethereum':
                from services.ethereum import ethereum_service
                info = await ethereum_service.get_address_balance(address)
                native = (info or {}).get('balance_eth', 0)
            elif target == 'polygon':
                from services.polygon import polygon_service
                info = await polygon_service.get_address_info(address)
                native = (info or {}).get('balance_matic', 0)
            elif target == 'base':
                from services.base import base_service
                info = await base_service.get_address_info(address)
                native = (info or {}).get('balance_eth', 0)
            else:
                return None
        except Exception as e:
            logger.warning(f"EVM fan-out balance fetch failed (target={target}): {e}")
            return None

    if not info:
        return None

    tokens = info.get('tokens') or []
    return {
        'target_chain': target,
        'native': native or 0,
        'tokens': tokens,
        'source_wallet_id': candidate.get('source_wallet_id'),
    }


def _empty_result() -> Dict[str, dict]:
    return {
        chain: {
            'extra_native': 0.0,
            'extra_value_usd': 0.0,
            'extra_token_count': 0,
            'addresses_count': 0,
            'symbol': NATIVE_SYMBOL[chain],
        }
        for chain in EVM_FANOUT_TARGET_CHAINS
    }


async def compute_evm_fanout(wallets: List[dict]) -> Dict[str, dict]:
    """Live fan-out fetch (no cache). Prefer get_evm_fanout_summary()."""
    candidates = _fanout_candidates(wallets)
    result = _empty_result()
    if not candidates:
        return result

    semaphore = asyncio.Semaphore(EVM_FANOUT_CONCURRENCY)
    fetched = await asyncio.gather(
        *[_fetch_one(c, semaphore) for c in candidates], return_exceptions=True
    )

    prices = {}
    for chain in EVM_FANOUT_TARGET_CHAINS:
        try:
            prices[chain] = await pricing_service.get_price(NATIVE_SYMBOL[chain])
        except Exception:
            prices[chain] = 0

    for item in fetched:
        if not item or isinstance(item, Exception):
            continue
        chain = item['target_chain']
        result[chain]['extra_native'] += item['native']
        result[chain]['extra_value_usd'] += item['native'] * (prices.get(chain) or 0)
        result[chain]['extra_token_count'] += len(item['tokens'])
        result[chain]['addresses_count'] += 1
        result[chain]['extra_value_usd'] += await _price_tokens(item['tokens'])

    return result


async def get_evm_fanout_summary(wallets: List[dict], force_refresh: bool = False) -> Dict[str, dict]:
    """Cached wrapper around compute_evm_fanout.

    Cached under a fingerprint of the full EVM wallet set (every EVM-family
    address, not just the target chains) so adding/removing ANY EVM wallet
    is picked up immediately instead of waiting out EVM_FANOUT_CACHE_TTL --
    mirrors services/solana_nft.py's wallet_fingerprint pattern (#16).
    """
    fp = wallet_fingerprint(
        w['address'] for w in wallets if w.get('blockchain') in EVM_ADDRESS_CHAINS and w.get('address')
    )

    if not force_refresh:
        try:
            cached = await get_cache(EVM_FANOUT_CACHE_KEY)
        except Exception as e:
            logger.debug(f"EVM fan-out cache read failed: {e}")
            cached = None
        if cached and cached.get('wallet_fingerprint') == fp:
            return cached.get('data', _empty_result())

    data = await compute_evm_fanout(wallets)
    try:
        await set_cache(EVM_FANOUT_CACHE_KEY, {
            'data': data,
            'wallet_fingerprint': fp,
            'computed_at': datetime.now().isoformat(),
        }, EVM_FANOUT_CACHE_TTL)
    except Exception as e:
        logger.error(f"Error saving EVM fan-out cache: {e}")

    return data
