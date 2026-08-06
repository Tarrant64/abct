import 'json_utils.dart';

/// Market data for a single asset from the `/portfolio/asset-detail` endpoint.
class AssetMarketData {
  AssetMarketData({
    required this.symbol,
    required this.name,
    required this.image,
    required this.description,
    required this.marketCapRank,
    required this.marketCap,
    required this.totalVolume,
    required this.high24h,
    required this.low24h,
    required this.currentPrice,
    required this.priceChange1h,
    required this.priceChange24h,
    required this.priceChange7d,
    required this.priceChange30d,
    required this.circulatingSupply,
    required this.totalSupply,
    required this.maxSupply,
    required this.ath,
    required this.athDate,
    required this.athChangePct,
    required this.atl,
    required this.atlDate,
    required this.atlChangePct,
    required this.partial,
  });

  final String symbol;
  final String name;
  final String image;
  final String description;
  final int marketCapRank;
  final double marketCap;
  final double totalVolume;
  final double high24h;
  final double low24h;
  final double currentPrice;
  final double priceChange1h;
  final double priceChange24h;
  final double priceChange7d;
  final double priceChange30d;
  final double circulatingSupply;
  final double totalSupply;
  final double maxSupply;
  final double ath;
  final String? athDate;
  final double athChangePct;
  final double atl;
  final String? atlDate;
  final double atlChangePct;
  final bool partial;

  factory AssetMarketData.fromJson(Map<String, dynamic> json) {
    return AssetMarketData(
      symbol: JsonUtils.string(json, 'symbol'),
      name: JsonUtils.string(json, 'name'),
      image: JsonUtils.string(json, 'image'),
      description: JsonUtils.string(json, 'description'),
      marketCapRank: JsonUtils.intValue(json, 'market_cap_rank'),
      marketCap: JsonUtils.doubleValue(json, 'market_cap'),
      totalVolume: JsonUtils.doubleValue(json, 'total_volume'),
      high24h: JsonUtils.doubleValue(json, 'high_24h'),
      low24h: JsonUtils.doubleValue(json, 'low_24h'),
      currentPrice: JsonUtils.doubleValue(json, 'current_price'),
      priceChange1h: JsonUtils.doubleValue(json, 'price_change_1h'),
      priceChange24h: JsonUtils.doubleValue(json, 'price_change_24h'),
      priceChange7d: JsonUtils.doubleValue(json, 'price_change_7d'),
      priceChange30d: JsonUtils.doubleValue(json, 'price_change_30d'),
      circulatingSupply: JsonUtils.doubleValue(json, 'circulating_supply'),
      totalSupply: JsonUtils.doubleValue(json, 'total_supply'),
      maxSupply: JsonUtils.doubleValue(json, 'max_supply'),
      ath: JsonUtils.doubleValue(json, 'ath'),
      athDate: JsonUtils.optionalString(json, 'ath_date'),
      athChangePct: JsonUtils.doubleValue(json, 'ath_change_pct'),
      atl: JsonUtils.doubleValue(json, 'atl'),
      atlDate: JsonUtils.optionalString(json, 'atl_date'),
      atlChangePct: JsonUtils.doubleValue(json, 'atl_change_pct'),
      partial: JsonUtils.boolValue(json, 'partial'),
    );
  }
}

/// Per-wallet/source breakdown for a single token.
class WalletBreakdownResponse {
  WalletBreakdownResponse({
    required this.symbol,
    required this.currentPriceUsd,
    required this.totalAmount,
    required this.totalValueUsd,
    required this.sources,
  });

  final String symbol;
  final double currentPriceUsd;
  final double totalAmount;
  final double totalValueUsd;
  final List<WalletBreakdownItem> sources;

  factory WalletBreakdownResponse.fromJson(Map<String, dynamic> json) {
    return WalletBreakdownResponse(
      symbol: JsonUtils.string(json, 'symbol'),
      currentPriceUsd: JsonUtils.doubleValue(json, 'current_price_usd'),
      totalAmount: JsonUtils.doubleValue(json, 'total_amount'),
      totalValueUsd: JsonUtils.doubleValue(json, 'total_value_usd'),
      sources: JsonUtils.listOfMaps(json['sources'])
          .map(WalletBreakdownItem.fromJson)
          .toList(),
    );
  }
}

/// A single source (wallet, exchange, staking, defi) holding a token.
class WalletBreakdownItem {
  WalletBreakdownItem({
    required this.sourceType,
    required this.label,
    this.address,
    this.blockchain,
    required this.amount,
    required this.valueUsd,
    required this.allocationPct,
    this.lastSynced,
  });

  final String sourceType;
  final String label;
  final String? address;
  final String? blockchain;
  final double amount;
  final double valueUsd;
  final double allocationPct;
  final String? lastSynced;

  factory WalletBreakdownItem.fromJson(Map<String, dynamic> json) {
    return WalletBreakdownItem(
      sourceType: JsonUtils.string(json, 'source_type'),
      label: JsonUtils.string(json, 'label'),
      address: JsonUtils.optionalString(json, 'address'),
      blockchain: JsonUtils.optionalString(json, 'blockchain'),
      amount: JsonUtils.doubleValue(json, 'amount'),
      valueUsd: JsonUtils.doubleValue(json, 'value_usd'),
      allocationPct: JsonUtils.doubleValue(json, 'allocation_pct'),
      lastSynced: JsonUtils.optionalString(json, 'last_synced'),
    );
  }
}
