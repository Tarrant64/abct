import 'package:flutter/material.dart';

import 'haptics.dart';

/// Pull-to-refresh with soft / hard distinction.
///
/// Short pull (below [hardThreshold] pixels of overscroll) → soft refresh.
/// Long pull (past threshold) → haptic bump + indicator turns amber → hard refresh.
///
/// Usage:
/// ```dart
/// SmartRefreshIndicator(
///   onRefresh: (hard) async { ... },
///   child: ListView(...),
/// )
/// ```
class SmartRefreshIndicator extends StatefulWidget {
  const SmartRefreshIndicator({
    super.key,
    required this.onRefresh,
    required this.child,
    this.hardThreshold = 140,
  });

  /// Called when the user releases after pulling down.
  /// [hard] is true when the pull exceeded [hardThreshold].
  final Future<void> Function(bool hard) onRefresh;
  final Widget child;

  /// Overscroll pixels required to trigger a hard refresh.
  final double hardThreshold;

  @override
  State<SmartRefreshIndicator> createState() => _SmartRefreshIndicatorState();
}

class _SmartRefreshIndicatorState extends State<SmartRefreshIndicator> {
  /// Deepest overscroll of the current drag; drives [_isHard].
  double _maxPull = 0;

  /// Live drag state: the current pull has crossed [SmartRefreshIndicator.hardThreshold].
  bool _isHard = false;

  /// Hard verdict latched when the drag ends, consumed by [_handleRefresh].
  ///
  /// RefreshIndicator invokes onRefresh asynchronously (after its snap
  /// animation), well after the ScrollEndNotification — so the verdict must
  /// survive until the callback runs. A timer-based reset here used to race
  /// that callback and could downgrade a hard pull to soft.
  bool _pendingHard = false;

  bool _onScroll(ScrollNotification notification) {
    if (notification is ScrollStartNotification) {
      // New gesture: discard a latch that was never consumed (a hard pull
      // pushed back up and released without triggering a refresh).
      _pendingHard = false;
    }
    if (notification is ScrollUpdateNotification) {
      final pixels = notification.metrics.pixels;
      if (pixels < 0) {
        final pull = pixels.abs();
        if (pull > _maxPull) _maxPull = pull;
        final nowHard = _maxPull >= widget.hardThreshold;
        if (nowHard && !_isHard) {
          Haptics.heavy();
          setState(() => _isHard = true);
        }
      }
    }
    if (notification is ScrollEndNotification) {
      if (_maxPull >= widget.hardThreshold) _pendingHard = true;
      _maxPull = 0;
      if (_isHard) setState(() => _isHard = false);
    }
    return false; // don't consume — let RefreshIndicator handle it
  }

  Future<void> _handleRefresh() async {
    // Covers both orderings: _pendingHard when the scroll already ended,
    // _isHard when onRefresh somehow fires before ScrollEndNotification.
    final hard = _pendingHard || _isHard;
    _maxPull = 0;
    if (_isHard) setState(() => _isHard = false);
    try {
      await widget.onRefresh(hard);
    } finally {
      if (_pendingHard) {
        _pendingHard = false;
        // Spinner color returns to primary now that the hard refresh is done.
        if (mounted) setState(() {});
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return NotificationListener<ScrollNotification>(
      onNotification: _onScroll,
      child: RefreshIndicator(
        color: (_isHard || _pendingHard)
            ? Colors.amber
            : Theme.of(context).colorScheme.primary,
        onRefresh: _handleRefresh,
        child: widget.child,
      ),
    );
  }
}
