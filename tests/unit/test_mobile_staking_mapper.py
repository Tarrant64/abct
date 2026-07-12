"""
Unit tests for the mobile staking mapper (P0c).

The old mapper only rendered each protocol's `staked` array, silently
dropping Strike V2 trading balances / vault deposits and Indigo CDPs /
stability-pool deposits. _map_staking_protocol_positions renders every
kind; these tests feed it entries shaped exactly like
defi_service.get_all_staking_positions output.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.mobile as mobile_module  # noqa: E402
from routers.mobile import _map_staking_protocol_positions  # noqa: E402

ADA_PRICE = 0.60
ALL_PRICES = {
    "ADA": {"usd": ADA_PRICE},
    "INDY": {"usd": 1.10},
    "LQ": {"usd": 2.50},
    "STRIKE": {"usd": 0.02},
    "IUSD": {"usd": 1.0},
}


@pytest.fixture(autouse=True)
def fake_token_info(monkeypatch):
    async def _fake(symbol):
        return symbol.capitalize(), f"https://img.test/{symbol.lower()}.png"

    monkeypatch.setattr(mobile_module, "_resolve_token_info", _fake)


async def test_staked_array_mapping_unchanged():
    """Legacy `staked`-array positions keep the exact same field names."""
    protocol_data = {
        "staked": [{
            "token": "INDY",
            "amount": 8670.383309,
            "amount_formatted": "8,670.383309",
            "positions": 1,
            "logo_url": None,
        }],
        "pending_indy": 0,
        "pending_ada": 0,
    }

    positions, staked_usd, rewards_usd, has_unpriced = (
        await _map_staking_protocol_positions(
            "Indigo", protocol_data, ALL_PRICES, ADA_PRICE
        )
    )

    assert len(positions) == 1
    pos = positions[0]
    assert pos == {
        "blockchain": "cardano",
        "protocol": "Indigo",
        "staked_amount": 8670.383309,
        "staked_symbol": "INDY",
        "staked_usd": round(8670.383309 * 1.10, 2),
        "rewards_amount": 0,
        "rewards_usd": 0,
        "apy": 0,
        "active": True,
        "logo_url": "https://img.test/indy.png",
    }
    assert staked_usd == pytest.approx(8670.383309 * 1.10)
    assert rewards_usd == 0
    assert has_unpriced is False


async def test_strike_v2_balance_and_vaults_render():
    """Strike V2 trading balance + vault deposits become ADA positions."""
    protocol_data = {
        "staked": [],
        "pending_rewards": 0,
        "reward_token": "STRIKE",
        "v2_balance": 56.93,
        "v2_vault_positions": [{
            "vault_id": "0197e1a2-aaaa-bbbb-cccc-9da520c4d339",
            "vault_name": "Glacier Arc Digital",
            "shares": 599.68,
            "share_price": 1.172,
            "value_ada": 702.98,
        }],
        "total_vault_ada": 702.98,
    }

    positions, staked_usd, rewards_usd, has_unpriced = (
        await _map_staking_protocol_positions(
            "Strike", protocol_data, ALL_PRICES, ADA_PRICE
        )
    )

    assert len(positions) == 2

    balance = next(p for p in positions if p["position_kind"] == "trading_balance")
    assert balance["staked_amount"] == 56.93
    assert balance["staked_symbol"] == "ADA"
    assert balance["staked_usd"] == round(56.93 * ADA_PRICE, 2)
    assert balance["pool_name"] == "Strike V2 Trading Account"

    vault = next(p for p in positions if p["position_kind"] == "vault")
    assert vault["pool_name"] == "Glacier Arc Digital"
    assert vault["staked_amount"] == 702.98
    assert vault["staked_symbol"] == "ADA"
    assert vault["staked_usd"] == round(702.98 * ADA_PRICE, 2)
    assert vault["shares"] == 599.68
    assert vault["priced"] is True
    assert vault["share_price_source"] == "vaults_api"

    assert staked_usd == pytest.approx((56.93 + 702.98) * ADA_PRICE)
    assert rewards_usd == 0
    assert has_unpriced is False


async def test_unpriced_vault_flag_passes_through():
    """A share_price=1 fallback vault must render flagged, not vanish or
    masquerade as a market valuation."""
    protocol_data = {
        "staked": [],
        "v2_vault_positions": [{
            "vault_id": "closed-vault-id",
            "vault_name": "Retired Vault",
            "shares": 599.68,
            "share_price": 1.0,
            "value_ada": 599.68,
            "priced": False,
            "share_price_source": "fallback",
        }],
    }

    positions, staked_usd, _, has_unpriced = await _map_staking_protocol_positions(
        "Strike", protocol_data, ALL_PRICES, ADA_PRICE
    )

    assert len(positions) == 1
    vault = positions[0]
    assert vault["priced"] is False
    assert vault["share_price_source"] == "fallback"
    assert vault["staked_amount"] == 599.68  # amount still visible
    assert vault["staked_usd"] == 0  # flagged value contributes nothing
    assert vault["pool_name"] == "Retired Vault"
    assert staked_usd == 0
    assert has_unpriced is True


async def test_indigo_cdps_and_stability_pool_render():
    protocol_data = {
        "staked": [],
        "cdps": [{
            "asset": "iUSD",
            "collateral_ada": 2500.0,
            "minted_amount": 750.0,
            "min_collateral_ratio": 150,
            "output_hash": "abc",
        }],
        "stability_pool": [{
            "asset": "iUSD",
            "deposited": 120.5,
            "position_count": 1,
        }],
    }

    positions, staked_usd, _, has_unpriced = await _map_staking_protocol_positions(
        "Indigo", protocol_data, ALL_PRICES, ADA_PRICE
    )

    assert len(positions) == 2

    cdp = next(p for p in positions if p["position_kind"] == "cdp")
    assert cdp["pool_name"] == "Indigo CDP (iUSD)"
    assert cdp["staked_amount"] == 2500.0  # gross collateral stays visible
    assert cdp["collateral_ada"] == 2500.0
    assert cdp["staked_symbol"] == "ADA"
    # Director decision: CDP USD value = NET equity (collateral - debt)
    cdp_net = 2500.0 * ADA_PRICE - 750.0 * 1.0
    assert cdp["staked_usd"] == round(cdp_net, 2)
    assert cdp["minted_asset"] == "iUSD"
    assert cdp["minted_amount"] == 750.0

    sp = next(p for p in positions if p["position_kind"] == "stability_pool")
    assert sp["pool_name"] == "Indigo Stability Pool (iUSD)"
    assert sp["staked_amount"] == 120.5
    assert sp["staked_symbol"] == "iUSD"
    assert sp["staked_usd"] == round(120.5 * 1.0, 2)  # iUSD priced at $1

    assert staked_usd == pytest.approx(cdp_net + 120.5)
    assert has_unpriced is False


async def test_cdp_with_unpriced_debt_flagged_not_overstated():
    """Unknown minted-asset price would silently overstate equity — the CDP
    must flag unpriced and contribute 0 instead."""
    protocol_data = {
        "staked": [],
        "cdps": [{
            "asset": "iBTC",  # not in the price map
            "collateral_ada": 5000.0,
            "minted_amount": 0.01,
        }],
    }

    positions, staked_usd, _, has_unpriced = await _map_staking_protocol_positions(
        "Indigo", protocol_data, ALL_PRICES, ADA_PRICE
    )

    assert len(positions) == 1
    cdp = positions[0]
    assert cdp["priced"] is False
    assert cdp["staked_usd"] == 0
    assert cdp["staked_amount"] == 5000.0  # amount still visible
    assert staked_usd == 0
    assert has_unpriced is True


async def test_empty_status_entry_yields_no_positions():
    """Iagon timeout/no_staking placeholder entries must render nothing."""
    protocol_data = {
        "staked": [],
        "category": "depin",
        "status": "no_staking",
        "reward_token": "IAG",
        "total_positions": 0,
    }

    positions, staked_usd, rewards_usd, has_unpriced = (
        await _map_staking_protocol_positions(
            "Iagon", protocol_data, ALL_PRICES, ADA_PRICE
        )
    )

    assert positions == []
    assert staked_usd == 0
    assert rewards_usd == 0
    assert has_unpriced is False


async def test_pending_rewards_counted():
    protocol_data = {
        "staked": [{"token": "LQ", "amount": 2089.169352}],
        "pending_rewards": 10.0,
        "reward_token": "LQ",
    }

    _, staked_usd, rewards_usd, _ = await _map_staking_protocol_positions(
        "Liqwid", protocol_data, ALL_PRICES, ADA_PRICE
    )

    assert staked_usd == pytest.approx(2089.169352 * 2.50)
    assert rewards_usd == pytest.approx(10.0 * 2.50)


async def test_cross_screen_totals_agree_by_construction():
    """The mapper (Staking tab), the top-holdings/snapshot consumers, and the
    token-detail drill-down all derive from iter_staking_token_values — the
    same fixture must produce the identical USD figure everywhere."""
    from services.defi import iter_staking_token_values

    protocol_data = {
        "staked": [{"token": "INDY", "amount": 8670.383309}],
        "v2_balance": 56.93,
        "v2_vault_positions": [{
            "vault_id": "v", "vault_name": "V", "shares": 599.68,
            "share_price": 1.172, "value_ada": 702.98,
        }],
        "cdps": [{"asset": "iUSD", "collateral_ada": 2500.0,
                  "minted_amount": 750.0}],
        "stability_pool": [{"asset": "iUSD", "deposited": 120.5}],
        "reward_token": "LQ",
        "pending_rewards": 10.0,
    }

    _, mapper_staked, mapper_rewards, _ = await _map_staking_protocol_positions(
        "Indigo", protocol_data, ALL_PRICES, ADA_PRICE
    )

    entries = iter_staking_token_values(protocol_data, ALL_PRICES)
    helper_staked = sum(e['usd'] for e in entries if e['kind'] != 'reward')
    helper_rewards = sum(e['usd'] for e in entries if e['kind'] == 'reward')

    assert mapper_staked == pytest.approx(helper_staked)
    assert mapper_rewards == pytest.approx(helper_rewards)

    # And the expected absolute value, spelled out once:
    expected = (
        8670.383309 * 1.10             # INDY staked
        + 56.93 * ADA_PRICE            # Strike V2 trading balance
        + 702.98 * ADA_PRICE           # vault
        + (2500.0 * ADA_PRICE - 750.0) # CDP net equity (iUSD @ $1)
        + 120.5 * 1.0                  # stability pool iUSD
    )
    assert helper_staked == pytest.approx(expected)
    assert helper_rewards == pytest.approx(10.0 * 2.50)


async def test_string_amounts_from_stale_cache_do_not_crash():
    """Cached payloads may carry string-typed amounts (pre-P0b writes)."""
    protocol_data = {
        "staked": [{"token": "IAG", "amount": "3858.0"}],
        "v2_balance": "56.93",
    }

    positions, staked_usd, _, _ = await _map_staking_protocol_positions(
        "Mixed", protocol_data, ALL_PRICES, ADA_PRICE
    )

    assert len(positions) == 2
    assert positions[0]["staked_amount"] == 3858.0
    assert positions[1]["staked_amount"] == 56.93
