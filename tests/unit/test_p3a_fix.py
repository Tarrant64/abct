"""
P3a-FIX tests.

H1 — confirmed_empty must be UNREACHABLE from truncated or schema-drifted
scans: Strike v1 needs a page terminator inside its window, Strike V2 needs
an untruncated probe list (covered in test_wallet_context), Indigo needs
shape-valid responses.
H2 — staking_portfolio_rows: the shared-valuation writer feeding
/portfolio/instant.
A1 — underwater CDPs value at NEGATIVE net equity (Director-approved: no
clamp — negative equity is real).
A3 — per-kind guard granularity: sub-source loss inside a surviving
protocol is refused.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.defi as defi_module  # noqa: E402
from services.defi import (  # noqa: E402
    DeFiService,
    iter_staking_token_values,
    staking_portfolio_rows,
)

USER_CRED = "4378058a7cccac8210e262f05c01a199aba092f30c3819ac2528fe2b"
ADDRESS = "addr1qtest"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or (str(json_data) if json_data is not None else "")

    def json(self):
        return self._json


@pytest.fixture
def service(monkeypatch):
    svc = DeFiService()
    monkeypatch.setattr(svc, "_get_payment_credential", lambda address: USER_CRED)

    async def fake_headers():
        return {}

    monkeypatch.setattr(svc, "_get_headers", fake_headers, raising=False)
    return svc


# ---------------------------------------------------------------------------
# H1(a) — Strike v1 scan needs a page terminator to confirm empty
# ---------------------------------------------------------------------------

def _wire_strike_pages(monkeypatch, pages: dict):
    """pages: page number -> list of UTxOs, or 'fail'. Missing pages 404."""

    async def fake_blockfrost_fetch(path, **kwargs):
        pg = (kwargs.get("params") or {}).get("page", 1)
        content = pages.get(pg, [])
        if content == "fail":
            return FakeResponse(status_code=500, text="boom")
        if content == []:
            return FakeResponse(status_code=404, text="no page")
        return FakeResponse(json_data=content)

    monkeypatch.setattr(defi_module, "blockfrost_fetch", fake_blockfrost_fetch)


def _full_page(n=100):
    return [{"amount": [], "tx_hash": "x", "output_index": 0}] * n


async def test_strike_v1_over_window_contract_is_indeterminate(service, monkeypatch):
    """All 15 pages full (no terminator seen): the contract may extend past
    the window — an empty match must be indeterminate, never confirmed."""
    _wire_strike_pages(monkeypatch, {pg: _full_page() for pg in range(1, 16)})

    assert await service.get_strike_staking(ADDRESS) is None


async def test_strike_v1_terminator_confirms_empty(service, monkeypatch):
    """A short page inside the window proves the scan reached the end."""
    _wire_strike_pages(monkeypatch, {1: _full_page(), 2: _full_page(30)})

    result = await service.get_strike_staking(ADDRESS)

    assert result is not None
    assert result["confirmed_empty"] is True


async def test_strike_v1_empty_contract_confirms_empty(service, monkeypatch):
    """Page 1 itself is a terminator (404 -> [])."""
    _wire_strike_pages(monkeypatch, {})

    result = await service.get_strike_staking(ADDRESS)

    assert result is not None
    assert result["confirmed_empty"] is True


async def test_strike_v1_unrecovered_page_is_indeterminate(service, monkeypatch):
    _wire_strike_pages(monkeypatch, {1: _full_page(30), 2: "fail"})

    assert await service.get_strike_staking(ADDRESS) is None


# ---------------------------------------------------------------------------
# H1(c) — Indigo schema drift is indeterminate, never confirmed
# ---------------------------------------------------------------------------

DRIFTED_STAKING = [
    # Plausible next rename: 'owner' -> 'ownerPkh'
    {"output_hash": "x", "ownerPkh": "someone", "staked_indy": 1_000_000},
    {"output_hash": "y", "ownerPkh": "other", "staked_indy": 2_000_000},
]


async def test_indigo_staking_schema_drift_is_indeterminate(service, monkeypatch, caplog):
    client_holder = {}

    class Client:
        async def get(self, url, **kwargs):
            return FakeResponse(json_data=DRIFTED_STAKING)

    monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: Client())

    with caplog.at_level("WARNING"):
        result = await service.get_indigo_staking(ADDRESS)

    assert result is None  # NOT confirmed_empty
    assert any("shape drift" in rec.message for rec in caplog.records)


async def test_indigo_cdps_schema_drift_is_indeterminate(service, monkeypatch, caplog):
    class Client:
        async def get(self, url, **kwargs):
            return FakeResponse(json_data=[
                {"output_hash": "x", "ownerPkh": "someone",
                 "collateralAmount": 1, "mintedAmount": 1},
            ])

    monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: Client())

    with caplog.at_level("WARNING"):
        result = await service.get_indigo_cdps(ADDRESS)

    assert result is None
    assert any("shape drift" in rec.message for rec in caplog.records)


async def test_indigo_empty_list_is_indeterminate(service, monkeypatch, caplog):
    """P3a-FIX2: the API demonstrably holds ~2,542 staking records — a sudden
    empty-list 200 is drift-shaped, not a universal exit. Applies to both the
    staking and CDP endpoints."""
    class Client:
        async def get(self, url, **kwargs):
            return FakeResponse(json_data=[])

    monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: Client())

    with caplog.at_level("WARNING"):
        staking = await service.get_indigo_staking(ADDRESS)
        cdps = await service.get_indigo_cdps(ADDRESS)

    assert staking is None  # NOT confirmed_empty
    assert cdps is None
    assert sum("empty list" in rec.message for rec in caplog.records) == 2


async def test_indigo_valid_shape_no_match_still_confirms(service, monkeypatch):
    class Client:
        async def get(self, url, **kwargs):
            return FakeResponse(json_data=[
                {"output_hash": "x", "owner": "someoneelse",
                 "staked_indy": 1_000_000, "snapshot_ada": 0},
            ])

    monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: Client())

    result = await service.get_indigo_staking(ADDRESS)

    assert result is not None
    assert result["confirmed_empty"] is True


# ---------------------------------------------------------------------------
# A1 — underwater CDP: NEGATIVE net equity, no clamp
# ---------------------------------------------------------------------------

PRICES = {"ADA": {"usd": 0.60}, "IUSD": {"usd": 1.0}}


def test_underwater_cdp_negative_net_equity_no_clamp():
    protocol_data = {
        "staked": [],
        "cdps": [{"asset": "iUSD", "collateral_ada": 1000.0,
                  "minted_amount": 750.0}],
    }

    entries = iter_staking_token_values(protocol_data, PRICES)

    assert len(entries) == 1
    cdp = entries[0]
    assert cdp["priced"] is True
    # 1000 * 0.60 - 750 * 1.0 = -150 — negative equity is real, not clamped
    assert cdp["usd"] == pytest.approx(-150.0)


# ---------------------------------------------------------------------------
# H2 — staking_portfolio_rows (backs /portfolio/instant)
# ---------------------------------------------------------------------------

FULL_PROTOCOLS = {
    "Indigo": {
        "staked": [{"token": "INDY", "amount": 100.0}],
        "cdps": [{"asset": "iUSD", "collateral_ada": 2500.0,
                  "minted_amount": 750.0}],
    },
    "Strike": {
        "staked": [],
        "v2_balance": 56.93,
        "v2_vault_positions": [{"vault_id": "v", "value_ada": 700.0,
                                "priced": True}],
        "reward_token": "STRIKE",
        "pending_rewards": 5.0,
    },
}

ROW_PRICES = {"ADA": {"usd": 0.60}, "INDY": {"usd": 1.10},
              "IUSD": {"usd": 1.0}, "STRIKE": {"usd": 0.02}}


def test_rows_value_equals_shared_valuation():
    rows = staking_portfolio_rows(1, FULL_PROTOCOLS, ROW_PRICES,
                                  include_rewards=True)

    rows_total = sum(r["quantity"] * r["last_price_usd"] for r in rows)
    entries_total = sum(
        e["usd"]
        for pdata in FULL_PROTOCOLS.values()
        for e in iter_staking_token_values(pdata, ROW_PRICES)
    )
    assert rows_total == pytest.approx(entries_total)

    # Kind-suffixed details keep upsert keys distinct
    details = sorted(r["source_detail"] for r in rows)
    assert details == [
        "indigo", "indigo_cdp", "strike_rewards",
        "strike_trading_balance", "strike_vault",
    ]

    # CDP row: real quantity (gross collateral), effective price = net/qty
    cdp_row = next(r for r in rows if r["source_detail"] == "indigo_cdp")
    assert cdp_row["quantity"] == pytest.approx(2500.0)
    assert cdp_row["quantity"] * cdp_row["last_price_usd"] == pytest.approx(
        2500.0 * 0.60 - 750.0
    )


def test_rows_semantics_flags():
    no_rewards = staking_portfolio_rows(1, FULL_PROTOCOLS, ROW_PRICES,
                                        include_rewards=False)
    assert all(not r["source_detail"].endswith("_rewards") for r in no_rewards)

    # D1 (P3-FIX): source_detail casing is canonical lowercase, with NO
    # override parameter — divergent casings doubled /portfolio/instant
    rows = staking_portfolio_rows(1, FULL_PROTOCOLS, ROW_PRICES)
    assert all(r["source_detail"] == r["source_detail"].lower() for r in rows)
    import inspect
    assert "detail_lower" not in inspect.signature(staking_portfolio_rows).parameters


def test_rows_unpriced_entry_prices_at_zero():
    protocols = {
        "Strike": {
            "staked": [],
            "v2_vault_positions": [{"vault_id": "v", "value_ada": 599.68,
                                    "priced": False}],
        },
    }
    rows = staking_portfolio_rows(1, protocols, ROW_PRICES)

    assert len(rows) == 1
    assert rows[0]["quantity"] == pytest.approx(599.68)  # amount visible
    assert rows[0]["last_price_usd"] == 0  # value contributes nothing


# ---------------------------------------------------------------------------
# A3 — per-kind guard granularity (sub-source loss refused)
# ---------------------------------------------------------------------------

def test_guard_pairs_catch_sub_source_loss():
    from routers.defi import _data_protocol_kinds

    baseline = {"protocols": {"Indigo": {
        "staked": [{"token": "INDY", "amount": 1.0}],
        "cdps": [{"collateral_ada": 2500.0}],
    }}}
    degraded = {"protocols": {"Indigo": {
        "staked": [{"token": "INDY", "amount": 1.0}],
        "cdps": [],  # CDP fetch failed; staking survived
    }}}

    lost = _data_protocol_kinds(baseline) - _data_protocol_kinds(degraded)
    assert lost == {("Indigo", "cdps")}
