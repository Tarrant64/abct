"""
Demo Mode Middleware - Intercepts API calls for demo accounts

Provides demo mode detection and request interception:
- Checks if current user is demo account
- Routes to mock services instead of real APIs
- Prevents real blockchain/API requests
- Returns realistic fake data

Usage:
    from middleware.demo_mode import is_demo_user, demo_mode_check

    @router.get("/endpoint")
    async def get_data(username: str = Depends(verify_session)):
        if await is_demo_user(username):
            return await demo_service.get_fake_data()
        return await real_service.get_data()
"""

from typing import Optional
from functools import wraps
import aiosqlite
from config import DATABASE_PATH


# Demo account username
DEMO_USERNAME = "demo"


async def is_demo_user(username: str) -> bool:
    """
    Check if the given username is a demo account.

    Args:
        username: Username to check

    Returns:
        True if demo user, False otherwise
    """
    if not username:
        return False

    # Check for anonymous/unauthenticated users
    if username in ["anonymous", "localhost"]:
        return False

    # Check if username is demo
    return username.lower() == DEMO_USERNAME.lower()


async def get_user_demo_status(username: str) -> dict:
    """
    Get demo mode status for a user.

    Args:
        username: Username to check

    Returns:
        Dict with is_demo flag and username
    """
    is_demo = await is_demo_user(username)

    return {
        "username": username,
        "is_demo": is_demo,
        "demo_mode_active": is_demo
    }


async def create_demo_user():
    """
    Create demo user account in database if it doesn't exist.
    Should be called during app startup.
    """
    import bcrypt
    import logging

    logger = logging.getLogger(__name__)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if demo user exists
        async with db.execute("SELECT COUNT(*) FROM users WHERE username = ?", (DEMO_USERNAME,)) as cursor:
            count = await cursor.fetchone()

        if count[0] == 0:
            # Create demo user with password "demo"
            password_hash = bcrypt.hashpw("demo".encode('utf-8'), bcrypt.gensalt())

            await db.execute(
                "INSERT INTO users (username, password_hash, password_changed) VALUES (?, ?, ?)",
                (DEMO_USERNAME, password_hash.decode('utf-8'), 1)  # password_changed=1 so no prompt
            )
            await db.commit()
            logger.info("Demo user created successfully (username: demo, password: demo)")
        else:
            logger.info("Demo user already exists")


def demo_mode_check(func):
    """
    Decorator to automatically route to demo services if user is in demo mode.

    This is a convenience decorator but most endpoints should explicitly check
    is_demo_user() for better control.

    Example:
        @router.get("/data")
        @demo_mode_check
        async def get_data(username: str = Depends(verify_session)):
            # This will be skipped if demo user
            return await real_service.get_data()
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if username in kwargs
        username = kwargs.get('username')

        if username and await is_demo_user(username):
            # Return demo data indicator
            return {
                "demo_mode": True,
                "message": "Demo mode active - no real data available"
            }

        return await func(*args, **kwargs)

    return wrapper
