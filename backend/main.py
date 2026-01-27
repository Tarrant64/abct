"""
ABCT Main Application Module

This is the entry point for the ABCT (A Better Crypto Tracker) FastAPI application.
It initializes the database, sets up API routers, serves the frontend, and manages
background tasks for portfolio snapshots and NFT price collection.

Startup Sequence:
    1. Initialize SQLite database schema
    2. Launch background task for portfolio snapshot (12 PM CT daily)
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
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import sys
import os

# Add backend directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PROJECT_ROOT, DATA_DIR, CERTS_DIR, DEFAULT_CERT_PATH, DEFAULT_KEY_PATH
from database import init_db
from nft_image_database import init_nft_image_db
from routers import wallets, portfolio, defi, prices, exchanges, nfts, custom_tokens, settings, security, logs

from middleware import RequestSizeLimitMiddleware, RATE_LIMITING_AVAILABLE
from services.logging_service import get_logging_service

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
            startup_status["snapshot_check"] = "loading"
            logger.info("Checking for portfolio snapshot...")
            await snapshot_service.check_and_create_snapshot()
            startup_status["snapshot_check"] = "ready"

            # Warm the portfolio cache for faster page loads
            try:
                logger.info("Warming portfolio cache...")
                from routers.portfolio import get_portfolio_summary
                await get_portfolio_summary(refresh=False)
                logger.info("Portfolio cache warmed successfully")
            except Exception as cache_error:
                logger.warning(f"Could not warm portfolio cache: {cache_error}")

        except Exception as e:
            startup_status["snapshot_check"] = "error"
            logger.warning(f"Could not check/create portfolio snapshot: {e}")

    # Incrementally collect NFT floor prices (runs in background)
    async def collect_nft_prices_background():
        try:
            from services.nft import nft_service

            startup_status["nft_prices"] = "loading"

            # First, load any stored prices from the database
            logger.info("Loading NFT floor prices from database...")
            loaded = await nft_service.load_floor_prices_from_db()
            logger.info(f"Loaded {loaded} floor prices from database")

            # Then incrementally collect new prices (small batches to avoid rate limits)
            logger.info("Starting incremental NFT floor price collection...")
            result = await nft_service.collect_floor_prices_incremental(
                batch_size=5,  # 5 collections per batch
                max_batches=2  # Only 2 batches on startup to avoid blocking
            )
            startup_status["nft_prices"] = "ready"
            logger.info(f"NFT price collection: {result['status']}, updated {result['collections_updated']} collections")

        except Exception as e:
            startup_status["nft_prices"] = "error"
            logger.warning(f"Could not collect NFT floor prices: {e}")
        finally:
            # Mark overall ready once NFT prices are done (last task)
            startup_status["ready"] = True

    # Start background tasks (non-blocking)
    asyncio.create_task(create_snapshot_background())
    asyncio.create_task(collect_nft_prices_background())

    yield

app = FastAPI(
    title="ABCT - Crypto Portfolio Tracker",
    description="Track your Cardano and Bitcoin portfolios",
    version="1.0.0",
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

# Mount static files (frontend)
frontend_path = PROJECT_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

@app.get("/")
async def root():
    """Serve the main dashboard."""
    return FileResponse(str(frontend_path / "index.html"))

@app.get("/nft-wall.html")
async def nft_wall():
    """Serve the NFT Wall gallery page."""
    return FileResponse(str(frontend_path / "nft-wall.html"))

@app.get("/wallets.html")
async def wallets_page():
    """Serve the Wallet Manager page."""
    return FileResponse(str(frontend_path / "wallets.html"))

@app.get("/apis.html")
async def apis_page():
    """Serve the API Manager page."""
    return FileResponse(str(frontend_path / "apis.html"))

@app.get("/services.html")
async def services_page():
    """Serve the Service Health page."""
    return FileResponse(str(frontend_path / "services.html"))

@app.get("/security.html")
async def security_page():
    """Serve the Security Settings page."""
    return FileResponse(str(frontend_path / "security.html"))

@app.get("/logs.html")
async def logs_page():
    """Serve the System Logs page."""
    return FileResponse(str(frontend_path / "logs.html"))

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
