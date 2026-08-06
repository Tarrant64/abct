import 'package:flutter/foundation.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

/// Wrapper around Sentry for error reporting.
///
/// In debug mode, errors are only logged to the console.
/// In release mode, errors are sent to Sentry if a DSN is configured.
class ErrorReporting {
  static bool get _enabled => !kDebugMode && Sentry.isEnabled;

  static Future<void> captureException(
    dynamic exception, {
    dynamic stackTrace,
    String? hint,
  }) async {
    if (_enabled) {
      await Sentry.captureException(
        exception,
        stackTrace: stackTrace,
        hint: hint != null ? Hint.withMap({'message': hint}) : null,
      );
    }
  }

  static void addBreadcrumb(String message, {String? category}) {
    if (_enabled) {
      Sentry.addBreadcrumb(Breadcrumb(
        message: message,
        category: category,
        timestamp: DateTime.now(),
      ));
    }
  }
}
