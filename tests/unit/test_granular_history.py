"""
WQ-0385 pins: dashboard Stocks stat card (replacing Transactions (7d)) and
the granular (intraday) portfolio-history mode.

The intraday math (bucketize/forward-fill/grid) is pure and tested directly;
the network paths are not exercised here (same policy as the stock engine
tests). Frontend pins are source-of-record like the other contract tests.
"""

import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- engine

def test_bucketize_takes_last_price_per_window():
    from services.intraday_history import _bucketize
    series = [(0, 1.0), (100, 2.0), (299, 3.0), (301, 4.0), (700, 5.0)]
    out = _bucketize(series, 300)
    assert out == {0: 3.0, 300: 4.0, 600: 5.0}


def test_forward_fill_carries_through_gaps():
    from services.intraday_history import _forward_fill
    buckets = {300: 10.0, 900: 12.0}
    grid = [0, 300, 600, 900, 1200]
    assert _forward_fill(buckets, grid) == [None, 10.0, 10.0, 12.0, 12.0]


def test_intraday_ranges_are_the_supported_pairs():
    from services.intraday_history import INTRADAY_RANGES
    # 24h at 5-minute buckets, 1w hourly -- CoinGecko free-tier granularity
    # (verified live: days=1 -> 5min, days=7 -> hourly).
    assert INTRADAY_RANGES == {"24h": (1, 300), "1w": (7, 3600)}


def test_granular_flag_only_shortcuts_short_ranges():
    src = _read("backend", "routers", "balance_history.py")
    assert 'if granular is True and range in ("24h", "1w"):' in src, \
        "granular must map only 24h/1w to intraday (strict True: direct " \
        "callers pass the Query marker, which is truthy)"
    assert "granular_unavailable" in src, \
        "failure must degrade to daily with a flag, never error the chart"


# ---------------------------------------------------------------- frontend

def test_stocks_stat_card_replaced_transactions_card():
    html = _read("frontend", "v2", "index.html")
    assert 'id="statStocks"' in html, "Stocks stat card missing"
    assert "Transactions (7d)" not in html, "old tx card must be gone from v2"
    # placement: Stocks sits after Exchanges, 7-Day Change moved down after it
    assert html.index("Exchanges") < html.index("Stocks") < html.index("7-Day Change")
    app = _read("frontend", "v2", "js", "v2-app.js")
    assert "function renderStocksStat" in app
    assert "statTx7d" not in app, "no tx-stat render path may remain"
    assert "renderStocksStat(results[3].value.data)" in app
    assert "renderStocksStat(data);" in app, "sync path must refresh the card"


def test_chart_detail_toggle_wired():
    html = _read("frontend", "v2", "index.html")
    assert 'id="chartDetailToggle"' in html
    assert "setChartDetail(true)" in html and "setChartDetail(false)" in html
    assert 'data-range="24h"' in html, "24H range button must exist"
    app = _read("frontend", "v2", "js", "v2-app.js")
    assert "function setChartDetail" in app
    assert "&granular=true" in app
    assert "detailAvailable" in app, "detail must hide itself on ranges without data"
    # spiky rendering: straight lines + real points in intraday mode
    assert "tension: isIntraday ? 0 : 0.35" in app
    assert "data.mode === 'intraday'" in app


def test_header_controls_are_static():
    """WQ-0387: the range buttons and Smooth/Detail pill must not move when
    ranges change or the detail note appears (user screenshots: controls
    drifted left/right). The pill is disabled-in-place, never removed, and
    the note lives OUTSIDE the flex header row."""
    html = _read("frontend", "v2", "index.html")
    assert 'class="v2-chart-controls"' in html, \
        "ranges + detail toggle must sit in one pinned right-hand group"
    # note must not be a header flex child (a 100%-width child inside the
    # header was what re-centered the buttons when it appeared)
    header = html[html.index('v2-chart-header'):html.index('chartContainer')]
    assert 'id="chartDetailNote"' not in header.split('</div>\n                    </div>')[0] \
        or 'margin:-6px 0 8px' in html
    css = _read("frontend", "v2", "css", "v2.css")
    assert ".v2-chart-controls" in css and "flex-shrink: 0" in css
    assert "v2-detail-disabled" in css
    app = _read("frontend", "v2", "js", "v2-app.js")
    assert "v2-detail-disabled" in app
    assert "btn.disabled = !detailAvailable" in app
    assert "btn.style.display = detailAvailable" not in app, \
        "hiding the buttons was the drift; disable in place instead"


def test_detail_preference_persists_and_reapplies():
    app = _read("frontend", "v2", "js", "v2-app.js")
    assert "v2_chart_detail" in app, "detail mode must persist across loads"
