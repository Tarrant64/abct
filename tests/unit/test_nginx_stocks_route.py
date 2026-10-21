"""
WQ-0382 nginx routing contract: the stocks API must be reachable through the
container's nginx the same way /custom-tokens is.

The classic frontend (and stocks-tab.js) fetches `${API_BASE}/stocks` with
API_BASE='' -- the SAME no-prefix path shape as the tokens tab -- so the route
only works if nginx's direct-API whitelist regex lists `stocks`. It was not
(verified against the deployed container 2026-10-21: /stocks returned the
static SPA HTML while /custom-tokens proxied). This test pins the whitelist
in BOTH nginx configs, emulates the regex against the real client paths, and
keeps every pre-existing prefix working.
"""

import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WHITELIST_RE = re.compile(
    r"location ~ \^/\(([^)]*)\)\(/\|\$\)")


def _whitelist(fname):
    with open(os.path.join(REPO, "abct-docker", fname), encoding="utf-8") as f:
        m = WHITELIST_RE.search(f.read())
    assert m, f"direct-API whitelist regex not found in {fname}"
    return set(m.group(1).split("|"))


def test_stocks_in_direct_api_whitelist_both_configs():
    for fname in ("nginx.conf", "nginx-ssl.conf"):
        prefixes = _whitelist(fname)
        assert "stocks" in prefixes, f"{fname} whitelist lacks 'stocks'"
        # stocks must not shadow or replace anything that was there
        for legacy in ("wallets", "portfolio", "custom-tokens", "search",
                       "pnl", "privacy", "health"):
            assert legacy in prefixes, f"{fname} lost '{legacy}'"


def test_whitelist_regex_matches_real_client_paths():
    # Same alternation nginx compiles, applied to the paths the frontend
    # actually requests (API_BASE='' -- see app.js line 3).
    for fname in ("nginx.conf", "nginx-ssl.conf"):
        pattern = re.compile(
            r"^/(" + "|".join(sorted(_whitelist(fname))) + r")(/|$)")
        for path in ("/stocks", "/stocks/1", "/stocks/1/history",
                     "/stocks/scheduler", "/stocks/scheduler/run",
                     "/stocks/search?q=NVDA", "/custom-tokens", "/health"):
            assert pattern.match(path), f"{fname}: {path} would NOT proxy"
        # static pages and lookalikes must still fall through to the SPA
        for path in ("/stocks.html", "/stockings", "/", "/assets.html"):
            assert not pattern.match(path), f"{fname}: {path} wrongly proxied"


def test_both_configs_share_the_same_whitelist():
    assert _whitelist("nginx.conf") == _whitelist("nginx-ssl.conf"), \
        "the two nginx configs must route the same API prefixes"
