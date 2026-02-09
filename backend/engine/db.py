"""
Engine Database Layer

Creates and manages all engine_* tables in the shared portfolio.db.
Uses the same aiosqlite pattern as the main database.py.
"""

import aiosqlite
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


async def init_engine_tables():
    """Create all engine tables. Called from main.py lifespan."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_account_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wallet_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                account_id TEXT NOT NULL,
                account_type TEXT NOT NULL,
                parent_account_id TEXT,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chain, account_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_tx_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                account_id TEXT NOT NULL,
                tx_id TEXT NOT NULL,
                block_height INTEGER,
                block_time INTEGER,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chain, account_id, tx_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_tx_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                tx_id TEXT NOT NULL,
                raw_data TEXT NOT NULL,
                provider TEXT NOT NULL,
                hydrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chain, tx_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                event_type TEXT NOT NULL,
                tx_id TEXT NOT NULL,
                event_index INTEGER NOT NULL,
                account_id TEXT NOT NULL,
                direction TEXT,
                asset_id TEXT NOT NULL,
                amount TEXT NOT NULL,
                counterparty TEXT,
                fee TEXT,
                block_height INTEGER,
                block_time INTEGER,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chain, tx_id, event_index, account_id, direction)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_work_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backfill_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                account_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                cursor_start TEXT,
                cursor_end TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                assigned_provider TEXT,
                attempt_count INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(backfill_id, chain, account_id, domain, cursor_start, cursor_end)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_backfills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chains TEXT NOT NULL,
                domains TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                status TEXT NOT NULL DEFAULT 'planning',
                total_work_units INTEGER DEFAULT 0,
                completed_work_units INTEGER DEFAULT 0,
                failed_work_units INTEGER DEFAULT 0,
                progress_pct REAL DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_provider_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name TEXT NOT NULL,
                chain TEXT NOT NULL,
                domain TEXT NOT NULL,
                is_healthy BOOLEAN DEFAULT 1,
                consecutive_failures INTEGER DEFAULT 0,
                last_success_at TIMESTAMP,
                last_failure_at TIMESTAMP,
                circuit_open_until TIMESTAMP,
                avg_latency_ms REAL DEFAULT 0,
                total_requests INTEGER DEFAULT 0,
                total_failures INTEGER DEFAULT 0,
                quota_remaining INTEGER,
                quota_resets_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider_name, chain, domain)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                date TEXT NOT NULL,
                price_usd REAL NOT NULL,
                source TEXT NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(asset_id, date)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_price_history_hourly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                datetime TEXT NOT NULL,
                price_usd REAL NOT NULL,
                source TEXT NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(asset_id, datetime)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_token_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                symbol TEXT,
                decimals INTEGER DEFAULT 0,
                defillama_key TEXT,
                coingecko_id TEXT,
                is_nft BOOLEAN DEFAULT 0,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chain, asset_id)
            )
        """)

        # Indexes for common query patterns
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_tx_index_chain_account
            ON engine_tx_index(chain, account_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_events_user_chain
            ON engine_events(user_id, chain, block_time)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_work_units_status
            ON engine_work_units(backfill_id, status)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_work_units_domain
            ON engine_work_units(backfill_id, domain, status)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_price_history_asset
            ON engine_price_history(asset_id, date)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_price_history_hourly_asset
            ON engine_price_history_hourly(asset_id, datetime)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_account_subjects_user
            ON engine_account_subjects(user_id, chain)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_engine_token_info_chain
            ON engine_token_info(chain, asset_id)
        """)

        await db.commit()
        logger.info("Engine tables initialized")


# ============================================================================
# BACKFILL CRUD
# ============================================================================

async def create_backfill(user_id: int, chains: List[str], domains: List[str],
                          start_date: Optional[str] = None, end_date: Optional[str] = None) -> int:
    """Create a new backfill plan. Returns the backfill_id."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cursor = await db.execute(
            """INSERT INTO engine_backfills (user_id, chains, domains, start_date, end_date)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, json.dumps(chains), json.dumps(domains), start_date, end_date)
        )
        await db.commit()
        return cursor.lastrowid


async def get_backfill(backfill_id: int) -> Optional[Dict[str, Any]]:
    """Get a backfill by ID."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM engine_backfills WHERE id = ?", (backfill_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result['chains'] = json.loads(result['chains'])
        result['domains'] = json.loads(result['domains'])
        return result


async def update_backfill(backfill_id: int, **kwargs):
    """Update backfill fields."""
    if not kwargs:
        return
    sets = []
    values = []
    for key, val in kwargs.items():
        if key in ('chains', 'domains') and isinstance(val, list):
            val = json.dumps(val)
        sets.append(f"{key} = ?")
        values.append(val)
    sets.append("updated_at = ?")
    values.append(datetime.utcnow().isoformat())
    values.append(backfill_id)

    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            f"UPDATE engine_backfills SET {', '.join(sets)} WHERE id = ?",
            values
        )
        await db.commit()


async def get_user_backfills(user_id: int) -> List[Dict[str, Any]]:
    """Get all backfills for a user."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM engine_backfills WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r['chains'] = json.loads(r['chains'])
            r['domains'] = json.loads(r['domains'])
            results.append(r)
        return results


# ============================================================================
# ACCOUNT SUBJECTS CRUD
# ============================================================================

async def upsert_account_subject(user_id: int, wallet_id: int, chain: str,
                                  account_id: str, account_type: str,
                                  parent_account_id: Optional[str] = None) -> int:
    """Insert or ignore an account subject. Returns the row id."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO engine_account_subjects
               (user_id, wallet_id, chain, account_id, account_type, parent_account_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, wallet_id, chain, account_id, account_type, parent_account_id)
        )
        await db.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        # If ignored (already exists), fetch the existing ID
        cursor = await db.execute(
            "SELECT id FROM engine_account_subjects WHERE user_id = ? AND chain = ? AND account_id = ?",
            (user_id, chain, account_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_account_subjects(user_id: int, chain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get account subjects for a user, optionally filtered by chain."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        if chain:
            cursor = await db.execute(
                "SELECT * FROM engine_account_subjects WHERE user_id = ? AND chain = ?",
                (user_id, chain)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM engine_account_subjects WHERE user_id = ?",
                (user_id,)
            )
        return [dict(row) for row in await cursor.fetchall()]


# ============================================================================
# TX INDEX CRUD
# ============================================================================

async def upsert_tx_index(user_id: int, chain: str, account_id: str, tx_id: str,
                           block_height: Optional[int] = None,
                           block_time: Optional[int] = None):
    """Insert or ignore a tx index entry."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT OR IGNORE INTO engine_tx_index
               (user_id, chain, account_id, tx_id, block_height, block_time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, chain, account_id, tx_id, block_height, block_time)
        )
        await db.commit()


async def upsert_tx_index_batch(entries: List[Dict[str, Any]]):
    """Batch insert tx index entries."""
    if not entries:
        return
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO engine_tx_index
               (user_id, chain, account_id, tx_id, block_height, block_time)
               VALUES (:user_id, :chain, :account_id, :tx_id, :block_height, :block_time)""",
            entries
        )
        await db.commit()


async def get_tx_ids_for_account(chain: str, account_id: str,
                                  min_block: Optional[int] = None,
                                  max_block: Optional[int] = None) -> List[str]:
    """Get indexed tx IDs for an account, optionally within a block range."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        query = "SELECT tx_id FROM engine_tx_index WHERE chain = ? AND account_id = ?"
        params: List[Any] = [chain, account_id]
        if min_block is not None:
            query += " AND block_height >= ?"
            params.append(min_block)
        if max_block is not None:
            query += " AND block_height <= ?"
            params.append(max_block)
        query += " ORDER BY block_height ASC, tx_id ASC"
        cursor = await db.execute(query, params)
        return [row[0] for row in await cursor.fetchall()]


async def get_unhydrated_tx_ids(chain: str, limit: int = 100) -> List[str]:
    """Get tx IDs that have been indexed but not yet hydrated."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cursor = await db.execute(
            """SELECT DISTINCT ti.tx_id FROM engine_tx_index ti
               LEFT JOIN engine_tx_raw tr ON ti.chain = tr.chain AND ti.tx_id = tr.tx_id
               WHERE ti.chain = ? AND tr.id IS NULL
               LIMIT ?""",
            (chain, limit)
        )
        return [row[0] for row in await cursor.fetchall()]


# ============================================================================
# TX RAW CRUD
# ============================================================================

async def upsert_tx_raw(chain: str, tx_id: str, raw_data: Dict[str, Any], provider: str):
    """Insert or replace raw transaction data."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT OR REPLACE INTO engine_tx_raw (chain, tx_id, raw_data, provider)
               VALUES (?, ?, ?, ?)""",
            (chain, tx_id, json.dumps(raw_data), provider)
        )
        await db.commit()


