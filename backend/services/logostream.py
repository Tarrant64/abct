"""
Logostream - web-frontend-only fallback logo provider (major coins).

Documented endpoint: https://api.logostream.dev/cryptos/{symbol}?key=KEY
Logostream's terms (logostream.dev/terms 2.3/2.4) allow only end-user (browser)
caching on paid plans and forbid any backend/CDN/proxy storage and bulk
enumeration below Enterprise; the Community plan allows no caching at all and
counts every request against a 20K/month quota. So this service never fetches,
caches or proxies logos. It only resolves the key (DB first, env fallback);
the web frontend hotlinks the URL in the browser, for majors only, and only
after the LogoKit image fails to load.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager

LOGOSTREAM_CRYPTO_URL = "https://api.logostream.dev/cryptos/{symbol}"


class LogostreamService(APIKeyManager):
    """Key resolver for the browser-side Logostream fallback."""

    def __init__(self):
        super().__init__(api_name='logostream', env_var='LOGOSTREAM_API_KEY')

    async def is_configured(self) -> bool:
        return bool(await self.get_api_key())

    async def get_public_key(self) -> str:
        return (await self.get_api_key()) or ''


# Singleton instance
logostream_service = LogostreamService()
