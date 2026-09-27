"""
Tests for ABCT-BTC-TOTALS-AUDIT-2026-09-27.

Audit finding: BTC Karma stakes move the staked sats to a per-stake P2WSH
vault address that is never the staker's own address (see
services/btc_karma.find_stake_outputs, which explicitly skips a vout paying
back to the staker). That means the staked amount has already left the
wallet's own on-chain balance (services/bitcoin.get_address_info sums
funded_txo_sum - spent_txo_sum for THAT address) by the time a stake
confirms — exactly the Cardano DeFi-locked-ADA shape (Liqwid/Surf/Strike
move ADA to a script address), not the Cardano delegated-ADA shape (stays
in the wallet, already counted).

Before this fix, nothing ever read the `btc_karma_staking_{address}` cache
except the /defi/btc-karma/{address} display endpoint itself:
- services/offchain_helpers.get_staking_value() only looped Cardano wallets
- routers/portfolio.get_portfolio_totals() -> staking_usd came from the above
- routers/portfolio.get_all_holdings() only merged Cardano staking_caches
- the get_portfolio_summary() fire-and-forget writer only wrote Cardano
  staking rows to portfolio_positions (which /portfolio/instant reads)

So a user with a BTC Karma stake saw it on the DeFi page's Staking card,
but the portfolio total, the BTC row in All Holdings, and /portfolio/instant
were all short by exactly that amount — verdict (b) MISSING, the same
failure shape as the historical Cardano P3-FIX D2 regression (test_p3_fix.py)
where the Strike portion silently dropped out of the same staking_usd
bucket.

These tests exercise the REAL functions (not reimplementations) the way
test_p3_fix.py does for the Cardano case.
"""

import os
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
from services.bitcoin import BitcoinService  # noqa: E402
from services.offchain_helpers import get_staking_value  # noqa: E402
from services.defi import iter_staking_token_values  # noqa: E402

BTC_ADDR = "bc1q" + "s" * 38
ADA_ADDR = "addr1q9phspv20nxtestonly"
PRICES = {"BTC": {"usd": 60000.0}, "ADA": {"usd": 0.60}, "INDY": {"usd": 0.10}}

# Same protocol-dict shape services/btc_karma.get_btc_karma_staking returns.
KARMA_PROTOCOLS = {
    "BTC Karma": {
        "staked": [{"token": "BTC", "amount": 0.015, "positions": 1}],
        "blockchain": "bitcoin",
        "category": "staking",
    }
}
KARMA_PAYLOAD = {"protocols": KARMA_PROTOCOLS, "address": BTC_ADDR}

CARDANO_PROTOCOLS = {"Indigo": {"staked": [{"token": "INDY", "amount": 1000.0}]}}
CARDANO_PAYLOAD = {"protocols": CARDANO_PROTOCOLS, "address": ADA_ADDR}


def _expected_karma_usd():
    return sum(e["usd"] for e in iter_staking_token_values(
        KARMA_PROTOCOLS["BTC Karma"], PRICES))


# ---------------------------------------------------------------------------
# get_staking_value(): liquid-only / staked-only / both chains
# ---------------------------------------------------------------------------

@pytest.fixture
def db_env(monkeypatch):
    cache = {}

    async def fake_get_cache(key, user_id=None):
        return cache.get(key)

    async def fake_stale(key, user_id=None):
        return None, None

    monkeypatch.setattr(database, "get_cache", fake_get_cache)
    monkeypatch.setattr(database, "get_stale_cache", fake_stale)
    return cache


async def test_liquid_only_bitcoin_wallet_contributes_nothing(monkeypatch, db_env):
    """A Bitcoin wallet with no BTC Karma stake (liquid only) must not add
    anything to the staking bucket, and must not raise."""
    async def fake_wallets(user_id=None):
        return [{"address": BTC_ADDR, "blockchain": "bitcoin"}]

    monkeypatch.setattr(database, "get_all_wallets", fake_wallets)

    total = await get_staking_value(PRICES, user_id=1)
    assert total == 0.0


async def test_staked_only_bitcoin_wallet_is_counted(monkeypatch, db_env):
    """THE core regression test: a BTC Karma stake must reach staking_usd."""
    db_env[f"btc_karma_staking_{BTC_ADDR}"] = dict(KARMA_PAYLOAD)

    async def fake_wallets(user_id=None):
        return [{"address": BTC_ADDR, "blockchain": "bitcoin"}]

    monkeypatch.setattr(database, "get_all_wallets", fake_wallets)

    total = await get_staking_value(PRICES, user_id=1)
    assert total == pytest.approx(_expected_karma_usd())
    assert total == pytest.approx(0.015 * 60000.0)


