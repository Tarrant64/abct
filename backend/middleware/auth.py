"""
Authentication Middleware - HTTP Basic Auth for ABCT

Provides HTTP Basic Auth verification for admin endpoints:
- Credentials from environment variables (ABCT_ADMIN_USER, ABCT_ADMIN_PASSWORD)
- Constant-time comparison to prevent timing attacks
- Optional localhost bypass (ABCT_REQUIRE_AUTH=false)
- Secure credential handling

Usage:
    from middleware.auth import verify_admin

    @router.post("/endpoint", dependencies=[Depends(verify_admin)])
    async def protected_endpoint():
        ...
"""

import os
import hmac
import secrets
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Optional

# Initialize HTTP Basic Auth
security = HTTPBasic()


def get_admin_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    Get admin credentials from environment variables.

    Returns:
        Tuple of (username, password) or (None, None) if not configured
    """
    username = os.getenv('ABCT_ADMIN_USER')
    password = os.getenv('ABCT_ADMIN_PASSWORD')
    return username, password


def is_auth_required() -> bool:
    """
    Check if authentication is required.

    Returns False if ABCT_REQUIRE_AUTH is explicitly set to 'false' (case-insensitive).
    Returns True otherwise (default behavior is to require auth).
    """
    require_auth = os.getenv('ABCT_REQUIRE_AUTH', 'true').lower()
    return require_auth != 'false'


def constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time to prevent timing attacks.

    Args:
        a: First string to compare
        b: Second string to compare

    Returns:
        True if strings are equal, False otherwise
    """
    # Use hmac.compare_digest for constant-time comparison
    # This prevents timing attacks where an attacker could measure
    # response times to guess credentials character by character
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


async def verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Verify HTTP Basic Auth credentials for admin access.

    This dependency can be added to any endpoint that requires authentication:
        @router.post("/endpoint", dependencies=[Depends(verify_admin)])
        async def protected_endpoint():
            ...

    Args:
        credentials: HTTP Basic Auth credentials from the request

    Returns:
        Username if authentication succeeds

    Raises:
        HTTPException: 401 Unauthorized if credentials are invalid or missing
        HTTPException: 503 Service Unavailable if auth is required but not configured
    """
    # Check if auth is disabled (for local development)
    if not is_auth_required():
        return "localhost"

    # Get configured credentials
    admin_user, admin_password = get_admin_credentials()

    # If credentials not configured but auth is required, return 503
    if not admin_user or not admin_password:
        raise HTTPException(
            status_code=503,
            detail="Authentication is required but not configured. Set ABCT_ADMIN_USER and ABCT_ADMIN_PASSWORD environment variables."
        )

    # Verify username and password using constant-time comparison
    username_correct = constant_time_compare(credentials.username, admin_user)
    password_correct = constant_time_compare(credentials.password, admin_password)

    if not (username_correct and password_correct):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm=\"ABCT Admin\""},
        )

    return credentials.username


async def optional_verify_admin(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> Optional[str]:
    """
    Optional authentication dependency.

    Similar to verify_admin, but allows requests without credentials if auth is disabled.
    Use this for endpoints that should work without auth in development but require it in production.

    Args:
        credentials: HTTP Basic Auth credentials from the request (optional)

    Returns:
        Username if authenticated, None if auth is disabled

    Raises:
        HTTPException: 401 Unauthorized if credentials provided but invalid
    """
    if not is_auth_required():
        return None

    if credentials:
        return await verify_admin(credentials)

    return None
