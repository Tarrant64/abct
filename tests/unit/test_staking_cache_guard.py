"""
Tests for the staking cache survival + degraded-result guard (P0-FIX2).

Root cause of the 2026-07-12 "reverts to Iagon-only" regression: the startup
purge deleted staking_positions_% rows, removing both the stale fallback and
the guard baseline, so a degraded post-restart recompute cached Iagon-only
data for 24 h.

F1: startup purge spares staking_positions_% (defi_summary_% only).
F2: guard baseline falls back to the stale row — worse fresh results can
    never displace better last-good data (monotonic staleness).
F3: guard richness metric counts ALL position kinds, not just staked arrays.
"""

import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.defi as defi_router  # noqa: E402
from routers.defi import _count_data_protocols, get_staking_positions  # noqa: E402

ADDRESS = "addr1q9phspv20nxtestonly"

# Result shapes as produced by defi_service.get_all_staking_positions
FULL_RESULT = {
    "address": ADDRESS,
    "protocols": {
        "Indigo": {"staked": [{"token": "INDY", "amount": 8670.38}]},
        "Liqwid": {"staked": [{"token": "LQ", "amount": 2089.17}]},
        "Strike": {
            "staked": [],
            "v2_balance": 56.93,
            "v2_vault_positions": [{"vault_id": "v", "value_ada": 697.84}],
        },
        "Iagon": {"staked": [{"token": "IAG", "amount": 3858.0}]},
    },
    "total_positions": 8,
}

IAGON_ONLY_RESULT = {
    "address": ADDRESS,
    "protocols": {
        "Indigo": {"staked": []},
        "Strike": {"staked": [], "v2_balance": 0.0, "v2_vault_positions": []},
        "Iagon": {"staked": [{"token": "IAG", "amount": 3858.0}]},
    },
    "total_positions": 1,
}


# ---------------------------------------------------------------------------
# F1 — startup purge spares staking rows
# ---------------------------------------------------------------------------

async def test_startup_purge_spares_staking_rows(monkeypatch, tmp_path):
    import config
    import main

    db_path = tmp_path / "portfolio.db"
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE cache (user_id INTEGER, key TEXT, value TEXT,"
        " expires_at TEXT, PRIMARY KEY (user_id, key))"
    )
    rows = [
        (1, f"staking_positions_{ADDRESS}", "{}", "2027-01-01T00:00:00"),
        (1, "staking_positions_addr1qother", "{}", "2020-01-01T00:00:00"),
        (1, "defi_summary_1", "{}", "2027-01-01T00:00:00"),
        (None, "defi_summary_global", "{}", "2027-01-01T00:00:00"),
        (1, "iagon_staking_addr1qother", "{}", "2027-01-01T00:00:00"),
    ]
    db.executemany("INSERT INTO cache VALUES (?, ?, ?, ?)", rows)
    db.commit()
    db.close()

    monkeypatch.setattr(config, "DATABASE_PATH", db_path)

    cleared = await main._purge_startup_response_caches()

    assert cleared == 2  # only the defi_summary rows

    db = sqlite3.connect(db_path)
    remaining = sorted(r[0] for r in db.execute("SELECT key FROM cache"))
    db.close()
    assert remaining == [
        "iagon_staking_addr1qother",
        f"staking_positions_{ADDRESS}",
        "staking_positions_addr1qother",
    ]


# ---------------------------------------------------------------------------
# F3 — richness metric counts every position kind
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol_entry,counts", [
    ({"staked": [{"token": "INDY", "amount": 1}]}, True),
    ({"staked": []}, False),
    ({}, False),
    ({"staked": [], "v2_balance": 56.93}, True),
    ({"staked": [], "v2_balance": 0.0, "v2_vault_positions": []}, False),
    ({"staked": [], "v2_vault_positions": [{"value_ada": 697.0}]}, True),
    ({"staked": [], "cdps": [{"collateral_ada": 2500}]}, True),
    ({"staked": [], "stability_pool": [{"deposited": 120.5}]}, True),
])
def test_count_data_protocols_kinds(protocol_entry, counts):
    result = {"protocols": {"P": protocol_entry}}
    assert _count_data_protocols(result) == (1 if counts else 0)


def test_count_data_protocols_full_and_empty():
    assert _count_data_protocols(FULL_RESULT) == 4
    assert _count_data_protocols(IAGON_ONLY_RESULT) == 1
    assert _count_data_protocols({}) == 0
    assert _count_data_protocols({"protocols": {}}) == 0


