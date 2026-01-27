"""
ABCT Middleware Package

This package contains custom middleware for the ABCT application:
- size_limit: Request body size limiting to prevent DoS attacks
- rate_limit: Rate limiting for sensitive endpoints
- auth: HTTP Basic Auth for admin endpoints
- localhost: Localhost-only enforcement
"""

from .size_limit import RequestSizeLimitMiddleware

try:
    from .rate_limit import limiter, RateLimitMiddleware, get_rate_limit_status
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    # slowapi not installed - rate limiting disabled
    limiter = None
    RateLimitMiddleware = None
    get_rate_limit_status = None
    RATE_LIMITING_AVAILABLE = False

try:
    from .auth import verify_admin, optional_verify_admin
    AUTH_AVAILABLE = True
except ImportError:
    verify_admin = None
    optional_verify_admin = None
    AUTH_AVAILABLE = False

try:
    from .localhost import require_localhost, optional_localhost, is_localhost
    LOCALHOST_AVAILABLE = True
except ImportError:
    require_localhost = None
    optional_localhost = None
    is_localhost = None
    LOCALHOST_AVAILABLE = False

__all__ = [
    "RequestSizeLimitMiddleware",
    "limiter",
    "RateLimitMiddleware",
    "get_rate_limit_status",
    "verify_admin",
    "optional_verify_admin",
    "require_localhost",
    "optional_localhost",
    "is_localhost",
    "RATE_LIMITING_AVAILABLE",
    "AUTH_AVAILABLE",
    "LOCALHOST_AVAILABLE"
]
