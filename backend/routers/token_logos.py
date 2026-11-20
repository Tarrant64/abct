"""
Cardano native-token logo + metadata endpoints for the mobile app.

GET /api/mobile/token-logo/{policy_id}/{asset_name_hex}  -> small PNG (<=128 px), cacheable, 404 when no source has a logo
GET /api/mobile/token-meta/{policy_id}/{asset_name_hex}  -> name / ticker / decimals / coingecko_id / has_logo / sources

Both require a session (verify_session), like every sibling under /api/mobile. Source chain: services/cardano_token_meta.py.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth_utils import verify_session
from services import cardano_token_meta as ctm

router = APIRouter(prefix="/api/mobile", tags=["mobile"])
logger = logging.getLogger(__name__)

RESOLVE_TIMEOUT = 25.0


def _ids(policy_id: str, asset_name_hex: str):
    p, n = (policy_id or "").lower(), (asset_name_hex or "").lower()
    if not ctm.valid_ids(p, n):
        raise HTTPException(status_code=400, detail="invalid policy id or asset name")
    return p, n


@router.get("/token-logo/{policy_id}/{asset_name_hex}")
async def get_token_logo(policy_id: str, asset_name_hex: str, request: Request, user_id: int = Depends(verify_session)):
    p, n = _ids(policy_id, asset_name_hex)
    blob = await ctm.get_logo_blob(p + n)
    if blob is None:
        try:
            meta = await asyncio.wait_for(ctm.resolve(p, n), timeout=RESOLVE_TIMEOUT)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="logo lookup timed out")
        if not meta.get("has_logo"):
            raise HTTPException(status_code=404, detail="no logo")
        blob = await ctm.get_logo_blob(p + n)
        if blob is None:
            raise HTTPException(status_code=404, detail="no logo")
    png, etag = blob
    quoted = f'"{etag}"'
    headers = {"ETag": quoted, "Cache-Control": "private, max-age=86400"}
    inm = request.headers.get("if-none-match")
    if inm and quoted in [x.strip() for x in inm.split(",")]:
        return Response(status_code=304, headers=headers)
    return Response(content=png, media_type="image/png", headers=headers)


@router.get("/token-meta/{policy_id}/{asset_name_hex}")
async def get_token_meta(policy_id: str, asset_name_hex: str, user_id: int = Depends(verify_session)):
    p, n = _ids(policy_id, asset_name_hex)
    try:
        m = await asyncio.wait_for(ctm.resolve(p, n), timeout=RESOLVE_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="metadata lookup timed out")
    import json
    try:
        sources = json.loads(m.get("sources") or "[]")
    except (TypeError, ValueError):
        sources = []
    return {
        "policy_id": p, "asset_name_hex": n, "name": m.get("name"), "ticker": m.get("ticker"),
        "decimals": m.get("decimals"), "coingecko_id": m.get("coingecko_id"),
        "has_logo": bool(m.get("has_logo")), "logo_url": ctm.logo_path(p, n) if m.get("has_logo") else None,
        "sources": sources, "status": m.get("status"),
    }
