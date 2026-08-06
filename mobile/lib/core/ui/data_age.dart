import 'package:flutter/material.dart';

/// Subtle "as of HH:MM" caption for data that is older than [threshold].
///
/// Renders nothing while the payload is recent — the common case stays
/// visually unchanged. Once the data's age crosses the threshold the caption
/// makes staleness visible instead of letting an old number pass as live
/// (the silent-stale failure mode behind PRICE-1: a frozen total looked
/// exactly like a healthy one).
///
/// [lastUpdated] is the payload's own server-side timestamp (UTC); the
/// caption shows it in device-local time.
class DataAgeCaption extends StatelessWidget {
  const DataAgeCaption({
    super.key,
    required this.lastUpdated,
    this.threshold = const Duration(minutes: 5),
    this.color,
  });

  final DateTime? lastUpdated;
  final Duration threshold;

  /// Caption color; defaults to a faint white matching header captions.
  final Color? color;

  /// Whether [lastUpdated] is old enough (vs [now]) to warrant the caption.
  static bool isStale(
    DateTime? lastUpdated,
    DateTime now, {
    Duration threshold = const Duration(minutes: 5),
  }) {
    if (lastUpdated == null) return false;
    return now.toUtc().difference(lastUpdated.toUtc()) > threshold;
  }

  @override
  Widget build(BuildContext context) {
    final updated = lastUpdated;
    if (!isStale(updated, DateTime.now(), threshold: threshold)) {
      return const SizedBox.shrink();
    }
    final local = TimeOfDay.fromDateTime(updated!.toLocal());
    return Text(
      'as of ${local.format(context)}',
      style: TextStyle(
        fontSize: 12,
        color: color ?? Colors.white.withValues(alpha: 0.4),
        letterSpacing: 0.2,
      ),
    );
  }
}
