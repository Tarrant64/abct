"""
Regression tests for ABCT-BGSYNC-LOGGER-20260919.

Root cause: routers/wallets.py never defined a module-level `logger` (no
`import logging`, no `logger = logging.getLogger(__name__)`), yet two
except-blocks inside _refresh_wallet_balance referenced a bare `logger`:

  - the Ethereum branch's ENS-reverse-resolution except (line ~812),
    meant to non-fatally swallow a failed ENS lookup after the wallet's
    real balance/assets had already been saved;
  - the Solana branch's "all sources failed" except (line ~852), meant to
    log a descriptive message when neither Helius nor the public RPC
    returned data.

Both paths only execute when something ELSE has already gone wrong (a
failed ENS lookup, a failed balance fetch) -- exactly the kind of path
nothing routinely exercises, which is why this shipped unnoticed for
months (git blame: 2026-02-05 and 2026-02-15) until the new background
sync (ABCT-BGSYNC-20260919) started calling _refresh_wallet_balance far
more often than any manual refresh ever had, and hit the ENS branch for
the first time in months.

Effect of the bug: the attempt to log the ORIGINAL failure via
`logger.debug(...)` / `logger.error(...)` itself raised NameError, which
propagated out of the inner except entirely and was caught instead by
_refresh_wallet_balance's OUTER catch-all, which returned
{'success': False, 'error': "name 'logger' is not defined"} -- losing the
real cause. For the Ethereum/ENS case this is worse than just a bad log
message: the wallet's balance and native assets were ALREADY saved
successfully (save_balance/save_native_assets run before the ENS block),
but the function still reported the whole refresh as a failure.

Fix: routers/wallets.py now defines `logger = logging.getLogger(__name__)`
at module level (matching every other router in this codebase), and the
function's outer except now logs the real exception (type + message +
wallet id + blockchain + address) and returns an `error_type` field
alongside `error` so callers (like the background scheduler) can report
something more useful than a bare string.

These tests call the REAL _refresh_wallet_balance with only the chain
service and DB writes mocked -- not _refresh_wallet_balance itself -- so
they exercise the actual (previously broken) except blocks.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.wallets as wallets_router  # noqa: E402
from services.moralis import moralis_service  # noqa: E402


def _eth_wallet(wallet_id=7):
    return {"id": wallet_id, "address": "0xdeadbeef", "blockchain": "ethereum", "label": "W7"}


def _sol_wallet(wallet_id=8):
    return {"id": wallet_id, "address": "SoLanaAddr111", "blockchain": "solana", "label": "W8"}


@pytest.mark.asyncio
async def test_ethereum_ens_failure_is_swallowed_not_reported_as_wallet_failure(monkeypatch):
    """This is exactly what wallet 7 almost certainly hit in production:
    a real balance fetch succeeds, ENS reverse-resolution then raises, and
    the wallet's refresh must still be reported as successful (its balance
    was already saved) -- not masked as a failure by a broken log call."""

    saved_balances = []
    saved_assets = []

    async def fake_get_address_balance(address):
        return {
            "balance_eth": 1.5,
            "tokens": [],
            "token_count": 0,
            "source": "alchemy",
        }

    async def fake_save_balance(wallet_id, amount, unit):
        saved_balances.append((wallet_id, amount, unit))

    async def fake_save_native_assets(wallet_id, assets):
        saved_assets.append((wallet_id, assets))

    async def fake_is_configured():
        return True

    async def fake_resolve_address_to_ens(address):
        raise RuntimeError("moralis rate limited")

    monkeypatch.setattr(wallets_router.ethereum_service, "get_address_balance", fake_get_address_balance)
    monkeypatch.setattr(wallets_router, "save_balance", fake_save_balance)
    monkeypatch.setattr(wallets_router, "save_native_assets", fake_save_native_assets)
    monkeypatch.setattr(moralis_service, "is_configured", fake_is_configured)
    monkeypatch.setattr(moralis_service, "resolve_address_to_ens", fake_resolve_address_to_ens)

    result = await wallets_router._refresh_wallet_balance(_eth_wallet())

    # The regression: pre-fix, this was {'success': False,
    # 'error': "name 'logger' is not defined"} because the ENS except
    # block's own logging call crashed and got caught by the OUTER
    # catch-all instead. Post-fix, the ENS failure is swallowed exactly as
    # originally intended and the refresh is reported as successful.
    assert result["success"] is True, (
        f"ENS lookup failure should not fail the whole wallet refresh -- got {result!r}"
    )
    assert "ens_name" not in result
    assert result.get("error") is None
    assert result.get("error_type") is None

    # And the real point: the wallet's actual balance/assets were saved
    # regardless of the ENS outcome.
    assert saved_balances == [(7, "1.5", "ETH")]
    assert saved_assets == [(7, [])]


@pytest.mark.asyncio
async def test_solana_all_sources_failed_reports_real_message_not_logger_crash(monkeypatch):
    """The other broken call site: when Solana balance fetch genuinely
    fails from every source, the descriptive error must survive -- not get
    replaced by "name 'logger' is not defined"."""

    async def fake_get_address_info(address):
        return None  # every source failed

    monkeypatch.setattr(wallets_router.solana_service, "get_address_info", fake_get_address_info)

    result = await wallets_router._refresh_wallet_balance(_sol_wallet())

    assert result["success"] is False
    assert result["error"] == "Failed to fetch balance from all sources (Helius + public RPC)", (
        f"expected the real descriptive error, got {result!r} -- pre-fix this "
        f"was masked as \"name 'logger' is not defined\""
    )
