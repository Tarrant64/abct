import 'dart:async';
import 'dart:developer' as developer;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import '../../../core/storage/secure_store.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/portfolio_history.dart';
import '../../../core/models/portfolio_instant.dart';
import '../../../core/models/portfolio_summary.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_interceptor.dart';
import '../../../core/platform/watch_sync_bridge.dart';
import '../../../core/services/alert_evaluator.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/data_age.dart';
import '../../../core/ui/chain_logo.dart';
import '../../../core/ui/haptics.dart';
import '../../../core/ui/line_chart_painter.dart';
import '../../../core/ui/smart_refresh.dart';
import '../../../core/ui/token_row.dart';
import '../../../core/ui/value_formatters.dart';
import '../../asset_detail/asset_detail_screen.dart';
import '../../settings/settings_scope.dart';

class DashboardTab extends StatefulWidget {
  const DashboardTab({
    super.key,
    required this.profile,
    this.onNavigateToAssets,
    this.apiClient,
  });

  final ConnectionProfile profile;
  final VoidCallback? onNavigateToAssets;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<DashboardTab> createState() => _DashboardTabState();
}

class _DashboardTabState extends State<DashboardTab> {
  static const _cachedTotalKey = 'dashboard_cached_total';

  late final ApiClient _api;
  late Future<_DashboardPayload> _future;
  _ChartRange _selectedRange = _ChartRange.d1;
  bool _privacyMode = false;

  final SecureStore _secureStore = SecureStore();

  /// Cached total from secure storage — shown instantly before any API call.
  double? _cachedTotal;

  /// Instant data from Phase B — shown before full summary arrives.
  PortfolioInstant? _instant;

  /// In-memory caches to avoid re-fetching on range changes.
  PortfolioSummary? _cachedSummary;
  final Map<_ChartRange, PortfolioHistory> _historyCache = {};

  /// Incremented each load to discard stale history callbacks.
  int _loadGeneration = 0;

  /// When the most recent progressive load started — guards the
  /// lifecycle-resume refresh from re-fetching too aggressively.
  DateTime? _lastLoadStartedAt;

