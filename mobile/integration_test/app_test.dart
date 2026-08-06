/// ABCT Mobile — End-to-End Integration Tests
///
/// Run with:
///   flutter test integration_test/app_test.dart
///
/// Or target a specific iOS simulator:
///   flutter test integration_test/app_test.dart -d "iPhone 16 Pro"
///
/// These tests launch the real app with a mock HTTP backend and exercise
/// the full UI flow: login, navigation, data display, pull-to-refresh,
/// and performance budgets.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'suites/functional_test.dart' as functional;
import 'suites/performance_test.dart' as performance;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  functional.main();
  performance.main();
}
