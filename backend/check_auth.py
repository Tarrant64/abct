#!/usr/bin/env python3
"""
Auth verification script - ensure admin user exists, optionally reset password.

Usage:
    # Verify admin exists (create if missing, preserve existing password)
    python backend/check_auth.py

    # Reset admin password to 'satoshi'
    python backend/check_auth.py --reset
"""

import asyncio
import sys
import aiosqlite
import bcrypt
from pathlib import Path

DATABASE_PATH = Path("/app/data/portfolio.db")


async def check_auth(reset_password: bool = False):
    print("=" * 60)
    print("ABCT Auth Check")
    print("=" * 60)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if users table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ) as cursor:
            table = await cursor.fetchone()

        if not table:
            print("Users table does NOT exist - creating admin user...")
            # Table will be created by init_db, but create it here for standalone use
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
            password_hash = bcrypt.hashpw("satoshi".encode('utf-8'), bcrypt.gensalt())
            await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", password_hash.decode('utf-8'))
            )
            await db.commit()
            print("CREATED admin user with default password")
            return

        # Check for admin user
        async with db.execute(
            "SELECT username, password_hash, created_at FROM users WHERE username = 'admin'"
        ) as cursor:
            admin = await cursor.fetchone()

        if not admin:
            print("Admin user missing - creating with default password...")
            password_hash = bcrypt.hashpw("satoshi".encode('utf-8'), bcrypt.gensalt())
            await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", password_hash.decode('utf-8'))
            )
            await db.commit()
            print("CREATED admin user with default password")
            return

        # Admin exists
        username, stored_hash, created_at = admin
        print(f"Admin user exists (created: {created_at})")

        # Check for empty/NULL password hash
        if not stored_hash or not stored_hash.strip():
            print("WARNING: Admin password hash is empty! Resetting to default...")
            password_hash = bcrypt.hashpw("satoshi".encode('utf-8'), bcrypt.gensalt())
            await db.execute(
                "UPDATE users SET password_hash = ? WHERE username = 'admin'",
                (password_hash.decode('utf-8'),)
            )
            await db.commit()
            print("RESET admin password (hash was empty)")
            return

        if reset_password:
            print("Resetting admin password to default...")
            password_hash = bcrypt.hashpw("satoshi".encode('utf-8'), bcrypt.gensalt())
            await db.execute(
                "UPDATE users SET password_hash = ?, password_changed = 0 WHERE username = 'admin'",
                (password_hash.decode('utf-8'),)
            )
            await db.commit()
            print("RESET admin password to 'satoshi'")
        else:
            print("Admin account OK (password preserved)")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    asyncio.run(check_auth(reset_password=reset))