async def get_tx_raw(chain: str, tx_id: str) -> Optional[Dict[str, Any]]:
    """Get raw transaction data if already hydrated."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM engine_tx_raw WHERE chain = ? AND tx_id = ?",
            (chain, tx_id)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result['raw_data'] = json.loads(result['raw_data'])
        return result


async def get_tx_raw_batch(chain: str, tx_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Get raw transaction data for multiple tx IDs. Returns {tx_id: raw_data}."""
    if not tx_ids:
        return {}
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ','.join('?' for _ in tx_ids)
        cursor = await db.execute(
            f"SELECT tx_id, raw_data FROM engine_tx_raw WHERE chain = ? AND tx_id IN ({placeholders})",
            [chain] + list(tx_ids)
        )
        result = {}
        for row in await cursor.fetchall():
            result[row['tx_id']] = json.loads(row['raw_data'])
        return result


# ============================================================================
# EVENTS CRUD
# ============================================================================

async def upsert_event(user_id: int, chain: str, event_type: str, tx_id: str,
                        event_index: int, account_id: str, direction: str,
                        asset_id: str, amount: str, counterparty: Optional[str] = None,
                        fee: Optional[str] = None, block_height: Optional[int] = None,
                        block_time: Optional[int] = None, metadata: Optional[Dict] = None):
    """Insert or ignore a canonical event."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT OR IGNORE INTO engine_events
               (user_id, chain, event_type, tx_id, event_index, account_id, direction,
                asset_id, amount, counterparty, fee, block_height, block_time, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, chain, event_type, tx_id, event_index, account_id, direction,
             asset_id, amount, counterparty, fee, block_height, block_time,
             json.dumps(metadata) if metadata else None)
        )
        await db.commit()


async def upsert_events_batch(events: List[Dict[str, Any]]):
    """Batch insert canonical events."""
    if not events:
        return
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        for evt in events:
            if 'metadata' in evt and isinstance(evt['metadata'], dict):
                evt['metadata'] = json.dumps(evt['metadata'])
        await db.executemany(
            """INSERT OR IGNORE INTO engine_events
               (user_id, chain, event_type, tx_id, event_index, account_id, direction,
                asset_id, amount, counterparty, fee, block_height, block_time, metadata)
               VALUES (:user_id, :chain, :event_type, :tx_id, :event_index, :account_id,
                       :direction, :asset_id, :amount, :counterparty, :fee, :block_height,
                       :block_time, :metadata)""",
            events
        )
        await db.commit()


async def get_events(user_id: int, chain: Optional[str] = None,
                      min_time: Optional[int] = None, max_time: Optional[int] = None,
                      asset_id: Optional[str] = None,
                      limit: int = 1000) -> List[Dict[str, Any]]:
    """Query canonical events with optional filters."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM engine_events WHERE user_id = ?"
        params: List[Any] = [user_id]
        if chain:
            query += " AND chain = ?"
            params.append(chain)
        if min_time is not None:
            query += " AND block_time >= ?"
            params.append(min_time)
        if max_time is not None:
            query += " AND block_time <= ?"
            params.append(max_time)
        if asset_id:
            query += " AND asset_id = ?"
            params.append(asset_id)
        query += " ORDER BY block_time ASC, event_index ASC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        results = []
        for row in await cursor.fetchall():
            r = dict(row)
            if r.get('metadata'):
                r['metadata'] = json.loads(r['metadata'])
            results.append(r)
        return results


