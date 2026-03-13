"""
Authentication Utilities - Session verification for protected endpoints

Provides the verify_session dependency using database-backed sessions.
This ensures session state is shared across multiple uvicorn worker processes.
"""

from typing import Optional
from datetime import datetime
from fastapi import HTTPException, Header, Query
import os


def is_auth_required() -> bool:
    """Check if authentication is required"""
    require_auth = os.getenv('ABCT_REQUIRE_AUTH', 'true').lower()
    return require_auth != 'false'


async def verify_session(authorization: Optional[str] = Header(None)) -> int:
    """
    Dependency to verify session token for protected endpoints.

    Use with Depends() to protect endpoints:
        @router.get("/endpoint")
        async def protected_endpoint(user_id: int = Depends(verify_session)):
            ...

    Implements sliding window session renewal: if a session has consumed more
    than half its lifetime, the expiry is extended. This ensures active users
    are never logged out unexpectedly.

    Args:
        authorization: Authorization header value (Bearer token)

    Returns:
        User ID of authenticated user, or 1 (admin) if auth disabled

    Raises:
        HTTPException: 401 if token is missing or invalid (when auth required)
    """
    # Default session lifetime for renewal (30 days in minutes)
    SESSION_LIFETIME_MINUTES = 43200

    # If auth not required, still check for a valid session token
    # so demo users get demo data instead of admin data
    if not is_auth_required():
        if authorization and authorization.startswith("Bearer "):
            try:
                from database import get_session
                session_data = await get_session(authorization[7:])
                if session_data:
                    return session_data['user_id']
            except Exception:
                pass
        return 1  # Default to admin user ID

    # Auth is required - check for token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    # Import database functions here to avoid circular imports
    from database import get_session, delete_session, cleanup_expired_sessions, renew_session

    # Clean expired sessions from database
    await cleanup_expired_sessions()

    # Check if token exists and is valid in database
    session_data = await get_session(token)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please login again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Check if session is expired
    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if expires_at < datetime.utcnow():
        await delete_session(token)
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Sliding window renewal: extend session if more than half its lifetime
    # has elapsed. This avoids a DB write on every single request while still
    # keeping active sessions alive indefinitely.
    remaining = (expires_at - datetime.utcnow()).total_seconds() / 60
    if remaining < SESSION_LIFETIME_MINUTES / 2:
        await renew_session(token, SESSION_LIFETIME_MINUTES)

    return session_data['user_id']


async def verify_session_optional(authorization: Optional[str] = Header(None)) -> Optional[int]:
    """
    Dependency to optionally verify session token.

    Unlike verify_session, this does not raise an exception if no auth is provided.
    Useful for endpoints that can work with or without authentication (e.g., public image proxies).

    Args:
        authorization: Authorization header value (Bearer token)

    Returns:
        User ID if authenticated, None if not authenticated
    """
    # If auth not required globally, return admin user
    if not is_auth_required():
        return 1

    # No authorization header provided - return None instead of raising
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]  # Remove "Bearer " prefix

    try:
        # Import database functions here to avoid circular imports
        from database import get_session, cleanup_expired_sessions

        # Clean expired sessions from database
        await cleanup_expired_sessions()

        # Check if token exists and is valid in database
        session_data = await get_session(token)
        if not session_data:
            return None

        # Check if session is expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if expires_at < datetime.utcnow():
            return None

        return session_data['user_id']
    except Exception:
        # On any error, just return None (not authenticated)
        return None


async def verify_session_sse(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None)
) -> int:
    """Verify session for SSE endpoints that use EventSource.
    EventSource can't send headers, so also accepts token as query param.
    Also performs sliding window session renewal."""
    from database import get_session, cleanup_expired_sessions, renew_session

    SESSION_LIFETIME_MINUTES = 43200  # 30 days

    actual_token = None
    if authorization and authorization.startswith("Bearer "):
        actual_token = authorization[7:]
    elif token:
        actual_token = token

    if not actual_token:
        if not is_auth_required():
            return 1
        raise HTTPException(status_code=401, detail="Not authenticated")

    await cleanup_expired_sessions()
    session_data = await get_session(actual_token)
    if not session_data:
        if not is_auth_required():
            return 1
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if expires_at < datetime.utcnow():
        if not is_auth_required():
            return 1
        raise HTTPException(status_code=401, detail="Session expired")

    # Sliding window renewal for SSE sessions too
    remaining = (expires_at - datetime.utcnow()).total_seconds() / 60
    if remaining < SESSION_LIFETIME_MINUTES / 2:
        await renew_session(actual_token, SESSION_LIFETIME_MINUTES)

    return session_data['user_id']
