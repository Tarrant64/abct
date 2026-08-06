import 'package:flutter/material.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/exchanges_summary.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_interceptor.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/section_card.dart';
import '../../../core/ui/value_formatters.dart';

class ExchangesTab extends StatefulWidget {
  const ExchangesTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<ExchangesTab> createState() => _ExchangesTabState();
}

class _ExchangesTabState extends State<ExchangesTab> {
  late final ApiClient _api;
  late Future<ExchangesSummary> _future;
  ExchangesSummary? _lastData; // In-memory cache for instant rendering
  final Map<String, Future<ExchangeDetail>> _details = {};
  final Set<String> _expanded = <String>{};
  DateTime? _lastLoadStartedAt;
  void Function()? _disposeRevalidation;

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
    _future = _load();
    AppRefreshSignal.instance.addListener(_onAppRefreshSignal);
    _disposeRevalidation = CacheInterceptor.onRevalidated(
      '/api/mobile/exchanges/summary',
      (_) => _silentReload(),
    );
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    _disposeRevalidation?.call();
    super.dispose();
  }

  Future<ExchangesSummary> _load({bool refresh = false}) {
    _lastLoadStartedAt = DateTime.now();
    return _api.getExchangesSummary(refresh: refresh);
  }

  void _onAppRefreshSignal() {
    if (!mounted) return;
    final last = _lastLoadStartedAt;
    if (last != null &&
        DateTime.now().difference(last) < AppRefreshSignal.minRefreshInterval) {
      return;
    }
    _silentReload();
  }

  /// Reloads the summary from the cache-backed API without disturbing the
  /// visible data or collapsing expanded exchange details. Used for resume
  /// refreshes and revalidation pickups; unlike [_refresh] this never forces
  /// a backend recompute.
  Future<void> _silentReload() async {
    try {
      final data = await _load();
      if (!mounted) return;
      setState(() {
        _lastData = data;
        _future = Future.value(data);
      });
    } catch (_) {
      // Keep showing current data; the next pull or load retries.
    }
  }

  Future<void> _refresh() async {
    final data = await _load(refresh: true);
    if (!mounted) return;
    setState(() {
      _lastData = data;
      _future = Future.value(data);
      _details.clear();
      _expanded.clear();
    });
  }

  Future<ExchangeDetail> _loadDetail(
    ExchangeSummaryItem exchange, {
    bool refresh = false,
  }) {
    final key = exchange.name.toLowerCase();
    if (refresh || !_details.containsKey(key)) {
      _details[key] = _api.getExchangeDetail(
        exchangeName: exchange.name,
        refresh: refresh,
      );
    }
    return _details[key]!;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<ExchangesSummary>(
      future: _future,
      builder: (context, snapshot) {
        // Stale-while-revalidate: render cached data while loading
        final data = snapshot.data ?? _lastData;

        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastData = snapshot.data;
        }

        if (data == null) {
          if (snapshot.hasError) {
            return _ErrorState(
              message: snapshot.error.toString(),
              onRetry: () {
                setState(() {
                  _future = _load();
                });
              },
            );
          }
          return const Center(child: CircularProgressIndicator());
        }
        final exchanges = data.exchanges;

        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              SectionCard(
                title: 'Exchanges',
                subtitle:
                    'Updated ${ValueFormatters.timestamp(data.lastUpdated?.toIso8601String())}',
                child: Row(
                  children: [
                    Expanded(
                      child: _statTile(
                        context,
                        'Connected',
                        '${data.totalExchanges}',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _statTile(
                        context,
                        'Total Value',
                        ValueFormatters.compactUsd(data.totalValueUsd),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Exchange Summary',
                child: exchanges.isEmpty
                    ? const Text(
                        'No exchanges configured. Add exchange keys in the ABCT web dashboard.',
                      )
                    : Column(
                        children: [
                          for (final exchange in exchanges)
                            _exchangeTile(context, exchange),
                        ],
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _exchangeTile(BuildContext context, ExchangeSummaryItem exchange) {
    final displayName = exchange.displayName;
    final configured = exchange.configured;
    final valueUsd = exchange.valueUsd;
    final assetCount = exchange.assetCount;
    final lastSync = exchange.lastSync?.toIso8601String();
    final key = exchange.name.toLowerCase();
    final isExpanded = _expanded.contains(key);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          onExpansionChanged: (expanded) {
            setState(() {
              if (expanded) {
                _expanded.add(key);
                _loadDetail(exchange);
              } else {
                _expanded.remove(key);
              }
            });
          },
          title: Row(
            children: [
              CircleAvatar(
                backgroundColor:
                    configured ? Colors.green.shade100 : Colors.red.shade100,
                child: Icon(
                  configured ? Icons.check_circle : Icons.link_off,
                  color:
                      configured ? Colors.green.shade800 : Colors.red.shade800,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      displayName,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${assetCount.toInt()} assets • ${configured ? 'Connected' : 'Not configured'}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Last sync: ${ValueFormatters.timestamp(lastSync)}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              Text(
                ValueFormatters.usd(valueUsd),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
          children: [
            if (isExpanded)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: FutureBuilder<ExchangeDetail>(
                  future: _loadDetail(exchange),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Padding(
                        padding: EdgeInsets.symmetric(vertical: 10),
                        child: LinearProgressIndicator(minHeight: 2),
                      );
                    }
                    if (snapshot.hasError) {
                      return Padding(
                        padding: const EdgeInsets.only(top: 2, bottom: 8),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                'Unable to load holdings for ${exchange.displayName}.',
                                style: TextStyle(
                                  color: Theme.of(context).colorScheme.error,
                                ),
                              ),
                            ),
                            TextButton(
                              onPressed: () {
                                setState(() {
                                  _details.remove(key);
                                });
                              },
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      );
                    }

                    final detail = snapshot.data!;
                    if (detail.assets.isEmpty) {
                      return const Padding(
                        padding: EdgeInsets.only(top: 4, bottom: 8),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text('No exchange assets found.'),
                        ),
                      );
                    }

                    return Column(
                      children: [
                        const Divider(height: 10),
                        for (final asset in detail.assets)
                          _assetRow(context, asset),
                      ],
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _assetRow(BuildContext context, ExchangeAsset asset) {
    final isPositive = asset.change24h >= 0;
    final changeColor = isPositive
        ? const Color(0xFF35D192)
        : Theme.of(context).colorScheme.error;
    final symbol = asset.symbol.isEmpty ? '?' : asset.symbol;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          CircleAvatar(
            radius: 15,
            backgroundColor:
                Theme.of(context).colorScheme.primary.withValues(alpha: 0.14),
            backgroundImage:
                asset.logoUrl != null ? NetworkImage(asset.logoUrl!) : null,
            child: asset.logoUrl == null
                ? Text(
                    symbol.substring(0, 1).toUpperCase(),
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 11),
                  )
                : null,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  symbol.toUpperCase(),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                Text(
                  asset.name.isEmpty
                      ? '${ValueFormatters.number(asset.balance, decimals: 6)} $symbol'
                      : '${asset.name} • ${ValueFormatters.number(asset.balance, decimals: 6)} $symbol',
                  style: Theme.of(context).textTheme.bodySmall,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                ValueFormatters.usd(asset.usdValue),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              Text(
                '${isPositive ? '+' : ''}${asset.change24h.toStringAsFixed(2)}%',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: changeColor,
                ),
              ),
              Text(
                '@ ${ValueFormatters.usd(asset.usdPrice)}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _statTile(BuildContext context, String label, String value) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

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
              style: TextStyle(color: Theme.of(context).colorScheme.error),
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
