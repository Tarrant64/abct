"""
NFT pricing helpers (WQ-0058).

A missing floor price and a genuine 0 floor are different facts. Before this
module every aggregation site collapsed the missing case with
``x.get('floor', 0) or 0`` and summed it, so an unpriced NFT entered portfolio
totals as $0 — indistinguishable from a collection that is really worthless
(ABCT-NFT-FLOOR-RESEARCH-2026-09-27 recommendation, PRJ-Y acceptance case 1).

The rule the whole NFT path now uses:
  - no floor found  -> the NFT is UNPRICED: excluded from every sum, marked
    with ``priced: False`` and a ``null`` USD value;
  - a real 0 floor  -> priced at 0 (``priced: True``);
  - a missing/failed native-currency price -> everything counts as unpriced,
    never as $0 (a failed lookup must not block total computation either).
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def to_price(value) -> Optional[float]:
    """Coerce a floor/price field to a float, preserving "no price" as None.

    None, '', [] and {} are "no price" (corrupted DB rows included); 0 is a
    real price. Anything unparseable is treated as no price, not as 0.
    """
    if value is None or value == '' or value == [] or value == {}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def price_floor_native(collection: dict, floor_key: str) -> Optional[float]:
    """The collection's native-asset floor, or None when unpriced."""
    return to_price((collection or {}).get(floor_key))


def priced_usd(native_price: Optional[float], floor_native: Optional[float]) -> Optional[float]:
    """USD value for one NFT: None (unpriced) if either input is missing."""
    if native_price is None or floor_native is None:
        return None
    return floor_native * native_price


def priced_totals(prices, floors):
    """Sum only the priced pairs; return (total, priced_count, unpriced_count).

    ``prices`` and ``floors`` are parallel iterables (already coerced with
    to_price / a native price); a pair contributes only when BOTH sides are
    real numbers.
    """
    total = 0.0
    priced = 0
    unpriced = 0
    for price, floor in zip(prices, floors):
        if price is None or floor is None:
            unpriced += 1
        else:
            total += price * floor
            priced += 1
    return total, priced, unpriced


def group_total_usd(nfts) -> Optional[float]:
    """Total USD floor of a group of NFT dicts: the sum of the PRICED ones only.

    ``floor_price_usd`` is None for an unpriced NFT (and ``.get(k, 0)`` would
    return that None, not 0). A group with no priced NFT has no total (None,
    shown as '-'), never $0.
    """
    priced = [n['floor_price_usd'] for n in nfts if n.get('floor_price_usd') is not None]
    return sum(priced) if priced else None


def unpriced_last_desc(value: Optional[float]):
    """Sort key: priced values high to low, then the unpriced (None) ones."""
    return (value is None, -(value or 0))


def collection_floor_rollup(all_nfts, floor_key: str) -> dict:
    """Group NFTs by collection name and total ONLY the priced floors.

    Returns {collection_name: {'count', 'priced_count', 'unpriced_count',
    'total_native'}}. An NFT whose collection carries no floor (None/missing/
    unparseable) is unpriced: it is counted but never added to total_native.
    A genuine 0.0 floor is priced and adds 0.
    """
    groups: dict = {}
    for nft in all_nfts:
        name = (nft.get('collection') or {}).get('name', 'Unknown Collection')
        group = groups.setdefault(name, {
            'count': 0, 'priced_count': 0, 'unpriced_count': 0, 'total_native': 0.0,
        })
        group['count'] += 1
        floor = price_floor_native(nft.get('collection') or {}, floor_key)
        if floor is None:
            group['unpriced_count'] += 1
        else:
            group['priced_count'] += 1
            group['total_native'] += floor
    return groups


def native_price_or_none(awaitable_or_value) -> Optional[float]:
    """Coerce a pricing-service result: 0.0 from a failed lookup means nothing.

    ``pricing_service.get_price`` returns 0 when the provider failed — that is
    "no price", not "worth zero".
    """
    value = to_price(awaitable_or_value)
    return value if value else None
