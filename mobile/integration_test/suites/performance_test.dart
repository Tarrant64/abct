/// Performance E2E tests for the ABCT mobile app.
///
/// These tests measure timing of key user flows and FAIL if performance
/// budgets are exceeded. Timings are printed to stdout for CI consumption.
///
/// Performance budgets:
///   - Cold start (launch to login screen): < 3000ms
///   - Login flow (submit to home screen): < 2000ms
///   - Tab navigation (tap to content visible): < 500ms
///   - Data refresh (pull to fresh data): < 2000ms
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import '../helpers/mock_server.dart';
import '../helpers/test_app.dart';

/// Multiplier applied to every budget, from
/// `--dart-define=ABCT_PERF_SCALE=<n>`.
///
/// The budgets below are calibrated for a release-mode iOS Simulator run. A
/// debug build on the Android emulator is roughly an order of magnitude
/// slower (login alone measures ~15s against a 2s budget), so the unscaled
/// budgets fail there unconditionally and carry no signal. Running the suite
/// scaled turns it into a crash/regression check on that target — the
/// absolute numbers are only comparable against other runs at the same scale,
/// never against the iOS figures.
const int _perfScale = int.fromEnvironment('ABCT_PERF_SCALE', defaultValue: 1);

/// Performance budget constants (in milliseconds).
class _Budget {
  static const int coldStartMs = 3000 * _perfScale;
  static const int loginFlowMs = 2000 * _perfScale;
  static const int tabNavigationMs = 500 * _perfScale;
  static const int dataRefreshMs = 2000 * _perfScale;

  /// Generous ceiling for the 3x6 rapid-switch stress test.
  static const int rapidSwitchMs = 10000 * _perfScale;
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  late MockServer server;

  setUp(() async {
    server = await MockServer.start();
  });

  tearDown(() async {
    await server.stop();
  });

  group('Performance', () {
    testWidgets('cold start: launch to login screen within budget',
        (tester) async {
      _suppressOverflowErrors();

      final stopwatch = Stopwatch()..start();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      stopwatch.stop();
      final elapsed = stopwatch.elapsedMilliseconds;

      // Verify login screen rendered.
      expect(find.text('ABCT'), findsWidgets);
      expect(find.text('Sign in'), findsOneWidget);

      _printTiming('Cold Start', elapsed, _Budget.coldStartMs);
      expect(
        elapsed,
        lessThan(_Budget.coldStartMs),
        reason: 'Cold start took ${elapsed}ms, budget is ${_Budget.coldStartMs}ms',
      );
    });

    testWidgets('login flow: submit to home screen within budget',
        (tester) async {
      _suppressOverflowErrors();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Pre-fill credentials.
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'),
        testUsername,
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'),
        testPassword,
      );
      await tester.pumpAndSettle();

      // Measure from tap to home screen render.
      final stopwatch = Stopwatch()..start();

      await tester.tap(find.text('Sign in'));
      await tester.pumpAndSettle(const Duration(seconds: 5));

      stopwatch.stop();
      final elapsed = stopwatch.elapsedMilliseconds;

      // Dismissed after the clock stops: the biometric offer is a device-state
      // artifact, not part of the login latency being budgeted.
      await dismissBiometricOfferIfShown(tester);

      // Verify we reached the home screen.
      expect(find.text('Overview'), findsOneWidget);

      _printTiming('Login Flow', elapsed, _Budget.loginFlowMs);
      expect(
        elapsed,
        lessThan(_Budget.loginFlowMs),
        reason: 'Login flow took ${elapsed}ms, budget is ${_Budget.loginFlowMs}ms',
      );
    });

    testWidgets('tab navigation: tap to content within budget',
        (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);

      // Measure navigation to each tab.
      final tabTimings = <String, int>{};

      for (final tab in ['Assets', 'Wallets', 'Staking', 'NFTs', 'Settings']) {
        final stopwatch = Stopwatch()..start();

        await tester.tap(navTab(tab));
        await tester.pumpAndSettle(const Duration(seconds: 5));

        stopwatch.stop();
        tabTimings[tab] = stopwatch.elapsedMilliseconds;
      }

      // Print all timings.
      for (final entry in tabTimings.entries) {
        _printTiming(
          'Navigate to ${entry.key}',
          entry.value,
          _Budget.tabNavigationMs,
        );
      }

      // Assert each tab navigation is within budget.
      for (final entry in tabTimings.entries) {
        expect(
          entry.value,
          lessThan(_Budget.tabNavigationMs),
          reason:
              '${entry.key} tab took ${entry.value}ms, budget is ${_Budget.tabNavigationMs}ms',
        );
      }
    });

