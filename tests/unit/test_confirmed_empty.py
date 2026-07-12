"""
Exit-vs-timeout matrix (P3a item 2).

A protocol that POSITIVELY answers "no positions" (confirmed_empty) is a
legitimate shrink: it must not be backfilled from stale data by the
aggregator, and the route guard must accept the smaller result — otherwise a
genuine protocol exit can never display. A failed/timed-out fetch (None)
keeps today's behavior: stale backfill and guard refusal.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.defi import DeFiService  # noqa: E402

ADDRESS = "addr1qtest"

LIQWID_DATA = {
    'protocol': 'Liqwid', 'address': ADDRESS,
    'positions': [{'staked_lq': 2089.17}],
    'total_staked_lq': 2089.17, 'position_count': 1,
}

LIQWID_CONFIRMED_EMPTY = {
    'protocol': 'Liqwid', 'address': ADDRESS,
    'positions': [], 'total_staked_lq': 0, 'position_count': 0,
    'confirmed_empty': True,
}

PREVIOUS_RESULT = {
    'address': ADDRESS,
    'protocols': {
        'Liqwid': {
            'staked': [{'token': 'LQ', 'amount': 2089.17}],
            'total_positions': 1,
        },
    },
    'total_positions': 1,
}


@pytest.fixture
def service(monkeypatch):
    """Aggregator with every fetcher stubbed to None unless overridden."""
    svc = DeFiService()

    async def none_fetcher(address, **kwargs):
        return None

    for method in [
        "get_indigo_staking", "get_strike_staking", "get_liqwid_staking",
        "get_iagon_staking", "get_surf_lending_positions",
        "get_indigo_cdps", "get_indigo_stability_pool",
        "get_strike_v2_positions",
    ]:
        monkeypatch.setattr(svc, method, none_fetcher)

    async def no_logo(token):
        return None

    monkeypatch.setattr(svc, "_get_token_logo_url", no_logo)

    async def no_rewards(address, **kwargs):
        return None

    monkeypatch.setattr(svc, "get_liqwid_pending_rewards", no_rewards)
    return svc


def set_fetcher(monkeypatch, svc, name, value):
    async def fetcher(address, **kwargs):
        return value

    monkeypatch.setattr(svc, name, fetcher)


async def test_confirmed_empty_is_not_backfilled(service, monkeypatch):
    """Liqwid positively exited: stale data must NOT resurrect it."""
    set_fetcher(monkeypatch, service, "get_liqwid_staking", LIQWID_CONFIRMED_EMPTY)

    result = await service.get_all_staking_positions(
        ADDRESS, previous_result=PREVIOUS_RESULT
    )

    assert 'Liqwid' not in result['protocols']
    assert result['confirmed_empty'] == ['Liqwid']


async def test_timeout_is_backfilled_from_previous(service):
    """Liqwid fetch failed: last-good data still backfills, flagged stale."""
    result = await service.get_all_staking_positions(
        ADDRESS, previous_result=PREVIOUS_RESULT
    )

    assert 'Liqwid' in result['protocols']
    assert result['protocols']['Liqwid']['stale'] is True
    assert result['confirmed_empty'] == []


async def test_liqwid_data_still_assembles(service, monkeypatch):
    set_fetcher(monkeypatch, service, "get_liqwid_staking", LIQWID_DATA)

    result = await service.get_all_staking_positions(ADDRESS)

    assert result['protocols']['Liqwid']['staked'][0]['amount'] == pytest.approx(2089.17)
    assert result['confirmed_empty'] == []


async def test_strike_needs_both_v1_and_v2_confirmations(service, monkeypatch):
    """Strike is confirmed empty only when BOTH the v1 scan and the V2 API
    positively answered — one confirmation plus one failure stays open."""
    set_fetcher(monkeypatch, service, "get_strike_staking", {
        'protocol': 'Strike', 'address': ADDRESS, 'positions': [],
        'total_staked_strike': 0, 'position_count': 0, 'confirmed_empty': True,
    })
    # get_strike_v2_positions stays None (failure)

    result = await service.get_all_staking_positions(ADDRESS)

    assert 'Strike' not in result['confirmed_empty']

    set_fetcher(monkeypatch, service, "get_strike_v2_positions", {
        'account_id': None, 'account_ids': [], 'v2_balance': 0.0,
        'vault_positions': [], 'total_vault_ada': 0.0, 'confirmed_empty': True,
    })

    result = await service.get_all_staking_positions(ADDRESS)

    assert 'Strike' in result['confirmed_empty']
    assert 'Strike' not in result['protocols']


async def test_indigo_needs_staking_and_cdps_confirmations(service, monkeypatch):
    indigo_ce = {
        'protocol': 'Indigo', 'address': ADDRESS, 'positions': [],
        'total_staked_indy': 0, 'position_count': 0, 'confirmed_empty': True,
    }
    set_fetcher(monkeypatch, service, "get_indigo_staking", indigo_ce)

    result = await service.get_all_staking_positions(ADDRESS)
    assert 'Indigo' not in result['confirmed_empty']  # CDPs still unknown

    set_fetcher(monkeypatch, service, "get_indigo_cdps", {
        'protocol': 'Indigo', 'address': ADDRESS, 'cdps': [],
        'total_collateral_ada': 0, 'cdp_count': 0, 'confirmed_empty': True,
    })

    result = await service.get_all_staking_positions(ADDRESS)
    assert 'Indigo' in result['confirmed_empty']
