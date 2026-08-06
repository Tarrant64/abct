import 'json_utils.dart';

class WalletsSummary {
  WalletsSummary({
    required this.totalWallets,
    required this.wallets,
    required this.totalValueUsd,
    this.lastUpdated,
  });

  final int totalWallets;
  final List<WalletSummaryItem> wallets;
  final double totalValueUsd;
  final DateTime? lastUpdated;

  factory WalletsSummary.fromJson(Map<String, dynamic> json) {
    final walletItems = JsonUtils.listOfMaps(json['wallets'])
        .map(WalletSummaryItem.fromJson)
        .toList();

    return WalletsSummary(
      totalWallets:
          JsonUtils.intValue(json, 'total_wallets', fallback: walletItems.length),
      wallets: walletItems,
      totalValueUsd: JsonUtils.doubleValue(json, 'total_value_usd'),
      lastUpdated: JsonUtils.dateTime(json, 'last_updated'),
    );
  }
}

class WalletSummaryItem {
  WalletSummaryItem({
    required this.id,
    required this.blockchain,
    required this.address,
    required this.label,
    required this.balance,
    required this.tokenCount,
    required this.nftCount,
    this.blockchainLogoUrl,
  });

  final int id;
  final String blockchain;
  final String address;
  final String label;
  final WalletBalance balance;
  final int tokenCount;
  final int nftCount;
  final String? blockchainLogoUrl;

  factory WalletSummaryItem.fromJson(Map<String, dynamic> json) {
    return WalletSummaryItem(
      id: JsonUtils.intValue(json, 'id'),
      blockchain: JsonUtils.string(json, 'blockchain', fallback: 'unknown'),
      address: JsonUtils.string(json, 'address'),
      label: JsonUtils.string(json, 'label'),
      balance: WalletBalance.fromJson(JsonUtils.map(json['balance'])),
      tokenCount: JsonUtils.intValue(json, 'token_count'),
      nftCount: JsonUtils.intValue(json, 'nft_count'),
      blockchainLogoUrl: JsonUtils.optionalString(json, 'blockchain_logo_url') ??
          JsonUtils.optionalString(json, 'logo_url') ??
          JsonUtils.optionalString(json, 'icon_url') ??
          JsonUtils.optionalString(json, 'chain_logo_url'),
    );
  }
}

class WalletBalance {
  WalletBalance({
    required this.native,
    required this.nativeSymbol,
    required this.usdValue,
    this.lastUpdated,
  });

  final double native;
  final String nativeSymbol;
  final double usdValue;
  final DateTime? lastUpdated;

  factory WalletBalance.fromJson(Map<String, dynamic> json) {
    return WalletBalance(
      native: JsonUtils.doubleValue(json, 'native'),
      nativeSymbol: JsonUtils.string(json, 'native_symbol'),
      usdValue: JsonUtils.doubleValue(json, 'usd_value'),
      lastUpdated: JsonUtils.dateTime(json, 'last_updated'),
    );
  }
}