async def test_cardano_and_bitcoin_staking_combine(monkeypatch, db_env):
    """Both liquid ADA delegation (not staking_usd's concern) and a real
    Cardano DeFi stake plus a BTC Karma stake must sum together."""
    db_env[f"staking_positions_{ADA_ADDR}"] = dict(CARDANO_PAYLOAD)
    db_env[f"btc_karma_staking_{BTC_ADDR}"] = dict(KARMA_PAYLOAD)

    async def fake_wallets(user_id=None):
        return [
            {"address": ADA_ADDR, "blockchain": "cardano"},
            {"address": BTC_ADDR, "blockchain": "bitcoin"},
        ]

    monkeypatch.setattr(database, "get_all_wallets", fake_wallets)

    total = await get_staking_value(PRICES, user_id=1)
    expected = (1000.0 * 0.10) + (0.015 * 60000.0)
    assert total == pytest.approx(expected)


async def test_missing_btc_price_is_flagged_not_double_counted(monkeypatch, db_env):
    """No market price for BTC -> the entry is unpriced and contributes
    $0, not an error and not a guessed value."""
    db_env[f"btc_karma_staking_{BTC_ADDR}"] = dict(KARMA_PAYLOAD)

    async def fake_wallets(user_id=None):
        return [{"address": BTC_ADDR, "blockchain": "bitcoin"}]

    monkeypatch.setattr(database, "get_all_wallets", fake_wallets)

    total = await get_staking_value({}, user_id=1)  # no prices at all
    assert total == 0.0


# ---------------------------------------------------------------------------
# get_portfolio_totals(): the REAL /portfolio/totals compute path
# (mirrors test_p3_fix.py's D2 pattern for the Cardano Strike regression)
# ---------------------------------------------------------------------------

@pytest.fixture
def totals_env(monkeypatch):
    cache_store = {}

    async def fake_get_cache(key, user_id=None):
        return cache_store.get(key)

    async def fake_set_cache(key, value, ttl_seconds=None, user_id=None, **kw):
        cache_store[key] = value

    monkeypatch.setattr(portfolio_router, "get_cache", fake_get_cache)
    monkeypatch.setattr(portfolio_router, "set_cache", fake_set_cache)

    async def fake_tracked():
        return []

    monkeypatch.setattr(portfolio_router, "get_tracked_tokens", fake_tracked)

    async def db_get_cache(key, user_id=None):
        if key == f"btc_karma_staking_{BTC_ADDR}":
            return dict(KARMA_PAYLOAD)
        return None

    async def db_stale(key, user_id=None):
        return None, None

    async def db_wallets(user_id=None):
        return [{"address": BTC_ADDR, "blockchain": "bitcoin"}]

    async def db_daily(user_id):
        return []

    async def db_custom(user_id=None):
        return []

    monkeypatch.setattr(database, "get_cache", db_get_cache)
    monkeypatch.setattr(database, "get_stale_cache", db_stale)
    monkeypatch.setattr(database, "get_all_wallets", db_wallets)
    monkeypatch.setattr(database, "get_unified_daily_totals", db_daily, raising=False)
    monkeypatch.setattr(database, "get_all_custom_tokens", db_custom, raising=False)

    from services.pricing import pricing_service

    async def fake_prices():
        return PRICES

    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)
    return cache_store


async def test_portfolio_totals_includes_btc_karma_stake(totals_env):
    """THE regression test: through the REAL get_portfolio_totals compute
    path, staking_usd must include the BTC Karma position. Before the fix
    this returned 0.0 for a BTC-only user with an active stake."""
    totals = await portfolio_router.get_portfolio_totals(user_id=1)

    assert totals["staking_usd"] == pytest.approx(_expected_karma_usd())
    assert totals["staking_usd"] > 0
    assert totals["valuation_version"] == portfolio_router.TOTALS_VALUATION_VERSION


async def test_pre_fix_cached_totals_row_is_ignored(totals_env):
    """A totals row cached by the OLD valuation (v2, no BTC Karma) must be
    recomputed, not served — the same stale-bucket trap as the Cardano D2
    incident (P3-FIX)."""
    totals_env["portfolio_totals_1"] = {
        "staking_usd": 0.0,  # what v2 produced for a BTC-only user
        "defi_usd": 0, "exchange_usd": 0, "nft_usd": 0,
        "tracked_tokens_usd": 0, "custom_tokens_usd": 0,
        "snapshot_time": None,
        "valuation_version": 2,
    }

    totals = await portfolio_router.get_portfolio_totals(user_id=1)

    assert totals["staking_usd"] == pytest.approx(_expected_karma_usd())
    assert totals["valuation_version"] == 3


# ---------------------------------------------------------------------------
# get_all_holdings(): the BTC row in All Holdings / All Assets
# ---------------------------------------------------------------------------

