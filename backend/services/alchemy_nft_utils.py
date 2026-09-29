"""
Shared helpers for Alchemy NFT API v3 ``getNFTsForOwner`` callers.

Used by the Ethereum, Polygon, Base and generic EVM (BSC/Arbitrum/Avalanche)
NFT services.

Why this exists
---------------
Alchemy now rejects the ``excludeFilters[]=SPAM`` query parameter on free-tier
keys with HTTP 400 ("... can only be used with a payg or higher plan"). Every
EVM NFT request was sending it, so every request failed and each chain showed
zero NFTs. The spam classification itself is still returned on every plan
(``contract.isSpam``), so the filter is applied client-side instead.

A failed fetch also used to overwrite the persistent NFT cache with an empty
list, wiping the last known-good data. ``restore_failed_wallets`` keeps the
previously cached NFTs for any wallet whose fetch failed.
"""

import hashlib
from typing import Dict, Iterable, List, Optional, Set


# ABCT-EVM-FANOUT-2026-09-28: one EVM private key/address can hold assets on
# any EVM chain. Wallets are stored one-row-per-(address, blockchain)
# (database.py wallets table, UNIQUE(user_id, address, blockchain)), and
# utils/address.detect_blockchain files any bare 0x address as 'ethereum'
# (chain prefixes like 'polygon:0x...' are the only way a row gets a
# different EVM blockchain value). Before this fix, each EVM NFT/balance
# fetcher only ever queried addresses whose OWN row said that exact chain,
# so a real Polygon/Base holder stored as 'ethereum' was invisible to
# /nfts/polygon and /nfts/base. EVM_ADDRESS_CHAINS is every blockchain value
# that is an EVM address (a "donor" of candidate addresses); a wallet whose
# blockchain is any of these is fanned out to every chain in
# EVM_FANOUT_TARGET_CHAINS instead of only its own stored chain.
EVM_ADDRESS_CHAINS = frozenset({
    'ethereum', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche',
})

# Chains this fan-out actually queries per ABCT-EVM-FANOUT-2026-09-28 (user
# decision, 2026-09-28). BSC/Arbitrum/Avalanche wallets are still valid
# ADDRESS DONORS above (their 0x address is equally an Ethereum/Polygon/Base
# address), but their own dedicated endpoints are out of scope for this fix.
EVM_FANOUT_TARGET_CHAINS = ('ethereum', 'polygon', 'base')


def evm_fanout_wallets(wallets: Iterable[dict]) -> List[dict]:
    """Every EVM-family wallet, deduplicated by address (case-insensitive).

    Used to build the candidate address list for an EVM NFT/balance fetcher
    that should query every EVM address the user has ever registered, not
    just the ones whose own DB row happens to already say that chain. First
    occurrence wins on a duplicate address (stable, deterministic ordering
    from the input list).
    """
    seen: Set[str] = set()
    result: List[dict] = []
    for w in wallets:
        addr = w.get('address') if isinstance(w, dict) else None
        if not addr:
            continue
        if w.get('blockchain') not in EVM_ADDRESS_CHAINS:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(w)
    return result


def wallet_fingerprint(addresses: Iterable[str]) -> str:
    """Stable, non-reversible fingerprint of a set of addresses (case-insensitive).

    Stored next to a cached fetch result so an EVM wallet added or removed
    after the last fetch is noticed instead of hiding behind a long TTL.
    Mirrors services/solana_nft.py's wallet_fingerprint (kept as an
    independent copy here rather than imported, so the EVM caching path
    does not depend on the Solana module). ABCT-EVM-FANOUT-2026-09-28.
    """
    joined = "\n".join(sorted({a.lower() for a in addresses if a}))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def build_owner_params(address: str, page_key: Optional[str] = None, page_size: int = 100) -> Dict[str, str]:
    """Query parameters for getNFTsForOwner that work on every Alchemy plan.

    Deliberately does NOT include ``excludeFilters[]`` (paid-plan only).
    """
    params = {
        'owner': address,
        'withMetadata': 'true',
        'pageSize': page_size,
    }
    if page_key:
        params['pageKey'] = page_key
    return params


def is_alchemy_spam(nft_data: dict) -> bool:
    """True when Alchemy classifies this NFT (or its contract) as spam.

    Alchemy v3 exposes the classification as ``contract.isSpam``; older
    response shapes used ``spamInfo.isSpam``. Both are honoured.
    """
    if not isinstance(nft_data, dict):
        return False
    contract = nft_data.get('contract') or {}
    if contract.get('isSpam') is True:
        return True
    spam_info = nft_data.get('spamInfo') or {}
    if spam_info.get('isSpam') in (True, 'true'):
        return True
    return False


def drop_spam(data: Optional[dict]) -> Optional[dict]:
    """Remove spam NFTs from a getNFTsForOwner response (in place, returned).

    Pagination fields (``pageKey``, ``totalCount``) are left untouched so the
    caller's paging loop behaves exactly as before.
    """
    if not isinstance(data, dict):
        return data
    owned = data.get('ownedNfts')
    if isinstance(owned, list):
        data['ownedNfts'] = [n for n in owned if not is_alchemy_spam(n)]
    return data


def restore_failed_wallets(
    fresh_cache: Dict[str, dict],
    previous_nfts: Iterable[dict],
    failed_addresses: Set[str],
) -> int:
    """Put back last-known NFTs for wallets whose fetch failed.

    Args:
        fresh_cache: the service's asset_id -> nft dict being rebuilt (mutated).
        previous_nfts: NFTs from before the refresh (in-memory or persistent cache).
        failed_addresses: wallet addresses whose first-page fetch returned nothing.

    Returns:
        Number of NFTs restored.
    """
    if not failed_addresses:
        return 0
    failed = {a.lower() for a in failed_addresses if a}
    restored = 0
    for nft in previous_nfts or []:
        if not isinstance(nft, dict):
            continue
        owner = (nft.get('wallet_address') or '').lower()
        asset_id = nft.get('asset_id')
        if owner in failed and asset_id and asset_id not in fresh_cache:
            fresh_cache[asset_id] = nft
            restored += 1
    return restored


def previous_nft_list(in_memory: Dict[str, dict], cached_data: Optional[dict]) -> List[dict]:
    """Best available pre-refresh NFT list: in-memory cache, else persistent cache."""
    if in_memory:
        return list(in_memory.values())
    if isinstance(cached_data, dict):
        return list(cached_data.get('nfts') or [])
    return []
