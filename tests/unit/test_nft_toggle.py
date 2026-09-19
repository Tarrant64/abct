"""
Unit tests for ABCT-NFT-TOGGLE-20260919: the server-side
`include_nfts_in_total` preference and every total-computation site that
must honor it.

Background: prior to this change, NFT value was structurally excluded from
every web total (/portfolio/instant sums portfolio_positions, which never
gets a source_type='nft' row; /portfolio/all-holdings has no NFT step in its
holdings builder) while /mobile/portfolio/summary unconditionally included
it -- web and mobile permanently disagreed. This adds one user-scoped
preference (default OFF, same semantics as web's prior behavior) and wires
it through every site that computes a portfolio total or history point.

Covered:
1. get_nft_inclusion_preference() defaults to False for a user who has never
   set it, using the real user_settings table/round-trip (not a stub) --
   the exact regression named in the task.
2. /portfolio/instant includes NFT value in breakdown['nft']/total_usd only
   when the preference is on.
3. /portfolio/history's per-day `value` excludes/includes the NFT component
   of get_unified_daily_totals() rows the same way.
4. /balance-history/data (the endpoint the V2 dashboard chart actually
   calls) does the same -- this is the piece that makes the headline total
   and the history chart agree.
5. Toggling the preference moves /portfolio/instant's total and
   /balance-history/data's total by the *same* NFT amount, in the same
   direction -- the actual "headline and history must agree" regression.
6. /mobile/portfolio/summary's total_value_usd respects the preference too
   (mobile used to be the only surface that always included NFTs).
"""

import os
import sys
import types

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.portfolio as portfolio  # noqa: E402
import routers.balance_history as balance_history  # noqa: E402
import routers.nfts as nfts_router  # noqa: E402
import routers.mobile as mobile  # noqa: E402

from tests.unit.test_summary_cache_variants import (  # noqa: E402
    _install_fake_cache,
    _stub_compute_upstreams,
)

USER_ID = 4242
NFT_VALUE_USD = 2649.82


# ---------------------------------------------------------------------------
# 1. Preference persistence — real user_settings table, no stubbing.
# ---------------------------------------------------------------------------

