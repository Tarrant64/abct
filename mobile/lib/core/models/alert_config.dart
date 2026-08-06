enum AlertType { portfolioPercent, assetPricePercent, assetPriceThreshold }

class PortfolioAlertConfig {
  PortfolioAlertConfig({Set<double>? enabledThresholds})
      : enabledThresholds = enabledThresholds ?? {};

  final Set<double> enabledThresholds;

  static const availableThresholds = [1.0, 3.0, 5.0, 10.0];

  Map<String, dynamic> toJson() => {
        'enabledThresholds': enabledThresholds.toList(),
      };

  factory PortfolioAlertConfig.fromJson(Map<String, dynamic> json) {
    final raw = json['enabledThresholds'];
    final thresholds = <double>{};
    if (raw is List) {
      for (final v in raw) {
        if (v is num) thresholds.add(v.toDouble());
      }
    }
    return PortfolioAlertConfig(enabledThresholds: thresholds);
  }
}

class AssetPriceAlert {
  AssetPriceAlert({
    required this.id,
    required this.symbol,
    required this.name,
    required this.type,
    required this.threshold,
    required this.above,
    required this.createdAt,
  });

  final String id;
  final String symbol;
  final String name;
  final AlertType type;
  final double threshold;
  final bool above;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => {
        'id': id,
        'symbol': symbol,
        'name': name,
        'type': type.name,
        'threshold': threshold,
        'above': above,
        'createdAt': createdAt.toIso8601String(),
      };

  factory AssetPriceAlert.fromJson(Map<String, dynamic> json) {
    return AssetPriceAlert(
      id: json['id'] as String? ?? '',
      symbol: json['symbol'] as String? ?? '',
      name: json['name'] as String? ?? '',
      type: AlertType.values.firstWhere(
        (t) => t.name == json['type'],
        orElse: () => AlertType.assetPricePercent,
      ),
      threshold: (json['threshold'] as num?)?.toDouble() ?? 0,
      above: json['above'] as bool? ?? true,
      createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  /// Generate a simple unique ID from timestamp + symbol.
  static String generateId(String symbol) {
    final ts = DateTime.now().microsecondsSinceEpoch;
    return '${symbol.toLowerCase()}_${ts.toRadixString(36)}';
  }
}

class AlertSnapshot {
  AlertSnapshot({
    required this.portfolioValueUsd,
    required this.assetPrices,
    required this.timestamp,
    Map<String, DateTime>? lastFired,
  }) : lastFired = lastFired ?? {};

  final double portfolioValueUsd;
  final Map<String, double> assetPrices;
  final DateTime timestamp;
  final Map<String, DateTime> lastFired;

  Map<String, dynamic> toJson() => {
        'portfolioValueUsd': portfolioValueUsd,
        'assetPrices': assetPrices,
        'timestamp': timestamp.toIso8601String(),
        'lastFired': lastFired.map(
          (k, v) => MapEntry(k, v.toIso8601String()),
        ),
      };

  factory AlertSnapshot.fromJson(Map<String, dynamic> json) {
    final prices = <String, double>{};
    final rawPrices = json['assetPrices'];
    if (rawPrices is Map) {
      for (final entry in rawPrices.entries) {
        final key = entry.key.toString();
        final val = entry.value;
        if (val is num) prices[key] = val.toDouble();
      }
    }

    final fired = <String, DateTime>{};
    final rawFired = json['lastFired'];
    if (rawFired is Map) {
      for (final entry in rawFired.entries) {
        final key = entry.key.toString();
        final dt = DateTime.tryParse(entry.value?.toString() ?? '');
        if (dt != null) fired[key] = dt;
      }
    }

    return AlertSnapshot(
      portfolioValueUsd:
          (json['portfolioValueUsd'] as num?)?.toDouble() ?? 0,
      assetPrices: prices,
      timestamp:
          DateTime.tryParse(json['timestamp'] as String? ?? '') ??
              DateTime.now(),
      lastFired: fired,
    );
  }

  AlertSnapshot copyWithFired(Map<String, DateTime> newFired) {
    return AlertSnapshot(
      portfolioValueUsd: portfolioValueUsd,
      assetPrices: assetPrices,
      timestamp: timestamp,
      lastFired: {...lastFired, ...newFired},
    );
  }
}

class FiredAlert {
  FiredAlert({
    required this.title,
    required this.body,
    required this.notificationId,
    this.isHighPriority = false,
  });

  final String title;
  final String body;
  final int notificationId;
  final bool isHighPriority;
}