  void Function()? _disposeSummaryRevalidation;
  void Function()? _disposeHistoryRevalidation;

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
    _restoreCachedTotal();
    _future = _loadProgressive();
    // Refresh silently when the app returns to the foreground.
    AppRefreshSignal.instance.addListener(_onAppRefreshSignal);
    // Swap in fresh data when a background cache revalidation lands, so
    // stale-served content converges on live data without user input.
    _disposeSummaryRevalidation = CacheInterceptor.onRevalidated(
      '/api/mobile/portfolio/summary',
      _applyRevalidatedSummary,
    );
    _disposeHistoryRevalidation = CacheInterceptor.onRevalidated(
      '/api/mobile/chart/portfolio-history',
      _applyRevalidatedHistory,
    );
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    _disposeSummaryRevalidation?.call();
    _disposeHistoryRevalidation?.call();
    super.dispose();
  }

  /// Test hook: backdates the last-load timestamp so a resume signal is not
  /// suppressed by the min-interval guard.
  @visibleForTesting
  void debugBackdateLastLoad(Duration by) {
    _lastLoadStartedAt = DateTime.now().subtract(by);
  }

  /// Called when the app returns to the foreground. Re-runs the progressive
  /// load in the background: the FutureBuilder keeps showing the previous
  /// payload until the new one arrives, so the refresh is seamless.
  void _onAppRefreshSignal() {
    if (!mounted) return;
    final last = _lastLoadStartedAt;
    if (last != null &&
        DateTime.now().difference(last) < AppRefreshSignal.minRefreshInterval) {
      return;
    }
    setState(() {
      _future = _loadProgressive();
    });
  }

  /// Applies a freshly revalidated `/portfolio/summary` payload to the UI.
  void _applyRevalidatedSummary(dynamic freshData) {
    if (!mounted || freshData is! Map<String, dynamic>) return;
    final PortfolioSummary summary;
    try {
      summary = PortfolioSummary.fromJson(freshData);
    } catch (error, stack) {
      developer.log(
        'Ignoring malformed revalidated summary',
        name: 'DashboardTab',
        error: error,
        stackTrace: stack,
      );
      return;
    }
    _cachedSummary = summary;
    _persistTotal(summary.totalValueUsd);
    final history = _historyCache[_selectedRange];
    final historyIssue = history == null ? null : _historyIssue(history);
    setState(() {
      _future = Future.value(_DashboardPayload(
        summary: summary,
        history: historyIssue == null ? history : null,
        historyUnavailableMessage: historyIssue,
        historyLoading: history == null,
      ));
    });
  }

  /// Applies a freshly revalidated `/chart/portfolio-history` payload,
  /// updating the range cache and — if it matches the selected range and a
  /// summary is available — the visible chart.
  void _applyRevalidatedHistory(dynamic freshData) {
    if (!mounted || freshData is! Map<String, dynamic>) return;
    final PortfolioHistory history;
    try {
      history = PortfolioHistory.fromJson(freshData);
    } catch (error, stack) {
      developer.log(
        'Ignoring malformed revalidated history',
        name: 'DashboardTab',
        error: error,
        stackTrace: stack,
      );
      return;
    }
    _ChartRange? range;
    for (final candidate in _ChartRange.values) {
      if (candidate.apiValue == history.range) {
        range = candidate;
        break;
      }
    }
    if (range == null) return;
    _historyCache[range] = history;
    final summary = _cachedSummary;
    if (range != _selectedRange || summary == null) return;
    final historyIssue = _historyIssue(history);
    setState(() {
      _future = Future.value(_DashboardPayload(
        summary: summary,
        history: historyIssue == null ? history : null,
        historyUnavailableMessage: historyIssue,
      ));
    });
  }

  void _restoreCachedTotal() {
    _secureStore.read(_cachedTotalKey).then((saved) {
      if (saved != null && mounted) {
        final value = double.tryParse(saved);
        if (value != null && value > 0) {
          setState(() {
            _cachedTotal = value;
          });
        }
      }
    });
  }

  void _persistTotal(double total) {
    if (total <= 0) return;
    _secureStore.write(_cachedTotalKey, total.toString());
  }

  /// Stale-while-revalidate progressive loading:
  /// Phase A:  Cached total / instant data shown immediately (no spinner)
  /// Phase B:  /portfolio/instant fires → updates placeholder with holdings
  /// Phase C1: /portfolio/summary → full dashboard renders (chart still loading)
  /// Phase C2: /chart/history resolves → chart appears
  Future<_DashboardPayload> _loadProgressive({
    bool refresh = false,
    bool revalidate = false,
  }) async {
    _lastLoadStartedAt = DateTime.now();
    // Phase B: Fire instant request — used as immediate display data while
    // full summary loads, and persisted for next cold start. Only needed
    // when there is nothing to display yet: refreshes and resume reloads
    // already have content on screen, so an extra instant fetch per refresh
    // is pure overhead.
    if (!refresh && _cachedSummary == null && _instant == null) {
      _api.getPortfolioInstant(revalidate: revalidate).then((instant) {
        if (!mounted) return;
        _persistTotal(instant.totalUsd);
        // Update state so ProgressivePlaceholder re-renders with instant data
        // (shows holdings list instead of shimmer boxes).
        setState(() {
          _instant = instant;
        });
      }).catchError((e) {
        developer.log(
          'Instant load failed (non-blocking)',
          name: 'DashboardTab',
          error: e,
        );
      });
    }

    // Phase C: Start both requests, but only block on summary.
    // History resolves in the background and fills in the chart.
    final generation = ++_loadGeneration;
    try {
      final selectedRange = _selectedRange;
      final historyFuture = _api.getPortfolioHistory(
        range: selectedRange.apiValue,
        revalidate: revalidate,
      );

      final summary = await _api.getPortfolioSummary(
        refresh: refresh,
        revalidate: revalidate,
        includeSparklines: false,
      );
      _cachedSummary = summary;
      _persistTotal(summary.totalValueUsd);
      unawaited(_syncWatchSnapshot(
        summary,
        history7d:
            selectedRange == _ChartRange.d7 ? historyFuture : null,
      ));
      unawaited(_checkPortfolioAlerts(summary.totalValueUsd));

      // Resolve history in background — chart appears when ready
      unawaited(historyFuture.then((history) {
        _historyCache[selectedRange] = history;
        if (!mounted || _loadGeneration != generation) return;
        final historyIssue = _historyIssue(history);
        setState(() {
          _future = Future.value(_DashboardPayload(
            summary: _cachedSummary ?? summary,
            history: historyIssue == null ? history : null,
            historyUnavailableMessage: historyIssue,
          ));
        });
      }).catchError((Object error, StackTrace stack) {
        developer.log(
          'History fetch failed (range=${selectedRange.apiValue})',
          name: 'DashboardTab',
          error: error,
          stackTrace: stack,
        );
        if (!mounted || _loadGeneration != generation) return;
        setState(() {
          _future = Future.value(_DashboardPayload(
            summary: _cachedSummary ?? summary,
            historyUnavailableMessage: 'Chart temporarily unavailable.',
          ));
        });
      }));

      // Return immediately with summary — the chart from the previous load
      // (if any) stays visible until the new history resolves, instead of
      // collapsing to an empty box.
      final priorHistory = _historyCache[selectedRange];
      final priorIssue =
          priorHistory == null ? null : _historyIssue(priorHistory);
      return _DashboardPayload(
        summary: summary,
        history: priorIssue == null ? priorHistory : null,
        historyLoading: priorHistory == null || priorIssue != null,
      );
    } catch (error, stack) {
      developer.log(
        'Dashboard load failed (range=${_selectedRange.apiValue}, refresh=$refresh)',
        name: 'DashboardTab',
        error: error,
        stackTrace: stack,
      );
      // If we have instant data, return a partial payload instead of
      // crashing — but never for a hard refresh, whose failure must reach
      // _smartRefresh's error affordance instead of being papered over.
      if (!refresh && _instant != null) {
        return _DashboardPayload.fromInstant(_instant!);
      }
      rethrow;
    }
  }

  Future<void> _smartRefresh(bool hard) async {
    // Hard pull forces a backend recompute (refresh=true); soft pull is
    // network-first against the backend cache (revalidate — see
    // CacheInterceptor.revalidateExtra). Neither clears the in-memory
    // caches up front: the header, chart, and movers keep showing the
    // previous data during the round-trip (and after a failure) instead of
    // flashing empty, and the fetches bypass the client cache anyway.
    try {
      final data = await _loadProgressive(refresh: hard, revalidate: !hard);
      if (!mounted) return;
      setState(() {
        _future = Future.value(data);
      });
    } catch (error, stack) {
      developer.log(
        'Pull-to-refresh failed (hard=$hard)',
        name: 'DashboardTab',
        error: error,
        stackTrace: stack,
      );
      if (!mounted) return;
      // A hard pull is an explicit demand for live data — its failure must
      // be visible, not answered by the unchanged number (PRICE-1). Soft
      // pulls keep the silent cached fallback.
      if (hard) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content:
                Text("Refresh failed — couldn't reach the server. "
                    'Showing cached data.'),
          ),
        );
      }
    }
  }

  /// Test hook: drives a pull-to-refresh outcome without simulating the
  /// 140px overscroll gesture.
  @visibleForTesting
  Future<void> debugSmartRefresh({required bool hard}) => _smartRefresh(hard);

  Future<void> _changeRange(_ChartRange range) async {
    if (range == _selectedRange) return;
    _selectedRange = range;

    // Fast path: both summary and history for this range are cached
    final cachedHistory = _historyCache[range];
    if (_cachedSummary != null && cachedHistory != null) {
      final historyIssue = _historyIssue(cachedHistory);
      setState(() {
        _future = Future.value(_DashboardPayload(
          summary: _cachedSummary!,
          history: historyIssue == null ? cachedHistory : null,
          historyUnavailableMessage: historyIssue,
        ));
      });
      return;
    }

    // Medium path: summary cached but need to fetch history for new range
    if (_cachedSummary != null) {
      setState(() {
        _future = _fetchHistoryOnly(range);
      });
      return;
    }

    // Cold path: full fetch
    setState(() {
      _future = _loadProgressive();
    });
  }

  /// Fetch only chart history for [range], reusing [_cachedSummary].
  Future<_DashboardPayload> _fetchHistoryOnly(_ChartRange range) async {
    try {
      final history = await _api.getPortfolioHistory(range: range.apiValue);
      _historyCache[range] = history;

      final summary = _cachedSummary!;
      final historyIssue = _historyIssue(history);
      if (historyIssue != null) {
        return _DashboardPayload(
          summary: summary,
          historyUnavailableMessage: historyIssue,
        );
      }
      return _DashboardPayload(summary: summary, history: history);
    } catch (error, stack) {
      developer.log(
        'History fetch failed (range=${range.apiValue})',
        name: 'DashboardTab',
        error: error,
        stackTrace: stack,
      );
      // Return summary-only payload so UI doesn't crash
      return _DashboardPayload(
        summary: _cachedSummary!,
        historyUnavailableMessage: 'Chart temporarily unavailable.',
      );
    }
  }

  Future<void> _checkPortfolioAlerts(double totalValueUsd) async {
    try {
      final settings = SettingsScope.maybeOf(context);
      if (settings?.notificationsEnabled != true) return;
      await AlertEvaluator.checkAndNotifyPortfolio(totalValueUsd);
    } catch (e, st) {
      developer.log(
        'Portfolio alert check failed',
        name: 'DashboardTab',
        error: e,
        stackTrace: st,
      );
    }
  }

  Future<void> _syncWatchSnapshot(
    PortfolioSummary summary, {
    Future<PortfolioHistory>? history7d,
  }) async {
    try {
      // Reuse the dashboard's own in-flight 7d fetch when it's loading that
      // range anyway, instead of issuing a duplicate request per refresh.
      // Otherwise fetch normally — the client cache serves it without a
      // network round while fresh.
      final history = await (history7d ?? _api.getPortfolioHistory(range: '7d'));
      if (_historyIssue(history) != null) return;
      // Top-of-market list for watch complication tracking. Rides this
      // existing sync trigger — the client cache (15 min TTL) makes repeat
      // calls free, and a failure just degrades the watch gallery.
      final marketAssets = await _api.getTopAssets();
      await WatchSyncBridge.pushPortfolioSnapshot(
        summary: summary,
        history7d: history,
        marketAssets: marketAssets,
      );
    } catch (error, stack) {
      developer.log(
        'Watch sync update skipped',
        name: 'DashboardTab',
        error: error,
        stackTrace: stack,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_DashboardPayload>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          // Range switch: previous payload exists — fall through to render it
          // so the old chart stays visible (no jutter)
          if (snapshot.hasData) {
            // fall through to normal rendering below
          } else {
            // Stale-while-revalidate: show progressive placeholder with
            // cached total and/or instant data instead of a bare spinner.
            // This ensures the user sees their portfolio value immediately
            // on app open, even before the full summary loads.
            if (_cachedTotal != null || _instant != null) {
              return _ProgressivePlaceholder(
                cachedTotal: _cachedTotal,
                instant: _instant,
                privacyMode: _privacyMode,
                profile: widget.profile,
                onTogglePrivacy: () {
                  setState(() => _privacyMode = !_privacyMode);
                },
              );
            }
            return const Center(child: CircularProgressIndicator());
          }
        }

        if (snapshot.hasError) {
          // Even on error, show cached data if available rather than an
          // error screen. Only show error if we have nothing to display.
          if (_cachedSummary != null || _instant != null || _cachedTotal != null) {
            if (_cachedSummary != null) {
              // We have a full summary from a previous load — show it
              final payload = _DashboardPayload(
                summary: _cachedSummary!,
                historyUnavailableMessage: 'Unable to refresh. Showing cached data.',
              );
              // Fall through to normal rendering (handled below)
              return _buildDashboardContent(payload);
            }
            return _ProgressivePlaceholder(
              cachedTotal: _cachedTotal,
              instant: _instant,
              privacyMode: _privacyMode,
              profile: widget.profile,
              onTogglePrivacy: () {
                setState(() => _privacyMode = !_privacyMode);
              },
            );
          }
          return _ErrorState(
            message: _friendlyError(snapshot.error),
            onRetry: () {
              setState(() {
                _future = _loadProgressive();
              });
            },
          );
        }

        final payload = snapshot.data!;
        return _buildDashboardContent(payload);
      },
    );
  }

  /// Renders the full dashboard content from a [_DashboardPayload].
  ///
  /// Extracted as a method so it can be called both from the normal
  /// FutureBuilder path and from the error-recovery path when cached
  /// data is available.
  Widget _buildDashboardContent(_DashboardPayload payload) {
    final summary = payload.summary;
    final history = payload.history;

    final changeUsd = history?.summary.changeUsd ?? 0;
    final changePercent = history?.summary.changePercent ?? 0;

    return SmartRefreshIndicator(
      onRefresh: _smartRefresh,
      child: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFF0B0F1A),
              Color(0xFF0D1117),
              Color(0xFF090D14),
            ],
          ),
        ),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
          children: [
            _buildPrivacyToggle(context),
            const SizedBox(height: 8),
            _PortfolioHeader(
              summary: summary,
              history: _historyCache[_ChartRange.d1] ?? history,
              privacyMode: _privacyMode,
            ),
            const SizedBox(height: 20),
            _PortfolioChart(
              history: history,
              historyUnavailableMessage:
                  payload.historyUnavailableMessage,
              historyLoading: payload.historyLoading,
              selectedRange: _selectedRange,
              onRangeChanged: _changeRange,
              changeUsd: changeUsd,
              changePercent: changePercent,
              privacyMode: _privacyMode,
              onRetry: () {
                setState(() {
                  _future = _loadProgressive();
                });
              },
            ),
            const SizedBox(height: 28),
            _TopMoversSection(
              holdings: summary.topHoldings.isNotEmpty
                  ? summary.topHoldings
                  : summary.blockchains,
              privacyMode: _privacyMode,
              profile: widget.profile,
            ),
            const SizedBox(height: 16),
            _AllHoldingsSection(
              holdings: summary.topHoldings.isNotEmpty
                  ? summary.topHoldings
                  : summary.blockchains,
              privacyMode: _privacyMode,
              profile: widget.profile,
              onViewAll: widget.onNavigateToAssets,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPrivacyToggle(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: GestureDetector(
        onTap: () {
          Haptics.light();
          setState(() {
            _privacyMode = !_privacyMode;
          });
        },
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(
            _privacyMode ? Icons.visibility_off : Icons.visibility,
            size: 20,
            color: Colors.white.withValues(alpha: 0.5),
          ),
        ),
      ),
    );
  }

  String _friendlyError(Object? error) {
    final message = error?.toString() ?? 'Unable to load dashboard data.';
    return message.replaceFirst('Exception: ', '');
  }

  String? _historyIssue(PortfolioHistory history) {
    if (history.error != null && history.error!.trim().isNotEmpty) {
      return history.error;
    }
    if (history.dataPoints == 0 || history.chartData.isEmpty) {
      return 'No chart data available for ${history.range.toUpperCase()} yet.';
    }

    final validValues = history.chartData
        .map((p) => p.totalValueUsd)
        .where((v) => v.isFinite)
        .toList();
    final distinctTimes = history.chartData
        .map((p) => p.timestamp.millisecondsSinceEpoch)
        .toSet();

    if (validValues.length < 2 || distinctTimes.length < 2) {
      return 'Not enough chart history to render ${history.range.toUpperCase()} yet.';
    }
    return null;
  }
}

