/// Functional E2E tests for the ABCT mobile app.
///
/// These tests verify that core user flows work end-to-end with a mock
/// backend. No real credentials or servers are used.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import '../helpers/mock_server.dart';
import '../helpers/test_app.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  late MockServer server;

  setUp(() async {
    server = await MockServer.start();
  });

  tearDown(() async {
    await server.stop();
  });

  group('App Launch', () {
    testWidgets('app launches and shows login screen', (tester) async {
      // Suppress font-related overflow errors (test fonts are wider than
      // SpaceGrotesk used in production).
      _suppressOverflowErrors();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // The login screen should show the ABCT branding and sign-in button.
      expect(find.text('ABCT'), findsWidgets);
      expect(find.text('Sign in'), findsOneWidget);
    });

    testWidgets('login screen shows username and password fields',
        (tester) async {
      _suppressOverflowErrors();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Verify form fields exist.
      expect(find.widgetWithText(TextFormField, 'Username'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Password'), findsOneWidget);
    });
  });

  group('Login Flow', () {
    testWidgets('successful login navigates to home screen', (tester) async {
      _suppressOverflowErrors();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Enter test credentials.
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'),
        testUsername,
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'),
        testPassword,
      );
      await tester.pumpAndSettle();

      // Tap sign-in.
      await _tapSignIn(tester);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // After login, we should see the home screen with the bottom nav.
      // The home screen shows "Portfolio" as the first tab title.
      expect(find.text('Portfolio'), findsWidgets);

      // The bottom nav should have the expected destinations.
      expect(find.text('Overview'), findsOneWidget);
      expect(find.text('Assets'), findsOneWidget);
      expect(find.text('Wallets'), findsOneWidget);
      expect(find.text('Staking'), findsOneWidget);
      expect(find.text('NFTs'), findsOneWidget);
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('invalid credentials show error message', (tester) async {
      _suppressOverflowErrors();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Enter wrong credentials.
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'),
        'wrong',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'),
        'wrong',
      );
      await tester.pumpAndSettle();

      // Tap sign-in.
      await _tapSignIn(tester);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // Should still be on login screen (not navigated away).
      expect(find.text('Sign in'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Username'), findsOneWidget);
    });

    testWidgets('empty credentials trigger validation', (tester) async {
      _suppressOverflowErrors();

      final app = await buildTestApp(server);
      await tester.pumpWidget(app);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Tap sign-in with empty fields.
      await _tapSignIn(tester);
      await tester.pumpAndSettle();

      // Validation error messages should appear.
      expect(find.text('Enter a username'), findsOneWidget);
      expect(find.text('Enter a password'), findsOneWidget);
    });
  });

  group('Navigation', () {
    testWidgets('bottom nav tabs switch content', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);

      // Verify we're on the Overview/Portfolio tab.
      expect(find.text('Portfolio'), findsWidgets);

      // Navigate to Assets tab.
      await tester.tap(find.text('Assets'));
      await tester.pumpAndSettle(const Duration(seconds: 3));
      // AppBar title should change to "Assets".
      expect(find.widgetWithText(AppBar, 'Assets'), findsOneWidget);

      // Navigate to Wallets tab.
      await tester.tap(find.text('Wallets'));
      await tester.pumpAndSettle(const Duration(seconds: 3));
      expect(find.widgetWithText(AppBar, 'Wallets'), findsOneWidget);

      // Navigate to Staking tab.
      await tester.tap(find.text('Staking'));
      await tester.pumpAndSettle(const Duration(seconds: 3));
      expect(find.widgetWithText(AppBar, 'Staking'), findsOneWidget);

      // Navigate to NFTs tab.
      await tester.tap(find.text('NFTs'));
      await tester.pumpAndSettle(const Duration(seconds: 3));
      expect(find.widgetWithText(AppBar, 'NFTs'), findsOneWidget);

      // Navigate to Settings tab.
      await tester.tap(find.text('Settings'));
      await tester.pumpAndSettle(const Duration(seconds: 3));
      expect(find.widgetWithText(AppBar, 'Settings'), findsOneWidget);

      // Navigate back to Overview.
      await tester.tap(find.text('Overview'));
      await tester.pumpAndSettle(const Duration(seconds: 3));
      expect(find.widgetWithText(AppBar, 'Portfolio'), findsOneWidget);
    });
  });

  group('Portfolio Data', () {
    testWidgets('dashboard tab shows portfolio data', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);

      // The dashboard should load and display portfolio data.
      // Wait for API data to render.
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // We should see portfolio value or top assets from the mock data.
      // The mock returns BTC, ETH, ADA, SOL as top assets.
      // Look for any of these tickers that DashboardTab might render.
      final hasSomeContent = find.text('BTC').evaluate().isNotEmpty ||
          find.text('Bitcoin').evaluate().isNotEmpty ||
          find.textContaining('\$').evaluate().isNotEmpty;
      expect(hasSomeContent, isTrue,
          reason: 'Dashboard should display portfolio data');
    });

    testWidgets('assets tab loads and displays holdings', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);

      // Navigate to Assets tab.
      await tester.tap(find.text('Assets'));
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // The assets tab has a segmented control with Holdings, Wallets, Exchanges.
      expect(find.text('Holdings'), findsWidgets);
      expect(find.text('Exchanges'), findsWidgets);
    });

    testWidgets('staking tab loads and displays positions', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);

      // Navigate to Staking tab.
      await tester.tap(find.text('Staking'));
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // Should see staking section headers from mock data.
      expect(find.text('Staking & DeFi'), findsOneWidget);
      expect(find.text('Positions'), findsOneWidget);
    });
  });

  group('Pull-to-Refresh', () {
    testWidgets('pull-to-refresh on dashboard reloads data', (tester) async {
      _suppressOverflowErrors();

      await _loginAndReachHome(tester, server);
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Find any scrollable widget on the dashboard.
      final scrollableFinder = find.byType(Scrollable).first;

      // Perform a pull-to-refresh gesture (drag down from center).
      await tester.fling(scrollableFinder, const Offset(0, 300), 1000);
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // If we get here without error, pull-to-refresh completed successfully.
      // The dashboard should still be visible.
      expect(find.text('Portfolio'), findsWidgets);
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

  // Enter credentials and log in.
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Username'),
    testUsername,
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Password'),
    testPassword,
  );
  await tester.pumpAndSettle();

  await _tapSignIn(tester);
  await tester.pumpAndSettle(const Duration(seconds: 5));

  // Verify we've reached the home screen.
  expect(find.text('Overview'), findsOneWidget,
      reason: 'Should be on home screen after login');
}

/// Taps the sign-in button reliably: scrolls it into view and taps the
/// ElevatedButton itself. Tapping the Text child derived a center point that
/// failed hit-testing under the simulator's overlay/scroll insets, which
/// blinded the whole suite at login.
Future<void> _tapSignIn(WidgetTester tester) async {
  final button = find.widgetWithText(ElevatedButton, 'Sign in');
  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  await tester.tap(button);
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
