import 'package:flutter/material.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/exchanges_summary.dart';
import '../../../core/models/token_holding.dart';
import '../../../core/models/wallets_summary.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_interceptor.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/chain_logo.dart';
import '../../../core/ui/haptics.dart';
import '../../../core/ui/section_card.dart';
import '../../../core/ui/smart_refresh.dart';
import '../../../core/ui/token_row.dart';
import '../../../core/ui/value_formatters.dart';

/// Combined All Holdings + Wallets + Exchanges tab with a segmented toggle.
class AssetsTab extends StatefulWidget {
  const AssetsTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<AssetsTab> createState() => _AssetsTabState();
}

enum _AssetView { allHoldings, wallets, exchanges }

class _AssetsTabState extends State<AssetsTab> {
  late final ApiClient _api;
  _AssetView _view = _AssetView.allHoldings;

  // All Holdings state
  late Future<AllHoldingsResponse> _holdingsFuture;
  AllHoldingsResponse? _lastHoldings; // In-memory cache for instant rendering
  HoldingsSortMode _sortMode = HoldingsSortMode.value;
  bool _sortAscending = false;
  bool _showZeroBalances = false;
  String _searchQuery = '';
  final _searchController = TextEditingController();

  // Wallets state
  late Future<WalletsSummary> _walletsFuture;
  WalletsSummary? _lastWallets; // In-memory cache for instant rendering
  String? _selectedBlockchain;
  bool _hideZeroBalances = true;

  // Exchanges state
  late Future<ExchangesSummary> _exchangesFuture;
  ExchangesSummary? _lastExchanges; // In-memory cache for instant rendering
  final Map<String, Future<ExchangeDetail>> _exchangeDetails = {};
  final Set<String> _expanded = <String>{};

