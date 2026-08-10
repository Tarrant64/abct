#!/usr/bin/env bash
#
# ABCT Mobile — Android emulator lifecycle
#
# There is no physical Android test device, so an emulator is the only Android
# target. This script starts/stops/inspects the project's AVDs without needing
# Android Studio, and without the caller having to export the SDK/JDK paths.
#
# Usage:
#   ./scripts/android_emu.sh start [--headless] [--avd <name>] [--wipe]
#   ./scripts/android_emu.sh stop  [--avd <name>]
#   ./scripts/android_emu.sh status
#   ./scripts/android_emu.sh serial          # print the serial of the running AVD
#
# Environment:
#   ABCT_AVD        default AVD name (default: abct_pixel)
#   ANDROID_HOME    SDK root (default: the Homebrew commandlinetools cask)
#   JAVA_HOME       JDK 17 root (default: the Homebrew openjdk@17 cask)
#
# Exit codes:
#   0 = success
#   1 = runtime failure (AVD missing, boot timeout, ...)
#   2 = usage error / missing prerequisite
#
# NOTE: this machine may host AVDs belonging to other projects, under a
# different SDK. Never start, wipe, or delete one of those from here.

set -euo pipefail

DEFAULT_AVD="${ABCT_AVD:-abct_pixel}"
BOOT_TIMEOUT_SECS=300

# ---- Toolchain resolution -------------------------------------------------

if [[ -z "${JAVA_HOME:-}" ]]; then
  if command -v brew &>/dev/null && brew --prefix openjdk@17 &>/dev/null; then
    JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
  fi
fi
: "${ANDROID_HOME:=/opt/homebrew/share/android-commandlinetools}"
export JAVA_HOME ANDROID_HOME
export PATH="${JAVA_HOME:-}/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

require_sdk() {
  if [[ ! -d "$ANDROID_HOME" ]]; then
    echo "ERROR: Android SDK not found at $ANDROID_HOME" >&2
    echo "       Install it with: brew install --cask android-commandlinetools" >&2
    echo "       Or set ANDROID_HOME to your SDK root." >&2
    exit 2
  fi
  for tool in adb emulator; do
    if ! command -v "$tool" &>/dev/null; then
      echo "ERROR: '$tool' not found under $ANDROID_HOME." >&2
      echo "       Expected in platform-tools/ and emulator/." >&2
      exit 2
    fi
  done
  if [[ -z "${JAVA_HOME:-}" || ! -x "${JAVA_HOME}/bin/java" ]]; then
    echo "ERROR: JDK 17 not found (JAVA_HOME='${JAVA_HOME:-unset}')." >&2
    echo "       Install it with: brew install openjdk@17" >&2
    exit 2
  fi
}

# Serial of the running emulator hosting $1, or empty.
avd_serial() {
  local want="$1" serial name
  for serial in $(adb devices | awk '/^emulator-/ {print $1}'); do
    name="$(adb -s "$serial" emu avd name 2>/dev/null | head -1 | tr -d '\r')"
    if [[ "$name" == "$want" ]]; then
      echo "$serial"
      return 0
    fi
  done
  return 0
}

cmd_start() {
  local avd="$DEFAULT_AVD" headless=false wipe=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --headless) headless=true; shift ;;
      --wipe)     wipe=true; shift ;;
      --avd)      avd="$2"; shift 2 ;;
      *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
  done
  require_sdk

  if ! avdmanager list avd 2>/dev/null | grep -q "Name: $avd\$"; then
    echo "ERROR: AVD '$avd' does not exist." >&2
    echo "       Create it (see README, 'Android emulator / testing'):" >&2
    echo "       avdmanager create avd -n $avd -k 'system-images;android-35;google_apis;arm64-v8a' -d pixel_6" >&2
    exit 1
  fi

  local existing
  existing="$(avd_serial "$avd")"
  if [[ -n "$existing" ]]; then
    echo "AVD '$avd' already running on $existing."
    return 0
  fi

  local args=(-avd "$avd" -no-boot-anim -netdelay none -netspeed full)
  $headless && args+=(-no-window -no-audio)
  $wipe && args+=(-wipe-data)

  echo "Starting '$avd'$($headless && echo ' (headless)')..."
  # Detached: the emulator must outlive this script.
  nohup emulator "${args[@]}" >/tmp/abct-emulator-$avd.log 2>&1 &
  disown || true

  echo -n "Waiting for boot"
  local waited=0 serial=""
  while (( waited < BOOT_TIMEOUT_SECS )); do
    serial="$(avd_serial "$avd")"
    if [[ -n "$serial" ]]; then
      if [[ "$(adb -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then
        echo ""
        echo "Booted: $avd on $serial"
        return 0
      fi
    fi
    echo -n "."
    sleep 3
    waited=$(( waited + 3 ))
  done

  echo ""
  echo "ERROR: '$avd' did not report boot_completed within ${BOOT_TIMEOUT_SECS}s." >&2
  echo "       Emulator log: /tmp/abct-emulator-$avd.log" >&2
  exit 1
}

cmd_stop() {
  local avd="$DEFAULT_AVD"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --avd) avd="$2"; shift 2 ;;
      *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
  done
  require_sdk

  local serial
  serial="$(avd_serial "$avd")"
  if [[ -z "$serial" ]]; then
    echo "AVD '$avd' is not running."
    return 0
  fi
  echo "Stopping '$avd' ($serial)..."
  adb -s "$serial" emu kill >/dev/null 2>&1 || true

  local waited=0
  while (( waited < 30 )); do
    [[ -z "$(avd_serial "$avd")" ]] && { echo "Stopped."; return 0; }
    sleep 2
    waited=$(( waited + 2 ))
  done
  echo "WARNING: '$avd' still listed after 30s; check for stray qemu processes." >&2
}

cmd_status() {
  require_sdk
  echo "ANDROID_HOME: $ANDROID_HOME"
  echo "JAVA_HOME:    $JAVA_HOME"
  echo ""
  echo "Defined AVDs:"
  avdmanager list avd 2>/dev/null | grep "    Name:" | sed 's/^ *//' || echo "  (none)"
  echo ""
  echo "Running emulators:"
  local serial name found=false
  for serial in $(adb devices | awk '/^emulator-/ {print $1}'); do
    name="$(adb -s "$serial" emu avd name 2>/dev/null | head -1 | tr -d '\r')"
    echo "  $serial -> ${name:-unknown}"
    found=true
  done
  $found || echo "  (none)"
}

cmd_serial() {
  require_sdk
  local serial
  serial="$(avd_serial "$DEFAULT_AVD")"
  if [[ -z "$serial" ]]; then
    echo "ERROR: AVD '$DEFAULT_AVD' is not running. Start it with: $0 start" >&2
    exit 1
  fi
  echo "$serial"
}

case "${1:-}" in
  start)  shift; cmd_start "$@" ;;
  stop)   shift; cmd_stop "$@" ;;
  status) shift; cmd_status ;;
  serial) shift; cmd_serial ;;
  *)
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
