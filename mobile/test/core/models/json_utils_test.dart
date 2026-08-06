import 'package:flutter_test/flutter_test.dart';
import 'package:abct_mobile/core/models/json_utils.dart';

void main() {
  group('JsonUtils.string', () {
    test('returns value when present', () {
      expect(JsonUtils.string({'key': 'hello'}, 'key'), 'hello');
    });

    test('returns fallback when key missing', () {
      expect(JsonUtils.string({}, 'key', fallback: 'default'), 'default');
    });

    test('converts non-string to string', () {
      expect(JsonUtils.string({'key': 42}, 'key'), '42');
    });
  });

  group('JsonUtils.doubleValue', () {
    test('parses num', () {
      expect(JsonUtils.doubleValue({'v': 3.14}, 'v'), 3.14);
    });

    test('parses string', () {
      expect(JsonUtils.doubleValue({'v': '2.5'}, 'v'), 2.5);
    });

    test('returns fallback for missing key', () {
      expect(JsonUtils.doubleValue({}, 'v', fallback: -1), -1);
    });

    test('returns fallback for invalid string', () {
      expect(JsonUtils.doubleValue({'v': 'abc'}, 'v', fallback: 0), 0);
    });
  });

  group('JsonUtils.intValue', () {
    test('parses int', () {
      expect(JsonUtils.intValue({'v': 42}, 'v'), 42);
    });

    test('parses num as int', () {
      expect(JsonUtils.intValue({'v': 3.9}, 'v'), 3);
    });

    test('parses string', () {
      expect(JsonUtils.intValue({'v': '7'}, 'v'), 7);
    });

    test('returns fallback for null', () {
      expect(JsonUtils.intValue({'v': null}, 'v', fallback: 99), 99);
    });
  });

  group('JsonUtils.boolValue', () {
    test('parses bool true', () {
      expect(JsonUtils.boolValue({'v': true}, 'v'), true);
    });

    test('parses string "true"', () {
      expect(JsonUtils.boolValue({'v': 'true'}, 'v'), true);
    });

    test('parses string "1"', () {
      expect(JsonUtils.boolValue({'v': '1'}, 'v'), true);
    });

    test('parses num 0 as false', () {
      expect(JsonUtils.boolValue({'v': 0}, 'v'), false);
    });

    test('returns fallback for missing', () {
      expect(JsonUtils.boolValue({}, 'v', fallback: true), true);
    });
  });

  group('JsonUtils.optionalString', () {
    test('returns null for missing key', () {
      expect(JsonUtils.optionalString({}, 'key'), null);
    });

    test('returns null for empty string', () {
      expect(JsonUtils.optionalString({'key': '  '}, 'key'), null);
    });

    test('returns trimmed value', () {
      expect(JsonUtils.optionalString({'key': ' hello '}, 'key'), 'hello');
    });
  });

  group('JsonUtils.map', () {
    test('returns empty map for null', () {
      expect(JsonUtils.map(null), isEmpty);
    });

    test('passes through Map<String, dynamic>', () {
      final m = {'a': 1};
      expect(JsonUtils.map(m), equals(m));
    });

    test('converts untyped Map', () {
      final m = {1: 'a', 'b': 2};
      final result = JsonUtils.map(m);
      expect(result['1'], 'a');
      expect(result['b'], 2);
    });
  });

  group('JsonUtils.listOfMaps', () {
    test('returns empty for non-list', () {
      expect(JsonUtils.listOfMaps('not a list'), isEmpty);
    });

    test('parses list of maps', () {
      final list = [
        {'a': 1},
        {'b': 2}
      ];
      expect(JsonUtils.listOfMaps(list), hasLength(2));
    });
  });

  group('JsonUtils.stringToDoubleMap', () {
    test('parses numeric values', () {
      final result = JsonUtils.stringToDoubleMap({'a': 1.5, 'b': 2});
      expect(result['a'], 1.5);
      expect(result['b'], 2.0);
    });

    test('parses string numeric values', () {
      final result = JsonUtils.stringToDoubleMap({'a': '3.14'});
      expect(result['a'], 3.14);
    });

    test('skips unparseable', () {
      final result = JsonUtils.stringToDoubleMap({'a': 'abc'});
      expect(result, isEmpty);
    });
  });
}
