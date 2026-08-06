import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// Reusable chart painter for portfolio history and asset detail screens.
class LineChartPainter extends CustomPainter {
  LineChartPainter({
    required this.points,
    required this.lineColor,
    required this.glowColor,
    required this.gridColor,
    required this.highlightedIndex,
    this.yLabels,
    this.xLabels,
    this.fillColorTop,
    this.fillColorBottom,
    this.markerColor,
  });

  final List<double> points;
  final Color lineColor;
  final Color glowColor;
  final Color gridColor;
  final int highlightedIndex;
  final List<String>? yLabels;
  final List<String>? xLabels;
  final Color? fillColorTop;
  final Color? fillColorBottom;
  final Color? markerColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;

    final hasYLabels = yLabels != null && yLabels!.length >= 2;
    final hasXLabels = xLabels != null && xLabels!.length >= 2;

    // Reserve margins for axis labels when present
    final leftMargin = hasYLabels ? 48.0 : 0.0;
    final bottomMargin = hasXLabels ? 20.0 : 0.0;

    final chartWidth = size.width - leftMargin;
    final chartHeight = size.height - bottomMargin;

    // Draw axis labels
    if (hasYLabels) {
      final labelStyle = ui.TextStyle(
        color: gridColor.withValues(alpha: 0.7),
        fontSize: 10,
      );

      // Max price (top)
      final maxBuilder = ui.ParagraphBuilder(ui.ParagraphStyle(
        textAlign: TextAlign.right,
        maxLines: 1,
      ))
        ..pushStyle(labelStyle)
        ..addText(yLabels![1]);
      final maxPara = maxBuilder.build()
        ..layout(ui.ParagraphConstraints(width: leftMargin - 6));
      canvas.drawParagraph(maxPara, const Offset(0, 2));

      // Min price (bottom)
      final minBuilder = ui.ParagraphBuilder(ui.ParagraphStyle(
        textAlign: TextAlign.right,
        maxLines: 1,
      ))
        ..pushStyle(labelStyle)
        ..addText(yLabels![0]);
      final minPara = minBuilder.build()
        ..layout(ui.ParagraphConstraints(width: leftMargin - 6));
      canvas.drawParagraph(
        minPara,
        Offset(0, chartHeight - minPara.height - 2),
      );
    }

    if (hasXLabels) {
      final labelStyle = ui.TextStyle(
        color: gridColor.withValues(alpha: 0.7),
        fontSize: 10,
      );

      // Start date (left)
      final startBuilder = ui.ParagraphBuilder(ui.ParagraphStyle(
        textAlign: TextAlign.left,
        maxLines: 1,
      ))
        ..pushStyle(labelStyle)
        ..addText(xLabels![0]);
      final startPara = startBuilder.build()
        ..layout(ui.ParagraphConstraints(width: chartWidth / 2));
      canvas.drawParagraph(
        startPara,
        Offset(leftMargin, chartHeight + 4),
      );

      // End date (right)
      final endBuilder = ui.ParagraphBuilder(ui.ParagraphStyle(
        textAlign: TextAlign.right,
        maxLines: 1,
      ))
        ..pushStyle(labelStyle)
        ..addText(xLabels![1]);
      final endPara = endBuilder.build()
        ..layout(ui.ParagraphConstraints(width: chartWidth / 2));
      canvas.drawParagraph(
        endPara,
        Offset(leftMargin + chartWidth / 2, chartHeight + 4),
      );
    }

