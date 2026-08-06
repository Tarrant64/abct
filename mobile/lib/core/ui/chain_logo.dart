import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

/// Displays a blockchain logo from cryptologos.cc with fallback to a colored
/// circle with the symbol's first letter (matching the previous behavior).
class ChainLogo extends StatelessWidget {
  const ChainLogo({super.key, required this.symbol, this.size = 40});

  final String symbol;
  final double size;

  // Maps symbol → cryptologos.cc slug (matches CHAIN_ICON_URLS in mobile.py)
  static const _logoSlugs = <String, String>{
    'ADA': 'cardano-ada-logo',
    'BTC': 'bitcoin-btc-logo',
    'ETH': 'ethereum-eth-logo',
    'SOL': 'solana-sol-logo',
    'POL': 'polygon-matic-logo',
    'MATIC': 'polygon-matic-logo',
    'ALGO': 'algorand-algo-logo',
    'BNB': 'bnb-bnb-logo',
    'AVAX': 'avalanche-avax-logo',
    'TRX': 'tron-trx-logo',
    'XRP': 'xrp-xrp-logo',
    'HBAR': 'hedera-hbar-logo',
    'EGLD': 'multiversx-egld-logo',
    'SUI': 'sui-sui-logo',
    'APT': 'aptos-apt-logo',
    'FIL': 'filecoin-fil-logo',
    'LTC': 'litecoin-ltc-logo',
    'DOGE': 'dogecoin-doge-logo',
    'ZEC': 'zcash-zec-logo',
    'XTZ': 'tezos-xtz-logo',
    'STX': 'stacks-stx-logo',
    'VET': 'vechain-vet-logo',
    'ATOM': 'cosmos-atom-logo',
    'NEAR': 'near-protocol-near-logo',
    'ICP': 'internet-computer-icp-logo',
    'DOT': 'polkadot-new-dot-logo',
    'LINK': 'chainlink-link-logo',
  };

  // GitHub avatars for chains without cryptologos entries
  static const _specialAvatars = <String, String>{
    'BASE': 'https://avatars.githubusercontent.com/u/108554348?s=64',
    'ARBITRUM': 'https://avatars.githubusercontent.com/u/119917794?s=64',
  };

  static const _symbolColors = <String, Color>{
    'BTC': Color(0xFFF7931A),
    'ETH': Color(0xFF627EEA),
    'SOL': Color(0xFF9945FF),
    'ADA': Color(0xFF0033AD),
    'DOT': Color(0xFFE6007A),
    'AVAX': Color(0xFFE84142),
    'MATIC': Color(0xFF8247E5),
    'ALGO': Color(0xFF000000),
    'ATOM': Color(0xFF2E3148),
    'LINK': Color(0xFF2A5ADA),
  };

  /// Returns true if ChainLogo has a known logo mapping for [symbol].
  static bool hasLogo(String symbol) {
    final upper = symbol.toUpperCase();
    return _logoSlugs.containsKey(upper) || _specialAvatars.containsKey(upper);
  }

  String? _imageUrl() {
    final upper = symbol.toUpperCase();

    final special = _specialAvatars[upper];
    if (special != null) return special;

    final slug = _logoSlugs[upper];
    if (slug != null) return 'https://cryptologos.cc/logos/$slug.png';

    return null;
  }

  @override
  Widget build(BuildContext context) {
    final upper = symbol.toUpperCase();
    final bgColor = _symbolColors[upper] ?? const Color(0xFF6366F1);
    final letter = upper.isNotEmpty ? upper[0] : '?';

    final fallback = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, color: bgColor),
      alignment: Alignment.center,
      child: Text(
        letter,
        style: TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w700,
          fontSize: size * 0.4,
        ),
      ),
    );

    final url = _imageUrl();
    if (url == null) return fallback;

    return ClipOval(
      child: SizedBox(
        width: size,
        height: size,
        child: CachedNetworkImage(
          imageUrl: url,
          width: size,
          height: size,
          fit: BoxFit.cover,
          placeholder: (_, __) => fallback,
          errorWidget: (_, __, ___) => fallback,
        ),
      ),
    );
  }
}
