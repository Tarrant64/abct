"""
Regression tests for ABCT-CARDANO-TAPTOOLS-KEYFIX-20260919.

CONFIRMED LIVE: user reported "a ton showing 0s" on their dashboard.

Root cause, round 2 (round 1 -- fixing the pos.get('adaValue', 0) /
pos['ada_value'] camelCase mismatch alone -- was a real but secondary bug
that would NOT have fixed the user's report): the `elif` in
calculate_wallet_native_assets_value() treated a Koios "match" (an asset
present in the stake account's on-chain position list) as having ALREADY
priced the asset, skipping the ticker-based fallback that would otherwise
price it. That assumption was always false, independent of the key-name
bug: services/taptools.py hardcodes `'ada_value': 0` for every position
because Koios does not return pricing data at all -- only quantity and
existence. So even with the key name fixed, every "matched" asset would
still read ada_value=0, `total_ada > 0` would still fail, and the ticker
fallback would still never run. The more assets Koios recognized, the more
of the portfolio silently zeroed -- worse than no integration at all.

Fix: a Koios match is not a price. The on-chain position lookup (a live
Koios call that fed only this now-removed dead branch) has been removed
entirely, and ticker-based pricing -- the only real pricing path currently
available for Cardano native assets -- now runs unconditionally for every
asset with a ticker. An asset that ends up unpriced (no ticker anywhere,
or a ticker whose price lookup failed) is logged explicitly rather than
silently folded into a $0 contribution with no trace.

No live calls -- pricing_service is mocked. Exercises the real
calculate_wallet_native_assets_value against a real temporary SQLite file.
"""

import logging
import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import config  # noqa: E402
import routers.portfolio as portfolio  # noqa: E402

USER_ID = 1
WALLET_ID = 1
ADDRESS = "addr1_test_wallet"


def _make_test_db(tmp_path):
    db_path = str(tmp_path / "test_taptools_keyfix.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE wallets (id INTEGER PRIMARY KEY, address TEXT)")
    conn.execute("INSERT INTO wallets (id, address) VALUES (?, ?)", (WALLET_ID, ADDRESS))
    conn.execute("""
        CREATE TABLE native_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER, user_id INTEGER,
            asset_id TEXT, policy_id TEXT, asset_name TEXT,
            quantity TEXT, decimals INTEGER, ignored INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE TABLE token_metadata (asset_id TEXT PRIMARY KEY, ticker TEXT)")
    conn.execute("CREATE TABLE custom_tokens (policy_id TEXT, asset_name TEXT, user_id INTEGER, ticker TEXT)")
    conn.commit()
    conn.close()
    return db_path


def _insert_asset(db_path, asset_id, ticker_metadata=None, quantity="1000000", decimals=0):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO native_assets (wallet_id, user_id, asset_id, policy_id, asset_name, quantity, decimals) "
        "VALUES (?, ?, ?, '', '', ?, ?)",
        (WALLET_ID, USER_ID, asset_id, quantity, decimals),
    )
    if ticker_metadata:
        conn.execute("INSERT INTO token_metadata (asset_id, ticker) VALUES (?, ?)", (asset_id, ticker_metadata))
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_asset_koios_would_have_matched_gets_priced_via_ticker(tmp_path, monkeypatch):
    """The exact shape of the user's report: an asset Koios recognizes
    (would have been in taptools_positions under the old code) must still
    get a real, non-zero valuation -- via ticker pricing, since Koios never
    provides a price. Verified to fail against the pre-fix code below."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetSTRIKE", ticker_metadata="STRIKE", quantity="5", decimals=0)

    async def fake_get_price(symbol):
        return 10.0 if symbol == "STRIKE" else 0

    monkeypatch.setattr(portfolio.pricing_service, "get_price", fake_get_price)

    total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    assert total == pytest.approx(50.0)  # 5 STRIKE * $10.00


@pytest.mark.asyncio
async def test_unmatched_asset_still_prices_correctly(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetUNKNOWN", ticker_metadata="UNKNOWN", quantity="10", decimals=0)

    async def fake_get_price(symbol):
        return 2.0 if symbol == "UNKNOWN" else 0

    monkeypatch.setattr(portfolio.pricing_service, "get_price", fake_get_price)

    total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    assert total == pytest.approx(20.0)  # 10 units * $2.00 ticker price


@pytest.mark.asyncio
async def test_unpriced_asset_is_logged_explicitly_not_silent(tmp_path, monkeypatch, caplog):
    """An asset with no ticker anywhere must not just silently contribute
    $0 -- it should be discoverable from logs without a DB query."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetNOTICKER", ticker_metadata=None, quantity="1", decimals=0)

    with caplog.at_level(logging.INFO, logger="routers.portfolio"):
        total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    assert total == 0.0
    assert any("unpriced" in r.message.lower() and "policyANDassetNOTICKER" in r.message for r in caplog.records), (
        "an unpriced asset must be logged by asset_id, not just silently dropped"
    )


