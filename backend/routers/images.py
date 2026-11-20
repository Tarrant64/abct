"""
Token Image Proxy Router

Serves cached token images, fetching and caching on first request.
Prefix: /images
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth_utils import verify_session
from services.image_cache import image_cache_service, is_safe_symbol

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


@router.get("/token/{symbol}")
async def get_token_image(symbol: str, _user_id: int = Depends(verify_session)):
    """Serve the cached image for a token symbol.

    If the image is already on disk, serve it directly.
    If not, attempt to fetch and cache it first.
    If all sources fail, 404.
    """
    symbol = symbol.upper()
    if not is_safe_symbol(symbol):
        raise HTTPException(status_code=404, detail="Not found")

    # Try serving from cache
    path = await image_cache_service.get_image_path(symbol)
    if path:
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Not cached yet — attempt fetch
    path = await image_cache_service.get_or_fetch_image(symbol)
    if path:
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # All sources failed. LogoKit/Logostream are deliberately NOT used here:
    # their terms forbid server-side storage/proxying (hotlink-only), so they
    # are web-frontend-only for major coins.
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/status")
async def image_cache_status(_user_id: int = Depends(verify_session)):
    """Return image cache statistics."""
    stats = await image_cache_service.get_cache_stats()
    return {
        "total_cached": stats["total_cached"],
        "disk_usage_bytes": stats["disk_usage_bytes"],
        "disk_usage_mb": round(stats["disk_usage_bytes"] / (1024 * 1024), 2),
    }
