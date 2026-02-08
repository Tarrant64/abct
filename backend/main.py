"""
ABCT Main Application Module

This is the entry point for the ABCT (A Better Crypto Tracker) FastAPI application.
It initializes the database, sets up API routers, serves the frontend, and manages
background tasks for portfolio snapshots and NFT price collection.

Startup Sequence:
    1. Initialize SQLite database schema
    2. Launch background task for portfolio snapshot (every 2 hours)
    3. Launch background task for incremental NFT floor price collection
    4. Register all API routers
    5. Mount static files for frontend
    6. Start Uvicorn ASGI server

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
from routers import wallets, portfolio, defi, prices, exchanges, nfts, custom_tokens, settings, security, logs, nft_scheduler as nft_scheduler_router, backup, auth, dashboard, mobile, nmkr, cache, spam, transactions, demo, cloudflare, system, balance_history

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

    # Check if we need to create today's portfolio snapshot (runs in background)
    async def create_snapshot_background():
        try:
            from services.snapshot import snapshot_service
            from services.rate_limit_tracker import rate_limit_tracker

            startup_status["snapshot_check"] = "loading"

            # Check if we should run snapshot creation (30 minute cooldown)
            should_run, reason = await rate_limit_tracker.should_run_task(
                task_name='portfolio_snapshot',
                service='portfolio',
                cooldown_minutes=30
            )

            if not should_run:
                logger.info(f"Skipping portfolio snapshot: {reason}")
                startup_status["snapshot_check"] = "skipped"
                return

            logger.info("Checking for portfolio snapshot...")
            await snapshot_service.check_and_create_snapshot()
            startup_status["snapshot_check"] = "ready"

            # Mark task as run
            await rate_limit_tracker.mark_task_run('portfolio_snapshot', 'portfolio', 'auto')

            # Auto-generate historical data if no snapshots exist for any user
            try:
                from database import get_all_users, get_portfolio_history
                users = await get_all_users()
                non_demo_users = [u for u in users if not u.get('is_demo', False)]
                for user in non_demo_users:
                    uid = user['id']
                    existing = await get_portfolio_history(days=30, user_id=uid)
                    if not existing or len(existing) < 2:
                        logger.info(f"No historical snapshots for user {uid}, auto-generating 30 days...")
                        await snapshot_service.generate_historical_data(days=30, user_id=uid)
                        logger.info(f"Historical data generated for user {uid}")
            except Exception as hist_error:
                logger.warning(f"Could not auto-generate historical data: {hist_error}")

            # Warm the portfolio cache for faster page loads (separate cooldown check)
            try:
                should_warm, warm_reason = await rate_limit_tracker.should_run_task(
                    task_name='cache_warm',
                    service='portfolio',
                    cooldown_minutes=10  # Shorter cooldown for cache warming
                )

                if should_warm:
                    logger.info("Warming portfolio cache...")
                    from routers.portfolio import get_portfolio_summary
                    await get_portfolio_summary(refresh=False)
                    logger.info("Portfolio cache warmed successfully")
                    await rate_limit_tracker.mark_task_run('cache_warm', 'portfolio', 'auto')
                else:
                    logger.info(f"Skipping cache warm: {warm_reason}")
            except Exception as cache_error:
                logger.warning(f"Could not warm portfolio cache: {cache_error}")

            # Warm price cache for faster initial page loads
            try:
                from services.pricing import pricing_service
                logger.info("Warming price cache...")
                await pricing_service.get_prices(['ADA', 'BTC', 'ETH', 'SOL', 'MATIC'])
                logger.info("Price cache warmed successfully")
            except Exception as price_error:
                logger.warning(f"Could not warm price cache: {price_error}")

        except Exception as e:
            startup_status["snapshot_check"] = "error"
            logger.warning(f"Could not check/create portfolio snapshot: {e}")

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

    # Periodic snapshot task - runs every 2 hours to create snapshots
    async def periodic_snapshot_task():
        """Background task that creates portfolio snapshots every 2 hours."""
        import asyncio
        from services.snapshot import snapshot_service

        while True:
            try:
                # Wait 2 hours between snapshots
                await asyncio.sleep(2 * 3600)

                logger.info("Periodic snapshot task: Creating portfolio snapshots...")
                await log_service.info("main", "Periodic snapshot task: Creating portfolio snapshots")

                await snapshot_service.check_and_create_snapshot()

                logger.info("Periodic snapshot task: Snapshot creation complete")
                await log_service.info("main", "Periodic snapshot task: Snapshot creation complete")
            except Exception as e:
                logger.error(f"Periodic snapshot task error: {e}")
                await log_service.error("main", f"Periodic snapshot task error: {e}")
                # Continue running despite errors
                await asyncio.sleep(3600)  # Wait 1 hour before retrying on error

    # Start background tasks (non-blocking)
    asyncio.create_task(create_snapshot_background())
    asyncio.create_task(collect_nft_prices_background())
    asyncio.create_task(periodic_snapshot_task())

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

    yield

    # Shutdown: Stop NFT scheduler
    logger.info("Shutting down NFT scheduler...")
    await nft_scheduler.stop()

    # Shutdown: Close all shared HTTP clients
    logger.info("Closing shared HTTP clients...")
    from services.http_client import close_all
    await close_all()

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
    version="1.0.0",
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

@app.get("/wallets.html")
async def wallets_page():
    """Serve the Wallet Manager page."""
    return FileResponse(str(frontend_path / "wallets.html"))

@app.get("/settings.html")
async def settings_page():
    """Serve the consolidated Settings page (APIs, Services, Security, Backup)."""
    return FileResponse(str(frontend_path / "settings.html"))

@app.get("/system.html")
async def system_page():
    """Serve the consolidated System page (Cache, Logs)."""
    return FileResponse(str(frontend_path / "system.html"))

# Legacy redirects — old URLs redirect to consolidated pages
@app.get("/apis.html")
async def apis_redirect():
    """Redirect to Settings page (API Keys tab)."""
    return RedirectResponse(url="/settings.html#apis", status_code=301)

@app.get("/services.html")
async def services_redirect():
    """Redirect to System page (Services tab)."""
    return RedirectResponse(url="/system.html#services", status_code=301)

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
    """Redirect to System page (Logs tab)."""
    return RedirectResponse(url="/system.html#logs", status_code=301)

@app.get("/api-help.html")
async def api_help_page():
    """Serve the API Reference documentation page."""
    return FileResponse(str(frontend_path / "api-help.html"))

@app.get("/dashv2.html")
async def dashv2_page():
    """Serve the DashV2 experimental widget dashboard page."""
    return FileResponse(str(frontend_path / "dashv2.html"))

@app.get("/cache.html")
async def cache_redirect():
    """Redirect to System page (Cache tab)."""
    return RedirectResponse(url="/system.html#cache", status_code=301)

@app.get("/transactions.html")
async def transactions_redirect():
    """Redirect to Wallets page (Transactions tab)."""
    return RedirectResponse(url="/wallets.html#transactions", status_code=301)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ABCT"}

@app.get("/api/startup-status")
async def get_startup_status():
    """Get startup status for background tasks."""
    return startup_status

@app.get("/api/status")
async def api_status():
    """Get API status and configuration."""
    from config import (
        BLOCKFROST_API_KEY, CEXPLORER_API_KEY, COINBASE_API_KEY_NAME,
        ALCHEMY_API_KEY, HELIUS_API_KEY, NFT_IMAGE_DB_PATH
    )
    from services.nft_image_service import nft_image_service

    # Check NFT image cache status
    image_cache_enabled = False
    try:
        image_cache_enabled = await nft_image_service.is_enabled()
    except Exception:
        pass

    return {
        "status": "running",
        "apis": {
            "blockfrost": "configured" if BLOCKFROST_API_KEY else "missing",
            "cexplorer": "configured" if CEXPLORER_API_KEY else "missing",
            "blockstream": "available",  # No key required
            "coinbase": "configured" if COINBASE_API_KEY_NAME else "missing",
            "alchemy": "configured" if ALCHEMY_API_KEY else "missing",
            "helius": "configured" if HELIUS_API_KEY else "missing"
        },
        "supported_blockchains": ["cardano", "bitcoin", "ethereum", "solana", "polygon", "base"],
        "supported_exchanges": ["coinbase"] if COINBASE_API_KEY_NAME else [],
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
