import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

import 'app.dart';
import 'core/services/background_sync.dart';
import 'core/services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize local notifications.
  await NotificationService.initialize();

  // Initialize background task scheduler (iOS/Android only — workmanager
  // has no macOS implementation and will hang if called).
  if (Platform.isIOS || Platform.isAndroid) {
    await BackgroundSync.initialize();
    // Re-submit the periodic task if the user has it enabled: the iOS
    // BGAppRefreshTask chain only self-reschedules from a completed run, so
    // without this a force-quit or expired request would silence background
    // sync until the user re-toggled the setting.
    await BackgroundSync.reArmIfEnabled();
  }

  // Sentry DSN is injected via --dart-define=SENTRY_DSN=...
  // If empty or unset, Sentry is effectively disabled.
  const sentryDsn = String.fromEnvironment('SENTRY_DSN');

  if (sentryDsn.isNotEmpty) {
    await SentryFlutter.init(
      (options) {
        options.dsn = sentryDsn;
        options.tracesSampleRate = 0.2;
      },
      appRunner: () => runApp(const AbctApp()),
    );
  } else {
    runApp(const AbctApp());
  }
}
