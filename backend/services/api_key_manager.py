"""
API Key Manager

Provides dynamic API key loading with caching for all services.
Checks database first (for runtime updates via UI), then falls back to environment variables.
"""

import os
import sys
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

# Import database functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_api_key, get_api_setting

logger = logging.getLogger(__name__)


class APIKeyManager:
    """
    Manages API key loading with caching.

    Usage:
        class MyService(APIKeyManager):
            def __init__(self):
                super().__init__(api_name='myapi', env_var='MYAPI_API_KEY')

            async def make_request(self):
                key = await self.get_api_key()
                # use key for request
    """

    def __init__(self, api_name: str, env_var: str, cache_ttl_seconds: int = 60):
        """
        Initialize API key manager.

        Args:
            api_name: Name of API in database (e.g., 'taptools', 'blockfrost')
            env_var: Environment variable name (e.g., 'TAPTOOLS_API_KEY')
            cache_ttl_seconds: How long to cache keys (default: 60 seconds)
        """
        self.api_name = api_name
        self.env_var = env_var
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)

        # Cache for API key
        self._cached_key: Optional[str] = None
        self._key_cache_time: Optional[datetime] = None

        # Cache for API secret (for exchanges)
        self._cached_secret: Optional[str] = None
        self._secret_cache_time: Optional[datetime] = None

        # Cache for API passphrase (for some exchanges)
        self._cached_passphrase: Optional[str] = None
        self._passphrase_cache_time: Optional[datetime] = None

    async def get_api_key(self, user_id: int = 1) -> str:
        """
        Get API key from database or environment variable.

        Checks in this order:
        1. Cache (if still valid)
        2. Database (allows runtime updates via UI)
        3. Environment variable (fallback)

        Args:
            user_id: User ID to fetch key for (default: 1 for admin/system)

        Returns:
            API key string or empty string if not configured
        """
        now = datetime.utcnow()

        # Check cache first
        if self._cached_key is not None and self._key_cache_time:
            if now - self._key_cache_time < self.cache_ttl:
                return self._cached_key

        # Try database
        try:
            db_key = await get_api_key(self.api_name, user_id=user_id)
            if db_key:
                self._cached_key = db_key
                self._key_cache_time = now
                logger.debug(f"Loaded API key for {self.api_name} from database")
                return db_key
        except Exception as e:
            logger.debug(f"Could not fetch API key for {self.api_name} from database: {e}")

        # Fall back to environment variable
        env_key = os.getenv(self.env_var, '')
        if env_key:
            self._cached_key = env_key
            self._key_cache_time = now
            logger.debug(f"Loaded API key for {self.api_name} from environment")
            return env_key

        # No key found
        self._cached_key = ''
        self._key_cache_time = now
        return ''

    async def get_api_credentials(self, user_id: int = 1) -> Dict[str, str]:
        """
        Get full API credentials (key, secret, passphrase) for exchange APIs.

        Returns:
            Dict with 'api_key', 'api_secret', 'api_passphrase' (may be empty strings)
        """
        now = datetime.utcnow()

        # Check if all credentials are cached and valid
        if (self._cached_key is not None and self._key_cache_time and
            now - self._key_cache_time < self.cache_ttl):
            return {
                'api_key': self._cached_key or '',
                'api_secret': self._cached_secret or '',
                'api_passphrase': self._cached_passphrase or ''
            }

        # Fetch from database
        try:
            setting = await get_api_setting(self.api_name, user_id=user_id)
            if setting and setting.get('enabled'):
                self._cached_key = setting.get('api_key', '')
                self._cached_secret = setting.get('api_secret', '')
                self._cached_passphrase = setting.get('api_passphrase', '')
                self._key_cache_time = now
                self._secret_cache_time = now
                self._passphrase_cache_time = now

                return {
                    'api_key': self._cached_key or '',
                    'api_secret': self._cached_secret or '',
                    'api_passphrase': self._cached_passphrase or ''
                }
        except Exception as e:
            logger.debug(f"Could not fetch credentials for {self.api_name} from database: {e}")

        # Fall back to environment (key only, secrets usually not in env)
        env_key = os.getenv(self.env_var, '')
        self._cached_key = env_key
        self._cached_secret = ''
        self._cached_passphrase = ''
        self._key_cache_time = now

        return {
            'api_key': env_key,
            'api_secret': '',
            'api_passphrase': ''
        }

    async def is_configured(self, user_id: int = 1) -> bool:
        """Check if API key is configured."""
        key = await self.get_api_key(user_id)
        return bool(key)

    def clear_cache(self):
        """Clear the API key cache (forces reload on next access)."""
        self._cached_key = None
        self._key_cache_time = None
        self._cached_secret = None
        self._secret_cache_time = None
        self._cached_passphrase = None
        self._passphrase_cache_time = None
        logger.info(f"Cleared API key cache for {self.api_name}")
