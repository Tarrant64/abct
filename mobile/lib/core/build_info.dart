import 'package:flutter/foundation.dart';

/// Build provenance embedded at compile time via `--dart-define`.
///
/// `scripts/build_device.sh` supplies `GIT_SHA` and `GIT_DIRTY` on every
/// device build. Builds made without them (IDE runs, a bare `flutter build`)
/// show "unknown", so a binary of unverifiable origin is recognizable at a
/// glance in Settings → About instead of silently passing for the latest
/// code — a stale mid-refactor binary cost a full false-regression debug
/// cycle on 2026-07-12.
abstract final class BuildInfo {
  /// Short git commit SHA the binary was built from.
  static const String gitSha =
      String.fromEnvironment('GIT_SHA', defaultValue: 'unknown');

  /// True when the working tree had uncommitted changes at build time.
  static const bool gitDirty = bool.fromEnvironment('GIT_DIRTY');

  /// Human-readable provenance label shown in Settings.
  static String get label => labelFor(gitSha, gitDirty);

  @visibleForTesting
  static String labelFor(String sha, bool dirty) {
    if (sha.isEmpty || sha == 'unknown') {
      return 'unknown — built without scripts/build_device.sh';
    }
    return dirty ? '$sha (dirty tree)' : sha;
  }
}
