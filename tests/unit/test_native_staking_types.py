"""
Regression tests for the native-staking TypeError (P0b).

get_stake_account_info used to return controlled_ada/rewards_ada/
withdrawable_ada as strings; the mobile staking endpoint compared
controlled_ada > 0 and raised TypeError for every wallet, so native
ADA delegation rows never rendered. The derived *_ada fields are now
numeric at the source, and the consumer coerces defensively.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.cardano as cardano_module  # noqa: E402
from routers.mobile import _as_float  # noqa: E402

STAKE_ADDRESS = "stake1u9urqtestonly"

# Real Blockfrost /accounts/{stake_address} shape — amounts are strings
BLOCKFROST_ACCOUNT_FIXTURE = {
    "stake_address": STAKE_ADDRESS,
    "active": True,
    "active_epoch": 412,
    "controlled_amount": "10432187654",
    "rewards_sum": "312876543",
    "withdrawals_sum": "250000000",
    "reserves_sum": "0",
    "treasury_sum": "0",
    "withdrawable_amount": "62876543",
    "pool_id": "pool1testpoolid",
    "drep_id": None,
}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


@pytest.fixture
def service(monkeypatch):
    svc = cardano_module.CardanoService()

    async def fake_headers():
        return {}

    monkeypatch.setattr(svc, "_get_blockfrost_headers", fake_headers)
    return svc


async def test_stake_account_ada_fields_are_numeric(service, monkeypatch):
    async def fake_fetch(path, **kwargs):
        return FakeResponse(json_data=BLOCKFROST_ACCOUNT_FIXTURE)

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    info = await service.get_stake_account_info(STAKE_ADDRESS)

    assert info is not None
    assert isinstance(info["controlled_ada"], float)
    assert info["controlled_ada"] == pytest.approx(10432.187654)
    assert isinstance(info["withdrawable_ada"], float)
    assert info["withdrawable_ada"] == pytest.approx(62.876543)
    assert isinstance(info["rewards_ada"], float)
    # The exact comparison that used to raise TypeError:
    assert info["controlled_ada"] > 0
    # Raw lovelace passthrough fields stay strings (Blockfrost contract)
    assert info["controlled_amount"] == "10432187654"


async def test_stake_account_404_returns_numeric_zeros(service, monkeypatch):
    async def fake_fetch(path, **kwargs):
        return FakeResponse(status_code=404, json_data=None)

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    info = await service.get_stake_account_info(STAKE_ADDRESS)

    assert info is not None
    assert info["active"] is False
    assert info["controlled_ada"] == 0.0
    assert info["withdrawable_ada"] == 0.0
    assert not info["controlled_ada"] > 0  # comparison must not raise


def test_as_float_coerces_legacy_string_values():
    # Cached payloads from the pre-fix code carry string-typed amounts
    assert _as_float("10432.187654") == pytest.approx(10432.187654)
    assert _as_float(7.5) == 7.5
    assert _as_float(42) == 42.0
    assert _as_float(None) == 0.0
    assert _as_float("not-a-number") == 0.0
    assert _as_float("", default=1.5) == 1.5
