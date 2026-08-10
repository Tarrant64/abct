#!/usr/bin/env bash
#
# ABCT Mobile — build, install and run on the Android emulator
#
# Wraps the Flutter Android loop so the SDK/JDK exports and the emulator
# serial do not have to be remembered. Starts the emulator if it isn't up.
#
# Usage:
#   ./scripts/android_run.sh                  # debug, attached (hot reload)
#   ./scripts/android_run.sh --release        # release APK: build, install, launch
#   ./scripts/android_run.sh --profile        # profile build
#   ./scripts/android_run.sh --mock           # also serve the E2E mock backend
#   ./scripts/android_run.sh --logs           # just tail this app's logcat
#   ./scripts/android_run.sh --test           # run the integration suite on the emulator
#   ./scripts/android_run.sh --drive          # same suite via `flutter drive`
#
# Options:
#   --avd <name>       target a specific AVD (default: $ABCT_AVD or abct_pixel)
#   --headless         start the emulator without a window if it isn't running
#   --perf-scale <n>   multiply the performance budgets by n (default 30).
#                      The budgets in the suite are calibrated for a release
#                      iOS Simulator; a debug build on the emulator is ~10x
#                      slower, so unscaled they fail unconditionally. Scaled
#                      runs are a crash/regression check, NOT a perf figure
#                      comparable to iOS.
#
# `--drive` exists because the "full flow timeline" test calls
# `binding.traceAction()`, which needs a VM Service connection that
# `flutter test` does not expose. Under `flutter test` that one test always
# fails with "Failed to connect to VM Service".
#
# IMPORTANT: a *debug* APK installed standalone (`adb install app-debug.apk`)
# hangs on the launch screen — it waits for the Dart VM service to attach.
# Use the default attached mode for debug work, or --release for a build that
# runs on its own. See README, "Android emulator / testing".
#
# Exit codes:
#   0 = success
#   1 = runtime failure
#   2 = usage error / missing prerequisite

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

APP_ID="com.teamcata.abct"
MOCK_PORT=8899

MODE="debug"
ACTION="run"
WITH_MOCK=false
EMU_ARGS=()
AVD="${ABCT_AVD:-abct_pixel}"
PERF_SCALE="${ABCT_PERF_SCALE:-30}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release)    MODE="release"; shift ;;
    --profile)    MODE="profile"; shift ;;
    --debug)      MODE="debug"; shift ;;
    --mock)       WITH_MOCK=true; shift ;;
    --logs)       ACTION="logs"; shift ;;
    --test)       ACTION="test"; shift ;;
    --drive)      ACTION="drive"; shift ;;
    --perf-scale) PERF_SCALE="$2"; shift 2 ;;
    --headless)   EMU_ARGS+=(--headless); shift ;;
    --avd)        AVD="$2"; EMU_ARGS+=(--avd "$2"); shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if ! [[ "$PERF_SCALE" =~ ^[0-9]+$ ]] || (( PERF_SCALE < 1 )); then
  echo "ERROR: --perf-scale must be a positive integer (got '$PERF_SCALE')." >&2
  exit 2
fi

# ---- Toolchain (same resolution as android_emu.sh) ------------------------

if [[ -z "${JAVA_HOME:-}" ]]; then
  if command -v brew &>/dev/null && brew --prefix openjdk@17 &>/dev/null; then
    JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
  fi
fi
: "${ANDROID_HOME:=/opt/homebrew/share/android-commandlinetools}"
export JAVA_HOME ANDROID_HOME
export PATH="${JAVA_HOME:-}/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

if ! command -v flutter &>/dev/null; then
  echo "ERROR: flutter not found on PATH." >&2
  echo "       Install Flutter: https://docs.flutter.dev/get-started/install" >&2
  exit 2
fi

# ---- Emulator -------------------------------------------------------------

# bash 3.2 (the macOS system bash) treats "${arr[@]}" on an empty array as an
# unset variable under `set -u`, so the expansion has to be guarded.
ABCT_AVD="$AVD" "$SCRIPT_DIR/android_emu.sh" start ${EMU_ARGS[@]+"${EMU_ARGS[@]}"}
SERIAL="$(ABCT_AVD="$AVD" "$SCRIPT_DIR/android_emu.sh" serial)"
echo "Target: $SERIAL ($AVD)"

# ---- Optional mock backend -----------------------------------------------

MOCK_PID=""
cleanup() {
  if [[ -n "$MOCK_PID" ]]; then
    kill "$MOCK_PID" 2>/dev/null || true
    echo "Mock backend stopped."
  fi
}
trap cleanup EXIT

if $WITH_MOCK; then
  # adb reverse makes the *device's* localhost:8899 reach the host, so the
  # in-app profile URL is the same http://localhost:8899 on any machine.
  adb -s "$SERIAL" reverse "tcp:$MOCK_PORT" "tcp:$MOCK_PORT"
  dart run tool/mock_backend.dart "$MOCK_PORT" &
  MOCK_PID=$!
  sleep 2
  echo "Mock backend on http://localhost:$MOCK_PORT (device-visible). Login: test / test123"
fi

# ---- Actions --------------------------------------------------------------

case "$ACTION" in
  logs)
    PID="$(adb -s "$SERIAL" shell pidof "$APP_ID" | tr -d '\r')"
    if [[ -z "$PID" ]]; then
      echo "ERROR: $APP_ID is not running on $SERIAL." >&2
      exit 1
    fi
    echo "Tailing logcat for pid $PID (Ctrl-C to stop)..."
    exec adb -s "$SERIAL" logcat --pid="$PID"
    ;;

  test)
    flutter pub get
    echo "Performance budgets scaled x$PERF_SCALE for this target."
    flutter test integration_test/app_test.dart -d "$SERIAL" --no-pub \
      --reporter expanded \
      --dart-define=ABCT_PERF_SCALE="$PERF_SCALE"
    ;;

  drive)
    flutter pub get
    echo "Performance budgets scaled x$PERF_SCALE for this target."
    flutter drive \
      --driver=test_driver/integration_test.dart \
      --target=integration_test/app_test.dart \
      -d "$SERIAL" --no-pub --no-dds \
      --dart-define=ABCT_PERF_SCALE="$PERF_SCALE"
    ;;

  run)
    if [[ "$MODE" == "debug" ]]; then
      # Attached: hot reload, and the debug engine needs the VM service.
      exec flutter run -d "$SERIAL" --debug
    fi

    echo "Building $MODE APK..."
    flutter build apk --"$MODE"
    APK="build/app/outputs/flutter-apk/app-$MODE.apk"
    [[ -f "$APK" ]] || { echo "ERROR: $APK not produced." >&2; exit 1; }

    adb -s "$SERIAL" install -r "$APK"
    adb -s "$SERIAL" shell am start -n "$APP_ID/.MainActivity" >/dev/null
    echo "Launched $APP_ID ($MODE) on $SERIAL."

    PID=""
    for _ in $(seq 1 20); do
      PID="$(adb -s "$SERIAL" shell pidof "$APP_ID" | tr -d '\r')"
      [[ -n "$PID" ]] && break
      sleep 1
    done
    if [[ -z "$PID" ]]; then
      echo "WARNING: could not resolve app pid; skipping log tail." >&2
      exit 0
    fi
    echo "Tailing logcat for pid $PID (Ctrl-C to stop)..."
    exec adb -s "$SERIAL" logcat --pid="$PID"
    ;;
esac