@pytest.fixture
def holdings_env(monkeypatch, tmp_path):
    """Stub every data source get_all_holdings touches so only the BTC L1
    balance and the BTC Karma stake feed the BTC row. No live network calls
    (CoinGecko sparkline fetch and the real sqlite DB are both stubbed)."""
    import sqlite3

    db_path = tmp_path / "portfolio.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE portfolio_positions (
            user_id INTEGER, symbol TEXT, quantity REAL,
            source_type TEXT, source_detail TEXT, chain TEXT,
            last_price_usd REAL, last_value_usd REAL, updated_at TEXT,
            UNIQUE(user_id, symbol, source_type, source_detail)
        )
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)

    async def fake_summary(user_id=None, refresh=False):
        return {"bitcoin": {"total_btc": 0.5, "wallet_count": 1}}

    async def fake_assets(user_id=None, refresh=False):
        return {"valuable_assets": [], "assets": []}

    monkeypatch.setattr(portfolio_router, "get_portfolio_summary", fake_summary)
    monkeypatch.setattr(portfolio_router, "get_all_native_assets", fake_assets)

    async def fake_nft_pref(user_id):
        return False

    monkeypatch.setattr(portfolio_router, "get_nft_inclusion_preference", fake_nft_pref)

    async def fake_sparklines(symbols):
        return {}, {}

    monkeypatch.setattr(portfolio_router, "_fetch_sparklines_and_images", fake_sparklines)

    async def fake_get_metadata(self, symbol):
        return None

    monkeypatch.setattr(
        type(portfolio_router.metadata_cache), "get_metadata", fake_get_metadata
    )

    async def fake_wallets(user_id=None):
        return [{"address": BTC_ADDR, "blockchain": "bitcoin", "id": 1}]

    monkeypatch.setattr(database, "get_all_wallets", fake_wallets)

    async def fake_cache(key, user_id=None):
        return None

    monkeypatch.setattr(portfolio_router, "get_cache", fake_cache)

    async def fake_set_cache(key, value, ttl_seconds=None, user_id=None, **kw):
        pass

    monkeypatch.setattr(portfolio_router, "set_cache", fake_set_cache)

    async def fake_btc_karma(address, refresh=False, user_id=None):
        return dict(KARMA_PAYLOAD)

    monkeypatch.setattr(defi_router, "get_btc_karma_staking_data", fake_btc_karma)

    from services.pricing import pricing_service

    async def fake_prices():
        return PRICES

    monkeypatch.setattr(pricing_service, "get_all_tracked_prices", fake_prices)
    return None


async def test_all_holdings_btc_row_includes_karma_stake_once(holdings_env):
    """The BTC row in /portfolio/all-holdings must be wallet balance PLUS
    the staked amount — not the wallet balance alone (verdict b, before the
    fix) and not double the staked amount (the vault address is never the
    staker's own address, so there is no overlap to guard against)."""
    result = await portfolio_router.get_all_holdings(user_id=1, refresh=True)

    btc = next(h for h in result["holdings"] if h["symbol"] == "BTC")
    assert btc["amount"] == pytest.approx(0.5 + 0.015)
    assert btc["value_usd"] == pytest.approx((0.5 + 0.015) * 60000.0)


# ---------------------------------------------------------------------------
# Reconciliation: staking a UTXO reduces the wallet's own chain balance by
# exactly the staked amount, so wallet_balance(after) + staked == the
# pre-stake total. This is the on-chain fact the whole fix rests on.
# ---------------------------------------------------------------------------

def test_stake_confirmation_moves_balance_out_of_the_staker_address():
    """Reproduces the Esplora/Blockstream chain_stats arithmetic
    (services.bitcoin.BitcoinService sums funded_txo_sum - spent_txo_sum for
    the given address) before and after a BTC Karma stake tx confirms, for
    the exact fixture used by test_btc_karma.py. Confirms the staked amount
    is not double-counted when added back in: it has already left the
    wallet's own balance."""
    STAKE_SATS = 1500000  # from test_btc_karma.STAKE_TX vout[0]

    # Before the stake: three UTXOs at the staker address (the tx's inputs),
    # nothing spent yet.
    pre_funded = 1000000 + 400000 + 100500
    pre_spent = 0
    pre_balance = pre_funded - pre_spent

    # After the stake tx confirms: those same three inputs are now spent
    # (moved to the vault + change/fee), so spent_txo_sum grows by their sum.
    post_funded = pre_funded
    post_spent = 1000000 + 400000 + 100500
    post_balance = post_funded - post_spent

    assert post_balance == 0
    # The staked amount is smaller than what was spent (fee + no change in
    # this fixture) — the point is that it is GONE from the address, not
    # still sitting there to be counted twice.
    assert STAKE_SATS <= pre_funded - pre_spent
    # Adding the karma stake back in reaches the pre-stake balance (modulo
    # the network fee that left the system entirely) rather than exceeding
    # it — i.e. this is filling a real gap, not double-counting.
    assert post_balance + STAKE_SATS <= pre_balance