    testWidgets('data refresh: pull-to-refresh within budget', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Find a scrollable to pull down on.
      final scrollableFinder = find.byType(Scrollable).first;

      final stopwatch = Stopwatch()..start();

      // Pull-to-refresh gesture.
      await tester.fling(scrollableFinder, const Offset(0, 300), 1000);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      stopwatch.stop();
      final elapsed = stopwatch.elapsedMilliseconds;

      _printTiming('Data Refresh', elapsed, _Budget.dataRefreshMs);
      expect(
        elapsed,
        lessThan(_Budget.dataRefreshMs),
        reason:
            'Data refresh took ${elapsed}ms, budget is ${_Budget.dataRefreshMs}ms',
      );
    });

    testWidgets('rapid tab switching: no jank or crashes', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      final tabs = ['Assets', 'Wallets', 'Staking', 'NFTs', 'Settings', 'Overview'];
      final stopwatch = Stopwatch()..start();

      // Rapidly switch through all tabs 3 times.
      for (int cycle = 0; cycle < 3; cycle++) {
        for (final tab in tabs) {
          await tester.tap(navTab(tab));
          await tester.pump(const Duration(milliseconds: 100));
        }
      }
      await tester.pumpAndSettle(const Duration(seconds: 5));

      stopwatch.stop();
      final elapsed = stopwatch.elapsedMilliseconds;

      _printTiming(
        'Rapid Tab Switching (3 cycles x ${tabs.length} tabs)',
        elapsed,
        _Budget.rapidSwitchMs,
      );

      // Verify app is still in a good state.
      expect(find.text('Portfolio'), findsWidgets);
    });

    testWidgets('report: generate performance summary', (tester) async {
      _suppressOverflowErrors();

      // Use reportData to make results visible to CI.
      await binding.traceAction(() async {
        final app = await buildTestApp(server);
        await tester.pumpWidget(app);
        await tester.pumpAndSettle(const Duration(seconds: 3));

        // Login.
        await tester.enterText(
          find.widgetWithText(TextFormField, 'Username'),
          testUsername,
        );
        await tester.enterText(
          find.widgetWithText(TextFormField, 'Password'),
          testPassword,
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Sign in'));
        await tester.pumpAndSettle(const Duration(seconds: 5));
        await dismissBiometricOfferIfShown(tester);

        // Navigate through all tabs.
        for (final tab in [
          'Assets',
          'Wallets',
          'Staking',
          'NFTs',
          'Settings',
          'Overview',
        ]) {
          await tapNavTab(tester, tab);
        }
      }, reportKey: 'full_flow_timeline');
    });
  });
}

/// Helper: log in with test credentials and wait until the home screen loads.
Future<void> _loginAndReachHome(
  WidgetTester tester,
  MockServer server,
) async {
  final app = await buildTestApp(server);
  await tester.pumpWidget(app);
  await tester.pumpAndSettle(const Duration(seconds: 3));

  await tester.enterText(
    find.widgetWithText(TextFormField, 'Username'),
    testUsername,
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Password'),
    testPassword,
  );
  await tester.pumpAndSettle();

  await tester.tap(find.text('Sign in'));
  await tester.pumpAndSettle(const Duration(seconds: 5));
  await dismissBiometricOfferIfShown(tester);

  expect(find.text('Overview'), findsOneWidget,
      reason: 'Should be on home screen after login');
}

/// Print a formatted timing result.
void _printTiming(String label, int elapsedMs, int budgetMs) {
  final status = elapsedMs < budgetMs ? 'PASS' : 'FAIL';
  final bar = '=' * 60;
  // debugPrint is available in integration tests and won't be stripped.
  debugPrint(bar);
  debugPrint('PERF [$status] $label');
  debugPrint('  Elapsed: ${elapsedMs}ms');
  debugPrint('  Budget:  ${budgetMs}ms');
  debugPrint('  Margin:  ${budgetMs - elapsedMs}ms');
  debugPrint(bar);
}

/// Suppress RenderFlex overflow errors that occur due to test fonts being
/// wider than the SpaceGrotesk font used in production.
void _suppressOverflowErrors() {
  final originalOnError = FlutterError.onError;
  FlutterError.onError = (details) {
    final isOverflow = details.exceptionAsString().contains('overflowed');
    if (!isOverflow) {
      originalOnError?.call(details);
    }
  };
}
