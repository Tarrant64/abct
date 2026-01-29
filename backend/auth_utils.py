"""
Authentication Utilities - Session verification for protected endpoints

Provides the verify_session dependency without circular import issues.
"""

from typing import Optional
from datetime import datetime
from fastapi import HTTPException, Header

# Import session store from auth router
# This will be set by auth.py on startup
_active_sessions = None


def init_session_store(sessions):
    """Initialize the session store reference"""
    global _active_sessions
    _active_sessions = sessions


def clean_expired_sessions():
    """Remove expired sessions from memory"""
    if not _active_sessions:
        return

    now = datetime.utcnow()
    expired_tokens = [
        token for token, data in _active_sessions.items()
        if data['expires'] < now
    ]
    for token in expired_tokens:
        del _active_sessions[token]


async def verify_session(authorization: Optional[str] = Header(None)) -> str:
    """
    Dependency to verify session token for protected endpoints.

    Use with Depends() to protect endpoints:
        @router.get("/endpoint", dependencies=[Depends(verify_session)])
        async def protected_endpoint():
            ...

    Args:
        authorization: Authorization header value (Bearer token)

    Returns:
        Username of authenticated user

    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    # Clean expired sessions
    clean_expired_sessions()

    # Check if session store is initialized
    if not _active_sessions:
        raise HTTPException(
            status_code=503,
            detail="Authentication system not initialized"
        )

    # Check if token exists and is valid
    session_data = _active_sessions.get(token)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please login again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if session_data['expires'] < datetime.utcnow():
        del _active_sessions[token]
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return session_data['username']