# ---------------------------------------------------------------------------
# F2 — guard refuses downgrades, against fresh AND stale baselines
# ---------------------------------------------------------------------------

class CacheStub:
    """Replaces the router's cache functions; records set_cache calls."""

    def __init__(self, fresh=None, stale=None):
        self.fresh = fresh
        self.stale = stale
        self.set_calls = []

    async def get_cache(self, key, user_id=None):
        return self.fresh

    async def get_stale_cache(self, key, user_id=None):
        if self.stale is not None:
            return self.stale, "2026-07-13T00:00:00"
        return None, None

    async def set_cache(self, key, value, ttl, user_id=None):
        self.set_calls.append((key, value))


@pytest.fixture
def wire(monkeypatch):
    """Wire the route to a CacheStub and a canned compute result."""

    def _wire(fresh, stale, compute_result):
        stub = CacheStub(fresh=fresh, stale=stale)
        monkeypatch.setattr(defi_router, "get_cache", stub.get_cache)
        monkeypatch.setattr(defi_router, "get_stale_cache", stub.get_stale_cache)
        monkeypatch.setattr(defi_router, "set_cache", stub.set_cache)

        async def fake_username(user_id):
            return "admin"

        async def fake_is_demo(username):
            return False

        monkeypatch.setattr(defi_router, "get_username_by_user_id", fake_username)
        monkeypatch.setattr(defi_router, "is_demo_user", fake_is_demo)

        async def fake_compute(address, previous_result=None,
                               payment_creds=None, account_addresses=None):
            return dict(compute_result)

        monkeypatch.setattr(
            defi_router.defi_service, "get_all_staking_positions", fake_compute
        )

        # Identity resolution (P2) is exercised in test_wallet_context.py —
        # here it resolves to the single-address fallback without network.
        async def fake_context(address):
            return {"address": address, "stake_address": None,
                    "addresses": [address], "payment_creds": ["cred0"],
                    "resolved": False}

        monkeypatch.setattr(
            defi_router.defi_service, "resolve_wallet_context", fake_context
        )

        # Neutralize the fire-and-forget portfolio write's price fetch
        from services.pricing import pricing_service

        async def fake_prices():
            return {}

        monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)
        return stub

    return _wire


async def test_degraded_fresh_result_cannot_overwrite_fresh_baseline(wire):
    stub = wire(fresh=dict(FULL_RESULT), stale=None,
                compute_result=IAGON_ONLY_RESULT)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []  # degraded result never cached
    assert out["from_cache"] is True
    assert _count_data_protocols(out) == 4  # the better data is returned


async def test_degraded_fresh_result_cannot_overwrite_stale_baseline(wire):
    """The purge/TTL-expiry scenario behind the Iagon-only regression:
    no fresh row, but the stale row is richer than the degraded recompute."""
    stub = wire(fresh=None, stale=dict(FULL_RESULT),
                compute_result=IAGON_ONLY_RESULT)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert out["from_cache"] is True
    assert out["stale"] is True  # flagged so clients know it's last-good
    assert _count_data_protocols(out) == 4


async def test_equal_or_better_result_is_cached(wire):
    stub = wire(fresh=dict(IAGON_ONLY_RESULT), stale=None,
                compute_result=FULL_RESULT)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert len(stub.set_calls) == 1
    assert _count_data_protocols(stub.set_calls[0][1]) == 4
    assert out["from_cache"] is False


async def test_no_baseline_at_all_caches_whatever_computed(wire):
    stub = wire(fresh=None, stale=None, compute_result=IAGON_ONLY_RESULT)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert len(stub.set_calls) == 1  # nothing better exists — cache it
    assert _count_data_protocols(out) == 1


async def test_scope_change_bypasses_downgrade_guard(wire):
    """H2 (P2-FIX): when the identity partition legitimately shrinks (the
    user stored a sibling as its own wallet, moving a credential out of this
    row's claim), the corrected smaller result must be ACCEPTED — refusing it
    would wedge the over-scoped row and double-count against the new sibling
    row until a manual cache clear."""
    over_scoped = dict(FULL_RESULT)
    over_scoped["account_scan"] = {"payment_creds": 6, "addresses": 6}
    corrected = dict(IAGON_ONLY_RESULT)
    corrected["account_scan"] = {"payment_creds": 5, "addresses": 5}

    stub = wire(fresh=over_scoped, stale=None, compute_result=corrected)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert len(stub.set_calls) == 1  # accepted despite fewer protocols
    assert out["from_cache"] is False
    assert _count_data_protocols(out) == 1


