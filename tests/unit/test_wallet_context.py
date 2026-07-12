"""
Tests for stake-account-wide owner matching (P2: WalletContext).

A stake account commonly has many HD payment addresses (the user's main
wallet has six payment credentials); positions opened from sibling addresses
were invisible to single-credential matching. resolve_wallet_context resolves
the full address/credential set via Koios (cached), and the route partitions
credentials across stored sibling rows so nothing is ever double-reported.
"""

import os
import sys

import bech32 as b32
import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.defi as defi_router  # noqa: E402
import services.defi as defi_module  # noqa: E402
from routers.defi import _resolve_scan_identity  # noqa: E402
from services.defi import DeFiService  # noqa: E402


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
        self.routes = routes
        self.requests = []

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


def use_client(monkeypatch, client):
    monkeypatch.setattr(defi_module, "get_client", lambda *a, **k: client)


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


def make_addr(payment_byte: int, stake_byte: int = 9) -> str:
    """Valid mainnet base address with synthetic payment/stake credentials."""
    data = bytes([0x01]) + bytes([payment_byte]) * 28 + bytes([stake_byte]) * 28
    return b32.bech32_encode("addr", b32.convertbits(list(data), 8, 5))


def cred_of(payment_byte: int) -> str:
    return (bytes([payment_byte]) * 28).hex()


# Six sibling addresses of one stake account (stake byte 9)
ADDRS = [make_addr(i) for i in range(1, 7)]
CREDS = [cred_of(i) for i in range(1, 7)]
STAKE_ADDRESS = "stake1uyysjzgfpyysjzgfpyysjzgfpyysjzgfpyysjzgfpyysjzg7nyvst"


@pytest.fixture
def service():
    return DeFiService()


class MemoryCache:
    def __init__(self):
        self.store = {}

    async def get_cache(self, key, user_id=None):
        return self.store.get((user_id, key))

    async def set_cache(self, key, value, ttl, user_id=None):
        self.store[(user_id, key)] = value


@pytest.fixture
def mem_cache(monkeypatch):
    cache = MemoryCache()
    monkeypatch.setattr(database, "get_cache", cache.get_cache)
    monkeypatch.setattr(database, "set_cache", cache.set_cache)
    return cache


def koios_client(addresses):
    return FakeClient([
        ("/account_addresses", FakeResponse(json_data=[
            {"stake_address": STAKE_ADDRESS, "addresses": addresses},
        ])),
    ])


# ---------------------------------------------------------------------------
# resolve_wallet_context
# ---------------------------------------------------------------------------

async def test_context_resolves_all_creds(service, monkeypatch, mem_cache):
    client = koios_client(ADDRS)
    use_client(monkeypatch, client)

    ctx = await service.resolve_wallet_context(ADDRS[0])

    assert ctx["resolved"] is True
    assert ctx["stake_address"] == STAKE_ADDRESS
    assert ctx["addresses"] == ADDRS
    assert ctx["payment_creds"] == CREDS  # all six, derived locally
    assert client.requests[0][0] == "POST"
    assert client.requests[0][1].endswith("/account_addresses")


async def test_context_is_cached_one_koios_call(service, monkeypatch, mem_cache):
    client = koios_client(ADDRS)
    use_client(monkeypatch, client)

    await service.resolve_wallet_context(ADDRS[0])
    ctx2 = await service.resolve_wallet_context(ADDRS[1])  # sibling, same account

    assert len(client.requests) == 1  # second resolution served from cache
    assert ctx2["payment_creds"] == CREDS


async def test_context_koios_failure_falls_back_single(service, monkeypatch, mem_cache, caplog):
    client = FakeClient([
        ("/account_addresses", FakeResponse(status_code=503, text="down")),
    ])
    use_client(monkeypatch, client)

    with caplog.at_level("WARNING"):
        ctx = await service.resolve_wallet_context(ADDRS[0])

    assert ctx["resolved"] is False
    assert ctx["addresses"] == [ADDRS[0]]
    assert ctx["payment_creds"] == [CREDS[0]]
    assert any("503" in rec.message for rec in caplog.records)


