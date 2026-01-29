#!/usr/bin/env python3
"""
Quick auth diagnostic script - check if admin user exists and test password
Run inside Docker: docker exec -it abct-dashboard python backend/check_auth.py
"""

import asyncio
import aiosqlite
import bcrypt
from pathlib import Path

DATABASE_PATH = Path("/app/data/portfolio.db")

async def check_auth():
    print("=" * 60)
    print("ABCT Auth Diagnostic")
    print("=" * 60)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if users table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ) as cursor:
            table = await cursor.fetchone()

        if not table:
            print("❌ Users table does NOT exist!")
            return

        print("✅ Users table exists")

        # Count users
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            count = await cursor.fetchone()

        print(f"📊 Total users in database: {count[0]}")

        # Check for admin user
        async with db.execute(
            "SELECT username, created_at FROM users WHERE username = 'admin'"
        ) as cursor:
            admin = await cursor.fetchone()

        if not admin:
            print("❌ Admin user does NOT exist!")
            print("\nCreating admin user with password 'satoshi'...")

            password_hash = bcrypt.hashpw("satoshi".encode('utf-8'), bcrypt.gensalt())
            await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", password_hash.decode('utf-8'))
            )
            await db.commit()
            print("✅ Admin user created!")

        else:
            print(f"✅ Admin user exists (created: {admin[1]})")

            # Test password verification
            async with db.execute(
                "SELECT password_hash FROM users WHERE username = 'admin'"
            ) as cursor:
                row = await cursor.fetchone()

            stored_hash = row[0].encode('utf-8')
            test_password = "satoshi"

            if bcrypt.checkpw(test_password.encode('utf-8'), stored_hash):
                print(f"✅ Password 'satoshi' IS VALID for admin user")
            else:
                print(f"❌ Password 'satoshi' is NOT VALID for admin user")
                print("\nResetting password to 'satoshi'...")

                password_hash = bcrypt.hashpw("satoshi".encode('utf-8'), bcrypt.gensalt())
                await db.execute(
                    "UPDATE users SET password_hash = ? WHERE username = 'admin'",
                    (password_hash.decode('utf-8'),)
                )
                await db.commit()
                print("✅ Password reset complete!")

if __name__ == "__main__":
    asyncio.run(check_auth())