async def get_event_count(user_id: int, chain: Optional[str] = None) -> int:
    """Count events for a user."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        query = "SELECT COUNT(*) FROM engine_events WHERE user_id = ?"
        params: List[Any] = [user_id]
        if chain:
            query += " AND chain = ?"
            params.append(chain)
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        return row[0] if row else 0


# ============================================================================
# WORK UNITS CRUD
# ============================================================================

async def create_work_unit(backfill_id: int, user_id: int, chain: str,
                            account_id: str, domain: str,
                            cursor_start: Optional[str] = None,
                            cursor_end: Optional[str] = None) -> int:
    """Create a work unit. Returns the work unit id."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO engine_work_units
               (backfill_id, user_id, chain, account_id, domain, cursor_start, cursor_end)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (backfill_id, user_id, chain, account_id, domain, cursor_start, cursor_end)
        )
        await db.commit()
        return cursor.lastrowid or 0


async def create_work_units_batch(units: List[Dict[str, Any]]):
    """Batch create work units."""
    if not units:
        return
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO engine_work_units
               (backfill_id, user_id, chain, account_id, domain, cursor_start, cursor_end)
               VALUES (:backfill_id, :user_id, :chain, :account_id, :domain,
                       :cursor_start, :cursor_end)""",
            units
        )
        await db.commit()


async def get_pending_work_units(backfill_id: int, domain: Optional[str] = None,
                                  limit: int = 10) -> List[Dict[str, Any]]:
    """Get pending work units for a backfill, optionally filtered by domain."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM engine_work_units WHERE backfill_id = ? AND status IN ('pending', 'retry')"
        params: List[Any] = [backfill_id]
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        query += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]


