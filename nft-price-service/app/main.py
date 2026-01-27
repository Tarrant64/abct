"""
Cardano NFT Floor Price Service

A standalone microservice that continuously fetches Cardano NFT floor prices from TapTools
and exposes them via REST API. Designed to run 24/7 on a server to work around
TapTools API rate limits (100 calls/day).

Strategy:
- Spread API calls across 24 hours (~4 calls/hour max)
- Prioritize high-value collections
- Store all prices in SQLite for fast retrieval
- Expose REST API for ABCT to query
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List, Dict

import httpx
import aiosqlite
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Configuration
TAPTOOLS_API_KEY = os.getenv("TAPTOOLS_API_KEY", "")
TAPTOOLS_BASE_URL = "https://openapi.taptools.io/api/v1"
DATABASE_PATH = os.getenv("DATABASE_PATH", "/app/data/nft_prices.db")
UPDATE_INTERVAL_MINUTES = int(os.getenv("UPDATE_INTERVAL_MINUTES", "15"))
CALLS_PER_UPDATE = int(os.getenv("CALLS_PER_UPDATE", "1"))  # Conservative: 4/hour = 96/day

# Security Configuration
ALLOWED_ORIGINS = os.getenv("NFT_SERVICE_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
SERVICE_HOST = os.getenv("NFT_SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("NFT_SERVICE_PORT", "8080"))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cardano-nft-price-service")

# Global state
db: Optional[aiosqlite.Connection] = None
scheduler: Optional[AsyncIOScheduler] = None
service_stats = {
    "started_at": None,
    "total_updates": 0,
    "successful_updates": 0,
    "failed_updates": 0,
    "last_update": None,
    "last_error": None,
    "rate_limited_until": None
}


async def init_database():
    """Initialize SQLite database with required tables."""
    global db

    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row

    await db.executescript("""
        CREATE TABLE IF NOT EXISTS collections (
            policy_id TEXT PRIMARY KEY,
            name TEXT,
            supply INTEGER,
            holders INTEGER,
            floor_price REAL,
            floor_price_ada REAL,
            volume_24h REAL,
            volume_7d REAL,
            volume_30d REAL,
            listings INTEGER,
            last_updated TEXT,
            priority INTEGER DEFAULT 0,
            update_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS nft_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_id TEXT NOT NULL,
            asset_name TEXT,
            unit TEXT UNIQUE,
            floor_price REAL,
            listing_price REAL,
            last_sale_price REAL,
            rarity_rank INTEGER,
            last_updated TEXT,
            FOREIGN KEY (policy_id) REFERENCES collections(policy_id)
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_id TEXT NOT NULL,
            floor_price REAL,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS api_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT,
            status_code INTEGER,
            called_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_nft_policy ON nft_prices(policy_id);
        CREATE INDEX IF NOT EXISTS idx_nft_unit ON nft_prices(unit);
        CREATE INDEX IF NOT EXISTS idx_history_policy ON price_history(policy_id);
        CREATE INDEX IF NOT EXISTS idx_collections_priority ON collections(priority DESC);
    """)
    await db.commit()
    logger.info(f"Database initialized at {DATABASE_PATH}")


async def close_database():
    """Close database connection."""
    global db
    if db:
        await db.close()
        db = None


async def get_api_calls_today() -> int:
    """Count API calls made today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cursor = await db.execute(
        "SELECT COUNT(*) FROM api_calls WHERE called_at >= ?",
        (f"{today} 00:00:00",)
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def log_api_call(endpoint: str, status_code: int):
    """Log an API call for rate limit tracking."""
    await db.execute(
        "INSERT INTO api_calls (endpoint, status_code, called_at) VALUES (?, ?, ?)",
        (endpoint, status_code, datetime.utcnow().isoformat())
    )
    await db.commit()


async def fetch_collection_floor(policy_id: str) -> Optional[Dict]:
    """Fetch floor price for a single collection from TapTools."""
    if not TAPTOOLS_API_KEY:
        logger.warning("TapTools API key not configured")
        return None

    # Check rate limit
    calls_today = await get_api_calls_today()
    if calls_today >= 95:  # Leave buffer
        logger.warning(f"Rate limit approaching: {calls_today}/100 calls today")
        service_stats["rate_limited_until"] = (
            datetime.utcnow().replace(hour=0, minute=0, second=0) + timedelta(days=1)
        ).isoformat()
        return None

    headers = {"x-api-key": TAPTOOLS_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get collection info
            response = await client.get(
                f"{TAPTOOLS_BASE_URL}/nft/collection/info",
                headers=headers,
                params={"policy": policy_id}
            )

            await log_api_call(f"collection/info/{policy_id[:12]}", response.status_code)

            if response.status_code == 429:
                logger.error("Rate limited by TapTools")
                service_stats["rate_limited_until"] = (
                    datetime.utcnow().replace(hour=0, minute=0, second=0) + timedelta(days=1)
                ).isoformat()
                return None

            if response.status_code != 200:
                logger.error(f"TapTools error: {response.status_code}")
                return None

            data = response.json()

            return {
                "policy_id": policy_id,
                "name": data.get("name", "Unknown"),
                "supply": data.get("supply", 0),
                "holders": data.get("holders", 0),
                "floor_price": data.get("floor", 0),
                "listings": data.get("listings", 0),
                "volume_24h": data.get("volume24h", 0),
                "volume_7d": data.get("volume7d", 0),
                "volume_30d": data.get("volume30d", 0)
            }

    except Exception as e:
        logger.error(f"Error fetching collection {policy_id[:12]}: {e}")
        return None


async def update_collection_price(policy_id: str, data: Dict):
    """Update collection price in database."""
    now = datetime.utcnow().isoformat()

    await db.execute("""
        INSERT INTO collections (
            policy_id, name, supply, holders, floor_price, floor_price_ada,
            listings, volume_24h, volume_7d, volume_30d, last_updated, update_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(policy_id) DO UPDATE SET
            name = excluded.name,
            supply = excluded.supply,
            holders = excluded.holders,
            floor_price = excluded.floor_price,
            floor_price_ada = excluded.floor_price,
            listings = excluded.listings,
            volume_24h = excluded.volume_24h,
            volume_7d = excluded.volume_7d,
            volume_30d = excluded.volume_30d,
            last_updated = excluded.last_updated,
            update_count = collections.update_count + 1
    """, (
        data["policy_id"],
        data["name"],
        data["supply"],
        data["holders"],
        data["floor_price"],
        data["floor_price"],
        data["listings"],
        data["volume_24h"],
        data["volume_7d"],
        data["volume_30d"],
        now
    ))

    # Record price history
    await db.execute(
        "INSERT INTO price_history (policy_id, floor_price) VALUES (?, ?)",
        (policy_id, data["floor_price"])
    )

    await db.commit()
    logger.info(f"Updated {data['name']}: {data['floor_price']} ADA")


async def get_next_collection_to_update() -> Optional[str]:
    """Get the next collection that needs updating based on priority and staleness."""
    # Prioritize: high priority, then oldest update
    cursor = await db.execute("""
        SELECT policy_id FROM collections
        WHERE last_updated < datetime('now', '-1 hour')
        ORDER BY priority DESC, last_updated ASC
        LIMIT 1
    """)
    row = await cursor.fetchone()
    return row["policy_id"] if row else None


async def scheduled_update():
    """Scheduled task to update collection prices."""
    service_stats["total_updates"] += 1

    try:
        # Check if rate limited
        if service_stats.get("rate_limited_until"):
            reset_time = datetime.fromisoformat(service_stats["rate_limited_until"])
            if datetime.utcnow() < reset_time:
                logger.info(f"Rate limited until {reset_time}")
                return
            else:
                service_stats["rate_limited_until"] = None

        # Get collections to update
        for _ in range(CALLS_PER_UPDATE):
            policy_id = await get_next_collection_to_update()
            if not policy_id:
                logger.info("No collections need updating")
                break

            data = await fetch_collection_floor(policy_id)
            if data:
                await update_collection_price(policy_id, data)
                service_stats["successful_updates"] += 1
            else:
                service_stats["failed_updates"] += 1

        service_stats["last_update"] = datetime.utcnow().isoformat()

    except Exception as e:
        logger.error(f"Scheduled update error: {e}")
        service_stats["last_error"] = str(e)
        service_stats["failed_updates"] += 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global scheduler

    # Startup
    await init_database()

    # Start scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_update,
        IntervalTrigger(minutes=UPDATE_INTERVAL_MINUTES),
        id="price_update",
        name="NFT Price Update"
    )
    scheduler.start()

    service_stats["started_at"] = datetime.utcnow().isoformat()
    logger.info(f"Service started. Update interval: {UPDATE_INTERVAL_MINUTES} minutes")

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown()
    await close_database()
    logger.info("Service stopped")


# FastAPI app
app = FastAPI(
    title="Cardano NFT Floor Price Service",
    description="Microservice for collecting and serving Cardano NFT floor prices from TapTools",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint with detailed status page."""
    # Get database stats
    calls_today = 0
    collections_total = 0
    collections_updated_today = 0
    collections_stale = 0

    if db:
        try:
            cursor = await db.execute("SELECT COUNT(*) FROM api_calls WHERE called_at >= date('now')")
            calls_today = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT COUNT(*) FROM collections")
            collections_total = (await cursor.fetchone())[0]

            cursor = await db.execute("""
                SELECT COUNT(*) FROM collections
                WHERE last_updated >= datetime('now', '-24 hours')
            """)
            collections_updated_today = (await cursor.fetchone())[0]

            cursor = await db.execute("""
                SELECT COUNT(*) FROM collections
                WHERE last_updated < datetime('now', '-1 hour') OR last_updated IS NULL
            """)
            collections_stale = (await cursor.fetchone())[0]
        except:
            pass

    # Calculate next run time
    next_run = "Unknown"
    if scheduler:
        job = scheduler.get_job("price_update")
        if job and job.next_run_time:
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Format last update time
    last_update = service_stats.get("last_update", "Never")
    if last_update and last_update != "Never":
        try:
            last_dt = datetime.fromisoformat(last_update)
            last_update = last_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            pass

    # Started at
    started_at = service_stats.get("started_at", "Unknown")
    if started_at and started_at != "Unknown":
        try:
            started_dt = datetime.fromisoformat(started_at)
            started_at = started_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            pass

    # Rate limit status
    rate_status = "OK"
    rate_color = "#4ade80"
    if service_stats.get("rate_limited_until"):
        rate_status = f"Limited until {service_stats['rate_limited_until']}"
        rate_color = "#f87171"
    elif calls_today >= 90:
        rate_status = "Warning - approaching limit"
        rate_color = "#fbbf24"

    # Progress percentage
    progress_pct = 0
    if collections_total > 0:
        progress_pct = round((collections_updated_today / collections_total) * 100, 1)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cardano NFT Price Service - Status</title>
        <meta http-equiv="refresh" content="30">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #e2e8f0;
                min-height: 100vh;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            h1 {{
                text-align: center;
                font-size: 2rem;
                margin-bottom: 10px;
                color: #60a5fa;
            }}
            .subtitle {{
                text-align: center;
                color: #94a3b8;
                margin-bottom: 40px;
            }}
            .status-card {{
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            .status-card h2 {{
                font-size: 1rem;
                color: #94a3b8;
                margin-bottom: 16px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .stat-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px;
            }}
            .stat-item {{
                background: rgba(0, 0, 0, 0.2);
                padding: 16px;
                border-radius: 8px;
            }}
            .stat-label {{
                font-size: 0.85rem;
                color: #94a3b8;
                margin-bottom: 4px;
            }}
            .stat-value {{
                font-size: 1.5rem;
                font-weight: 600;
                color: #f1f5f9;
            }}
            .stat-value.highlight {{
                color: #60a5fa;
            }}
            .stat-value.success {{
                color: #4ade80;
            }}
            .stat-value.warning {{
                color: #fbbf24;
            }}
            .progress-bar {{
                height: 8px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                overflow: hidden;
                margin-top: 12px;
            }}
            .progress-fill {{
                height: 100%;
                background: linear-gradient(90deg, #60a5fa, #a78bfa);
                border-radius: 4px;
                transition: width 0.3s ease;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 500;
            }}
            .badge-healthy {{
                background: rgba(74, 222, 128, 0.2);
                color: #4ade80;
            }}
            .timestamp {{
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 0.9rem;
            }}
            .footer {{
                text-align: center;
                margin-top: 40px;
                color: #64748b;
                font-size: 0.85rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Cardano NFT Floor Price Service</h1>
            <p class="subtitle">
                <span class="badge badge-healthy">Healthy</span>
                &nbsp;&middot;&nbsp; Auto-refreshes every 30 seconds
            </p>

            <div class="status-card">
                <h2>Scheduler Status</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-label">Last Update</div>
                        <div class="stat-value timestamp">{last_update}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Next Scheduled Run</div>
                        <div class="stat-value timestamp highlight">{next_run}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Update Interval</div>
                        <div class="stat-value">{UPDATE_INTERVAL_MINUTES} min</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Service Started</div>
                        <div class="stat-value timestamp">{started_at}</div>
                    </div>
                </div>
            </div>

            <div class="status-card">
                <h2>Collection Progress</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-label">Total Collections</div>
                        <div class="stat-value">{collections_total}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Updated (24h)</div>
                        <div class="stat-value success">{collections_updated_today}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Needs Update</div>
                        <div class="stat-value warning">{collections_stale}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Progress (24h)</div>
                        <div class="stat-value highlight">{progress_pct}%</div>
                    </div>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {progress_pct}%"></div>
                </div>
            </div>

            <div class="status-card">
                <h2>API Rate Limits (TapTools)</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-label">Calls Today</div>
                        <div class="stat-value">{calls_today} / 100</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Remaining</div>
                        <div class="stat-value highlight">{100 - calls_today}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Rate Status</div>
                        <div class="stat-value" style="color: {rate_color}">{rate_status}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Calls Per Update</div>
                        <div class="stat-value">{CALLS_PER_UPDATE}</div>
                    </div>
                </div>
            </div>

            <div class="status-card">
                <h2>Update Statistics</h2>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-label">Total Update Cycles</div>
                        <div class="stat-value">{service_stats.get('total_updates', 0)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Successful Updates</div>
                        <div class="stat-value success">{service_stats.get('successful_updates', 0)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Failed Updates</div>
                        <div class="stat-value" style="color: #f87171">{service_stats.get('failed_updates', 0)}</div>
                    </div>
                </div>
            </div>

            <div class="footer">
                Cardano NFT Floor Price Service v1.0 &middot; Part of ABCT
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@app.get("/status")
async def get_status():
    """Get service status and statistics."""
    calls_today = await get_api_calls_today() if db else 0

    cursor = await db.execute("SELECT COUNT(*) FROM collections")
    collection_count = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM nft_prices")
    nft_count = (await cursor.fetchone())[0]

    return {
        **service_stats,
        "api_calls_today": calls_today,
        "api_calls_remaining": 100 - calls_today,
        "collections_tracked": collection_count,
        "nfts_tracked": nft_count,
        "update_interval_minutes": UPDATE_INTERVAL_MINUTES,
        "taptools_configured": bool(TAPTOOLS_API_KEY)
    }


@app.get("/collections")
async def list_collections(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_floor: float = Query(0, ge=0)
):
    """List all tracked collections with floor prices."""
    cursor = await db.execute("""
        SELECT * FROM collections
        WHERE floor_price >= ?
        ORDER BY floor_price DESC
        LIMIT ? OFFSET ?
    """, (min_floor, limit, offset))

    rows = await cursor.fetchall()
    return {
        "collections": [dict(row) for row in rows],
        "count": len(rows),
        "limit": limit,
        "offset": offset
    }


@app.get("/collections/{policy_id}")
async def get_collection(policy_id: str):
    """Get a specific collection by policy ID."""
    cursor = await db.execute(
        "SELECT * FROM collections WHERE policy_id = ?",
        (policy_id,)
    )
    row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Collection not found")

    return dict(row)


@app.get("/collections/{policy_id}/history")
async def get_collection_history(
    policy_id: str,
    days: int = Query(7, ge=1, le=90)
):
    """Get price history for a collection."""
    cursor = await db.execute("""
        SELECT floor_price, recorded_at FROM price_history
        WHERE policy_id = ? AND recorded_at >= datetime('now', ?)
        ORDER BY recorded_at ASC
    """, (policy_id, f"-{days} days"))

    rows = await cursor.fetchall()
    return {
        "policy_id": policy_id,
        "days": days,
        "history": [dict(row) for row in rows]
    }


@app.get("/floor/{policy_id}")
async def get_floor_price(policy_id: str):
    """Get floor price for a collection (simple endpoint for ABCT)."""
    cursor = await db.execute(
        "SELECT floor_price, last_updated FROM collections WHERE policy_id = ?",
        (policy_id,)
    )
    row = await cursor.fetchone()

    if not row:
        return {"policy_id": policy_id, "floor_price": None, "found": False}

    return {
        "policy_id": policy_id,
        "floor_price": row["floor_price"],
        "last_updated": row["last_updated"],
        "found": True
    }


@app.get("/floors")
async def get_multiple_floors(policy_ids: str = Query(..., description="Comma-separated policy IDs")):
    """Get floor prices for multiple collections at once."""
    ids = [p.strip() for p in policy_ids.split(",") if p.strip()]

    if not ids:
        return {"floors": {}}

    placeholders = ",".join("?" * len(ids))
    cursor = await db.execute(
        f"SELECT policy_id, floor_price, last_updated FROM collections WHERE policy_id IN ({placeholders})",
        ids
    )

    rows = await cursor.fetchall()
    floors = {row["policy_id"]: {
        "floor_price": row["floor_price"],
        "last_updated": row["last_updated"]
    } for row in rows}

    return {"floors": floors, "found": len(floors), "requested": len(ids)}


@app.post("/collections/register")
async def register_collection(policy_id: str, name: str = None, priority: int = 0):
    """Register a new collection to track."""
    await db.execute("""
        INSERT INTO collections (policy_id, name, priority, last_updated)
        VALUES (?, ?, ?, datetime('now', '-2 hours'))
        ON CONFLICT(policy_id) DO UPDATE SET
            priority = excluded.priority,
            name = COALESCE(excluded.name, collections.name)
    """, (policy_id, name, priority))
    await db.commit()

    return {"registered": True, "policy_id": policy_id, "priority": priority}


@app.post("/collections/register-batch")
async def register_collections_batch(collections: List[Dict]):
    """Register multiple collections at once."""
    registered = 0
    for coll in collections:
        policy_id = coll.get("policy_id")
        if policy_id:
            await db.execute("""
                INSERT INTO collections (policy_id, name, priority, last_updated)
                VALUES (?, ?, ?, datetime('now', '-2 hours'))
                ON CONFLICT(policy_id) DO NOTHING
            """, (policy_id, coll.get("name"), coll.get("priority", 0)))
            registered += 1

    await db.commit()
    return {"registered": registered, "total": len(collections)}


@app.post("/sync/trigger")
async def trigger_sync():
    """Manually trigger a sync (respects rate limits)."""
    calls_today = await get_api_calls_today()

    if calls_today >= 95:
        return {
            "triggered": False,
            "reason": "Rate limit reached",
            "calls_today": calls_today
        }

    # Run update in background
    asyncio.create_task(scheduled_update())

    return {
        "triggered": True,
        "calls_today": calls_today,
        "message": "Update triggered"
    }


@app.delete("/collections/{policy_id}")
async def remove_collection(policy_id: str):
    """Remove a collection from tracking."""
    await db.execute("DELETE FROM collections WHERE policy_id = ?", (policy_id,))
    await db.execute("DELETE FROM price_history WHERE policy_id = ?", (policy_id,))
    await db.commit()

    return {"deleted": True, "policy_id": policy_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT)
