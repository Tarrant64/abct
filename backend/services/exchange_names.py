"""Single source of truth for which exchanges participate in portfolio aggregation.

Snapshot totals and the mobile top-holdings/source-breakdown views each used to
carry their own copy of the same seven-exchange literal, so every exchange added
through register_exchange() was silently excluded from the numbers the user sees.
Deriving the list from EXCHANGE_REGISTRY keeps those call sites correct as new
exchanges are registered.
"""

import logging

logger = logging.getLogger(__name__)

# Exchanges wired up directly in routers/exchanges.py rather than through
# register_exchange(), so they never appear in EXCHANGE_REGISTRY.
LEGACY_EXCHANGE_NAMES = (
    "coinbase",
    "binance",
    "binance_us",
    "okx",
    "bitget",
    "gate",
    "kucoin",
)


def get_aggregation_exchange_names() -> list:
    """Every exchange whose '<name>_portfolio' cache counts toward totals.

    routers.exchanges is imported lazily: it pulls in every exchange service
    module, and this helper is used from both a router and a service that runs
    standalone from migration scripts. If that import fails the legacy names are
    still returned, so aggregation degrades to the old behaviour rather than
    dropping exchange value entirely.
    """
    names = set(LEGACY_EXCHANGE_NAMES)
    try:
        from routers.exchanges import EXCHANGE_REGISTRY
        names.update(EXCHANGE_REGISTRY)
    except Exception as e:
        logger.warning(
            "Could not load EXCHANGE_REGISTRY, falling back to legacy exchange "
            "list; registry-based exchanges will be missing from totals: %s", e
        )
    return sorted(names)


def get_exchange_display_name(name: str) -> str:
    """Human-readable label for a registry exchange.

    Registered exchanges carry their own display name ('Crypto.com', 'WOO X',
    'Independent Reserve'), which name.title() would mangle. Falls back to
    title-casing for anything not in the registry.
    """
    try:
        from routers.exchanges import EXCHANGE_REGISTRY
        entry = EXCHANGE_REGISTRY.get(name) or {}
        display = entry.get("display_name")
        if display:
            return display
    except Exception:
        pass
    return name.title()
