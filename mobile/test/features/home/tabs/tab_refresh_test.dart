import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/models/portfolio_history.dart';
import 'package:abct_mobile/core/models/portfolio_instant.dart';
import 'package:abct_mobile/core/models/portfolio_summary.dart';
import 'package:abct_mobile/core/models/staking_summary.dart';
import 'package:abct_mobile/core/models/wallets_summary.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/core/network/cache_interceptor.dart';
import 'package:abct_mobile/core/ui/app_refresh.dart';
import 'package:abct_mobile/features/home/tabs/dashboard_tab.dart';
import 'package:abct_mobile/features/home/tabs/staking_tab.dart';
import 'package:abct_mobile/features/home/tabs/wallets_tab.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Per-tab refresh-signal and revalidation-subscription behavior, using an
/// injected fake client (the MOBILE-2/3 deferred test debt).
///
/// Covered per tab: the app-resume signal triggers a silent reload (guarded
/// by the 30s min-interval), and a background revalidation landing for the
/// tab's endpoint applies fresh data without any loading spinner.
final _profile = ConnectionProfile(
  name: 'test',
  baseUrl: 'https://example.invalid',
);

class FakeStakingApi extends ApiClient {
  FakeStakingApi() : super(_profile);

  int fetches = 0;
  double staked = 1500;

  @override
  Future<StakingSummary> getStaking({
    bool refresh = false,
    bool revalidate = false,
  }) async {
    fetches++;
    return StakingSummary(
      totalStakedUsd: staked,
      totalRewardsUsd: 10,
      positions: const [],
    );
  }
}

class FakeWalletsApi extends ApiClient {
  FakeWalletsApi() : super(_profile);

  int fetches = 0;

  @override
  Future<WalletsSummary> getWallets({
    String? blockchain,
    bool includeBalances = true,
    bool refresh = false,
    bool revalidate = false,
  }) async {
    fetches++;
    return WalletsSummary(
      totalWallets: 0,
      wallets: const [],
      totalValueUsd: 0,
    );
  }
}

class FakeDashboardApi extends ApiClient {
  FakeDashboardApi() : super(_profile);

  int summaryFetches = 0;
  double total = 1500;

  @override
  Future<PortfolioSummary> getPortfolioSummary({
    bool refresh = false,
    bool revalidate = false,
    bool includeSparklines = true,
  }) async {
    summaryFetches++;
    return PortfolioSummary.fromJson({'total_value_usd': total});
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
    final now = DateTime.now();
    return PortfolioHistory(
      range: range,
      interval: 'hour',
      dataPoints: 2,
      chartData: [
        PortfolioHistoryPoint(
          timestamp: now.subtract(const Duration(hours: 1)),
          totalValueUsd: total - 10,
          onChainValueUsd: total - 10,
          offChainValueUsd: 0,
          nativeValues: const {},
        ),
        PortfolioHistoryPoint(
          timestamp: now,
          totalValueUsd: total,
          onChainValueUsd: total,
          offChainValueUsd: 0,
          nativeValues: const {},
        ),
      ],
      summary: PortfolioHistorySummary(
        startingValue: total - 10,
        endingValue: total,
        changeUsd: 10,
        changePercent: 1,
        highestValue: total,
        lowestValue: total - 10,
      ),
    );
  }
}

Widget harness(Widget tab) => MaterialApp(home: Scaffold(body: tab));

void backdate(WidgetTester tester, Type widgetType) {
  (tester.state(find.byType(widgetType)) as dynamic)
      .debugBackdateLastLoad(const Duration(seconds: 31));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // flutter_secure_storage channel no-op (DashboardTab persists its total).
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

  group('StakingTab', () {
    testWidgets('resume signal reloads silently and updates values',
        (tester) async {
      final api = FakeStakingApi();
      await tester
          .pumpWidget(harness(StakingTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      expect(api.fetches, 1);
      expect(find.textContaining('1.5K'), findsWidgets);

      api.staked = 2500;
      backdate(tester, StakingTab);
      AppRefreshSignal.instance.debugEmitSignal();
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      expect(api.fetches, 2);
      expect(find.textContaining('2.5K'), findsWidgets);
    });

    testWidgets('resume signal within the min interval does not reload',
        (tester) async {
      final api = FakeStakingApi();
      await tester
          .pumpWidget(harness(StakingTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      expect(api.fetches, 1);

      // No backdating: the tab just loaded, so the guard suppresses this.
      AppRefreshSignal.instance.debugEmitSignal();
      await tester.pumpAndSettle();

      expect(api.fetches, 1);
    });

    testWidgets('revalidation for its endpoint applies silently',
        (tester) async {
      final api = FakeStakingApi();
      await tester
          .pumpWidget(harness(StakingTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      expect(api.fetches, 1);

      api.staked = 2500;
      CacheInterceptor.debugNotifyRevalidated(
        'https://example.invalid/api/mobile/defi/staking',
        <String, dynamic>{},
      );
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      expect(api.fetches, 2);
      expect(find.textContaining('2.5K'), findsWidgets);
    });
  });

  group('WalletsTab', () {
    testWidgets('resume signal reloads silently', (tester) async {
      final api = FakeWalletsApi();
      await tester
          .pumpWidget(harness(WalletsTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      expect(api.fetches, 1);

      backdate(tester, WalletsTab);
      AppRefreshSignal.instance.debugEmitSignal();
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      expect(api.fetches, 2);
    });

    testWidgets('revalidation for its endpoint applies silently',
        (tester) async {
      final api = FakeWalletsApi();
      await tester
          .pumpWidget(harness(WalletsTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      expect(api.fetches, 1);

      CacheInterceptor.debugNotifyRevalidated(
        'https://example.invalid/api/mobile/wallets?include_balances=true',
        <String, dynamic>{},
      );
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      expect(api.fetches, 2);
    });
  });

  group('DashboardTab', () {
    testWidgets('resume signal reloads silently and updates the total',
        (tester) async {
      final api = FakeDashboardApi();
      await tester.pumpWidget(
          harness(DashboardTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      expect(api.summaryFetches, 1);
      expect(find.textContaining('1,5'), findsWidgets);

      api.total = 4242;
      backdate(tester, DashboardTab);
      AppRefreshSignal.instance.debugEmitSignal();
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      expect(api.summaryFetches, 2);
      expect(find.textContaining('4,242'), findsWidgets);
    });

    testWidgets(
        'revalidated summary payload applies directly without a re-fetch',
        (tester) async {
      final api = FakeDashboardApi();
      await tester.pumpWidget(
          harness(DashboardTab(profile: _profile, apiClient: api)));
      await tester.pumpAndSettle();
      final fetchesBefore = api.summaryFetches;

      CacheInterceptor.debugNotifyRevalidated(
        'https://example.invalid/api/mobile/portfolio/summary',
        <String, dynamic>{'total_value_usd': 9999.0},
      );
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      // The dashboard parses the pushed payload; no additional fetch.
      expect(api.summaryFetches, fetchesBefore);
      expect(find.textContaining('9,999'), findsWidgets);
    });
  });
}
