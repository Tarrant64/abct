"""
P3-FIX3 approval requirements.

1. Local bech32 stake-address derivation correctness against CIP-19
   specification test vectors plus synthetic constructed vectors. This
   fixture pins a live bug caught on arrival: the CIP-19 type mapping was
   (0,2)→key instead of (0,1)→key, so addr1z payment-script wallets derived
   a script-stake address (stake17…) and their delegations would have been
   misattributed.
2. Blockfrost-failure resilience: a wallet's delegation row must never
   vanish because a fetch hiccuped — expired cached account info is served.
3. Cooldown: a legitimately cold wallet (never scanned) bypasses the
   rescan cooldown and fills promptly.
"""

import asyncio
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.defi as defi_router  # noqa: E402
import routers.mobile as mobile_router  # noqa: E402
from services.cardano import _derive_stake_key_local  # noqa: E402

# Derivation vectors. The first two are the mainnet example addresses from
# the CIP-19 specification (type 0 and type 1, sharing one stake key hash);
# the rest are synthetic mainnet base addresses built from fixed credential
# bytes, with the expected reward address encoded directly from the chosen
# stake credential (0xe1 header + 28-byte key hash) — independent of the
# parsing code under test. The addr1z entries are CIP-19 type 1 (payment
# SCRIPT / stake KEY) — the case the old (0,2)→key mapping got wrong: it
# derived stake17… (script-stake) for them instead of stake1u….
KNOWN_PAIRS = [
    # CIP-19 mainnet examples: type 0 (key/key) and type 1 (script/key)
    ("addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgse35a3x",
     "stake1uyehkck0lajq8gr28t9uxnuvgcqrc6070x3k9r8048z8y5gh6ffgw"),
    ("addr1z8phkx6acpnf78fuvxn0mkew3l0fd058hzquvz7w36x4gten0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgs9yc0hh",
     "stake1uyehkck0lajq8gr28t9uxnuvgcqrc6070x3k9r8048z8y5gh6ffgw"),
    # Synthetic: payment cred 0x11*28 / stake cred 0xab*28, type 0
    ("addr1qyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zydt4w46h2at4w46h2at4w46h2at4w46h2at4w46h2at4w4sm0f8ct",
     "stake1ux46h2at4w46h2at4w46h2at4w46h2at4w46h2at4w46h2cfk870n"),
    # Synthetic: payment cred 0x22*28 / stake cred 0xcd*28, type 0
    ("addr1qy3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zygkdehxumnwdehxumnwdehxumnwdehxumnwdehxumnwdehxsu52c9d",
     "stake1u8xumnwdehxumnwdehxumnwdehxumnwdehxumnwdehxumngnxnspf"),
    # Synthetic: type 1 (addr1z) sharing the 0xcd stake cred with the pair above
    ("addr1zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zywdehxumnwdehxumnwdehxumnwdehxumnwdehxumnwdehxsa575x2",
     "stake1u8xumnwdehxumnwdehxumnwdehxumnwdehxumnwdehxumngnxnspf"),
]

VALID_ADDR = KNOWN_PAIRS[0][0]
VALID_STAKE = KNOWN_PAIRS[0][1]


@pytest.mark.parametrize("address,expected_stake", KNOWN_PAIRS)
def test_local_derivation_matches_koios(address, expected_stake):
    assert _derive_stake_key_local(address) == expected_stake


def test_local_derivation_rejects_non_base_inputs():
    # A stake address is not a payment address
    assert _derive_stake_key_local(VALID_STAKE) is None
    # Garbage
    assert _derive_stake_key_local("addr1junkjunkjunk") is None
    assert _derive_stake_key_local("") is None


# ---------------------------------------------------------------------------
# Delegation rows never vanish on Blockfrost failure
# ---------------------------------------------------------------------------

