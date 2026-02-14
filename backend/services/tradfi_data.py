"""
TradFi Data Service - Alpha Vantage integration

Provides traditional finance index data: S&P 500, NASDAQ, Dow Jones, BTC ETF.
Requires optional Alpha Vantage API key (free tier: 25 requests/day).
"""

import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from services.api_key_manager import APIKeyManager
from services.http_client import get_client
from database import get_cache, set_cache
from config import CACHE_TTL_COLD

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

SYMBOLS = {
    'SPY': 'S&P 500',
    'QQQ': 'NASDAQ 100',
    'DIA': 'Dow Jones',
    'IBIT': 'BTC ETF (IBIT)'
}


class TradFiDataService(APIKeyManager):
    """Alpha Vantage TradFi data service."""

    def __init__(self):
        super().__init__(api_name='alphavantage', env_var='ALPHAVANTAGE_API_KEY')
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_client("alphavantage", timeout=30.0)
        return self._client

    async def is_configured(self) -> bool:
        """Check if Alpha Vantage API key is available."""
        key = await self.get_api_key()
        return bool(key)

    async def get_daily_data(self, symbol: str) -> Optional[Dict]:
        """
        Get daily OHLCV data for a symbol.
        Returns dict with current price, changes, and history list.
        Cache: 24 hours (COLD) to conserve API budget.
        """
        cache_key = f"tradfi:daily:{symbol}"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        api_key = await self.get_api_key()
        if not api_key:
            return None

        try:
            resp = await self.client.get(ALPHA_VANTAGE_BASE, params={
                'function': 'TIME_SERIES_DAILY',
                'symbol': symbol,
                'apikey': api_key,
                'outputsize': 'compact'  # Last 100 trading days
            })

            if resp.status_code != 200:
                logger.warning(f"Alpha Vantage returned {resp.status_code} for {symbol}")
                return None

            data = resp.json()

            # Check for rate limit / error messages
            if 'Note' in data or 'Information' in data:
                logger.warning(f"Alpha Vantage rate limited: {data.get('Note', data.get('Information', ''))}")
                return None

            time_series = data.get('Time Series (Daily)', {})
            if not time_series:
                return None

            # Parse into sorted list (newest first)
            history = []
            for date_str, values in sorted(time_series.items(), reverse=True):
                history.append({
                    'date': date_str,
                    'open': float(values.get('1. open', 0)),
                    'high': float(values.get('2. high', 0)),
                    'low': float(values.get('3. low', 0)),
                    'close': float(values.get('4. close', 0)),
                    'volume': int(float(values.get('5. volume', 0)))
                })

            if not history:
                return None

            current_price = history[0]['close']

            # Calculate changes
            change_1d = self._calc_change(history, 1)
            change_7d = self._calc_change(history, 5)  # ~5 trading days
            change_30d = self._calc_change(history, 22)  # ~22 trading days
            change_ytd = self._calc_ytd_change(history)

            result = {
                'symbol': symbol,
                'name': SYMBOLS.get(symbol, symbol),
                'price': current_price,
                'change_1d': change_1d,
                'change_7d': change_7d,
                'change_30d': change_30d,
                'change_ytd': change_ytd,
                'history': history[:100],  # Keep last 100 days
                'timestamp': int(time.time())
            }

            await set_cache(cache_key, result, CACHE_TTL_COLD)
            return result

        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage data for {symbol}: {e}")
            return None

    def _calc_change(self, history: List[Dict], days_ago: int) -> Optional[float]:
        """Calculate % change from N trading days ago."""
        if len(history) <= days_ago:
            return None
        current = history[0]['close']
        past = history[days_ago]['close']
        if past <= 0:
            return None
        return ((current - past) / past) * 100

    def _calc_ytd_change(self, history: List[Dict]) -> Optional[float]:
        """Calculate year-to-date % change."""
        if not history:
            return None
        current_year = datetime.now().year
        # Find first trading day of current year
        for entry in reversed(history):
            if entry['date'].startswith(str(current_year)):
                past = entry['close']
                if past > 0:
                    return ((history[0]['close'] - past) / past) * 100
                break
        return None

    async def get_all_indices(self) -> Dict:
        """
        Get data for all TradFi indices.
        Returns dict: symbol -> {name, price, change_1d, change_7d, change_30d, change_ytd}
        """
        cache_key = "tradfi:all_indices"
        cached = await get_cache(cache_key)
        if cached:
            return cached

        import asyncio
        results = {}

        # Fetch sequentially to avoid hitting rate limits
        # Alpha Vantage free tier: 25 requests/day, 5/min
        for symbol in SYMBOLS:
            data = await self.get_daily_data(symbol)
            if data:
                results[symbol] = {
                    'name': data['name'],
                    'price': data['price'],
                    'change_1d': data['change_1d'],
                    'change_7d': data['change_7d'],
                    'change_30d': data['change_30d'],
                    'change_ytd': data['change_ytd']
                }
            # Small delay between requests
            await asyncio.sleep(0.5)

        if results:
            await set_cache(cache_key, results, CACHE_TTL_COLD)

        return results

    async def get_btc_spy_correlation(self, days: int = 30) -> Optional[float]:
        """Calculate Pearson correlation between BTC and S&P 500 daily returns."""
        cache_key = f"tradfi:correlation:btc_spy:{days}"
        cached = await get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            # Get S&P 500 data
            spy_data = await self.get_daily_data('SPY')
            if not spy_data or len(spy_data.get('history', [])) < days:
                return None

            # Get BTC data from our pricing service
            from services.pricing import pricing_service
            btc_history = await pricing_service.get_historical_prices(['BTC'], days)
            btc_prices = btc_history.get('BTC', [])
            if not btc_prices or len(btc_prices) < days // 2:
                return None

            # Build date -> price maps
            spy_prices = {h['date']: h['close'] for h in spy_data['history']}
            btc_price_map = {}
            for p in btc_prices:
                date_str = p.get('date', '')
                if ' ' in date_str:
                    date_str = date_str.split(' ')[0]
                btc_price_map[date_str] = p.get('price', 0)

            # Find overlapping dates and compute daily returns
            common_dates = sorted(set(spy_prices.keys()) & set(btc_price_map.keys()))
            if len(common_dates) < 5:
                return None

            # Take only last N dates
            common_dates = common_dates[-days:]

            spy_returns = []
            btc_returns = []
            for i in range(1, len(common_dates)):
                prev_date = common_dates[i - 1]
                curr_date = common_dates[i]

                spy_prev = spy_prices.get(prev_date, 0)
                spy_curr = spy_prices.get(curr_date, 0)
                btc_prev = btc_price_map.get(prev_date, 0)
                btc_curr = btc_price_map.get(curr_date, 0)

                if spy_prev > 0 and btc_prev > 0:
                    spy_returns.append((spy_curr - spy_prev) / spy_prev)
                    btc_returns.append((btc_curr - btc_prev) / btc_prev)

            if len(spy_returns) < 5:
                return None

            # Pearson correlation
            n = len(spy_returns)
            mean_spy = sum(spy_returns) / n
            mean_btc = sum(btc_returns) / n

            cov = sum((s - mean_spy) * (b - mean_btc) for s, b in zip(spy_returns, btc_returns)) / n
            std_spy = (sum((s - mean_spy) ** 2 for s in spy_returns) / n) ** 0.5
            std_btc = (sum((b - mean_btc) ** 2 for b in btc_returns) / n) ** 0.5

            if std_spy == 0 or std_btc == 0:
                return 0.0

            correlation = cov / (std_spy * std_btc)
            correlation = max(-1.0, min(1.0, correlation))

            await set_cache(cache_key, correlation, CACHE_TTL_COLD)
            return round(correlation, 4)

        except Exception as e:
            logger.error(f"Error computing BTC/SPY correlation: {e}")
            return None


tradfi_service = TradFiDataService()
