import 'package:flutter_test/flutter_test.dart';
import 'package:abct_mobile/core/models/portfolio_history.dart';

void main() {
  group('PortfolioHistoryPoint timestamp parsing', () {
    test('parses ISO string', () {
      final point = PortfolioHistoryPoint.fromJson({
        'timestamp': '2025-01-15T12:00:00Z',
        'total_value_usd': 1000,
      });
      expect(point.timestamp.year, 2025);
      expect(point.timestamp.month, 1);
      expect(point.timestamp.day, 15);
    });

    test('parses unix seconds', () {
      final point = PortfolioHistoryPoint.fromJson({
        'timestamp': 1705312800, // 2024-01-15 10:00 UTC
        'total_value_usd': 2000,
      });
      expect(point.timestamp.year, 2024);
    });

    test('parses unix milliseconds', () {
      final point = PortfolioHistoryPoint.fromJson({
        'timestamp': 1705312800000,
        'total_value_usd': 3000,
      });
      expect(point.timestamp.year, 2024);
    });

    test('falls back to epoch for null', () {
      final point = PortfolioHistoryPoint.fromJson({
        'total_value_usd': 500,
      });
      expect(point.timestamp.year, 1970);
    });
  });

  group('PortfolioHistoryPoint total value keys', () {
    test('reads total_value_usd', () {
      final p = PortfolioHistoryPoint.fromJson({
        'timestamp': '2025-01-01T00:00:00Z',
        'total_value_usd': 1234,
      });
      expect(p.totalValueUsd, 1234);
    });

    test('reads value_usd as fallback', () {
      final p = PortfolioHistoryPoint.fromJson({
        'timestamp': '2025-01-01T00:00:00Z',
        'value_usd': 5678,
      });
      expect(p.totalValueUsd, 5678);
    });
  });

  group('PortfolioHistory.fromJson', () {
    test('parses nested data format', () {
      final json = {
        'data': {
          'range': '7d',
          'interval': 'daily',
          'data_points': 7,
          'chart_data': [
            {
              'timestamp': '2025-01-10T00:00:00Z',
              'total_value_usd': 1000,
            },
            {
              'timestamp': '2025-01-11T00:00:00Z',
              'total_value_usd': 1100,
            },
          ],
          'summary': {
            'starting_value': 1000,
            'ending_value': 1100,
            'change_usd': 100,
            'change_percent': 10,
            'highest_value': 1100,
            'lowest_value': 1000,
          },
        },
      };

      final history = PortfolioHistory.fromJson(json);
      expect(history.range, '7d');
      expect(history.chartData.length, 2);
      expect(history.summary.changePercent, 10);
      // Should be sorted by timestamp
      expect(
        history.chartData.first.timestamp
            .isBefore(history.chartData.last.timestamp),
        true,
      );
    });

    test('parses flat format', () {
      final json = {
        'range': '4w',
        'chart_data': [
          {
            'timestamp': '2025-01-01T00:00:00Z',
            'total_value_usd': 500,
          },
        ],
        'summary': {
          'starting_value': 500,
          'ending_value': 500,
          'change_usd': 0,
          'change_percent': 0,
          'highest_value': 500,
          'lowest_value': 500,
        },
      };

      final history = PortfolioHistory.fromJson(json);
      expect(history.range, '4w');
      expect(history.chartData.length, 1);
    });
  });
}