STALE_ACCOUNT_INFO = {
    "stake_address": VALID_STAKE,
    "active": True,
    "controlled_ada": 2032.78,
    "withdrawable_ada": 0.07,
    "rewards_ada": 0.07,
    "pool_id": "pool14wk2m2af7y4gk5uzlsmsunn7d9ppldvcxxa5an9r5ywek8330fg",
}


@pytest.fixture
def mobile_env(monkeypatch):
    """The real mobile staking endpoint wired to stubs: one wallet, fresh
    account-info cache MISS, stale row available, Blockfrost DOWN."""

    async def fake_wallets(user_id=None):
        return [{"id": 1, "address": VALID_ADDR, "blockchain": "cardano"}]

    monkeypatch.setattr(mobile_router, "get_all_wallets", fake_wallets)

    async def fake_get_cache(key, user_id=None):
        return None  # every fresh cache misses

    async def fake_get_stale_cache(key, user_id=None):
        if key.startswith("stake_account_info_"):
            return dict(STALE_ACCOUNT_INFO), "2026-07-12T00:00:00"
        return None, None

    set_calls = {}

    async def fake_set_cache(key, value, ttl, user_id=None):
        set_calls[key] = value

    monkeypatch.setattr(mobile_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(mobile_router, "get_stale_cache", fake_get_stale_cache)
    monkeypatch.setattr(mobile_router, "set_cache", fake_set_cache)

    async def blockfrost_down(stake_address):
        raise RuntimeError("blockfrost hiccup")

    monkeypatch.setattr(
        mobile_router.cardano_service, "get_stake_account_info", blockfrost_down
    )

    async def api_never_needed(address):
        raise AssertionError("get_stake_address API must not be called for a "
                             "locally derivable address")

    monkeypatch.setattr(
        mobile_router.cardano_service, "get_stake_address", api_never_needed
    )

    from services.pricing import pricing_service

    async def fake_prices():
        return {"ADA": {"usd": 0.60}}

    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)

    async def no_protocols(address, refresh=False, user_id=None):
        return None

    monkeypatch.setattr(defi_router, "get_staking_positions", no_protocols)
    return set_calls


async def test_delegation_survives_blockfrost_outage(mobile_env):
    """Account-info fetch fails AND the fresh cache is empty: the expired
    cached info must be served — the delegation row never vanishes."""
    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)

    native = [p for p in out["positions"] if p.get("stake_key") == VALID_STAKE]
    assert len(native) == 1
    assert native[0]["delegated_amount"] == pytest.approx(2032.78)
    assert out["total_staked_usd"] == pytest.approx(2032.78 * 0.60, rel=1e-3)


async def test_local_derivation_used_no_api(mobile_env):
    """The stake address comes from local bech32 derivation — the fixture's
    get_stake_address stub raises if the API path is ever taken."""
    out = await mobile_router.get_mobile_defi_staking(refresh=False, user_id=1)
    assert any(p.get("stake_key") == VALID_STAKE for p in out["positions"])


# ---------------------------------------------------------------------------
# Cold wallets bypass the rescan cooldown
# ---------------------------------------------------------------------------

async def test_cold_wallet_bypasses_cooldown(monkeypatch):
    """A wallet with no completion record schedules immediately even while
    other wallets sit in cooldown — new wallets must fill promptly."""
    import time as _t

    calls = []

    async def fake_compute(address, user_id):
        calls.append(address)
        return {}

    monkeypatch.setattr(defi_router, "_compute_staking_positions", fake_compute)
    defi_router._staking_refresh_tasks.clear()
    defi_router._staking_scan_completions.clear()

    # An existing wallet just finished scanning — in cooldown
    defi_router._staking_scan_completions["1:staking_positions_addr1old"] = _t.monotonic()

    defi_router._schedule_staking_refresh("addr1old", 1)
    defi_router._schedule_staking_refresh("addr1brandnew", 1)
    await asyncio.sleep(0.01)

    assert calls == ["addr1brandnew"]  # cooldown held for old, cold fills
    for task in list(defi_router._staking_refresh_tasks.values()):
        await task
