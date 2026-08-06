import 'json_utils.dart';

/// A market-cap-ranked asset (not necessarily held) used for watch
/// complication tracking. Deliberately lean — no sparklines or holdings
/// context — because it rides the WatchConnectivity payload.
class MarketAsset {
  MarketAsset({
    required this.symbol,
    required this.name,
    required this.priceUsd,
    required this.change24h,
  });

  final String symbol;
  final String name;
  final double priceUsd;
  final double change24h;

  factory MarketAsset.fromJson(Map<String, dynamic> json) {
    return MarketAsset(
      symbol: JsonUtils.string(json, 'symbol').toUpperCase(),
      name: JsonUtils.string(json, 'name'),
      priceUsd: JsonUtils.doubleValue(json, 'price'),
      change24h: JsonUtils.doubleValue(json, 'change_24h'),
    );
  }
}
