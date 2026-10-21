"""
WQ-0383 routing-contract pins: /next is the default dashboard, the classic V1
UI is deprecated and lives at /legacy (user order 2026-10-21).

Pins (source-of-record, mirroring test_nginx_stocks_route.py's approach):
  1. backend/main.py: "/" redirects to /next/; /legacy serves the V1 index;
     /legacy/<page> resolves V1 pages (the old routes stay untouched).
  2. nginx (both configs): exact-match "location = /" 302s to /next/ BEFORE
     the try_files SPA fallback, and /legacy proxies to FastAPI instead of
     falling into try_files (which would serve the V1 index at /legacy).
  3. frontend/v2/assets.html: the Stocks tab is wired (button, panel, modal,
     script include, lazy-load hook).
"""

import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- backend

def test_root_redirects_to_next():
    main = _read("backend", "main.py")
    assert 'return RedirectResponse(url="/next/", status_code=302)' in main, \
        '"/" must redirect to /next/ (WQ-0383 default flip)'
    # the redirect must be the body of root(), not some unrelated handler
    m = re.search(r'@app\.get\("/"\)\s*\nasync def root\(\).*?\n(.*RedirectResponse\(url="/next/", status_code=302\))',
                  main, re.S)
    assert m, "root() itself must perform the /next/ redirect"


def test_legacy_routes_exist():
    main = _read("backend", "main.py")
    assert '@app.get("/legacy/")' in main, "/legacy/ must serve the V1 index"
    assert '@app.get("/legacy/{page}")' in main, "/legacy/<page> must resolve V1 pages"
    assert 'frontend_path / "index.html"' in main, "legacy index still comes from frontend/"
    # every old V1 route remains (deep links must keep working)
    for old in ("/assets.html", "/nfts.html", "/data.html", "/settings.html",
                "/login.html", "/help.html"):
        assert f'@app.get("{old}")' in main, f"legacy deep link {old} was removed"


# ---------------------------------------------------------------- nginx

def _nginx_body(fname):
    return _read("abct-docker", fname)


def test_nginx_root_sends_to_next_both_configs():
    for fname in ("nginx.conf", "nginx-ssl.conf"):
        body = _nginx_body(fname)
        assert re.search(r'location\s*=\s*/\s*\{\s*return\s+302\s+/next/;', body), \
            f"{fname}: exact-match location = / must 302 to /next/"
        # ordering: the exact match must come before the SPA try_files block
        assert body.index("return 302 /next/") < body.index("try_files $uri $uri/ /index.html"), \
            f"{fname}: root redirect placed after try_files (exact match wins in nginx, " \
            "but the order is pinned so a future edit cannot swap intent)"


def test_nginx_legacy_proxies_to_backend_both_configs():
    for fname in ("nginx.conf", "nginx-ssl.conf"):
        body = _nginx_body(fname)
        m = re.search(r"location /legacy \{([^}]*)\}", body)
        assert m, f"{fname}: /legacy location block missing"
        assert "proxy_pass http://127.0.0.1:8000;" in m.group(1), \
            f"{fname}: /legacy must proxy to FastAPI (try_files would serve V1 index at the wrong path)"


# ---------------------------------------------------------------- v2 assets page

def test_v2_assets_page_wires_the_stocks_tab():
    html = _read("frontend", "v2", "assets.html")
    assert 'data-tab="stocks"' in html, "Stocks tab button missing"
    assert 'id="tabStocks"' in html, "stocks panel missing"
    assert 'id="stocksContent"' in html, "stocks table container missing"
    assert 'id="v2StockModal"' in html, "add-stock modal missing"
    assert 'id="addStockBtn"' in html, "add-stock button missing"
    assert "/next/static/js/v2-stocks.js" in html, "v2-stocks.js not included"
    assert "loadStocksTab()" in html, "lazy-load hook not wired"
    assert "'stocks'" in html.split("Handle hash-based tab navigation")[1], \
        "hash routing must know the stocks tab"


def test_v2_stocks_script_uses_the_contracted_endpoints():
    js = _read("frontend", "v2", "js", "v2-stocks.js")
    for ep in ("'/stocks'", "'/stocks/search?q='", "'/stocks/' + stockId"):
        assert ep in js, f"v2-stocks.js missing endpoint {ep}"
    assert "v2Fetch" in js, "must use the v2 auth wrapper"
    # v1 stocks-tab.js keeps its own surface untouched
    v1 = _read("frontend", "js", "stocks-tab.js")
    assert "authFetch" in v1 and "loadStocks" in v1
