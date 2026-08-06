import 'json_utils.dart';

class PortfolioSummary {
  PortfolioSummary({
    required this.totalValueUsd,
    required this.totalNative,
    required this.breakdown,
    required this.blockchains,
    required this.topHoldings,
    this.lastUpdated,
    required this.fromCache,
  });

  final double totalValueUsd;
  final Map<String, double> totalNative;
  final PortfolioBreakdown breakdown;
  final List<BlockchainHolding> blockchains;
  final List<BlockchainHolding> topHoldings;
  final DateTime? lastUpdated;
  final bool fromCache;

  factory PortfolioSummary.fromJson(Map<String, dynamic> json) {
    final chains = JsonUtils.listOfMaps(json['blockchains'])
        .map(BlockchainHolding.fromJson)
        .toList()
      ..sort((a, b) => b.valueUsd.compareTo(a.valueUsd));

    final holdings = JsonUtils.listOfMaps(json['top_holdings'])
        .map(BlockchainHolding.fromJson)
        .toList()
      ..sort((a, b) => b.valueUsd.compareTo(a.valueUsd));

    return PortfolioSummary(
      totalValueUsd: JsonUtils.doubleValue(json, 'total_value_usd'),
      totalNative: JsonUtils.stringToDoubleMap(json['total_native']),
      breakdown: PortfolioBreakdown.fromJson(JsonUtils.map(json['breakdown'])),
      blockchains: chains,
      topHoldings: holdings,
      lastUpdated: JsonUtils.dateTime(json, 'last_updated'),
      fromCache: JsonUtils.boolValue(json, 'from_cache'),
    );
  }
}

class PortfolioBreakdown {
  PortfolioBreakdown({
    required this.selfCustody,
    required this.exchanges,
    required this.nfts,
    required this.staking,
    required this.defi,
    required this.trackedTokens,
    required this.customTokens,
  });

  final BreakdownItem selfCustody;
  final BreakdownItem exchanges;
  final BreakdownItem nfts;
  final BreakdownItem staking;
  final BreakdownItem defi;
  final BreakdownItem trackedTokens;
  final BreakdownItem customTokens;

  factory PortfolioBreakdown.fromJson(Map<String, dynamic> json) {
    return PortfolioBreakdown(
      selfCustody: BreakdownItem.fromJson(JsonUtils.map(json['self_custody'])),
      exchanges: BreakdownItem.fromJson(JsonUtils.map(json['exchanges'])),
      nfts: BreakdownItem.fromJson(JsonUtils.map(json['nfts'])),
      staking: BreakdownItem.fromJson(JsonUtils.map(json['staking'])),
      defi: BreakdownItem.fromJson(JsonUtils.map(json['defi'])),
      trackedTokens: BreakdownItem.fromJson(JsonUtils.map(json['tracked_tokens'])),
      customTokens: BreakdownItem.fromJson(JsonUtils.map(json['custom_tokens'])),
    );
  }
}

class BreakdownItem {
  BreakdownItem({
    required this.valueUsd,
    required this.percentage,
  });

  final double valueUsd;
  final double percentage;

  factory BreakdownItem.fromJson(Map<String, dynamic> json) {
    return BreakdownItem(
      valueUsd: JsonUtils.doubleValue(json, 'value_usd'),
      percentage: JsonUtils.doubleValue(json, 'percentage'),
    );
  }
}

class BlockchainHolding {
  BlockchainHolding({
    required this.name,
    required this.symbol,
    required this.valueUsd,
    required this.nativeAmount,
    required this.nativePriceUsd,
    required this.walletCount,
    required this.percentage,
    this.priceChange24h = 0,
    this.imageUrl = '',
    this.sparkline7d = const [],
    this.sparkline24h = const [],
    this.watchImageUrl = '',
  });

  final String name;
  final String symbol;
  final double valueUsd;
  final double nativeAmount;
  final double nativePriceUsd;
  final int walletCount;
  final double percentage;
  final double priceChange24h;
  final String imageUrl;
  final List<double> sparkline7d;
  final List<double> sparkline24h;
  final String watchImageUrl;

  factory BlockchainHolding.fromJson(Map<String, dynamic> json) {
    return BlockchainHolding(
      name: JsonUtils.string(json, 'name', fallback: 'unknown'),
      symbol: JsonUtils.string(json, 'symbol'),
      valueUsd: JsonUtils.doubleValue(json, 'value_usd'),
      nativeAmount: JsonUtils.doubleValue(json, 'native_amount'),
      nativePriceUsd: JsonUtils.doubleValue(json, 'native_price_usd'),
      walletCount: JsonUtils.intValue(json, 'wallet_count'),
      percentage: JsonUtils.doubleValue(json, 'percentage'),
      priceChange24h: JsonUtils.doubleValue(json, 'price_change_24h'),
      imageUrl: JsonUtils.string(json, 'image_url'),
      sparkline7d: JsonUtils.doubleList(json, 'sparkline_7d'),
      sparkline24h: JsonUtils.doubleList(json, 'sparkline_24h'),
      watchImageUrl: JsonUtils.string(json, 'watch_image_url'),
    );
  }
}
