import 'dart:convert';

import 'package:abct_mobile/core/models/alert_config.dart';
import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/models/portfolio_summary.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/core/services/background_sync.dart';
import 'package:abct_mobile/core/storage/alert_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// ApiClient whose summary fetch is canned; records the flags the task
/// passes so tests can pin the network-first / no-forced-refresh contract.
class _RecordingApiClient extends ApiClient {
  _RecordingApiClient(super.profile, this.summary);

  final PortfolioSummary summary;
  int fetchCount = 0;
  bool? lastRefresh;
  bool? lastRevalidate;

  @override
  Future<PortfolioSummary> getPortfolioSummary({
    bool refresh = false,
    bool revalidate = false,
    bool includeSparklines = true,
  }) async {
    fetchCount++;
    lastRefresh = refresh;
    lastRevalidate = revalidate;
    return summary;
  }
}

PortfolioSummary _summary({double totalValueUsd = 50000}) =>
    PortfolioSummary.fromJson({
      'total_value_usd': totalValueUsd,
      'breakdown': {
        'self_custody': {},
        'exchanges': {},
        'nfts': {},
        'staking': {},
      },
      'blockchains': [
        {
          'name': 'bitcoin',
          'symbol': 'BTC',
          'value_usd': totalValueUsd,
          'native_amount': 1,
          'native_price_usd': totalValueUsd,
          'wallet_count': 1,
          'percentage': 100,
        },
      ],
    });

Map<String, Object> _profilePrefs({bool notificationsEnabled = false}) => {
      'alert_active_profile_v1': jsonEncode(
        ConnectionProfile(name: 'test', baseUrl: 'https://example.com')
            .toJson(),
      ),
      'settings_notifications_enabled_v1': notificationsEnabled,
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late List<String> shown;
  late int notificationInits;

  Future<void> fakeInit() async => notificationInits++;
  Future<void> fakeShow({
    required String title,
    required String body,
    int id = 0,
  }) async =>
      shown.add('normal:$title');
  Future<void> fakeShowPriceAlert({
    required String title,
    required String body,
    int id = 0,
  }) async =>
      shown.add('priority:$title');

  /// Runs the task with all side-effectful dependencies faked.
  Future<_RecordingApiClient> runTask({
    String taskName = kPortfolioSyncTask,
    double totalValueUsd = 50000,
  }) async {
    final client = _RecordingApiClient(
      ConnectionProfile(name: 'test', baseUrl: 'https://example.com'),
      _summary(totalValueUsd: totalValueUsd),
    );
    final result = await runPortfolioSyncTask(
      taskName,
      apiClientFactory: (_) => client,
      initializeNotifications: fakeInit,
      showNotification: fakeShow,
      showPriceAlert: fakeShowPriceAlert,
    );
    // The task must never report failure to the OS scheduler.
    expect(result, isTrue);
    return client;
  }

  setUp(() {
    shown = [];
    notificationInits = 0;
  });

  test('unknown task name is a no-op', () async {
    SharedPreferences.setMockInitialValues(_profilePrefs());

    final client = await runTask(taskName: 'some.other.task');

    expect(client.fetchCount, 0);
    expect(await AlertRepository().loadSnapshot(), isNull);
  });

  test('missing active profile skips the fetch', () async {
    SharedPreferences.setMockInitialValues({});

    final client = await runTask();

    expect(client.fetchCount, 0);
  });

  test('fetch is network-first and never a forced server refresh', () async {
    SharedPreferences.setMockInitialValues(_profilePrefs());

    final client = await runTask();

    expect(client.fetchCount, 1);
    expect(client.lastRevalidate, isTrue);
    expect(client.lastRefresh, isFalse);
  });

  test('notifications disabled: still fetches and saves the snapshot, '
      'but never touches the notification stack', () async {
    SharedPreferences.setMockInitialValues(
        _profilePrefs(notificationsEnabled: false));

    final client = await runTask(totalValueUsd: 50000);

    expect(client.fetchCount, 1);
    expect(notificationInits, 0);
    expect(shown, isEmpty);

    final snapshot = await AlertRepository().loadSnapshot();
    expect(snapshot, isNotNull);
    expect(snapshot!.portfolioValueUsd, 50000);
    expect(snapshot.assetPrices['btc'], 50000);
  });

  test('notifications enabled: fires portfolio alert past its threshold',
      () async {
    SharedPreferences.setMockInitialValues(
        _profilePrefs(notificationsEnabled: true));
    final repo = AlertRepository();
    await repo.savePortfolioAlerts(
        PortfolioAlertConfig(enabledThresholds: {10}));
    await repo.saveSnapshot(AlertSnapshot(
      portfolioValueUsd: 40000,
      assetPrices: const {},
      timestamp: DateTime.now(),
      lastFired: const {},
    ));

    // 40000 -> 50000 is +25%, past the 10% threshold.
    await runTask(totalValueUsd: 50000);

    expect(notificationInits, 1);
    expect(shown, hasLength(1));
    expect(shown.single, startsWith('normal:Portfolio up 25.0%'));

    final snapshot = await repo.loadSnapshot();
    expect(snapshot!.portfolioValueUsd, 50000);
    expect(snapshot.lastFired, isNotEmpty);
  });

  test('notifications enabled but below threshold: no alert, snapshot moves',
      () async {
    SharedPreferences.setMockInitialValues(
        _profilePrefs(notificationsEnabled: true));
    final repo = AlertRepository();
    await repo.savePortfolioAlerts(
        PortfolioAlertConfig(enabledThresholds: {50}));
    await repo.saveSnapshot(AlertSnapshot(
      portfolioValueUsd: 49000,
      assetPrices: const {},
      timestamp: DateTime.now(),
      lastFired: const {},
    ));

    await runTask(totalValueUsd: 50000);

    expect(shown, isEmpty);
    expect((await repo.loadSnapshot())!.portfolioValueUsd, 50000);
  });

  test('fetch failure is swallowed and reported as success to the scheduler',
      () async {
    SharedPreferences.setMockInitialValues(_profilePrefs());

    final result = await runPortfolioSyncTask(
      kPortfolioSyncTask,
      apiClientFactory: (_) => throw StateError('boom'),
      initializeNotifications: fakeInit,
      showNotification: fakeShow,
      showPriceAlert: fakeShowPriceAlert,
    );

    expect(result, isTrue);
    expect(await AlertRepository().loadSnapshot(), isNull);
  });
}