async def test_context_non_base_address_falls_back(service, monkeypatch, mem_cache):
    client = koios_client(ADDRS)
    use_client(monkeypatch, client)

    ctx = await service.resolve_wallet_context("stake1uyysjzgnotanaddr")

    assert ctx["resolved"] is False
    assert client.requests == []  # no Koios call without a stake key


# ---------------------------------------------------------------------------
# Multi-credential matching per protocol
# ---------------------------------------------------------------------------

async def test_indigo_finds_position_owned_by_fourth_cred(service, monkeypatch):
    fixture = [
        {"owner": "someoneelse" + "0" * 45, "staked_indy": 1_000_000,
         "snapshot_ada": 0, "output_hash": "x"},
        {"owner": CREDS[3], "staked_indy": 8_670_383_309,
         "snapshot_ada": 0, "output_hash": "y"},
    ]
    client = FakeClient([
        ("/api/staking-positions", FakeResponse(json_data=fixture)),
    ])
    use_client(monkeypatch, client)

    # Scanned address is ADDRS[0]; the position belongs to cred #4 of 6
    result = await service.get_indigo_staking(ADDRS[0], payment_creds=CREDS)

    assert result is not None
    assert result["total_staked_indy"] == pytest.approx(8670.383309)
    assert result["positions"][0]["owner"] == CREDS[3]

    # Single-cred call (pre-P2 behavior) must NOT see the sibling's position
    assert await service.get_indigo_staking(ADDRS[0]) is None
    # Widening costs no extra API calls — one download per lookup
    assert len(client.requests) == 2


async def test_liqwid_sends_all_payment_keys_in_one_query(service, monkeypatch):
    client = FakeClient([
        ("/graphql", liqwid_graphql_response([
            {"txId": "aa-0", "owner": CREDS[4], "stakedAmount": 42.0,
             "delegatedTo": None},
        ])),
    ])
    use_client(monkeypatch, client)

    result = await service.get_liqwid_staking(ADDRS[0], payment_creds=CREDS)

    assert result is not None
    assert result["total_staked_lq"] == pytest.approx(42.0)
    assert len(client.requests) == 1  # whole account in ONE query
    sent = client.requests[0][2]["json"]["variables"]["input"]["paymentKeys"]
    assert sorted(sent) == sorted(CREDS)


async def test_strike_v2_probes_addresses_dedupes_accounts(service, monkeypatch):
    """Two sibling addresses resolve to the SAME Strike account — balance and
    vaults must not double; a third address holds a second account — summed."""
    calls = {"accounts": []}

    class StrikeClient(FakeClient):
        async def get(self, url, **kwargs):
            self.requests.append(("GET", url, kwargs))
            params = kwargs.get("params") or {}
            if "/v2/account" in url:
                addr = params["blockchain_address"]
                calls["accounts"].append(addr)
                if addr in (ADDRS[0], ADDRS[1]):
                    return FakeResponse(json_data={
                        "account_id": "acct-main", "wallet_balance": 56.93})
                if addr == ADDRS[2]:
                    return FakeResponse(json_data={
                        "account_id": "acct-second", "wallet_balance": 10.0})
                return FakeResponse(status_code=404, text="no account")
            if "/v2/vault/positions" in url:
                if params["account_id"] == "acct-main":
                    return FakeResponse(json_data={"positions": [
                        {"vault_id": "v1", "shares": 100}]})
                return FakeResponse(json_data={"positions": []})
            if "/v2/vaults" in url:
                return FakeResponse(json_data={"vaults": [
                    {"vault_id": "v1", "name": "V One", "share_price": 1.5}]})
            return FakeResponse(status_code=404)

    client = StrikeClient([])
    use_client(monkeypatch, client)

    result = await service.get_strike_v2_positions(
        ADDRS[0], account_addresses=ADDRS
    )

    assert result is not None
    assert sorted(calls["accounts"]) == sorted(ADDRS)  # every address probed once
    assert sorted(result["account_ids"]) == ["acct-main", "acct-second"]
    assert result["v2_balance"] == pytest.approx(56.93 + 10.0)  # deduped, then summed
    assert len(result["vault_positions"]) == 1  # v1 counted once
    assert result["vault_positions"][0]["value_ada"] == pytest.approx(150.0)