// ---------------------------------------------------------------------------
// Progressive placeholder — shown while full summary is loading
// ---------------------------------------------------------------------------

class _ProgressivePlaceholder extends StatelessWidget {
  const _ProgressivePlaceholder({
    required this.cachedTotal,
    required this.instant,
    required this.privacyMode,
    required this.profile,
    required this.onTogglePrivacy,
  });

  final double? cachedTotal;
  final PortfolioInstant? instant;
  final bool privacyMode;
  final ConnectionProfile profile;
  final VoidCallback onTogglePrivacy;

  @override
  Widget build(BuildContext context) {
    final total = instant?.totalUsd ?? cachedTotal ?? 0;
    final holdings = instant?.topHoldings ?? const [];

    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF0B0F1A),
            Color(0xFF0D1117),
            Color(0xFF090D14),
          ],
        ),
      ),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
        children: [
          // Privacy toggle
          Align(
            alignment: Alignment.centerRight,
            child: GestureDetector(
              onTap: onTogglePrivacy,
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Icon(
                  privacyMode ? Icons.visibility_off : Icons.visibility,
                  size: 20,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          // Portfolio value
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Portfolio value',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.white.withValues(alpha: 0.55),
                  letterSpacing: 0.3,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                privacyMode ? r'$••••••' : ValueFormatters.usd(total),
                style: const TextStyle(
                  fontSize: 36,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                  letterSpacing: -0.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          // Chart shimmer placeholder
          _ShimmerBox(height: 180),
          const SizedBox(height: 28),
          // Holdings from instant data (or shimmer if not yet loaded)
          if (holdings.isNotEmpty) ...[
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(20),
                color: const Color(0xFF141922),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.06),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'All Holdings',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 14),
                  for (var i = 0; i < holdings.take(5).length; i++) ...[
                    _InstantHoldingRow(
                      holding: holdings[i],
                      privacyMode: privacyMode,
                    ),
                    if (i < holdings.take(5).length - 1)
                      Divider(
                        height: 1,
                        color: Colors.white.withValues(alpha: 0.06),
                      ),
                  ],
                ],
              ),
            ),
          ] else ...[
            _ShimmerBox(height: 200),
          ],
        ],
      ),
    );
  }
}

