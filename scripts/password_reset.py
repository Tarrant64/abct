#!/usr/bin/env python3
"""
ABCT Password Reset Utility

Interactive command-line tool to reset the admin password for ABCT.
This script updates the password hash in the database.

Usage:
    # Local development
    python scripts/password_reset.py

    # Docker container
    docker exec -it abct-dashboard python scripts/password_reset.py

Requirements:
    - bcrypt library for password hashing
    - Access to ABCT database (data/portfolio.db)

Build: v1769649627
"""

import os
import sys
import sqlite3
import getpass
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import bcrypt
except ImportError:
    print("ERROR: bcrypt library not found.")
    print("Install with: pip install bcrypt")
    sys.exit(1)


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength.

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    # Check for basic complexity
    has_letter = any(c.isalpha() for c in password)
    has_number = any(c.isdigit() for c in password)

    if not has_letter:
        return False, "Password must contain at least one letter"

    # Warning if no number (but allow it)
    if not has_number:
        print("WARNING: Password does not contain numbers. Consider adding numbers for better security.")

    return True, ""


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.

    Args:
        password: Plain-text password

    Returns:
        Hashed password string
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)  # 12 rounds is secure
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def update_password_in_db(username: str, password_hash: str, db_path: Path) -> bool:
    """
    Update password hash in database.

    Args:
        username: Username to update
        password_hash: New password hash
        db_path: Path to database file

    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if users table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='users'
        """)
        if not cursor.fetchone():
            print("ERROR: Users table does not exist. Run ABCT at least once to initialize the database.")
            conn.close()
            return False

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            print(f"ERROR: User '{username}' not found in database.")
            print("Run ABCT at least once to create the default admin user.")
            conn.close()
            return False

        # Update password
        cursor.execute("""
            UPDATE users
            SET password_hash = ?, updated_at = datetime('now')
            WHERE username = ?
        """, (password_hash, username))

        conn.commit()
        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"ERROR: Database error: {e}")
        return False


def main():
    """Main password reset flow"""
    print("=" * 60)
    print("ABCT Password Reset Utility")
    print("=" * 60)
    print()

    # Determine database path
    # Check if we're in Docker or local
    if os.path.exists("/app"):
        # Docker environment
        db_path = Path("/app/data/portfolio.db")
    else:
        # Local environment
        project_root = Path(__file__).parent.parent
        db_path = project_root / "data" / "portfolio.db"

    print(f"Database: {db_path}")
    print()

    # Check if database exists
    if not db_path.exists():
        print("ERROR: Database not found.")
        print(f"Expected location: {db_path}")
        print()
        print("Make sure ABCT has been run at least once to create the database.")
        sys.exit(1)

    # Get username (default to admin)
    username = input("Username to reset [admin]: ").strip()
    if not username:
        username = "admin"

    print(f"\nResetting password for user: {username}")
    print()

    # Get new password
    while True:
        password1 = getpass.getpass("Enter new password: ")
        if not password1:
            print("ERROR: Password cannot be empty.")
            continue

        # Validate password
        is_valid, error_msg = validate_password(password1)
        if not is_valid:
            print(f"ERROR: {error_msg}")
            continue

        # Confirm password
        password2 = getpass.getpass("Confirm new password: ")

        if password1 != password2:
            print("ERROR: Passwords do not match. Please try again.")
            print()
            continue

        # Passwords match and are valid
        break

    print()
    print("Hashing password...")

    # Hash the password
    password_hash = hash_password(password1)

    print("Updating database...")

    # Update database
    if update_password_in_db(username, password_hash, db_path):
        print()
        print("=" * 60)
        print("SUCCESS! Password has been reset.")
        print("=" * 60)
        print()
        print(f"Username: {username}")
        print("Password: <your new password>")
        print()
        print("You can now login with your new credentials.")
        print()
        return 0
    else:
        print()
        print("=" * 60)
        print("FAILED: Could not update password.")
        print("=" * 60)
        print()
        print("Please check the error messages above and try again.")
        print()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print()
        print("Password reset cancelled.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"UNEXPECTED ERROR: {e}")
        print()
        print("Please report this issue.")
        sys.exit(1)
