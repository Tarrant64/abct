"""
NFT Image Database Module

Separate SQLite database for storing NFT images as BLOBs.
Keeps large binary data separate from the main portfolio.db text data.
"""

import aiosqlite
from datetime import datetime
from pathlib import Path
from config import NFT_IMAGE_DB_PATH, DATA_DIR
import logging

logger = logging.getLogger(__name__)


async def init_nft_image_db():
    """Initialize the NFT image database with required tables."""
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        # NFT images table - stores image BLOBs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nft_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                blockchain TEXT NOT NULL,
                image_url TEXT,
                image_data BLOB,
                image_format TEXT,
                image_size INTEGER,
                width INTEGER,
                height INTEGER,
                thumbnail_data BLOB,
                fetch_status TEXT DEFAULT 'pending',
                error_message TEXT,
                fetched_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(asset_id, blockchain)
            )
        """)

        # Indexes for efficient lookups
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_images_blockchain
            ON nft_images(blockchain)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_images_status
            ON nft_images(fetch_status)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_images_fetched
            ON nft_images(fetched_at)
        """)

        # Configuration table for image caching settings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS image_cache_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert default configuration if not exists
        defaults = [
            ('enabled', 'false'),
            ('max_image_size_bytes', '5242880'),  # 5MB
            ('generate_thumbnails', 'true'),
            ('thumbnail_size', '150'),
            ('auto_fetch_on_nft_load', 'false'),
            ('enabled_chains', '["cardano","ethereum","solana","polygon","base"]'),
        ]

        for key, value in defaults:
            await db.execute("""
                INSERT OR IGNORE INTO image_cache_config (key, value)
                VALUES (?, ?)
            """, (key, value))

        await db.commit()
        logger.info(f"NFT image database initialized at {NFT_IMAGE_DB_PATH}")


async def get_nft_image_db():
    """Get database connection for NFT images."""
    db = await aiosqlite.connect(NFT_IMAGE_DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ============================================================================
# Configuration Functions
# ============================================================================

async def get_image_cache_config() -> dict:
    """Get all image cache configuration settings."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT key, value FROM image_cache_config")
        rows = await cursor.fetchall()

        config = {}
        for row in rows:
            key = row['key']
            value = row['value']
            # Parse JSON arrays and booleans
            if value in ('true', 'false'):
                config[key] = value == 'true'
            elif value.startswith('[') or value.startswith('{'):
                import json
                config[key] = json.loads(value)
            elif value.isdigit():
                config[key] = int(value)
            else:
                config[key] = value
        return config


async def update_image_cache_config(key: str, value) -> bool:
    """Update a single configuration setting."""
    import json

    # Convert value to string for storage
    if isinstance(value, bool):
        str_value = 'true' if value else 'false'
    elif isinstance(value, (list, dict)):
        str_value = json.dumps(value)
    else:
        str_value = str(value)

    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        await db.execute("""
            INSERT INTO image_cache_config (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, str_value, datetime.now()))
        await db.commit()
        return True


async def is_image_cache_enabled() -> bool:
    """Check if image caching is enabled."""
    config = await get_image_cache_config()
    return config.get('enabled', False)


# ============================================================================
# Image Storage Functions
# ============================================================================

