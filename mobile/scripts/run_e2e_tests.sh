#!/usr/bin/env bash
#
# ABCT Mobile — E2E Test Runner
#
# Usage:
#   ./scripts/run_e2e_tests.sh                     # Auto-select best iOS simulator
#   ./scripts/run_e2e_tests.sh "iPhone 16 Pro"     # Target specific simulator
#   ./scripts/run_e2e_tests.sh --functional         # Run only functional tests
#   ./scripts/run_e2e_tests.sh --performance        # Run only performance tests
#   ./scripts/run_e2e_tests.sh --all                # Run the combined suite (default)
#
# Prerequisites:
#   - Xcode with iOS Simulator installed (xcode-select -p)
#   - Flutter SDK on PATH
#   - Run 'flutter pub get' first
#
# Exit codes:
#   0 = All tests passed (including performance budgets)
#   1 = One or more tests failed
#

set -euo pipefail

# Resolve script location.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults. DEVICE_NAME is assigned only by the argument loop below —
# grabbing $1 up front consumed flags like --functional as a device name.
DEVICE_NAME=""
SUITE="all"

# Parse arguments.
for arg in "$@"; do
  case "$arg" in
    --functional)
      SUITE="functional"
      ;;
    --performance)
      SUITE="performance"
      ;;
    --all)
      SUITE="all"
      ;;
    --*)
      echo "Unknown flag: $arg"
      exit 1
      ;;
    *)
      DEVICE_NAME="$arg"
      ;;
  esac
done

echo "============================================================"
echo "  ABCT Mobile — E2E Test Runner"
echo "============================================================"
echo ""

# ---- Preflight checks ----

# Check Flutter.
if ! command -v flutter &>/dev/null; then
  echo "ERROR: flutter not found on PATH."
  echo "Install Flutter: https://docs.flutter.dev/get-started/install"
  exit 1
fi

# Check Xcode.
if ! xcode-select -p &>/dev/null; then
  echo "ERROR: Xcode command-line tools not installed."
  echo "Run: xcode-select --install"
  exit 1
fi

echo "Flutter: $(flutter --version 2>&1 | head -1)"
echo "Xcode:   $(xcode-select -p)"
echo ""

# ---- Resolve iOS Simulator ----

if [ -z "$DEVICE_NAME" ]; then
  # Auto-select the first booted simulator, or boot one.
  BOOTED=$(xcrun simctl list devices booted -j 2>/dev/null | \
    python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data.get('devices', {}).items():
    if 'iOS' in runtime:
        for d in devices:
            if d['state'] == 'Booted':
                print(d['udid'])
                sys.exit(0)
" 2>/dev/null || true)

  if [ -n "$BOOTED" ]; then
    DEVICE_ID="$BOOTED"
    echo "Using booted simulator: $DEVICE_ID"
  else
    # Find an available iPhone simulator and boot it.
    DEVICE_ID=$(xcrun simctl list devices available -j 2>/dev/null | \
      python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data.get('devices', {}).items():
    if 'iOS' in runtime:
        for d in devices:
            if 'iPhone' in d.get('name', ''):
                print(d['udid'])
                sys.exit(0)
print('')
" 2>/dev/null || true)

    if [ -z "$DEVICE_ID" ]; then
      echo "ERROR: No iOS simulators found."
      echo "Open Xcode > Settings > Platforms to install an iOS Simulator runtime."
      exit 1
    fi

    echo "Booting simulator: $DEVICE_ID"
    xcrun simctl boot "$DEVICE_ID" 2>/dev/null || true
  fi
else
  # Find simulator by name.
  DEVICE_ID=$(xcrun simctl list devices available -j 2>/dev/null | \
    python3 -c "
import json, sys
name = '$DEVICE_NAME'
data = json.load(sys.stdin)
for runtime, devices in data.get('devices', {}).items():
    if 'iOS' in runtime:
        for d in devices:
            if d.get('name', '') == name:
                print(d['udid'])
                sys.exit(0)
print('')
" 2>/dev/null || true)

  if [ -z "$DEVICE_ID" ]; then
    echo "ERROR: Simulator '$DEVICE_NAME' not found."
    echo ""
    echo "Available iOS simulators:"
    xcrun simctl list devices available | grep -i iphone
    exit 1
  fi

  echo "Booting simulator: $DEVICE_NAME ($DEVICE_ID)"
  xcrun simctl boot "$DEVICE_ID" 2>/dev/null || true
fi

echo ""

# ---- Resolve test file ----

case "$SUITE" in
  functional)
    TEST_FILE="integration_test/suites/functional_test.dart"
    ;;
  performance)
    TEST_FILE="integration_test/suites/performance_test.dart"
    ;;
  all)
    TEST_FILE="integration_test/app_test.dart"
    ;;
esac

echo "Suite:   $SUITE"
echo "File:    $TEST_FILE"
echo "Device:  $DEVICE_ID"
echo ""
echo "------------------------------------------------------------"
echo ""

# ---- Run tests ----

cd "$PROJECT_DIR"

# Ensure dependencies are resolved.
flutter pub get

# Run the integration tests on the selected simulator.
flutter test "$TEST_FILE" \
  -d "$DEVICE_ID" \
  --no-pub \
  --reporter expanded \
  2>&1

EXIT_CODE=$?

echo ""
echo "============================================================"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  ALL TESTS PASSED"
else
  echo "  SOME TESTS FAILED (exit code $EXIT_CODE)"
fi
echo "============================================================"

exit $EXIT_CODE
