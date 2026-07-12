"""
Unit tests for DeFi staking-position fetchers (services/defi.py).

Fixtures mirror the live response shapes verified 2026-07-12:
- Indigo analytics moved to un-versioned paths (/api/staking-positions,
  /api/cdps) with renamed fields (staked_indy, snapshot_ada,
  collateralAmount, mintedAmount).
- Liqwid Agora stakes come from the official GraphQL API keyed by
  payment credentials.

No network access — the shared HTTP client is replaced with a fake.
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
from services.defi import DeFiService  # noqa: E402

USER_CRED = "4378058a7cccac8210e262f05c01a199aba092f30c3819ac2528fe2b"
OTHER_CRED = "caa1842a84f9d69cd0814d16c072e4f4aaa045f8d85c20587ed3c045"
ADDRESS = "addr1qtest"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or (str(json_data) if json_data is not None else "")

    def json(self):
        return self._json


class FakeClient:
    """Records requests and serves canned responses keyed by URL substring."""

    def __init__(self, routes):
        self.routes = routes  # list of (substring, FakeResponse)
        self.requests = []  # (method, url, kwargs)

    def _match(self, url):
        for substring, response in self.routes:
            if substring in url:
                return response
        return FakeResponse(status_code=404, text="no fake route")

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self._match(url)

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self._match(url)


@pytest.fixture
def service(monkeypatch):
    svc = DeFiService()
    monkeypatch.setattr(
        svc, "_get_payment_credential", lambda address: USER_CRED
    )
    return svc


def use_client(monkeypatch, client):
    monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: client)


# ---------------------------------------------------------------------------
# Indigo staking — /api/staking-positions (P0a)
# ---------------------------------------------------------------------------

# Real shape from analytics.indigoprotocol.io/api/staking-positions
INDIGO_STAKING_FIXTURE = [
    {
        "output_hash": "422a075219cdef8d071db3bcb1e89305d752952be69e772279770b46f96db0e4",
        "output_index": 0,
        "owner": OTHER_CRED,
        "staked_indy": 746502844,
        "locked_amount": "{}",
        "snapshot_ada": 1423157470784,
    },
    {
        "output_hash": "9eda84db921f299e5b71cb2fe37cccb1fac31e6cb68d1bfd04ff10637fd0f7db",
        "output_index": 0,
        "owner": USER_CRED,
        "staked_indy": 8670383309,
        "locked_amount": "{}",
        "snapshot_ada": 1422545368364,
    },
]


async def test_indigo_staking_parses_current_api_shape(service, monkeypatch):
    client = FakeClient([
        ("/api/staking-positions", FakeResponse(json_data=INDIGO_STAKING_FIXTURE)),
    ])
    use_client(monkeypatch, client)

    result = await service.get_indigo_staking(ADDRESS)

    assert result is not None
    assert result["protocol"] == "Indigo"
    assert result["position_count"] == 1
    assert result["total_staked_indy"] == pytest.approx(8670.383309)
    pos = result["positions"][0]
    assert pos["staked_indy_raw"] == 8670383309
    assert pos["staked_indy"] == pytest.approx(8670.383309)
    assert pos["output_hash"] == INDIGO_STAKING_FIXTURE[1]["output_hash"]

    # Must call the un-versioned endpoint, not the dead /api/v1 path
    assert client.requests[0][1].endswith("/api/staking-positions")


async def test_indigo_staking_non_200_logs_warning_and_returns_none(
    service, monkeypatch, caplog
):
    client = FakeClient([
        ("/api/staking-positions", FakeResponse(status_code=503, text="down")),
    ])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_indigo_staking(ADDRESS)

    assert result is None
    assert any(
        "503" in rec.message and "staking-positions" in rec.message
        for rec in caplog.records
    )


async def test_indigo_staking_no_match_returns_none(service, monkeypatch):
    client = FakeClient([
        ("/api/staking-positions", FakeResponse(json_data=[INDIGO_STAKING_FIXTURE[0]])),
    ])
    use_client(monkeypatch, client)

    assert await service.get_indigo_staking(ADDRESS) is None


# ---------------------------------------------------------------------------
# Indigo CDPs — /api/cdps (P0a)
# ---------------------------------------------------------------------------

# Real shape from analytics.indigoprotocol.io/api/cdps (mixed-case fields)
INDIGO_CDPS_FIXTURE = [
    {
        "output_hash": "868af8eb2e60b4e07cdcf01e4b7646b0f364f4d1fd88e82a428687896ca22795",
        "output_index": 0,
        "owner": OTHER_CRED,
        "asset": "iBTC",
        "collateral_asset": "",
        "collateralAmount": 5576215171,
        "mintedAmount": 11719,
    },
    {
        "output_hash": "aaa0f8eb2e60b4e07cdcf01e4b7646b0f364f4d1fd88e82a42868789deadbeef",
        "output_index": 0,
        "owner": USER_CRED,
        "asset": "iUSD",
        "collateral_asset": "",
        "collateralAmount": 2_500_000_000,
        "mintedAmount": 750_000_000,
    },
]


async def test_indigo_cdps_parses_current_api_shape(service, monkeypatch):
    client = FakeClient([
        ("/api/cdps", FakeResponse(json_data=INDIGO_CDPS_FIXTURE)),
    ])
    use_client(monkeypatch, client)

    result = await service.get_indigo_cdps(ADDRESS)

    assert result is not None
    assert result["cdp_count"] == 1
    assert result["total_collateral_ada"] == pytest.approx(2500.0)
    cdp = result["cdps"][0]
    assert cdp["asset"] == "iUSD"
    assert cdp["collateral_ada"] == pytest.approx(2500.0)
    assert cdp["minted_amount"] == pytest.approx(750.0)

    assert client.requests[0][1].endswith("/api/cdps")


async def test_indigo_cdps_non_200_logs_warning_and_returns_none(
    service, monkeypatch, caplog
):
    client = FakeClient([
        ("/api/cdps", FakeResponse(status_code=404, text="<html>404</html>")),
    ])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_indigo_cdps(ADDRESS)

    assert result is None
    assert any("404" in rec.message and "cdps" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Strike V2 — vaults must be fetched even with an empty trading account (P0c)
# ---------------------------------------------------------------------------

STRIKE_ACCOUNT_ID = "019d0ddc-8cd5-7dc9-9308-9da520c4d339"
STRIKE_VAULT_ID = "0197e1a2-test-vault"


def strike_routes(wallet_balance, vault_positions):
    return [
        ("/v2/account", FakeResponse(json_data={
            "account_id": STRIKE_ACCOUNT_ID,
            "wallet_balance": wallet_balance,
        })),
        ("/v2/vault/positions", FakeResponse(json_data={
            "positions": vault_positions,
        })),
        ("/v2/vaults", FakeResponse(json_data={
            "vaults": [{
                "vault_id": STRIKE_VAULT_ID,
                "name": "Glacier Arc Digital",
                "share_price": 1.172265,
            }],
        })),
    ]


async def test_strike_v2_vaults_found_with_zero_trading_balance(service, monkeypatch):
    client = FakeClient(strike_routes(
        wallet_balance=0,
        vault_positions=[{"vault_id": STRIKE_VAULT_ID, "shares": 599.68}],
    ))
    use_client(monkeypatch, client)

    result = await service.get_strike_v2_positions(ADDRESS)

    assert result is not None
    assert result["v2_balance"] == 0
    assert len(result["vault_positions"]) == 1
    vault = result["vault_positions"][0]
    assert vault["vault_name"] == "Glacier Arc Digital"
    assert vault["value_ada"] == pytest.approx(599.68 * 1.172265)
    assert vault["priced"] is True
    assert vault["share_price_source"] == "vaults_api"
    assert result["total_vault_ada"] == pytest.approx(599.68 * 1.172265)


async def test_strike_v2_no_balance_no_vaults_returns_none(service, monkeypatch):
    client = FakeClient(strike_routes(wallet_balance=0, vault_positions=[]))
    use_client(monkeypatch, client)

    assert await service.get_strike_v2_positions(ADDRESS) is None


async def test_strike_v2_balance_and_vaults_both_reported(service, monkeypatch):
    client = FakeClient(strike_routes(
        wallet_balance=56.93,
        vault_positions=[{"vault_id": STRIKE_VAULT_ID, "shares": 599.68}],
    ))
    use_client(monkeypatch, client)

    result = await service.get_strike_v2_positions(ADDRESS)

    assert result is not None
    assert result["v2_balance"] == pytest.approx(56.93)
    assert len(result["vault_positions"]) == 1


async def test_strike_v2_missing_vault_price_flagged_not_silent(
    service, monkeypatch, caplog
):
    """Vault absent from the active list: fallback share_price=1 must be
    flagged priced=false with a warning — never a silent ~15%-low value."""
    client = FakeClient([
        ("/v2/account", FakeResponse(json_data={
            "account_id": STRIKE_ACCOUNT_ID, "wallet_balance": 0,
        })),
        ("/v2/vault/positions", FakeResponse(json_data={
            "positions": [{"vault_id": "closed-vault-id", "shares": "599.68",
                           "name": "Retired Vault"}],
        })),
        ("/v2/vaults", FakeResponse(json_data={"vaults": []})),
    ])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_strike_v2_positions(ADDRESS)

    assert result is not None
    assert len(result["vault_positions"]) == 1
    vault = result["vault_positions"][0]
    assert vault["priced"] is False
    assert vault["share_price_source"] == "fallback"
    assert vault["share_price"] == 1.0
    assert vault["value_ada"] == pytest.approx(599.68)
    assert vault["vault_name"] == "Retired Vault"  # position never vanishes
    assert any(
        "share price" in rec.message and "closed-v" in rec.message
        for rec in caplog.records
    )


async def test_strike_v2_vaults_lookup_failure_flags_unpriced(
    service, monkeypatch, caplog
):
    client = FakeClient([
        ("/v2/account", FakeResponse(json_data={
            "account_id": STRIKE_ACCOUNT_ID, "wallet_balance": 0,
        })),
        ("/v2/vault/positions", FakeResponse(json_data={
            "positions": [{"vault_id": STRIKE_VAULT_ID, "shares": 100}],
        })),
        ("/v2/vaults", FakeResponse(status_code=502, text="bad gateway")),
    ])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_strike_v2_positions(ADDRESS)

    assert result is not None
    vault = result["vault_positions"][0]
    assert vault["priced"] is False
    assert vault["share_price_source"] == "fallback"
    assert any("502" in rec.message for rec in caplog.records)


async def test_strike_v2_malformed_vault_skipped_others_survive(
    service, monkeypatch, caplog
):
    client = FakeClient(strike_routes(
        wallet_balance=0,
        vault_positions=[
            {"vault_id": STRIKE_VAULT_ID, "shares": "not-a-number"},
            {"vault_id": STRIKE_VAULT_ID, "shares": 599.68},
        ],
    ))
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_strike_v2_positions(ADDRESS)

    assert result is not None
    assert len(result["vault_positions"]) == 1
    assert result["vault_positions"][0]["value_ada"] == pytest.approx(599.68 * 1.172265)
    assert any("malformed vault" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Indigo pending rewards — current endpoint, pending heuristic retired (P0-FIX)
# ---------------------------------------------------------------------------

async def test_indigo_pending_rewards_uses_current_endpoint(service, monkeypatch):
    client = FakeClient([
        ("/api/staking-positions", FakeResponse(json_data=INDIGO_STAKING_FIXTURE)),
    ])
    use_client(monkeypatch, client)

    result = await service.get_indigo_pending_rewards(ADDRESS)

    assert result is not None
    assert result["total_staked"] == pytest.approx(8670.383309)
    assert result["ada_backing"] == pytest.approx(1422545.368364)
    # Per-epoch locked_amount semantics don't support the old pending
    # heuristic — pending must be 0, never an over-counted guess
    assert result["pending_indy"] == 0
    assert result["pending_ada"] == 0

    assert client.requests[0][1].endswith("/api/staking-positions")


async def test_indigo_apy_disabled_no_network(service, monkeypatch):
    client = FakeClient([])
    use_client(monkeypatch, client)

    assert await service._get_indigo_apy(client) is None
    assert client.requests == []


# ---------------------------------------------------------------------------
# Liqwid — Agora stakes via official GraphQL (P1)
# ---------------------------------------------------------------------------

def liqwid_graphql_response(results, page=0, per_page=100, pages_count=1, total=None):
    return FakeResponse(json_data={
        "data": {"agora": {"data": {"stakes": {
            "page": page,
            "perPage": per_page,
            "pagesCount": pages_count,
            "totalCount": total if total is not None else len(results),
            "results": results,
        }}}},
    })


# Real shape from v2.api.liqwid.finance/graphql agora.data.stakes
LIQWID_STAKES_FIXTURE = [
    {"txId": "c9f8cad7d0811a845c8b8da939f41bb731dfb1a7a02b792f0a1e8934e57a1375-2",
     "owner": USER_CRED, "stakedAmount": 200.454545, "delegatedTo": None},
    {"txId": "c9f8cad7d0811a845c8b8da939f41bb731dfb1a7a02b792f0a1e8934e57a1375-1",
     "owner": USER_CRED, "stakedAmount": 260.383619, "delegatedTo": None},
    {"txId": "ad7d5f6c7b884186bf2def919fb0f6d833b8f164fa9ab792452cf2269fa15598-2",
     "owner": USER_CRED, "stakedAmount": 297.631134, "delegatedTo": None},
    {"txId": "4e897e2ac992cf4254efd3c0bb391271fba109cffe9344cb48c8422ea25959a8-1",
     "owner": USER_CRED, "stakedAmount": 316.166374, "delegatedTo": None},
    {"txId": "4e897e2ac992cf4254efd3c0bb391271fba109cffe9344cb48c8422ea25959a8-0",
     "owner": USER_CRED, "stakedAmount": 1014.53368, "delegatedTo": None},
]


async def test_liqwid_graphql_parses_agora_stakes(service, monkeypatch):
    client = FakeClient([
        ("/graphql", liqwid_graphql_response(LIQWID_STAKES_FIXTURE)),
    ])
    use_client(monkeypatch, client)

    result = await service.get_liqwid_staking(ADDRESS)

    assert result is not None
    assert result["protocol"] == "Liqwid"
    assert result["position_count"] == 5
    assert result["total_staked_lq"] == pytest.approx(2089.169352)

    pos = result["positions"][0]
    assert pos["staked_lq"] == pytest.approx(200.454545)
    assert pos["staked_lq_raw"] == 200454545
    assert pos["tx_hash"] == (
        "c9f8cad7d0811a845c8b8da939f41bb731dfb1a7a02b792f0a1e8934e57a1375"
    )
    assert pos["output_index"] == 2

    # The query must go to the GraphQL API keyed by payment credential
    method, url, kwargs = client.requests[0]
    assert method == "POST"
    assert url.endswith("/graphql")
    assert kwargs["json"]["variables"]["input"]["paymentKeys"] == [USER_CRED]


async def test_liqwid_graphql_paginates(service, monkeypatch):
    pages = [
        liqwid_graphql_response(LIQWID_STAKES_FIXTURE[:3], page=0, pages_count=2, total=5),
        liqwid_graphql_response(LIQWID_STAKES_FIXTURE[3:], page=1, pages_count=2, total=5),
    ]

    class PagingClient(FakeClient):
        async def post(self, url, **kwargs):
            self.requests.append(("POST", url, kwargs))
            return pages[kwargs["json"]["variables"]["input"]["page"]]

    client = PagingClient([])
    use_client(monkeypatch, client)

    result = await service.get_liqwid_staking(ADDRESS)

    assert result is not None
    assert result["position_count"] == 5
    assert result["total_staked_lq"] == pytest.approx(2089.169352)
    assert len(client.requests) == 2


async def test_liqwid_graphql_page_cap(service, monkeypatch, caplog):
    """pagesCount is untrusted input — the loop must stop at 50 pages."""
    class RunawayClient(FakeClient):
        async def post(self, url, **kwargs):
            self.requests.append(("POST", url, kwargs))
            return liqwid_graphql_response(
                [LIQWID_STAKES_FIXTURE[0]], pages_count=999, total=999
            )

    client = RunawayClient([])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_liqwid_staking(ADDRESS)

    assert len(client.requests) == 50
    assert result is not None
    assert result["position_count"] == 50
    assert any("capped at 50 pages" in rec.message for rec in caplog.records)


async def test_liqwid_graphql_no_stakes_returns_none(service, monkeypatch):
    client = FakeClient([("/graphql", liqwid_graphql_response([]))])
    use_client(monkeypatch, client)

    assert await service.get_liqwid_staking(ADDRESS) is None


async def test_liqwid_graphql_errors_logged_and_none(service, monkeypatch, caplog):
    error_resp = FakeResponse(json_data={
        "errors": [{"message": "Unknown argument"}],
    })
    client = FakeClient([("/graphql", error_resp)])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_liqwid_staking(ADDRESS)

    assert result is None
    assert any("GraphQL errors" in rec.message for rec in caplog.records)


async def test_liqwid_graphql_http_error_logged_and_none(service, monkeypatch, caplog):
    client = FakeClient([("/graphql", FakeResponse(status_code=502, text="bad gateway"))])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        result = await service.get_liqwid_staking(ADDRESS)

    assert result is None
    assert any("502" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Indigo stability pool — disabled until a per-account endpoint exists (P0a)
# ---------------------------------------------------------------------------

async def test_indigo_stability_pool_disabled_returns_none(service, monkeypatch):
    client = FakeClient([])
    use_client(monkeypatch, client)

    assert await service.get_indigo_stability_pool(ADDRESS) is None
    # Disabled path must not hit the network at all
    assert client.requests == []
