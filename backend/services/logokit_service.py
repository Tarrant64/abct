"""
LogoKit Service - Professional logo API integration

Provides methods to generate logo URLs for cryptocurrencies, tokens,
and blockchain assets using the LogoKit API.
"""

from config import LOGOKIT_API_KEY, LOGOKIT_BASE_URL
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class LogoKitService:
    """Service for generating LogoKit logo URLs."""

    def __init__(self):
        self.api_key = LOGOKIT_API_KEY
        self.base_url = LOGOKIT_BASE_URL

    def get_crypto_logo_url(
        self,
        symbol: str,
        size: Optional[int] = None,
        fallback_404: bool = False
    ) -> str:
        """
        Get LogoKit URL for cryptocurrency logo.

        Args:
            symbol: Crypto symbol (e.g., 'BTC', 'ETH', 'ADA')
            size: Optional size parameter (e.g., 64, 128, 256)
            fallback_404: If True, return 404 instead of monogram fallback

        Returns:
            Full LogoKit CDN URL

        Examples:
            >>> service.get_crypto_logo_url('BTC')
            'https://img.logokit.com/crypto/BTC?token=pk_...'

            >>> service.get_crypto_logo_url('ETH', size=128)
            'https://img.logokit.com/crypto/ETH?token=pk_...&size=128'
        """
        # Normalize symbol to uppercase
        symbol = symbol.upper()

        # Build URL
        url = f"{self.base_url}/crypto/{symbol}?token={self.api_key}"

        # Add optional parameters
        if size:
            url += f"&size={size}"

        if fallback_404:
            url += "&fallback=404"

        return url

    def get_token_logo_url(
        self,
        symbol: str,
        size: Optional[int] = None,
        fallback_404: bool = False
    ) -> str:
        """
        Get LogoKit URL for token logo (alias for get_crypto_logo_url).

        The /token/ and /crypto/ endpoints are interchangeable.
        """
        return self.get_crypto_logo_url(symbol, size, fallback_404)

    def get_blockchain_logo_url(self, blockchain: str, size: Optional[int] = None) -> str:
        """
        Get logo URL for a blockchain's native coin.

        Args:
            blockchain: Blockchain name (cardano, bitcoin, ethereum, etc.)
            size: Optional size parameter

        Returns:
            LogoKit CDN URL for the blockchain's native token
        """
        # Map blockchain names to their native coin symbols
        blockchain_symbols = {
            'cardano': 'ADA',
            'bitcoin': 'BTC',
            'ethereum': 'ETH',
            'solana': 'SOL',
            'polygon': 'MATIC',  # POL is rebranded MATIC
            'base': 'ETH'  # Base uses ETH
        }

        symbol = blockchain_symbols.get(blockchain.lower())
        if not symbol:
            logger.warning(f"Unknown blockchain: {blockchain}")
            return ""

        return self.get_crypto_logo_url(symbol, size)

    def get_logo_urls_batch(self, symbols: list[str], size: Optional[int] = None) -> Dict[str, str]:
        """
        Get logo URLs for multiple symbols at once.

        Args:
            symbols: List of crypto symbols
            size: Optional size parameter

        Returns:
            Dict mapping symbol to logo URL
        """
        return {
            symbol: self.get_crypto_logo_url(symbol, size)
            for symbol in symbols
        }


# Singleton instance
logokit_service = LogoKitService()
