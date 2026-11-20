"""Bounded aggregate queries behind /api/mobile/analytics/*.

fees_summary():           network + exchange fees paid, by month / chain / exchange
staking_income_summary(): staking-type income by month, from stored data only

Both read local SQLite only (no network), aggregate in SQL, are capped by a
`months` window (<= 60) and return a few dozen rows at most. Callers cache them.
Nothing here fabricates data: figures that cannot be derived from stored rows
are reported as unavailable / unpriced instead of estimated.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import aiosqlite

# Exchange tx_types that are staking-type income in exchange_transactions
STAKING_INCOME_TYPES = ("staking_reward", "inflation_reward", "staking_income",
                        "interest", "reward")

USD_LIKE = {"USD", "USDT", "USDC", "USDS", "DAI", "BUSD", "FDUSD", "PYUSD"}


def _db_path():
    import database  # looked up at call time so tests can repoint DATABASE_PATH
    return database.DATABASE_PATH


def _month_cutoff(months: int) -> str:
    """First day (YYYY-MM-01) of the oldest month in a `months`-month window
    that includes the current month."""
    now = datetime.now(timezone.utc)
    total = now.year * 12 + (now.month - 1) - (months - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}-01"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _price(prices: Dict, symbol: str) -> Optional[float]:
    if not symbol:
        return None
    sym = symbol.upper()
    if sym in USD_LIKE:
        return 1.0
    info = prices.get(sym)
    if isinstance(info, dict):
        try:
            p = float(info.get("usd") or 0)
        except (TypeError, ValueError):
            return None
        return p if p > 0 else None
    return None


async def fees_summary(user_id: int, months: int, prices: Dict, native_symbols: Dict[str, str]) -> dict:
    cutoff = _month_cutoff(months)
    by_month: Dict[str, dict] = {}
    by_chain: Dict[str, dict] = {}
    by_exchange: Dict[str, dict] = {}
    unpriced: Dict[str, dict] = {}
    total_usd = 0.0
    tx_count = 0

    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # On-chain: the fee is paid by the sender only, so only 'sent' rows;
        # one fee per (chain, tx_hash) even when a tx has several token rows.
        cur = await db.execute(
            """
            SELECT month, blockchain, SUM(fee) AS fee_sum, COUNT(*) AS n FROM (
                SELECT substr(tx_time, 1, 7) AS month, blockchain, tx_hash,
                       MAX(CAST(fee AS REAL)) AS fee
                FROM transaction_history
                WHERE user_id = ? AND direction = 'sent'
                  AND status IN ('confirmed', 'failed')
                  AND tx_time >= ? AND CAST(fee AS REAL) > 0
                GROUP BY blockchain, tx_hash
            ) GROUP BY month, blockchain
            """,
            (user_id, cutoff),
        )
        for row in await cur.fetchall():
            chain = row["blockchain"]
            symbol = native_symbols.get(chain)
            price = _price(prices, symbol) if symbol else None
            fee = float(row["fee_sum"] or 0)
            n = int(row["n"] or 0)
            ch = by_chain.setdefault(chain, {"chain": chain, "native_symbol": symbol,
                                             "native_amount": 0.0, "usd": 0.0, "tx_count": 0})
            ch["native_amount"] += fee
            ch["tx_count"] += n
            tx_count += n
            if price is None:
                u = unpriced.setdefault(symbol or chain, {"symbol": symbol or chain, "native_amount": 0.0, "tx_count": 0})
                u["native_amount"] += fee
                u["tx_count"] += n
                continue
            usd = fee * price
            ch["usd"] += usd
            total_usd += usd
            m = by_month.setdefault(row["month"], {"month": row["month"], "usd": 0.0, "tx_count": 0})
            m["usd"] += usd
            m["tx_count"] += n

        # Exchanges: fee + fee_currency per row
        cur = await db.execute(
            """
            SELECT substr(tx_time, 1, 7) AS month, exchange,
                   UPPER(COALESCE(NULLIF(fee_currency, ''), native_currency, 'USD')) AS cur,
                   SUM(CAST(fee AS REAL)) AS fee_sum, COUNT(*) AS n
            FROM exchange_transactions
            WHERE user_id = ? AND tx_time >= ? AND CAST(fee AS REAL) > 0
              AND status IN ('completed', 'confirmed', 'success')
            GROUP BY month, exchange, cur
            """,
            (user_id, cutoff),
        )
        for row in await cur.fetchall():
            fee = float(row["fee_sum"] or 0)
            n = int(row["n"] or 0)
            cur_sym = row["cur"]
            ex = by_exchange.setdefault(row["exchange"], {"exchange_id": row["exchange"], "usd": 0.0, "tx_count": 0})
            ex["tx_count"] += n
            tx_count += n
            price = _price(prices, cur_sym)
            if price is None:
                u = unpriced.setdefault(cur_sym, {"symbol": cur_sym, "native_amount": 0.0, "tx_count": 0})
                u["native_amount"] += fee
                u["tx_count"] += n
                continue
            usd = fee * price
            ex["usd"] += usd
            total_usd += usd
            m = by_month.setdefault(row["month"], {"month": row["month"], "usd": 0.0, "tx_count": 0})
            m["usd"] += usd
            m["tx_count"] += n

    return {
        "months": months,
        "since": cutoff[:7],
        "total_usd": round(total_usd, 2),
        "tx_count": tx_count,
        "by_month": [{**v, "usd": round(v["usd"], 2)} for _, v in sorted(by_month.items())],
        "by_chain": sorted(
            ({**v, "usd": round(v["usd"], 2), "native_amount": round(v["native_amount"], 8)}
             for v in by_chain.values()), key=lambda x: x["usd"], reverse=True),
        "by_exchange": sorted(
            ({**v, "usd": round(v["usd"], 2)} for v in by_exchange.values()),
            key=lambda x: x["usd"], reverse=True),
        # Fees whose currency has no current price: amounts kept, USD excluded
        "unpriced": [{**v, "native_amount": round(v["native_amount"], 8)} for v in unpriced.values()],
        # On-chain fees (and non-USD exchange fees) are valued at TODAY's price,
        # not the price on the day they were paid: totals are approximate.
        "price_basis": "current",
        "approximate": True,
        "note": ("On-chain network fees are stored in native units and converted at the "
                 "current price (not historical). Only fees on sent transactions are counted, "
                 "once per transaction. Exchange fees in USD are exact."),
        "generated_at": _now_iso(),
    }


async def staking_income_summary(user_id: int, months: int, prices: Dict) -> dict:
    cutoff = _month_cutoff(months)
    placeholders = ",".join("?" for _ in STAKING_INCOME_TYPES)
    by_month: Dict[str, dict] = {}
    by_asset: Dict[str, dict] = {}
    total_usd = 0.0
    count = 0
    approximate = False
    unpriced: Dict[str, dict] = {}

    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute(
            f"""SELECT MIN(substr(tx_time, 1, 10)) AS first_day, COUNT(*) AS n
                FROM exchange_transactions
                WHERE user_id = ? AND LOWER(tx_type) IN ({placeholders})""",
            (user_id, *STAKING_INCOME_TYPES),
        )
        meta = await cur.fetchone()
        available_from = meta["first_day"] if meta and meta["n"] else None

        # `native_amount` is the USD value recorded at receipt for rows whose
        # native_currency is USD (exact); other rows fall back to the current price.
        cur = await db.execute(
            f"""
            SELECT substr(tx_time, 1, 7) AS month,
                   UPPER(COALESCE(token_symbol, '')) AS symbol,
                   SUM(CAST(amount AS REAL)) AS qty,
                   SUM(CASE WHEN UPPER(COALESCE(native_currency, 'USD')) = 'USD'
                                 AND CAST(native_amount AS REAL) > 0
                            THEN CAST(native_amount AS REAL) ELSE 0 END) AS usd_at_receipt,
                   SUM(CASE WHEN UPPER(COALESCE(native_currency, 'USD')) = 'USD'
                                 AND CAST(native_amount AS REAL) > 0
                            THEN 0 ELSE CAST(amount AS REAL) END) AS qty_unvalued,
                   COUNT(*) AS n
            FROM exchange_transactions
            WHERE user_id = ? AND tx_time >= ? AND LOWER(tx_type) IN ({placeholders})
              AND status IN ('completed', 'confirmed', 'success')
            GROUP BY month, symbol
            """,
            (user_id, cutoff, *STAKING_INCOME_TYPES),
        )
        for row in await cur.fetchall():
            symbol = row["symbol"] or "UNKNOWN"
            qty = float(row["qty"] or 0)
            usd = float(row["usd_at_receipt"] or 0)
            unvalued = float(row["qty_unvalued"] or 0)
            n = int(row["n"] or 0)
            if unvalued > 0:
                price = _price(prices, symbol)
                if price is None:
                    u = unpriced.setdefault(symbol, {"symbol": symbol, "amount": 0.0})
                    u["amount"] += unvalued
                else:
                    usd += unvalued * price
                    approximate = True
            count += n
            total_usd += usd
            m = by_month.setdefault(row["month"], {"month": row["month"], "usd": 0.0, "count": 0})
            m["usd"] += usd
            m["count"] += n
            a = by_asset.setdefault(symbol, {"symbol": symbol, "amount": 0.0, "usd": 0.0})
            a["amount"] += qty
            a["usd"] += usd

    return {
        "months": months,
        "since": cutoff[:7],
        "total_usd": round(total_usd, 2),
        "count": count,
        "by_month": [{**v, "usd": round(v["usd"], 2)} for _, v in sorted(by_month.items())],
        "by_asset": sorted(
            ({**v, "amount": round(v["amount"], 8), "usd": round(v["usd"], 2)} for v in by_asset.values()),
            key=lambda x: x["usd"], reverse=True),
        "unpriced": [{**v, "amount": round(v["amount"], 8)} for v in unpriced.values()],
        # First day with ANY stored staking-reward row (null = none stored at all)
        "available_from": available_from,
        "sources": [
            {"source": "exchange", "available": available_from is not None,
             "available_from": available_from,
             "detail": "Exchange staking rewards (e.g. Coinbase) from synced transaction history"},
            {"source": "onchain", "available": False, "available_from": None,
             "detail": ("No on-chain staking-reward history is stored (Cardano epoch rewards via "
                        "Koios/Blockfrost are not ingested), so self-custody staking income is "
                        "not included.")},
        ],
        "price_basis": "at_receipt (USD value recorded at receipt); rows without one use the current price",
        "approximate": approximate,
        "generated_at": _now_iso(),
    }
