"""
P3-FIX tests — the three live defects that rolled back the P3 deploy.

D1: ALL portfolio_positions writers against ONE real sqlite table must
produce exactly one row per position with identical (lowercase)
source_detail keys — divergent casing between writers doubled
/portfolio/instant in production.
D2: the REAL get_portfolio_totals path must include every staking kind
(Strike V2/vault) and must never serve a cached row computed by an older
valuation — the deployed summary bucket was short by exactly the Strike
portion for the totals TTL.
D3: the synchronous refresh path must stay under the latency budget with
bounded 429s — simulated 429-storm timing on a virtual clock (no
wall-clock waits).
"""

import asyncio
import heapq
import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.defi as defi_router  # noqa: E402
import routers.portfolio as portfolio_router  # noqa: E402
import services.defi as defi_module  # noqa: E402
import services.http_client as http_client  # noqa: E402
from services.defi import iter_staking_token_values, staking_portfolio_rows  # noqa: E402

ADDRESS = "addr1q9phspv20nxtestonly"
PRICES = {"ADA": {"usd": 0.60}, "INDY": {"usd": 0.10}, "IAG": {"usd": 0.02}}

# The live positions that doubled: Indigo staked, Iagon staked, Strike
# trading balance + vault (all under user 1, one wallet)
LIVE_PROTOCOLS = {
    "Indigo": {"staked": [{"token": "INDY", "amount": 8670.383309}]},
    "Iagon": {"staked": [{"token": "IAG", "amount": 3858.0}]},
    "Strike": {
        "staked": [],
        "v2_balance": 56.93,
        "v2_vault_positions": [{"vault_id": "v", "vault_name": "G",
                                "shares": 599.68, "share_price": 1.17,
                                "value_ada": 702.98, "priced": True}],
        "total_vault_ada": 702.98,
    },
}

EXPECTED_DETAILS = sorted([
    "indigo", "iagon", "strike_trading_balance", "strike_vault",
])

STAKING_PAYLOAD = {"protocols": LIVE_PROTOCOLS, "address": ADDRESS}


def _create_positions_table(db_path):
    db = sqlite3.connect(db_path)
    db.execute("""
        CREATE TABLE portfolio_positions (
            user_id INTEGER, symbol TEXT, quantity REAL,
            source_type TEXT, source_detail TEXT, chain TEXT,
            last_price_usd REAL, last_value_usd REAL, updated_at TEXT,
            UNIQUE(user_id, symbol, source_type, source_detail)
        )
    """)
    db.commit()
    db.close()


def _staking_rows(db_path):
    db = sqlite3.connect(db_path)
    rows = db.execute(
        "SELECT symbol, source_detail, quantity, last_value_usd "
        "FROM portfolio_positions WHERE source_type='staking' "
        "ORDER BY source_detail"
    ).fetchall()
    db.close()
    return rows


# ---------------------------------------------------------------------------
# D1 — all writers, one table, one canonical key set
# ---------------------------------------------------------------------------

@pytest.fixture
def positions_db(monkeypatch, tmp_path):
    db_path = tmp_path / "portfolio.db"
    _create_positions_table(db_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    return db_path


@pytest.fixture
def d1_env(monkeypatch, positions_db):
    """Stub every data source so each REAL writer sees the same wallet."""

    async def fake_get_cache(key, user_id=None):
        if key.startswith("staking_positions_"):
            return dict(STAKING_PAYLOAD)
        return None

    async def fake_get_stale_cache(key, user_id=None):
        return None, None

    async def fake_set_cache(key, value, ttl, user_id=None):
        pass

    async def fake_wallets(user_id=None):
        return [{"address": ADDRESS, "blockchain": "cardano", "id": 1}]

    async def fake_sources(user_id, source_type=None):
        return []

    async def fake_none_list(*a, **k):
        return []

    monkeypatch.setattr(database, "get_cache", fake_get_cache)
    monkeypatch.setattr(database, "get_stale_cache", fake_get_stale_cache)
    monkeypatch.setattr(database, "set_cache", fake_set_cache)
    monkeypatch.setattr(database, "get_all_wallets", fake_wallets)
    monkeypatch.setattr(database, "get_wallet_sources", fake_sources,
                        raising=False)
    monkeypatch.setattr(database, "get_tracked_tokens", fake_none_list,
                        raising=False)
    monkeypatch.setattr(database, "get_all_custom_tokens", fake_none_list,
                        raising=False)

    from services.pricing import pricing_service

    async def fake_prices():
        return PRICES

    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)
    return positions_db


