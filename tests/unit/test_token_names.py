"""
Server-fixes item 4 (2026-11-20): all-holdings token names come from token
metadata (registry/CoinGecko), then the static display table, then the ticker
-- never from native_assets.asset_name (wallet-side label / 'ERC-20' placeholder).
"""

import os
import sys

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.portfolio as portfolio_router  # noqa: E402
from services.token_names import resolve_token_display_name  # noqa: E402

from tests.unit.test_btc_totals_integration import holdings_env  # noqa: E402,F401


def test_resolver_order():
    assert resolve_token_display_name("SNEK", {"name": "Snek"}) == "Snek"       # metadata wins
    assert resolve_token_display_name("INDY", None) == "Indigo"                 # static table
    assert resolve_token_display_name("WEIRD", None) == "WEIRD"                 # ticker fallback
    assert resolve_token_display_name("WEIRD", {"name": "  "}) == "WEIRD"       # blank metadata ignored
    assert resolve_token_display_name("", None, fallback="x") == "x"


async def test_all_holdings_token_name_ignores_wallet_label(holdings_env, monkeypatch):  # noqa: F811
    async def assets(user_id=None, refresh=False):
        return {"valuable_assets": [
            {"ticker": "USDT", "asset_name": "ERC-20", "total_quantity": 50.0,
             "price_usd": 1.0, "value_usd": 50.0, "wallet_count": 1},
            {"ticker": "INDY", "asset_name": "my-hot-wallet-label", "total_quantity": 10.0,
             "price_usd": 0.5, "value_usd": 5.0, "wallet_count": 1},
            {"ticker": "ZZZ", "asset_name": "SPL", "total_quantity": 1.0,
             "price_usd": 2.0, "value_usd": 2.0, "wallet_count": 1},
        ], "assets": []}
    monkeypatch.setattr(portfolio_router, "get_all_native_assets", assets)

    # Patch the INSTANCE: other tests' monkeypatch undo leaves a bound-method
    # attribute on the shared metadata_cache instance, which would shadow a
    # class-level patch.
    async def meta(symbol):
        return {"name": "Tether USD", "image_url": None} if symbol == "USDT" else None
    monkeypatch.setattr(portfolio_router.metadata_cache, "get_metadata", meta)

    result = await portfolio_router.get_all_holdings(user_id=1, refresh=True)
    names = {h["symbol"]: h["name"] for h in result["holdings"]}
    assert names["USDT"] == "Tether USD"   # registry/metadata name
    assert names["INDY"] == "Indigo"       # static table, not the wallet label
    assert names["ZZZ"] == "ZZZ"           # ticker fallback, not 'SPL'