async def update_work_unit(work_unit_id: int, **kwargs):
    """Update work unit fields."""
    if not kwargs:
        return
    sets = []
    values = []
    for key, val in kwargs.items():
        sets.append(f"{key} = ?")
        values.append(val)
    values.append(work_unit_id)

    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            f"UPDATE engine_work_units SET {', '.join(sets)} WHERE id = ?",
            values
        )
        await db.commit()


async def get_work_unit_stats(backfill_id: int) -> Dict[str, Dict[str, int]]:
    """Get work unit counts by domain and status for a backfill."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cursor = await db.execute(
            """SELECT domain, status, COUNT(*) as cnt
               FROM engine_work_units WHERE backfill_id = ?
               GROUP BY domain, status""",
            (backfill_id,)
        )
        rows = await cursor.fetchall()
        stats: Dict[str, Dict[str, int]] = {}
        for domain, status, cnt in rows:
            if domain not in stats:
                stats[domain] = {'total': 0, 'done': 0, 'failed': 0, 'pending': 0, 'running': 0}
            stats[domain]['total'] += cnt
            if status == 'completed':
                stats[domain]['done'] += cnt
            elif status == 'failed':
                stats[domain]['failed'] += cnt
            elif status in ('pending', 'retry'):
                stats[domain]['pending'] += cnt
            elif status in ('assigned', 'running'):
                stats[domain]['running'] += cnt
        return stats


async def cancel_backfill_work_units(backfill_id: int):
    """Cancel all pending/running work units for a backfill."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """UPDATE engine_work_units SET status = 'failed', error_message = 'cancelled'
               WHERE backfill_id = ? AND status IN ('pending', 'assigned', 'running', 'retry')""",
            (backfill_id,)
        )
        await db.commit()


# ============================================================================
# PROVIDER HEALTH CRUD
# ============================================================================

async def upsert_provider_health(provider_name: str, chain: str, domain: str,
                                  **kwargs):
    """Update or insert provider health data."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        # Check if exists
        cursor = await db.execute(
            """SELECT id FROM engine_provider_health
               WHERE provider_name = ? AND chain = ? AND domain = ?""",
            (provider_name, chain, domain)
        )
        existing = await cursor.fetchone()

        if existing:
            if kwargs:
                sets = ["updated_at = ?"]
                values = [datetime.utcnow().isoformat()]
                for key, val in kwargs.items():
                    sets.append(f"{key} = ?")
                    values.append(val)
                values.append(existing[0])
                await db.execute(
                    f"UPDATE engine_provider_health SET {', '.join(sets)} WHERE id = ?",
                    values
                )
        else:
            cols = ['provider_name', 'chain', 'domain']
            vals = [provider_name, chain, domain]
            for key, val in kwargs.items():
                cols.append(key)
                vals.append(val)
            placeholders = ','.join('?' for _ in vals)
            await db.execute(
                f"INSERT INTO engine_provider_health ({','.join(cols)}) VALUES ({placeholders})",
                vals
            )
        await db.commit()


async def get_provider_health(provider_name: str, chain: str, domain: str) -> Optional[Dict[str, Any]]:
    """Get health data for a specific provider+chain+domain."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM engine_provider_health
               WHERE provider_name = ? AND chain = ? AND domain = ?""",
            (provider_name, chain, domain)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_provider_health() -> List[Dict[str, Any]]:
    """Get all provider health records."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM engine_provider_health")
        return [dict(row) for row in await cursor.fetchall()]


# ============================================================================
# PRICE HISTORY CRUD
# ============================================================================

async def upsert_price(asset_id: str, date: str, price_usd: float, source: str):
    """Insert or replace a historical price."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT OR REPLACE INTO engine_price_history (asset_id, date, price_usd, source)
               VALUES (?, ?, ?, ?)""",
            (asset_id, date, price_usd, source)
        )
        await db.commit()


async def upsert_prices_batch(prices: List[Dict[str, Any]]):
    """Batch insert historical prices."""
    if not prices:
        return
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO engine_price_history (asset_id, date, price_usd, source)
               VALUES (:asset_id, :date, :price_usd, :source)""",
            prices
        )
        await db.commit()


