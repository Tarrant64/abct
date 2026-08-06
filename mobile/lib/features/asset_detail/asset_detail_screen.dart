import 'dart:developer' as developer;
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/models/alert_config.dart';
import '../../core/models/asset_detail.dart';
import '../../core/models/connection_profile.dart';
import '../../core/models/json_utils.dart';
import '../../core/network/api_client.dart';
import '../../core/services/alert_evaluator.dart';
import '../../core/storage/alert_repository.dart';
import '../../core/ui/chain_logo.dart';
import '../../core/ui/line_chart_painter.dart';
import '../../core/ui/value_formatters.dart';
import '../settings/settings_scope.dart';

enum _PriceRange {
  d1('1D', '1d'),
  d7('7D', '7d'),
  d30('30D', '30d'),
  d90('90D', '90d'),
  y1('1Y', '1y');

  const _PriceRange(this.label, this.apiValue);
  final String label;
  final String apiValue;
}

class AssetDetailScreen extends StatefulWidget {
  const AssetDetailScreen({
    super.key,
    required this.profile,
    required this.symbol,
    required this.name,
    required this.holdingValueUsd,
    required this.holdingPercentage,
    this.nativeAmount = 0,
  });

  final ConnectionProfile profile;
  final String symbol;
  final String name;
  final double holdingValueUsd;
  final double holdingPercentage;
  final double nativeAmount;

  @override
  State<AssetDetailScreen> createState() => _AssetDetailScreenState();
}

class _AssetDetailScreenState extends State<AssetDetailScreen> {
  late final ApiClient _api;
  final _alertRepo = AlertRepository();

  late Future<_ChartPayload?> _chartFuture;
  late Future<AssetMarketData?> _marketFuture;
  late Future<WalletBreakdownResponse?> _breakdownFuture;
  String? _breakdownDebug; // temporary debug info

  // In-memory caches for stale-while-revalidate rendering.
  // Prevents spinners when switching chart ranges or revisiting the screen.
  _ChartPayload? _lastChart;
  AssetMarketData? _lastMarket;
  WalletBreakdownResponse? _lastBreakdown;
  final Map<_PriceRange, _ChartPayload?> _chartCache = {};

  _PriceRange _range = _PriceRange.d7;
  int? _activeIndex;
  int _alertCount = 0;

  @override
  void initState() {
    super.initState();
    _api = ApiClient.shared(widget.profile);
    _chartFuture = _loadChart();
    _marketFuture = _loadMarketData();
    _breakdownFuture = _loadBreakdown();
    _loadAlertCount();
  }

  Future<void> _loadAlertCount() async {
    final alerts = await _alertRepo.loadAlertsForSymbol(widget.symbol);
    if (!mounted) return;
    setState(() => _alertCount = alerts.length);
  }

  Future<_ChartPayload?> _loadChart() async {
    try {
      final json = await _api.getAssetPriceChart(
        symbol: widget.symbol,
        range: _range.apiValue,
      );
      final payload = _ChartPayload.fromJson(json);

      // Cache the result for instant rendering on range switches
      _chartCache[_range] = payload;
      _lastChart = payload;

      // Foreground alert check
      if (payload.closePrices.isNotEmpty) {
        final currentPrice = payload.closePrices.last;
        final settings = SettingsScope.maybeOf(context);
        if (settings?.notificationsEnabled == true) {
          AlertEvaluator.checkAndNotifyAssetPrice(
            symbol: widget.symbol,
            currentPrice: currentPrice,
          );
        }
      }

      return payload;
    } catch (e, st) {
      developer.log(
        'Asset chart load failed for ${widget.symbol}',
        name: 'AssetDetail',
        error: e,
        stackTrace: st,
      );
      return null;
    }
  }

