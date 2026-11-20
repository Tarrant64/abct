"""
Server-fixes item 6 (2026-11-20): P&L summary computed_at / uncovered, the
/api/mobile/pnl/* wrappers (router ETag -> 304) and the 409 job info.
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.mobile as mobile  # noqa: E402
import routers.pnl as pnl  # noqa: E402
from auth_utils import verify_session  # noqa: E402
from services.pricing import pricing_service  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    store = {}
    calls = {"perf": 0}

    async def get_cache(key, user_id=None):
        return store.get((user_id, key))

    async def set_cache(key, value, ttl_seconds=300, user_id=None):
        store[(user_id, key)] = value

    async def clear_cache(key, user_id=None):
        for k in [k for k in store if k[0] == user_id and key in k[1]]:
            del store[k]

    monkeypatch.setattr(database, "get_cache", get_cache)
    monkeypatch.setattr(database, "set_cache", set_cache)
    monkeypatch.setattr(database, "clear_cache", clear_cache)

    async def performance(user_id):
        calls["perf"] += 1
        return {"total_invested": 100.0, "current_value": 150.0, "total_unrealized": 50.0,
                "total_realized": 0.0, "total_pnl": 50.0, "pnl_percent": 50.0,
                "top_gainers": [], "top_losers": [], "assets_count": 1}

    async def unrealized(user_id, token=None):
        return [{"token_symbol": "BTC", "total_quantity": 0.001, "current_value": 150.0,
                 "total_invested": 100.0, "unrealized_gain": 50.0}]

    async def monthly(user_id, months=12):
        return [{"month": "2026-10", "realized": 12.5, "count": 2}]

    async def asset_detail(user_id, symbol):
        return {"token_symbol": symbol, "open_lots": []}

    eng = pnl.cost_basis_engine
    monkeypatch.setattr(eng, "get_portfolio_performance", performance)
    monkeypatch.setattr(eng, "compute_unrealized_pnl", unrealized)
    monkeypatch.setattr(eng, "get_monthly_realized", monthly)
    monkeypatch.setattr(eng, "get_asset_detail", asset_detail)

    async def positions(user_id):
        return [
            {"symbol": "BTC", "quantity": 0.001, "last_price_usd": 100000.0},
            {"symbol": "ADA", "quantity": 1000.0, "last_price_usd": 0.5},
            {"symbol": "ADA", "quantity": 500.0, "last_price_usd": 0.5},   # same symbol, other source
            {"symbol": "DUST", "quantity": 1.0, "last_price_usd": 0.01},
            {"symbol": "USD", "quantity": 99.0, "last_price_usd": 1.0},
        ]
    monkeypatch.setattr(database, "get_all_portfolio_positions", positions)

    async def prices():
        return {"ADA": {"usd": 0.6}}   # live price wins over last_price_usd
    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", prices)

    app = FastAPI()
    app.include_router(mobile.router)
    app.include_router(pnl.router)
    app.dependency_overrides[verify_session] = lambda: 7
    client = TestClient(app)
    client.calls = calls
    client.store = store
    return client


def test_summary_has_computed_at_and_uncovered(env):
    body = env.get("/pnl/summary").json()
    assert body["total_pnl"] == 50.0                       # legacy fields intact
    assert body["computed_at"].endswith("Z") and "T" in body["computed_at"]
    # BTC has lots -> covered; ADA (1500 x live 0.6) uncovered; dust and USD dropped
    assert body["uncovered"] == [{"symbol": "ADA", "value_usd": 900.0}]


def test_summary_is_cached_so_computed_at_is_stable_and_invalidated_on_write(env, monkeypatch):
    a = env.get("/pnl/summary").json()
    b = env.get("/pnl/summary").json()
    assert a["computed_at"] == b["computed_at"] and env.calls["perf"] == 1

    async def record_manual_lot(*args, **kw):
        return 1
    monkeypatch.setattr(pnl.cost_basis_engine, "record_manual_lot", record_manual_lot)
    r = env.post("/pnl/lots/manual", json={"token_symbol": "ada", "quantity": 1, "cost_per_unit": 1})
    assert r.status_code == 200
    env.get("/pnl/summary")
    assert env.calls["perf"] == 2                           # recomputed after the write


def test_mobile_summary_has_etag_and_conditional_get_304(env):
    r = env.get("/api/mobile/pnl/summary")
    assert r.status_code == 200
    assert r.json()["computed_at"] and "uncovered" in r.json()
    etag = r.headers["etag"]
    r2 = env.get("/api/mobile/pnl/summary", headers={"If-None-Match": etag})
    assert r2.status_code == 304 and r2.content == b""


def test_mobile_wrappers_match_legacy_and_carry_etag(env):
    for mobile_path, legacy_path in [
        ("/api/mobile/pnl/unrealized", "/pnl/unrealized"),
        ("/api/mobile/pnl/realized/monthly?months=6", "/pnl/realized/monthly?months=6"),
        ("/api/mobile/pnl/asset/btc", "/pnl/asset/btc"),
    ]:
        m = env.get(mobile_path)
        assert m.status_code == 200, mobile_path
        assert m.json() == env.get(legacy_path).json()
        assert m.headers.get("etag")
        assert env.get(mobile_path, headers={"If-None-Match": m.headers["etag"]}).status_code == 304


def test_409_names_the_running_job(env, monkeypatch):
    import asyncio

    started = {}

    async def hang(user_id, exchange, include_wallets):
        started["ran"] = True
        await asyncio.sleep(30)

    monkeypatch.setattr(pnl, "_run_compute", hang)
    pnl._compute_progress.clear()

    first = env.post("/pnl/compute")
    assert first.status_code == 202
    job_id = first.json()["job_id"]
    assert job_id

    second = env.post("/pnl/compute")
    assert second.status_code == 409
    body = second.json()
    assert body["detail"] == "Computation already in progress"
    assert body["job_id"] == job_id
    assert body["status"] == "starting"
    assert body["started_at"]

    # job_id survives whole-dict progress updates and shows in /compute/status
    pnl._compute_progress[7] = {"stage": "ingesting_transactions", "progress": 15, "details": "x"}
    st = env.get("/pnl/compute/status").json()
    assert st["job_id"] == job_id and st["stage"] == "ingesting_transactions"
    assert env.post("/pnl/compute/wallets").json()["job_id"] == job_id  # 409 body from wallets route too
    pnl._compute_progress.clear()