async def _run_route_writer(monkeypatch):
    """The staking route's fire-and-forget writer, through the REAL route."""
    stub_cache_calls = {}

    async def fake_get_cache(key, user_id=None):
        return None

    async def fake_get_stale_cache(key, user_id=None):
        return None, None

    async def fake_set_cache(key, value, ttl, user_id=None):
        stub_cache_calls[key] = value

    monkeypatch.setattr(defi_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(defi_router, "get_stale_cache", fake_get_stale_cache)
    monkeypatch.setattr(defi_router, "set_cache", fake_set_cache)

    async def fake_username(user_id):
        return "admin"

    async def fake_is_demo(username):
        return False

    monkeypatch.setattr(defi_router, "get_username_by_user_id", fake_username)
    monkeypatch.setattr(defi_router, "is_demo_user", fake_is_demo)

    async def fake_compute(address, previous_result=None,
                           payment_creds=None, account_addresses=None):
        return {"address": address, "protocols": dict(LIVE_PROTOCOLS),
                "confirmed_empty": [], "total_positions": 4}

    monkeypatch.setattr(
        defi_router.defi_service, "get_all_staking_positions", fake_compute
    )

    async def fake_context(address):
        return {"address": address, "stake_address": None,
                "addresses": [address], "payment_creds": ["c"],
                "resolved": False}

    monkeypatch.setattr(
        defi_router.defi_service, "resolve_wallet_context", fake_context
    )

    # The route now answers refresh promptly and runs the compute (and
    # its fire-and-forget writer) in the background job — drive the
    # compute path directly, which IS the production write path
    await defi_router._compute_staking_positions(ADDRESS, 1)


async def _run_offchain_collector():
    """The REAL offchain collector writer (the path that emitted 'Indigo' /
    'Strike_vault' mixed-case rows in production)."""
    from services.offchain_collector import OffchainCollector

    collector = OffchainCollector()

    class FakePricing:
        async def get_all_tracked_prices(self):
            return PRICES

    async def fake_pricing_service(self=None):
        return FakePricing()

    collector._get_pricing_service = fake_pricing_service
    await collector.collect_for_user(1)


def _writer_call_shapes():
    """The exact staking_portfolio_rows call shapes of the two writers that
    live inside mega-functions (main.py seeder: include_rewards=False;
    portfolio summary writer: include_rewards=True)."""
    return [
        staking_portfolio_rows(1, LIVE_PROTOCOLS, PRICES, include_rewards=False),
        staking_portfolio_rows(1, LIVE_PROTOCOLS, PRICES, include_rewards=True),
    ]


async def test_all_writers_one_table_no_duplicates(monkeypatch, d1_env):
    """THE D1 test: every writer against one real table, exactly one row
    per position, all source_detail keys identical (canonical lowercase).
    Against the rolled-back build this produces case-variant duplicates
    ('Indigo' + 'indigo') and fails."""
    # Legacy mixed-case rows from the incident, pre-seeded
    db = sqlite3.connect(d1_env)
    db.executemany(
        "INSERT INTO portfolio_positions VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
        [
            (1, "INDY", 8670.383309, "staking", "Indigo", "cardano", 0.10, 867.04),
            (1, "ADA", 702.98, "staking", "Strike_vault", "cardano", 0.60, 421.79),
            (1, "IAG", 3858.0, "staking", "Iagon", "cardano", 0.02, 77.16),
        ],
    )
    db.commit()
    db.close()

    # Run every writer path into the same table
    await _run_route_writer(monkeypatch)
    await _run_offchain_collector()
    from database import upsert_portfolio_positions_batch
    for rows in _writer_call_shapes():
        await upsert_portfolio_positions_batch(rows)

    rows = _staking_rows(d1_env)
    details = [r[1] for r in rows]

    # Exactly one row per position — no case-variant duplicates survive
    assert details == EXPECTED_DETAILS
    assert all(d == d.lower() for d in details)

    # And the money is counted ONCE: table total equals the shared valuation
    table_total = sum(r[3] for r in rows)
    expected = sum(
        e["usd"] for pdata in LIVE_PROTOCOLS.values()
        for e in iter_staking_token_values(pdata, PRICES)
        if e["kind"] != "reward"
    )
    assert table_total == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# D2 — the REAL summary-bucket path includes Strike and never serves
#      an older valuation's cached row
# ---------------------------------------------------------------------------

@pytest.fixture
def d2_env(monkeypatch):
    cache_store = {}

    async def fake_get_cache(key, user_id=None):
        return cache_store.get(key)

    async def fake_set_cache(key, value, ttl_seconds=None, user_id=None, **kw):
        cache_store[key] = value

    # portfolio.py resolves get_cache/set_cache from its module namespace
    monkeypatch.setattr(portfolio_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(portfolio_router, "set_cache", fake_set_cache)

    async def fake_tracked():
        return []

    monkeypatch.setattr(portfolio_router, "get_tracked_tokens", fake_tracked)

    # offchain_helpers / call-time database imports
    async def db_get_cache(key, user_id=None):
        if key.startswith("staking_positions_"):
            return dict(STAKING_PAYLOAD)
        return None

    async def db_stale(key, user_id=None):
        return None, None

    async def db_wallets(user_id=None):
        return [{"address": ADDRESS, "blockchain": "cardano"}]

    async def db_daily(user_id):
        return []

    async def db_custom(user_id=None):
        return []

    monkeypatch.setattr(database, "get_cache", db_get_cache)
    monkeypatch.setattr(database, "get_stale_cache", db_stale)
    monkeypatch.setattr(database, "get_all_wallets", db_wallets)
    monkeypatch.setattr(database, "get_unified_daily_totals", db_daily,
                        raising=False)
    monkeypatch.setattr(database, "get_all_custom_tokens", db_custom,
                        raising=False)

    from services.pricing import pricing_service

    async def fake_prices():
        return PRICES

    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)
    return cache_store


def _expected_staking_bucket():
    """What the Staking tab shows for the same fixture (incl. rewards, which
    offchain-based buckets include)."""
    return sum(
        e["usd"] for pdata in LIVE_PROTOCOLS.values()
        for e in iter_staking_token_values(pdata, PRICES)
    )


async def test_summary_bucket_includes_strike_kinds(d2_env):
    """THE D2 test: through the REAL get_portfolio_totals compute path, the
    staking bucket must include Strike V2/vault kinds (mobile-portion ==
    summary-bucket)."""
    totals = await portfolio_router.get_portfolio_totals(user_id=1)

    assert totals["staking_usd"] == pytest.approx(_expected_staking_bucket())
    # Strike specifically present (the live deficit was exactly this)
    strike_only = sum(
        e["usd"] for e in iter_staking_token_values(LIVE_PROTOCOLS["Strike"], PRICES)
    )
    assert strike_only > 0
    assert totals["staking_usd"] >= strike_only


async def test_stale_valuation_cache_row_is_recomputed(d2_env):
    """A cached totals row computed by an OLDER valuation (no
    valuation_version — exactly what the pre-deploy row looked like) must be
    ignored, not served. Fails against the rolled-back build."""
    d2_env["portfolio_totals_1"] = {
        "staking_usd": 941.89,  # staked-only: short by the Strike portion
        "defi_usd": 0, "exchange_usd": 0, "nft_usd": 0,
        "tracked_tokens_usd": 0, "custom_tokens_usd": 0,
        "snapshot_time": None,
    }

    totals = await portfolio_router.get_portfolio_totals(user_id=1)

    assert totals["staking_usd"] == pytest.approx(_expected_staking_bucket())
    assert totals["valuation_version"] == portfolio_router.TOTALS_VALUATION_VERSION


async def test_current_version_cache_row_is_served(d2_env):
    versioned = {
        "staking_usd": 123.0,
        "valuation_version": portfolio_router.TOTALS_VALUATION_VERSION,
    }
    d2_env["portfolio_totals_1"] = versioned

    totals = await portfolio_router.get_portfolio_totals(user_id=1)
    assert totals is versioned  # cache still works for current-version rows


async def test_refresh_bypasses_totals_cache(d2_env):
    """The phone's hard pull propagates refresh here — it must recompute."""
    d2_env["portfolio_totals_1"] = {
        "staking_usd": 123.0,
        "valuation_version": portfolio_router.TOTALS_VALUATION_VERSION,
    }

    totals = await portfolio_router.get_portfolio_totals(user_id=1, refresh=True)
    assert totals["staking_usd"] == pytest.approx(_expected_staking_bucket())


# ---------------------------------------------------------------------------
# D3 — latency budget under simulated 429 storms (virtual clock)
# ---------------------------------------------------------------------------

class VirtualClock:
    """Deterministic virtual time: all waiting in the paced path goes
    through _bf_sleep/_bf_monotonic, so tests advance time explicitly with
    zero wall-clock delay."""

    def __init__(self):
        self.now = 0.0
        self._waiters = []
        self._seq = 0

    def monotonic(self):
        return self.now

    async def sleep(self, d):
        if d <= 0:
            await asyncio.sleep(0)
            return
        ev = asyncio.Event()
        heapq.heappush(self._waiters, (self.now + d, self._seq, ev))
        self._seq += 1
        await ev.wait()

    async def run(self, coro):
        task = asyncio.ensure_future(coro)
        while not task.done():
            # Let runnable tasks make progress
            for _ in range(10):
                if task.done():
                    break
                await asyncio.sleep(0)
            if task.done():
                break
            if not self._waiters:
                await asyncio.sleep(0)
                continue
            # Advance to the earliest wake time and release EVERY waiter due
            # by then in one batch (waiters scheduled within the same paced
            # window share wake times — popping one at a time is O(n^2))
            wake, _, ev = heapq.heappop(self._waiters)
            self.now = max(self.now, wake)
            ev.set()
            while self._waiters and self._waiters[0][0] <= self.now + 1e-9:
                heapq.heappop(self._waiters)[2].set()
        return task.result()


class FakeBlockfrostServer:
    """Server-side rate model: token bucket like Blockfrost's advertised
    limits (burst capacity, fixed refill)."""

    def __init__(self, clock, capacity, refill_per_s):
        self.clock = clock
        self.capacity = capacity
        self.refill = refill_per_s
        self.tokens = float(capacity)
        self.ts = 0.0
        self.served = 0
        self.throttled = 0

    def handle(self):
        now = self.clock.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.refill)
        self.ts = now
        if self.tokens >= 1:
            self.tokens -= 1
            self.served += 1
            return 200
        self.throttled += 1
        return 429


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture
def d3_env(monkeypatch):
    clock = VirtualClock()
    monkeypatch.setattr(http_client, "_bf_monotonic", clock.monotonic)
    monkeypatch.setattr(http_client, "_bf_sleep", clock.sleep)
    monkeypatch.setattr(http_client, "_blockfrost_bucket", http_client._TokenBucket(
        http_client._BLOCKFROST_BUCKET_CAPACITY,
        http_client._BLOCKFROST_BUCKET_REFILL,
    ))

    def wire_server(server):
        async def fake_once(path, **kwargs):
            return _Resp(server.handle())

        monkeypatch.setattr(http_client, "_blockfrost_fetch_once", fake_once)

    return clock, wire_server