  Future<AssetMarketData?> _loadMarketData() async {
    try {
      return await _api.getAssetMarketData(symbol: widget.symbol);
    } catch (e, st) {
      developer.log(
        'Asset market data load failed for ${widget.symbol}',
        name: 'AssetDetail',
        error: e,
        stackTrace: st,
      );
      return null;
    }
  }

  Future<WalletBreakdownResponse?> _loadBreakdown() async {
    try {
      final encoded = Uri.encodeComponent(widget.symbol.toUpperCase());
      final dio = await _api.create();
      final resp = await dio.get('/api/mobile/asset/$encoded/wallet-breakdown');
      final json = resp.data as Map<String, dynamic>? ?? {};
      // Capture debug info if present
      if (json.containsKey('_debug')) {
        _breakdownDebug = json['_debug'].toString();
        developer.log('Breakdown debug: $_breakdownDebug', name: 'AssetDetail');
      }
      return WalletBreakdownResponse.fromJson(json);
    } catch (e, st) {
      _breakdownDebug = 'ERROR: $e';
      developer.log(
        'Wallet breakdown load failed for ${widget.symbol}',
        name: 'AssetDetail',
        error: e,
        stackTrace: st,
      );
      return null;
    }
  }

  void _showAlertSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _AlertBottomSheet(
        symbol: widget.symbol,
        name: widget.name,
        alertRepo: _alertRepo,
        onChanged: _loadAlertCount,
      ),
    );
  }

  void _changeRange(_PriceRange range) {
    if (range == _range) return;
    setState(() {
      _range = range;
      _activeIndex = null;
      // Use cached chart data if available for instant rendering
      final cached = _chartCache[range];
      if (cached != null) {
        _lastChart = cached;
        _chartFuture = Future.value(cached);
      } else {
        _chartFuture = _loadChart();
      }
    });
  }

  static const _months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  String _formatDate(DateTime dt) => '${_months[dt.month - 1]} ${dt.day}';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final symbol = widget.symbol.toUpperCase();

    return Scaffold(
      appBar: AppBar(
        title: Text('$symbol \u2013 ${ValueFormatters.titleCase(widget.name)}'),
        actions: [
          Stack(
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_outlined),
                tooltip: 'Price Alerts',
                onPressed: () => _showAlertSheet(context),
              ),
              if (_alertCount > 0)
                Positioned(
                  right: 8,
                  top: 8,
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── 1. Price + Chart (top) ──
          _buildChartSection(theme, symbol),
          const SizedBox(height: 20),

          // ── 2. Market Data ──
          _buildMarketDataSection(theme),
          const SizedBox(height: 20),

          // ── 3. Your Holding ──
          _buildHoldingCard(theme, symbol),
          const SizedBox(height: 20),

          // ── 4. Wallet Breakdown ──
          _buildWalletBreakdownSection(theme, symbol),
        ],
      ),
    );
  }

  // ────────────────────────────────────────────────────────────────────────
  // Section 1: Price + Chart
  // ────────────────────────────────────────────────────────────────────────

  Widget _buildChartSection(ThemeData theme, String symbol) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Range selector
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Wrap(
            spacing: 6,
            children: [
              for (final r in _PriceRange.values)
                ChoiceChip(
                  label: Text(r.label),
                  selected: _range == r,
                  onSelected: (_) => _changeRange(r),
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        // Price chart
        FutureBuilder<_ChartPayload?>(
          future: _chartFuture,
          builder: (context, snapshot) {
            // Stale-while-revalidate: show cached chart while loading
            final payload = snapshot.data ?? _lastChart;

            if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
              _lastChart = snapshot.data;
            }

            if (payload == null && snapshot.connectionState == ConnectionState.waiting) {
              return const SizedBox(
                height: 240,
                child: Center(child: CircularProgressIndicator()),
              );
            }
            if (payload == null || payload.closePrices.length < 2) {
              return SizedBox(
                height: 240,
                child: Center(
                  child: Text(
                    'Price chart unavailable for $symbol.',
                    style: theme.textTheme.bodyMedium,
                  ),
                ),
              );
            }

            final points = payload.closePrices;
            final activeIdx =
                (_activeIndex ?? (points.length - 1)).clamp(0, points.length - 1);
            final currentPrice = points[activeIdx];

            final minPrice = points.reduce(math.min);
            final maxPrice = points.reduce(math.max);
            final yLabels = [
              ValueFormatters.usd(minPrice),
              ValueFormatters.usd(maxPrice),
            ];

            List<String>? xLabels;
            if (payload.timestamps.length >= 2) {
              xLabels = [
                _formatDate(payload.timestamps.first),
                _formatDate(payload.timestamps.last),
              ];
            }

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  ValueFormatters.usd(currentPrice),
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: 240,
                  child: InteractiveLineChart(
                    points: points,
                    highlightedIndex: activeIdx,
                    yLabels: yLabels,
                    xLabels: xLabels,
                    onPointSelected: (index) {
                      final safe = index.clamp(0, points.length - 1);
                      if (_activeIndex != safe) {
                        setState(() => _activeIndex = safe);
                      }
                    },
                    onInteractionEnd: () {
                      if (_activeIndex != null) {
                        setState(() => _activeIndex = null);
                      }
                    },
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'High: ${ValueFormatters.usd(maxPrice)}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF4ADE80),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    Text(
                      'Low: ${ValueFormatters.usd(minPrice)}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: const Color(0xFFFF6B6B),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ],
            );
          },
        ),
      ],
    );
  }

  // ────────────────────────────────────────────────────────────────────────
  // Section 2: Market Data
  // ────────────────────────────────────────────────────────────────────────

  Widget _buildMarketDataSection(ThemeData theme) {
    return FutureBuilder<AssetMarketData?>(
      future: _marketFuture,
      builder: (context, snapshot) {
        // Stale-while-revalidate: show cached market data while loading
        final data = snapshot.data ?? _lastMarket;

        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastMarket = snapshot.data;
        }

        if (data == null) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return Container(
              height: 60,
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: const Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            );
          }
          return const SizedBox.shrink();
        }

        return _CompactMarketData(data: data, theme: theme);
      },
    );
  }

  // ────────────────────────────────────────────────────────────────────────
  // Section 3: Your Holding
  // ────────────────────────────────────────────────────────────────────────

  Widget _buildHoldingCard(ThemeData theme, String symbol) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Your Holding',
              style: theme.textTheme.titleSmall
                  ?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                ValueFormatters.usd(widget.holdingValueUsd),
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              Text(
                '${ValueFormatters.percent(widget.holdingPercentage)} of portfolio',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
          if (widget.nativeAmount > 0) ...[
            const SizedBox(height: 4),
            Text(
              '${ValueFormatters.number(widget.nativeAmount, decimals: 4)} $symbol',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }

  // ────────────────────────────────────────────────────────────────────────
  // Section 4: Wallet Breakdown
  // ────────────────────────────────────────────────────────────────────────

  Widget _buildWalletBreakdownSection(ThemeData theme, String symbol) {
    return FutureBuilder<WalletBreakdownResponse?>(
      future: _breakdownFuture,
      builder: (context, snapshot) {
        // Stale-while-revalidate: show cached breakdown while loading
        final data = snapshot.data ?? _lastBreakdown;

        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastBreakdown = snapshot.data;
        }

        if (data == null && snapshot.connectionState == ConnectionState.waiting) {
          return Container(
            height: 120,
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: theme.colorScheme.outlineVariant),
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
        if (data == null || data.sources.isEmpty) {
          return Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: theme.colorScheme.outlineVariant),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Where You Hold $symbol',
                  style: theme.textTheme.titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 12),
                Text(
                  'Not found in any wallets or exchanges',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
                if (_breakdownDebug != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    _breakdownDebug!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
                      fontSize: 9,
                    ),
                    maxLines: 6,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          );
        }

        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: theme.colorScheme.outlineVariant),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Where You Hold $symbol',
                style: theme.textTheme.titleSmall
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              for (int i = 0; i < data.sources.length; i++) ...[
                if (i > 0) const SizedBox(height: 12),
                _BreakdownRow(
                  item: data.sources[i],
                  symbol: symbol,
                  theme: theme,
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Compact Market Data
// ══════════════════════════════════════════════════════════════════════════════

class _CompactMarketData extends StatelessWidget {
  const _CompactMarketData({required this.data, required this.theme});
  final AssetMarketData data;
  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    final dimStyle = theme.textTheme.labelSmall?.copyWith(
      color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
    );
    final valStyle = theme.textTheme.labelSmall?.copyWith(
      fontWeight: FontWeight.w600,
    );

    // Row 1: Rank, Market Cap, Volume
    final row1 = <InlineSpan>[];
    if (data.marketCapRank > 0) {
      row1.add(TextSpan(text: 'Rank ', style: dimStyle));
      row1.add(TextSpan(text: '#${data.marketCapRank}', style: valStyle));
    }
    if (data.marketCap > 0) {
      if (row1.isNotEmpty) row1.add(TextSpan(text: '  \u2022  ', style: dimStyle));
      row1.add(TextSpan(text: 'MCap ', style: dimStyle));
      row1.add(TextSpan(text: ValueFormatters.compactUsd(data.marketCap), style: valStyle));
    }
    if (data.totalVolume > 0) {
      if (row1.isNotEmpty) row1.add(TextSpan(text: '  \u2022  ', style: dimStyle));
      row1.add(TextSpan(text: 'Vol ', style: dimStyle));
      row1.add(TextSpan(text: ValueFormatters.compactUsd(data.totalVolume), style: valStyle));
    }

    // Row 2: Supply, 24h High/Low
    final row2 = <InlineSpan>[];
    if (data.circulatingSupply > 0) {
      row2.add(TextSpan(text: 'Supply ', style: dimStyle));
      row2.add(TextSpan(text: _compactNumber(data.circulatingSupply), style: valStyle));
    }
    if (data.high24h > 0 && data.low24h > 0) {
      if (row2.isNotEmpty) row2.add(TextSpan(text: '  \u2022  ', style: dimStyle));
      row2.add(TextSpan(text: '24h ', style: dimStyle));
      row2.add(TextSpan(
        text: ValueFormatters.usd(data.low24h),
        style: valStyle?.copyWith(color: const Color(0xFFFF6B6B)),
      ));
      row2.add(TextSpan(text: ' \u2013 ', style: dimStyle));
      row2.add(TextSpan(
        text: ValueFormatters.usd(data.high24h),
        style: valStyle?.copyWith(color: const Color(0xFF4ADE80)),
      ));
    }

    // Row 3: ATH / ATL
    final row3 = <InlineSpan>[];
    if (data.ath > 0) {
      row3.add(TextSpan(text: 'ATH ', style: dimStyle));
      row3.add(TextSpan(text: ValueFormatters.usd(data.ath), style: valStyle));
      if (data.athChangePct != 0) {
        row3.add(TextSpan(
          text: ' (${data.athChangePct.toStringAsFixed(1)}%)',
          style: dimStyle?.copyWith(
            color: data.athChangePct >= 0 ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B),
          ),
        ));
      }
    }
    if (data.atl > 0) {
      if (row3.isNotEmpty) row3.add(TextSpan(text: '  \u2022  ', style: dimStyle));
      row3.add(TextSpan(text: 'ATL ', style: dimStyle));
      row3.add(TextSpan(text: ValueFormatters.usd(data.atl), style: valStyle));
    }

    // Price change pills
    final changes = <MapEntry<String, double>>[];
    if (data.priceChange1h != 0) changes.add(MapEntry('1h', data.priceChange1h));
    if (data.priceChange24h != 0) changes.add(MapEntry('24h', data.priceChange24h));
    if (data.priceChange7d != 0) changes.add(MapEntry('7d', data.priceChange7d));
    if (data.priceChange30d != 0) changes.add(MapEntry('30d', data.priceChange30d));

    final hasContent = row1.isNotEmpty || row2.isNotEmpty || row3.isNotEmpty || changes.isNotEmpty;
    if (!hasContent) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (row1.isNotEmpty)
            RichText(text: TextSpan(children: row1)),
          if (row2.isNotEmpty) ...[
            const SizedBox(height: 3),
            RichText(text: TextSpan(children: row2)),
          ],
          if (row3.isNotEmpty) ...[
            const SizedBox(height: 3),
            RichText(text: TextSpan(children: row3)),
          ],
          if (changes.isNotEmpty) ...[
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: [
                for (final e in changes)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: (e.value >= 0
                              ? const Color(0xFF4ADE80)
                              : const Color(0xFFFF6B6B))
                          .withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      '${e.key}: ${e.value >= 0 ? '+' : ''}${e.value.toStringAsFixed(1)}%',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: e.value >= 0
                            ? const Color(0xFF4ADE80)
                            : const Color(0xFFFF6B6B),
                        fontWeight: FontWeight.w600,
                        fontSize: 10,
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  static String _compactNumber(num value) {
    final abs = value.abs();
    if (abs >= 1e12) return '${(value / 1e12).toStringAsFixed(2)}T';
    if (abs >= 1e9) return '${(value / 1e9).toStringAsFixed(2)}B';
    if (abs >= 1e6) return '${(value / 1e6).toStringAsFixed(2)}M';
    if (abs >= 1e3) return '${(value / 1e3).toStringAsFixed(1)}K';
    return value.toStringAsFixed(0);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Wallet Breakdown Row
// ══════════════════════════════════════════════════════════════════════════════

class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow({
    required this.item,
    required this.symbol,
    required this.theme,
  });

  final WalletBreakdownItem item;
  final String symbol;
  final ThemeData theme;

  static const _sourceTypeLabels = {
    'wallet': 'Wallet',
    'exchange': 'Exchange',
    'staking': 'Staking',
    'defi': 'DeFi',
  };

  static const _sourceTypeColors = {
    'wallet': Color(0xFF818CF8),
    'exchange': Color(0xFFFBBF24),
    'staking': Color(0xFF34D399),
    'defi': Color(0xFF22D3EE),
  };

  @override
  Widget build(BuildContext context) {
    final chipLabel = _sourceTypeLabels[item.sourceType] ?? item.sourceType;
    final barColor = _sourceTypeColors[item.sourceType] ?? const Color(0xFF6366F1);
    final displayLabel = item.label.isNotEmpty
        ? item.label
        : (item.address != null
            ? ValueFormatters.shortenAddress(item.address!)
            : 'Unknown');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Row 1: icon + label + chip
        Row(
          children: [
            _buildIcon(),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                displayLabel,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w500,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: barColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                chipLabel,
                style: theme.textTheme.labelSmall?.copyWith(
                  color: barColor,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        // Row 2: amount + value
        Padding(
          padding: const EdgeInsets.only(left: 40),
          child: Text(
            '${ValueFormatters.tokenAmount(item.amount)} $symbol \u2014 ${ValueFormatters.usd(item.valueUsd)}',
            style: theme.textTheme.bodySmall,
          ),
        ),
        const SizedBox(height: 4),
        // Row 3: allocation bar + percentage
        Padding(
          padding: const EdgeInsets.only(left: 40),
          child: Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: SizedBox(
                    height: 8,
                    child: LinearProgressIndicator(
                      value: (item.allocationPct / 100).clamp(0.0, 1.0),
                      backgroundColor:
                          theme.colorScheme.onSurface.withValues(alpha: 0.08),
                      valueColor: AlwaysStoppedAnimation(barColor),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '${item.allocationPct.toStringAsFixed(1)}%',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: barColor,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
        // Row 4: last synced (if available)
        if (item.lastSynced != null) ...[
          const SizedBox(height: 2),
          Padding(
            padding: const EdgeInsets.only(left: 40),
            child: Text(
              'Synced ${ValueFormatters.timestamp(item.lastSynced)}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildIcon() {
    // For wallet/staking with a blockchain, use ChainLogo
    if ((item.sourceType == 'wallet' || item.sourceType == 'staking') &&
        item.blockchain != null &&
        item.blockchain!.isNotEmpty) {
      // Map blockchain name to symbol for ChainLogo
      final chainSymbol = _blockchainToSymbol[item.blockchain!.toLowerCase()];
      if (chainSymbol != null && ChainLogo.hasLogo(chainSymbol)) {
        return ChainLogo(symbol: chainSymbol, size: 32);
      }
    }
    // For exchanges, show a colored circle with first letter
    final letter = item.label.isNotEmpty ? item.label[0].toUpperCase() : '?';
    final bgColor = _sourceTypeColors[item.sourceType] ?? const Color(0xFF6366F1);
    return Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(shape: BoxShape.circle, color: bgColor),
      alignment: Alignment.center,
      child: Text(
        letter,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w700,
          fontSize: 14,
        ),
      ),
    );
  }

  static const _blockchainToSymbol = {
    'cardano': 'ADA',
    'bitcoin': 'BTC',
    'ethereum': 'ETH',
    'solana': 'SOL',
    'polygon': 'POL',
    'base': 'BASE',
    'algorand': 'ALGO',
    'bsc': 'BNB',
    'arbitrum': 'ARBITRUM',
    'avalanche': 'AVAX',
    'tron': 'TRX',
    'xrp': 'XRP',
    'hedera': 'HBAR',
    'multiversx': 'EGLD',
    'sui': 'SUI',
    'aptos': 'APT',
    'filecoin': 'FIL',
    'litecoin': 'LTC',
    'dogecoin': 'DOGE',
    'zcash': 'ZEC',
    'tezos': 'XTZ',
    'stacks': 'STX',
    'vechain': 'VET',
    'cosmos': 'ATOM',
    'near': 'NEAR',
    'icp': 'ICP',
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// Alert Bottom Sheet (unchanged)
// ══════════════════════════════════════════════════════════════════════════════

class _AlertBottomSheet extends StatefulWidget {
  const _AlertBottomSheet({
    required this.symbol,
    required this.name,
    required this.alertRepo,
    required this.onChanged,
  });

  final String symbol;
  final String name;
  final AlertRepository alertRepo;
  final VoidCallback onChanged;

  @override
  State<_AlertBottomSheet> createState() => _AlertBottomSheetState();
}

class _AlertBottomSheetState extends State<_AlertBottomSheet> {
  List<AssetPriceAlert> _existingAlerts = [];
  bool _loadingExisting = true;

  // Price change alert
  bool _priceChangeEnabled = false;
  double _priceChangeThreshold = 10.0;
  static const _priceChangeOptions = [5.0, 10.0, 15.0, 20.0];

  // Price threshold alert
  final _thresholdController = TextEditingController();
  bool _thresholdAbove = true;

  @override
  void initState() {
    super.initState();
    _loadExistingAlerts();
  }

  Future<void> _loadExistingAlerts() async {
    final alerts =
        await widget.alertRepo.loadAlertsForSymbol(widget.symbol);
    if (!mounted) return;
    setState(() {
      _existingAlerts = alerts;
      _loadingExisting = false;
    });
  }

  @override
  void dispose() {
    _thresholdController.dispose();
    super.dispose();
  }

  bool _isDuplicate(AlertType type, double threshold, bool above) {
    return _existingAlerts.any((a) =>
        a.type == type &&
        a.threshold == threshold &&
        (type == AlertType.assetPricePercent || a.above == above));
  }

  Future<void> _deleteAlert(String id) async {
    await widget.alertRepo.removeAssetAlert(id);
    if (!mounted) return;
    setState(() {
      _existingAlerts.removeWhere((a) => a.id == id);
    });
    widget.onChanged();
  }

  String _alertDescription(AssetPriceAlert alert) {
    if (alert.type == AlertType.assetPriceThreshold) {
      final direction = alert.above ? 'above' : 'below';
      return 'Notify when $direction \$${alert.threshold.toStringAsFixed(2)}';
    }
    return 'Notify on ${alert.threshold.toStringAsFixed(0)}% change';
  }

  Future<void> _save() async {
    int added = 0;

    if (_priceChangeEnabled) {
      if (_isDuplicate(
          AlertType.assetPricePercent, _priceChangeThreshold, true)) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  'A ${_priceChangeThreshold.toStringAsFixed(0)}% alert already exists for ${widget.symbol.toUpperCase()}'),
            ),
          );
        }
      } else {
        final alert = AssetPriceAlert(
          id: AssetPriceAlert.generateId(widget.symbol),
          symbol: widget.symbol,
          name: widget.name,
          type: AlertType.assetPricePercent,
          threshold: _priceChangeThreshold,
          above: true,
          createdAt: DateTime.now(),
        );
        await widget.alertRepo.addAssetAlert(alert);
        added++;
      }
    }

    final thresholdText = _thresholdController.text.trim();
    if (thresholdText.isNotEmpty) {
      final value = double.tryParse(thresholdText);
      if (value != null && value > 0) {
        if (_isDuplicate(
            AlertType.assetPriceThreshold, value, _thresholdAbove)) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                    'A \$${value.toStringAsFixed(2)} ${_thresholdAbove ? "above" : "below"} alert already exists for ${widget.symbol.toUpperCase()}'),
              ),
            );
          }
        } else {
          final alert = AssetPriceAlert(
            id: AssetPriceAlert.generateId(widget.symbol),
            symbol: widget.symbol,
            name: widget.name,
            type: AlertType.assetPriceThreshold,
            threshold: value,
            above: _thresholdAbove,
            createdAt: DateTime.now(),
          );
          await widget.alertRepo.addAssetAlert(alert);
          added++;
        }
      }
    }

    widget.onChanged();
    if (mounted) {
      if (added > 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
                'Alert saved for ${widget.symbol.toUpperCase()}'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final symbol = widget.symbol.toUpperCase();

    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Price Alerts for $symbol',
            style: theme.textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 16),

          // Existing alerts section
          if (_loadingExisting)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            )
          else if (_existingAlerts.isNotEmpty) ...[
            Text(
              'Active Alerts',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
              ),
            ),
            const SizedBox(height: 8),
            for (final alert in _existingAlerts)
              Dismissible(
                key: Key(alert.id),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 16),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.error,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    Icons.delete,
                    color: theme.colorScheme.onError,
                  ),
                ),
                onDismissed: (_) => _deleteAlert(alert.id),
                child: Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest
                        .withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        alert.type == AlertType.assetPriceThreshold
                            ? Icons.attach_money
                            : Icons.trending_up,
                        size: 18,
                        color: theme.colorScheme.primary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _alertDescription(alert),
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, size: 18),
                        onPressed: () => _deleteAlert(alert.id),
                        visualDensity: VisualDensity.compact,
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 8),
            const Divider(height: 1),
            const SizedBox(height: 12),
          ],

          // Add new alert section
          Text(
            _existingAlerts.isEmpty ? 'Add Alert' : 'Add New Alert',
            style: theme.textTheme.titleSmall?.copyWith(
              color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
            ),
          ),
          const SizedBox(height: 8),

          // Price change alert
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: const Text('Price change alert'),
            subtitle: const Text('Notify on significant % move'),
            value: _priceChangeEnabled,
            onChanged: (v) => setState(() => _priceChangeEnabled = v),
          ),
          if (_priceChangeEnabled)
            Wrap(
              spacing: 8,
              children: [
                for (final opt in _priceChangeOptions)
                  ChoiceChip(
                    label: Text('${opt.toStringAsFixed(0)}%'),
                    selected: _priceChangeThreshold == opt,
                    onSelected: (_) =>
                        setState(() => _priceChangeThreshold = opt),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
          const SizedBox(height: 12),
          const Divider(height: 1),
          const SizedBox(height: 12),

          // Price threshold alert
          Text(
            'Price threshold alert',
            style: theme.textTheme.titleSmall,
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _thresholdController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'USD price',
                    prefixText: '\$',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: true, label: Text('Above')),
                  ButtonSegment(value: false, label: Text('Below')),
                ],
                selected: {_thresholdAbove},
                onSelectionChanged: (v) =>
                    setState(() => _thresholdAbove = v.first),
                style: ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          FilledButton(
            onPressed: _save,
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Chart Payload Parser (unchanged)
// ══════════════════════════════════════════════════════════════════════════════

class _ChartPayload {
  _ChartPayload({required this.closePrices, required this.timestamps});

  final List<double> closePrices;
  final List<DateTime> timestamps;

  factory _ChartPayload.fromJson(Map<String, dynamic> json) {
    // The OHLCV endpoint returns data in various formats.
    final List<double> prices = [];
    final List<DateTime> timestamps = [];

    final ohlcv = json['ohlcv_data'] ?? json['ohlcv'] ?? json['data'] ?? json['chart_data'];
    if (ohlcv is List) {
      for (final candle in ohlcv) {
        if (candle is Map) {
          final m = JsonUtils.map(candle);
          final close = JsonUtils.doubleValue(m, 'close',
              fallback: JsonUtils.doubleValue(m, 'price'));
          if (close > 0) {
            prices.add(close);
            final ts = m['timestamp'] ?? m['time'] ?? m['date'];
            timestamps.add(_parseTimestamp(ts));
          }
        } else if (candle is List && candle.length >= 5) {
          // Array format: [timestamp, open, high, low, close]
          final close = (candle[4] is num) ? candle[4].toDouble() : 0.0;
          if (close > 0) {
            prices.add(close);
            timestamps.add(_parseTimestamp(candle[0]));
          }
        }
      }
    }

    // Fallback: simple price points
    if (prices.isEmpty) {
      final points = json['prices'] ?? json['points'];
      if (points is List) {
        for (final p in points) {
          if (p is num) {
            prices.add(p.toDouble());
          } else if (p is Map) {
            final m = JsonUtils.map(p);
            final v = JsonUtils.doubleValue(m, 'price',
                fallback: JsonUtils.doubleValue(m, 'value'));
            if (v > 0) {
              prices.add(v);
              final ts = m['timestamp'] ?? m['time'] ?? m['date'];
              timestamps.add(_parseTimestamp(ts));
            }
          }
        }
      }
    }

    // Pad timestamps if some entries lacked them
    while (timestamps.length < prices.length) {
      timestamps.add(DateTime.now());
    }

    return _ChartPayload(closePrices: prices, timestamps: timestamps);
  }

  static DateTime _parseTimestamp(dynamic ts) {
    if (ts is int) {
      // Unix seconds vs milliseconds
      return ts > 1e12
          ? DateTime.fromMillisecondsSinceEpoch(ts)
          : DateTime.fromMillisecondsSinceEpoch(ts * 1000);
    }
    if (ts is double) {
      return DateTime.fromMillisecondsSinceEpoch((ts * 1000).round());
    }
    if (ts is String) {
      return DateTime.tryParse(ts) ?? DateTime.now();
    }
    return DateTime.now();
  }
}
