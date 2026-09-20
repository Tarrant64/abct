"""
Regression tests for ABCT-CARDANO-TAPTOOLS-KEYFIX-20260919.

Root cause: routers/portfolio.py's calculate_wallet_native_assets_value()
read `pos.get('adaValue', 0)` (camelCase) from a Koios-matched position, but
services/taptools.py's get_wallet_portfolio() only ever sets
`pos['ada_value']` (snake_case). The lookup always missed -> total_ada was
always 0.0 -> because the pricing branch was `elif`, not a second `if`, a
genuine Koios match ALSO skipped the ticker-based fallback that would
otherwise have priced the asset. Confirmed live: user reported "a ton
showing 0s" -- the more assets Koios recognized, the more of the portfolio
silently disappeared.

Fix: correct the key name, and replace elif with an explicit
`priced_on_chain` flag so the ticker fallback only gets skipped when the
on-chain path produced a REAL usable value -- a Koios match that comes
back zero or missing must still fall through to ticker pricing.

Mocks taptools_wallet_service and pricing_service -- no live calls.
Exercises the real calculate_wallet_native_assets_value against a real
temporary SQLite file.
"""

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


def _install_common_mocks(monkeypatch, positions, ada_price=1.0, ticker_prices=None):
    ticker_prices = ticker_prices or {}

    async def fake_is_configured():
        return True

    async def fake_get_wallet_portfolio(address):
        return {"positions": positions}

    async def fake_get_price(symbol):
        if symbol == "ADA":
            return ada_price
        return ticker_prices.get(symbol, 0)

    monkeypatch.setattr(portfolio.taptools_wallet_service, "is_configured", fake_is_configured)
    monkeypatch.setattr(portfolio.taptools_wallet_service, "get_wallet_portfolio", fake_get_wallet_portfolio)
    monkeypatch.setattr(portfolio.pricing_service, "get_price", fake_get_price)


@pytest.mark.asyncio
async def test_koios_matched_asset_with_real_value_gets_priced(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetSTRIKE")

    positions = [{"unit": "policyANDassetSTRIKE", "ada_value": 100.0}]
    _install_common_mocks(monkeypatch, positions, ada_price=0.5)

    total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    # 100 ADA worth * $0.50/ADA = $50 -- this is the regression: pre-fix,
    # pos.get('adaValue', 0) always returned 0, so this was always $0.
    assert total == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_unmatched_asset_still_falls_back_to_ticker_price(tmp_path, monkeypatch):
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetUNKNOWN", ticker_metadata="UNKNOWN", quantity="10", decimals=0)

    positions = []  # Koios has no position for this asset at all
    _install_common_mocks(monkeypatch, positions, ticker_prices={"UNKNOWN": 2.0})

    total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    assert total == pytest.approx(20.0)  # 10 units * $2.00 ticker price


@pytest.mark.asyncio
async def test_koios_match_with_zero_value_still_falls_back_to_ticker_price(tmp_path, monkeypatch):
    """The specific case the old elif silently broke: Koios recognizes the
    asset (asset_id is in taptools_positions) but returns a zero/absent
    ada_value -- this must NOT be left unpriced."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetINDY", ticker_metadata="INDY", quantity="5", decimals=0)

    positions = [{"unit": "policyANDassetINDY", "ada_value": 0}]  # matched, but zero
    _install_common_mocks(monkeypatch, positions, ticker_prices={"INDY": 3.0})

    total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    assert total == pytest.approx(15.0), (
        "a Koios match with a zero value must still fall through to ticker pricing, "
        "not end up silently unpriced"
    )


@pytest.mark.asyncio
async def test_koios_match_with_real_value_does_not_also_apply_ticker_fallback(tmp_path, monkeypatch):
    """Once a Koios match carries a real non-zero value, the ticker fallback
    must be skipped -- not double-priced."""
    db_path = _make_test_db(tmp_path)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    _insert_asset(db_path, "policyANDassetLQ", ticker_metadata="LQ", quantity="7", decimals=0)

    positions = [{"unit": "policyANDassetLQ", "ada_value": 10.0}]
    _install_common_mocks(monkeypatch, positions, ada_price=2.0, ticker_prices={"LQ": 999.0})

    total = await portfolio.calculate_wallet_native_assets_value(WALLET_ID, "cardano", USER_ID)

    # Must be 10 ADA * $2.00 = $20 (on-chain path), NOT also + 7 * $999 (ticker fallback).
    assert total == pytest.approx(20.0)