async def test_strike_v2_probe_fanout_capped(service, monkeypatch):
    many = [make_addr(i) for i in range(1, 30)]

    class CountingClient(FakeClient):
        async def get(self, url, **kwargs):
            self.requests.append(("GET", url, kwargs))
            return FakeResponse(status_code=404, text="no account")

    client = CountingClient([])
    use_client(monkeypatch, client)

    result = await service.get_strike_v2_positions(many[0], account_addresses=many)

    assert result is None
    assert len(client.requests) == 12  # capped fan-out


# ---------------------------------------------------------------------------
# Route-level credential partition (no double counting across stored rows)
# ---------------------------------------------------------------------------

@pytest.fixture
def identity_env(monkeypatch):
    """Wire _resolve_scan_identity to a canned context and stored-wallet set."""

    def _wire(context_addresses, context_creds, stored_addresses, resolved=True):
        async def fake_context(address):
            return {
                "address": address,
                "stake_address": STAKE_ADDRESS,
                "addresses": context_addresses,
                "payment_creds": context_creds,
                "resolved": resolved,
            }

        monkeypatch.setattr(
            defi_router.defi_service, "resolve_wallet_context", fake_context
        )

        addr_to_cred = dict(zip(ADDRS, CREDS))
        monkeypatch.setattr(
            defi_router.defi_service, "_get_payment_credential",
            lambda a: addr_to_cred.get(a),
        )

        async def fake_wallets(user_id=None):
            return [{"address": a, "blockchain": "cardano"}
                    for a in stored_addresses]

        monkeypatch.setattr(defi_router, "get_all_wallets", fake_wallets)

    return _wire


async def test_representative_claims_orphan_creds_only(identity_env):
    # Two stored rows; the lexicographically-lowest is the representative.
    # Orphan creds (the four unstored siblings') go to it exclusively.
    stored = [ADDRS[0], ADDRS[2]]
    identity_env(ADDRS, CREDS, stored_addresses=stored)
    addr_to_cred = dict(zip(ADDRS, CREDS))
    rep = sorted(stored)[0]
    other = next(a for a in stored if a != rep)

    creds, addresses = await _resolve_scan_identity(rep, user_id=1)

    assert creds is not None
    assert addr_to_cred[rep] in creds           # own cred
    assert addr_to_cred[other] not in creds     # stored sibling's cred EXCLUDED
    assert set(creds) == set(CREDS) - {addr_to_cred[other]}
    assert other not in addresses               # stored sibling's address excluded
    assert rep in addresses


async def test_non_representative_sibling_scans_own_cred_only(identity_env):
    stored = [ADDRS[0], ADDRS[2]]
    identity_env(ADDRS, CREDS, stored_addresses=stored)
    non_rep = sorted(stored)[1]

    creds, addresses = await _resolve_scan_identity(non_rep, user_id=1)

    assert (creds, addresses) == (None, None)  # pre-P2 single-address scan


async def test_partition_covers_account_exactly_once(identity_env):
    """Union of every stored row's matching set == all creds, no overlaps."""
    stored = [ADDRS[0], ADDRS[2], ADDRS[5]]
    identity_env(ADDRS, CREDS, stored_addresses=stored)

    union = []
    for addr in stored:
        creds, _ = await _resolve_scan_identity(addr, user_id=1)
        if creds is None:
            creds = [dict(zip(ADDRS, CREDS))[addr]]  # own-cred fallback
        union.extend(creds)

    assert sorted(union) == sorted(CREDS)  # complete AND disjoint


async def test_unresolved_context_falls_back(identity_env):
    identity_env([ADDRS[0]], [CREDS[0]], stored_addresses=[ADDRS[0]],
                 resolved=False)

    assert await _resolve_scan_identity(ADDRS[0], user_id=1) == (None, None)


async def test_single_cred_account_falls_back(identity_env):
    identity_env([ADDRS[0]], [CREDS[0]], stored_addresses=[ADDRS[0]])

    assert await _resolve_scan_identity(ADDRS[0], user_id=1) == (None, None)
