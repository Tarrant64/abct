import 'dart:convert';
import 'dart:io';

import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/models/portfolio_history.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/core/storage/auth_session_store.dart';
import 'package:abct_mobile/core/storage/auth_token_store.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Slim chart contract (dashboard D4): the client requests ?slim=true on
/// portfolio-history and parses the reduced per-point shape
/// {"timestamp","total_value_usd"} without losing anything the app uses.
class _StubTokenStore extends AuthTokenStore {
  @override
  Future<String?> readToken(ConnectionProfile profile) async => null;
}

class _StubSessionStore extends AuthSessionStore {
  @override
  Future<String?> readSessionCookie(ConnectionProfile profile) async => null;
}

/// Restores real HttpClients (TestWidgetsFlutterBinding stubs them to 400)
/// for the loopback-server test.
class _RealHttpOverrides extends HttpOverrides {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // The real ApiClient wires in CacheInterceptor → CacheStore.instance →
  // path_provider; point it at a temp directory.
  final cacheDir = Directory.systemTemp.createTempSync('api_history_test_');
  const pathChannel = MethodChannel('plugins.flutter.io/path_provider');

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(pathChannel, (call) async => cacheDir.path);
  });

  tearDownAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(pathChannel, null);
    if (cacheDir.existsSync()) cacheDir.deleteSync(recursive: true);
  });

  const slimPoints = [
    {'timestamp': '2026-07-10T00:00:00Z', 'total_value_usd': 100.0},
    {'timestamp': '2026-07-11T00:00:00Z', 'total_value_usd': 110.0},
    {'timestamp': '2026-07-12T00:00:00Z', 'total_value_usd': 105.0},
  ];

  test('getPortfolioHistory requests slim=true and parses the slim payload',
      () async {
    Map<String, String>? receivedQuery;
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      receivedQuery = request.uri.queryParameters;
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'range': '7d',
        'interval': 'daily',
        'data_points': slimPoints.length,
        'chart_data': slimPoints,
        'summary': {
          'starting_value': 100.0,
          'ending_value': 105.0,
          'change_usd': 5.0,
          'change_percent': 5.0,
          'highest_value': 110.0,
          'lowest_value': 100.0,
        },
      }));
      await request.response.close();
    });

    final client = ApiClient(
      ConnectionProfile(
        name: 'test',
        baseUrl: 'http://127.0.0.1:${server.port}',
      ),
      tokenStore: _StubTokenStore(),
      sessionStore: _StubSessionStore(),
    );

    final history = await HttpOverrides.runWithHttpOverrides(
      () => client.getPortfolioHistory(range: '7d'),
      _RealHttpOverrides(),
    );

    expect(receivedQuery?['slim'], 'true');
    expect(receivedQuery?['range'], '7d');

    expect(history.range, '7d');
    expect(history.dataPoints, 3);
    expect(history.chartData, hasLength(3));
    expect(history.chartData.last.totalValueUsd, 105.0);
    expect(history.summary.changeUsd, 5.0);
  });

  test('slim points parse with absent breakdown fields defaulting safely',
      () {
    final history = PortfolioHistory.fromJson({
      'range': 'all',
      'interval': 'daily',
      'data_points': slimPoints.length,
      'chart_data': slimPoints,
      'summary': const <String, dynamic>{},
    });

    expect(history.chartData, hasLength(3));
    for (final point in history.chartData) {
      expect(point.totalValueUsd, greaterThan(0));
      expect(point.timestamp.year, 2026);
      // Fields the slim contract drops — never consumed by the app
      // (chart and watch sync read only timestamp/total_value_usd).
      expect(point.onChainValueUsd, 0);
      expect(point.offChainValueUsd, 0);
      expect(point.nativeValues, isEmpty);
    }
  });

  test('slim payload keeps the watch-sync inputs intact', () {
    final history = PortfolioHistory.fromJson({
      'range': '7d',
      'chart_data': slimPoints,
      'summary': {'change_usd': 5.0, 'change_percent': 5.0},
    });

    // WatchSyncBridge reads exactly these: per-point totalValueUsd plus the
    // top-level summary change values. All survive the slim contract.
    final values =
        history.chartData.map((p) => p.totalValueUsd).toList();
    expect(values, [100.0, 110.0, 105.0]);
    expect(history.summary.changeUsd, 5.0);
    expect(history.summary.changePercent, 5.0);
  });
}
