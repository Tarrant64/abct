import 'package:flutter/material.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/transaction.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_interceptor.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/value_formatters.dart';

class TransactionsTab extends StatefulWidget {
  const TransactionsTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<TransactionsTab> createState() => _TransactionsTabState();
}

enum _DayRange {
  d7(7, '7D'),
  d30(30, '30D'),
  d90(90, '90D');

  const _DayRange(this.days, this.label);
  final int days;
  final String label;
}

enum _DirectionFilter { all, sent, received }

class _TransactionsTabState extends State<TransactionsTab> {
  late final ApiClient _api;
  late Future<TransactionHistory> _future;
  TransactionHistory? _lastData; // In-memory cache for instant rendering

  _DayRange _range = _DayRange.d30;
  _DirectionFilter _direction = _DirectionFilter.all;
  String? _chainFilter;
  String _searchQuery = '';

  final _searchController = TextEditingController();
  DateTime? _lastLoadStartedAt;
  void Function()? _disposeRevalidation;

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
    _future = _load();
    AppRefreshSignal.instance.addListener(_onAppRefreshSignal);
    _disposeRevalidation = CacheInterceptor.onRevalidated(
      '/api/transactions',
      (_) => _silentReload(),
    );
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    _disposeRevalidation?.call();
    _searchController.dispose();
    super.dispose();
  }

  Future<TransactionHistory> _load({bool revalidate = false}) {
    _lastLoadStartedAt = DateTime.now();
    return _api.getTransactions(
      days: _range.days,
      blockchain: _chainFilter,
      direction: _direction == _DirectionFilter.all
          ? null
          : _direction.name,
      revalidate: revalidate,
    );
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

  /// Reloads with the current filters from the cache-backed API without
  /// disturbing the visible data; [_lastData] keeps the current content on
  /// screen until the new payload lands. Used for resume refreshes and
  /// revalidation pickups.
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
    // Manual pull: network-first so the pull never re-serves the cache entry
    // it is refreshing.
    final data = await _load(revalidate: true);
    if (!mounted) return;
    setState(() {
      _lastData = data;
      _future = Future.value(data);
    });
  }

  void _changeRange(_DayRange range) {
    if (range == _range) return;
    setState(() {
      _range = range;
      _future = _load();
    });
  }

  List<Transaction> _applyClientFilters(List<Transaction> txs) {
    var filtered = txs;
    if (_searchQuery.isNotEmpty) {
      final q = _searchQuery.toLowerCase();
      filtered = filtered.where((tx) {
        return tx.txHash.toLowerCase().contains(q) ||
            tx.symbol.toLowerCase().contains(q) ||
            tx.fromAddress.toLowerCase().contains(q) ||
            tx.toAddress.toLowerCase().contains(q) ||
            tx.blockchain.toLowerCase().contains(q);
      }).toList();
    }
    return filtered;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<TransactionHistory>(
      future: _future,
      builder: (context, snapshot) {
        // Stale-while-revalidate: render cached data while loading
        final history = snapshot.data ?? _lastData;

        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastData = snapshot.data;
        }

        if (history == null) {
          if (snapshot.hasError) {
            return _ErrorView(
              message: snapshot.error.toString().replaceFirst('Exception: ', ''),
              onRetry: () => setState(() => _future = _load()),
            );
          }
          return const Center(child: CircularProgressIndicator());
        }
        final allTxs = history.transactions;
        final chains = allTxs
            .map((tx) => tx.blockchain)
            .toSet()
            .toList()
          ..sort();
        final filtered = _applyClientFilters(allTxs);

        return RefreshIndicator(
          onRefresh: _refresh,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Day range chips
                      Wrap(
                        spacing: 8,
                        children: [
                          for (final r in _DayRange.values)
                            ChoiceChip(
                              label: Text(r.label),
                              selected: _range == r,
                              onSelected: (_) => _changeRange(r),
                              visualDensity: VisualDensity.compact,
                            ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      // Direction filter
                      SegmentedButton<_DirectionFilter>(
                        segments: const [
                          ButtonSegment(
                            value: _DirectionFilter.all,
                            label: Text('All'),
                          ),
                          ButtonSegment(
                            value: _DirectionFilter.sent,
                            icon: Icon(Icons.arrow_upward, size: 16),
                            label: Text('Sent'),
                          ),
                          ButtonSegment(
                            value: _DirectionFilter.received,
                            icon: Icon(Icons.arrow_downward, size: 16),
                            label: Text('Received'),
                          ),
                        ],
                        selected: {_direction},
                        onSelectionChanged: (selection) {
                          setState(() {
                            _direction = selection.first;
                            _future = _load();
                          });
                        },
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _searchController,
                              decoration: InputDecoration(
                                hintText: 'Search transactions...',
                                prefixIcon: const Icon(Icons.search, size: 20),
                                suffixIcon: _searchQuery.isNotEmpty
                                    ? IconButton(
                                        icon: const Icon(Icons.clear, size: 18),
                                        onPressed: () {
                                          _searchController.clear();
                                          setState(() => _searchQuery = '');
                                        },
                                      )
                                    : null,
                                isDense: true,
                                contentPadding: const EdgeInsets.symmetric(
                                    vertical: 10, horizontal: 12),
                              ),
                              onChanged: (value) =>
                                  setState(() => _searchQuery = value),
                            ),
                          ),
                          if (chains.length > 1) ...[
                            const SizedBox(width: 8),
                            DropdownButton<String?>(
                              value: _chainFilter,
                              hint: const Text('Chain'),
                              underline: const SizedBox.shrink(),
                              items: [
                                const DropdownMenuItem(
                                  value: null,
                                  child: Text('All Chains'),
                                ),
                                for (final chain in chains)
                                  DropdownMenuItem(
                                    value: chain,
                                    child: Text(
                                        ValueFormatters.titleCase(chain)),
                                  ),
                              ],
                              onChanged: (value) {
                                setState(() {
                                  _chainFilter = value;
                                  _future = _load();
                                });
                              },
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 4),
                    ],
                  ),
                ),
              ),
              if (filtered.isEmpty)
                const SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: Text('No transactions found.')),
                )
              else
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) =>
                        _TransactionTile(tx: filtered[index]),
                    childCount: filtered.length,
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _TransactionTile extends StatelessWidget {
  const _TransactionTile({required this.tx});

  final Transaction tx;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isSent = tx.direction.toLowerCase() == 'sent';
    final dirColor = isSent ? theme.colorScheme.error : const Color(0xFF6AE9C0);
    final dirIcon = isSent ? Icons.arrow_upward : Icons.arrow_downward;

    final mm = tx.txTime.month.toString().padLeft(2, '0');
    final dd = tx.txTime.day.toString().padLeft(2, '0');
    final hh = tx.txTime.hour.toString().padLeft(2, '0');
    final min = tx.txTime.minute.toString().padLeft(2, '0');
    final timeStr = '$mm/$dd $hh:$min';

    return ListTile(
      leading: CircleAvatar(
        backgroundColor: dirColor.withValues(alpha: 0.15),
        child: Icon(dirIcon, color: dirColor, size: 20),
      ),
      title: Row(
        children: [
          Expanded(
            child: Text(
              '${tx.amount > 0 ? ValueFormatters.number(tx.amount, decimals: 4) : ''} ${tx.symbol.toUpperCase()}',
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          if (tx.valueUsd > 0)
            Text(
              ValueFormatters.usd(tx.valueUsd),
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
        ],
      ),
      subtitle: Row(
        children: [
          Expanded(
            child: Text(
              '${ValueFormatters.titleCase(tx.blockchain)} • $timeStr',
              style: theme.textTheme.bodySmall,
            ),
          ),
          Text(
            isSent
                ? 'To: ${ValueFormatters.shortenAddress(tx.toAddress)}'
                : 'From: ${ValueFormatters.shortenAddress(tx.fromAddress)}',
            style: theme.textTheme.bodySmall?.copyWith(fontSize: 11),
          ),
        ],
      ),
      dense: true,
      visualDensity: VisualDensity.compact,
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

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
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
