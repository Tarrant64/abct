"""
Unit tests for the opt-in slim chart payload (DASHBOARD-4,
/api/mobile/chart/portfolio-history?slim=true).

Slim contract: chart_data points are exactly {timestamp, total_value_usd};
range/interval/data_points/summary/last_updated unchanged; default
(no param or slim=false) keeps the full per-point breakdown. Upstream
chart sources are faked — no DB, no server.
"""

import os
import sys
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile  # noqa: E402
from auth_utils import verify_session  # noqa: E402

URL = "/api/mobile/chart/portfolio-history"


def _points(n):
    return [{
        'date': f'2026-06-{i + 1:02d}T00:00:00Z',
        'total_value': 1000.0 + i,
        'on_chain_value': 700.0 + i,
        'off_chain_value': 300.0,
        'breakdown': {'components': {
            'wallets': 500.0, 'staking': 100.0, 'defi': 50.0,
            'exchange': 200.0, 'nfts': 100.0, 'tracked_tokens': 50.0,
        }},
    } for i in range(n)]


@pytest.fixture
def client(monkeypatch):
    async def fake_unified(user_id=None, range=None):
        return {'data': _points(7)}

    async def fake_hourly(user_id=None, refresh=False):
        return {'data': _points(24)}

    class FrozenDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return datetime(2026, 7, 4, 12, 0, 0)

    monkeypatch.setattr(mobile.portfolio, "get_unified_chart", fake_unified)
    monkeypatch.setattr(mobile.portfolio, "get_24h_hourly_chart", fake_hourly)
    monkeypatch.setattr(mobile, "datetime", FrozenDatetime)  # stable last_updated
    app = FastAPI()
    app.include_router(mobile.router)
    app.dependency_overrides[verify_session] = lambda: 1
    return TestClient(app)


def test_default_keeps_full_shape(client):
    body = client.get(URL).json()
    point = body['chart_data'][0]
    assert set(point.keys()) == {
        'timestamp', 'total_value_usd', 'on_chain_value_usd',
        'off_chain_value_usd', 'breakdown'}
    assert set(point['breakdown'].keys()) == {
        'wallets', 'staking', 'defi', 'exchanges', 'nfts', 'tracked_tokens'}


def test_slim_false_identical_to_default(client):
    assert client.get(URL).content == client.get(URL + "?slim=false").content


def test_slim_points_have_exactly_contract_fields(client):
    full = client.get(URL).json()
    slim = client.get(URL + "?slim=true").json()
    assert set(slim.keys()) == set(full.keys())
    assert slim['summary'] == full['summary']
    assert slim['data_points'] == full['data_points'] == len(slim['chart_data'])
    for sp, fp in zip(slim['chart_data'], full['chart_data']):
        assert set(sp.keys()) == {'timestamp', 'total_value_usd'}
        assert sp['timestamp'] == fp['timestamp']
        assert sp['total_value_usd'] == fp['total_value_usd']


def test_slim_excludes_fields_from_body_bytes(client):
    content = client.get(URL + "?slim=true").content
    for banned in (b'breakdown', b'on_chain_value_usd', b'off_chain_value_usd'):
        assert banned not in content


def test_slim_and_full_etags_differ(client):
    full = client.get(URL)
    slim = client.get(URL + "?slim=true")
    assert full.headers['etag'] != slim.headers['etag']
    # and a full-response ETag must not 304 a slim request
    r = client.get(URL + "?slim=true", headers={"If-None-Match": full.headers['etag']})
    assert r.status_code == 200


def test_slim_works_on_24h_range(client):
    slim = client.get(URL + "?range=24h&slim=true").json()
    assert slim['data_points'] == 24
    assert all(set(p.keys()) == {'timestamp', 'total_value_usd'} for p in slim['chart_data'])