async def _make_user_settings_db(tmp_path):
    """A minimal DB with just the user_settings table (matches database.py's
    CREATE TABLE), so get_user_setting/set_user_setting exercise real SQL."""
    import aiosqlite
    db_path = str(tmp_path / "test_user_settings.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE user_settings (
                user_id INTEGER NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                PRIMARY KEY (user_id, setting_key)
            )
        """)
        await db.commit()
    return db_path


async def test_preference_defaults_to_false_for_new_user(tmp_path, monkeypatch):
    db_path = await _make_user_settings_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    # Never set for this user — must default to False, not error or None.
    result = await portfolio.get_nft_inclusion_preference(USER_ID)
    assert result is False


async def test_preference_round_trips_through_real_db(tmp_path, monkeypatch):
    db_path = await _make_user_settings_db(tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    assert await portfolio.get_nft_inclusion_preference(USER_ID) is False

    await database.set_user_setting(USER_ID, portfolio.NFT_INCLUSION_SETTING_KEY, "1")
    assert await portfolio.get_nft_inclusion_preference(USER_ID) is True

    await database.set_user_setting(USER_ID, portfolio.NFT_INCLUSION_SETTING_KEY, "0")
    assert await portfolio.get_nft_inclusion_preference(USER_ID) is False

    # A different user is unaffected by user A's setting.
    other_user = USER_ID + 1
    await database.set_user_setting(USER_ID, portfolio.NFT_INCLUSION_SETTING_KEY, "1")
    assert await portfolio.get_nft_inclusion_preference(other_user) is False


# ---------------------------------------------------------------------------
# 2. /portfolio/instant
# ---------------------------------------------------------------------------

def _fake_position(symbol, source_type, quantity, price):
    return {
        "symbol": symbol, "quantity": quantity, "source_type": source_type,
        "source_detail": "", "chain": "cardano", "last_price_usd": price,
    }


async def _run_instant(monkeypatch, include_nfts: bool, nft_value=NFT_VALUE_USD):
    monkeypatch.setattr(database, "get_all_portfolio_positions",
                         lambda user_id: _positions_fixture())
    monkeypatch.setattr(database, "get_positions_freshness",
                         lambda user_id: _freshness_fixture())
    monkeypatch.setattr(portfolio.pricing_service, "get_all_tracked_prices",
                         _prices_fixture)
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference",
                         lambda user_id: _bool_fixture(include_nfts))
    monkeypatch.setattr(nfts_router, "get_all_chains_nft_summary",
                         lambda user_id: _nft_summary_fixture(nft_value))
    return await portfolio.get_portfolio_instant(user_id=USER_ID)


async def _positions_fixture():
    return [_fake_position("ADA", "chain", 1000.0, 0.226)]


async def _freshness_fixture():
    return {"oldest": None, "newest": None, "count": 1}


async def _prices_fixture():
    return {"ADA": {"usd": 0.226}}


async def _bool_fixture(value):
    return value


async def _async_none():
    return None


async def _nft_summary_fixture(value):
    return {"total_value_usd": value, "chains": {}}


async def test_instant_excludes_nfts_by_default(monkeypatch):
    data = await _run_instant(monkeypatch, include_nfts=False)
    assert "nft" not in data["breakdown"]
    assert data["total_usd"] == pytest.approx(226.0)


async def test_instant_includes_nfts_when_enabled(monkeypatch):
    data = await _run_instant(monkeypatch, include_nfts=True)
    assert data["breakdown"]["nft"] == pytest.approx(NFT_VALUE_USD)
    assert data["total_usd"] == pytest.approx(226.0 + NFT_VALUE_USD)


# ---------------------------------------------------------------------------
# 3 & 4. History endpoints — /portfolio/history and /balance-history/data
# ---------------------------------------------------------------------------

async def _daily_totals_fixture():
    return [{
        "date": "2026-09-18",
        "total_value": 17225.86,
        "on_chain_value": 13000.0,
        "exchange_value": 1109.58,
        "staking_value": 0.0,
        "defi_value": 0.0,
        "nft_value": NFT_VALUE_USD,
        "tracked_tokens_value": 0.0,
        "custom_tokens_value": 0.0,
    }]


async def test_portfolio_history_excludes_nfts_by_default(monkeypatch):
    monkeypatch.setattr(portfolio, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None, end_date=None: _daily_totals_fixture())
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", lambda user_id: _bool_fixture(False))

    result = await portfolio.get_portfolio_history(user_id=USER_ID, range="7d")
    point = result["data"][0]
    assert point["breakdown"]["nfts"] == pytest.approx(NFT_VALUE_USD)  # informational, always reported
    assert point["value"] == pytest.approx(17225.86 - NFT_VALUE_USD)


async def test_portfolio_history_includes_nfts_when_enabled(monkeypatch):
    monkeypatch.setattr(portfolio, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None, end_date=None: _daily_totals_fixture())
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", lambda user_id: _bool_fixture(True))

    result = await portfolio.get_portfolio_history(user_id=USER_ID, range="7d")
    point = result["data"][0]
    assert point["value"] == pytest.approx(17225.86)


async def test_balance_history_data_excludes_nfts_by_default(monkeypatch):
    monkeypatch.setattr(balance_history, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None, end_date=None: _daily_totals_fixture())
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", lambda user_id: _bool_fixture(False))

    result = await balance_history.get_history_data(user_id=USER_ID, range="1w")
    point = result["data"][0]
    assert point["value"] == pytest.approx(17225.86 - NFT_VALUE_USD)
    assert point["total_value"] == point["value"]


async def test_balance_history_data_includes_nfts_when_enabled(monkeypatch):
    monkeypatch.setattr(balance_history, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None, end_date=None: _daily_totals_fixture())
    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", lambda user_id: _bool_fixture(True))

    result = await balance_history.get_history_data(user_id=USER_ID, range="1w")
    assert result["data"][0]["value"] == pytest.approx(17225.86)


# ---------------------------------------------------------------------------
# 5. Headline (/portfolio/instant) and history (/balance-history/data) must
#    move by the SAME NFT amount when the preference flips. This is the
#    actual "headline and history disagree" regression from the original
#    bug report -- guard the fix, not just each endpoint in isolation.
# ---------------------------------------------------------------------------

async def test_headline_and_history_move_by_the_same_nft_amount(monkeypatch):
    # Headline (/portfolio/instant)
    monkeypatch.setattr(database, "get_all_portfolio_positions",
                         lambda user_id: _positions_fixture())
    monkeypatch.setattr(database, "get_positions_freshness",
                         lambda user_id: _freshness_fixture())
    monkeypatch.setattr(portfolio.pricing_service, "get_all_tracked_prices",
                         _prices_fixture)
    monkeypatch.setattr(nfts_router, "get_all_chains_nft_summary",
                         lambda user_id: _nft_summary_fixture(NFT_VALUE_USD))

    # History (/balance-history/data)
    monkeypatch.setattr(balance_history, "get_username_by_user_id", lambda user_id: _async_none())
    monkeypatch.setattr(database, "get_unified_daily_totals",
                         lambda user_id, start_date=None, end_date=None: _daily_totals_fixture())

    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", lambda user_id: _bool_fixture(False))
    headline_off = (await portfolio.get_portfolio_instant(user_id=USER_ID))["total_usd"]
    history_off = (await balance_history.get_history_data(user_id=USER_ID, range="1w"))["data"][0]["value"]

    monkeypatch.setattr(portfolio, "get_nft_inclusion_preference", lambda user_id: _bool_fixture(True))
    headline_on = (await portfolio.get_portfolio_instant(user_id=USER_ID))["total_usd"]
    history_on = (await balance_history.get_history_data(user_id=USER_ID, range="1w"))["data"][0]["value"]

    headline_delta = headline_on - headline_off
    history_delta = history_on - history_off
    assert headline_delta == pytest.approx(NFT_VALUE_USD)
    assert history_delta == pytest.approx(NFT_VALUE_USD)
    assert headline_delta == pytest.approx(history_delta)


# ---------------------------------------------------------------------------
# 6. /mobile/portfolio/summary
# ---------------------------------------------------------------------------

async def _run_mobile_summary(monkeypatch, include_nfts: bool):
    _install_fake_cache(monkeypatch)
    _stub_compute_upstreams(monkeypatch)
    # Override the NFT-summary stub to a nonzero value and set the preference
    # explicitly for this test (the shared stub defaults to 0/False already,
    # but we want both toggle states exercised here).
    monkeypatch.setattr(mobile.nfts, "get_all_chains_nft_summary",
                         lambda user_id: _nft_summary_fixture(NFT_VALUE_USD))
    monkeypatch.setattr(mobile.portfolio, "get_nft_inclusion_preference",
                         lambda user_id: _bool_fixture(include_nfts))
    return await mobile.get_mobile_portfolio_summary(
        user_id=USER_ID, refresh=False, include_sparklines=False)


async def test_mobile_summary_excludes_nfts_by_default(monkeypatch):
    result = await _run_mobile_summary(monkeypatch, include_nfts=False)
    assert result["breakdown"]["nfts"]["value_usd"] == pytest.approx(NFT_VALUE_USD)  # informational
    assert result["total_value_usd"] == pytest.approx(0.0)  # NFT not folded into total


async def test_mobile_summary_includes_nfts_when_enabled(monkeypatch):
    result = await _run_mobile_summary(monkeypatch, include_nfts=True)
    assert result["total_value_usd"] == pytest.approx(NFT_VALUE_USD)
