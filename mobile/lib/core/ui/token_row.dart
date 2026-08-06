import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/connection_profile.dart';
import '../models/token_holding.dart';
import 'chain_logo.dart';
import 'haptics.dart';
import 'value_formatters.dart';
import '../../features/asset_detail/asset_detail_screen.dart';

/// Sort modes for the unified holdings list.
enum HoldingsSortMode {
  value('Value'),
  name('Name'),
  quantity('Quantity');

  const HoldingsSortMode(this.label);
  final String label;
}

/// Pill-shaped sort toggle button.
class SortPill extends StatelessWidget {
  const SortPill({
    super.key,
    required this.label,
    required this.isSelected,
    required this.ascending,
    required this.onTap,
  });

  final String label;
  final bool isSelected;
  final bool? ascending;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final onSurface = Theme.of(context).colorScheme.onSurface;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          color: isSelected
              ? onSurface.withValues(alpha: 0.12)
              : onSurface.withValues(alpha: 0.04),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                color: isSelected
                    ? onSurface
                    : onSurface.withValues(alpha: 0.5),
              ),
            ),
            if (isSelected && ascending != null) ...[
              const SizedBox(width: 3),
              Icon(
                ascending! ? Icons.arrow_upward : Icons.arrow_downward,
                size: 12,
                color: onSurface.withValues(alpha: 0.7),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A single token row showing logo, name, quantity, value, and 24h change.
/// Tapping navigates to [AssetDetailScreen].
class TokenRow extends StatelessWidget {
  const TokenRow({
    super.key,
    required this.token,
    required this.privacyMode,
    required this.profile,
  });

  final TokenHolding token;
  final bool privacyMode;
  final ConnectionProfile profile;

  @override
  Widget build(BuildContext context) {
    final onSurface = Theme.of(context).colorScheme.onSurface;
    final ticker = token.ticker.isNotEmpty
        ? token.ticker.toUpperCase()
        : token.assetName.toUpperCase();
    final displayName = token.displayName;
    final hasPriceChange = token.priceChange24h != 0;
    final priceChangePositive = token.priceChange24h >= 0;
    final priceChangeColor = priceChangePositive
        ? const Color(0xFF4ADE80)
        : Theme.of(context).colorScheme.error;
    final dimColor = onSurface.withValues(alpha: 0.45);

    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () {
        Haptics.light();
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => AssetDetailScreen(
              profile: profile,
              symbol: ticker,
              name: token.assetName,
              holdingValueUsd: token.valueUsd ?? 0,
              holdingPercentage: 0,
              nativeAmount: token.totalQuantity,
            ),
          ),
        );
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            _buildLogo(ticker),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    displayName,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: onSurface,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    privacyMode
                        ? ticker
                        : '${ValueFormatters.tokenAmount(token.totalQuantity)} $ticker',
                    style: TextStyle(fontSize: 13, color: dimColor),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  privacyMode
                      ? r'$••••'
                      : ValueFormatters.usd(token.valueUsd ?? 0),
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: onSurface,
                  ),
                ),
                const SizedBox(height: 3),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (token.priceUsd != null)
                      Text(
                        privacyMode
                            ? r'$••••'
                            : ValueFormatters.usd(token.priceUsd!),
                        style: TextStyle(fontSize: 12, color: dimColor),
                      ),
                    if (hasPriceChange) ...[
                      const SizedBox(width: 4),
                      Icon(
                        priceChangePositive
                            ? Icons.north_east
                            : Icons.south_east,
                        size: 10,
                        color: priceChangeColor,
                      ),
                      const SizedBox(width: 1),
                      Text(
                        ValueFormatters.percent(token.priceChange24h.abs()),
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: priceChangeColor,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLogo(String ticker) {
    if (ChainLogo.hasLogo(ticker)) {
      return ChainLogo(symbol: ticker, size: 40);
    }
    final logoUrl = token.logoUrl;
    if (logoUrl != null && logoUrl.isNotEmpty) {
      final letter = ticker.isNotEmpty ? ticker[0] : '?';
      return ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: CachedNetworkImage(
          imageUrl: logoUrl,
          width: 40,
          height: 40,
          fit: BoxFit.cover,
          placeholder: (_, __) => LetterFallback(letter: letter, size: 40),
          errorWidget: (_, __, ___) => LetterFallback(letter: letter, size: 40),
        ),
      );
    }
    return ChainLogo(symbol: ticker, size: 40);
  }
}

/// Colored circle with a letter initial, used as a fallback for token logos.
class LetterFallback extends StatelessWidget {
  const LetterFallback({super.key, required this.letter, required this.size});

  final String letter;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: _colorForLetter(letter),
      ),
      alignment: Alignment.center,
      child: Text(
        letter,
        style: TextStyle(
          fontSize: size * 0.45,
          fontWeight: FontWeight.w700,
          color: Colors.white,
        ),
      ),
    );
  }

  static Color _colorForLetter(String letter) {
    const palette = [
      Color(0xFF6366F1),
      Color(0xFF8B5CF6),
      Color(0xFFEC4899),
      Color(0xFFEF4444),
      Color(0xFFF97316),
      Color(0xFFEAB308),
      Color(0xFF22C55E),
      Color(0xFF14B8A6),
      Color(0xFF06B6D4),
      Color(0xFF3B82F6),
    ];
    final index = letter.codeUnitAt(0) % palette.length;
    return palette[index];
  }
}
