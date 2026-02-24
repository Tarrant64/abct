"""
Token Metadata Cache Service

Maintains a local cache of cryptocurrency metadata (supply data, rankings,
ATH/ATL, descriptions) to eliminate real-time dependency on CoinGecko for
static/slow-changing data. Populated from CoinGecko + CoinPaprika on startup
and refreshed periodically (every 24h).
"""

import aiosqlite
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import DATABASE_PATH
from services.http_client import get_client, fetch_with_retry

logger = logging.getLogger(__name__)

# Re-import the symbol mapping to know which tokens we track
from services.pricing import ASSET_TO_COINGECKO
from services.coinpaprika import SYMBOL_TO_COINPAPRIKA, coinpaprika_service

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# How old a row can be before we consider it stale and re-fetch
STALE_THRESHOLD_HOURS = 24


class TokenMetadataCacheService:
    """Maintains a SQLite cache of token metadata from CoinGecko + CoinPaprika."""

    def __init__(self) -> None:
        self._cg_api_key: Optional[str] = None
        self._cg_key_loaded = False

    # ------------------------------------------------------------------
    # CoinGecko API key (avoids circular import from pricing_service)
    # ------------------------------------------------------------------
    async def _get_cg_headers(self) -> dict:
        """Get CoinGecko request headers with API key if configured."""
        if not self._cg_key_loaded:
            try:
                from database import get_api_key
                self._cg_api_key = await get_api_key("coingecko")
                if self._cg_api_key:
                    logger.info("TokenMetadataCache: CoinGecko API key loaded")
            except Exception:
                pass
            self._cg_key_loaded = True

        headers = {"Accept": "application/json"}
        if self._cg_api_key:
            headers["x-cg-demo-api-key"] = self._cg_api_key
        return headers

    # ------------------------------------------------------------------
    # 1. Table initialization
    # ------------------------------------------------------------------
    async def init_table(self) -> None:
        """Create the token_metadata_cache table if it does not exist."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS token_metadata_cache (
                    symbol TEXT PRIMARY KEY,
                    coingecko_id TEXT,
                    coinpaprika_id TEXT,
                    name TEXT,
                    image_url TEXT,
                    image_thumb TEXT,
                    market_cap_rank INTEGER,
                    circulating_supply REAL,
                    total_supply REAL,
                    max_supply REAL,
                    ath REAL,
                    ath_date TEXT,
                    atl REAL,
                    atl_date TEXT,
                    description TEXT,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            logger.info("token_metadata_cache table initialized")

    # ------------------------------------------------------------------
    # 2. Single-row getters
    # ------------------------------------------------------------------
    async def get_metadata(self, symbol: str) -> Optional[dict]:
        """Return the full cached metadata row for a symbol, or None."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM token_metadata_cache WHERE symbol = ?",
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def get_supply(self, symbol: str) -> dict:
        """Return {circulating, total, max} supply for a symbol."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT circulating_supply, total_supply, max_supply "
                "FROM token_metadata_cache WHERE symbol = ?",
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"circulating": None, "total": None, "max": None}
            return {
                "circulating": row[0],
                "total": row[1],
                "max": row[2],
            }

    async def get_rank(self, symbol: str) -> Optional[int]:
        """Return market cap rank for a symbol, or None."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT market_cap_rank FROM token_metadata_cache WHERE symbol = ?",
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_ath_atl(self, symbol: str) -> dict:
        """Return {ath, ath_date, atl, atl_date} for a symbol."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT ath, ath_date, atl, atl_date "
                "FROM token_metadata_cache WHERE symbol = ?",
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"ath": None, "ath_date": None, "atl": None, "atl_date": None}
            return {
                "ath": row[0],
                "ath_date": row[1],
                "atl": row[2],
                "atl_date": row[3],
            }

    async def get_image(self, symbol: str) -> Optional[str]:
        """Return cached image URL for a symbol, or None."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT image_url FROM token_metadata_cache WHERE symbol = ?",
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------
    # 3. Upsert
    # ------------------------------------------------------------------
    async def upsert_metadata(self, symbol: str, data: dict) -> None:
        """Insert or update a single token metadata entry."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """
                INSERT INTO token_metadata_cache (
                    symbol, coingecko_id, coinpaprika_id, name,
                    image_url, image_thumb,
                    market_cap_rank,
                    circulating_supply, total_supply, max_supply,
                    ath, ath_date, atl, atl_date,
                    description, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    coingecko_id = COALESCE(excluded.coingecko_id, coingecko_id),
                    coinpaprika_id = COALESCE(excluded.coinpaprika_id, coinpaprika_id),
                    name = COALESCE(excluded.name, name),
                    image_url = COALESCE(excluded.image_url, image_url),
                    image_thumb = COALESCE(excluded.image_thumb, image_thumb),
                    market_cap_rank = COALESCE(excluded.market_cap_rank, market_cap_rank),
                    circulating_supply = COALESCE(excluded.circulating_supply, circulating_supply),
                    total_supply = COALESCE(excluded.total_supply, total_supply),
                    max_supply = COALESCE(excluded.max_supply, max_supply),
                    ath = COALESCE(excluded.ath, ath),
                    ath_date = COALESCE(excluded.ath_date, ath_date),
                    atl = COALESCE(excluded.atl, atl),
                    atl_date = COALESCE(excluded.atl_date, atl_date),
                    description = COALESCE(excluded.description, description),
                    last_updated = excluded.last_updated
                """,
                (
                    symbol.upper(),
                    data.get("coingecko_id"),
                    data.get("coinpaprika_id"),
                    data.get("name"),
                    data.get("image_url"),
                    data.get("image_thumb"),
                    data.get("market_cap_rank"),
                    data.get("circulating_supply"),
                    data.get("total_supply"),
                    data.get("max_supply"),
                    data.get("ath"),
                    data.get("ath_date"),
                    data.get("atl"),
                    data.get("atl_date"),
                    data.get("description"),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

    # ------------------------------------------------------------------
    # 4. Bulk read
    # ------------------------------------------------------------------
    async def get_all_cached(self) -> List[dict]:
        """Return all cached entries as a list of dicts."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM token_metadata_cache")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # 5. Cache warming
    # ------------------------------------------------------------------
    async def warm_cache(self) -> None:
        """
        Populate / refresh the metadata cache.

        Strategy:
        1. Fetch CoinGecko /coins/markets for top 250 (1 API call).
        2. Match against ASSET_TO_COINGECKO to populate our tracked symbols.
        3. For any symbols still missing, fetch from CoinPaprika.
        4. Upsert all results into the cache table.
        """
        logger.info("TokenMetadataCache: starting cache warm")

        # Build reverse map: coingecko_id -> symbol
        cg_id_to_symbol: Dict[str, str] = {
            cg_id: sym for sym, cg_id in ASSET_TO_COINGECKO.items()
        }

        # Determine which symbols are stale or missing
        symbols_to_update = await self._get_stale_symbols()
        if not symbols_to_update:
            logger.info("TokenMetadataCache: all entries fresh, skipping warm")
            return

        populated_symbols: set = set()

        # ----- Step 1: CoinGecko /coins/markets (top 250) -----
        try:
            populated_symbols = await self._warm_from_coingecko(
                cg_id_to_symbol, symbols_to_update
            )
            logger.info(
                "TokenMetadataCache: CoinGecko populated %d symbols",
                len(populated_symbols),
            )
        except Exception as e:
            logger.warning("TokenMetadataCache: CoinGecko warm failed: %s", e)

        # ----- Step 2: CoinPaprika supplement for missing symbols -----
        missing = symbols_to_update - populated_symbols
        if missing:
            try:
                paprika_count = await self._warm_from_coinpaprika(missing)
                logger.info(
                    "TokenMetadataCache: CoinPaprika supplemented %d symbols",
                    paprika_count,
                )
            except Exception as e:
                logger.warning("TokenMetadataCache: CoinPaprika warm failed: %s", e)

        logger.info("TokenMetadataCache: cache warm complete")

    # ------------------------------------------------------------------
    # Internal: determine stale / missing symbols
    # ------------------------------------------------------------------
    async def _get_stale_symbols(self) -> set:
        """Return the set of tracked symbols that are stale or missing from cache."""
        all_tracked = set(ASSET_TO_COINGECKO.keys())
        cutoff = (datetime.utcnow() - timedelta(hours=STALE_THRESHOLD_HOURS)).isoformat()

        fresh_symbols: set = set()
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT symbol FROM token_metadata_cache WHERE last_updated > ?",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            fresh_symbols = {row[0] for row in rows}

        return all_tracked - fresh_symbols

    # ------------------------------------------------------------------
    # Internal: CoinGecko warm
    # ------------------------------------------------------------------
    async def _warm_from_coingecko(
        self, cg_id_to_symbol: Dict[str, str], target_symbols: set
    ) -> set:
        """
        Fetch CoinGecko /coins/markets for the top 250 coins and upsert
        any that match our tracked symbols.

        Returns the set of symbols that were successfully populated.
        """
        populated: set = set()

        client = get_client("coingecko", timeout=30.0)
        headers = await self._get_cg_headers()

        response = await fetch_with_retry(
            client,
            "GET",
            f"{COINGECKO_BASE_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
            },
            headers=headers,
        )

        if response.status_code != 200:
            logger.warning(
                "TokenMetadataCache: CoinGecko /coins/markets returned %d",
                response.status_code,
            )
            return populated

        coins = response.json()
        for coin in coins:
            cg_id = coin.get("id", "")
            symbol = cg_id_to_symbol.get(cg_id)
            if symbol is None or symbol not in target_symbols:
                continue

            await self.upsert_metadata(
                symbol,
                {
                    "coingecko_id": cg_id,
                    "name": coin.get("name"),
                    "image_url": coin.get("image"),
                    "image_thumb": coin.get("image"),  # markets endpoint returns one size
                    "market_cap_rank": coin.get("market_cap_rank"),
                    "circulating_supply": coin.get("circulating_supply"),
                    "total_supply": coin.get("total_supply"),
                    "max_supply": coin.get("max_supply"),
                    "ath": coin.get("ath"),
                    "ath_date": coin.get("ath_date"),
                    "atl": coin.get("atl"),
                    "atl_date": coin.get("atl_date"),
                },
            )
            populated.add(symbol)

        return populated

    # ------------------------------------------------------------------
    # Internal: CoinPaprika warm (supplement)
    # ------------------------------------------------------------------
    async def _warm_from_coinpaprika(self, missing_symbols: set) -> int:
        """
        For each missing symbol, fetch metadata from CoinPaprika and upsert.

        Uses CoinPaprika /tickers/{id} for supply/rank and /coins/{id} for
        descriptions. Throttled via the service's internal semaphore.

        Returns the count of symbols successfully populated.
        """
        count = 0

        async def _fetch_one(symbol: str) -> None:
            nonlocal count
            cp_id = SYMBOL_TO_COINPAPRIKA.get(symbol)
            if not cp_id:
                return

            # Fetch ticker data (supply, rank)
            ticker = await coinpaprika_service.get_coin_market_data(cp_id)
            if not ticker:
                return

            # Fetch coin details (description, logo)
            details = await coinpaprika_service.get_coin_details(cp_id)

            quotes = ticker.get("quotes", {}).get("USD", {})

            await self.upsert_metadata(
                symbol,
                {
                    "coinpaprika_id": cp_id,
                    "name": ticker.get("name"),
                    "image_url": details.get("logo") if details else None,
                    "market_cap_rank": ticker.get("rank"),
                    "circulating_supply": ticker.get("circulating_supply"),
                    "total_supply": ticker.get("total_supply"),
                    "max_supply": ticker.get("max_supply"),
                    "ath": quotes.get("ath_price"),
                    "ath_date": quotes.get("ath_date"),
                    "description": details.get("description") if details else None,
                },
            )
            count += 1

        # Run in parallel with reasonable concurrency
        await asyncio.gather(
            *[_fetch_one(s) for s in missing_symbols],
            return_exceptions=True,
        )
        return count


# Singleton
metadata_cache = TokenMetadataCacheService()
