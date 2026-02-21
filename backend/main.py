"""
ABCT Main Application Module

This is the entry point for the ABCT (A Better Crypto Tracker) FastAPI application.
It initializes the database, sets up API routers, serves the frontend, and manages
background tasks for portfolio snapshots and NFT price collection.

Startup Sequence:
    1. Initialize SQLite database schema
    2. Warm price caches and collect NFT floor prices
    3. Seed wallet sources and run off-chain collector (V2)
    4. Auto-materialize on-chain data from engine events
    5. Register all API routers
    6. Mount static files for frontend
    7. Start Uvicorn ASGI server

API Endpoints:
    - GET /           : Serve frontend dashboard
    - GET /health     : Health check endpoint
    - GET /api/status : API configuration status
    - /wallets/*      : Wallet management
    - /portfolio/*    : Portfolio summary and history
    - /prices/*       : Cryptocurrency prices
    - /defi/*         : DeFi/staking positions
    - /exchanges/*    : Exchange balances
    - /nfts/*         : NFT collection and prices

Usage:
    # Development (with auto-reload)
    python main.py

    # Production
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import sys
import os

# Add backend directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PROJECT_ROOT, DATA_DIR, CERTS_DIR, DEFAULT_CERT_PATH, DEFAULT_KEY_PATH, NFT_SCHEDULER_ENABLED
from database import init_db, init_encryption, migrate_encrypt_api_keys
from nft_image_database import init_nft_image_db
from routers import wallets, portfolio, defi, prices, exchanges, nfts, custom_tokens, settings, security, logs, nft_scheduler as nft_scheduler_router, backup, auth, dashboard, mobile, nmkr, cache, spam, transactions, demo, cloudflare, system, balance_history, analytics, intelligence, search, pnl
from routers import engine as engine_router

from middleware import RequestSizeLimitMiddleware, RATE_LIMITING_AVAILABLE
from services.logging_service import get_logging_service
from services.nft_scheduler import nft_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Startup status tracking
startup_status = {
    "database": "pending",
    "nft_image_db": "pending",
    "snapshot_check": "pending",
    "nft_prices": "pending",
    "nft_scheduler": "pending",
    "ready": False
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and check for snapshots on startup."""
    import asyncio

    # Initialize logging service first
    logger.info("Initializing logging service...")
    log_service = get_logging_service()
    await log_service.initialize()
    await log_service.info("main", "Application starting up")

    logger.info("Initializing database...")
    await init_db()
    startup_status["database"] = "ready"
    logger.info("Database initialized")
    await log_service.info("main", "Main database initialized")

    # Initialize V2 engine tables
    logger.info("Initializing V2 engine tables...")
    try:
        from engine.db import init_engine_tables
        await init_engine_tables()
        logger.info("V2 engine tables initialized")
        await log_service.info("main", "V2 engine tables initialized")
    except Exception as e:
        logger.warning(f"V2 engine table init failed: {e}")
        await log_service.warning("main", f"V2 engine table init failed: {e}")

    # Initialize API key encryption
    logger.info("Initializing API key encryption...")
    try:
        init_encryption()
        logger.info("API key encryption initialized")
        await log_service.info("main", "API key encryption initialized")
    except Exception as e:
        logger.error(f"Failed to initialize encryption: {e}")
        await log_service.error("main", f"Encryption initialization failed: {e}")

    # Migrate plaintext API keys to encrypted storage
    logger.info("Checking API key encryption migration...")
    try:
        await migrate_encrypt_api_keys()
        await log_service.info("main", "API key encryption migration complete")
    except Exception as e:
        logger.warning(f"API key encryption migration failed: {e}")
        await log_service.warning("main", f"API key encryption migration failed: {e}")

    # API health checks run in background (don't block startup)
    async def _run_health_checks_background():
        try:
            from services.api_health import run_startup_health_checks
            await asyncio.wait_for(run_startup_health_checks(), timeout=60.0)
            await log_service.info("main", "Startup API health checks complete")
        except asyncio.TimeoutError:
            logger.warning("Startup API health checks timed out after 60s, skipping")
            await log_service.warning("main", "Startup API health checks timed out")
        except Exception as e:
            logger.warning(f"Startup API health checks failed: {e}")
            await log_service.warning("main", f"Startup API health checks failed: {e}")

    # Clean up expired cache entries
    logger.info("Cleaning up expired cache entries...")
    try:
        from database import cleanup_expired_cache
        deleted_cache = await cleanup_expired_cache()
        logger.info(f"Cleaned up {deleted_cache} expired cache entries")
        await log_service.info("main", f"Expired cache cleanup: {deleted_cache} entries removed")
    except Exception as e:
        logger.warning(f"Expired cache cleanup failed: {e}")
        await log_service.warning("main", f"Expired cache cleanup failed: {e}")

    # Invalidate stale DeFi/staking response caches (ensures fresh logo data after code updates)
    logger.info("Clearing stale DeFi/staking response caches...")
    try:
        import aiosqlite
        from config import DATABASE_PATH
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM cache WHERE key LIKE 'defi_summary_%' OR key LIKE 'staking_positions_%'"
            )
            cleared = cursor.rowcount
            await db.commit()
            if cleared > 0:
                logger.info(f"Cleared {cleared} stale DeFi/staking cache entries")
    except Exception as e:
        logger.warning(f"DeFi cache cleanup failed: {e}")

    # Seed missing logos for known DeFi governance tokens (background, don't block startup)
    async def _seed_defi_logos_background():
        try:
            import aiosqlite
            from config import DATABASE_PATH
            from services.defi import DEFI_PROTOCOLS
            from services.http_client import get_client

            tokens_needing_logos = []
            async with aiosqlite.connect(DATABASE_PATH) as db:
                for pid, info in DEFI_PROTOCOLS.items():
                    token = info.get('token')
                    if not token or info.get('type') != 'governance':
                        continue
                    async with db.execute(
                        "SELECT logo_url FROM token_metadata WHERE policy_id = ? AND logo_url IS NOT NULL AND logo_url != '' LIMIT 1",
                        (pid,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if not row:
                            async with db.execute(
                                "SELECT logo_url FROM token_metadata WHERE ticker = ? AND logo_url IS NOT NULL AND logo_url != '' LIMIT 1",
                                (token,)
                            ) as cursor2:
                                row2 = await cursor2.fetchone()
                                if not row2:
                                    token_name_hex = token.encode('utf-8').hex()
                                    tokens_needing_logos.append((pid, token, token_name_hex))

            if tokens_needing_logos:
                logger.info(f"Seeding logos for {len(tokens_needing_logos)} DeFi tokens: {[t[1] for t in tokens_needing_logos]}")
                client = get_client("cardano_token_registry", timeout=10)
                for pid, token, hex_name in tokens_needing_logos:
                    try:
                        registry_url = f"https://raw.githubusercontent.com/cardano-foundation/cardano-token-registry/master/mappings/{pid}{hex_name}.json"
                        resp = await client.get(registry_url)
                        if resp.status_code == 200:
                            data = resp.json()
                            logo_b64 = data.get("logo", {}).get("value", "")
                            if logo_b64:
                                logo_data_uri = f"data:image/png;base64,{logo_b64}"
                                async with aiosqlite.connect(DATABASE_PATH) as db:
                                    await db.execute(
                                        """INSERT INTO token_metadata (asset_id, policy_id, ticker, logo_url, updated_at)
                                           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                                           ON CONFLICT(asset_id) DO UPDATE SET logo_url = ?, updated_at = CURRENT_TIMESTAMP""",
                                        (f"{pid}{hex_name}", pid, token, logo_data_uri, logo_data_uri)
                                    )
                                    await db.commit()
                                logger.info(f"Seeded logo for {token} ({len(logo_data_uri)} chars)")
                            else:
                                logger.debug(f"No logo in Token Registry for {token}")
                        else:
                            logger.debug(f"Token Registry returned {resp.status_code} for {token}")
                    except Exception as e:
                        logger.debug(f"Could not seed logo for {token}: {e}")
            else:
                logger.info("All DeFi token logos already cached")
        except Exception as e:
            logger.warning(f"DeFi logo seeding failed: {e}")

    # Clean up old API call logs (keep last 7 days)
    logger.info("Cleaning up old API call logs...")
    try:
        from database import cleanup_old_api_call_logs
        deleted_count = await cleanup_old_api_call_logs(days_to_keep=7)
        logger.info(f"Cleaned up {deleted_count} old API call log entries")
        await log_service.info("main", f"API call log cleanup: {deleted_count} entries removed")
    except Exception as e:
        logger.warning(f"API call log cleanup failed: {e}")
        await log_service.warning("main", f"API call log cleanup failed: {e}")

    # Initialize authentication tables
    logger.info("Initializing authentication system...")
    try:
        from routers.auth import init_auth_tables
        await init_auth_tables()
        logger.info("Authentication system initialized")
        await log_service.info("main", "Authentication system initialized")
    except Exception as e:
        logger.warning(f"Could not initialize auth tables: {e}")
        await log_service.warning("main", f"Auth initialization failed: {e}")

    # Initialize NFT image cache database (separate from main DB)
    logger.info("Initializing NFT image cache database...")
    await init_nft_image_db()
    startup_status["nft_image_db"] = "ready"
    logger.info("NFT image cache database initialized")
    await log_service.info("main", "NFT image cache database initialized")

    # Warm caches on startup (prices + portfolio) — no V1 snapshot needed
    async def warm_caches_background():
        try:
            startup_status["snapshot_check"] = "loading"

            # Warm price cache for faster initial page loads
            try:
                from services.pricing import pricing_service
                logger.info("Warming price cache...")
                await pricing_service.get_prices(['ADA', 'BTC', 'ETH', 'SOL', 'MATIC'])
                logger.info("Price cache warmed successfully")
            except Exception as price_error:
                logger.warning(f"Could not warm price cache: {price_error}")

            startup_status["snapshot_check"] = "ready"
        except Exception as e:
            startup_status["snapshot_check"] = "error"
            logger.warning(f"Cache warming failed: {e}")

    # Incrementally collect NFT floor prices (runs in background)
    async def collect_nft_prices_background():
        try:
            from services.nft import nft_service
            from services.rate_limit_tracker import rate_limit_tracker

            startup_status["nft_prices"] = "loading"

            # CRITICAL: Taptools has very strict rate limits (100 requests/day on $9/mo plan)
            # Use aggressive 4-hour cooldown to protect the API key
            should_run, reason = await rate_limit_tracker.should_run_task(
                task_name='nft_floor_prices',
                service='taptools',
                cooldown_minutes=240  # 4 HOURS for Taptools protection
            )

            if not should_run:
                logger.info(f"Skipping Taptools NFT floor price collection: {reason}")
                startup_status["nft_prices"] = "skipped"

                # Still load cached prices from database even if we skip API calls
                logger.info("Loading cached Cardano NFT floor prices from database...")
                loaded = await nft_service.load_floor_prices_from_db()
                logger.info(f"Loaded {loaded} cached Cardano floor prices from database")

                startup_status["ready"] = True
                return

            # First, load any stored prices from the database
            logger.info("Loading Cardano NFT floor prices from database...")
            loaded = await nft_service.load_floor_prices_from_db()
            logger.info(f"Loaded {loaded} Cardano floor prices from database")

            # Then incrementally collect new prices (small batches to avoid rate limits)
            # Note: This is Cardano-only. Other chains (Ethereum, Solana, Polygon, Base)
            # fetch floor prices on-demand from their respective APIs (Alchemy, etc.)
            logger.info("Starting incremental Cardano NFT floor price collection...")
            result = await nft_service.collect_floor_prices_incremental(
                batch_size=5,  # 5 collections per batch
                max_batches=2  # Only 2 batches on startup to avoid blocking
            )
            startup_status["nft_prices"] = "ready"

            if result['status'] == 'rate_limited':
                # Mark Taptools as rate limited in the tracker
                await rate_limit_tracker.mark_rate_limited('taptools', recovery_minutes=1440)  # 24 hours
                logger.warning(f"Cardano NFT price collection rate limited after updating {result['collections_updated']} collections. Taptools blocked for 24 hours.")
            else:
                logger.info(f"Cardano NFT price collection: {result['status']}, updated {result['collections_updated']} collections")
                # Mark task as successfully run
                await rate_limit_tracker.mark_task_run('nft_floor_prices', 'taptools', 'auto')

        except Exception as e:
            startup_status["nft_prices"] = "error"
            logger.warning(f"Could not collect Cardano NFT floor prices: {e}. Other chains (Ethereum, Solana, etc.) unaffected.")
        finally:
            # Mark overall ready once NFT prices are done (last task)
            startup_status["ready"] = True

    # Track all background tasks for graceful cancellation on shutdown
    _background_tasks = []

    # Start background tasks (non-blocking) — V1 snapshot tasks removed (V2 only)
    _background_tasks.append(asyncio.create_task(warm_caches_background()))
    _background_tasks.append(asyncio.create_task(collect_nft_prices_background()))
    _background_tasks.append(asyncio.create_task(_run_health_checks_background()))
    _background_tasks.append(asyncio.create_task(_seed_defi_logos_background()))

    # Seed wallet_sources and start off-chain collector (V2 per-wallet balances)
    async def offchain_collector_startup():
        try:
            from database import get_all_users, seed_wallet_sources
            from services.offchain_collector import offchain_collector

            users = await get_all_users()
            non_demo = [u for u in users if not u.get('is_demo', False)]
            for user in non_demo:
                await seed_wallet_sources(user['id'])
            logger.info(f"Wallet sources seeded for {len(non_demo)} user(s)")
            await log_service.info("main", f"Wallet sources seeded for {len(non_demo)} user(s)")

            # Initial off-chain collection (with timeout to prevent hang)
            try:
                await asyncio.wait_for(offchain_collector.collect_all_users(), timeout=120.0)
                logger.info("Initial off-chain collection complete")
                await log_service.info("main", "Initial off-chain collection complete")
            except asyncio.TimeoutError:
                logger.warning("Initial off-chain collection timed out after 120s, continuing")
                await log_service.warning("main", "Initial off-chain collection timed out")
        except Exception as e:
            logger.warning(f"Off-chain collector startup failed: {e}")
            await log_service.warning("main", f"Off-chain collector startup failed: {e}")

    async def periodic_offchain_collector():
        """Background task: collect off-chain balances every 2 hours."""
        from services.offchain_collector import offchain_collector
        while True:
            try:
                await asyncio.sleep(2 * 3600)
                logger.info("Periodic off-chain collector: Starting collection...")
                await log_service.info("main", "Periodic off-chain collector: Starting collection")
                await asyncio.wait_for(offchain_collector.collect_all_users(), timeout=300.0)
                logger.info("Periodic off-chain collector: Collection complete")
                await log_service.info("main", "Periodic off-chain collector: Collection complete")
            except asyncio.TimeoutError:
                logger.warning("Periodic off-chain collector timed out after 5min")
            except asyncio.CancelledError:
                logger.info("Periodic off-chain collector cancelled (shutdown)")
                raise
            except Exception as e:
                logger.error(f"Periodic off-chain collector error: {e}")
                await log_service.error("main", f"Periodic off-chain collector error: {e}")
                await asyncio.sleep(3600)

    # Auto-materialize on-chain data on startup if engine_events exist
    async def materialize_on_startup():
        try:
            from engine.materializer import materializer
            from engine import db as engine_db
            from database import get_all_users

            users = await get_all_users()
            non_demo = [u for u in users if not u.get('is_demo', False)]
            for user in non_demo:
                uid = user['id']
                event_count = await engine_db.get_event_count(uid)
                if event_count > 0:
                    logger.info(f"Startup materialize: user {uid} has {event_count} engine_events, materializing...")
                    await asyncio.wait_for(materializer.materialize_onchain(uid), timeout=180.0)
                else:
                    logger.info(f"Startup materialize: user {uid} has 0 engine_events, trying V1 balance_history...")
                    await asyncio.wait_for(
                        materializer.materialize_onchain_from_v1_balance_history(uid), timeout=120.0
                    )
                logger.info(f"Startup materialize: user {uid} complete")
        except asyncio.TimeoutError:
            logger.warning("Startup materialization timed out, will complete on next cycle")
            await log_service.warning("main", "Startup materialization timed out")
        except Exception as e:
            logger.warning(f"Startup materialization failed: {e}")
            await log_service.warning("main", f"Startup materialization failed: {e}")

    _background_tasks.append(asyncio.create_task(offchain_collector_startup()))
    _background_tasks.append(asyncio.create_task(periodic_offchain_collector()))
    _background_tasks.append(asyncio.create_task(materialize_on_startup()))
    logger.info("Off-chain collector + startup materialization started (V2 only)")

    # Initialize and optionally start NFT background scheduler
    startup_status["nft_scheduler"] = "initializing"
    try:
        logger.info("Initializing NFT background scheduler...")
        await nft_scheduler.initialize()

        if NFT_SCHEDULER_ENABLED or nft_scheduler.enabled:
            logger.info("NFT scheduler is enabled, starting...")
            await nft_scheduler.start()
            startup_status["nft_scheduler"] = "running"
            await log_service.info("main", "NFT background scheduler started")
        else:
            startup_status["nft_scheduler"] = "disabled"
            logger.info("NFT scheduler disabled (set NFT_SCHEDULER_ENABLED=true to enable)")

    except Exception as e:
        startup_status["nft_scheduler"] = "error"
        logger.warning(f"Could not initialize NFT scheduler: {e}")
        await log_service.warning("main", f"NFT scheduler initialization failed: {e}")

    # Initialize V2 engine orchestrator
    try:
        from engine.orchestrator import backfill_orchestrator
        await backfill_orchestrator.initialize()
        logger.info("V2 engine orchestrator initialized")
        await log_service.info("main", "V2 engine orchestrator initialized")

        # Start V2 auto-collect schedulers for users that have them enabled
        from database import get_all_users, get_user_setting
        users = await get_all_users()
        for user in users:
            uid = user['id']
            enabled = await get_user_setting(uid, 'balance_history_schedule_enabled', '0')
            interval = await get_user_setting(uid, 'balance_history_schedule_hours', '0')
            if enabled == '1' and int(interval) > 0:
                await backfill_orchestrator.start_auto_collect(uid, int(interval))
                logger.info(f"V2 auto-collect started for user {uid}, interval={interval}h")
                await log_service.info("main", f"V2 auto-collect started for user {uid}, interval={interval}h")
    except Exception as e:
        logger.warning(f"V2 engine orchestrator init failed: {e}")
        await log_service.warning("main", f"V2 engine orchestrator init failed: {e}")

    # Restore Cloudflare tunnel if a token was previously configured
    async def restore_cloudflare_tunnel():
        try:
            from routers.cloudflare import auto_restore_tunnel
            await auto_restore_tunnel()
        except Exception as e:
            logger.warning(f"Cloudflare tunnel auto-restore failed: {e}")
            await log_service.warning("main", f"Cloudflare tunnel auto-restore failed: {e}")

    _background_tasks.append(asyncio.create_task(restore_cloudflare_tunnel()))

    # Clear all chart caches on startup (ensures fresh data after materialization)
    try:
        from database import clear_cache, get_all_users
        users = await get_all_users()
        for user in users:
            uid = user['id']
            for r in ('24h', '1w', '1m', '3m', '6m', '1y', 'all'):
                await clear_cache(f"unified_chart_{uid}_{r}", user_id=uid)
                await clear_cache(f"unified_chart_{uid}_{r}_by_chain", user_id=uid)
        logger.info("Cleared all chart caches on startup")
    except Exception as e:
        logger.warning(f"Failed to clear chart cache: {e}")

    # Backfill balance_history prices in background (enables streamgraph historical data)
    async def backfill_history_prices():
        try:
            from database import get_unpriced_date_ranges, update_balance_history_prices
            from services.http_client import get_client, fetch_with_retry
            from services.pricing import ASSET_TO_COINGECKO, COINGECKO_BASE_URL, pricing_service
            from datetime import datetime as dt, timezone

            unpriced = await get_unpriced_date_ranges(user_id=1)
            if not unpriced:
                logger.info("Balance history: all prices up to date")
                return

            for entry in unpriced:
                symbol = entry['symbol']
                cg_id = ASSET_TO_COINGECKO.get(symbol)
                if not cg_id:
                    continue
                try:
                    dt_min = dt.strptime(entry['min_date'], '%Y-%m-%d')
                    dt_max = dt.strptime(entry['max_date'], '%Y-%m-%d')
                    days = min((dt_max - dt_min).days + 2, 365)  # CoinGecko demo API max
                except (ValueError, TypeError):
                    days = 365

                logger.info(f"Backfill: fetching {days}d of {symbol} prices")
                try:
                    client = get_client("coingecko_historical", timeout=30.0)
                    cg_headers = await pricing_service._get_cg_headers()
                    response = await fetch_with_retry(
                        client, "GET",
                        f"{COINGECKO_BASE_URL}/coins/{cg_id}/market_chart",
                        params={'vs_currency': 'usd', 'days': days},
                        headers=cg_headers,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        price_map = {}
                        for ts_ms, price in data.get('prices', []):
                            date_str = dt.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
                            price_map[date_str] = price
                        updated = await update_balance_history_prices(1, symbol, price_map)
                        logger.info(f"Backfill: {symbol} — {updated} records updated with {len(price_map)} prices")
                    else:
                        logger.warning(f"Backfill: {symbol} API returned {response.status_code}")
                    await asyncio.sleep(2)  # Rate limit courtesy
                except Exception as e:
                    logger.warning(f"Backfill: {symbol} failed: {e}")
        except Exception as e:
            logger.warning(f"Balance history price backfill failed: {e}")

    _background_tasks.append(asyncio.create_task(backfill_history_prices()))

    yield

    # --- Graceful shutdown ---
    logger.info("Shutdown initiated...")

    # 1. Cancel all tracked background tasks first (with timeout)
    logger.info(f"Cancelling {len(_background_tasks)} background tasks...")
    for task in _background_tasks:
        if not task.done():
            task.cancel()
    if _background_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*_background_tasks, return_exceptions=True),
                timeout=8.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Background task cancellation timed out after 8s, continuing shutdown")
    _background_tasks.clear()
    logger.info("Background tasks cancelled")

    # 2. Shut down services with an overall timeout
    async def _shutdown_services():
        # Stop V2 auto-collect schedulers
        try:
            from engine.orchestrator import backfill_orchestrator as bo
            for uid in list(bo._auto_collect_tasks.keys()):
                await bo.stop_auto_collect(uid)
            logger.info("V2 auto-collect schedulers stopped")
        except Exception as e:
            logger.warning(f"Error stopping V2 auto-collect: {e}")

        # Stop NFT scheduler
        logger.info("Shutting down NFT scheduler...")
        await nft_scheduler.stop()

        # Close all shared HTTP clients
        logger.info("Closing shared HTTP clients...")
        from services.http_client import close_all
        await close_all()

    try:
        await asyncio.wait_for(_shutdown_services(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Shutdown timed out after 10s, forcing exit")

    logger.info("Shutdown complete")

app = FastAPI(
    title="ABCT - A Better Crypto Tracker",
    description="""
## Welcome to ABCT API

A comprehensive cryptocurrency portfolio tracking system supporting multiple blockchains and asset types.

### 🌐 Supported Blockchains
- **Cardano** (ADA) - Native assets, staking, NFTs
- **Bitcoin** (BTC) - Native balance tracking
- **Ethereum** (ETH) - ERC-20 tokens, NFTs
- **Solana** (SOL) - SPL tokens, NFTs
- **Polygon** (POL/MATIC) - Native and token support
- **Base** (ETH) - Layer 2 support

### 🎯 Core Features
- **Multi-blockchain wallet tracking** - Monitor balances across all chains
- **NFT collections** - Track floor prices and valuations
- **DeFi positions** - Staking and protocol participation
- **Exchange integration** - Coinbase and more
- **Real-time pricing** - Multiple price feed integrations
- **Portfolio analytics** - Historical tracking and visualizations

### 🔐 Authentication
All endpoints require session-based authentication. Login at `/login.html` to access the API.

### ⚡ Rate Limits
API calls are rate-limited per endpoint. Check response headers for limit information.

### 📊 API Health
Monitor API utilization and service status at `/apis.html`
    """,
    version="1.12.3",
    contact={
        "name": "ABCT Project",
        "url": "https://github.com/Tarrant64/abct",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    docs_url="/docs",  # Swagger UI
    redoc_url="/api-reference",  # Redoc documentation
    lifespan=lifespan
)

# Add security middleware
# 1. Request size limiting (prevents DoS via large payloads)
app.add_middleware(RequestSizeLimitMiddleware)
logger.info("Request size limiting enabled (10MB default, 5MB uploads)")

# 2. Rate limiting (if slowapi is installed)
if RATE_LIMITING_AVAILABLE:
    from middleware import limiter, RateLimitMiddleware
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler
    app.state.limiter = limiter
    app.add_middleware(RateLimitMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("Rate limiting enabled (in-memory storage)")
else:
    logger.warning("Rate limiting not available - install slowapi for rate limiting")

# 3. GZip compression for responses (reduces bandwidth for large JSON responses)
app.add_middleware(GZipMiddleware, minimum_size=1000)
logger.info("GZip compression enabled (minimum 1000 bytes)")


# Custom exception handlers for CRIT-003
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """
    Global exception handler to prevent error disclosure (CRIT-003).

    Returns generic error messages to clients while logging full details internally.
    """
    from fastapi.responses import JSONResponse
    log_service = get_logging_service()

    # Log full error details internally
    await log_service.error(
        source="api",
        message=f"Unhandled exception in {request.method} {request.url.path}: {str(exc)}",
        exc_info=exc,
        method=request.method,
        path=str(request.url.path),
        client=request.client.host if request.client else "unknown"
    )

    # Return generic error to client (no sensitive details)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Handler for HTTP exceptions.

    Logs the error but allows HTTPException details through since they're
    controlled by the application.
    """
    from fastapi.responses import JSONResponse
    log_service = get_logging_service()

    # Log HTTP exceptions at warning level
    await log_service.warning(
        source="api",
        message=f"HTTP {exc.status_code} in {request.method} {request.url.path}: {exc.detail}",
        status_code=exc.status_code,
        method=request.method,
        path=str(request.url.path)
    )

    # Return the HTTPException detail (these are safe, controlled messages)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )

# Include routers
app.include_router(auth.router)  # Auth router first (no dependencies)
app.include_router(mobile.router)  # Mobile API
app.include_router(wallets.router)
app.include_router(portfolio.router)
app.include_router(defi.router)
app.include_router(prices.router)
app.include_router(exchanges.router)
app.include_router(nfts.router)
app.include_router(custom_tokens.router)
app.include_router(settings.router)
app.include_router(security.router)
app.include_router(logs.router)
app.include_router(nft_scheduler_router.router)
app.include_router(backup.router)
app.include_router(dashboard.router)
app.include_router(nmkr.router)
app.include_router(cache.router)
app.include_router(spam.router)
app.include_router(transactions.router)
app.include_router(demo.router)
app.include_router(cloudflare.router)
app.include_router(system.router)
app.include_router(balance_history.router)
app.include_router(engine_router.router)
app.include_router(analytics.router)
app.include_router(intelligence.router)
app.include_router(search.router)
app.include_router(pnl.router)

# Mount static files (frontend)
frontend_path = PROJECT_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

@app.get("/")
async def root():
    """Serve the main dashboard."""
    return FileResponse(str(frontend_path / "index.html"))

@app.get("/login.html")
async def login_page():
    """Serve the login page."""
    return FileResponse(str(frontend_path / "login.html"))

@app.get("/assets.html")
async def assets_page():
    """Serve the Assets page (Wallets, Exchanges, DeFi, Custom Tokens)."""
    return FileResponse(str(frontend_path / "assets.html"))

@app.get("/nfts.html")
async def nfts_page():
    """Serve the NFTs page (My NFTs + NFT Wall)."""
    return FileResponse(str(frontend_path / "nfts.html"))

@app.get("/nft-wall.html")
async def nft_wall():
    """Redirect NFT Wall to NFTs page (Wall tab)."""
    return RedirectResponse(url="/nfts.html#wall", status_code=301)

@app.get("/data.html")
async def data_page():
    """Serve the Data & Analytics page (Transactions, Analytics)."""
    return FileResponse(str(frontend_path / "data.html"))

@app.get("/wallets.html")
async def wallets_redirect():
    """Redirect old Wallets page to Data & Analytics."""
    return RedirectResponse(url="/data.html", status_code=301)

@app.get("/settings.html")
async def settings_page():
    """Serve the consolidated Settings page (APIs, Data Collectors, Cache, Logs, Services, Security, Backup)."""
    return FileResponse(str(frontend_path / "settings.html"))

@app.get("/system.html")
async def system_redirect():
    """Redirect old System page to Settings."""
    return RedirectResponse(url="/settings.html", status_code=301)

# Legacy redirects — old URLs redirect to consolidated pages
@app.get("/apis.html")
async def apis_redirect():
    """Redirect to Settings page (API Keys tab)."""
    return RedirectResponse(url="/settings.html#apis", status_code=301)

@app.get("/services.html")
async def services_redirect():
    """Redirect to Settings page (Services tab)."""
    return RedirectResponse(url="/settings.html#services", status_code=301)

@app.get("/security.html")
async def security_redirect():
    """Redirect to Settings page (Security tab)."""
    return RedirectResponse(url="/settings.html#security", status_code=301)

@app.get("/backup.html")
async def backup_redirect():
    """Redirect to Settings page (Backup tab)."""
    return RedirectResponse(url="/settings.html#backup", status_code=301)

@app.get("/logs.html")
async def logs_redirect():
    """Redirect to Settings page (Logs tab)."""
    return RedirectResponse(url="/settings.html#logs", status_code=301)

@app.get("/api-help.html")
async def api_help_page():
    """Serve the API Reference documentation page."""
    return FileResponse(str(frontend_path / "api-help.html"))

@app.get("/help.html")
async def help_page():
    """Serve the Help & Guide page."""
    return FileResponse(str(frontend_path / "help.html"))

@app.get("/dashv2.html")
async def dashv2_page():
    """Serve the DashV2 experimental widget dashboard page."""
    return FileResponse(str(frontend_path / "dashv2.html"))

@app.get("/cache.html")
async def cache_redirect():
    """Redirect to Settings page (Cache tab)."""
    return RedirectResponse(url="/settings.html#cache", status_code=301)

@app.get("/transactions.html")
async def transactions_redirect():
    """Redirect to Data & Analytics page (Transactions tab)."""
    return RedirectResponse(url="/data.html#transactions", status_code=301)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ABCT"}

@app.get("/api/config/public")
async def public_config():
    """Public config values needed by frontend (no auth required)."""
    from config import LOGOKIT_API_KEY
    return {"logokit_token": LOGOKIT_API_KEY}

@app.get("/api/startup-status")
async def get_startup_status():
    """Get startup status for background tasks."""
    return startup_status

@app.get("/api/status")
async def api_status():
    """Get API status and configuration."""
    from config import NFT_IMAGE_DB_PATH
    from database import get_all_api_settings
    from routers.settings import API_REGISTRY
    from services.nft_image_service import nft_image_service

    # Check NFT image cache status
    image_cache_enabled = False
    try:
        image_cache_enabled = await nft_image_service.is_enabled()
    except Exception:
        pass

    # Check API keys from both database and env vars
    # Same pattern as the working /api/apis endpoint
    saved_settings = await get_all_api_settings()
    saved_map = {s['api_name']: s for s in saved_settings}

    status_apis = {}
    check_apis = ['blockfrost', 'cexplorer', 'blockstream', 'coinbase', 'alchemy', 'helius']
    for api_id in check_apis:
        if api_id == 'blockstream':
            status_apis[api_id] = 'available'  # No key required
            continue
        saved = saved_map.get(api_id)
        has_db_key = bool(saved and saved.get('api_key'))
        has_env_key = bool(os.getenv(API_REGISTRY.get(api_id, {}).get('env_var', ''), '')) if api_id in API_REGISTRY else False
        status_apis[api_id] = 'configured' if (has_db_key or has_env_key) else 'missing'

    return {
        "status": "running",
        "apis": status_apis,
        "supported_blockchains": ["cardano", "bitcoin", "ethereum", "solana", "polygon", "base"],
        "supported_exchanges": ["coinbase"] if status_apis.get('coinbase') == 'configured' else [],
        "features": {
            "nft_image_cache": {
                "enabled": image_cache_enabled,
                "database": str(NFT_IMAGE_DB_PATH)
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Use string import path for reload to work properly
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
