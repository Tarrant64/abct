"""
WQ-0397: DexScreener 24h-change enrichment for Cardano native tokens.

parse_pairs is pure and tested against a recorded live payload shape; the
pricing route pin asserts the enrichment sits in the cardano path (the
sources that actually run keyless here -- Charli3-no-key and DefiLlama --
carry no change field, which is what left every STRIKE/INDY/IAG tile at
0.00%).
"""

import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

from services.dexscreener import (  # noqa: E402
    parse_pairs, dexscreener_units, to_price_cache_entry)


def _pair(sym, price, chg, liq, dex="sundaeswap", chain="cardano"):
    return {
        "chainId": chain, "dexId": dex, "priceUsd": str(price),
        "baseToken": {"symbol": sym},
        "priceChange": {"h24": chg},
        "liquidity": {"usd": liq},
        "volume": {"h24": liq * 10},
    }


def test_units_concatenate_policy_and_hexname():
    units = dexscreener_units({"STRIKE": ("f13ac", "535452494b45")})
    assert units["STRIKE"] == "f13ac535452494b45"


def test_deepest_liquidity_pair_wins():
    payload = {"pairs": [
        _pair("STRIKE", 0.44, -9.9, 1000, dex="meteora"),
        _pair("STRIKE", 0.4682, -5.36, 277039),
        _pair("STRIKE", 0.45, -3.0, 5000),
    ]}
    out = parse_pairs(payload, ["STRIKE"])
    assert out["STRIKE"]["price"] == 0.4682
    assert out["STRIKE"]["change_24h"] == -5.36
    assert out["STRIKE"]["dex"] == "sundaeswap"


def test_other_chains_and_unwanted_symbols_ignored():
    payload = {"pairs": [
        _pair("IAG", 0.0169, -6.2, 16948, chain="ethereum"),
        _pair("USDC", 1.0, 0.01, 9e9),
        _pair("IAG", 0.01694, -6.22, 16948),
    ]}
    out = parse_pairs(payload, ["IAG"])
    assert set(out) == {"IAG"}
    assert out["IAG"]["change_24h"] == -6.22


def test_missing_change_field_is_none_not_zero():
    p = _pair("LQ", 0.26, None, 9802)
    p["priceChange"] = {}
    out = parse_pairs({"pairs": [p]}, ["LQ"])
    assert out["LQ"]["change_24h"] is None


def test_zero_price_pairs_skipped():
    payload = {"pairs": [_pair("INDY", 0, -1.0, 500)]}
    assert parse_pairs(payload, ["INDY"]) == {}


def test_empty_or_malformed_payload():
    assert parse_pairs({}, ["STRIKE"]) == {}
    assert parse_pairs({"pairs": None}, ["STRIKE"]) == {}
    assert parse_pairs([{"chainId": "cardano"}], ["STRIKE"]) == {}


def test_cache_entry_shape():
    data = {"price": 0.4682, "change_24h": -5.36, "volume_24h": 100,
            "liquidity_usd": 277039, "dex": "sundaeswap"}
    e = to_price_cache_entry(data)
    assert e["usd"] == 0.4682
    assert e["usd_24h_change"] == -5.36
    assert e["source"] == "DexScreener:sundaeswap"
    assert e["data_completeness"] == "full"
    # a None change degrades the completeness label, never borrows a number
    e2 = to_price_cache_entry({**data, "change_24h": None})
    assert e2["usd_24h_change"] == 0
    assert e2["data_completeness"] == "price_only"


# ------------------------------------------------------------------ route

def test_cardano_route_enriches_after_defillama_fallback():
    src = _read_route()
    i = src.index("async def _fetch_cardano_prices")
    body = src[i:src.index("async def _fetch_major_prices", i)]
    assert "get_cardano_token_data" in body, \
        "cardano route must consult DexScreener for 24h changes"
    assert body.index("_fetch_from_defillama") < body.index("get_cardano_token_data"), \
        "enrichment runs after the price fallbacks so it can attach changes to any priced token"
    assert "self.cache[sym] = entry" in body


def _read_route():
    with open(os.path.join(REPO, "backend", "services", "pricing.py"),
              encoding="utf-8") as f:
        return f.read()
