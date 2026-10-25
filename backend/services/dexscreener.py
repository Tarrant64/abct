"""
DexScreener pricing for Cardano native tokens (WQ-0397).

Why: the cardano pricing route was Charli3 -> DefiLlama. Charli3 needs an
API key that this install does not have (is_configured False since the
encryption keychain issue; TapTools, the old change source, is dead), and
DefiLlama's current-price endpoint is price_only -- it never carries a 24h
change. Result: STRIKE/INDY/LQ/IAG/MIN... showed $0.00 24h change on the
dashboard and mobile while their click-through charts (a different,
historical endpoint) showed real movement like STRIKE -5%.

DexScreener is free, keyless, and returns price + 24h change + liquidity
per DEX pair. One batch call (latest/dex/tokens/<comma-list>) covers every
token in CARDANO_TOKEN_POLICIES at once; we pick the deepest-liquidity
pair whose base token matches, which is what the price should be read from.

Known limit observed live (2026-10-24): LQ has no listed pair -> stays
change-0 via the DefiLlama price it already has; a token with no pool is
not silently given someone else's change.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEXSCREENER_TOKENS_URL = "https://api.dexscreener.com/latest/dex/tokens"
_CARDANO_CHAIN = "cardano"


def dexscreener_units(policies: Dict[str, Tuple[str, str]]) -> Dict[str, str]:
    """symbol -> concatenated policy_id + hex_name address that DexScreener
    indexes Cardano tokens under (same units Charli3's map uses)."""
    return {sym: f"{policy}{hexname}"
            for sym, (policy, hexname) in policies.items()}


def _pair_usd_liquidity(pair: dict) -> float:
    try:
        return float((pair.get("liquidity") or {}).get("usd") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_pairs(payload, wanted_symbols: List[str]) -> Dict[str, dict]:
    """Pure: DexScreener /latest/dex/tokens payload ->
    {symbol: {price, change_24h, volume_24h, source_pair}} keeping, per
    requested symbol, the deepest-liquidity pair that actually prices it
    (on Cardano)."""
    pairs = payload.get("pairs") if isinstance(payload, dict) else payload
    if not pairs:
        return {}
    wanted = {s.upper() for s in wanted_symbols}
    best: Dict[str, dict] = {}
    for p in pairs:
        if (p.get("chainId") or "").lower() != _CARDANO_CHAIN:
            continue
        sym = ((p.get("baseToken") or {}).get("symbol") or "").upper()
        if sym not in wanted:
            continue
        try:
            price = float(p.get("priceUsd") or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            continue
        change = (p.get("priceChange") or {}).get("h24")
        try:
            change = float(change) if change is not None else None
        except (TypeError, ValueError):
            change = None
        cand = {
            "price": price,
            "change_24h": change,
            "volume_24h": (p.get("volume") or {}).get("h24") or 0,
            "liquidity_usd": _pair_usd_liquidity(p),
            "dex": p.get("dexId") or "",
        }
        prev = best.get(sym)
        if prev is None or cand["liquidity_usd"] > prev["liquidity_usd"]:
            best[sym] = cand
    return best


async def get_cardano_token_data(symbols: List[str]) -> Dict[str, dict]:
    """One batched DexScreener call for the requested Cardano tokens."""
    from services.pricing import CARDANO_TOKEN_POLICIES
    from services.http_client import get_client

    units = dexscreener_units(CARDANO_TOKEN_POLICIES)
    addrs = [units[s.upper()] for s in symbols if s.upper() in units]
    if not addrs:
        return {}
    try:
        client = get_client("dexscreener", timeout=20.0)
        resp = await client.get(f"{DEXSCREENER_TOKENS_URL}/{','.join(addrs)}")
        if resp.status_code == 429:
            logger.debug("dexscreener rate limited")
            return {}
        if resp.status_code != 200:
            logger.debug("dexscreener HTTP %s", resp.status_code)
            return {}
        return parse_pairs(resp.json(), [s.upper() for s in symbols])
    except Exception as e:
        logger.warning("dexscreener fetch failed: %s", e)
        return {}


def to_price_cache_entry(data: dict) -> dict:
    """Shape a parse_pairs() entry like the pricing service cache rows."""
    return {
        "usd": data["price"],
        "usd_1h_change": 0,
        "usd_24h_change": data.get("change_24h") or 0,
        "market_cap": 0,
        "volume_24h": data.get("volume_24h", 0),
        "source": f"DexScreener:{data.get('dex', '')}".rstrip(":"),
        "data_completeness": "full" if data.get("change_24h") is not None
                             else "price_only",
        "updated_at": datetime.now().isoformat(),
    }