async def save_nft_image(
    asset_id: str,
    blockchain: str,
    image_url: str = None,
    image_data: bytes = None,
    image_format: str = None,
    width: int = None,
    height: int = None,
    thumbnail_data: bytes = None,
    fetch_status: str = 'pending',
    error_message: str = None
) -> int:
    """Save or update an NFT image in the database."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        image_size = len(image_data) if image_data else None
        fetched_at = datetime.now() if image_data else None

        cursor = await db.execute("""
            INSERT INTO nft_images (
                asset_id, blockchain, image_url, image_data, image_format,
                image_size, width, height, thumbnail_data, fetch_status,
                error_message, fetched_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, blockchain) DO UPDATE SET
                image_url = COALESCE(excluded.image_url, nft_images.image_url),
                image_data = COALESCE(excluded.image_data, nft_images.image_data),
                image_format = COALESCE(excluded.image_format, nft_images.image_format),
                image_size = COALESCE(excluded.image_size, nft_images.image_size),
                width = COALESCE(excluded.width, nft_images.width),
                height = COALESCE(excluded.height, nft_images.height),
                thumbnail_data = COALESCE(excluded.thumbnail_data, nft_images.thumbnail_data),
                fetch_status = excluded.fetch_status,
                error_message = excluded.error_message,
                fetched_at = COALESCE(excluded.fetched_at, nft_images.fetched_at),
                updated_at = excluded.updated_at
        """, (
            asset_id, blockchain, image_url, image_data, image_format,
            image_size, width, height, thumbnail_data, fetch_status,
            error_message, fetched_at, datetime.now()
        ))
        await db.commit()
        return cursor.lastrowid


async def get_nft_image(asset_id: str, blockchain: str) -> dict:
    """Get a cached NFT image by asset_id and blockchain."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM nft_images
            WHERE asset_id = ? AND blockchain = ?
        """, (asset_id, blockchain))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_nft_image_data(asset_id: str, blockchain: str) -> tuple:
    """Get just the image data and format for serving."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        cursor = await db.execute("""
            SELECT image_data, image_format FROM nft_images
            WHERE asset_id = ? AND blockchain = ? AND image_data IS NOT NULL
        """, (asset_id, blockchain))
        row = await cursor.fetchone()
        if row:
            return row[0], row[1]
        return None, None


async def get_nft_thumbnail_data(asset_id: str, blockchain: str) -> tuple:
    """Get just the thumbnail data and format for serving."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        cursor = await db.execute("""
            SELECT thumbnail_data, image_format FROM nft_images
            WHERE asset_id = ? AND blockchain = ? AND thumbnail_data IS NOT NULL
        """, (asset_id, blockchain))
        row = await cursor.fetchone()
        if row:
            return row[0], row[1]
        return None, None


async def get_pending_images(blockchain: str = None, limit: int = 50) -> list:
    """Get NFT images that are pending fetch."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if blockchain:
            cursor = await db.execute("""
                SELECT asset_id, blockchain, image_url FROM nft_images
                WHERE fetch_status = 'pending' AND blockchain = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (blockchain, limit))
        else:
            cursor = await db.execute("""
                SELECT asset_id, blockchain, image_url FROM nft_images
                WHERE fetch_status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,))

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_image_status(
    asset_id: str,
    blockchain: str,
    status: str,
    error_message: str = None
):
    """Update the fetch status of an image."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        await db.execute("""
            UPDATE nft_images
            SET fetch_status = ?, error_message = ?, updated_at = ?
            WHERE asset_id = ? AND blockchain = ?
        """, (status, error_message, datetime.now(), asset_id, blockchain))
        await db.commit()


# ============================================================================
# Statistics Functions
# ============================================================================

async def get_image_cache_stats() -> dict:
    """Get statistics about the image cache."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Total counts by status
        cursor = await db.execute("""
            SELECT
                blockchain,
                fetch_status,
                COUNT(*) as count,
                SUM(COALESCE(image_size, 0)) as total_size
            FROM nft_images
            GROUP BY blockchain, fetch_status
        """)
        rows = await cursor.fetchall()

        by_chain = {}
        total_images = 0
        total_size = 0

        for row in rows:
            chain = row['blockchain']
            status = row['fetch_status']
            count = row['count']
            size = row['total_size'] or 0

            if chain not in by_chain:
                by_chain[chain] = {'fetched': 0, 'pending': 0, 'failed': 0, 'skipped': 0, 'size_bytes': 0}

            by_chain[chain][status] = count
            if status == 'fetched':
                by_chain[chain]['size_bytes'] = size
                total_size += size
            total_images += count

        # Database file size
        db_size = 0
        if NFT_IMAGE_DB_PATH.exists():
            db_size = NFT_IMAGE_DB_PATH.stat().st_size

        return {
            'total_images': total_images,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'database_size_mb': round(db_size / (1024 * 1024), 2),
            'by_chain': by_chain
        }


async def clear_image_cache(blockchain: str = None) -> int:
    """Clear cached images. Optionally filter by blockchain."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        if blockchain:
            cursor = await db.execute(
                "DELETE FROM nft_images WHERE blockchain = ?",
                (blockchain,)
            )
        else:
            cursor = await db.execute("DELETE FROM nft_images")

        deleted = cursor.rowcount
        await db.commit()

        # Vacuum to reclaim space
        await db.execute("VACUUM")

        return deleted


async def has_cached_image(asset_id: str, blockchain: str) -> bool:
    """Check if an NFT has a cached image."""
    async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
        cursor = await db.execute("""
            SELECT 1 FROM nft_images
            WHERE asset_id = ? AND blockchain = ? AND fetch_status = 'fetched'
            LIMIT 1
        """, (asset_id, blockchain))
        row = await cursor.fetchone()
        return row is not None