async def test_same_scope_degraded_still_refused(wire):
    """Scope-change bypass must NOT weaken the guard when scope is equal."""
    full = dict(FULL_RESULT)
    full["account_scan"] = {"payment_creds": 6, "addresses": 6}
    degraded = dict(IAGON_ONLY_RESULT)
    degraded["account_scan"] = {"payment_creds": 6, "addresses": 6}

    stub = wire(fresh=full, stale=None, compute_result=degraded)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert _count_data_protocols(out) == 4


async def test_legacy_row_without_scope_guard_holds(wire):
    """Pre-P2 cached rows carry no account_scan — treated as single-address
    scope, so a single-address degraded recompute is still refused."""
    stub = wire(fresh=dict(FULL_RESULT), stale=None,
                compute_result=IAGON_ONLY_RESULT)  # neither has account_scan

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert _count_data_protocols(out) == 4


async def test_sub_source_loss_within_surviving_protocol_refused(wire):
    """A3 (P3a-FIX): Indigo CDPs failed while Indigo staking succeeded — the
    protocol survives but a position KIND vanished without confirmation.
    Per-kind granularity must refuse the write."""
    baseline = {
        "address": ADDRESS,
        "protocols": {"Indigo": {
            "staked": [{"token": "INDY", "amount": 8670.38}],
            "cdps": [{"asset": "iUSD", "collateral_ada": 2500.0}],
        }},
        "total_positions": 2,
    }
    degraded = {
        "address": ADDRESS,
        "protocols": {"Indigo": {
            "staked": [{"token": "INDY", "amount": 8670.38}],
            "cdps": [],
        }},
        "total_positions": 1,
    }

    stub = wire(fresh=baseline, stale=None, compute_result=degraded)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert out["protocols"]["Indigo"]["cdps"]  # baseline preserved


async def test_confirmed_exit_is_accepted(wire):
    """P3a: every lost protocol positively confirmed empty — a genuine exit
    must finally display instead of being pinned to stale data forever."""
    corrected = dict(IAGON_ONLY_RESULT)
    corrected["confirmed_empty"] = ["Indigo", "Liqwid", "Strike"]

    stub = wire(fresh=dict(FULL_RESULT), stale=None, compute_result=corrected)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert len(stub.set_calls) == 1  # accepted
    assert _count_data_protocols(out) == 1


async def test_partially_confirmed_loss_still_refused(wire):
    """Only Liqwid confirmed its exit; Indigo/Strike losses are unconfirmed
    fetch failures — the guard must refuse the whole downgrade."""
    corrected = dict(IAGON_ONLY_RESULT)
    corrected["confirmed_empty"] = ["Liqwid"]

    stub = wire(fresh=dict(FULL_RESULT), stale=None, compute_result=corrected)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert _count_data_protocols(out) == 4


async def test_equal_count_protocol_swap_refused(wire):
    """Name-based guard: losing Indigo while gaining Liqwid keeps the count
    equal but is still an unconfirmed loss — refused."""
    indigo_only = {
        "address": ADDRESS,
        "protocols": {"Indigo": {"staked": [{"token": "INDY", "amount": 1.0}]}},
        "total_positions": 1,
    }
    liqwid_only = {
        "address": ADDRESS,
        "protocols": {"Liqwid": {"staked": [{"token": "LQ", "amount": 1.0}]}},
        "total_positions": 1,
    }

    stub = wire(fresh=indigo_only, stale=None, compute_result=liqwid_only)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert "Indigo" in out["protocols"]


async def test_v2_only_wallet_protected_by_guard(wire):
    """F3 in action: a wallet whose only data is a Strike V2 vault used to
    count as zero protocols and went unprotected."""
    v2_only = {
        "address": ADDRESS,
        "protocols": {
            "Strike": {
                "staked": [],
                "v2_balance": 0.0,
                "v2_vault_positions": [{"vault_id": "v", "value_ada": 697.84}],
            },
        },
        "total_positions": 1,
    }
    empty = {"address": ADDRESS, "protocols": {"Strike": {"staked": []}},
             "total_positions": 0}

    stub = wire(fresh=dict(v2_only), stale=None, compute_result=empty)

    out = await get_staking_positions(ADDRESS, refresh=True, user_id=1)

    assert stub.set_calls == []
    assert _count_data_protocols(out) == 1
