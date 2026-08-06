import 'json_utils.dart';

class PortfolioHistory {
  PortfolioHistory({
    required this.range,
    required this.interval,
    required this.dataPoints,
    required this.chartData,
    required this.summary,
    this.error,
    this.lastUpdated,
  });

  final String range;
  final String interval;
  final int dataPoints;
  final List<PortfolioHistoryPoint> chartData;
  final PortfolioHistorySummary summary;
  final String? error;
  final DateTime? lastUpdated;

  factory PortfolioHistory.fromJson(Map<String, dynamic> json) {
    final payload = _historyPayload(json);
    final points = _readPoints(payload)
        .map(PortfolioHistoryPoint.fromJson)
        .toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));

    return PortfolioHistory(
      range: JsonUtils.string(payload, 'range', fallback: '7d'),
      interval: JsonUtils.string(payload, 'interval', fallback: 'daily'),
      dataPoints:
          JsonUtils.intValue(payload, 'data_points', fallback: points.length),
      chartData: points,
      summary:
          PortfolioHistorySummary.fromJson(JsonUtils.map(payload['summary'])),
      error: JsonUtils.optionalString(payload, 'error') ??
          JsonUtils.optionalString(json, 'error'),
      lastUpdated: _readLastUpdated(payload),
    );
  }

  static Map<String, dynamic> _historyPayload(Map<String, dynamic> raw) {
    for (final key in const ['data', 'result', 'history']) {
      final nested = JsonUtils.map(raw[key]);
      if (nested.isNotEmpty) {
        return nested;
      }
    }
    return raw;
  }

  static List<Map<String, dynamic>> _readPoints(Map<String, dynamic> json) {
    for (final key in const ['chart_data', 'points', 'history_data']) {
      final points = JsonUtils.listOfMaps(json[key]);
      if (points.isNotEmpty) {
        return points;
      }
    }
    return const [];
  }

  static DateTime? _readLastUpdated(Map<String, dynamic> json) {
    final direct = JsonUtils.dateTime(json, 'last_updated');
    if (direct != null) return direct;
    return JsonUtils.dateTime(json, 'updated_at');
  }
}

class PortfolioHistoryPoint {
  PortfolioHistoryPoint({
    required this.timestamp,
    required this.totalValueUsd,
    required this.onChainValueUsd,
    required this.offChainValueUsd,
    required this.nativeValues,
  });

  final DateTime timestamp;
  final double totalValueUsd;
  final double onChainValueUsd;
  final double offChainValueUsd;
  final Map<String, double> nativeValues;

  factory PortfolioHistoryPoint.fromJson(Map<String, dynamic> json) {
    final parsedTimestamp = _parseTimestamp(json['timestamp']);

    return PortfolioHistoryPoint(
      timestamp: parsedTimestamp ?? DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      totalValueUsd: _readTotalValue(json),
      onChainValueUsd: JsonUtils.doubleValue(json, 'on_chain_value_usd'),
      offChainValueUsd: JsonUtils.doubleValue(json, 'off_chain_value_usd'),
      nativeValues: _readBreakdown(json),
    );
  }

  static Map<String, double> _readBreakdown(Map<String, dynamic> json) {
    final breakdown = JsonUtils.stringToDoubleMap(json['breakdown']);
    if (breakdown.isNotEmpty) {
      return breakdown;
    }
    return JsonUtils.stringToDoubleMap(json['native_values']);
  }

  static double _readTotalValue(Map<String, dynamic> json) {
    for (final key in const [
      'total_value_usd',
      'total_usd_value',
      'value_usd',
      'portfolio_value_usd',
      'total_value',
    ]) {
      if (json.containsKey(key)) {
        return JsonUtils.doubleValue(json, key);
      }
    }
    return 0;
  }

  static DateTime? _parseTimestamp(dynamic raw) {
    if (raw is String && raw.trim().isNotEmpty) {
      return DateTime.tryParse(raw)?.toUtc();
    }
    if (raw is int) {
      final isMillis = raw > 1000000000000;
      final value = isMillis ? raw : raw * 1000;
      return DateTime.fromMillisecondsSinceEpoch(value, isUtc: true);
    }
    if (raw is num) {
      final asInt = raw.toInt();
      final isMillis = asInt > 1000000000000;
      final value = isMillis ? asInt : asInt * 1000;
      return DateTime.fromMillisecondsSinceEpoch(value, isUtc: true);
    }
    return null;
  }
}

class PortfolioHistorySummary {
  PortfolioHistorySummary({
    required this.startingValue,
    required this.endingValue,
    required this.changeUsd,
    required this.changePercent,
    required this.highestValue,
    required this.lowestValue,
  });

  final double startingValue;
  final double endingValue;
  final double changeUsd;
  final double changePercent;
  final double highestValue;
  final double lowestValue;

  factory PortfolioHistorySummary.fromJson(Map<String, dynamic> json) {
    return PortfolioHistorySummary(
      startingValue: JsonUtils.doubleValue(json, 'starting_value'),
      endingValue: JsonUtils.doubleValue(json, 'ending_value'),
      changeUsd: JsonUtils.doubleValue(json, 'change_usd'),
      changePercent: JsonUtils.doubleValue(json, 'change_percent'),
      highestValue: JsonUtils.doubleValue(json, 'highest_value'),
      lowestValue: JsonUtils.doubleValue(json, 'lowest_value'),
    );
  }
}
