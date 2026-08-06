import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

class AllocationSection {
  const AllocationSection({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final double value;
  final Color color;
}

class AllocationDonut extends StatelessWidget {
  const AllocationDonut({
    super.key,
    required this.sections,
    this.centerText,
  });

  final List<AllocationSection> sections;
  final String? centerText;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final visible = sections.where((s) => s.value > 0).toList();

    if (visible.isEmpty) {
      return Center(
        child: Text('No allocation data.', style: theme.textTheme.bodySmall),
      );
    }

    final total = visible.fold<double>(0, (sum, s) => sum + s.value);

    return Row(
      children: [
        SizedBox(
          width: 140,
          height: 140,
          child: PieChart(
            PieChartData(
              sectionsSpace: 2,
              centerSpaceRadius: 40,
              sections: [
                for (final s in visible)
                  PieChartSectionData(
                    value: s.value,
                    color: s.color,
                    radius: 24,
                    showTitle: false,
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (centerText != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    centerText!,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              for (final s in visible)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    children: [
                      Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(
                          color: s.color,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          s.label,
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                      Text(
                        total > 0
                            ? '${(s.value / total * 100).toStringAsFixed(1)}%'
                            : '0%',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
