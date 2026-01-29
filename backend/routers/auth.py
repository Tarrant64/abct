"""
Authentication Router - Session-based authentication for ABCT

Provides endpoints for:
- User login (username/password) with session tokens
- Token verification
- Session logout
- Password management

Default credentials:
- Username: admin
- Password: satoshi (hashed in database)

Build: v1769649627
"""

import os
import sys
import secrets
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Response, Header
from pydantic import BaseModel
import aiosqlite
from config import DATABASE_PATH

# Initialize auth_utils with session store
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auth_utils

router = APIRouter(prefix="/auth", tags=["authentication"])

# In-memory session store (in production, use Redis or database)
active_sessions = {}
SESSION_TIMEOUT_MINUTES = 480  # 8 hours

# Initialize auth_utils with session store reference
auth_utils.init_session_store(active_sessions)


class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model"""
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None


class TokenVerifyResponse(BaseModel):
    """Token verification response"""
    valid: bool
    username: Optional[str] = None


async def init_auth_tables():
    """Initialize authentication tables in database"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check if admin user exists
        async with db.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'") as cursor:
            count = await cursor.fetchone()

        if count[0] == 0:
            # Create default admin user
            default_password = os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")
            password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

            await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", password_hash.decode('utf-8'))
            )
            await db.commit()


async def verify_password(username: str, password: str) -> bool:
    """
    Verify username and password against database.

    Args:
        username: Username to verify
        password: Plain-text password to verify

    Returns:
        True if credentials are valid, False otherwise
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        return False

    stored_hash = row[0].encode('utf-8')
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash)


async def update_password(username: str, new_password: str) -> bool:
    """
    Update user password in database.

    Args:
        username: Username to update
        new_password: New plain-text password

    Returns:
        True if update succeeded, False otherwise
    """
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
            (password_hash.decode('utf-8'), datetime.utcnow(), username)
        )
        await db.commit()

    return True


def create_session_token() -> str:
    """Generate a secure random session token"""
    return secrets.token_urlsafe(32)


def clean_expired_sessions():
    """Remove expired sessions from memory"""
    now = datetime.utcnow()
    expired_tokens = [
        token for token, data in active_sessions.items()
        if data['expires'] < now
    ]
    for token in expired_tokens:
        del active_sessions[token]


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Login endpoint - authenticate user and create session.

    Args:
        request: Login credentials (username, password)

    Returns:
        LoginResponse with success status and session token
    """
    # Clean expired sessions
    clean_expired_sessions()

    # Verify credentials
    if not await verify_password(request.username, request.password):
        return LoginResponse(
            success=False,
            message="Invalid username or password"
        )

    # Create session token
    token = create_session_token()
    expires = datetime.utcnow() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    active_sessions[token] = {
        'username': request.username,
        'expires': expires,
        'created_at': datetime.utcnow()
    }

    return LoginResponse(
        success=True,
        token=token,
        message="Login successful"
    )


@router.get("/verify", response_model=TokenVerifyResponse)
async def verify_token(token: Optional[str] = None):
    """
    Verify session token validity.

    Args:
        token: Session token from Authorization header (Bearer token)

    Returns:
        TokenVerifyResponse with validity status and username
    """
    if not token:
        return TokenVerifyResponse(valid=False)

    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    # Clean expired sessions
    clean_expired_sessions()

    # Check if token exists and is valid
    session_data = active_sessions.get(token)
    if not session_data:
        return TokenVerifyResponse(valid=False)

    if session_data['expires'] < datetime.utcnow():
        del active_sessions[token]
        return TokenVerifyResponse(valid=False)

    return TokenVerifyResponse(
        valid=True,
        username=session_data['username']
    )


@router.post("/logout")
async def logout(token: Optional[str] = None):
    """
    Logout endpoint - invalidate session token.

    Args:
        token: Session token to invalidate

    Returns:
        Success message
    """
    if token and token in active_sessions:
        del active_sessions[token]

    return {"success": True, "message": "Logged out successfully"}


@router.get("/status")
async def auth_status():
    """
    Get authentication system status.

    Returns:
        Status information about auth system
    """
    clean_expired_sessions()

    return {
        "enabled": True,
        "active_sessions": len(active_sessions),
        "session_timeout_minutes": SESSION_TIMEOUT_MINUTES,
        "default_credentials": {
            "username": "admin",
            "password": "satoshi (change on first login)"
        }
    }


# Initialize auth tables on import
import asyncio
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # If event loop is already running, schedule the init
        asyncio.create_task(init_auth_tables())
    else:
        # If no event loop, run it synchronously
        loop.run_until_complete(init_auth_tables())
except RuntimeError:
    # No event loop, will be initialized on first request
    pass
