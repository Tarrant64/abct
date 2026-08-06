#!/usr/bin/env bash
#
# Build-and-install for a physical iPhone, with build provenance.
#
# This is the documented push-to-phone procedure. It exists because of two
# incidents that plain `flutter build` / `flutter run` do not guard against:
#
#   1. STALE BINARY: an install made from an old or mid-refactor build is
#      indistinguishable from the current code on the phone. This script
#      refuses to build from a dirty tree (unless --allow-dirty) and embeds
#      the git SHA + dirty flag via --dart-define, shown in Settings → About.
#   2. SIGNATURE REJECTION: some embedded frameworks (notably the Flutter
#      native-assets objective_c.framework) end up ad-hoc signed, and
#      physical devices refuse the install (ApplicationVerificationFailed).
#      The script re-signs every embedded framework and re-seals the watch
#      app and Runner.app with their original entitlements.
#
# Usage:
#   scripts/build_device.sh [--allow-dirty] [--no-install] [--device <udid>]
#
# Environment:
#   ABCT_DEVICE_ID  target device UDID (overridden by --device)

set -euo pipefail

cd "$(dirname "$0")/.."

BUNDLE_ID="teamcata.com.ABCT-Mobile"
APP="build/ios/iphoneos/Runner.app"
WATCH_APP="$APP/Watch/ABCT-watchosapp Watch App.app"
DEVICE_ID="${ABCT_DEVICE_ID:-}"
ALLOW_DIRTY=false
INSTALL=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-dirty) ALLOW_DIRTY=true; shift ;;
    --no-install)  INSTALL=false; shift ;;
    --device)      DEVICE_ID="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ "$INSTALL" == true && -z "$DEVICE_ID" ]]; then
  echo "ERROR: no target device. Set ABCT_DEVICE_ID or pass --device <udid>." >&2
  echo "       (List devices with: xcrun devicectl list devices)" >&2
  exit 2
fi

# --- Provenance ------------------------------------------------------------
GIT_SHA="$(git rev-parse --short HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then
  if [[ "$ALLOW_DIRTY" != true ]]; then
    echo "ERROR: working tree is dirty. Commit or stash first, or pass --allow-dirty." >&2
    git status --short >&2
    exit 1
  fi
  GIT_DIRTY=true
else
  GIT_DIRTY=false
fi
echo "Building $GIT_SHA (dirty: $GIT_DIRTY)"

# --- Build -------------------------------------------------------------------
# Auto-increment the build number from commit count: watchOS caches each widget
# extension's complication descriptors and gallery recommendations per version
# and will not re-query an extension whose version hasn't changed.
BUILD_NUMBER="$(git rev-list --count HEAD)"
echo "Build number: $BUILD_NUMBER"

flutter build ios --release \
  --build-number="$BUILD_NUMBER" \
  --dart-define=GIT_SHA="$GIT_SHA" \
  --dart-define=GIT_DIRTY="$GIT_DIRTY"

# The embed-watch-app build phase downgrades watch failures to warnings, so a
# "successful" build can silently ship without (or with a skeleton) watch app.
if [[ ! -x "$WATCH_APP/ABCT-watchosapp Watch App" ]]; then
  echo "ERROR: watch app missing or skeletal at $WATCH_APP — build is incomplete." >&2
  exit 1
fi

# --- Re-sign -----------------------------------------------------------------
IDENTITY="$(security find-identity -v -p codesigning \
  | awk -F'"' '/Apple Development/ {print $2; exit}')"
if [[ -z "$IDENTITY" ]]; then
  echo "ERROR: no 'Apple Development' signing identity in the keychain." >&2
  exit 1
fi
echo "Re-signing with: $IDENTITY"

ENT_DIR="$(mktemp -d)"
trap 'rm -rf "$ENT_DIR"' EXIT
codesign -d --entitlements "$ENT_DIR/runner.plist" --xml "$APP" 2>/dev/null
codesign -d --entitlements "$ENT_DIR/watch.plist" --xml "$WATCH_APP" 2>/dev/null

for framework in "$APP"/Frameworks/*.framework; do
  codesign --force --sign "$IDENTITY" "$framework"
done
codesign --force --sign "$IDENTITY" \
  --entitlements "$ENT_DIR/watch.plist" "$WATCH_APP"
codesign --force --sign "$IDENTITY" \
  --entitlements "$ENT_DIR/runner.plist" "$APP"

# --- Install -----------------------------------------------------------------
if [[ "$INSTALL" != true ]]; then
  echo "Built $APP at $GIT_SHA (dirty: $GIT_DIRTY); install skipped."
  exit 0
fi

xcrun devicectl device install app --device "$DEVICE_ID" "$APP"

# flutter/devicectl installs have failed AFTER uninstalling the old app,
# leaving no app on the phone — verify it is actually present.
if ! xcrun devicectl device info apps --device "$DEVICE_ID" 2>/dev/null \
    | grep -q "$BUNDLE_ID"; then
  echo "ERROR: $BUNDLE_ID not present on device after install." >&2
  exit 1
fi

echo "Installed $GIT_SHA (dirty: $GIT_DIRTY) on $DEVICE_ID."
echo "Verify on the phone: Settings tab → About → Build shows $GIT_SHA."
