import 'dart:async';

import 'package:flutter/widgets.dart';

/// App-wide lifecycle refresh signal.
///
/// Notifies listeners when the app returns to the foreground
/// ([AppLifecycleState.resumed]) and periodically while it stays there, so
/// data views can silently re-fetch while their cached content stays on
/// screen. Cold launch does not emit a signal — each tab's initial load in
/// `initState` covers that case.
///
/// A minimum interval between signals prevents refresh storms when the app is
/// rapidly backgrounded and resumed (control centre, app switcher peek, etc.)
/// and coalesces a periodic tick that lands right after a resume signal.
class AppRefreshSignal extends ChangeNotifier with WidgetsBindingObserver {
  AppRefreshSignal({
    Duration minInterval = minRefreshInterval,
    Duration foregroundInterval = foregroundRefreshInterval,
  })  : _minInterval = minInterval,
        _foregroundInterval = foregroundInterval;

  /// Shared instance used by the app shell and all tabs.
  static final AppRefreshSignal instance = AppRefreshSignal();

  /// Minimum time between refresh signals. Also the recommended minimum data
  /// age before a listener re-fetches in response to a signal.
  static const Duration minRefreshInterval = Duration(seconds: 30);

  /// How often to signal while the app stays foregrounded, so an open-but-idle
  /// app doesn't sit on stale numbers indefinitely.
  ///
  /// 10 minutes is deliberate: the server's summary row is fresh for 120s and
  /// stale-servable (SWR) for 600s past that, so a tick at this cadence is
  /// answered instantly from the server cache while kicking off one cheap
  /// background recompute — which the cache layer's one-shot stale follow-up
  /// then collects ~35s later. Longer gaps fall out of the SWR window and
  /// force synchronous recomputes; shorter ones buy nothing the 120s TTL
  /// doesn't already serve.
  static const Duration foregroundRefreshInterval = Duration(minutes: 10);

  final Duration _minInterval;
  final Duration _foregroundInterval;
  DateTime? _lastSignalAt;
  bool _observing = false;
  Timer? _foregroundTimer;

  /// Whether this signal is currently registered as a lifecycle observer.
  @visibleForTesting
  bool get isObserving => _observing;

  /// Whether the foreground periodic timer is currently running.
  @visibleForTesting
  bool get isForegroundTimerActive => _foregroundTimer != null;

  /// Start observing app lifecycle changes. Idempotent; call once during app
  /// start-up, after the widgets binding is initialized.
  void start() {
    if (_observing) return;
    _observing = true;
    // Treat launch itself as a fresh load so a resumed event fired right
    // after start-up doesn't trigger a redundant refresh.
    _lastSignalAt = DateTime.now();
    WidgetsBinding.instance.addObserver(this);
    // Launch means foregrounded: begin the periodic cycle now rather than
    // waiting for a background/resume round trip.
    _startForegroundTimer();
  }

  /// Stop observing lifecycle changes.
  void stop() {
    // Cancel unconditionally: a resume event delivered before start() (tests
    // drive the observer callback directly) starts the timer without setting
    // the observing flag, and it must still be stoppable.
    _stopForegroundTimer();
    if (!_observing) return;
    _observing = false;
    WidgetsBinding.instance.removeObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _startForegroundTimer();
      _maybeNotify();
      return;
    }
    // inactive / hidden / paused / detached: the app is no longer the active
    // foreground app, so the periodic cycle stops (iOS suspends the process
    // shortly after backgrounding anyway). The resume path above restarts it.
    _stopForegroundTimer();
  }

  void _startForegroundTimer() {
    if (_foregroundTimer != null) return;
    _foregroundTimer = Timer.periodic(_foregroundInterval, (_) {
      _maybeNotify();
    });
  }

  void _stopForegroundTimer() {
    _foregroundTimer?.cancel();
    _foregroundTimer = null;
  }

  /// Emits a refresh signal unless one fired within [_minInterval] — the
  /// single guarded path shared by resume events and foreground timer ticks,
  /// so triggers landing close together coalesce into one signal.
  void _maybeNotify() {
    final last = _lastSignalAt;
    final now = DateTime.now();
    if (last != null && now.difference(last) < _minInterval) return;
    _lastSignalAt = now;
    notifyListeners();
  }

  /// Test hook: emits a refresh signal unconditionally, bypassing the
  /// min-interval guard (which real wall-clock time in tests can't get past).
  @visibleForTesting
  void debugEmitSignal() {
    _lastSignalAt = DateTime.now();
    notifyListeners();
  }

  /// Test hook: drives a foreground timer tick through the guarded notify
  /// path without waiting for the real interval.
  @visibleForTesting
  void debugTick() => _maybeNotify();
}
