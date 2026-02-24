"""
Token Image Proxy Router

Serves cached token images, fetching and caching on first request.
Prefix: /images
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from auth_utils import verify_session
from services.image_cache import image_cache_service

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


@router.get("/token/{symbol}")
async def get_token_image(symbol: str, _user_id: int = Depends(verify_session)):
    """Serve the cached image for a token symbol.

    If the image is already on disk, serve it directly.
    If not, attempt to fetch and cache it first.
    If all sources fail, redirect to LogoKit.
    """
    symbol = symbol.upper()

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

    # All sources failed — redirect to LogoKit as last resort
    logokit_url = f"https://img.logokit.com/crypto/{symbol}?size=128"
    return RedirectResponse(
        url=logokit_url,
        status_code=302,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/status")
async def image_cache_status(_user_id: int = Depends(verify_session)):
    """Return image cache statistics."""
    stats = await image_cache_service.get_cache_stats()
    return {
        "total_cached": stats["total_cached"],
        "disk_usage_bytes": stats["disk_usage_bytes"],
        "disk_usage_mb": round(stats["disk_usage_bytes"] / (1024 * 1024), 2),
    }
