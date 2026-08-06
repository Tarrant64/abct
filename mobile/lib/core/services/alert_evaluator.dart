import '../models/alert_config.dart';
import '../storage/alert_repository.dart';
import 'notification_service.dart';

/// Pure logic alert evaluator. No Flutter UI dependencies.
class AlertEvaluator {
  static const _cooldownMinutes = 30;

  /// Evaluate portfolio value change against configured thresholds.
  static List<FiredAlert> evaluatePortfolio({
    required double currentValue,
    required AlertSnapshot? snapshot,
    required PortfolioAlertConfig config,
  }) {
    if (snapshot == null || config.enabledThresholds.isEmpty) return [];
    if (snapshot.portfolioValueUsd <= 0 || currentValue <= 0) return [];

    final change =
        ((currentValue - snapshot.portfolioValueUsd) / snapshot.portfolioValueUsd) *
            100;
    final absChange = change.abs();
    final now = DateTime.now();
    final alerts = <FiredAlert>[];

    for (final threshold in config.enabledThresholds) {
      if (absChange >= threshold) {
        final key = 'portfolio_${threshold.toStringAsFixed(0)}';
        if (_isCoolingDown(snapshot, key, now)) continue;

        final direction = change >= 0 ? 'up' : 'down';
        final sign = change >= 0 ? '+' : '';
        alerts.add(FiredAlert(
          title: 'Portfolio $direction ${absChange.toStringAsFixed(1)}%',
          body:
              'Your portfolio moved $sign${change.toStringAsFixed(1)}% (threshold: ${threshold.toStringAsFixed(0)}%)',
          notificationId: key.hashCode & 0x7FFFFFFF,
        ));
      }
    }

    return alerts;
  }

  /// Evaluate a single asset price against configured alerts.
  static List<FiredAlert> evaluateAssetPrice({
    required String symbol,
    required double currentPrice,
    required AlertSnapshot? snapshot,
    required List<AssetPriceAlert> alerts,
  }) {
    if (alerts.isEmpty || currentPrice <= 0) return [];
    final now = DateTime.now();
    final fired = <FiredAlert>[];

    for (final alert in alerts) {
      final key = 'asset_${alert.id}';

      if (alert.type == AlertType.assetPricePercent) {
        final lastPrice =
            snapshot?.assetPrices[symbol.toLowerCase()] ?? 0;
        if (lastPrice <= 0) continue;
        final change = ((currentPrice - lastPrice) / lastPrice) * 100;
        if (change.abs() >= alert.threshold) {
          if (_isCoolingDown(snapshot, key, now)) continue;
          final direction = change >= 0 ? 'up' : 'down';
          final sign = change >= 0 ? '+' : '';
          fired.add(FiredAlert(
            title:
                '${alert.symbol.toUpperCase()} $direction ${change.abs().toStringAsFixed(1)}%',
            body:
                '${alert.name} moved $sign${change.toStringAsFixed(1)}% (threshold: ${alert.threshold.toStringAsFixed(0)}%)',
            notificationId: key.hashCode & 0x7FFFFFFF,
            isHighPriority: true,
          ));
        }
      } else if (alert.type == AlertType.assetPriceThreshold) {
        final crossed = alert.above
            ? currentPrice >= alert.threshold
            : currentPrice <= alert.threshold;
        if (crossed) {
          if (_isCoolingDown(snapshot, key, now)) continue;
          final direction = alert.above ? 'above' : 'below';
          fired.add(FiredAlert(
            title:
                '${alert.symbol.toUpperCase()} crossed \$${alert.threshold.toStringAsFixed(2)}',
            body:
                '${alert.name} is now $direction your \$${alert.threshold.toStringAsFixed(2)} target (\$${currentPrice.toStringAsFixed(2)})',
            notificationId: key.hashCode & 0x7FFFFFFF,
            isHighPriority: true,
          ));
        }
      }
    }

    return fired;
  }

  /// Convenience: evaluate portfolio and fire notifications in one call.
  static Future<void> checkAndNotifyPortfolio(
    double currentValue,
  ) async {
    final repo = AlertRepository();
    final config = await repo.loadPortfolioAlerts();
    if (config.enabledThresholds.isEmpty) return;

    final snapshot = await repo.loadSnapshot();
    final alerts = evaluatePortfolio(
      currentValue: currentValue,
      snapshot: snapshot,
      config: config,
    );

    final now = DateTime.now();
    final newFired = <String, DateTime>{};

    for (final alert in alerts) {
      await NotificationService.show(
        title: alert.title,
        body: alert.body,
        id: alert.notificationId,
      );
      newFired['portfolio_${alert.title.hashCode}'] = now;
    }

    // Update snapshot with current value + fired timestamps
    final updated = AlertSnapshot(
      portfolioValueUsd: currentValue,
      assetPrices: snapshot?.assetPrices ?? {},
      timestamp: now,
      lastFired: {...?snapshot?.lastFired, ...newFired},
    );
    await repo.saveSnapshot(updated);
  }

  /// Convenience: evaluate asset price and fire notifications.
  static Future<void> checkAndNotifyAssetPrice({
    required String symbol,
    required double currentPrice,
  }) async {
    final repo = AlertRepository();
    final assetAlerts = await repo.loadAlertsForSymbol(symbol);
    if (assetAlerts.isEmpty) return;

    final snapshot = await repo.loadSnapshot();
    final fired = evaluateAssetPrice(
      symbol: symbol,
      currentPrice: currentPrice,
      snapshot: snapshot,
      alerts: assetAlerts,
    );

    final now = DateTime.now();
    final newFired = <String, DateTime>{};

    for (final alert in fired) {
      if (alert.isHighPriority) {
        await NotificationService.showPriceAlert(
          title: alert.title,
          body: alert.body,
          id: alert.notificationId,
        );
      } else {
        await NotificationService.show(
          title: alert.title,
          body: alert.body,
          id: alert.notificationId,
        );
      }
      newFired['asset_${alert.notificationId}'] = now;
    }

    // Update asset price in snapshot
    if (snapshot != null) {
      final updatedPrices = {...snapshot.assetPrices};
      updatedPrices[symbol.toLowerCase()] = currentPrice;
      final updated = AlertSnapshot(
        portfolioValueUsd: snapshot.portfolioValueUsd,
        assetPrices: updatedPrices,
        timestamp: now,
        lastFired: {...snapshot.lastFired, ...newFired},
      );
      await repo.saveSnapshot(updated);
    }
  }

  static bool _isCoolingDown(
    AlertSnapshot? snapshot,
    String key,
    DateTime now,
  ) {
    if (snapshot == null) return false;
    final lastFired = snapshot.lastFired[key];
    if (lastFired == null) return false;
    return now.difference(lastFired).inMinutes < _cooldownMinutes;
  }
}