async def _full_rescan(wallets=26, requests_per_wallet=20):
    """Shape of a full refresh: N wallet scans in parallel, each firing its
    page fetches concurrently (like the Strike/Iagon scans do)."""

    async def scan_wallet(w):
        await asyncio.gather(*[
            http_client.blockfrost_fetch(f"/w{w}/p{i}")
            for i in range(requests_per_wallet)
        ])

    await asyncio.gather(*[scan_wallet(w) for w in range(wallets)])


async def test_full_rescan_latency_budget_normal_limits(d3_env):
    """520-request full rescan against Blockfrost's advertised limits
    (burst 500, 10 req/s): must finish under the 45 s refresh budget with
    real 429s under 100."""
    clock, wire_server = d3_env
    server = FakeBlockfrostServer(clock, capacity=500, refill_per_s=10.0)
    wire_server(server)

    await clock.run(_full_rescan())

    assert clock.now < 45.0, f"full rescan took {clock.now:.1f}s virtual"
    assert server.throttled < 100, f"{server.throttled} real 429s"


async def test_rescan_under_degraded_server_still_bounded(d3_env):
    """429 storm: a degraded server (burst only 100) throttles hard — the
    penalty must pull the client to refill pace, keeping total 429s bounded
    and latency finite (worse than the normal budget, but no runaway)."""
    clock, wire_server = d3_env
    server = FakeBlockfrostServer(clock, capacity=100, refill_per_s=10.0)
    wire_server(server)

    await clock.run(_full_rescan())

    assert clock.now < 90.0, f"degraded rescan took {clock.now:.1f}s virtual"
    assert server.throttled < 150, f"{server.throttled} real 429s"


