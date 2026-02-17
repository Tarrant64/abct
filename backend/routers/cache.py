"""
Cache Management Router - Endpoints for viewing and clearing application caches

Provides granular control over different cache types:
- Token logos
- NFT images and metadata
- NFT floor prices
- Portfolio snapshots
- API response cache
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import verify_session
from typing import Dict

router = APIRouter(prefix="/api/cache", tags=["cache"])
logger = logging.getLogger(__name__)


@router.get("/stats")
async def get_cache_stats(user_id: int = Depends(verify_session)):
    """
    Get statistics about all caches.

    Returns item counts and estimated sizes for each cache type.
    """
    import aiosqlite
    from config import DATABASE_PATH, NFT_IMAGE_DB_PATH
    import os

    stats = {}

    try:
        # Token logos cache
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM token_metadata WHERE logo_url IS NOT NULL AND logo_url != ''"
            )
            row = await cursor.fetchone()
            stats['token_logos'] = {
                'count': row[0] if row else 0,
                'description': 'Cached token logo URLs'
            }

        # NFT images cache
        try:
            if os.path.exists(NFT_IMAGE_DB_PATH):
                async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
                    cursor = await db.execute("SELECT COUNT(*) FROM nft_images")
                    row = await cursor.fetchone()
                    stats['nft_images'] = {
                        'count': row[0] if row else 0,
                        'description': 'Cached NFT images (base64)'
                    }

                    # Get total size
                    cursor = await db.execute(
                        "SELECT SUM(LENGTH(image_data)) FROM nft_images"
                    )
                    row = await cursor.fetchone()
                    size_bytes = row[0] if row and row[0] else 0
                    stats['nft_images']['size_mb'] = round(size_bytes / 1024 / 1024, 2)
            else:
                stats['nft_images'] = {'count': 0, 'description': 'NFT image cache (not initialized)'}
        except Exception as e:
            logger.warning(f"Could not get NFT image stats: {e}")
            stats['nft_images'] = {'count': 0, 'description': 'NFT image cache (error)'}

        # NFT floor prices cache
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM nft_floor_prices")
            row = await cursor.fetchone()
            stats['nft_floor_prices'] = {
                'count': row[0] if row else 0,
                'description': 'Cached NFT floor prices'
            }

        # Portfolio snapshots
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM portfolio_snapshots WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            stats['portfolio_snapshots'] = {
                'count': row[0] if row else 0,
                'description': 'Historical portfolio snapshots'
            }

        # API response cache
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM cache WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            stats['api_cache'] = {
                'count': row[0] if row else 0,
                'description': 'Cached API responses'
            }

        # Database file sizes
        stats['database_sizes'] = {
            'portfolio_db': round(os.path.getsize(DATABASE_PATH) / 1024 / 1024, 2) if os.path.exists(DATABASE_PATH) else 0,
            'nft_images_db': round(os.path.getsize(NFT_IMAGE_DB_PATH) / 1024 / 1024, 2) if os.path.exists(NFT_IMAGE_DB_PATH) else 0,
        }

        return stats

    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache statistics: {str(e)}")


@router.post("/clear/token-logos")
async def clear_token_logos_cache(user_id: int = Depends(verify_session)):
    """Clear all cached token logo URLs."""
    import aiosqlite
    from config import DATABASE_PATH

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE token_metadata SET logo_url = NULL")
            await db.commit()

        logger.info("Cleared token logos cache")
        return {"success": True, "message": "Token logo cache cleared"}

    except Exception as e:
        logger.error(f"Error clearing token logos cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/clear/nft-images")
async def clear_nft_images_cache(user_id: int = Depends(verify_session)):
    """Clear all cached NFT images."""
    import aiosqlite
    from config import NFT_IMAGE_DB_PATH
    import os

    try:
        if os.path.exists(NFT_IMAGE_DB_PATH):
            async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
                await db.execute("DELETE FROM nft_images")
                await db.commit()
                await db.execute("VACUUM")  # Reclaim space

            logger.info("Cleared NFT images cache")
            return {"success": True, "message": "NFT images cache cleared"}
        else:
            return {"success": True, "message": "NFT images cache does not exist"}

    except Exception as e:
        logger.error(f"Error clearing NFT images cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/clear/nft-floor-prices")
async def clear_nft_floor_prices_cache(user_id: int = Depends(verify_session)):
    """Clear all cached NFT floor prices."""
    import aiosqlite
    from config import DATABASE_PATH

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM nft_floor_prices")
            await db.commit()

        logger.info("Cleared NFT floor prices cache")
        return {"success": True, "message": "NFT floor prices cache cleared"}

    except Exception as e:
        logger.error(f"Error clearing NFT floor prices cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/clear/portfolio-snapshots")
async def clear_portfolio_snapshots_cache(user_id: int = Depends(verify_session)):
    """Clear portfolio snapshots (keeps last 7 days)."""
    import aiosqlite
    from config import DATABASE_PATH

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Keep last 7 days of snapshots
            await db.execute("""
                DELETE FROM portfolio_snapshots
                WHERE user_id = ?
                AND snapshot_date < date('now', '-7 days')
            """, (user_id,))
            await db.commit()

        logger.info(f"Cleared old portfolio snapshots for user {user_id}")
        return {"success": True, "message": "Old portfolio snapshots cleared (kept last 7 days)"}

    except Exception as e:
        logger.error(f"Error clearing portfolio snapshots: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/clear/staking-cache")
async def clear_staking_cache(user_id: int = Depends(verify_session)):
    """Clear staking and DeFi position caches (system-wide, not user-scoped)."""
    import aiosqlite
    from config import DATABASE_PATH

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM cache WHERE key LIKE 'staking_positions_%' OR key LIKE 'iagon_staking_%' OR key LIKE 'iagon_scan_state_%' OR key LIKE 'defi_summary_%'"
            )
            deleted = cursor.rowcount
            await db.commit()

        logger.info(f"Cleared {deleted} staking/DeFi cache entries")
        return {"success": True, "message": f"Cleared {deleted} staking cache entries", "deleted": deleted}

    except Exception as e:
        logger.error(f"Error clearing staking cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/clear/api-cache")
async def clear_api_cache(user_id: int = Depends(verify_session)):
    """Clear all API response caches."""
    import aiosqlite
    from config import DATABASE_PATH

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM cache WHERE user_id = ?", (user_id,))
            await db.commit()

        logger.info(f"Cleared API cache for user {user_id}")
        return {"success": True, "message": "API response cache cleared"}

    except Exception as e:
        logger.error(f"Error clearing API cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/clear/all")
async def clear_all_caches(user_id: int = Depends(verify_session)):
    """
    Clear ALL caches (nuclear option).

    Warning: This will clear:
    - Token logos
    - NFT images
    - NFT floor prices
    - Portfolio snapshots (except last 7 days)
    - API response cache
    """
    try:
        results = []

        # Clear each cache type
        result = await clear_token_logos_cache(user_id)
        results.append(("Token Logos", result.get('success', False)))

        result = await clear_nft_images_cache(user_id)
        results.append(("NFT Images", result.get('success', False)))

        result = await clear_nft_floor_prices_cache(user_id)
        results.append(("NFT Floor Prices", result.get('success', False)))

        result = await clear_portfolio_snapshots_cache(user_id)
        results.append(("Portfolio Snapshots", result.get('success', False)))

        result = await clear_api_cache(user_id)
        results.append(("API Cache", result.get('success', False)))

        success_count = sum(1 for _, success in results if success)

        logger.info(f"Cleared all caches for user {user_id}: {success_count}/{len(results)} successful")

        return {
            "success": True,
            "message": f"Cleared {success_count}/{len(results)} cache types",
            "details": [{"type": t, "success": s} for t, s in results]
        }

    except Exception as e:
        logger.error(f"Error clearing all caches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear caches: {str(e)}")


@router.post("/optimize")
async def optimize_databases(user_id: int = Depends(verify_session)):
    """Run VACUUM on all databases to reclaim space."""
    import aiosqlite
    from config import DATABASE_PATH, NFT_IMAGE_DB_PATH
    import os

    try:
        results = []

        # Optimize main database
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("VACUUM")
        results.append(("portfolio.db", True))

        # Optimize NFT images database
        if os.path.exists(NFT_IMAGE_DB_PATH):
            async with aiosqlite.connect(NFT_IMAGE_DB_PATH) as db:
                await db.execute("VACUUM")
            results.append(("nft_images.db", True))

        logger.info(f"Optimized databases for user {user_id}")

        return {
            "success": True,
            "message": "Databases optimized",
            "details": [{"database": db, "success": s} for db, s in results]
        }

    except Exception as e:
        logger.error(f"Error optimizing databases: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to optimize databases: {str(e)}")
