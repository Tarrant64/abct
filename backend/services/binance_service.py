"""
Binance Service - Fetches portfolio data from Binance.com using REST API.
Uses HMAC SHA256 authentication.
"""

import httpx
import logging
import time
import hmac
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlencode
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BINANCE_API_KEY, BINANCE_API_SECRET
from services.http_client import get_client

logger = logging.getLogger(__name__)

BINANCE_API_BASE = "https://api.binance.com"


class BinanceService:
    """Service for fetching portfolio data from Binance.com."""

    def __init__(self):
        self.api_key = BINANCE_API_KEY
        self.api_secret = BINANCE_API_SECRET

    def is_configured(self) -> bool:
        """Check if Binance API is properly configured."""
        return bool(self.api_key and self.api_secret)

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for Binance API."""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _make_request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the Binance API."""
        if not self.is_configured():
            logger.warning("Binance API not configured")
            return None

        try:
            if params is None:
                params = {}

            # Add timestamp
            params['timestamp'] = int(time.time() * 1000)

            # Create query string and signature
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            query_string += f"&signature={signature}"

            url = f"{BINANCE_API_BASE}{endpoint}?{query_string}"
            headers = {
                "X-MBX-APIKEY": self.api_key
            }

            client = get_client("binance", timeout=30.0)
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Binance API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Binance API error: {e}")
            return None

    async def get_trade_history(self, user_id: int = None, limit: int = 500) -> List[Dict]:
        """Get trade history from Binance for assets with balance."""
        if not self.is_configured():
            return []

        try:
            # Get account balances to find assets with holdings
            data = await self._make_request("/api/v3/account")
            if not data:
                return []

            # Find assets with non-zero balance (top 20 by total balance)
            assets_with_balance = []
            for balance in data.get("balances", []):
                total = float(balance.get("free", 0)) + float(balance.get("locked", 0))
                if total > 0 and balance["asset"] not in ("USD", "USDT", "USDC", "BUSD"):
                    assets_with_balance.append((balance["asset"], total))

            assets_with_balance.sort(key=lambda x: x[1], reverse=True)
            assets_with_balance = assets_with_balance[:20]

            all_trades = []
            for asset, _ in assets_with_balance:
                # Try USDT pair first, then BUSD, then USD
                for quote in ("USDT", "BUSD", "USD"):
                    symbol = f"{asset}{quote}"
                    trades = await self._make_request("/api/v3/myTrades", {"symbol": symbol, "limit": 50})
                    if trades and isinstance(trades, list) and len(trades) > 0:
                        for trade in trades:
                            all_trades.append({
                                "exchange": "binance",
                                "time": self._format_timestamp(trade.get("time", 0)),
                                "side": "BUY" if trade.get("isBuyer") else "SELL",
                                "amount": float(trade.get("qty", 0)),
                                "token": asset,
                                "quote_amount": float(trade.get("quoteQty", 0)),
                                "quote_token": quote,
                                "price": float(trade.get("price", 0)),
                                "fee": float(trade.get("commission", 0)),
                                "fee_token": trade.get("commissionAsset", ""),
                                "order_id": str(trade.get("orderId", ""))
                            })
                        break  # Found trades for this asset, skip other quote currencies

            # Sort by time descending
            all_trades.sort(key=lambda x: x["time"], reverse=True)
            return all_trades[:limit]

        except Exception as e:
            logger.error(f"Error fetching Binance trade history: {e}")
            return []

    @staticmethod
    def _format_timestamp(ms_timestamp: int) -> str:
        """Convert millisecond timestamp to ISO format."""
        from datetime import datetime, timezone
        if not ms_timestamp:
            return ""
        return datetime.fromtimestamp(ms_timestamp / 1000, tz=timezone.utc).isoformat()

    async def get_account_balances(self, user_id: int = None) -> Dict:
        """Get account balances from Binance."""
        data = await self._make_request("/api/v3/account")

        if not data:
            return {
                "exchange": "binance",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            }

        # Extract non-zero balances
        assets = []
        for balance in data.get("balances", []):
            free = float(balance.get("free", 0))
            locked = float(balance.get("locked", 0))
            total = free + locked

            if total > 0:
                assets.append({
                    "currency": balance["asset"],
                    "name": balance["asset"],
                    "balance": total,
                    "available_balance": free,
                    "hold_balance": locked,
                    "needs_price": True
                })

        return {
            "exchange": "binance",
            "configured": True,
            "assets": assets,
            "total_usd": 0,  # Will be calculated by router
            "asset_count": len(assets)
        }

    # ── Full transaction history (DB-compatible format) ──────────────

    async def get_all_transactions(self, user_id: int = None) -> List[Dict]:
        """Fetch trades, deposits, and withdrawals in DB-compatible format.

        Analogous to Coinbase get_all_v2_transactions.
        Returns deduplicated list sorted by tx_time DESC.
        """
        if not self.is_configured():
            return []

        trades = await self._get_all_trade_history(user_id=user_id)

        deposits = []
        try:
            deposits = await self.get_deposit_history(user_id=user_id)
        except Exception as e:
            logger.warning(f"Binance deposit history unavailable: {e}")

        withdrawals = []
        try:
            withdrawals = await self.get_withdrawal_history(user_id=user_id)
        except Exception as e:
            logger.warning(f"Binance withdrawal history unavailable: {e}")

        # Deduplicate by tx_id
        seen = set()
        combined = []
        for tx in trades + deposits + withdrawals:
            tid = tx.get("tx_id", "")
            if tid and tid not in seen:
                seen.add(tid)
                combined.append(tx)

        combined.sort(key=lambda x: x.get("tx_time", ""), reverse=True)
        logger.info(f"Binance total transactions: {len(trades)} trades, {len(deposits)} deposits, {len(withdrawals)} withdrawals")
        return combined

    async def _get_all_trade_history(self, user_id: int = None) -> List[Dict]:
        """Fetch all trades in the 17-field DB-compatible format.

        Same asset-discovery logic as get_trade_history() but outputs the
        format expected by transaction_history_service.save_exchange_transactions().
        """
        if not self.is_configured():
            return []

        try:
            data = await self._make_request("/api/v3/account")
            if not data:
                return []

            assets_with_balance = []
            for balance in data.get("balances", []):
                total = float(balance.get("free", 0)) + float(balance.get("locked", 0))
                if total > 0 and balance["asset"] not in ("USD", "USDT", "USDC", "BUSD"):
                    assets_with_balance.append((balance["asset"], total))

            assets_with_balance.sort(key=lambda x: x[1], reverse=True)
            assets_with_balance = assets_with_balance[:20]

            all_trades = []
            for asset, _ in assets_with_balance:
                for quote in ("USDT", "BUSD", "USD"):
                    symbol = f"{asset}{quote}"
                    trades = await self._make_request("/api/v3/myTrades", {"symbol": symbol, "limit": 1000})
                    if trades and isinstance(trades, list) and len(trades) > 0:
                        for trade in trades:
                            side = "buy" if trade.get("isBuyer") else "sell"
                            all_trades.append({
                                "tx_id": f"trade_{trade['id']}",
                                "tx_type": side,
                                "status": "completed",
                                "tx_time": self._format_timestamp(trade.get("time", 0)),
                                "amount": str(trade.get("qty", "0")),
                                "token_symbol": asset,
                                "native_amount": str(trade.get("quoteQty", "0")),
                                "native_currency": quote,
                                "fee": str(trade.get("commission", "0")),
                                "fee_currency": trade.get("commissionAsset", ""),
                                "from_address": "",
                                "to_address": "",
                                "network_hash": "",
                                "metadata": json.dumps(trade),
                            })
                        break  # Found trades for this asset, skip other quotes

            logger.info(f"Binance: fetched {len(all_trades)} trades across {len(assets_with_balance)} assets")
            return all_trades

        except Exception as e:
            logger.error(f"Error fetching Binance full trade history: {e}")
            return []

    async def get_deposit_history(self, user_id: int = None) -> List[Dict]:
        """Fetch deposit history from /sapi/v1/capital/deposit/hisrec.

        Binance limits queries to 90-day windows. Iterates from 1 year ago
        to now in 90-day chunks with pagination (limit=1000 per page).
        """
        if not self.is_configured():
            return []

        all_deposits = []
        now_ms = int(time.time() * 1000)
        one_year_ago_ms = now_ms - (365 * 24 * 60 * 60 * 1000)
        window_ms = 90 * 24 * 60 * 60 * 1000  # 90 days in ms

        start_ms = one_year_ago_ms
        while start_ms < now_ms:
            end_ms = min(start_ms + window_ms, now_ms)
            offset = 0
            while True:
                params = {
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": 1000,
                    "offset": offset,
                }
                result = await self._make_request("/sapi/v1/capital/deposit/hisrec", params)
                if result is None:
                    # Endpoint not supported or error — stop entirely
                    return all_deposits
                if not isinstance(result, list) or len(result) == 0:
                    break

                for dep in result:
                    # Status 1 = success, 6 = credited but pending unlock
                    if dep.get("status") not in (1, 6):
                        continue
                    insert_time_ms = dep.get("insertTime", 0)
                    all_deposits.append({
                        "tx_id": f"dep_{dep.get('id', dep.get('txId', ''))}",
                        "tx_type": "deposit",
                        "status": "completed",
                        "tx_time": self._format_timestamp(insert_time_ms),
                        "amount": str(dep.get("amount", "0")),
                        "token_symbol": dep.get("coin", ""),
                        "native_amount": "",
                        "native_currency": "USD",
                        "fee": "",
                        "fee_currency": "",
                        "from_address": "",
                        "to_address": dep.get("address", ""),
                        "network_hash": dep.get("txId", ""),
                        "metadata": json.dumps(dep),
                    })

                if len(result) < 1000:
                    break
                offset += len(result)

            start_ms = end_ms

        logger.info(f"Binance: fetched {len(all_deposits)} deposits")
        return all_deposits

    async def get_withdrawal_history(self, user_id: int = None) -> List[Dict]:
        """Fetch withdrawal history from /sapi/v1/capital/withdraw/history.

        Same 90-day windowing as deposits. applyTime is a datetime string
        (not ms epoch) so we convert with strptime.
        """
        if not self.is_configured():
            return []

        all_withdrawals = []
        now_ms = int(time.time() * 1000)
        one_year_ago_ms = now_ms - (365 * 24 * 60 * 60 * 1000)
        window_ms = 90 * 24 * 60 * 60 * 1000

        start_ms = one_year_ago_ms
        while start_ms < now_ms:
            end_ms = min(start_ms + window_ms, now_ms)
            offset = 0
            while True:
                params = {
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": 1000,
                    "offset": offset,
                }
                result = await self._make_request("/sapi/v1/capital/withdraw/history", params)
                if result is None:
                    return all_withdrawals
                if not isinstance(result, list) or len(result) == 0:
                    break

                for wd in result:
                    # Status 6 = completed
                    if wd.get("status") != 6:
                        continue

                    # applyTime is "2019-10-12 11:12:02" format
                    apply_time = wd.get("applyTime", "")
                    tx_time = ""
                    if apply_time:
                        try:
                            dt = datetime.strptime(apply_time, "%Y-%m-%d %H:%M:%S")
                            dt = dt.replace(tzinfo=timezone.utc)
                            tx_time = dt.isoformat()
                        except (ValueError, TypeError):
                            tx_time = apply_time

                    all_withdrawals.append({
                        "tx_id": f"wd_{wd.get('id', '')}",
                        "tx_type": "withdrawal",
                        "status": "completed",
                        "tx_time": tx_time,
                        "amount": str(wd.get("amount", "0")),
                        "token_symbol": wd.get("coin", ""),
                        "native_amount": "",
                        "native_currency": "USD",
                        "fee": str(wd.get("transactionFee", "0")),
                        "fee_currency": wd.get("coin", ""),
                        "from_address": "",
                        "to_address": wd.get("address", ""),
                        "network_hash": wd.get("txId", ""),
                        "metadata": json.dumps(wd),
                    })

                if len(result) < 1000:
                    break
                offset += len(result)

            start_ms = end_ms

        logger.info(f"Binance: fetched {len(all_withdrawals)} withdrawals")
        return all_withdrawals


# Create singleton instance
binance_service = BinanceService()
