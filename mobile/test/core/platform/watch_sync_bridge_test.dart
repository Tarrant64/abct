import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:abct_mobile/core/models/market_asset.dart';
import 'package:abct_mobile/core/models/portfolio_history.dart';
import 'package:abct_mobile/core/models/portfolio_summary.dart';
import 'package:abct_mobile/core/platform/watch_sync_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('abct/watch_sync');
  final capturedCalls = <MethodCall>[];

  setUp(() {
    capturedCalls.clear();
    WatchSyncBridge.debugResetDebounce();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      capturedCalls.add(call);
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  PortfolioSummary summary({double totalValueUsd = 14000.0}) {
    final breakdownItem = BreakdownItem(valueUsd: 0, percentage: 0);
    return PortfolioSummary(
      totalValueUsd: totalValueUsd,
      totalNative: const {},
      breakdown: PortfolioBreakdown(
        selfCustody: breakdownItem,
        exchanges: breakdownItem,
        nfts: breakdownItem,
        staking: breakdownItem,
        defi: breakdownItem,
        trackedTokens: breakdownItem,
        customTokens: breakdownItem,
      ),
      blockchains: const [],
      topHoldings: [
        BlockchainHolding(
          name: 'Cardano',
          symbol: 'ada',
          valueUsd: 9000,
          nativeAmount: 12000,
          nativePriceUsd: 0.75,
          walletCount: 1,
          percentage: 64.3,
          priceChange24h: 2.1,
          sparkline7d: const [0.7, 0.72, 0.75],
        ),
      ],
      fromCache: false,
    );
  }

  PortfolioHistory history({List<double> values = const []}) {
    return PortfolioHistory(
      range: '7d',
      interval: 'daily',
      dataPoints: values.length,
      chartData: [
        for (final (i, value) in values.indexed)
          PortfolioHistoryPoint(
            timestamp: DateTime.utc(2026, 7, 1 + i),
            totalValueUsd: value,
            onChainValueUsd: value,
            offChainValueUsd: 0,
            nativeValues: const {},
          ),
      ],
      summary: PortfolioHistorySummary(
        startingValue: values.isEmpty ? 0 : values.first,
        endingValue: values.isEmpty ? 0 : values.last,
        changeUsd: 182.55,
        changePercent: 1.21,
        highestValue: 0,
        lowestValue: 0,
      ),
    );
  }

  test('totalValue comes from the summary, not the history tail', () async {
    await WatchSyncBridge.pushPortfolioSnapshot(
      summary: summary(totalValueUsd: 14000.0),
      history7d: history(
        values: const [12000, 12200, 12400, 12500, 12600, 12700, 12800],
      ),
    );

    expect(capturedCalls, hasLength(1));
    expect(capturedCalls.single.method, 'updateSnapshot');
    final payload = Map<String, dynamic>.from(
      capturedCalls.single.arguments as Map,
    );
    // The wrist must match the phone dashboard (summary total), even when
    // the cached history series lags behind ($12.8K tail vs $14K summary).
    expect(payload['totalValue'], 14000.0);
    expect(payload['historyPoints'], hasLength(7));
    expect((payload['historyPoints'] as List).last, 12800);
  });

  test('falls back to the history tail when the summary total is zero',
      () async {
    await WatchSyncBridge.pushPortfolioSnapshot(
      summary: summary(totalValueUsd: 0),
      history7d: history(
        values: const [12000, 12200, 12400, 12500, 12600, 12700, 12800],
      ),
    );

    final payload = Map<String, dynamic>.from(
      capturedCalls.single.arguments as Map,
    );
    expect(payload['totalValue'], 12800);
  });

  test('skips the push entirely when history is empty', () async {
    await WatchSyncBridge.pushPortfolioSnapshot(
      summary: summary(),
      history7d: history(values: const []),
    );

    expect(capturedCalls, isEmpty);
  });

  test('debounces a second push inside the 60s window', () async {
    final h = history(
      values: const [12000, 12200, 12400, 12500, 12600, 12700, 12800],
    );
    await WatchSyncBridge.pushPortfolioSnapshot(summary: summary(), history7d: h);
    await WatchSyncBridge.pushPortfolioSnapshot(summary: summary(), history7d: h);

    expect(capturedCalls, hasLength(1));
  });

  List<MarketAsset> topAssets(int count) => [
        for (var i = 0; i < count; i++)
          MarketAsset(
            symbol: 'TK$i',
            name: 'Token Number $i',
            priceUsd: 1000.0 + i,
            change24h: i.isEven ? 1.5 : -2.25,
          ),
      ];

  test('marketAssets ride the payload with lean keys only', () async {
    await WatchSyncBridge.pushPortfolioSnapshot(
      summary: summary(),
      history7d: history(
        values: const [12000, 12200, 12400, 12500, 12600, 12700, 12800],
      ),
      marketAssets: topAssets(20),
    );

    final payload = Map<String, dynamic>.from(
      capturedCalls.single.arguments as Map,
    );
    final market = (payload['marketAssets'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    expect(market, hasLength(20));
    // Lean contract: these entries ride every WatchConnectivity payload.
    expect(
      market.first.keys.toSet(),
      {'symbol', 'name', 'nativePriceUsd', 'priceChange24h'},
    );
    expect(market.first['symbol'], 'TK0');
    expect(market.first['nativePriceUsd'], 1000.0);
  });

  test('payload omitting market data still carries an empty list', () async {
    await WatchSyncBridge.pushPortfolioSnapshot(
      summary: summary(),
      history7d: history(
        values: const [12000, 12200, 12400, 12500, 12600, 12700, 12800],
      ),
    );

    final payload = Map<String, dynamic>.from(
      capturedCalls.single.arguments as Map,
    );
    expect(payload['marketAssets'], isEmpty);
  });

  test('worst-case payload stays far below the ~65KB WC transfer limit',
      () async {
    // 20 market assets + dense holdings; JSON length is a good proxy for
    // the property-list encoding WatchConnectivity uses.
    final denseSummary = PortfolioSummary(
      totalValueUsd: 14000.0,
      totalNative: const {},
      breakdown: summary().breakdown,
      blockchains: const [],
      topHoldings: [
        for (var i = 0; i < 10; i++)
          BlockchainHolding(
            name: 'Holding Number $i',
            symbol: 'HOLD$i',
            valueUsd: 1000.0 + i,
            nativeAmount: 42.0,
            nativePriceUsd: 97210.55,
            walletCount: 2,
            percentage: 10.0,
            priceChange24h: 2.15,
            imageUrl: 'https://example.invalid/assets/token-$i-logo.png',
            sparkline7d: [for (var p = 0; p < 168; p++) 90000.0 + p],
            sparkline24h: [for (var p = 0; p < 96; p++) 90000.0 + p],
          ),
      ],
      fromCache: false,
    );

    await WatchSyncBridge.pushPortfolioSnapshot(
      summary: denseSummary,
      history7d: history(
        values: const [12000, 12200, 12400, 12500, 12600, 12700, 12800],
      ),
      marketAssets: topAssets(20),
    );

    final payload = capturedCalls.single.arguments as Map;
    final bytes = utf8.encode(jsonEncode(payload)).length;
    // WCSession rejects payloads at 65,536 bytes; require ≥25% headroom.
    expect(bytes, lessThan(49152),
        reason: 'payload was $bytes bytes — too close to the WC limit');
  });
}
