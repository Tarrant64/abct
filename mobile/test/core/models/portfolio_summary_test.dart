import 'package:flutter_test/flutter_test.dart';
import 'package:abct_mobile/core/models/portfolio_summary.dart';

void main() {
  group('PortfolioSummary.fromJson', () {
    test('parses minimal valid JSON', () {
      final json = {
        'total_value_usd': 50000.0,
        'total_native': {'BTC': 1.5, 'ETH': 10.0},
        'breakdown': {
          'self_custody': {'value_usd': 30000, 'percentage': 60},
          'exchanges': {'value_usd': 15000, 'percentage': 30},
          'nfts': {'value_usd': 3000, 'percentage': 6},
          'staking': {'value_usd': 2000, 'percentage': 4},
        },
        'blockchains': [
          {
            'name': 'bitcoin',
            'symbol': 'BTC',
            'value_usd': 40000,
            'native_amount': 1.5,
            'native_price_usd': 26666.67,
            'wallet_count': 2,
            'percentage': 80,
          },
          {
            'name': 'ethereum',
            'symbol': 'ETH',
            'value_usd': 10000,
            'native_amount': 10,
            'native_price_usd': 1000,
            'wallet_count': 1,
            'percentage': 20,
          },
        ],
        'from_cache': true,
      };

      final summary = PortfolioSummary.fromJson(json);
      expect(summary.totalValueUsd, 50000.0);
      expect(summary.fromCache, true);
      expect(summary.breakdown.selfCustody.valueUsd, 30000);
      expect(summary.breakdown.exchanges.percentage, 30);
      // Blockchains should be sorted by value descending
      expect(summary.blockchains.first.symbol, 'BTC');
      expect(summary.blockchains.last.symbol, 'ETH');
    });

    test('handles missing optional fields', () {
      final json = {
        'total_value_usd': 0,
        'breakdown': {
          'self_custody': {},
          'exchanges': {},
          'nfts': {},
          'staking': {},
        },
        'blockchains': [],
      };

      final summary = PortfolioSummary.fromJson(json);
      expect(summary.totalValueUsd, 0);
      expect(summary.blockchains, isEmpty);
      expect(summary.lastUpdated, isNull);
      expect(summary.fromCache, false);
    });
  });

  group('BlockchainHolding.fromJson', () {
    test('parses string numeric values', () {
      final json = {
        'name': 'cardano',
        'symbol': 'ADA',
        'value_usd': '5000.50',
        'native_amount': '10000',
        'native_price_usd': '0.50',
        'wallet_count': '3',
        'percentage': '10.5',
      };

      final holding = BlockchainHolding.fromJson(json);
      expect(holding.name, 'cardano');
      expect(holding.symbol, 'ADA');
      expect(holding.valueUsd, 5000.50);
      expect(holding.walletCount, 3);
    });
  });
}
