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

from typing import Dict, Iterable, List, Optional, Set


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