    // Clip to chart area for drawing
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(leftMargin, 0, chartWidth, chartHeight));
    canvas.translate(leftMargin, 0);

    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;

    const vLines = 7;
    const hLines = 4;

    for (var i = 0; i <= vLines; i++) {
      final x = chartWidth * (i / vLines);
      canvas.drawLine(Offset(x, 0), Offset(x, chartHeight), gridPaint);
    }

    for (var i = 0; i <= hLines; i++) {
      final y = chartHeight * (i / hLines);
      canvas.drawLine(Offset(0, y), Offset(chartWidth, y), gridPaint);
    }

    final minY = points.reduce(math.min);
    final maxY = points.reduce(math.max);
    final rawRange = (maxY - minY).abs();
    // Use 1% of maxY as floor to avoid division-by-zero when all values equal,
    // but never force range=1.0 which crushes sub-dollar coins like ADA.
    final range = rawRange < maxY.abs() * 0.0001 ? (maxY.abs() * 0.01).clamp(1e-9, double.infinity) : rawRange;

    final line = Path();
    for (var i = 0; i < points.length; i++) {
      final x = chartWidth * (i / (points.length - 1));
      final y =
          chartHeight - ((points[i] - minY) / range * chartHeight);
      if (i == 0) {
        line.moveTo(x, y);
      } else {
        line.lineTo(x, y);
      }
    }

    final fill = Path.from(line)
      ..lineTo(chartWidth, chartHeight)
      ..lineTo(0, chartHeight)
      ..close();

    final effectiveFillTop =
        fillColorTop ?? const Color(0xFF826FFF).withValues(alpha: 0.32);
    final effectiveFillBottom =
        fillColorBottom ?? const Color(0xFF5FADFF).withValues(alpha: 0.04);

    final fillPaint = Paint()
      ..shader = ui.Gradient.linear(
        Offset(0, 0),
        Offset(0, chartHeight),
        [effectiveFillTop, effectiveFillBottom],
      );

    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..color = glowColor.withValues(alpha: 0.16)
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final lighterLine = Color.lerp(lineColor, Colors.white, 0.35)!;
    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.6
      ..shader = ui.Gradient.linear(
        Offset(0, 0),
        Offset(chartWidth, 0),
        [lighterLine, lineColor, lighterLine],
        const [0.0, 0.5, 1.0],
      )
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    canvas.drawPath(fill, fillPaint);
    canvas.drawPath(line, glowPaint);
    canvas.drawPath(line, linePaint);

    final effectiveMarker =
        markerColor ?? const Color(0xFFD2C8FF);
    final markerOffset =
        _pointAt(points, highlightedIndex, chartWidth, chartHeight, minY, range);
    final markerPaint = Paint()..color = effectiveMarker;
    canvas.drawLine(
      Offset(markerOffset.dx, 0),
      Offset(markerOffset.dx, chartHeight),
      Paint()
        ..color = effectiveMarker.withValues(alpha: 0.28)
        ..strokeWidth = 1.2,
    );
    canvas.drawCircle(markerOffset, 3.8, markerPaint);
    canvas.drawCircle(
      markerOffset,
      8,
      Paint()..color = effectiveMarker.withValues(alpha: 0.14),
    );

    canvas.restore();
  }

  Offset _pointAt(
    List<double> values,
    int index,
    double width,
    double height,
    double minY,
    double range,
  ) {
    final x = width * (index / (values.length - 1));
    final y = height - ((values[index] - minY) / range * height);
    return Offset(x, y);
  }

  @override
  bool shouldRepaint(covariant LineChartPainter oldDelegate) {
    // Value equality on the lists — callers rebuild widgets (and often the
    // lists) far more often than the data actually changes, and an identity
    // compare would repaint the whole chart on every such rebuild.
    return !listEquals(oldDelegate.points, points) ||
        oldDelegate.lineColor != lineColor ||
        oldDelegate.glowColor != glowColor ||
        oldDelegate.gridColor != gridColor ||
        oldDelegate.highlightedIndex != highlightedIndex ||
        !listEquals(oldDelegate.yLabels, yLabels) ||
        !listEquals(oldDelegate.xLabels, xLabels) ||
        oldDelegate.fillColorTop != fillColorTop ||
        oldDelegate.fillColorBottom != fillColorBottom ||
        oldDelegate.markerColor != markerColor;
  }
}

/// Interactive chart widget wrapping [LineChartPainter].
class InteractiveLineChart extends StatelessWidget {
  const InteractiveLineChart({
    super.key,
    required this.points,
    required this.highlightedIndex,
    required this.onPointSelected,
    required this.onInteractionEnd,
    this.lineColor = const Color(0xFF8B7BFF),
    this.glowColor = const Color(0xFF79B2FF),
    this.yLabels,
    this.xLabels,
    this.fillColorTop,
    this.fillColorBottom,
    this.markerColor,
    this.padding,
    this.showBorder = true,
  });

  final List<double> points;
  final int highlightedIndex;
  final ValueChanged<int> onPointSelected;
  final VoidCallback onInteractionEnd;
  final Color lineColor;
  final Color glowColor;
  final List<String>? yLabels;
  final List<String>? xLabels;
  final Color? fillColorTop;
  final Color? fillColorBottom;
  final Color? markerColor;
  final EdgeInsets? padding;
  final bool showBorder;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: padding ?? const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: showBorder
          ? BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: theme.colorScheme.outlineVariant),
              color: theme.colorScheme.surface.withValues(alpha: 0.34),
            )
          : null,
      child: LayoutBuilder(
        builder: (context, constraints) {
          int indexFromLocalDx(double dx) {
            if (points.length <= 1 || constraints.maxWidth <= 0) return 0;
            final normalized = (dx / constraints.maxWidth).clamp(0.0, 1.0);
            return (normalized * (points.length - 1)).round();
          }

          return MouseRegion(
            onHover: (event) =>
                onPointSelected(indexFromLocalDx(event.localPosition.dx)),
            onExit: (_) => onInteractionEnd(),
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTapDown: (details) =>
                  onPointSelected(indexFromLocalDx(details.localPosition.dx)),
              onHorizontalDragStart: (details) =>
                  onPointSelected(indexFromLocalDx(details.localPosition.dx)),
              onHorizontalDragUpdate: (details) =>
                  onPointSelected(indexFromLocalDx(details.localPosition.dx)),
              onHorizontalDragCancel: onInteractionEnd,
              onHorizontalDragEnd: (_) => onInteractionEnd(),
              // Isolate the chart's layer: scrub repaints stay inside this
              // boundary, and unrelated ancestor repaints don't re-run the
              // (comparatively expensive) chart painter.
              child: RepaintBoundary(
                child: CustomPaint(
                  painter: LineChartPainter(
                    points: points,
                    lineColor: lineColor,
                    glowColor: glowColor,
                    gridColor:
                        theme.colorScheme.onSurface.withValues(alpha: 0.08),
                    highlightedIndex: highlightedIndex,
                    yLabels: yLabels,
                    xLabels: xLabels,
                    fillColorTop: fillColorTop,
                    fillColorBottom: fillColorBottom,
                    markerColor: markerColor,
                  ),
                  child: const SizedBox.expand(),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