class _InstantHoldingRow extends StatelessWidget {
  const _InstantHoldingRow({
    required this.holding,
    required this.privacyMode,
  });

  final InstantHolding holding;
  final bool privacyMode;

  @override
  Widget build(BuildContext context) {
    final symbol = holding.symbol.isEmpty
        ? '?'
        : holding.symbol.toUpperCase();
    final hasPriceChange = holding.priceChange24h != 0;
    final priceChangePositive = holding.priceChange24h >= 0;
    final priceChangeColor = priceChangePositive
        ? const Color(0xFF4ADE80)
        : const Color(0xFFFF6B6B);
    final dimWhite = Colors.white.withValues(alpha: 0.45);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          _buildLogo(symbol),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  symbol,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  privacyMode
                      ? symbol
                      : '${ValueFormatters.tokenAmount(holding.quantity)} $symbol',
                  style: TextStyle(fontSize: 13, color: dimWhite),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    privacyMode
                        ? r'$••••'
                        : ValueFormatters.usd(holding.valueUsd),
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    privacyMode
                        ? '••%'
                        : ValueFormatters.percent(holding.allocationPct),
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withValues(alpha: 0.35),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 3),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    privacyMode
                        ? r'$••••'
                        : ValueFormatters.usd(holding.priceUsd),
                    style: TextStyle(fontSize: 12, color: dimWhite),
                  ),
                  if (hasPriceChange) ...[
                    const SizedBox(width: 4),
                    Icon(
                      priceChangePositive
                          ? Icons.north_east
                          : Icons.south_east,
                      size: 10,
                      color: priceChangeColor,
                    ),
                    const SizedBox(width: 1),
                    Text(
                      ValueFormatters.percent(holding.priceChange24h.abs()),
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: priceChangeColor,
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLogo(String ticker) {
    if (ChainLogo.hasLogo(ticker)) {
      return ChainLogo(symbol: ticker, size: 40);
    }
    if (holding.imageUrl.isNotEmpty) {
      final letter = ticker.isNotEmpty ? ticker[0] : '?';
      return ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: CachedNetworkImage(
          imageUrl: holding.imageUrl,
          width: 40,
          height: 40,
          fit: BoxFit.cover,
          placeholder: (_, __) => LetterFallback(letter: letter, size: 40),
          errorWidget: (_, __, ___) => LetterFallback(letter: letter, size: 40),
        ),
      );
    }
    return ChainLogo(symbol: ticker, size: 40);
  }
}

