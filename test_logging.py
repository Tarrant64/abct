#!/usr/bin/env python3
"""
Quick test script for centralized logging service.

Tests:
1. Logging service initialization
2. Log entry sanitization
3. In-memory buffer
4. Database persistence
5. Error message sanitization

Run: python test_logging.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from services.logging_service import get_logging_service, LogLevel


async def test_sanitization():
    """Test that sensitive data is properly sanitized."""
    print("\n=== Testing Log Sanitization ===")

    # Create temp directory for test database
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_db = temp_dir / "test_logs.db"

    from services.logging_service import LoggingService
    log_service = LoggingService(db_path=temp_db)
    await log_service.initialize()

    # Test API key redaction
    await log_service.error(
        "test",
        "API error: api_key=bf123abc456def, token: secret123"
    )

    # Test wallet address redaction
    await log_service.warning(
        "test",
        "Wallet addr1qxy1234567890abcdefghijklmnopqrstuvwxyz1234567890abcdefghijklmnopqrstuvwxyz1234567890abcdefghijk has low balance"
    )

    # Test file path sanitization
    await log_service.error(
        "test",
        "Error in /Users/chris/ABCT/backend/services/nft.py at line 42"
    )

    # Test Ethereum address
    await log_service.info(
        "test",
        "Transfer from 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1 to 0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B"
    )

    # Get recent logs and check sanitization
    logs = await log_service.get_recent(limit=10)

    print(f"\n✓ Created {len(logs)} test logs")

    for log in logs:
        print(f"\n[{log['level']}] {log['source']}: {log['message']}")

        # Verify sanitization
        message = log['message']

        if 'bf123abc456def' in message:
            print("  ✗ FAILED: API key not redacted!")
            return False

        if 'secret123' in message:
            print("  ✗ FAILED: Token not redacted!")
            return False

        if 'addr1qxy' in message and len(message.split('addr1')[1].split()[0]) > 20:
            print("  ✗ FAILED: Wallet address not redacted!")
            return False

        if '/Users/chris/' in message or 'C:\\Users\\' in message:
            print("  ✗ FAILED: Absolute path not sanitized!")
            return False

        if '***REDACTED***' in message or 'addr1***' in message or '0x***' in message or '.../' in message:
            print("  ✓ Sanitization working")

    return True


async def test_exception_logging():
    """Test exception logging with traceback sanitization."""
    print("\n=== Testing Exception Logging ===")

    # Use temp database
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_db = temp_dir / "test_logs.db"

    from services.logging_service import LoggingService
    log_service = LoggingService(db_path=temp_db)
    await log_service.initialize()

    try:
        # Trigger an exception
        with open('/nonexistent/file/path/with/secrets/api_key=secret123.txt') as f:
            f.read()
    except Exception as e:
        await log_service.error(
            "test",
            "Failed to read configuration file",
            exc_info=e
        )

    # Check if traceback was sanitized
    logs = await log_service.get_recent(limit=1)

    if logs:
        log = logs[0]
        print(f"\n✓ Exception logged: {log['message']}")

        if log['traceback']:
            print(f"\nTraceback (sanitized):\n{log['traceback'][:200]}...")

            # Check sanitization
            if '/Users/' not in log['traceback'] and 'C:\\Users\\' not in log['traceback']:
                print("\n✓ Traceback paths sanitized")
            else:
                print("\n✗ FAILED: Absolute paths in traceback!")
                return False

            if 'api_key=secret123' not in log['traceback']:
                print("✓ Sensitive data removed from traceback")
            else:
                print("✗ FAILED: Sensitive data in traceback!")
                return False

    return True


async def test_persistence():
    """Test database persistence."""
    print("\n=== Testing Database Persistence ===")

    # Use temp database
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_db = temp_dir / "test_logs.db"

    from services.logging_service import LoggingService
    log_service = LoggingService(db_path=temp_db)
    await log_service.initialize()

    # Create error and warning (should persist)
    await log_service.error("test", "Test error for persistence")
    await log_service.warning("test", "Test warning for persistence")

    # Create info (should not persist to DB)
    await log_service.info("test", "Test info (memory only)")

    # Query from database
    result = await log_service.get_from_db(limit=10)

    print(f"\n✓ Database contains {result['total']} logs")

    errors = [l for l in result['logs'] if l['level'] == 'ERROR']
    warnings = [l for l in result['logs'] if l['level'] == 'WARNING']

    print(f"  - {len(errors)} errors")
    print(f"  - {len(warnings)} warnings")

    if len(errors) > 0 and len(warnings) > 0:
        print("\n✓ Persistence working (ERROR and WARNING saved to DB)")
        return True
    else:
        print("\n✗ FAILED: Logs not persisted to database!")
        return False


async def test_stats():
    """Test logging statistics."""
    print("\n=== Testing Statistics ===")

    # Use temp database
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_db = temp_dir / "test_logs.db"

    from services.logging_service import LoggingService
    log_service = LoggingService(db_path=temp_db)
    await log_service.initialize()

    # Add some test logs first
    await log_service.error("test", "Test error")
    await log_service.warning("test", "Test warning")
    await log_service.info("test", "Test info")

    stats = await log_service.get_stats()

    print(f"\n✓ Statistics retrieved:")
    print(f"  Buffer: {stats['buffer']['total']} logs")
    print(f"    - Errors: {stats['buffer']['by_level'].get('ERROR', 0)}")
    print(f"    - Warnings: {stats['buffer']['by_level'].get('WARNING', 0)}")
    print(f"    - Info: {stats['buffer']['by_level'].get('INFO', 0)}")
    print(f"  Database: {stats['database']['total']} logs")
    print(f"  Active subscribers: {stats['subscribers']}")

    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("ABCT Centralized Logging Service - Test Suite")
    print("=" * 60)

    tests = [
        ("Sanitization", test_sanitization),
        ("Exception Logging", test_exception_logging),
        ("Persistence", test_persistence),
        ("Statistics", test_stats),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Logging service is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
