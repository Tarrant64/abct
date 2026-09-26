"""
Unit tests for ABCT-MOBILE-CHART-TOTAL-20260921:

The mobile app's Overview chart (/api/mobile/chart/portfolio-history) and
Overview header (/api/mobile/portfolio/summary) disagreed on the current
value, for every range. Root cause: the chart's latest point comes from
wallet_daily_balances, a periodically-collected snapshot written on its own
schedule by services/offchain_collector.py and engine/materializer.py, while
the header (_compute_mobile_portfolio_summary) recomputes live on every
call -- the two can (and did) disagree on "now" even though both already
apply the same NFT-inclusion gate (fixed earlier the same day in
ec4b72a/28a8877 for ABCT-MOBILE-VALUE-MISMATCH-20260921).

Rather than reconcile two independently computed numbers, the fix makes the
chart's LATEST point reuse the header's own live computation verbatim
(_apply_live_total_to_latest_chart_point in routers/mobile.py). These tests
cover that override: the latest point matches the live summary total for
every range, earlier points are untouched, demo users are exempt, and a
failure in the override degrades gracefully instead of losing the response.
"""

import os
import sys
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402
from auth_utils import verify_session  # noqa: E402

URL = "/api/mobile/chart/portfolio-history"

# Stale wallet_daily_balances-derived total for "today" -- deliberately far
# from the live summary total below, so a passing test proves the override
# actually ran rather than the two numbers coincidentally matching.
STALE_TODAY_TOTAL = 19844.24
LIVE_TOTAL = 18479.01


def _points(n, last_date="2026-09-21T00:00:00Z"):
    pts = [{
        'date': f'2026-06-{i + 1:02d}T00:00:00Z',
        'total_value': 1000.0 + i,
        'on_chain_value': 700.0 + i,
        'off_chain_value': 300.0,
        'breakdown': {'components': {
            'wallets': 500.0, 'staking': 100.0, 'defi': 50.0,
            'exchange': 200.0, 'nfts': 100.0, 'tracked_tokens': 50.0,
        }},
    } for i in range(n - 1)]
    pts.append({
        'date': last_date,
        'total_value': STALE_TODAY_TOTAL,
        'on_chain_value': 0.0,
        'off_chain_value': 0.0,
        'breakdown': {'components': {
            'wallets': 0.0, 'staking': 0.0, 'defi': 0.0,
            'exchange': 0.0, 'nfts': 0.0, 'tracked_tokens': 0.0,
        }},
    })
    return pts


def _live_summary():
    return {
        'total_value_usd': LIVE_TOTAL,
        'breakdown': {
            'self_custody': {'value_usd': 12814.21, 'percentage': 0},
            'exchanges': {'value_usd': 1196.76, 'percentage': 0},
            'nfts': {'value_usd': 2898.38, 'percentage': 0},
            'staking': {'value_usd': 1888.19, 'percentage': 0},
            'defi': {'value_usd': 2579.85, 'percentage': 0},
            'tracked_tokens': {'value_usd': 0, 'percentage': 0},
            'custom_tokens': {'value_usd': 0, 'percentage': 0},
        },
    }


@pytest.fixture
def client(monkeypatch):
    async def fake_unified(user_id=None, range=None):
        return {'data': _points(7)}

    async def fake_hourly(user_id=None, refresh=False):
        return {'data': _points(24, last_date="2026-09-22T01:00:00Z")}

    async def fake_username(user_id):
        return "not-a-demo-user"

    async def fake_is_demo_user(username):
        return False

    async def fake_summary(user_id, refresh, include_sparklines):
        return _live_summary()

    class FrozenDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return datetime(2026, 9, 22, 1, 30, 0)

    monkeypatch.setattr(mobile.portfolio, "get_unified_chart", fake_unified)
    monkeypatch.setattr(mobile.portfolio, "get_24h_hourly_chart", fake_hourly)
    monkeypatch.setattr(mobile, "get_username_by_user_id", fake_username)
    monkeypatch.setattr(mobile, "is_demo_user", fake_is_demo_user)
    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", fake_summary)
    monkeypatch.setattr(mobile, "datetime", FrozenDatetime)
    app = FastAPI()
    app.include_router(mobile.router)
    app.dependency_overrides[verify_session] = lambda: 1
    return TestClient(app)


