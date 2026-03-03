"""
Direct PostgreSQL connection to DB Sync via asyncpg.

Read-only connection pool for querying Cardano blockchain data
directly from DB Sync, bypassing Blockfrost API overhead.

This module is OPTIONAL — when DBSYNC_PG_HOST is not set, the pool
is never created and all functions gracefully return None or raise
ConnectionError (which callers handle via the fallback pattern).
"""

import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

# asyncpg is optional — app works without it
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None
    ASYNCPG_AVAILABLE = False
    logger.info("asyncpg not installed — DB Sync direct access unavailable")

_pool = None


async def get_pool():
    """Get or create the DB Sync connection pool. Returns None if unavailable."""
    global _pool
    if _pool is not None:
        return _pool

    if not ASYNCPG_AVAILABLE:
        return None

    from config import (
        DBSYNC_PG_ENABLED, DBSYNC_PG_HOST, DBSYNC_PG_PORT,
        DBSYNC_PG_DATABASE, DBSYNC_PG_USER, DBSYNC_PG_PASSWORD,
        DBSYNC_PG_MIN_CONNECTIONS, DBSYNC_PG_MAX_CONNECTIONS,
    )

    if not DBSYNC_PG_ENABLED:
        return None

    try:
        _pool = await asyncpg.create_pool(
            host=DBSYNC_PG_HOST,
            port=DBSYNC_PG_PORT,
            database=DBSYNC_PG_DATABASE,
            user=DBSYNC_PG_USER,
            password=DBSYNC_PG_PASSWORD,
            min_size=DBSYNC_PG_MIN_CONNECTIONS,
            max_size=DBSYNC_PG_MAX_CONNECTIONS,
            command_timeout=30,
            server_settings={
                'default_transaction_read_only': 'on',
                'statement_timeout': '30000',
            },
        )
        logger.info(
            f"DB Sync connection pool created: "
            f"{DBSYNC_PG_HOST}:{DBSYNC_PG_PORT}/{DBSYNC_PG_DATABASE}"
        )
        return _pool
    except Exception as e:
        logger.warning(f"Failed to connect to DB Sync PostgreSQL: {e}")
        _pool = None
        return None


async def close_pool():
    """Close the connection pool during shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("DB Sync connection pool closed")


async def query(sql: str, *args, timeout: float = 30.0) -> List:
    """Execute a read-only query against DB Sync."""
    pool = await get_pool()
    if pool is None:
        raise ConnectionError("DB Sync pool unavailable")
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args, timeout=timeout)


async def query_one(sql: str, *args, timeout: float = 30.0):
    """Execute a query expecting at most one row."""
    pool = await get_pool()
    if pool is None:
        raise ConnectionError("DB Sync pool unavailable")
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, *args, timeout=timeout)


async def is_available() -> bool:
    """Health check: can we reach DB Sync?"""
    try:
        pool = await get_pool()
        if pool is None:
            return False
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1", timeout=5)
        return True
    except Exception:
        return False
