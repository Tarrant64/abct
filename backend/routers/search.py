"""
Global Search Router

Provides a unified search endpoint that queries wallets and cached portfolio tokens.
Used by the frontend global search component in the header.
"""

from fastapi import APIRouter, Depends, Query
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_cache
from auth_utils import verify_session

import aiosqlite
from config import DATABASE_PATH

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(
    q: str = Query(..., min_length=2, max_length=100),
    user_id: int = Depends(verify_session),
):
    """Search wallets and tokens across the portfolio"""
    query = q.strip().lower()

    # 1. Search wallets by label or address
    wallets = []
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, address, label, blockchain FROM wallets
                   WHERE user_id = ? AND (LOWER(label) LIKE ? OR LOWER(address) LIKE ?)
                   LIMIT 3""",
                (user_id, f"%{query}%", f"%{query}%"),
            )
            rows = await cursor.fetchall()
            wallets = [
                {
                    "id": row["id"],
                    "address": row["address"],
                    "label": row["label"],
                    "blockchain": row["blockchain"],
                }
                for row in rows
            ]
    except Exception:
        pass

    # 2. Search tokens from cached portfolio assets
    tokens = []
    try:
        cached = await get_cache("native_assets_all", user_id=user_id)
        if cached:
            assets = json.loads(cached) if isinstance(cached, str) else cached
            if isinstance(assets, dict):
                # Handle both list and dict formats
                asset_list = assets.get("assets", assets.get("tokens", []))
                if isinstance(asset_list, dict):
                    asset_list = list(asset_list.values())
            elif isinstance(assets, list):
                asset_list = assets
            else:
                asset_list = []

            for asset in asset_list:
                if not isinstance(asset, dict):
                    continue
                ticker = (asset.get("ticker") or asset.get("symbol") or "").lower()
                name = (asset.get("asset_name") or asset.get("name") or "").lower()
                if query in ticker or query in name:
                    tokens.append(
                        {
                            "ticker": asset.get("ticker") or asset.get("symbol", ""),
                            "name": asset.get("asset_name") or asset.get("name", ""),
                            "blockchain": asset.get("blockchain", ""),
                            "total_value_usd": asset.get("total_value_usd", 0),
                            "price_usd": asset.get("price_usd") or asset.get("price", 0),
                            "logo_url": asset.get("logo_url") or asset.get("logo", ""),
                        }
                    )
                    if len(tokens) >= 4:
                        break
    except Exception:
        pass

    return {"tokens": tokens, "wallets": wallets}