class _ShimmerBox extends StatelessWidget {
  const _ShimmerBox({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: Colors.white.withValues(alpha: 0.04),
      ),
      child: const Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      ),
    );
  }
}

class _DashboardPayload {
  _DashboardPayload({
    required this.summary,
    this.history,
    this.historyUnavailableMessage,
    this.instant,
    this.partialLoad = false,
    this.historyLoading = false,
  });

  /// Creates a partial payload from instant data when full summary timed out.
  factory _DashboardPayload.fromInstant(PortfolioInstant instant) {
    return _DashboardPayload(
      summary: PortfolioSummary(
        totalValueUsd: instant.totalUsd,
        totalNative: const {},
        breakdown: PortfolioBreakdown(
          selfCustody: BreakdownItem(valueUsd: 0, percentage: 0),
          exchanges: BreakdownItem(valueUsd: 0, percentage: 0),
          nfts: BreakdownItem(valueUsd: 0, percentage: 0),
          staking: BreakdownItem(valueUsd: 0, percentage: 0),
          defi: BreakdownItem(valueUsd: 0, percentage: 0),
          trackedTokens: BreakdownItem(valueUsd: 0, percentage: 0),
          customTokens: BreakdownItem(valueUsd: 0, percentage: 0),
        ),
        blockchains: const [],
        topHoldings: instant.topHoldings
            .map((h) => BlockchainHolding(
                  name: h.name,
                  symbol: h.symbol,
                  valueUsd: h.valueUsd,
                  nativeAmount: h.quantity,
                  nativePriceUsd: h.priceUsd,
                  walletCount: 0,
                  percentage: h.allocationPct,
                  priceChange24h: h.priceChange24h,
                  imageUrl: h.imageUrl,
                ))
            .toList(),
        fromCache: false,
      ),
      instant: instant,
      partialLoad: true,
      historyUnavailableMessage: 'Chart loading...',
    );
  }

  final PortfolioSummary summary;
  final PortfolioHistory? history;
  final String? historyUnavailableMessage;
  final PortfolioInstant? instant;
  final bool partialLoad;
  final bool historyLoading;
}

enum _ChartRange {
  d1('1D', '24h'),
  d7('7D', '7d'),
  m1('1M', '4w'),
  m3('3M', '3m'),
  y1('1Y', '1y'),
  all('ALL', 'all');

  const _ChartRange(this.label, this.apiValue);

  final String label;
  final String apiValue;
}

// ---------------------------------------------------------------------------
// Portfolio value header (matches reference: label, big value, two metrics)
// ---------------------------------------------------------------------------

class _PortfolioHeader extends StatelessWidget {
  const _PortfolioHeader({
    required this.summary,
    required this.history,
    required this.privacyMode,
  });

  final PortfolioSummary summary;
  final PortfolioHistory? history;
  final bool privacyMode;

