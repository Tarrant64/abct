import 'json_utils.dart';

/// Response from the unified /portfolio/all-holdings endpoint.
class AllHoldingsResponse {
  AllHoldingsResponse({
    required this.holdings,
    required this.totalValueUsd,
    required this.count,
  });

  final List<TokenHolding> holdings;
  final double totalValueUsd;
  final int count;

  factory AllHoldingsResponse.fromJson(Map<String, dynamic> json) {
    return AllHoldingsResponse(
      holdings: JsonUtils.listOfMaps(json['holdings'])
          .map(TokenHolding.fromUnifiedJson)
          .toList(),
      totalValueUsd: JsonUtils.doubleValue(json, 'total_value_usd'),
      count: JsonUtils.intValue(json, 'count'),
    );
  }
}

class TokenHolding {
  TokenHolding({
    required this.ticker,
    required this.assetName,
    required this.totalQuantity,
    this.priceUsd,
    this.valueUsd,
    this.logoUrl,
    required this.walletCount,
    this.priceChange24h = 0,
    this.source = '',
  });

  final String ticker;
  final String assetName;
  final double totalQuantity;
  final double? priceUsd;
  final double? valueUsd;
  final String? logoUrl;
  final int walletCount;
  final double priceChange24h;
  final String source;

  String get displayName =>
      ticker.isNotEmpty ? ticker.toUpperCase() : assetName;

  /// Parse from the unified /portfolio/all-holdings response.
  factory TokenHolding.fromUnifiedJson(Map<String, dynamic> json) {
    return TokenHolding(
      ticker: JsonUtils.string(json, 'symbol'),
      assetName: JsonUtils.string(json, 'name'),
      totalQuantity: JsonUtils.doubleValue(json, 'amount'),
      priceUsd: json['price_usd'] != null
          ? JsonUtils.doubleValue(json, 'price_usd')
          : null,
      valueUsd: json['value_usd'] != null
          ? JsonUtils.doubleValue(json, 'value_usd')
          : null,
      logoUrl: JsonUtils.optionalString(json, 'logo_url'),
      walletCount: JsonUtils.intValue(json, 'wallet_count'),
      priceChange24h: JsonUtils.doubleValue(json, 'price_change_24h'),
      source: JsonUtils.string(json, 'source'),
    );
  }
}
