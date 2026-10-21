"""
Source-of-record pins for the WQ-0382 stocks frontend (behavior is exercised
under node in tests/unit/stocks_frontend_check.js; this file fails the pytest
suite if the shipped files drift from the contract the node check asserts).

Why pinned: the repo has no JS test runner wired into CI, so the integration
lines (portfolio totals including stocks, single shared `let` declarations,
v2 manual_stock buckets) can silently regress in any future frontend edit.
"""

import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


def test_app_totals_include_stocks_value():
    app = _read("frontend", "js", "app.js")
    assert ("const liquidTotal = walletsTotal + exchangesTotal + "
            "trackedTokensTotal + customTokensTotal + stocksTotal;" in app), \
        "liquid breakdown must include stocksTotal"
    assert ("return walletsTotal + exchangesTotal + stakingTotal + defiTotal "
            "+ nftsTotal + trackedTokensTotal + customTokensTotal + stocksTotal;"
            in app), "grand total getter must include stocksTotal"
    assert ("stocks: (typeof stocksValue !== 'undefined' && stocksValue) || 0"
            in app), "chart breakdown must carry its own stocks bucket"
    assert "value += breakdown.stocks || 0;" in app, \
        "calculateChartValues must add the stocks bucket"
    assert "stocks: 'Stocks'" in app, \
        "history tooltip label map must know the stocks bucket"


def test_stocks_bindings_declared_exactly_once():
    # Classic top-level `let` is a shared global lexical binding: declaring
    # stocksValue/stocks in BOTH scripts throws SyntaxError and kills
    # stocks-tab.js entirely (the tab silently renders nothing).
    app = _read("frontend", "js", "app.js")
    tab = _read("frontend", "js", "stocks-tab.js")
    assert app.count("let stocksValue") == 1, "app.js must declare stocksValue once"
    assert app.count("let stocks =") == 1, "app.js must declare stocks once"
    assert "let stocksValue" not in tab, "stocks-tab.js must NOT redeclare stocksValue"
    assert "let stocks =" not in tab, "stocks-tab.js must NOT redeclare stocks"


def test_v2_surface_knows_manual_stock_bucket():
    v2 = _read("frontend", "v2", "js", "v2-app.js")
    assert "parseFloat(bd.manual_stock)" in v2, \
        "v2 hero liquid must include the manual_stock breakdown bucket"
    assert "liquid += manualStockTotal;" in v2, \
        "v2 reconcileStatCards must re-add manual_stock (all-holdings lacks it)"


def test_assets_page_wires_the_stocks_tab():
    html = _read("frontend", "assets.html")
    assert "switchAssetsTab('stocks')" in html, "tab button must exist"
    assert 'id="stocksTab"' in html, "tab content div must exist"
    assert "id=\"addStockModal\"" in html, "add-stock modal must exist"
    assert "stocks-tab.js?v=" in html, "script must be included with cache-bust"
    assert "'stocks'" in html.split("const ASSETS_TABS")[1].split("]")[0], \
        "ASSETS_TABS must include stocks"
    assert "loadStocks()" in html, "lazy-load hook must call loadStocks"


def test_backend_positions_and_totals_carry_manual_stock():
    port = _read("backend", "routers", "portfolio.py")
    assert "'source_type': 'manual_stock'" in port, \
        "portfolio_positions write must tag manual stock rows"
    assert "manual_stocks_usd" in port, \
        "/portfolio/totals must compute the manual stocks bucket"
    assert "TOTALS_VALUATION_VERSION = 4" in port, \
        "valuation version bumped so cached pre-stocks totals rows expire"
