/// Test driver for running integration tests via `flutter drive`.
///
/// This is the standard Flutter integration test driver. It is used when
/// running tests with:
///   flutter drive --driver=test_driver/integration_test.dart \
///                 --target=integration_test/app_test.dart
///
/// For most use cases, prefer:
///   flutter test integration_test/app_test.dart -d <device>
library;

import 'package:integration_test/integration_test_driver.dart';

Future<void> main() => integrationDriver();