  @override
  Widget build(BuildContext context) {
    final mainValue = summary.totalValueUsd;

    final hourlyChange = _computeHourlyChange(history);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Portfolio value',
          style: TextStyle(
            fontSize: 14,
            color: Colors.white.withValues(alpha: 0.55),
            letterSpacing: 0.3,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          privacyMode ? r'$••••••' : ValueFormatters.usd(mainValue),
          style: const TextStyle(
            fontSize: 36,
            fontWeight: FontWeight.w700,
            color: Colors.white,
            letterSpacing: -0.5,
          ),
        ),
        if (hourlyChange != null && !privacyMode) ...[
          const SizedBox(height: 6),
          _HourlyChangeIndicator(changePercent: hourlyChange),
        ],
        // Silent staleness was the PRICE-1 failure mode: a frozen total was
        // indistinguishable from a live one. Older than 5 min → say so.
        if (DataAgeCaption.isStale(summary.lastUpdated, DateTime.now())) ...[
          const SizedBox(height: 4),
          DataAgeCaption(lastUpdated: summary.lastUpdated),
        ],
      ],
    );
  }

  /// Finds the chart point nearest to 1 hour ago and computes % change vs
  /// the latest point. Returns null if the nearest point is >30min away
  /// from the 1-hour mark (sparse data) or if history is unavailable.
  static double? _computeHourlyChange(PortfolioHistory? history) {
    if (history == null || history.chartData.length < 2) return null;

    final points = history.chartData;
    final latest = points.last;
    final oneHourAgo = latest.timestamp.subtract(const Duration(hours: 1));

    // Find nearest point to 1hr ago
    PortfolioHistoryPoint? nearest;
    Duration? nearestDiff;
    for (final point in points) {
      final diff = point.timestamp.difference(oneHourAgo).abs();
      if (nearestDiff == null || diff < nearestDiff) {
        nearest = point;
        nearestDiff = diff;
      }
    }

    if (nearest == null || nearestDiff == null) return null;
    // Skip if nearest point is >30min away from the 1hr mark
    if (nearestDiff.inMinutes > 30) return null;
    if (nearest.totalValueUsd <= 0 || !nearest.totalValueUsd.isFinite) {
      return null;
    }

    final change =
        (latest.totalValueUsd - nearest.totalValueUsd) /
        nearest.totalValueUsd *
        100;
    return change.isFinite ? change : null;
  }
}

class _HourlyChangeIndicator extends StatelessWidget {
  const _HourlyChangeIndicator({required this.changePercent});

  final double changePercent;

  @override
  Widget build(BuildContext context) {
    final isPositive = changePercent >= 0;
    final color =
        isPositive ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B);
    final arrow = isPositive ? '\u2197' : '\u2198'; // ↗ or ↘

    return Text(
      '$arrow ${isPositive ? "+" : ""}${changePercent.toStringAsFixed(2)}% 1h',
      style: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w500,
        color: color,
      ),
    );
  }
}

class _MetricColumn extends StatelessWidget {
  const _MetricColumn({
    required this.label,
    required this.value,
    required this.valueColor,
    required this.isPositive,
  });

