import 'package:flutter_test/flutter_test.dart';
import 'package:abct_mobile/core/models/transaction.dart';

void main() {
  group('Transaction.fromJson', () {
    test('parses complete transaction', () {
      final json = {
        'tx_hash': '0xabc123',
        'blockchain': 'ethereum',
        'direction': 'sent',
        'amount': 1.5,
        'symbol': 'ETH',
        'value_usd': 3000.0,
        'from_address': '0xfrom',
        'to_address': '0xto',
        'tx_time': '2025-06-15T10:30:00Z',
        'fee': 0.002,
        'fee_symbol': 'ETH',
      };

      final tx = Transaction.fromJson(json);
      expect(tx.txHash, '0xabc123');
      expect(tx.blockchain, 'ethereum');
      expect(tx.direction, 'sent');
      expect(tx.amount, 1.5);
      expect(tx.symbol, 'ETH');
      expect(tx.valueUsd, 3000.0);
      expect(tx.fee, 0.002);
    });

    test('handles missing fields gracefully', () {
      final json = <String, dynamic>{};
      final tx = Transaction.fromJson(json);
      expect(tx.txHash, '');
      expect(tx.direction, 'unknown');
      expect(tx.amount, 0);
    });

    test('parses unix timestamp', () {
      final json = {
        'tx_time': 1718444400, // unix seconds
        'blockchain': 'bitcoin',
      };
      final tx = Transaction.fromJson(json);
      expect(tx.txTime.year, greaterThanOrEqualTo(2024));
    });
  });

  group('TransactionHistory.fromJson', () {
    test('parses transaction list', () {
      final json = {
        'transactions': [
          {
            'tx_hash': 'hash1',
            'blockchain': 'ethereum',
            'tx_time': '2025-01-02T00:00:00Z',
          },
          {
            'tx_hash': 'hash2',
            'blockchain': 'bitcoin',
            'tx_time': '2025-01-01T00:00:00Z',
          },
        ],
        'total_count': 2,
        'days': 30,
      };

      final history = TransactionHistory.fromJson(json);
      expect(history.transactions.length, 2);
      expect(history.totalCount, 2);
      expect(history.days, 30);
      // Should be sorted descending by time
      expect(
        history.transactions.first.txTime
            .isAfter(history.transactions.last.txTime),
        true,
      );
    });

    test('handles alternative keys', () {
      final json = {
        'items': [
          {'tx_hash': 'h1', 'tx_time': '2025-01-01T00:00:00Z'},
        ],
      };

      final history = TransactionHistory.fromJson(json);
      expect(history.transactions.length, 1);
    });
  });
}