async def test_single_heavy_wallet_refresh_is_fast(d3_env):
    """The phone's hard-pull contract: one heavy wallet (~30 requests) must
    complete in seconds."""
    clock, wire_server = d3_env
    server = FakeBlockfrostServer(clock, capacity=500, refill_per_s=10.0)
    wire_server(server)

    await clock.run(_full_rescan(wallets=1, requests_per_wallet=30))

    assert clock.now < 5.0
    assert server.throttled == 0


# ---------------------------------------------------------------------------
# Reviewer finding: the dead-path grep test must grep the ACTUAL literals
# ---------------------------------------------------------------------------

DEAD_INDIGO_PATHS = [
    "/api/v1/staking/positions",
    "/api/v1/loans",
    "/api/v1/stability-pools",
    "/api/v1/protocol/stats",
]


def test_no_dead_indigo_path_literals_in_runtime_code():
    """Greps the exact dead-path literals across backend/ — the previous
    test grepped a base-URL concatenation that could never match, making it
    vacuous. Sole documented exception: the disabled legacy stability-pool
    parser in services/defi.py."""
    import subprocess
    for dead in DEAD_INDIGO_PATHS:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", "-F", dead,
             os.path.join(BACKEND_DIR)],
            capture_output=True, text=True,
        ).stdout
        offenders = [
            line for line in out.splitlines()
            if "services/defi.py" not in line  # disabled parser, documented
        ]
        assert offenders == [], f"dead Indigo path {dead} referenced: {offenders}"
