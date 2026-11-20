"""
LogoKit - web-frontend-only logo provider (major coins).

LogoKit's terms (docs: logokit.com/terms 2.2-2.4) require HOTLINKING logos via
the provided img.logokit.com URLs; scraping/caching/proxying is Enterprise-only.
It also looks logos up by SYMBOL only (no policy id), so it must never be used
for obscure tokens (ticker collisions give wrong logos).

Therefore this service does NOT build or fetch logo URLs for API responses.
It only (a) resolves the publishable key (DB first, env fallback, same as every
other service) and (b) owns the MAJOR_SYMBOLS allowlist. The web frontend
receives both via the session-authenticated GET /api/config/public and builds
img.logokit.com URLs in the browser. Nothing is stored or proxied server-side,
and no /api/mobile/* payload contains a LogoKit URL.
"""

import logging
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

# Majors: chain-native coins ABCT tracks plus large-cap / mainstream stablecoin
# assets. Deliberately excludes Cardano native tokens (symbol collisions).
MAJOR_SYMBOLS = frozenset({
    # chain natives (match frontend chain list)
    'ADA', 'BTC', 'ETH', 'SOL', 'MATIC', 'POL', 'ALGO', 'BNB', 'ARB', 'AVAX', 'TRX',
    'XRP', 'HBAR', 'EGLD', 'SUI', 'APT', 'FIL', 'LTC', 'DOGE', 'ZEC', 'XTZ', 'STX',
    'VET', 'ATOM', 'NEAR', 'ICP', 'TON', 'DOT', 'KSM', 'XLM', 'KAS', 'OSMO', 'TIA',
    'INJ', 'DYDX', 'SEI', 'AKT', 'KLAY', 'KAIA', 'ERG', 'IOTA', 'WAVES', 'MINA',
    'ZIL', 'OP', 'ZK', 'LINEA', 'SCR', 'FTM', 'CRO', 'GNO', 'GLMR', 'XMR', 'SCRT',
    # large caps / mainstream
    'LINK', 'UNI', 'AAVE', 'MKR', 'LDO', 'RNDR', 'GRT', 'BCH', 'ETC', 'SHIB',
    'WBTC', 'WETH', 'STETH',
    # stablecoins
    'USDC', 'USDT', 'DAI', 'USDE', 'FDUSD', 'PYUSD',
})


def is_major(symbol) -> bool:
    return isinstance(symbol, str) and symbol.strip().upper() in MAJOR_SYMBOLS


class LogoKitService(APIKeyManager):
    """Key resolver + majors allowlist for the web-only LogoKit hotlinks."""

    def __init__(self):
        super().__init__(api_name='logokit', env_var='LOGOKIT_API_KEY')

    @property
    def majors(self) -> List[str]:
        return sorted(MAJOR_SYMBOLS)

    async def get_public_token(self) -> str:
        """Publishable token (DB first, then env). Empty string when unset."""
        return (await self.get_api_key()) or ''


# Singleton instance
logokit_service = LogoKitService()
