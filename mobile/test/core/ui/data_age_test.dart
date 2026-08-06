import 'package:abct_mobile/core/ui/data_age.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('DataAgeCaption.isStale', () {
    final now = DateTime.utc(2026, 7, 13, 12, 0, 0);

    test('null lastUpdated is never stale (nothing to report)', () {
      expect(DataAgeCaption.isStale(null, now), isFalse);
    });

    test('recent payloads are not stale', () {
      expect(
        DataAgeCaption.isStale(
            now.subtract(const Duration(minutes: 4)), now),
        isFalse,
      );
    });

    test('payloads older than the threshold are stale', () {
      expect(
        DataAgeCaption.isStale(
            now.subtract(const Duration(minutes: 6)), now),
        isTrue,
      );
    });

    test('comparison is timezone-safe (local vs UTC timestamps)', () {
      // A 2-minute-old timestamp expressed in a non-UTC zone must not be
      // misread as hours old.
      final localish = now.subtract(const Duration(minutes: 2)).toLocal();
      expect(DataAgeCaption.isStale(localish, now), isFalse);
    });
  });

  group('DataAgeCaption widget', () {
    Widget harness(Widget child) =>
        MaterialApp(home: Scaffold(body: child));

    testWidgets('renders "as of" caption for stale data', (tester) async {
      await tester.pumpWidget(harness(DataAgeCaption(
        lastUpdated: DateTime.now().subtract(const Duration(minutes: 30)),
      )));
      expect(find.textContaining('as of '), findsOneWidget);
    });

    testWidgets('renders nothing for fresh data', (tester) async {
      await tester.pumpWidget(harness(DataAgeCaption(
        lastUpdated: DateTime.now().subtract(const Duration(minutes: 1)),
      )));
      expect(find.byType(Text), findsNothing);
    });

    testWidgets('renders nothing when the payload has no timestamp',
        (tester) async {
      await tester.pumpWidget(harness(const DataAgeCaption(
        lastUpdated: null,
      )));
      expect(find.byType(Text), findsNothing);
    });
  });
}
