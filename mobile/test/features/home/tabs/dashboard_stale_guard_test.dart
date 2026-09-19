import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/models/portfolio_history.dart';
import 'package:abct_mobile/core/models/portfolio_instant.dart';
import 'package:abct_mobile/core/models/portfolio_summary.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/core/network/cache_interceptor.dart';
import 'package:abct_mobile/core/ui/app_refresh.dart';
import 'package:abct_mobile/features/home/tabs/dashboard_tab.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Monotonic-display regression coverage (ABCT-MOBILE-STALE-20260918
/// follow-up). The cache-key canonicalization fix keeps the client HTTP
/// cache itself consistent between a hard refresh and an ordinary load, but
/// it does not by itself stop an older response from applying to the UI
/// after a newer one already landed — e.g. a foreground-resume reload
/// racing a still-in-flight fresher write. DashboardTab's
/// `_isStalerThanDisplayed` guard is the last line of defense against that:
/// any cache-sourced summary (ordinary load, resume reload, background
/// revalidation) older than what's already on screen must be discarded.
/// Only an explicit hard refresh is exempt (it always demands and gets a
/// live server recompute).
final _profile = ConnectionProfile(
  name: 'test',
  baseUrl: 'https://example.invalid',
);

class MonotonicDashboardApi extends ApiClient {
  MonotonicDashboardApi() : super(_profile);

  double total = 1000;
  DateTime lastUpdated = DateTime.utc(2026, 9, 18, 4);

  @override
  Future<PortfolioSummary> getPortfolioSummary({
    bool refresh = false,
    bool revalidate = false,
    bool includeSparklines = true,
  }) async {
    return PortfolioSummary.fromJson({
      'total_value_usd': total,
      'last_updated': lastUpdated.toIso8601String(),
    });
  }

  @override
  Future<PortfolioInstant> getPortfolioInstant({
    bool revalidate = false,
  }) async {
    return PortfolioInstant(
      totalUsd: total,
      breakdown: const {},
      topHoldings: const [],
      hasPositions: true,
    );
  }

  @override
  Future<PortfolioHistory> getPortfolioHistory({
    required String range,
    bool revalidate = false,
  }) async {
    return PortfolioHistory(
      range: range,
      interval: 'hour',
      dataPoints: 0,
      chartData: const [],
      summary: PortfolioHistorySummary(
        startingValue: total,
        endingValue: total,
        changeUsd: 0,
        changePercent: 0,
        highestValue: total,
        lowestValue: total,
      ),
    );
  }
}

void backdate(WidgetTester tester) {
  (tester.state(find.byType(DashboardTab)) as dynamic)
      .debugBackdateLastLoad(const Duration(seconds: 31));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final secureValues = <String, String>{};
  const channel =
      MethodChannel('plugins.it_nomads.com/flutter_secure_storage');

  setUp(() {
    secureValues.clear();
    ApiClient.resetSharedForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      final args =
          (call.arguments as Map?)?.cast<String, dynamic>() ?? const {};
      switch (call.method) {
        case 'read':
          return secureValues[args['key']];
        case 'write':
          secureValues[args['key'] as String] = args['value'] as String;
          return null;
        case 'delete':
          secureValues.remove(args['key']);
          return null;
        case 'readAll':
          return Map<String, String>.from(secureValues);
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  Future<MonotonicDashboardApi> pumpLoadedDashboard(WidgetTester tester) async {
    final api = MonotonicDashboardApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DashboardTab(profile: _profile, apiClient: api),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('1,000'), findsWidgets);
    return api;
  }

  testWidgets(
      'a foreground-resume reload does not roll the total back past a '
      'fresher hard refresh', (tester) async {
    final api = await pumpLoadedDashboard(tester);

    // User's hard refresh at "7:00 PM": fresh, current data.
    api.total = 2000;
    api.lastUpdated = DateTime.utc(2026, 9, 18, 19);
    final state = tester.state(find.byType(DashboardTab)) as dynamic;
    await state.debugSmartRefresh(hard: true);
    await tester.pumpAndSettle();
    expect(find.textContaining('2,000'), findsWidgets);

    // Reopen ~20-30 minutes later: the ordinary (non-refresh) load path
    // returns an OLDER payload than what's displayed (simulating a stale
    // cache-sourced response — e.g. the client cache hadn't converged yet,
    // or a slow-to-land background revalidation raced this one). The guard
    // must keep showing the fresher 7:00 PM data, not regress to it.
    api.total = 500;
    api.lastUpdated = DateTime.utc(2026, 9, 18, 4); // the ~4 AM snapshot
    backdate(tester);
    AppRefreshSignal.instance.debugEmitSignal();
    await tester.pumpAndSettle();

    expect(find.textContaining('2,000'), findsWidgets);
    expect(find.textContaining('500'), findsNothing);
  });

  testWidgets(
      'a foreground-resume reload DOES apply when it is genuinely newer',
      (tester) async {
    final api = await pumpLoadedDashboard(tester);

    api.total = 2000;
    api.lastUpdated = DateTime.utc(2026, 9, 18, 19);
    final state = tester.state(find.byType(DashboardTab)) as dynamic;
    await state.debugSmartRefresh(hard: true);
    await tester.pumpAndSettle();
    expect(find.textContaining('2,000'), findsWidgets);

    // A later, genuinely newer reload must still win.
    api.total = 2100;
    api.lastUpdated = DateTime.utc(2026, 9, 18, 19, 30);
    backdate(tester);
    AppRefreshSignal.instance.debugEmitSignal();
    await tester.pumpAndSettle();

    expect(find.textContaining('2,100'), findsWidgets);
  });

  testWidgets(
      'a stale background revalidation for /portfolio/summary is ignored',
      (tester) async {
    await pumpLoadedDashboard(tester);
    final state = tester.state(find.byType(DashboardTab)) as dynamic;
    await state.debugSmartRefresh(hard: true); // still total=1000 here
    await tester.pumpAndSettle();

    // Push display forward first.
    final freshData = {
      'total_value_usd': 3000.0,
      'last_updated': DateTime.utc(2026, 9, 18, 19).toIso8601String(),
    };
    CacheInterceptor.debugNotifyRevalidated(
      'https://example.invalid/api/mobile/portfolio/summary',
      freshData,
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('3,000'), findsWidgets);

    // A stale revalidation (older than what's displayed) must be ignored.
    final staleData = {
      'total_value_usd': 999.0,
      'last_updated': DateTime.utc(2026, 9, 18, 4).toIso8601String(),
    };
    CacheInterceptor.debugNotifyRevalidated(
      'https://example.invalid/api/mobile/portfolio/summary',
      staleData,
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('3,000'), findsWidgets);
    expect(find.textContaining('999'), findsNothing);
  });
}
