import 'package:flutter_test/flutter_test.dart';
import 'package:abct_mobile/core/ui/value_formatters.dart';

void main() {
  group('ValueFormatters.usd', () {
    test('formats positive values', () {
      expect(ValueFormatters.usd(1234.56), r'$1,234.56');
    });

    test('formats negative values', () {
      expect(ValueFormatters.usd(-500), r'-$500.00');
    });

    test('formats zero', () {
      expect(ValueFormatters.usd(0), r'$0.00');
    });

    test('custom decimals', () {
      expect(ValueFormatters.usd(100, decimals: 0), r'$100');
    });
  });

  group('ValueFormatters.percent', () {
    test('formats with default 1 decimal', () {
      expect(ValueFormatters.percent(5.678), '5.7%');
    });

    test('formats negative', () {
      expect(ValueFormatters.percent(-3.2), '-3.2%');
    });
  });

  group('ValueFormatters.compactUsd', () {
    test('billions', () {
      expect(ValueFormatters.compactUsd(1500000000), r'$1.50B');
    });

    test('millions', () {
      expect(ValueFormatters.compactUsd(2500000), r'$2.50M');
    });

    test('thousands', () {
      expect(ValueFormatters.compactUsd(5500), r'$5.5K');
    });

    test('small values fall through to usd', () {
      expect(ValueFormatters.compactUsd(42.5), r'$42.50');
    });

    test('negative values', () {
      expect(ValueFormatters.compactUsd(-3000000), r'-$3.00M');
    });
  });

  group('ValueFormatters.shortenAddress', () {
    test('shortens long address', () {
      expect(
        ValueFormatters.shortenAddress('0x1234567890abcdef1234567890abcdef12345678'),
        '0x1234...345678',
      );
    });

    test('returns short address as-is', () {
      expect(ValueFormatters.shortenAddress('0x1234'), '0x1234');
    });
  });

  group('ValueFormatters.titleCase', () {
    test('capitalizes words', () {
      expect(ValueFormatters.titleCase('hello world'), 'Hello World');
    });

    test('handles underscores', () {
      expect(ValueFormatters.titleCase('self_custody'), 'Self Custody');
    });

    test('handles hyphens', () {
      expect(ValueFormatters.titleCase('ocean-depths'), 'Ocean Depths');
    });

    test('handles empty string', () {
      expect(ValueFormatters.titleCase(''), '');
    });
  });

  group('ValueFormatters.timestamp', () {
    test('formats ISO timestamp', () {
      final result = ValueFormatters.timestamp('2025-06-15T10:30:00Z');
      // Result depends on local timezone, so just check format
      expect(result, contains('-'));
      expect(result, contains(':'));
    });

    test('returns Unknown for null', () {
      expect(ValueFormatters.timestamp(null), 'Unknown');
    });

    test('returns raw for unparseable', () {
      expect(ValueFormatters.timestamp('not-a-date'), 'not-a-date');
    });
  });
}
