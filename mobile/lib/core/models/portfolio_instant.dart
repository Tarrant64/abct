import 'json_utils.dart';

class PortfolioInstant {
  PortfolioInstant({
    required this.totalUsd,
    required this.breakdown,
    required this.topHoldings,
    required this.hasPositions,
  });

  final double totalUsd;
  final Map<String, double> breakdown;
  final List<InstantHolding> topHoldings;
  final bool hasPositions;

  factory PortfolioInstant.fromJson(Map<String, dynamic> json) {
    return PortfolioInstant(
      totalUsd: JsonUtils.doubleValue(json, 'total_usd'),
      breakdown: JsonUtils.stringToDoubleMap(json['breakdown']),
      topHoldings: JsonUtils.listOfMaps(json['top_holdings'])
          .map(InstantHolding.fromJson)
          .toList(),
      hasPositions: JsonUtils.boolValue(json, 'has_positions'),
    );
  }
}

class InstantHolding {
  InstantHolding({
    required this.symbol,
    required this.name,
    required this.imageUrl,
    required this.quantity,
    required this.valueUsd,
    required this.priceUsd,
    required this.priceChange24h,
    required this.allocationPct,
    required this.sources,
  });

  final String symbol;
  final String name;
  final String imageUrl;
  final double quantity;
  final double valueUsd;
  final double priceUsd;
  final double priceChange24h;
  final double allocationPct;
  final List<String> sources;

  factory InstantHolding.fromJson(Map<String, dynamic> json) {
    final rawSources = json['sources'];
    final sources = rawSources is List
        ? rawSources.map((e) => '$e').toList()
        : const <String>[];

    return InstantHolding(
      symbol: JsonUtils.string(json, 'symbol'),
      name: JsonUtils.string(json, 'name'),
      imageUrl: JsonUtils.string(json, 'image_url'),
      quantity: JsonUtils.doubleValue(json, 'quantity'),
      valueUsd: JsonUtils.doubleValue(json, 'value_usd'),
      priceUsd: JsonUtils.doubleValue(json, 'price_usd'),
      priceChange24h: JsonUtils.doubleValue(json, 'price_change_24h'),
      allocationPct: JsonUtils.doubleValue(json, 'allocation_pct'),
      sources: sources,
    );
  }
}