async def get_prices(asset_id: str, start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get historical prices for an asset, optionally within a date range."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM engine_price_history WHERE asset_id = ?"
        params: List[Any] = [asset_id]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date ASC"
        cursor = await db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]


async def get_prices_for_date(date: str) -> Dict[str, float]:
    """Get all asset prices for a specific date. Returns {asset_id: price_usd}."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        cursor = await db.execute(
            "SELECT asset_id, price_usd FROM engine_price_history WHERE date = ?",
            (date,)
        )
        return {row[0]: row[1] for row in await cursor.fetchall()}


# ============================================================================
# HOURLY PRICE HISTORY CRUD
# ============================================================================

async def upsert_hourly_price(asset_id: str, datetime_str: str, price_usd: float, source: str):
    """Insert or replace an hourly historical price."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT OR REPLACE INTO engine_price_history_hourly (asset_id, datetime, price_usd, source)
               VALUES (?, ?, ?, ?)""",
            (asset_id, datetime_str, price_usd, source)
        )
        await db.commit()


async def get_hourly_prices(asset_id: str, start_datetime: Optional[str] = None,
                             end_datetime: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get hourly prices for an asset, optionally within a datetime range."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM engine_price_history_hourly WHERE asset_id = ?"
        params: List[Any] = [asset_id]
        if start_datetime:
            query += " AND datetime >= ?"
            params.append(start_datetime)
        if end_datetime:
            query += " AND datetime <= ?"
            params.append(end_datetime)
        query += " ORDER BY datetime ASC"
        cursor = await db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]


async def upsert_hourly_prices_batch(prices: List[Dict[str, Any]]):
    """Batch insert hourly historical prices."""
    if not prices:
        return
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO engine_price_history_hourly (asset_id, datetime, price_usd, source)
               VALUES (:asset_id, :datetime, :price_usd, :source)""",
            prices
        )
        await db.commit()


# ============================================================================
# TOKEN INFO CRUD
# ============================================================================

async def get_token_info(chain: str, asset_id: str) -> Optional[Dict[str, Any]]:
    """Get cached token info for a specific chain+asset_id."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM engine_token_info WHERE chain = ? AND asset_id = ?",
            (chain, asset_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def upsert_token_info(chain: str, asset_id: str, symbol: Optional[str] = None,
                             decimals: int = 0, defillama_key: Optional[str] = None,
                             coingecko_id: Optional[str] = None, is_nft: bool = False):
    """Insert or update token info."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        await db.execute(
            """INSERT INTO engine_token_info (chain, asset_id, symbol, decimals, defillama_key, coingecko_id, is_nft)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chain, asset_id) DO UPDATE SET
                   symbol = COALESCE(excluded.symbol, engine_token_info.symbol),
                   decimals = CASE WHEN excluded.decimals > 0 THEN excluded.decimals ELSE engine_token_info.decimals END,
                   defillama_key = COALESCE(excluded.defillama_key, engine_token_info.defillama_key),
                   coingecko_id = COALESCE(excluded.coingecko_id, engine_token_info.coingecko_id),
                   is_nft = excluded.is_nft""",
            (chain, asset_id, symbol, decimals, defillama_key, coingecko_id, int(is_nft))
        )
        await db.commit()


async def get_all_token_info(chain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all token info records, optionally filtered by chain."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        if chain:
            cursor = await db.execute(
                "SELECT * FROM engine_token_info WHERE chain = ?", (chain,)
            )
        else:
            cursor = await db.execute("SELECT * FROM engine_token_info")
        return [dict(row) for row in await cursor.fetchall()]


async def get_unique_asset_ids(user_id: int, chain: Optional[str] = None) -> List[Dict[str, str]]:
    """Get unique (chain, asset_id) pairs from events for a user."""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT DISTINCT chain, asset_id FROM engine_events WHERE user_id = ?"
        params: List[Any] = [user_id]
        if chain:
            query += " AND chain = ?"
            params.append(chain)
        cursor = await db.execute(query, params)
        return [dict(row) for row in await cursor.fetchall()]
