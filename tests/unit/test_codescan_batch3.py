"""Tests for code-scanning batch 3: analytics/intelligence endpoints must not leak exception text."""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from auth_utils import verify_session  # noqa: E402
from routers import analytics, intelligence  # noqa: E402
from services.chain_analytics import chain_analytics_service  # noqa: E402

LEAK_MARKER = "ExceptionTextMarker123"


async def _aboom(*a, **kw):
    raise RuntimeError(LEAK_MARKER)


def _client(router):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[verify_session] = lambda: 1
    return TestClient(app, raise_server_exceptions=False)


def _check(resp, keys, name):
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert LEAK_MARKER not in resp.text
    assert body["error"].endswith("(RuntimeError)")
    assert set(body) == set(keys) | {"success", "error"}, name


@pytest.mark.parametrize("method,path,extra_keys", [
    ("get_chain_overview", "/analytics/chain-metrics", ["chains"]),
    ("get_chain_overview", "/analytics/chain-metrics/Ethereum", []),
    ("get_chain_fees_history", "/analytics/chain-fees-history/Ethereum", ["history"]),
    ("get_top_cryptos", "/analytics/market/top-cryptos", ["cryptos", "source"]),
])
def test_analytics_error_is_generic(monkeypatch, method, path, extra_keys):
    monkeypatch.setattr(chain_analytics_service, method, _aboom)
    _check(_client(analytics.router).get(path), extra_keys, path)


def test_analytics_logs_real_exception(monkeypatch, caplog):
    monkeypatch.setattr(chain_analytics_service, "get_chain_overview", _aboom)
    with caplog.at_level("ERROR"):
        _client(analytics.router).get("/analytics/chain-metrics")
    assert LEAK_MARKER in caplog.text


def test_no_str_e_in_response_sources():
    for name in ("analytics.py", "intelligence.py"):
        src = open(os.path.join(BACKEND_DIR, "routers", name)).read()
        assert '"error": str(e)' not in src, name


def test_intelligence_counterparties_error_is_generic(monkeypatch):
    monkeypatch.setattr(intelligence, "get_username_by_user_id", _aboom)
    resp = _client(intelligence.router).get("/intelligence/counterparties")
    _check(resp, ["counterparties"], "counterparties")
