from fastapi import APIRouter, Depends, HTTPException
from auth_utils import verify_session
import aiosqlite
from config import DATABASE_PATH
from typing import Dict
import json
import logging

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


@router.get("/layout")
async def get_dashboard_layout(user_id: int = Depends(verify_session)):
    """Get saved dashboard layout for user."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT layout_data
                FROM dashboard_layouts
                WHERE user_id = ?
            """, (user_id,))

            row = await cursor.fetchone()

            if row:
                return json.loads(row[0])
            else:
                # Return default layout
                return get_default_layout()

    except Exception as e:
        logger.error(f"Error loading dashboard layout: {e}")
        raise HTTPException(500, "Failed to load dashboard layout")


@router.post("/layout")
async def save_dashboard_layout(
    layout: Dict,
    user_id: int = Depends(verify_session)
):
    """Save dashboard layout for user."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT OR REPLACE INTO dashboard_layouts (user_id, layout_data, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (user_id, json.dumps(layout)))

            await db.commit()

            return {"status": "saved"}

    except Exception as e:
        logger.error(f"Error saving dashboard layout: {e}")
        raise HTTPException(500, "Failed to save dashboard layout")


def get_default_layout():
    """Default widget layout."""
    return {
        "widgets": [
            {
                "id": "widget-1",
                "type": "portfolio-summary",
                "x": 0,
                "y": 0,
                "w": 4,
                "h": 3
            },
            {
                "id": "widget-2",
                "type": "blockchain-prices",
                "x": 4,
                "y": 0,
                "w": 4,
                "h": 3
            },
            {
                "id": "widget-3",
                "type": "price-chart",
                "x": 0,
                "y": 3,
                "w": 6,
                "h": 4
            },
            {
                "id": "widget-4",
                "type": "recent-wallets",
                "x": 6,
                "y": 3,
                "w": 3,
                "h": 4
            }
        ]
    }
