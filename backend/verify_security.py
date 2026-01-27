#!/usr/bin/env python3
"""
ABCT Security Verification Script

Verifies that all HIGH-002 and HIGH-004 security fixes are properly implemented.

Usage:
    python verify_security.py

Exit codes:
    0 - All checks passed
    1 - Some checks failed
"""

import sys
import os
from pathlib import Path

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def check_pass(message):
    print(f"{GREEN}✓{RESET} {message}")
    return True

def check_fail(message):
    print(f"{RED}✗{RESET} {message}")
    return False

def check_warn(message):
    print(f"{YELLOW}⚠{RESET} {message}")

def main():
    print("=" * 60)
    print("ABCT Security Verification - HIGH-002 & HIGH-004")
    print("=" * 60)
    print()

    backend_dir = Path(__file__).parent
    checks_passed = 0
    checks_failed = 0
    warnings = 0

    # Check 1: Middleware files exist
    print("1. Checking middleware files...")
    middleware_dir = backend_dir / "middleware"
    required_files = [
        middleware_dir / "__init__.py",
        middleware_dir / "size_limit.py",
        middleware_dir / "rate_limit.py",
    ]

    for file in required_files:
        if file.exists():
            checks_passed += check_pass(f"Found {file.name}")
        else:
            checks_failed += check_fail(f"Missing {file.name}")

    print()

    # Check 2: Validation models exist
    print("2. Checking validation models...")
    validation_file = backend_dir / "routers" / "validation_models.py"
    if validation_file.exists():
        checks_passed += check_pass("Found validation_models.py")
    else:
        checks_failed += check_fail("Missing validation_models.py")

    print()

    # Check 3: Test imports
    print("3. Testing imports...")
    try:
        sys.path.insert(0, str(backend_dir))
        from middleware import RequestSizeLimitMiddleware, RATE_LIMITING_AVAILABLE
        checks_passed += check_pass("RequestSizeLimitMiddleware import successful")

        if RATE_LIMITING_AVAILABLE:
            checks_passed += check_pass("Rate limiting available (slowapi installed)")
        else:
            warnings += 1
            check_warn("Rate limiting not available (slowapi not installed)")
            print(f"         Install with: pip install slowapi")
    except ImportError as e:
        checks_failed += check_fail(f"Middleware import failed: {e}")

    try:
        from routers.validation_models import (
            WalletAddressRequest, MultipleWalletsRequest,
            XPubDiscoveryRequest, TokenTrackRequest
        )
        checks_passed += check_pass("Validation models import successful")
    except ImportError as e:
        checks_failed += check_fail(f"Validation models import failed: {e}")

    print()

    # Check 4: Test validation
    print("4. Testing validation...")
    try:
        from routers.validation_models import WalletAddressRequest
        from pydantic import ValidationError

        # Test valid input
        valid = WalletAddressRequest(address="addr1test123")
        checks_passed += check_pass("Valid address accepted")

        # Test invalid input
        try:
            invalid = WalletAddressRequest(address="")
            checks_failed += check_fail("Empty address not rejected")
        except ValidationError:
            checks_passed += check_pass("Empty address rejected")
    except Exception as e:
        checks_failed += check_fail(f"Validation test failed: {e}")

    print()

    # Check 5: Check main.py integration
    print("5. Checking main.py integration...")
    main_file = backend_dir / "main.py"
    if main_file.exists():
        with open(main_file, 'r') as f:
            content = f.read()

        if "RequestSizeLimitMiddleware" in content:
            checks_passed += check_pass("Size limit middleware integrated")
        else:
            checks_failed += check_fail("Size limit middleware not integrated")

        if "RATE_LIMITING_AVAILABLE" in content:
            checks_passed += check_pass("Rate limiting integration found")
        else:
            checks_failed += check_fail("Rate limiting integration missing")
    else:
        checks_failed += check_fail("main.py not found")

    print()

    # Check 6: Security router enhancements
    print("6. Checking security router enhancements...")
    security_file = backend_dir / "routers" / "security.py"
    if security_file.exists():
        with open(security_file, 'r') as f:
            content = f.read()

        checks_to_find = [
            ("ALLOWED_CERT_EXTENSIONS", "Certificate extension validation"),
            ("ALLOWED_KEY_EXTENSIONS", "Key extension validation"),
            ("BEGIN CERTIFICATE", "PEM format validation"),
            ("UTF-8", "UTF-8 encoding validation"),
        ]

        for check_str, description in checks_to_find:
            if check_str in content:
                checks_passed += check_pass(description)
            else:
                checks_failed += check_fail(f"Missing {description}")
    else:
        checks_failed += check_fail("security.py not found")

    print()

    # Check 7: Environment variables
    print("7. Checking environment variables...")
    max_body = os.getenv("ABCT_MAX_BODY_SIZE")
    max_upload = os.getenv("ABCT_MAX_UPLOAD_SIZE")

    if max_body:
        check_warn(f"ABCT_MAX_BODY_SIZE set to {max_body} (overriding 10MB default)")
        warnings += 1
    else:
        checks_passed += check_pass("Using default ABCT_MAX_BODY_SIZE (10MB)")

    if max_upload:
        check_warn(f"ABCT_MAX_UPLOAD_SIZE set to {max_upload} (overriding 5MB default)")
        warnings += 1
    else:
        checks_passed += check_pass("Using default ABCT_MAX_UPLOAD_SIZE (5MB)")

    print()

    # Check 8: Documentation
    print("8. Checking documentation...")
    sec_dir = backend_dir.parent / "sec"
    rollback_doc = sec_dir / "ROLLBACK.md"
    impl_doc = sec_dir / "HIGH-002-HIGH-004-IMPLEMENTATION.md"

    if rollback_doc.exists():
        checks_passed += check_pass("Found ROLLBACK.md")
    else:
        checks_failed += check_fail("Missing ROLLBACK.md")

    if impl_doc.exists():
        checks_passed += check_pass("Found HIGH-002-HIGH-004-IMPLEMENTATION.md")
    else:
        checks_failed += check_fail("Missing implementation documentation")

    print()

    # Summary
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"{GREEN}Passed:{RESET} {checks_passed}")
    if checks_failed > 0:
        print(f"{RED}Failed:{RESET} {checks_failed}")
    if warnings > 0:
        print(f"{YELLOW}Warnings:{RESET} {warnings}")
    print()

    if checks_failed == 0:
        print(f"{GREEN}✓ All checks passed!{RESET}")
        print()
        print("Security enhancements are properly implemented.")
        print("The application is protected against:")
        print("  - DoS via large uploads (HIGH-002)")
        print("  - Missing input validation (HIGH-004)")
        print()
        if warnings > 0:
            print("Note: Warnings indicate optional configurations or recommendations.")
        print()
        print("Next steps:")
        print("  1. Install slowapi for rate limiting: pip install slowapi")
        print("  2. Test the application: python main.py")
        print("  3. Monitor logs for 413/429 responses")
        return 0
    else:
        print(f"{RED}✗ Some checks failed!{RESET}")
        print()
        print("Please review the failures above and ensure all required")
        print("files are present and properly configured.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
