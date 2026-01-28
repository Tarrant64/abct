"""
TapTools Wallet Service - Portfolio verification and DeFi position tracking.

Uses TapTools API to:
- Get wallet portfolio positions (ADA + tokens)
- Track DeFi-locked assets (LP positions, collateral, etc.)
- Verify balances across stake keys
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TAPTOOLS_API_KEY, TAPTOOLS_BASE_URL

# Import API tracker
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'middleware'))
from api_tracker import get_taptools_client

logger = logging.getLogger(__name__)


class TapToolsWalletService:
    """Service for TapTools wallet portfolio data."""

    def __init__(self):
        self.api_base = TAPTOOLS_BASE_URL
        self.headers = {"x-api-key": TAPTOOLS_API_KEY} if TAPTOOLS_API_KEY else {}
        self._cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    def is_configured(self) -> bool:
        """Check if TapTools API key is configured."""
        return bool(TAPTOOLS_API_KEY)

    async def get_wallet_portfolio(self, address: str) -> Optional[Dict]:
        """
        Get wallet portfolio positions from TapTools.

        Returns full portfolio for the stake key associated with this address,
        including DeFi positions.

        Args:
            address: Cardano address (bech32 format)

        Returns:
            {
                'ada_balance': float,  # Total ADA (liquid + DeFi)
                'ada_value': float,    # Value in ADA terms
                'liquid_value': float, # Liquid value in ADA
                'num_tokens': int,
                'num_nfts': int,
                'positions': [...],    # Token positions
                'source': 'TapTools'
            }
        """
        if not self.is_configured():
            logger.debug("TapTools API not configured")
            return None

        # Check cache
        cache_key = f"portfolio_{address}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now() - cached['timestamp'] < self._cache_ttl:
                return cached['data']

        try:
            async with get_taptools_client(headers=self.headers, timeout=30) as client:
                response = await client.get(
                    f"{self.api_base}/wallet/portfolio/positions",
                    params={"address": address}
                )

                if response.status_code == 200:
                    data = response.json()

                    result = {
                        'ada_balance': data.get('adaBalance', 0),
                        'ada_value': data.get('adaValue', 0),
                        'liquid_value': data.get('liquidValue', 0),
                        'num_tokens': data.get('numFTs', 0),
                        'num_nfts': data.get('numNFTs', 0),
                        'positions': data.get('positionsFt', []),
                        'nft_positions': data.get('positionsNft', []),
                        'source': 'TapTools'
                    }

                    # Cache result
                    self._cache[cache_key] = {
                        'data': result,
                        'timestamp': datetime.now()
                    }

                    return result
                else:
                    logger.warning(f"TapTools portfolio request failed: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching TapTools portfolio: {e}")
            return None

    async def get_stake_key_balance(self, address: str) -> Optional[Dict]:
        """
        Get balance summary for stake key.

        TapTools returns full stake key balance when queried with any address.
        This gives the total ADA across all addresses under the stake key.
        """
        portfolio = await self.get_wallet_portfolio(address)
        if not portfolio:
            return None

        # Find ADA position
        ada_position = None
        for pos in portfolio.get('positions', []):
            if pos.get('ticker') == 'ADA':
                ada_position = pos
                break

        return {
            'total_ada': portfolio['ada_balance'],
            'liquid_ada': ada_position.get('liquidBalance', portfolio['ada_balance']) if ada_position else portfolio['ada_balance'],
            'ada_value_usd': None,  # Would need price conversion
            'total_tokens': portfolio['num_tokens'],
            'total_nfts': portfolio['num_nfts'],
            'source': 'TapTools'
        }

    async def get_defi_positions(self, address: str) -> Optional[List[Dict]]:
        """
        Extract DeFi-related positions from portfolio.

        Returns LP tokens, receipt tokens, and other DeFi positions.
        """
        portfolio = await self.get_wallet_portfolio(address)
        if not portfolio:
            return None

        defi_positions = []

        # Known DeFi protocol tickers/patterns
        defi_indicators = [
            'LP', 'lp', 'q', 'i',  # LP tokens, qTokens, iAssets
            'SNEK', 'MIN', 'SUNDAE', 'WRT',  # DEX governance
            'LQ', 'LENFI', 'INDY',  # Lending governance
            'DJED', 'SHEN', 'iUSD', 'iBTC',  # Stablecoins/synthetics
        ]

        for pos in portfolio.get('positions', []):
            ticker = pos.get('ticker', '')
            unit = pos.get('unit', '')

            # Skip ADA
            if ticker == 'ADA':
                continue

            # Check if likely a DeFi position
            is_defi = any(ind in ticker for ind in defi_indicators)

            if is_defi or pos.get('adaValue', 0) > 10:  # Include significant positions
                defi_positions.append({
                    'ticker': ticker,
                    'unit': unit,
                    'balance': pos.get('balance', 0),
                    'liquid_balance': pos.get('liquidBalance', 0),
                    'ada_value': pos.get('adaValue', 0),
                    'price': pos.get('price', 0),
                    'change_24h': pos.get('24h', 0),
                    'change_7d': pos.get('7d', 0),
                })

        return defi_positions

    async def compare_with_local(self, address: str, local_ada_balance: float) -> Dict:
        """
        Compare local balance with TapTools data.

        Returns discrepancy info if balances don't match.
        """
        taptools_data = await self.get_stake_key_balance(address)
        if not taptools_data:
            return {
                'status': 'unavailable',
                'message': 'TapTools data not available'
            }

        taptools_ada = taptools_data['total_ada']
        difference = taptools_ada - local_ada_balance
        pct_diff = (difference / local_ada_balance * 100) if local_ada_balance > 0 else 0

        if abs(pct_diff) < 1:  # Within 1%
            status = 'match'
        elif abs(pct_diff) < 10:  # Within 10%
            status = 'minor_discrepancy'
        else:
            status = 'significant_discrepancy'

        return {
            'status': status,
            'local_ada': local_ada_balance,
            'taptools_ada': taptools_ada,
            'difference': difference,
            'pct_difference': pct_diff,
            'note': 'TapTools returns full stake key balance including DeFi positions'
        }

    def clear_cache(self):
        """Clear the portfolio cache."""
        self._cache.clear()


# Singleton instance
taptools_wallet_service = TapToolsWalletService()