  final String label;
  final String value;
  final Color valueColor;
  final bool isPositive;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 12,
            color: Colors.white.withValues(alpha: 0.45),
            decoration: TextDecoration.underline,
            decorationColor: Colors.white.withValues(alpha: 0.25),
            decorationStyle: TextDecorationStyle.dashed,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isPositive ? Icons.north_east : Icons.south_east,
              size: 14,
              color: valueColor,
            ),
            const SizedBox(width: 2),
            Text(
              value,
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: valueColor,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Chart section (clean purple line, range pills underneath)
// ---------------------------------------------------------------------------

class _PortfolioChart extends StatefulWidget {
  const _PortfolioChart({
    required this.history,
    required this.historyUnavailableMessage,
    required this.historyLoading,
    required this.selectedRange,
    required this.onRangeChanged,
    required this.onRetry,
    required this.changeUsd,
    required this.changePercent,
    required this.privacyMode,
  });

  final PortfolioHistory? history;
  final String? historyUnavailableMessage;
  final bool historyLoading;
  final _ChartRange selectedRange;
  final ValueChanged<_ChartRange> onRangeChanged;
  final VoidCallback onRetry;
  final double changeUsd;
  final double changePercent;
  final bool privacyMode;

  @override
  State<_PortfolioChart> createState() => _PortfolioChartState();
}

class _PortfolioChartState extends State<_PortfolioChart> {
  int? _activeIndex;

  /// Memoized projections of `widget.history.chartData`, rebuilt only when
  /// the history object changes — not on every scrub/selection rebuild.
  /// Stable list instances also let the painter's value-equality
  /// shouldRepaint short-circuit on identity.
  PortfolioHistory? _pointsSource;
  List<PortfolioHistoryPoint> _chartPoints = const [];
  List<double> _chartValues = const [];

  void _syncChartPoints() {
    if (identical(_pointsSource, widget.history)) return;
    _pointsSource = widget.history;
    _chartPoints = widget.history?.chartData
            .where((point) => point.totalValueUsd.isFinite)
            .toList(growable: false) ??
        const <PortfolioHistoryPoint>[];
    _chartValues = _chartPoints
        .map((point) => point.totalValueUsd)
        .toList(growable: false);
  }

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    _syncChartPoints();
    final chartPoints = _chartPoints;
    final hasChart = chartPoints.length >= 2;
    final activeIndex = hasChart
        ? (_activeIndex ?? (chartPoints.length - 1)).clamp(
            0,
            chartPoints.length - 1,
          )
        : 0;
    final isTracking = _activeIndex != null && hasChart;
    final selectedPoint = hasChart ? chartPoints[activeIndex] : null;

    final trackingValueColor = Color.lerp(primary, Colors.white, 0.4)!;

    return Column(
      children: [
        if (hasChart) ...[
          // Price + date overlay (visible when tracking)
          AnimatedOpacity(
            opacity: isTracking ? 1.0 : 0.0,
            duration: const Duration(milliseconds: 150),
            child: selectedPoint != null
                ? Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Column(
                      children: [
                        Text(
                          ValueFormatters.usd(selectedPoint.totalValueUsd),
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: trackingValueColor,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          ValueFormatters.timestamp(
                            selectedPoint.timestamp.toIso8601String(),
                          ),
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.white.withValues(alpha: 0.5),
                          ),
                        ),
                      ],
                    ),
                  )
                : const SizedBox.shrink(),
          ),
          // Edge-to-edge chart: use LayoutBuilder + OverflowBox to break out
          // of the parent ListView's 20px horizontal padding
          SizedBox(
            height: 180,
            child: LayoutBuilder(
              builder: (context, constraints) {
                return OverflowBox(
                  maxWidth: constraints.maxWidth + 40, // +20px each side
                  child: InteractiveLineChart(
                    points: _chartValues,
                    highlightedIndex: activeIndex,
                    lineColor: primary,
                    glowColor: primary.withValues(alpha: 0.5),
                    fillColorTop: primary.withValues(alpha: 0.32),
                    fillColorBottom: primary.withValues(alpha: 0.04),
                    markerColor: primary.withValues(alpha: 0.8),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    showBorder: false,
                    onPointSelected: (index) {
                      final safeIndex = index.clamp(0, chartPoints.length - 1);
                      if (_activeIndex == safeIndex) return;
                      Haptics.light();
                      setState(() {
                        _activeIndex = safeIndex;
                      });
                    },
                    onInteractionEnd: () {
                      if (_activeIndex == null) return;
                      setState(() {
                        _activeIndex = null;
                      });
                    },
                  ),
                );
              },
            ),
          ),
        ] else if (widget.historyLoading)
          const SizedBox(height: 180)
        else
          _ChartUnavailable(
            message: widget.historyUnavailableMessage ??
                'History is temporarily unavailable.',
            onRetry: widget.onRetry,
          ),
        if (hasChart) ...[
          const SizedBox(height: 12),
          _BalanceChangeRow(
            rangeLabel: widget.selectedRange.label,
            changeUsd: widget.changeUsd,
            changePercent: widget.changePercent,
            privacyMode: widget.privacyMode,
          ),
        ],
        const SizedBox(height: 14),
        _RangeSelector(
          selected: widget.selectedRange,
          onChanged: widget.onRangeChanged,
        ),
      ],
    );
  }
}

class _RangeSelector extends StatelessWidget {
  const _RangeSelector({required this.selected, required this.onChanged});

