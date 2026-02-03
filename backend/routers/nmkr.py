"""
NMKR Router - Proxy endpoint for NMKR token images

Provides a backend proxy for NMKR Studio API requests to hide the API key from frontend.
"""

import httpx
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from auth_utils import verify_session_optional
from services.nmkr_service import nmkr_service

router = APIRouter(prefix="/nmkr", tags=["nmkr"])
logger = logging.getLogger(__name__)

NMKR_BASE_URL = "https://studio-api.nmkr.io"


@router.get("/image/{policy_id}/{token_name_hex}")
async def get_token_image_proxy(
    policy_id: str,
    token_name_hex: str,
    user_id: Optional[int] = Depends(verify_session_optional)
):
    """
    Proxy NMKR token image requests through backend to hide API key.

    This endpoint fetches images from NMKR Studio API with proper authentication
    and returns the image to the frontend, preventing API key exposure.

    Authentication is optional - if not provided, uses default user (user_id=1).
    This allows image tags to load without auth headers.

    Args:
        policy_id: Cardano policy ID (hex)
        token_name_hex: Token name in hexadecimal format
        user_id: Authenticated user ID (optional, defaults to 1)

    Returns:
        Image data with appropriate content type

    Raises:
        HTTPException: If NMKR not configured, image not found, or request fails
    """
    # Use default user if not authenticated (for img tag requests)
    if user_id is None:
        user_id = 1

    # Get API key for user
    api_key = await nmkr_service.get_api_key(user_id)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="NMKR API not configured. Please add your NMKR API key in settings."
        )

    # Build NMKR API URL
    nmkr_url = f"{NMKR_BASE_URL}/v2/GetPreviewImageForToken/{policy_id}/{token_name_hex}"

    try:
        # Fetch image from NMKR with authentication
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                nmkr_url,
                headers={"Authorization": api_key}
            )

            if response.status_code == 200:
                # NMKR returns IPFS URLs (e.g., ipfs://Qm...), not actual images
                ipfs_url = response.text.strip()

                # Convert IPFS URL to HTTP gateway URL for browser display
                if ipfs_url.startswith("ipfs://"):
                    ipfs_hash = ipfs_url.replace("ipfs://", "")
                    # Use public IPFS gateway
                    http_url = f"https://ipfs.io/ipfs/{ipfs_hash}"
                    return Response(
                        content=http_url,
                        media_type="text/plain",
                        headers={
                            "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                            "X-NMKR-Proxy": "true",
                            "X-IPFS-Original": ipfs_url
                        }
                    )
                else:
                    # If not IPFS, return as-is (might be direct image URL)
                    return Response(
                        content=ipfs_url,
                        media_type="text/plain",
                        headers={
                            "Cache-Control": "public, max-age=86400",
                            "X-NMKR-Proxy": "true"
                        }
                    )
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Token image not found in NMKR")
            else:
                logger.warning(f"NMKR returned {response.status_code} for {policy_id}/{token_name_hex}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"NMKR API error: {response.text}"
                )

    except httpx.TimeoutException:
        logger.error(f"NMKR request timeout for {policy_id}/{token_name_hex}")
        raise HTTPException(status_code=504, detail="NMKR request timeout")
    except httpx.RequestError as e:
        logger.error(f"NMKR request failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch image from NMKR")
