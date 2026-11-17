"""Tests for code-scanning batch 2: URL log redaction, generic error text, JS escape helpers."""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from auth_utils import verify_session  # noqa: E402
from services.http_client import _redact_url  # noqa: E402

LEAK_MARKER = "ExceptionTextMarker123"


# --- URL redaction -----------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://api.example.com/v1/price?apikey=KEYVAL&x=1", "https://api.example.com/v1/price"),
    ("https://user:pw@api.example.com:8443/a/b?token=KEYVAL#frag", "https://api.example.com:8443/a/b"),
    ("https://api.example.com/plain", "https://api.example.com/plain"),
    ("https://api.example.com", "https://api.example.com"),
])
def test_redact_url_strips_query_userinfo_fragment(url, expected):
    out = _redact_url(url)
    assert out == expected
    assert "KEYVAL" not in out and "pw" not in out.split("//", 1)[-1].split("/")[0]


def test_redact_url_non_string_safe():
    assert isinstance(_redact_url(None), str)


async def test_fetch_with_retry_logs_no_query(monkeypatch, caplog):
    import httpx
    from services import http_client

    class FakeClient:
        async def request(self, method, url, **kw):
            return httpx.Response(503, request=httpx.Request(method, url))

    async def _nosleep(_):
        return None

    monkeypatch.setattr(http_client.asyncio, "sleep", _nosleep)
    with caplog.at_level("WARNING"):
        await http_client.fetch_with_retry(
            FakeClient(), "GET", "https://api.example.com/p?apikey=" + LEAK_MARKER, max_retries=1
        )
    assert caplog.records
    assert LEAK_MARKER not in caplog.text
    assert "api.example.com/p" in caplog.text


# --- router error text -------------------------------------------------------

def _boom(*a, **kw):
    raise RuntimeError(LEAK_MARKER)


async def _aboom(*a, **kw):
    raise RuntimeError(LEAK_MARKER)


def _client(router):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[verify_session] = lambda: 1
    return TestClient(app, raise_server_exceptions=False)


def test_mobile_nft_summary_generic_error(monkeypatch):
    import routers.mobile as mobile
    monkeypatch.setattr(mobile.nfts, "get_nft_summary", _aboom)
    r = _client(mobile.router).get("/api/mobile/nfts/summary")
    body = r.json()
    assert LEAK_MARKER not in r.text
    assert body["error"] == "Unable to load data"
    assert set(body) >= {"total_nfts", "total_collections", "total_floor_value_usd",
                         "collections", "last_updated", "error"}


def test_uniswap_generic_error(monkeypatch):
    import routers.defi as defi
    import services.graph as graph
    monkeypatch.setattr(graph.graph_service, "is_configured", _boom)
    r = _client(defi.router).get("/defi/uniswap-positions/0xabc")
    if r.status_code == 404:  # router mounted with its own prefix
        r = _client(defi.router).get(f"{defi.router.prefix}/uniswap-positions/0xabc")
    body = r.json()
    assert LEAK_MARKER not in r.text
    assert body["success"] is False and set(body) == {"success", "error"}


def test_quota_generic_error(monkeypatch):
    import routers.prices as prices

    async def bad_headers():
        raise RuntimeError(LEAK_MARKER)

    monkeypatch.setattr(prices.pricing_service, "_get_cg_headers", bad_headers)
    r = _client(prices.router).get(f"{prices.router.prefix}/quota")
    body = r.json()
    assert LEAK_MARKER not in r.text
    assert body["configured"] is False and "error" in body


# --- JS escape helpers (run under node) --------------------------------------

def _extract(path, signature):
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    start = src.index(signature)
    depth, i = 0, src.index("{", start)
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("path,sig,name", [
    ("frontend/js/pnl-tab.js", "function _escHtml(", "_escHtml"),
    ("frontend/js/wallet-intelligence.js", "function escapeHtml(", "escapeHtml"),
])
def test_js_escape_helpers_escape_quotes(path, sig, name):
    fn = _extract(path, sig)
    harness = r"""
const document = { createElement() {
  let t = '';
  return { set textContent(v) { t = String(v); },
           get innerHTML() { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); } };
}};
%s
const out = %s('"><img onerror=x(\'1\')> & ok');
console.log(JSON.stringify(out));
""" % (fn, name)
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    assert '"' not in out and "'" not in out and "<" not in out and ">" not in out
    assert "&quot;" in out and "&#39;" in out and "&amp;" in out


def test_wallet_intelligence_no_inline_onclick_for_address():
    src = open(os.path.join(ROOT, "frontend/js/wallet-intelligence.js"), encoding="utf-8").read()
    assert "onclick=\"copyAddress" not in src
    assert 'data-addr="${escapeHtml(addr)}"' in src
