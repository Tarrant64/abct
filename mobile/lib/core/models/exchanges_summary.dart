import 'json_utils.dart';

class ExchangesSummary {
  ExchangesSummary({
    required this.totalExchanges,
    required this.totalValueUsd,
    required this.exchanges,
    this.lastUpdated,
  });

  final int totalExchanges;
  final double totalValueUsd;
  final List<ExchangeSummaryItem> exchanges;
  final DateTime? lastUpdated;

  factory ExchangesSummary.fromJson(Map<String, dynamic> json) {
    final exchangeItems = JsonUtils.listOfMaps(json['exchanges'])
        .map(ExchangeSummaryItem.fromJson)
        .toList()
      ..sort((a, b) => b.valueUsd.compareTo(a.valueUsd));

    return ExchangesSummary(
      totalExchanges: JsonUtils.intValue(
        json,
        'total_exchanges',
        fallback: exchangeItems.length,
      ),
      totalValueUsd: JsonUtils.doubleValue(json, 'total_value_usd'),
      exchanges: exchangeItems,
      lastUpdated: JsonUtils.dateTime(json, 'last_updated'),
    );
  }
}

class ExchangeSummaryItem {
  ExchangeSummaryItem({
    required this.name,
    required this.displayName,
    required this.configured,
    required this.valueUsd,
    required this.assetCount,
    this.logoUrl,
    this.lastSync,
  });

  final String name;
  final String displayName;
  final bool configured;
  final double valueUsd;
  final int assetCount;
  final String? logoUrl;
  final DateTime? lastSync;

  factory ExchangeSummaryItem.fromJson(Map<String, dynamic> json) {
    final name = JsonUtils.string(json, 'name', fallback: 'unknown');
    final displayName = JsonUtils.string(
      json,
      'display_name',
      fallback: name,
    );

    return ExchangeSummaryItem(
      name: name,
      displayName: displayName,
      configured: JsonUtils.boolValue(json, 'configured'),
      valueUsd: JsonUtils.doubleValue(json, 'value_usd'),
      assetCount: JsonUtils.intValue(json, 'asset_count'),
      logoUrl: JsonUtils.optionalString(json, 'logo_url'),
      lastSync: JsonUtils.dateTime(json, 'last_sync'),
    );
  }
}

class ExchangeDetail {
  ExchangeDetail({
    required this.exchange,
    required this.displayName,
    required this.configured,
    required this.totalUsd,
    required this.assetCount,
    required this.assets,
    this.lastSync,
    required this.fromCache,
  });

  final String exchange;
  final String displayName;
  final bool configured;
  final double totalUsd;
  final int assetCount;
  final List<ExchangeAsset> assets;
  final DateTime? lastSync;
  final bool fromCache;

  factory ExchangeDetail.fromJson(Map<String, dynamic> json) {
    final exchange = JsonUtils.string(json, 'exchange');
    final assets = JsonUtils.listOfMaps(json['assets'])
        .map(ExchangeAsset.fromJson)
        .toList()
      ..sort((a, b) => b.usdValue.compareTo(a.usdValue));

    return ExchangeDetail(
      exchange: exchange,
      displayName: JsonUtils.string(
        json,
        'display_name',
        fallback: exchange,
      ),
      configured: JsonUtils.boolValue(
        json,
        'configured',
        fallback: true,
      ),
      totalUsd: JsonUtils.doubleValue(
        json,
        'total_usd',
        fallback: JsonUtils.doubleValue(json, 'value_usd'),
      ),
      assetCount: JsonUtils.intValue(
        json,
        'asset_count',
        fallback: assets.length,
      ),
      assets: assets,
      lastSync: JsonUtils.dateTime(json, 'last_sync'),
      fromCache: JsonUtils.boolValue(json, 'from_cache'),
    );
  }
}

class ExchangeAsset {
  ExchangeAsset({
    required this.symbol,
    required this.name,
    required this.balance,
    required this.usdValue,
    required this.usdPrice,
    required this.change24h,
    this.logoUrl,
  });

  final String symbol;
  final String name;
  final double balance;
  final double usdValue;
  final double usdPrice;
  final double change24h;
  final String? logoUrl;

  factory ExchangeAsset.fromJson(Map<String, dynamic> json) {
    return ExchangeAsset(
      symbol: JsonUtils.string(json, 'symbol'),
      name: JsonUtils.string(json, 'name'),
      balance: JsonUtils.doubleValue(json, 'balance'),
      usdValue: JsonUtils.doubleValue(
        json,
        'usd_value',
        fallback: JsonUtils.doubleValue(json, 'value_usd'),
      ),
      usdPrice: JsonUtils.doubleValue(
        json,
        'usd_price',
        fallback: JsonUtils.doubleValue(json, 'price_usd'),
      ),
      change24h: JsonUtils.doubleValue(
        json,
        'change_24h',
        fallback: JsonUtils.doubleValue(json, 'change_percent_24h'),
      ),
      logoUrl: JsonUtils.optionalString(json, 'logo_url'),
    );
  }
}