def test_latest_point_matches_live_summary_total(client):
    body = client.get(URL).json()
    assert body['chart_data'][-1]['total_value_usd'] == LIVE_TOTAL
    assert body['chart_data'][-1]['total_value_usd'] != STALE_TODAY_TOTAL


def test_latest_point_breakdown_reflects_live_summary(client):
    point = client.get(URL).json()['chart_data'][-1]
    assert point['on_chain_value_usd'] == 12814.21
    assert point['breakdown']['exchanges'] == 1196.76
    assert point['breakdown']['staking'] == 1888.19
    assert point['breakdown']['defi'] == 2579.85
    assert point['breakdown']['nfts'] == 2898.38
    assert point['breakdown']['tracked_tokens'] == 0
    # off_chain = total - self_custody - tracked_tokens - custom_tokens
    assert point['off_chain_value_usd'] == round(LIVE_TOTAL - 12814.21 - 0 - 0, 2)


def test_historical_points_untouched(client):
    body = client.get(URL).json()
    for i, point in enumerate(body['chart_data'][:-1]):
        assert point['total_value_usd'] == 1000.0 + i
        assert point['on_chain_value_usd'] == 700.0 + i


def test_top_level_summary_reflects_override(client):
    body = client.get(URL).json()
    # ending_value/highest_value must track the corrected latest point, not
    # the stale wallet_daily_balances value -- otherwise the chart's own
    # start/end/high/low strip would re-introduce the same mismatch.
    assert body['summary']['ending_value'] == LIVE_TOTAL
    assert body['summary']['highest_value'] == LIVE_TOTAL


def test_24h_range_latest_point_also_overridden(client):
    body = client.get(URL + "?range=24h").json()
    assert body['chart_data'][-1]['total_value_usd'] == LIVE_TOTAL


def test_slim_mode_latest_point_matches_total(client):
    body = client.get(URL + "?slim=true").json()
    assert body['chart_data'][-1]['total_value_usd'] == LIVE_TOTAL
    assert set(body['chart_data'][-1].keys()) == {'timestamp', 'total_value_usd'}


def test_demo_user_keeps_stale_point_untouched(client, monkeypatch):
    async def fake_is_demo_user(username):
        return True

    async def summary_should_not_be_called(user_id, refresh, include_sparklines):
        raise AssertionError("live summary must not be fetched for demo users")

    monkeypatch.setattr(mobile, "is_demo_user", fake_is_demo_user)
    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", summary_should_not_be_called)

    body = client.get(URL).json()
    assert body['chart_data'][-1]['total_value_usd'] == STALE_TODAY_TOTAL


def test_override_failure_degrades_to_original_point(client, monkeypatch):
    async def failing_summary(user_id, refresh, include_sparklines):
        raise RuntimeError("upstream data source unavailable")

    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", failing_summary)

    resp = client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body['chart_data'][-1]['total_value_usd'] == STALE_TODAY_TOTAL
    assert body['data_points'] == 7


def test_override_skipped_when_no_data_points(client, monkeypatch):
    async def empty_unified(user_id=None, range=None):
        return {'data': []}

    async def summary_should_not_be_called(user_id, refresh, include_sparklines):
        raise AssertionError("live summary must not be fetched when there is no chart data")

    monkeypatch.setattr(mobile.portfolio, "get_unified_chart", empty_unified)
    monkeypatch.setattr(mobile, "_compute_mobile_portfolio_summary", summary_should_not_be_called)

    body = client.get(URL).json()
    assert body['chart_data'] == []
    assert body['data_points'] == 0
