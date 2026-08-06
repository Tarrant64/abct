import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../models/market_asset.dart';
import '../models/portfolio_history.dart';
import '../models/portfolio_summary.dart';

class WatchSyncBridge {
  WatchSyncBridge._();

  static const MethodChannel _channel = MethodChannel('abct/watch_sync');

  /// Minimum interval between watch syncs to prevent battery drain.
  static const _minSyncInterval = Duration(seconds: 60);
  static DateTime? _lastSyncTime;

  @visibleForTesting
  static void debugResetDebounce() {
    _lastSyncTime = null;
  }

  static Future<void> pushPortfolioSnapshot({
    required PortfolioSummary summary,
    required PortfolioHistory history7d,
    List<MarketAsset> marketAssets = const [],
  }) async {
    // Debounce: skip if synced less than 60 seconds ago
    final now = DateTime.now();
    if (_lastSyncTime != null &&
        now.difference(_lastSyncTime!) < _minSyncInterval) {
      return;
    }

    final historyValues = _normalizeHistory(history7d);
    if (historyValues.isEmpty) return;

    // The watch must show the same total the phone's dashboard renders
    // (summary.totalValueUsd). The history series can lag behind it (cached
    // chart data), so its last point is only a fallback, never the primary.
    final totalValue =
        summary.totalValueUsd > 0 ? summary.totalValueUsd : historyValues.last;
    final sevenDayChange = history7d.summary.changeUsd;
    final percentChange = history7d.summary.changePercent;

    final source = summary.topHoldings.isNotEmpty
        ? summary.topHoldings
        : summary.blockchains;
    final assets = source.map((h) => <String, dynamic>{
      'symbol': h.symbol.toUpperCase(),
      'name': h.name,
      'valueUsd': h.valueUsd,
      'nativePriceUsd': h.nativePriceUsd,
      'priceChange24h': h.priceChange24h,
      'percentage': h.percentage,
      'imageUrl': h.watchImageUrl.isNotEmpty ? h.watchImageUrl : h.imageUrl,
      'sparkline7d': h.sparkline7d,
      'sparkline24h': h.sparkline24h,
    }).toList();

    // Lean by design: market entries ride every WatchConnectivity payload,
    // so no sparklines or holdings context for tokens the user doesn't own.
    final market = marketAssets.map((m) => <String, dynamic>{
      'symbol': m.symbol,
      'name': m.name,
      'nativePriceUsd': m.priceUsd,
      'priceChange24h': m.change24h,
    }).toList();

    final payload = <String, dynamic>{
      'totalValue': totalValue,
      'sevenDayChange': sevenDayChange,
      'percentChange': percentChange,
      'historyPoints': historyValues,
      'assets': assets,
      'marketAssets': market,
    };

    try {
      await _channel.invokeMethod<void>('updateSnapshot', payload);
      _lastSyncTime = DateTime.now();
    } on MissingPluginException {
      // Expected on non-iOS platforms.
    } on PlatformException catch (error, stack) {
      developer.log(
        'Watch sync platform error: ${error.code} ${error.message}',
        name: 'WatchSyncBridge',
        error: error,
        stackTrace: stack,
      );
    } catch (error, stack) {
      developer.log(
        'Watch sync failed',
        name: 'WatchSyncBridge',
        error: error,
        stackTrace: stack,
      );
    }
  }

  static List<double> _normalizeHistory(PortfolioHistory history) {
    final values = history.chartData
        .map((point) => point.totalValueUsd)
        .where((value) => value.isFinite)
        .toList();

    if (values.isEmpty) return const [];
    if (values.length == 7) return values;
    if (values.length < 7) {
      final padded = List<double>.filled(7 - values.length, values.first);
      return <double>[...padded, ...values];
    }

    final lastSeven = values.sublist(values.length - 7);
    return lastSeven;
  }
}
