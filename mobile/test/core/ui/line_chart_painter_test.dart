import 'package:abct_mobile/core/ui/line_chart_painter.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// shouldRepaint value-equality matrix: rebuilding a widget tree (and its
/// point lists) with unchanged data must NOT repaint; genuine data or
/// selection changes must.
void main() {
  LineChartPainter painter({
    List<double> points = const [1, 2, 3],
    int highlightedIndex = 2,
    List<String>? yLabels,
    List<String>? xLabels,
    Color lineColor = Colors.purple,
  }) {
    return LineChartPainter(
      points: points,
      lineColor: lineColor,
      glowColor: Colors.blue,
      gridColor: Colors.grey,
      highlightedIndex: highlightedIndex,
      yLabels: yLabels,
      xLabels: xLabels,
    );
  }

  test('same values in different list instances do not repaint', () {
    final old = painter(points: [1.0, 2.0, 3.0], yLabels: ['a', 'b']);
    final fresh = painter(points: [1.0, 2.0, 3.0], yLabels: ['a', 'b']);

    expect(identical(old.points, fresh.points), isFalse);
    expect(fresh.shouldRepaint(old), isFalse);
  });

  test('identical list instances do not repaint', () {
    final shared = [1.0, 2.0, 3.0];
    expect(
      painter(points: shared).shouldRepaint(painter(points: shared)),
      isFalse,
    );
  });

  test('changed point values repaint', () {
    final old = painter(points: [1.0, 2.0, 3.0]);
    final fresh = painter(points: [1.0, 2.0, 4.0]);
    expect(fresh.shouldRepaint(old), isTrue);
  });

  test('changed point count repaints', () {
    final old = painter(points: [1.0, 2.0, 3.0]);
    final fresh = painter(points: [1.0, 2.0, 3.0, 4.0]);
    expect(fresh.shouldRepaint(old), isTrue);
  });

  test('changed highlighted index repaints (scrubbing stays live)', () {
    final old = painter(highlightedIndex: 1);
    final fresh = painter(highlightedIndex: 2);
    expect(fresh.shouldRepaint(old), isTrue);
  });

  test('changed labels repaint; equal labels in new instances do not', () {
    expect(
      painter(xLabels: ['Jan', 'Jun'])
          .shouldRepaint(painter(xLabels: ['Jan', 'May'])),
      isTrue,
    );
    expect(
      painter(xLabels: ['Jan', 'Jun'])
          .shouldRepaint(painter(xLabels: ['Jan', 'Jun'])),
      isFalse,
    );
  });

  test('changed color repaints', () {
    final old = painter(lineColor: Colors.purple);
    final fresh = painter(lineColor: Colors.teal);
    expect(fresh.shouldRepaint(old), isTrue);
  });
}
