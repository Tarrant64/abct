"""
Regression tests for ABCT-COINBASE-POSITIONS-20260919.

Root cause: get_coinbase_portfolio()'s fire-and-forget write to
portfolio_positions referenced `exchange_name`, which is a real parameter
on the generic process_exchange_portfolio() helper (used by binance,
binance_us, okx, bitget, gate, kucoin) but was never a name in this
Coinbase-specific function's own scope -- a copy-paste bug. Confirmed via
pyflakes: exactly one undefined-name hit, at this line, in this file.

Effect: the NameError raised while building `pp_rows`, before
upsert_portfolio_positions_batch() was ever called, so the write silently
failed on every single invocation that reached this block (i.e. any
Coinbase-connected user with at least one non-zero balance) since this
code was added -- not an edge case like the wallets.py logger bug, this
fires on essentially every real call. The other 6 exchanges' generic
handler was never affected (it has a real exchange_name parameter,
confirmed unflagged by pyflakes).

This is NOT the whole explanation for a user's missing exchange total --
services/offchain_collector.py's periodic (every 2 hours) sweep also
writes source_type='exchange' rows by reading the same 5-minute-TTL
`{exchange}_portfolio` cache, so Coinbase COULD already be intermittently
captured that way. But that path only catches a fresh cache at the
moment the 2-hour sweep fires, which is a narrow window against a 5-
minute TTL -- this endpoint's own fire-and-forget write was meant to be
the reliable, immediate one, and it never worked at all.

Fix: 'coinbase' literal in place of the undefined exchange_name (matching
the hardcoded "exchange": "coinbase" a few lines above it in the same
function), and the swallowing except now logs at WARNING instead of
DEBUG so a write failure like this is actually visible in default logs
next time.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.exchanges as exchanges_router  # noqa: E402


async def _fake_get_portfolio_balances(user_id=None):
    return {
        "assets": [{"currency": "USD", "balance": 1109.58}],
        "asset_count": 1,
        "total_usd": 1109.58,
    }


def _install_common_fakes(monkeypatch):
    async def fake_get_username_by_user_id(user_id):
        return "tester"

    async def fake_is_demo_user(username):
        return False

    async def fake_is_configured(user_id=None):
        return True

    async def fake_get_cache(key, user_id=None):
        return None  # force a fresh fetch, not a cache hit

    async def fake_set_cache(key, value, ttl_seconds=300, user_id=None):
        pass

    monkeypatch.setattr(exchanges_router, "get_username_by_user_id", fake_get_username_by_user_id)
    monkeypatch.setattr(exchanges_router, "is_demo_user", fake_is_demo_user)
    monkeypatch.setattr(exchanges_router.coinbase_service, "is_configured", fake_is_configured)
    monkeypatch.setattr(exchanges_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(exchanges_router, "set_cache", fake_set_cache)
    monkeypatch.setattr(exchanges_router.coinbase_service, "get_portfolio_balances", _fake_get_portfolio_balances)


@pytest.mark.asyncio
async def test_coinbase_portfolio_writes_positions_with_correct_source_detail(monkeypatch):
    _install_common_fakes(monkeypatch)

    written = []

    async def fake_upsert(positions):
        written.extend(positions)

    monkeypatch.setattr(database, "upsert_portfolio_positions_batch", fake_upsert)

    result = await exchanges_router.get_coinbase_portfolio(user_id=1, refresh=False)

    assert result["assets"], "sanity: the portfolio call itself should still return assets"

    # This is the actual regression: pre-fix, upsert_portfolio_positions_batch
    # was never called at all -- the NameError on `exchange_name` happened
    # while building pp_rows, before this call was ever reached.
    assert len(written) == 1, f"expected exactly one portfolio_positions row written, got {written!r}"
    row = written[0]
    assert row["source_type"] == "exchange"
    assert row["source_detail"] == "coinbase"
    assert row["symbol"] == "USD"
    assert row["quantity"] == 1109.58


@pytest.mark.asyncio
async def test_coinbase_write_failure_is_still_fire_and_forget(monkeypatch):
    """Confirms step 2's other requirement: a write failure here must not
    break the endpoint -- the fire-and-forget contract must survive even a
    genuinely broken upsert, just log louder about it now (WARNING)."""
    _install_common_fakes(monkeypatch)

    async def broken_upsert(positions):
        raise RuntimeError("db is locked")

    monkeypatch.setattr(database, "upsert_portfolio_positions_batch", broken_upsert)

    # Must not raise -- the endpoint's real response is more important than
    # this side-write succeeding.
    result = await exchanges_router.get_coinbase_portfolio(user_id=1, refresh=False)
    assert result["assets"]
