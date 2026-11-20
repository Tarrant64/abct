"""
Authentication Middleware - admin gate for ABCT

verify_admin accepts the normal session Bearer token when the session is the
admin account (see verify_admin). Optional bypass when ABCT_REQUIRE_AUTH=false.

Usage:
    from middleware.auth import verify_admin

    @router.post("/endpoint", dependencies=[Depends(verify_admin)])
    async def protected_endpoint():
        ...
"""

import os
import hmac
import aiosqlite
from fastapi import HTTPException, Header
from typing import Optional

from auth_utils import verify_session, ADMIN_USER_ID
from config import DATABASE_PATH


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


async def verify_admin(authorization: Optional[str] = Header(None)) -> str:
    """
    Admin gate for sensitive routes (security settings/certs, NFT image admin).

    Accepts the normal session login (Authorization: Bearer <token>) when the
    session belongs to the admin account. There is no separate Basic credential.

    The users table has no role/is_admin column. The admin is the primary,
    non-demo account: user id ADMIN_USER_ID (1), the account seeded at first run
    and the owner of all legacy data (auth_utils.verify_session also treats id 1
    as admin when auth is off). Demo and any other account get 403.

    Raises:
        401: no/invalid/expired token (auth required)
        403: valid session but not the admin account
    """
    # Auth disabled (dev/LAN mode): unchanged behaviour, tokenless == admin.
    if not is_auth_required():
        return "localhost"

    # Validates the Bearer token (401 on missing/invalid/expired)
    user_id = await verify_session(authorization)

    if user_id == ADMIN_USER_ID:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT username, is_demo FROM users WHERE id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
        if row and not row[1]:
            return row[0]

    raise HTTPException(status_code=403, detail="Admin access required")


async def optional_verify_admin(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Like verify_admin but returns None (instead of 401) when no token is sent and auth is disabled."""
    if not is_auth_required():
        return None
    return await verify_admin(authorization)
