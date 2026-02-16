"""
Wallet Intelligence Router

Analyzes wallet interaction patterns: counterparty identification,
CEX detection, activity heatmaps, and flow direction analysis.

Endpoints:
    GET /intelligence/counterparties   - Top counterparty addresses with labels
    GET /intelligence/flow-summary     - Sent/received aggregates per chain
    GET /intelligence/activity-heatmap - 7x24 transaction frequency matrix
"""

import logging
import os
import sys
from typing import Optional
from datetime import datetime, timedelta

import aiosqlite
from fastapi import APIRouter, Depends, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_utils import verify_session
from config import DATABASE_PATH, CACHE_TTL_WARM
from database import get_cache, set_cache, get_all_wallets, get_username_by_user_id
from middleware.demo_mode import is_demo_user
from services.known_addresses import identify_address
from services.coinbase import coinbase_service
from services.pricing import pricing_service

router = APIRouter(prefix="/intelligence", tags=["intelligence"])
logger = logging.getLogger(__name__)


def _get_time_filter(days: int) -> Optional[str]:
    """Return ISO timestamp string for N days ago, or None for 'all time'."""
    if days <= 0:
        return None
    cutoff = datetime.utcnow() - timedelta(days=days)
    return cutoff.isoformat()


def _generate_demo_counterparties():
    """Generate realistic demo counterparty data."""
    return [
        {"address": "0x28c6c06298d514db089934071355e5743bf21d60", "label": "Binance", "label_type": "cex", "blockchain": "ethereum", "tx_count": 24, "total_sent": 15200.50, "total_received": 8300.00, "first_seen": "2025-03-15T10:30:00", "last_seen": "2026-02-10T14:22:00"},
        {"address": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3", "label": "Coinbase", "label_type": "cex", "blockchain": "ethereum", "tx_count": 18, "total_sent": 5000.00, "total_received": 12500.00, "first_seen": "2025-06-01T08:15:00", "last_seen": "2026-02-08T16:45:00"},
        {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "label": "Unknown", "label_type": "unknown", "blockchain": "ethereum", "tx_count": 12, "total_sent": 0, "total_received": 3200.00, "first_seen": "2025-09-20T12:00:00", "last_seen": "2026-01-15T09:30:00"},
        {"address": "addr1q9yr2...qs58zt3j", "label": "Binance", "label_type": "cex", "blockchain": "cardano", "tx_count": 8, "total_sent": 2500.00, "total_received": 1800.00, "first_seen": "2025-08-10T06:00:00", "last_seen": "2026-02-01T20:00:00"},
        {"address": "DRpbCB...7HM3k2", "label": "Self", "label_type": "self", "blockchain": "solana", "tx_count": 6, "total_sent": 800.00, "total_received": 800.00, "first_seen": "2025-11-01T15:00:00", "last_seen": "2026-01-20T11:00:00"},
    ]


def _generate_demo_flow_summary():
    """Generate realistic demo flow summary data."""
    return {
        "total_sent": 23500.50,
        "total_received": 26600.00,
        "net_flow": 3099.50,
        "unique_counterparties": 15,
        "cex_deposits": 8,
        "cex_withdrawals": 12,
        "self_transfers": 4,
        "exchange_trades": 15,
        "chains": {
            "ethereum": {"sent": 15200.50, "received": 20800.00, "tx_count": 42},
            "cardano": {"sent": 5000.00, "received": 3200.00, "tx_count": 18},
            "solana": {"sent": 2500.00, "received": 1800.00, "tx_count": 12},
            "bitcoin": {"sent": 800.00, "received": 800.00, "tx_count": 4},
        },
    }


def _generate_demo_heatmap():
    """Generate realistic demo heatmap data (7x24 matrix)."""
    import random
    random.seed(42)
    matrix = []
    for dow in range(7):
        for hour in range(24):
            # Higher activity during weekday business hours (UTC)
            is_weekday = dow < 5
            is_active_hour = 8 <= hour <= 22
            base = 3 if (is_weekday and is_active_hour) else 1
            count = random.randint(0, base * 2)
            if count > 0:
                matrix.append({"day": dow, "hour": hour, "count": count})
    return matrix


@router.get("/counterparties")
async def get_counterparties(
    days: int = Query(default=365, ge=0, le=3650),
    blockchain: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: int = Depends(verify_session),
):
    """Top counterparty addresses the user has interacted with"""
    try:
        # Demo mode
        username = await get_username_by_user_id(user_id)
        if username and await is_demo_user(username):
            return {"success": True, "counterparties": _generate_demo_counterparties()}

        # Check cache
        cache_key = f"intelligence_counterparties_{user_id}_{days}_{blockchain or 'all'}"
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return {"success": True, "counterparties": cached}

        # Get user's own wallet addresses for self-transfer detection
        wallets = await get_all_wallets(user_id=user_id)
        own_addresses = set()
        for w in wallets:
            addr = w["address"]
            chain = w.get("blockchain", "").lower()
            if chain != "cardano":
                own_addresses.add(addr.lower())
            else:
                own_addresses.add(addr)

        time_filter = _get_time_filter(days)

        # Query transaction_history for counterparty aggregation
        counterparty_map = {}  # key: (address_normalized, chain) -> stats

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # Build query for transaction_history
            sql = """
                SELECT
                    blockchain,
                    direction,
                    from_address,
                    to_address,
                    CAST(COALESCE(amount, '0') AS REAL) as amount_val,
                    tx_time
                FROM transaction_history
                WHERE user_id = ?
            """
            params = [user_id]

            if time_filter:
                sql += " AND tx_time >= ?"
                params.append(time_filter)
            if blockchain:
                sql += " AND blockchain = ?"
                params.append(blockchain)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            for row in rows:
                chain = row["blockchain"]
                direction = row["direction"]
                from_addr = row["from_address"] or ""
                to_addr = row["to_address"] or ""

                # Determine counterparty: it's the address that is NOT ours
                if direction == "sent":
                    counterparty = to_addr
                else:
                    counterparty = from_addr

                if not counterparty:
                    continue

                # Normalize for comparison
                norm_addr = counterparty.lower() if chain.lower() != "cardano" else counterparty
                key = (norm_addr, chain)

                if key not in counterparty_map:
                    counterparty_map[key] = {
                        "address": counterparty,
                        "blockchain": chain,
                        "tx_count": 0,
                        "total_sent": 0.0,
                        "total_received": 0.0,
                        "first_seen": row["tx_time"],
                        "last_seen": row["tx_time"],
                    }

                entry = counterparty_map[key]
                entry["tx_count"] += 1
                amount = row["amount_val"] or 0
                if direction == "sent":
                    entry["total_sent"] += amount
                else:
                    entry["total_received"] += amount

                # Update first/last seen
                tx_time = row["tx_time"]
                if tx_time and (not entry["first_seen"] or tx_time < entry["first_seen"]):
                    entry["first_seen"] = tx_time
                if tx_time and (not entry["last_seen"] or tx_time > entry["last_seen"]):
                    entry["last_seen"] = tx_time

            # Also merge engine_events counterparty data
            engine_sql = """
                SELECT
                    chain as blockchain,
                    direction,
                    account_id,
                    counterparty,
                    CAST(COALESCE(amount, '0') AS REAL) as amount_val,
                    block_time
                FROM engine_events
                WHERE user_id = ?
                  AND counterparty IS NOT NULL
                  AND counterparty != ''
            """
            engine_params = [user_id]

            if time_filter:
                engine_sql += " AND datetime(block_time, 'unixepoch') >= ?"
                engine_params.append(time_filter)
            if blockchain:
                engine_sql += " AND chain = ?"
                engine_params.append(blockchain)

            try:
                cursor2 = await db.execute(engine_sql, engine_params)
                engine_rows = await cursor2.fetchall()

                for row in engine_rows:
                    chain = row["blockchain"]
                    counterparty = row["counterparty"]
                    if not counterparty:
                        continue

                    norm_addr = counterparty.lower() if chain.lower() != "cardano" else counterparty
                    key = (norm_addr, chain)

                    if key not in counterparty_map:
                        block_time = row["block_time"]
                        ts = datetime.utcfromtimestamp(block_time).isoformat() if block_time else None
                        counterparty_map[key] = {
                            "address": counterparty,
                            "blockchain": chain,
                            "tx_count": 0,
                            "total_sent": 0.0,
                            "total_received": 0.0,
                            "first_seen": ts,
                            "last_seen": ts,
                        }

                    entry = counterparty_map[key]
                    entry["tx_count"] += 1
                    amount = row["amount_val"] or 0
                    direction = row["direction"]
                    if direction == "sent" or direction == "out":
                        entry["total_sent"] += amount
                    else:
                        entry["total_received"] += amount

                    if row["block_time"]:
                        ts = datetime.utcfromtimestamp(row["block_time"]).isoformat()
                        if not entry["first_seen"] or ts < entry["first_seen"]:
                            entry["first_seen"] = ts
                        if not entry["last_seen"] or ts > entry["last_seen"]:
                            entry["last_seen"] = ts
            except Exception as e:
                # engine_events table may not exist yet
                logger.debug(f"Engine events query skipped: {e}")

        # Label counterparties and build result
        results = []
        for (norm_addr, chain), stats in counterparty_map.items():
            # Check if it's a known CEX
            label = identify_address(stats["address"], chain)
            if label:
                label_type = "cex"
            elif norm_addr in own_addresses:
                label = "Self"
                label_type = "self"
            else:
                label = "Unknown"
                label_type = "unknown"

            stats["label"] = label
            stats["label_type"] = label_type
            # Round amounts
            stats["total_sent"] = round(stats["total_sent"], 2)
            stats["total_received"] = round(stats["total_received"], 2)
            results.append(stats)

        # Sort by tx_count descending
        results.sort(key=lambda x: x["tx_count"], reverse=True)
        results = results[:limit]

        await set_cache(cache_key, results, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
        return {"success": True, "counterparties": results}

    except Exception as e:
        logger.error(f"Error fetching counterparties: {e}")
        return {"success": False, "error": str(e), "counterparties": []}


async def _get_exchange_trade_counts(user_id: int, time_filter: Optional[str] = None) -> dict:
    """Fetch trade counts from connected exchanges (Coinbase etc.)."""
    result = {"total": 0, "deposits": 0, "withdrawals": 0, "buys": 0, "sells": 0}
    try:
        if await coinbase_service.is_configured(user_id=user_id):
            orders = await coinbase_service.get_transactions(user_id=user_id, limit=500)
            for order in orders:
                # Filter by time if needed
                created = order.get("created_time") or order.get("created_at", "")
                if time_filter and created and created < time_filter:
                    continue
                side = (order.get("side") or "").upper()
                result["total"] += 1
                if side == "BUY":
                    result["buys"] += 1
                    result["withdrawals"] += 1  # Buy = funds come from CEX to user
                elif side == "SELL":
                    result["sells"] += 1
                    result["deposits"] += 1  # Sell = funds go from user to CEX
    except Exception as e:
        logger.debug(f"Exchange trade count fetch failed: {e}")
    return result


@router.get("/flow-summary")
async def get_flow_summary(
    days: int = Query(default=365, ge=0, le=3650),
    blockchain: Optional[str] = Query(default=None),
    user_id: int = Depends(verify_session),
):
    """Aggregate flow stats: sent/received per chain, CEX interaction counts"""
    try:
        # Demo mode
        username = await get_username_by_user_id(user_id)
        if username and await is_demo_user(username):
            return {"success": True, **_generate_demo_flow_summary()}

        # Check cache
        cache_key = f"intelligence_flow_{user_id}_{days}_{blockchain or 'all'}"
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return {"success": True, **cached}

        # Get user wallets for self-transfer detection
        wallets = await get_all_wallets(user_id=user_id)
        own_addresses = set()
        for w in wallets:
            addr = w["address"]
            chain = w.get("blockchain", "").lower()
            if chain != "cardano":
                own_addresses.add(addr.lower())
            else:
                own_addresses.add(addr)

        time_filter = _get_time_filter(days)

        total_sent = 0.0
        total_received = 0.0
        cex_deposits = 0
        cex_withdrawals = 0
        self_transfers = 0
        unique_counterparties = set()
        chains = {}

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            sql = """
                SELECT
                    blockchain,
                    direction,
                    from_address,
                    to_address,
                    CAST(COALESCE(amount, '0') AS REAL) as amount_val
                FROM transaction_history
                WHERE user_id = ?
            """
            params = [user_id]

            if time_filter:
                sql += " AND tx_time >= ?"
                params.append(time_filter)
            if blockchain:
                sql += " AND blockchain = ?"
                params.append(blockchain)

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            for row in rows:
                chain = row["blockchain"]
                direction = row["direction"]
                amount = row["amount_val"] or 0
                from_addr = row["from_address"] or ""
                to_addr = row["to_address"] or ""

                # Determine counterparty
                counterparty = to_addr if direction == "sent" else from_addr
                norm_cp = counterparty.lower() if chain.lower() != "cardano" else counterparty

                if counterparty:
                    unique_counterparties.add((norm_cp, chain))

                # Chain aggregation
                if chain not in chains:
                    chains[chain] = {"sent": 0.0, "received": 0.0, "tx_count": 0}
                chains[chain]["tx_count"] += 1

                if direction == "sent":
                    total_sent += amount
                    chains[chain]["sent"] += amount
                    # Check if sending to CEX (deposit)
                    if counterparty and identify_address(counterparty, chain):
                        cex_deposits += 1
                else:
                    total_received += amount
                    chains[chain]["received"] += amount
                    # Check if receiving from CEX (withdrawal)
                    if counterparty and identify_address(counterparty, chain):
                        cex_withdrawals += 1

                # Self-transfer detection
                if norm_cp in own_addresses:
                    self_transfers += 1

        # Round chain values
        for c in chains:
            chains[c]["sent"] = round(chains[c]["sent"], 2)
            chains[c]["received"] = round(chains[c]["received"], 2)

        # Add exchange API trade counts (Coinbase etc.)
        exchange_trades = await _get_exchange_trade_counts(user_id, time_filter)
        cex_deposits += exchange_trades["deposits"]
        cex_withdrawals += exchange_trades["withdrawals"]

        result = {
            "total_sent": round(total_sent, 2),
            "total_received": round(total_received, 2),
            "net_flow": round(total_received - total_sent, 2),
            "unique_counterparties": len(unique_counterparties),
            "cex_deposits": cex_deposits,
            "cex_withdrawals": cex_withdrawals,
            "self_transfers": self_transfers,
            "exchange_trades": exchange_trades["total"],
            "chains": chains,
        }

        await set_cache(cache_key, result, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
        return {"success": True, **result}

    except Exception as e:
        logger.error(f"Error fetching flow summary: {e}")
        return {"success": False, "error": str(e)}


@router.get("/activity-heatmap")
async def get_activity_heatmap(
    days: int = Query(default=365, ge=0, le=3650),
    blockchain: Optional[str] = Query(default=None),
    user_id: int = Depends(verify_session),
):
    """7x24 transaction frequency matrix (day-of-week x hour-of-day)"""
    try:
        # Demo mode
        username = await get_username_by_user_id(user_id)
        if username and await is_demo_user(username):
            return {"success": True, "heatmap": _generate_demo_heatmap()}

        # Check cache
        cache_key = f"intelligence_heatmap_{user_id}_{days}_{blockchain or 'all'}"
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return {"success": True, "heatmap": cached}

        time_filter = _get_time_filter(days)

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            sql = """
                SELECT
                    CAST(strftime('%w', tx_time) AS INTEGER) as dow,
                    CAST(strftime('%H', tx_time) AS INTEGER) as hour,
                    COUNT(*) as count
                FROM transaction_history
                WHERE user_id = ?
            """
            params = [user_id]

            if time_filter:
                sql += " AND tx_time >= ?"
                params.append(time_filter)
            if blockchain:
                sql += " AND blockchain = ?"
                params.append(blockchain)

            sql += " GROUP BY dow, hour"

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

            heatmap = []
            for row in rows:
                heatmap.append({
                    "day": row["dow"],
                    "hour": row["hour"],
                    "count": row["count"],
                })

        await set_cache(cache_key, heatmap, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
        return {"success": True, "heatmap": heatmap}

    except Exception as e:
        logger.error(f"Error fetching activity heatmap: {e}")
        return {"success": False, "error": str(e), "heatmap": []}


def _generate_demo_large_transactions():
    """Generate realistic demo large transaction data."""
    return [
        {"tx_hash": "0xabc123...def456", "blockchain": "ethereum", "direction": "sent", "token_symbol": "ETH", "amount": 5.2, "usd_value": 18200.00, "counterparty": "0x28c6c0...bf21d60", "counterparty_label": "Binance", "tx_time": "2026-02-10T14:22:00"},
        {"tx_hash": "0x789abc...123def", "blockchain": "ethereum", "direction": "received", "token_symbol": "ETH", "amount": 3.0, "usd_value": 10500.00, "counterparty": "0x71660c...fe775d3", "counterparty_label": "Coinbase", "tx_time": "2026-02-08T16:45:00"},
        {"tx_hash": "abc123def456...789", "blockchain": "cardano", "direction": "sent", "token_symbol": "ADA", "amount": 15000, "usd_value": 7500.00, "counterparty": "addr1q9yr2...qs58zt3j", "counterparty_label": "Binance", "tx_time": "2026-01-28T09:30:00"},
        {"tx_hash": "0xdef789...abc123", "blockchain": "ethereum", "direction": "received", "token_symbol": "USDC", "amount": 5000, "usd_value": 5000.00, "counterparty": "0xd8dA6B...96045", "counterparty_label": "Unknown", "tx_time": "2026-01-15T12:00:00"},
        {"tx_hash": "5KJn8m...3Rj7Qp", "blockchain": "solana", "direction": "sent", "token_symbol": "SOL", "amount": 20.5, "usd_value": 4305.00, "counterparty": "DRpbCB...7HM3k2", "counterparty_label": "Unknown", "tx_time": "2025-12-20T15:30:00"},
        {"tx_hash": "bc1abc...def789", "blockchain": "bitcoin", "direction": "received", "token_symbol": "BTC", "amount": 0.025, "usd_value": 2375.00, "counterparty": "bc1qxy2...g8rd9", "counterparty_label": "Unknown", "tx_time": "2025-11-10T08:00:00"},
        {"tx_hash": "0x456def...789abc", "blockchain": "polygon", "direction": "sent", "token_symbol": "MATIC", "amount": 3500, "usd_value": 1750.00, "counterparty": "0x28c6c0...bf21d60", "counterparty_label": "Binance", "tx_time": "2025-10-05T20:15:00"},
    ]


@router.get("/large-transactions")
async def get_large_transactions(
    min_usd: float = Query(default=100, ge=0),
    days: int = Query(default=0, ge=0, le=3650),
    blockchain: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user_id: int = Depends(verify_session),
):
    """Large transactions filtered by USD value threshold"""
    try:
        # Demo mode
        username = await get_username_by_user_id(user_id)
        if username and await is_demo_user(username):
            demo = _generate_demo_large_transactions()
            return {"success": True, "transactions": [t for t in demo if t["usd_value"] >= min_usd][:limit]}

        # Check cache
        cache_key = f"intelligence_large_tx_{user_id}_{min_usd}_{days}_{blockchain or 'all'}"
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return {"success": True, "transactions": cached}

        time_filter = _get_time_filter(days) if days > 0 else None

        # Get user wallets for counterparty labeling
        wallets = await get_all_wallets(user_id=user_id)
        own_addresses = set()
        for w in wallets:
            addr = w["address"]
            chain = w.get("blockchain", "").lower()
            if chain != "cardano":
                own_addresses.add(addr.lower())
            else:
                own_addresses.add(addr)

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            sql = """
                SELECT
                    tx_hash,
                    blockchain,
                    direction,
                    token_symbol,
                    CAST(COALESCE(amount, '0') AS REAL) as amount_val,
                    from_address,
                    to_address,
                    tx_time
                FROM transaction_history
                WHERE user_id = ?
            """
            params = [user_id]

            if time_filter:
                sql += " AND tx_time >= ?"
                params.append(time_filter)
            if blockchain:
                sql += " AND blockchain = ?"
                params.append(blockchain)

            sql += " ORDER BY tx_time DESC"

            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()

        if not rows:
            await set_cache(cache_key, [], ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
            return {"success": True, "transactions": []}

        # Collect unique token symbols for batch price lookup
        symbols = set()
        for row in rows:
            sym = row["token_symbol"]
            if sym:
                symbols.add(sym.upper())

        # Batch fetch current prices
        prices = {}
        if symbols:
            try:
                prices = await pricing_service.get_prices(list(symbols))
            except Exception as e:
                logger.debug(f"Price fetch for large tx failed: {e}")

        # Build results with USD values
        results = []
        for row in rows:
            sym = (row["token_symbol"] or "").upper()
            amount = row["amount_val"] or 0
            price = prices.get(sym, 0)

            # Stablecoins default to $1
            if sym in ("USDC", "USDT", "DAI", "BUSD") and price == 0:
                price = 1.0

            usd_value = amount * price
            if usd_value < min_usd:
                continue

            direction = row["direction"]
            counterparty = row["to_address"] if direction == "sent" else row["from_address"]
            counterparty = counterparty or ""

            # Label counterparty
            chain = row["blockchain"]
            label = identify_address(counterparty, chain)
            if not label:
                norm = counterparty.lower() if chain.lower() != "cardano" else counterparty
                if norm in own_addresses:
                    label = "Self"
                else:
                    label = "Unknown"

            # Truncate hash for display
            tx_hash = row["tx_hash"] or ""
            short_hash = tx_hash[:10] + "..." + tx_hash[-6:] if len(tx_hash) > 20 else tx_hash

            results.append({
                "tx_hash": tx_hash,
                "tx_hash_short": short_hash,
                "blockchain": chain,
                "direction": direction,
                "token_symbol": row["token_symbol"],
                "amount": round(amount, 6),
                "usd_value": round(usd_value, 2),
                "counterparty": counterparty,
                "counterparty_label": label,
                "tx_time": row["tx_time"],
            })

        # Sort by USD value descending
        results.sort(key=lambda x: x["usd_value"], reverse=True)
        results = results[:limit]

        await set_cache(cache_key, results, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
        return {"success": True, "transactions": results}

    except Exception as e:
        logger.error(f"Error fetching large transactions: {e}")
        return {"success": False, "error": str(e), "transactions": []}
