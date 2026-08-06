import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/models/portfolio_history.dart';
import 'package:abct_mobile/core/models/portfolio_instant.dart';
import 'package:abct_mobile/core/models/portfolio_summary.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/features/home/tabs/dashboard_tab.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Hard pull-to-refresh honesty (PRICE-1): a hard pull is an explicit demand
/// for live data, so its failure must surface via the SnackBar affordance and
/// must NOT be papered over by cached/instant data. Soft-pull failures keep
/// the silent fallback (the user still sees the previous payload).
final _profile = ConnectionProfile(
  name: 'test',
  baseUrl: 'https://example.invalid',
);

class FlakyDashboardApi extends ApiClient {
  FlakyDashboardApi() : super(_profile);

  /// When true, summary fetches fail as an unreachable server would.
  bool failSummary = false;
  double total = 1500;

  @override
  Future<PortfolioSummary> getPortfolioSummary({
    bool refresh = false,
    bool revalidate = false,
    bool includeSparklines = true,
  }) async {
    if (failSummary) {
      throw DioException.connectionError(
        requestOptions: RequestOptions(path: '/api/mobile/portfolio/summary'),
        reason: 'connection refused',
      );
    }
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

  Future<FlakyDashboardApi> pumpLoadedDashboard(WidgetTester tester) async {
    final api = FlakyDashboardApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: DashboardTab(profile: _profile, apiClient: api),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('1,500'), findsWidgets);
    return api;
  }

  testWidgets('hard pull failure shows the error SnackBar and keeps the '
      'previous data on screen', (tester) async {
    final api = await pumpLoadedDashboard(tester);

    api.failSummary = true;
    final state = tester.state(find.byType(DashboardTab)) as dynamic;
    await state.debugSmartRefresh(hard: true);
    await tester.pumpAndSettle();

    expect(find.textContaining('Refresh failed'), findsOneWidget);
    expect(find.textContaining('1,500'), findsWidgets); // data kept
  });

  testWidgets('soft pull failure stays silent (previous data, no SnackBar)',
      (tester) async {
    final api = await pumpLoadedDashboard(tester);

    api.failSummary = true;
    final state = tester.state(find.byType(DashboardTab)) as dynamic;
    await state.debugSmartRefresh(hard: false);
    await tester.pumpAndSettle();

    expect(find.textContaining('Refresh failed'), findsNothing);
    expect(find.textContaining('1,500'), findsWidgets);
  });

  testWidgets('hard pull success replaces the total', (tester) async {
    final api = await pumpLoadedDashboard(tester);

    api.total = 2600;
    final state = tester.state(find.byType(DashboardTab)) as dynamic;
    await state.debugSmartRefresh(hard: true);
    await tester.pumpAndSettle();

    expect(find.textContaining('2,600'), findsWidgets);
    expect(find.textContaining('Refresh failed'), findsNothing);
  });
}
