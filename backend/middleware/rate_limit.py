"""
Rate Limiting Middleware

Implements rate limiting for sensitive endpoints to prevent abuse.

Configuration:
    - Certificate uploads: 5 requests per hour per IP
    - Certificate generation: 10 requests per hour per IP
    - Settings updates: 20 requests per hour per IP

Uses in-memory storage (can be upgraded to Redis for production).

Usage:
    from middleware.rate_limit import limiter, RateLimitMiddleware

    # Add to FastAPI app
    app.state.limiter = limiter
    app.add_middleware(RateLimitMiddleware)

    # Use decorator on specific endpoints
    @router.post("/endpoint")
    @limiter.limit("5/hour")
    async def protected_endpoint():
        ...
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request
import logging

logger = logging.getLogger(__name__)

# Create limiter instance
# Uses client IP address as the key for rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10000/day", "2000/hour"],  # Global default limits (generous for localhost)
    storage_uri="memory://",  # In-memory storage (use Redis in production)
    headers_enabled=True,  # Add rate limit info to response headers
)

# Rate limit configurations for specific endpoint patterns
RATE_LIMITS = {
    "certificate_upload": "5/hour",       # Certificate uploads
    "certificate_generate": "10/hour",    # Self-signed cert generation
    "settings_update": "20/hour",         # API key/settings updates
    "wallet_operations": "100/hour",      # Wallet add/delete operations
}


class RateLimitMiddleware(SlowAPIMiddleware):
    """
    Custom rate limiting middleware with logging.

    Extends SlowAPI middleware to add detailed logging of rate limit events.
    """

    async def __call__(self, scope, receive, send):
        """Process request with rate limiting."""
        try:
            return await super().__call__(scope, receive, send)
        except RateLimitExceeded as e:
            # Log rate limit exceeded events
            if scope["type"] == "http":
                request = Request(scope, receive=receive)
                client_ip = get_remote_address(request)
                path = request.url.path
                logger.warning(
                    f"Rate limit exceeded for {client_ip} on {path}: {str(e)}"
                )
            raise


def get_rate_limit_status():
    """
    Get current rate limit configuration.

    Returns:
        dict: Current rate limit settings
    """
    return {
        "enabled": True,
        "storage": "memory",  # Change to "redis" if using Redis
        "limits": RATE_LIMITS,
        "global_limits": limiter._default_limits,
        "headers_enabled": True,
        "note": "Rate limits are per IP address"
    }