  final _ChartRange selected;
  final ValueChanged<_ChartRange> onChanged;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (final range in _ChartRange.values) ...[
            GestureDetector(
              onTap: () {
                Haptics.light();
                onChanged(range);
              },
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  color: selected == range
                      ? Colors.white.withValues(alpha: 0.12)
                      : Colors.transparent,
                ),
                child: Text(
                  range.label,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight:
                        selected == range ? FontWeight.w600 : FontWeight.w400,
                    color: selected == range
                        ? Colors.white
                        : Colors.white.withValues(alpha: 0.45),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _BalanceChangeRow extends StatelessWidget {
  const _BalanceChangeRow({
    required this.rangeLabel,
    required this.changeUsd,
    required this.changePercent,
    required this.privacyMode,
  });

  final String rangeLabel;
  final double changeUsd;
  final double changePercent;
  final bool privacyMode;

  @override
  Widget build(BuildContext context) {
    final isPositive = changeUsd >= 0;
    final changeColor =
        isPositive ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B);

    return Row(
      children: [
        _MetricColumn(
          label: '$rangeLabel Balance change',
          value: privacyMode
              ? r'$•••'
              : '${isPositive ? "+" : ""}${ValueFormatters.usd(changeUsd)}',
          valueColor: changeColor,
          isPositive: isPositive,
        ),
        const SizedBox(width: 32),
        _MetricColumn(
          label: '$rangeLabel Change',
          value: privacyMode
              ? '•••%'
              : '${isPositive ? "+" : ""}${changePercent.toStringAsFixed(2)}%',
          valueColor: changeColor,
          isPositive: isPositive,
        ),
      ],
    );
  }
}

class _ChartUnavailable extends StatelessWidget {
  const _ChartUnavailable({
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 180,
      width: double.infinity,
      alignment: Alignment.center,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.5),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 10),
          TextButton(
            onPressed: onRetry,
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Top Movers section (biggest 24h price changes, up or down)
// ---------------------------------------------------------------------------

class _TopMoversSection extends StatelessWidget {
  const _TopMoversSection({
    required this.holdings,
    required this.privacyMode,
    required this.profile,
  });

  final List<BlockchainHolding> holdings;
  final bool privacyMode;
  final ConnectionProfile profile;

  @override
  Widget build(BuildContext context) {
    if (holdings.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(12),
        child: Text(
          'No holdings available yet.',
          style: TextStyle(color: Colors.white.withValues(alpha: 0.5)),
        ),
      );
    }

    final movers = holdings
        .where((h) => h.priceChange24h != 0)
        .toList()
      ..sort(
          (a, b) => b.priceChange24h.abs().compareTo(a.priceChange24h.abs()));
    final visible = movers.take(5).toList();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: const Color(0xFF141922),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Top Movers',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 14),
          if (visible.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'No price movement data available',
                style: TextStyle(
                  fontSize: 13,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ),
            )
          else
            for (var i = 0; i < visible.length; i++) ...[
              _HoldingRow(
                holding: visible[i],
                privacyMode: privacyMode,
                profile: profile,
              ),
              if (i < visible.length - 1)
                Divider(
                  height: 1,
                  color: Colors.white.withValues(alpha: 0.06),
                ),
            ],
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// All Holdings section (top 5 by value, with "View all" link)
// ---------------------------------------------------------------------------

class _AllHoldingsSection extends StatelessWidget {
  const _AllHoldingsSection({
    required this.holdings,
    required this.privacyMode,
    required this.profile,
    this.onViewAll,
  });

  final List<BlockchainHolding> holdings;
  final bool privacyMode;
  final ConnectionProfile profile;
  final VoidCallback? onViewAll;

  @override
  Widget build(BuildContext context) {
    if (holdings.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(12),
        child: Text(
          'No holdings available yet.',
          style: TextStyle(color: Colors.white.withValues(alpha: 0.5)),
        ),
      );
    }

    final sorted = [...holdings]
      ..sort((a, b) => b.valueUsd.compareTo(a.valueUsd));
    final visible = sorted.take(5).toList();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: const Color(0xFF141922),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'All Holdings',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 14),
          for (var i = 0; i < visible.length; i++) ...[
            _HoldingRow(
              holding: visible[i],
              privacyMode: privacyMode,
              profile: profile,
            ),
            if (i < visible.length - 1)
              Divider(
                height: 1,
                color: Colors.white.withValues(alpha: 0.06),
              ),
          ],
          const SizedBox(height: 14),
          Center(
            child: GestureDetector(
              onTap: () {
                Haptics.light();
                onViewAll?.call();
              },
              child: Text(
                'View all holdings \u2192',
                style: TextStyle(
                  fontSize: 13,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HoldingRow extends StatelessWidget {
  const _HoldingRow({
    required this.holding,
    required this.privacyMode,
    required this.profile,
  });

  final BlockchainHolding holding;
  final bool privacyMode;
  final ConnectionProfile profile;

  @override
  Widget build(BuildContext context) {
    final symbol =
        holding.symbol.isEmpty ? '?' : holding.symbol.toUpperCase();
    final displayName = symbol;
    final hasPriceChange = holding.priceChange24h != 0;
    final priceChangePositive = holding.priceChange24h >= 0;
    final priceChangeColor = priceChangePositive
        ? const Color(0xFF4ADE80)
        : const Color(0xFFFF6B6B);
    final dimWhite = Colors.white.withValues(alpha: 0.45);

    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () {
        Haptics.light();
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => AssetDetailScreen(
              profile: profile,
              symbol: holding.symbol,
              name: holding.name,
              holdingValueUsd: holding.valueUsd,
              holdingPercentage: holding.percentage,
              nativeAmount: holding.nativeAmount,
            ),
          ),
        );
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(
          children: [
            _buildLogo(symbol),
            const SizedBox(width: 12),
            // Name + Token amount
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    displayName,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    privacyMode
                        ? symbol
                        : '${ValueFormatters.tokenAmount(holding.nativeAmount)} $symbol',
                    style: TextStyle(fontSize: 13, color: dimWhite),
                  ),
                ],
              ),
            ),
            // Value, price, portfolio %
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                // Total value + portfolio %
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      privacyMode
                          ? r'$••••'
                          : ValueFormatters.usd(holding.valueUsd),
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      privacyMode
                          ? '••%'
                          : ValueFormatters.percent(holding.percentage),
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.white.withValues(alpha: 0.35),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                // Current price + 24h change
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      privacyMode
                          ? r'$••••'
                          : ValueFormatters.usd(holding.nativePriceUsd),
                      style: TextStyle(fontSize: 12, color: dimWhite),
                    ),
                    if (hasPriceChange) ...[
                      const SizedBox(width: 4),
                      Icon(
                        priceChangePositive
                            ? Icons.north_east
                            : Icons.south_east,
                        size: 10,
                        color: priceChangeColor,
                      ),
                      const SizedBox(width: 1),
                      Text(
                        ValueFormatters.percent(
                            holding.priceChange24h.abs()),
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: priceChangeColor,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLogo(String ticker) {
    // Prefer ChainLogo for known major coins (reliable cryptologos.cc URLs)
    if (ChainLogo.hasLogo(ticker)) {
      return ChainLogo(symbol: ticker, size: 40);
    }
    // Prefer CoinGecko CDN image (watchImageUrl), fall back to LogoKit (imageUrl)
    final logoUrl = holding.watchImageUrl.isNotEmpty
        ? holding.watchImageUrl
        : holding.imageUrl;
    if (logoUrl.isNotEmpty) {
      final letter = ticker.isNotEmpty ? ticker[0] : '?';
      return ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: CachedNetworkImage(
          imageUrl: logoUrl,
          width: 40,
          height: 40,
          fit: BoxFit.cover,
          placeholder: (_, __) =>
              LetterFallback(letter: letter, size: 40),
          errorWidget: (_, __, ___) =>
              LetterFallback(letter: letter, size: 40),
        ),
      );
    }
    return ChainLogo(symbol: ticker, size: 40);
  }
}

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Color(0xFFFF6B6B)),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: onRetry,
              child: const Text('Retry'),
            )
          ],
        ),
      ),
    );
  }
}