  DateTime? _lastLoadStartedAt;
  final List<void Function()> _disposeRevalidations = [];

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
    _lastLoadStartedAt = DateTime.now();
    _holdingsFuture = _api.getAllHoldings();
    _walletsFuture = _loadWallets();
    _exchangesFuture = _loadExchanges();
    AppRefreshSignal.instance.addListener(_onAppRefreshSignal);
    _disposeRevalidations.addAll([
      CacheInterceptor.onRevalidated(
        '/portfolio/all-holdings',
        (_) => _silentReloadHoldings(),
      ),
      CacheInterceptor.onRevalidated(
        '/api/mobile/wallets',
        (_) => _silentReloadWallets(),
      ),
      CacheInterceptor.onRevalidated(
        '/api/mobile/exchanges/summary',
        (_) => _silentReloadExchanges(),
      ),
    ]);
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    for (final disposeListener in _disposeRevalidations) {
      disposeListener();
    }
    _searchController.dispose();
    super.dispose();
  }

  Future<WalletsSummary> _loadWallets({bool revalidate = false}) {
    return _api.getWallets(
      blockchain: _selectedBlockchain,
      revalidate: revalidate,
    );
  }

  Future<ExchangesSummary> _loadExchanges({bool refresh = false}) {
    return _api.getExchangesSummary(refresh: refresh);
  }

  void _onAppRefreshSignal() {
    if (!mounted) return;
    final last = _lastLoadStartedAt;
    if (last != null &&
        DateTime.now().difference(last) < AppRefreshSignal.minRefreshInterval) {
      return;
    }
    _lastLoadStartedAt = DateTime.now();
    // Reload all three views from the cache-backed API; entries past the
    // revalidation threshold refresh in the background and land through the
    // onRevalidated subscriptions.
    _silentReloadHoldings();
    _silentReloadWallets();
    _silentReloadExchanges();
  }

  // Silent reloads keep the visible data on screen (via the _last* caches)
  // until the new payload lands, and never collapse expanded exchange rows.
  // Used for resume refreshes and revalidation pickups.

  Future<void> _silentReloadHoldings() async {
    try {
      final data = await _api.getAllHoldings();
      if (!mounted) return;
      setState(() {
        _lastHoldings = data;
        _holdingsFuture = Future.value(data);
      });
    } catch (_) {
      // Keep showing current data; the next pull or load retries.
    }
  }

  Future<void> _silentReloadWallets() async {
    try {
      final data = await _loadWallets();
      if (!mounted) return;
      setState(() {
        _lastWallets = data;
        _walletsFuture = Future.value(data);
      });
    } catch (_) {
      // Keep showing current data; the next pull or load retries.
    }
  }

  Future<void> _silentReloadExchanges() async {
    try {
      final data = await _loadExchanges();
      if (!mounted) return;
      setState(() {
        _lastExchanges = data;
        _exchangesFuture = Future.value(data);
      });
    } catch (_) {
      // Keep showing current data; the next pull or load retries.
    }
  }

  Future<void> _refreshHoldings({bool hard = false}) async {
    // Manual pull: hard forces a backend recompute; soft is network-first so
    // the pull never re-serves the cache entry it is refreshing.
    final data = await _api.getAllHoldings(refresh: hard, revalidate: !hard);
    if (!mounted) return;
    setState(() {
      _lastHoldings = data;
      _holdingsFuture = Future.value(data);
    });
  }

  Future<void> _refreshWallets({bool hard = false}) async {
    final data = await _api.getWallets(
      blockchain: _selectedBlockchain,
      refresh: hard,
      revalidate: !hard,
    );
    if (!mounted) return;
    setState(() {
      _lastWallets = data;
      _walletsFuture = Future.value(data);
    });
  }

  Future<void> _refreshExchanges({bool hard = false}) async {
    final data = await _api.getExchangesSummary(
      refresh: hard,
      revalidate: !hard,
    );
    if (!mounted) return;
    setState(() {
      _lastExchanges = data;
      _exchangesFuture = Future.value(data);
      _exchangeDetails.clear();
      _expanded.clear();
    });
  }

  Future<ExchangeDetail> _loadExchangeDetail(
    ExchangeSummaryItem exchange, {
    bool refresh = false,
  }) {
    final key = exchange.name.toLowerCase();
    if (refresh || !_exchangeDetails.containsKey(key)) {
      _exchangeDetails[key] = _api.getExchangeDetail(
        exchangeName: exchange.name,
        refresh: refresh,
      );
    }
    return _exchangeDetails[key]!;
  }

  // ---------------------------------------------------------------------------
  // All Holdings helpers
  // ---------------------------------------------------------------------------

  List<TokenHolding> _filteredHoldings(List<TokenHolding> items) {
    var result = items;
    if (!_showZeroBalances) {
      result = result.where((h) => (h.valueUsd ?? 0) > 0).toList();
    }
    if (_searchQuery.isNotEmpty) {
      final q = _searchQuery.toLowerCase();
      result = result.where((h) {
        return h.ticker.toLowerCase().contains(q) ||
            h.assetName.toLowerCase().contains(q) ||
            h.displayName.toLowerCase().contains(q);
      }).toList();
    }
    return result;
  }

  /// Memoized filter+sort of the holdings list. Rebuilds only when the
  /// source list instance or a filter/sort input changes — every other
  /// setState (view toggles, exchange expansion, refresh completion with
  /// unchanged data identity) reuses the previous result instead of
  /// re-sorting the full list per frame.
  List<TokenHolding>? _displayedHoldingsCache;
  List<TokenHolding>? _displayedSource;
  HoldingsSortMode? _displayedSortMode;
  bool? _displayedAscending;
  bool? _displayedShowZero;
  String? _displayedQuery;

  List<TokenHolding> _displayedHoldings(List<TokenHolding> holdings) {
    final cached = _displayedHoldingsCache;
    if (cached != null &&
        identical(_displayedSource, holdings) &&
        _displayedSortMode == _sortMode &&
        _displayedAscending == _sortAscending &&
        _displayedShowZero == _showZeroBalances &&
        _displayedQuery == _searchQuery) {
      return cached;
    }
    final result = _sortedHoldings(_filteredHoldings(holdings));
    _displayedSource = holdings;
    _displayedSortMode = _sortMode;
    _displayedAscending = _sortAscending;
    _displayedShowZero = _showZeroBalances;
    _displayedQuery = _searchQuery;
    _displayedHoldingsCache = result;
    return result;
  }

  List<TokenHolding> _sortedHoldings(List<TokenHolding> items) {
    final sorted = [...items];
    switch (_sortMode) {
      case HoldingsSortMode.value:
        sorted.sort((a, b) => (a.valueUsd ?? 0).compareTo(b.valueUsd ?? 0));
      case HoldingsSortMode.name:
        sorted.sort((a, b) =>
            a.displayName.toLowerCase().compareTo(b.displayName.toLowerCase()));
      case HoldingsSortMode.quantity:
        sorted.sort((a, b) => a.totalQuantity.compareTo(b.totalQuantity));
    }
    if (!_sortAscending) {
      return sorted.reversed.toList();
    }
    return sorted;
  }

  void _toggleSort(HoldingsSortMode mode) {
    Haptics.light();
    setState(() {
      if (_sortMode == mode) {
        _sortAscending = !_sortAscending;
      } else {
        _sortMode = mode;
        _sortAscending = mode == HoldingsSortMode.name;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
          child: SegmentedButton<_AssetView>(
            segments: const [
              ButtonSegment(
                value: _AssetView.allHoldings,
                label: Text('Holdings'),
                icon: Icon(Icons.pie_chart_outline, size: 18),
              ),
              ButtonSegment(
                value: _AssetView.wallets,
                label: Text('Wallets'),
                icon: Icon(Icons.account_balance_wallet_outlined, size: 18),
              ),
              ButtonSegment(
                value: _AssetView.exchanges,
                label: Text('Exchanges'),
                icon: Icon(Icons.storefront_outlined, size: 18),
              ),
            ],
            selected: {_view},
            onSelectionChanged: (selection) {
              Haptics.light();
              setState(() {
                _view = selection.first;
              });
            },
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: switch (_view) {
            _AssetView.allHoldings => _buildAllHoldings(),
            _AssetView.wallets => _buildWallets(),
            _AssetView.exchanges => _buildExchanges(),
          },
        ),
      ],
    );
  }

  // ---------------------------------------------------------------------------
  // All Holdings view
  // ---------------------------------------------------------------------------

  Widget _buildAllHoldings() {
    return FutureBuilder<AllHoldingsResponse>(
      future: _holdingsFuture,
      builder: (context, snapshot) {
        // Stale-while-revalidate: use cached data while loading
        final response = snapshot.data ?? _lastHoldings;

        // Cache fresh data for instant rendering next time
        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastHoldings = snapshot.data;
        }

        if (response == null) {
          if (snapshot.hasError) {
            return _ErrorView(
              message: snapshot.error.toString(),
              onRetry: () {
                setState(() {
                  _holdingsFuture = _api.getAllHoldings();
                });
              },
            );
          }
          return const Center(child: CircularProgressIndicator());
        }
        final hasZero =
            response.holdings.any((h) => (h.valueUsd ?? 0) <= 0);
        final displayed = _displayedHoldings(response.holdings);
        final onSurface = Theme.of(context).colorScheme.onSurface;

        return SmartRefreshIndicator(
          onRefresh: (hard) => _refreshHoldings(hard: hard),
          child: CustomScrollView(
            slivers: [
              // Search field
              SliverToBoxAdapter(child: _buildSearchField(onSurface)),
              // Sort bar
              SliverToBoxAdapter(
                child: _buildSortBar(onSurface, hasZero),
              ),
              // Token list or empty state
              if (displayed.isEmpty)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(
                    child: Text(
                      _searchQuery.isNotEmpty
                          ? 'No tokens match "$_searchQuery".'
                          : 'No holdings found.',
                      style: TextStyle(
                        color: onSurface.withValues(alpha: 0.5),
                      ),
                    ),
                  ),
                )
              else
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      if (index.isOdd) {
                        return Divider(
                          height: 1,
                          indent: 20,
                          endIndent: 20,
                          color: onSurface.withValues(alpha: 0.06),
                        );
                      }
                      final tokenIndex = index ~/ 2;
                      if (tokenIndex >= displayed.length) return null;
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 20),
                        child: TokenRow(
                          token: displayed[tokenIndex],
                          privacyMode: false,
                          profile: widget.profile,
                        ),
                      );
                    },
                    childCount: displayed.length * 2 - 1,
                  ),
                ),
              // Bottom padding
              const SliverToBoxAdapter(
                child: SizedBox(height: 20),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSearchField(Color onSurface) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
      child: TextField(
        controller: _searchController,
        decoration: InputDecoration(
          hintText: 'Search tokens...',
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
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(
              color: onSurface.withValues(alpha: 0.12),
            ),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(
              color: onSurface.withValues(alpha: 0.12),
            ),
          ),
        ),
        onChanged: (value) => setState(() => _searchQuery = value),
      ),
    );
  }

  Widget _buildSortBar(Color onSurface, bool hasZero) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
      child: Row(
        children: [
          Text(
            'Sort by',
            style: TextStyle(
              fontSize: 12,
              color: onSurface.withValues(alpha: 0.4),
            ),
          ),
          const SizedBox(width: 10),
          for (final mode in HoldingsSortMode.values) ...[
            SortPill(
              label: mode.label,
              isSelected: _sortMode == mode,
              ascending: _sortMode == mode ? _sortAscending : null,
              onTap: () => _toggleSort(mode),
            ),
            const SizedBox(width: 6),
          ],
          const Spacer(),
          if (hasZero)
            GestureDetector(
              onTap: () {
                Haptics.light();
                setState(() {
                  _showZeroBalances = !_showZeroBalances;
                });
              },
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 18,
                    height: 18,
                    child: Checkbox(
                      value: _showZeroBalances,
                      onChanged: (v) {
                        Haptics.light();
                        setState(() {
                          _showZeroBalances = v ?? false;
                        });
                      },
                      materialTapTargetSize:
                          MaterialTapTargetSize.shrinkWrap,
                      visualDensity: VisualDensity.compact,
                      side: BorderSide(
                        color: onSurface.withValues(alpha: 0.3),
                      ),
                      activeColor: const Color(0xFF4ADE80),
                      checkColor: Colors.black,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    r'$0',
                    style: TextStyle(
                      fontSize: 11,
                      color: onSurface.withValues(alpha: 0.4),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Wallets view
  // ---------------------------------------------------------------------------

  Widget _buildWallets() {
    return FutureBuilder<WalletsSummary>(
      future: _walletsFuture,
      builder: (context, snapshot) {
        // Stale-while-revalidate: use cached data while loading
        final data = snapshot.data ?? _lastWallets;

        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastWallets = snapshot.data;
        }

        if (data == null) {
          if (snapshot.hasError) {
            return _ErrorView(
              message: snapshot.error.toString(),
              onRetry: () {
                setState(() {
                  _walletsFuture = _loadWallets();
                });
              },
            );
          }
          return const Center(child: CircularProgressIndicator());
        }
        final wallets = data.wallets;
        final totalWallets = data.totalWallets;
        final visibleWallets = wallets
            .where(
              (wallet) =>
                  !_hideZeroBalances ||
                  wallet.balance.usdValue.abs() > 0.0000001 ||
                  wallet.balance.native.abs() > 0.0000001,
            )
            .toList()
          ..sort((a, b) => b.balance.usdValue.compareTo(a.balance.usdValue));
        final visibleTotalValue = visibleWallets.fold<double>(
          0,
          (sum, wallet) => sum + wallet.balance.usdValue,
        );
        final lastUpdated = data.lastUpdated?.toIso8601String();
        final allChains = wallets
            .map((w) => w.blockchain)
            .where((e) => e.isNotEmpty)
            .toSet()
            .toList()
          ..sort();

        return SmartRefreshIndicator(
          onRefresh: (hard) => _refreshWallets(hard: hard),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              SectionCard(
                title: 'Wallets',
                subtitle: 'Updated ${ValueFormatters.timestamp(lastUpdated)}',
                child: Row(
                  children: [
                    Expanded(
                      child: _statTile(
                        context,
                        label: 'Visible Wallets',
                        value: '${visibleWallets.length}/$totalWallets',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _statTile(
                        context,
                        label: 'Visible Value',
                        value: ValueFormatters.compactUsd(visibleTotalValue),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Filter',
                child: Column(
                  children: [
                    SwitchListTile.adaptive(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Hide zero balances'),
                      subtitle:
                          const Text('Enabled by default for a cleaner list.'),
                      value: _hideZeroBalances,
                      onChanged: (value) {
                        setState(() {
                          _hideZeroBalances = value;
                        });
                      },
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String?>(
                      initialValue: _selectedBlockchain,
                      items: [
                        const DropdownMenuItem<String?>(
                          value: null,
                          child: Text('All blockchains'),
                        ),
                        for (final chain in allChains)
                          DropdownMenuItem<String?>(
                            value: chain,
                            child: Text(ValueFormatters.titleCase(chain)),
                          )
                      ],
                      onChanged: (value) {
                        setState(() {
                          _selectedBlockchain = value;
                          _walletsFuture = _loadWallets();
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (visibleWallets.isEmpty)
                const SectionCard(
                  title: 'Wallet List',
                  child: Text('No wallets found for the current filters.'),
                )
              else
                SectionCard(
                  title: 'Wallet List',
                  child: Column(
                    children: [
                      for (final wallet in visibleWallets)
                        _walletTile(context, wallet),
                    ],
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _walletTile(BuildContext context, WalletSummaryItem wallet) {
    final balance = wallet.balance;
    final label = wallet.label;
    final address = wallet.address;
    final blockchain = wallet.blockchain;
    final native = balance.native;
    final symbol = balance.nativeSymbol;
    final usdValue = balance.usdValue;
    final tokenCount = wallet.tokenCount;
    final nftCount = wallet.nftCount;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              ChainLogo(symbol: symbol.isEmpty ? blockchain : symbol, size: 32),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label.isEmpty
                      ? ValueFormatters.shortenAddress(address)
                      : label,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              _chip(ValueFormatters.titleCase(blockchain)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            address,
            style: Theme.of(context).textTheme.bodySmall,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${ValueFormatters.number(native)} $symbol',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              Text(
                ValueFormatters.usd(usdValue),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
          if (tokenCount > 0 || nftCount > 0) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                if (tokenCount > 0) _chip('${tokenCount.toInt()} tokens'),
                if (nftCount > 0) _chip('${nftCount.toInt()} NFTs'),
              ],
            )
          ]
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Exchanges view
  // ---------------------------------------------------------------------------

  Widget _buildExchanges() {
    return FutureBuilder<ExchangesSummary>(
      future: _exchangesFuture,
      builder: (context, snapshot) {
        // Stale-while-revalidate: use cached data while loading
        final data = snapshot.data ?? _lastExchanges;

        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          _lastExchanges = snapshot.data;
        }

        if (data == null) {
          if (snapshot.hasError) {
            return _ErrorView(
              message: snapshot.error.toString(),
              onRetry: () {
                setState(() {
                  _exchangesFuture = _loadExchanges();
                });
              },
            );
          }
          return const Center(child: CircularProgressIndicator());
        }
        final exchanges = data.exchanges;

        return SmartRefreshIndicator(
          onRefresh: (hard) => _refreshExchanges(hard: hard),
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
                        label: 'Connected',
                        value: '${data.totalExchanges}',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _statTile(
                        context,
                        label: 'Total Value',
                        value: ValueFormatters.compactUsd(data.totalValueUsd),
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
                _loadExchangeDetail(exchange);
              } else {
                _expanded.remove(key);
              }
            });
          },
          title: Row(
            children: [
              _exchangeLogo(context, exchange),
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
                      '${assetCount.toInt()} assets \u2022 ${configured ? 'Connected' : 'Not configured'}',
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
                  future: _loadExchangeDetail(exchange),
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
                                  _exchangeDetails.remove(key);
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
                      : '${asset.name} \u2022 ${ValueFormatters.number(asset.balance, decimals: 6)} $symbol',
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

  // ---------------------------------------------------------------------------
  // Exchange logo
  // ---------------------------------------------------------------------------

  static const _exchangeLogos = <String, String>{
    'binance': 'https://cryptologos.cc/logos/binance-coin-bnb-logo.png',
    'binance_us': 'https://cryptologos.cc/logos/binance-coin-bnb-logo.png',
    'coinbase': 'https://avatars.githubusercontent.com/u/1885080?s=64',
    'okx': 'https://avatars.githubusercontent.com/u/33779786?s=64',
    'bitget': 'https://avatars.githubusercontent.com/u/54851994?s=64',
    'gate': 'https://avatars.githubusercontent.com/u/41354999?s=64',
    'kucoin': 'https://avatars.githubusercontent.com/u/33002631?s=64',
  };

  Widget _exchangeLogo(BuildContext context, ExchangeSummaryItem exchange) {
    final key = exchange.name.toLowerCase();
    final url = exchange.logoUrl ?? _exchangeLogos[key];
    final theme = Theme.of(context);

    final fallback = CircleAvatar(
      radius: 20,
      backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.18),
      child: Text(
        exchange.displayName.isNotEmpty
            ? exchange.displayName[0].toUpperCase()
            : '?',
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
      ),
    );

    if (url == null || url.isEmpty) return fallback;

    return CircleAvatar(
      radius: 20,
      backgroundColor: Colors.transparent,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: Image.network(
          url,
          width: 40,
          height: 40,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => fallback,
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Shared helpers
  // ---------------------------------------------------------------------------

  Widget _statTile(
    BuildContext context, {
    required String label,
    required String value,
  }) {
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

  Widget _chip(String text) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text),
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
