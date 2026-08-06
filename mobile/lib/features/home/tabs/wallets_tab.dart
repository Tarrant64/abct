import 'dart:developer' as developer;

import 'package:flutter/material.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/wallets_summary.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_interceptor.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/haptics.dart';
import '../../../core/ui/section_card.dart';
import '../../../core/ui/value_formatters.dart';
import '../../wallets/add_wallet_screen.dart';

class WalletsTab extends StatefulWidget {
  const WalletsTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<WalletsTab> createState() => _WalletsTabState();
}

class _WalletsTabState extends State<WalletsTab> {
  late final ApiClient _api;
  late Future<WalletsSummary> _future;
  WalletsSummary? _lastData; // In-memory cache for instant rendering
  String? _selectedBlockchain;
  bool _hideZeroBalances = true;
  DateTime? _lastLoadStartedAt;
  void Function()? _disposeRevalidation;

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
    _future = _load();
    AppRefreshSignal.instance.addListener(_onAppRefreshSignal);
    _disposeRevalidation = CacheInterceptor.onRevalidated(
      '/api/mobile/wallets',
      (_) => _silentReload(),
    );
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    _disposeRevalidation?.call();
    super.dispose();
  }

  Future<WalletsSummary> _load({bool revalidate = false}) {
    _lastLoadStartedAt = DateTime.now();
    return _api.getWallets(
      blockchain: _selectedBlockchain,
      revalidate: revalidate,
    );
  }

  /// Test hook: backdates the last-load timestamp so a resume signal is not
  /// suppressed by the min-interval guard.
  @visibleForTesting
  void debugBackdateLastLoad(Duration by) {
    _lastLoadStartedAt = DateTime.now().subtract(by);
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

  /// Reloads from the cache-backed API without disturbing the visible data;
  /// [_lastData] keeps the current content on screen until the new payload
  /// lands. Used for resume refreshes and revalidation pickups.
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

  /// Navigate to the Add Wallet screen, then refresh if a wallet was added.
  Future<void> _navigateToAddWallet() async {
    final added = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => AddWalletScreen(profile: widget.profile),
      ),
    );
    if (added == true && mounted) {
      setState(() {
        _future = _load();
      });
    }
  }

  /// Show a confirmation dialog and delete the wallet if confirmed.
  Future<void> _confirmDeleteWallet(WalletSummaryItem wallet) async {
    final displayName = wallet.label.isNotEmpty
        ? wallet.label
        : ValueFormatters.shortenAddress(wallet.address);

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove Wallet'),
        content: Text(
          'Are you sure you want to remove "$displayName"?\n\n'
          'This will remove the wallet and all its tracked data '
          'from your portfolio.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
              foregroundColor: Theme.of(context).colorScheme.onError,
            ),
            child: const Text('Remove'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    try {
      // Build the address string, prefixing with blockchain for non-standard
      // chains so the backend can find the correct wallet.
      final deleteAddress = _buildDeleteAddress(wallet);
      await _api.deleteWallet(address: deleteAddress);

      if (!mounted) return;
      Haptics.success();

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Removed "$displayName".')),
      );

      // Reload the wallet list.
      setState(() {
        _future = _load();
      });
    } catch (e) {
      if (!mounted) return;
      Haptics.error();

      developer.log(
        'Failed to remove wallet: $e',
        name: 'WalletsTab',
      );
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to remove wallet: ${_friendlyError(e)}'),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    }
  }

  String _friendlyError(Object e) {
    final msg = e.toString();
    if (msg.contains('403')) return 'Access denied. Please check your credentials.';
    if (msg.contains('404')) return 'Wallet not found.';
    if (msg.contains('409')) return 'This wallet has already been added.';
    return 'Something went wrong. Please try again.';
  }

  /// Build the address string for deletion.
  ///
  /// Some chains (e.g. polygon, base, arbitrum) share the 0x address format with
  /// Ethereum, so we prefix them with the chain name to help the backend
  /// disambiguate.
  String _buildDeleteAddress(WalletSummaryItem wallet) {
    const prefixedChains = {
      'polygon', 'base', 'arbitrum', 'avalanche', 'bsc',
      'kaia', 'vechain', 'iota',
    };
    final chain = wallet.blockchain.toLowerCase();
    if (prefixedChains.contains(chain)) {
      return '$chain:${wallet.address}';
    }
    return wallet.address;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<WalletsSummary>(
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

        return Stack(
          children: [
            RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 80),
                children: [
                  SectionCard(
                    title: 'Wallets',
                    subtitle:
                        'Updated ${ValueFormatters.timestamp(lastUpdated)}',
                    trailing: IconButton(
                      onPressed: _navigateToAddWallet,
                      icon: const Icon(Icons.add_circle_outline),
                      tooltip: 'Add wallet',
                    ),
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
                            value:
                                ValueFormatters.compactUsd(visibleTotalValue),
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
                          subtitle: const Text(
                              'Enabled by default for a cleaner list.'),
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
                                child:
                                    Text(ValueFormatters.titleCase(chain)),
                              )
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedBlockchain = value;
                              _future = _load();
                            });
                          },
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (visibleWallets.isEmpty)
                    SectionCard(
                      title: 'Wallet List',
                      child: Column(
                        children: [
                          const Text(
                              'No wallets found for the current filters.'),
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                            onPressed: _navigateToAddWallet,
                            icon: const Icon(Icons.add, size: 18),
                            label: const Text('Add your first wallet'),
                          ),
                        ],
                      ),
                    )
                  else
                    SectionCard(
                      title: 'Wallet List',
                      subtitle: 'Swipe left on a wallet to remove it.',
                      child: Column(
                        children: [
                          for (final wallet in visibleWallets)
                            _dismissibleWalletTile(context, wallet),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            // Floating action button
            Positioned(
              bottom: 16,
              right: 16,
              child: FloatingActionButton(
                onPressed: _navigateToAddWallet,
                tooltip: 'Add wallet',
                child: const Icon(Icons.add),
              ),
            ),
          ],
        );
      },
    );
  }

  /// Wraps a wallet tile in a [Dismissible] for swipe-to-delete.
  Widget _dismissibleWalletTile(
      BuildContext context, WalletSummaryItem wallet) {
    final theme = Theme.of(context);

    return Dismissible(
      key: ValueKey('wallet_${wallet.id}_${wallet.address}'),
      direction: DismissDirection.endToStart,
      confirmDismiss: (_) async {
        await _confirmDeleteWallet(wallet);
        // Always return false -- we handle the reload in _confirmDeleteWallet.
        return false;
      },
      background: Container(
        alignment: Alignment.centerRight,
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.only(right: 20),
        decoration: BoxDecoration(
          color: theme.colorScheme.error,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Icon(
          Icons.delete_outline,
          color: theme.colorScheme.onError,
        ),
      ),
      child: _walletTile(context, wallet),
    );
  }

  Widget _walletTile(BuildContext context, WalletSummaryItem wallet) {
    final balance = wallet.balance;
    final label = wallet.label;
    final address = wallet.address;
    final blockchain = wallet.blockchain;
    final logoUrl = wallet.blockchainLogoUrl;
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
              _chainLogo(context, blockchain, logoUrl),
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

  Widget _chainLogo(BuildContext context, String blockchain, String? logoUrl) {
    final theme = Theme.of(context);
    final placeholder = CircleAvatar(
      radius: 16,
      backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.18),
      child: Text(
        blockchain.isNotEmpty ? blockchain[0].toUpperCase() : '?',
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
      ),
    );

    if (logoUrl == null || logoUrl.isEmpty) {
      return placeholder;
    }

    return CircleAvatar(
      radius: 16,
      backgroundColor: Colors.transparent,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Image.network(
          logoUrl,
          width: 32,
          height: 32,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => placeholder,
        ),
      ),
    );
  }

  Widget _statTile(BuildContext context,
      {required String label, required String value}) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border:
            Border.all(color: Theme.of(context).colorScheme.outlineVariant),
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
