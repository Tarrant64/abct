"""
Tests for exchange aggregation coverage.

Snapshot totals and the mobile top-holdings/source-breakdown views each carried
their own hardcoded seven-exchange literal, so every exchange registered through
register_exchange() was excluded from the numbers the user sees. The list is now
derived from EXCHANGE_REGISTRY, so those call sites pick up new exchanges
automatically instead of drifting.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from routers.exchanges import EXCHANGE_REGISTRY  # noqa: E402
from services import exchange_names  # noqa: E402
from services.exchange_names import (  # noqa: E402
    LEGACY_EXCHANGE_NAMES,
    get_aggregation_exchange_names,
    get_exchange_display_name,
)
from services.snapshot import SnapshotService  # noqa: E402


def test_includes_every_legacy_exchange():
    names = get_aggregation_exchange_names()
    for legacy in LEGACY_EXCHANGE_NAMES:
        assert legacy in names


def test_includes_every_registered_exchange():
    """The bug: registry exchanges were absent from all three call sites."""
    names = get_aggregation_exchange_names()
    missing = sorted(set(EXCHANGE_REGISTRY) - set(names))
    assert missing == [], f"registered exchanges excluded from totals: {missing}"


def test_covers_more_than_the_old_hardcoded_seven():
    assert len(get_aggregation_exchange_names()) > len(LEGACY_EXCHANGE_NAMES)


def test_names_are_unique_and_sorted():
    names = get_aggregation_exchange_names()
    assert len(names) == len(set(names))
    assert names == sorted(names)


def test_falls_back_to_legacy_when_registry_unavailable(monkeypatch):
    """Aggregation must degrade to the old behaviour, not drop exchange value."""
    import builtins

    real_import = builtins.__import__

    def boom(name, *args, **kwargs):
        if name == "routers.exchanges":
            raise ImportError("simulated circular import")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "routers.exchanges", raising=False)
    monkeypatch.setattr(builtins, "__import__", boom)

    assert get_aggregation_exchange_names() == sorted(LEGACY_EXCHANGE_NAMES)


# --- display names ----------------------------------------------------------

@pytest.mark.parametrize(
    "name,expected",
    [
        ("independentreserve", "Independent Reserve"),
        ("cryptocom", "Crypto.com"),
        ("woox", "WOO X"),
    ],
)
def test_registry_display_names_are_used(name, expected):
    """name.title() would mangle these into 'Independentreserve' etc."""
    if name not in EXCHANGE_REGISTRY:
        pytest.skip(f"{name} not registered in this build")
    assert get_exchange_display_name(name) == expected


def test_display_name_falls_back_to_title_case():
    assert get_exchange_display_name("someexchange") == "Someexchange"


# --- snapshot aggregation behaviour -----------------------------------------

@pytest.mark.asyncio
async def test_missing_cache_entries_contribute_zero(monkeypatch):
    """Every exchange lacking a cache entry must contribute 0, not raise."""
    import database

    async def empty_cache(key, user_id=None):
        return None

    monkeypatch.setattr(database, "get_cache", empty_cache)

    total = await SnapshotService()._get_exchange_value(prices={}, user_id=1)
    assert total == 0.0


@pytest.mark.asyncio
async def test_registry_exchange_value_is_counted(monkeypatch):
    """A registered (non-legacy) exchange must now reach the snapshot total."""
    import database

    registry_only = sorted(set(EXCHANGE_REGISTRY) - set(LEGACY_EXCHANGE_NAMES))
    if not registry_only:
        pytest.skip("no registry-only exchanges in this build")
    target = f"{registry_only[0]}_portfolio"

    async def cache(key, user_id=None):
        return {"total_usd": 1234.56} if key == target else None

    monkeypatch.setattr(database, "get_cache", cache)

    total = await SnapshotService()._get_exchange_value(prices={}, user_id=1)
    assert total == pytest.approx(1234.56)


@pytest.mark.asyncio
async def test_malformed_cache_entry_does_not_break_total(monkeypatch):
    """A cache row without total_usd is skipped rather than counted or raising."""
    import database

    async def cache(key, user_id=None):
        if key == "coinbase_portfolio":
            return {"assets": []}  # no total_usd
        if key == "binance_us_portfolio":
            return {"total_usd": 10.0}
        return None

    monkeypatch.setattr(database, "get_cache", cache)

    total = await SnapshotService()._get_exchange_value(prices={}, user_id=1)
    assert total == pytest.approx(10.0)
