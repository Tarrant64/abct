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

Build: v1769653325
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
from database import create_session, get_session, delete_session, cleanup_expired_sessions

router = APIRouter(prefix="/auth", tags=["authentication"])

# Session timeout in minutes
SESSION_TIMEOUT_MINUTES = 480  # 8 hours


class LoginRequest(BaseModel):
    """Login request model"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model"""
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None
    should_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    """Change password request model"""
    current_password: str
    new_password: str


class TokenVerifyResponse(BaseModel):
    """Token verification response"""
    valid: bool
    username: Optional[str] = None


async def init_auth_tables():
    """Initialize authentication tables in database"""
    import logging
    logger = logging.getLogger(__name__)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_changed BOOLEAN DEFAULT 0,
                is_demo BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

        # Sessions table (database-backed sessions for multi-process safety)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                is_demo BOOLEAN DEFAULT 0,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.commit()
        logger.info("Sessions table initialized")

        # Add password_changed column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN password_changed BOOLEAN DEFAULT 0")
            await db.commit()
            logger.info("Added password_changed column to users table")
        except Exception:
            # Column already exists
            pass

        # Add is_demo column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_demo BOOLEAN DEFAULT 0")
            await db.commit()
            logger.info("Added is_demo column to users table")
        except Exception:
            # Column already exists
            pass

        # Check if admin user exists
        async with db.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'") as cursor:
            count = await cursor.fetchone()

        logger.info(f"Admin user check: {count[0]} users found with username 'admin'")

        if count[0] == 0:
            # Create default admin user
            default_password = os.getenv("ABCT_ADMIN_PASSWORD", "satoshi")
            logger.info(f"Creating default admin user with password from env (using default: {'satoshi'})")
            password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

            await db.execute(
                "INSERT INTO users (username, password_hash, is_demo) VALUES (?, ?, ?)",
                ("admin", password_hash.decode('utf-8'), 0)
            )
            await db.commit()
            logger.info("Default admin user created successfully")
        else:
            logger.info("Admin user already exists, skipping creation")

        # Check if demo user exists
        async with db.execute("SELECT COUNT(*) FROM users WHERE username = 'demo'") as cursor:
            count = await cursor.fetchone()

        logger.info(f"Demo user check: {count[0]} users found with username 'demo'")

        if count[0] == 0:
            # Create demo user (username: demo, password: demo)
            logger.info("Creating demo user account")
            password_hash = bcrypt.hashpw("demo".encode('utf-8'), bcrypt.gensalt())

            await db.execute(
                "INSERT INTO users (username, password_hash, password_changed, is_demo) VALUES (?, ?, ?, ?)",
                ("demo", password_hash.decode('utf-8'), 1, 1)  # password_changed=1, is_demo=1
            )
            await db.commit()
            logger.info("Demo user created successfully (username: demo, password: demo)")
        else:
            # Ensure existing demo user has is_demo flag set
            await db.execute(
                "UPDATE users SET is_demo = 1 WHERE username = 'demo'",
            )
            await db.commit()
            logger.info("Demo user already exists, ensured is_demo flag is set")


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


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Login endpoint - authenticate user and create session.

    Args:
        request: Login credentials (username, password)

    Returns:
        LoginResponse with success status and session token
    """
    # Clean expired sessions from database
    await cleanup_expired_sessions()

    # Verify credentials
    if not await verify_password(request.username, request.password):
        return LoginResponse(
            success=False,
            message="Invalid username or password"
        )

    # Get user details including ID and is_demo
    is_demo = False
    user_id = None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT id, is_demo FROM users WHERE username = ?",
            (request.username,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
                if row[1]:  # is_demo is True/1
                    is_demo = True

    # Create session token and store in database
    token = create_session_token()
    await create_session(token, request.username, user_id, is_demo, SESSION_TIMEOUT_MINUTES)

    return LoginResponse(
        success=True,
        token=token,
        message="Login successful",
        should_change_password=False  # Never prompt for password change
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

    # Clean expired sessions from database
    await cleanup_expired_sessions()

    # Check if token exists and is valid in database
    session_data = await get_session(token)
    if not session_data:
        return TokenVerifyResponse(valid=False)

    # Check if session is expired
    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if expires_at < datetime.utcnow():
        await delete_session(token)
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
    if token:
        await delete_session(token)

    return {"success": True, "message": "Logged out successfully"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Change password endpoint - allows authenticated users to change their password.

    Args:
        request: Current password and new password
        authorization: Bearer token from Authorization header

    Returns:
        Success message
    """
    # Verify user is authenticated
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization[7:]
    session_data = await get_session(token)

    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    username = session_data['username']

    # Verify current password
    if not await verify_password(username, request.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Validate new password
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    if request.new_password == request.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    # Update password
    password_hash = bcrypt.hashpw(request.new_password.encode('utf-8'), bcrypt.gensalt())

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET password_hash = ?, password_changed = 1, updated_at = ? WHERE username = ?",
            (password_hash.decode('utf-8'), datetime.utcnow(), username)
        )
        await db.commit()

    return {"success": True, "message": "Password changed successfully"}


@router.get("/status")
async def auth_status():
    """
    Get authentication system status.

    Returns:
        Status information about auth system
    """
    await cleanup_expired_sessions()

    # Check user count and active sessions in database
    user_count = 0
    session_count = 0
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Count users
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                user_count = row[0] if row else 0

            # Count active sessions
            async with db.execute("SELECT COUNT(*) FROM sessions") as cursor:
                row = await cursor.fetchone()
                session_count = row[0] if row else 0
    except Exception as e:
        user_count = f"Error: {e}"

    return {
        "enabled": True,
        "active_sessions": session_count,
        "session_timeout_minutes": SESSION_TIMEOUT_MINUTES,
        "users_in_database": user_count,
        "default_credentials": {
            "username": "admin",
            "password": "satoshi (change on first login)"
        },
        "demo_account": {
            "username": "demo",
            "password": "demo",
            "description": "Demo account with fake data (no real API calls)"
        }
    }


@router.get("/demo-status")
async def get_demo_status(authorization: Optional[str] = Header(None)):
    """
    Get demo mode status for current user.

    Args:
        authorization: Authorization header value (Bearer token)

    Returns:
        Demo mode status
    """
    if not authorization or not authorization.startswith("Bearer "):
        return {
            "authenticated": False,
            "is_demo": False
        }

    token = authorization[7:]
    session_data = await get_session(token)

    if not session_data:
        return {
            "authenticated": False,
            "is_demo": False
        }

    is_demo = session_data.get('is_demo', False)

    return {
        "authenticated": True,
        "username": session_data['username'],
        "is_demo": is_demo,
        "message": "Demo mode active - all data is fake" if is_demo else "Normal mode - using real data"
    }


# Note: Auth tables are initialized via startup event in main.py
# Do not initialize here during import to avoid asyncio issues
