import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/staking_summary.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_interceptor.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/chain_logo.dart';
import '../../../core/ui/section_card.dart';
import '../../../core/ui/smart_refresh.dart';
import '../../../core/ui/value_formatters.dart';

class StakingTab extends StatefulWidget {
  const StakingTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<StakingTab> createState() => _StakingTabState();
}

class _StakingTabState extends State<StakingTab> {
  late final ApiClient _api;
  late Future<StakingSummary> _future;
  StakingSummary? _lastData; // In-memory cache for instant rendering
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
      '/api/mobile/defi/staking',
      (_) => _silentReload(),
    );
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    _disposeRevalidation?.call();
    super.dispose();
  }

  Future<StakingSummary> _load() {
    _lastLoadStartedAt = DateTime.now();
    return _api.getStaking();
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

  Future<void> _smartRefresh(bool hard) async {
    final data = await _api.getStaking(refresh: hard, revalidate: !hard);
    if (!mounted) return;
    setState(() {
      _lastData = data;
      _future = Future.value(data);
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<StakingSummary>(
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
        final groups = _groupByProtocol(data.positions);

        return SmartRefreshIndicator(
          onRefresh: _smartRefresh,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              SectionCard(
                title: 'Staking & DeFi',
                subtitle:
                    'Updated ${ValueFormatters.timestamp(data.lastUpdated?.toIso8601String())}',
                child: Row(
                  children: [
                    Expanded(
                      child: _statTile(
                        context,
                        'Total Staked',
                        ValueFormatters.compactUsd(
                          data.totalStakedUsd,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _statTile(
                        context,
                        'Total Rewards',
                        ValueFormatters.compactUsd(
                          data.totalRewardsUsd,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Positions',
                child: groups.isEmpty
                    ? const Text('No staking positions found.')
                    : Column(
                        children: [
                          for (final group in groups)
                            _groupSection(context, group),
                        ],
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  static const _blockchainSymbols = <String, String>{
    'cardano': 'ADA',
    'bitcoin': 'BTC',
    'ethereum': 'ETH',
    'solana': 'SOL',
    'polygon': 'POL',
    'base': 'ETH',
    'algorand': 'ALGO',
    'bsc': 'BNB',
    'arbitrum': 'ETH',
    'avalanche': 'AVAX',
    'tron': 'TRX',
    'xrp': 'XRP',
    'hedera': 'HBAR',
    'multiversx': 'EGLD',
    'sui': 'SUI',
    'aptos': 'APT',
    'cosmos': 'ATOM',
    'near': 'NEAR',
    'polkadot': 'DOT',
  };

  /// Friendly names for known protocol identifiers; anything else falls back
  /// to title-casing whatever the payload carries.
  static const _protocolDisplayNames = <String, String>{
    'cardano': 'Cardano',
    'native': 'Cardano',
    'native_delegation': 'Cardano',
    'indigo': 'Indigo',
    'liqwid': 'Liqwid',
    'strike': 'Strike',
    'strike_finance': 'Strike',
    'iagon': 'Iagon',
  };

  /// Protocol-token symbols for group-header logos, served by the
  /// dashboard's /images/token library. Needed because a protocol's
  /// positions may all be chain-denominated (e.g. ADA-based Strike V2
  /// trading/vault rows), so no position row carries the protocol mark.
  static const _protocolTokenSymbols = <String, String>{
    'strike': 'STRIKE',
    'indigo': 'INDY',
    'liqwid': 'LQ',
    'iagon': 'IAG',
  };

  static String _protocolDisplayName(String protocol) {
    final normalized = protocol.trim().toLowerCase();
    return _protocolDisplayNames[normalized] ??
        ValueFormatters.titleCase(protocol);
  }

  /// Groups positions by protocol display name (so aliases like "native" and
  /// "cardano" collapse together), keeping each group's positions in payload
  /// order and sorting groups by total staked USD descending.
  static List<_ProtocolGroup> _groupByProtocol(
    List<StakingPosition> positions,
  ) {
    final byKey = <String, _ProtocolGroup>{};
    for (final position in positions) {
      final displayName = _protocolDisplayName(position.protocol);
      final key = displayName.toLowerCase();
      byKey
          .putIfAbsent(key, () => _ProtocolGroup(key, displayName))
          .positions
          .add(position);
    }
    return byKey.values.toList()
      ..sort((a, b) => b.totalStakedUsd.compareTo(a.totalStakedUsd));
  }

  Widget _positionLogo(
    StakingPosition position,
    String chainSymbol,
    String baseUrl,
  ) {
    // For DeFi positions, use the staked token symbol; for native staking,
    // fall back to the chain symbol.
    final tokenSymbol = position.stakedSymbol.isNotEmpty
        ? position.stakedSymbol.toUpperCase()
        : chainSymbol;
    final isDeFi = position.stakedSymbol.isNotEmpty &&
        position.stakedSymbol.toUpperCase() != chainSymbol;

    // Primary: dashboard image endpoint (CoinGecko CDN cache + LogoKit fallback)
    final dashboardUrl = '$baseUrl/images/token/$tokenSymbol';
    // Secondary: backend-provided logoUrl
    final backendUrl = position.logoUrl;

    final fallback = ChainLogo(symbol: chainSymbol, size: 32);

    Widget tokenImage = CachedNetworkImage(
      imageUrl: dashboardUrl,
      width: 32,
      height: 32,
      fit: BoxFit.cover,
      placeholder: (_, __) => fallback,
      errorWidget: (_, __, ___) => backendUrl.isNotEmpty
          ? CachedNetworkImage(
              imageUrl: backendUrl,
              width: 32,
              height: 32,
              fit: BoxFit.cover,
              placeholder: (_, __) => fallback,
              errorWidget: (_, __, ___) => fallback,
            )
          : fallback,
    );

    // Wrap the main logo in a clip oval
    final mainLogo = ClipOval(
      child: SizedBox(width: 32, height: 32, child: tokenImage),
    );

    // For DeFi tokens, overlay a small chain badge in the bottom-right
    if (!isDeFi) return mainLogo;

    return SizedBox(
      width: 38,
      height: 38,
      child: Stack(
        children: [
          Positioned(top: 0, left: 0, child: mainLogo),
          Positioned(
            right: 0,
            bottom: 0,
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: Theme.of(context).colorScheme.surface,
                  width: 1.5,
                ),
              ),
              child: ChainLogo(symbol: chainSymbol, size: 16),
            ),
          ),
        ],
      ),
    );
  }

  /// Group headers show the PROTOCOL mark, not the first position's token:
  /// known protocols resolve their token symbol through the dashboard image
  /// library; unknown ones fall back to the first protocol-token position in
  /// the group, then to the first position (chain logo for pure native
  /// delegation groups like Cardano — which is the correct mark there).
  Widget _groupLogo(_ProtocolGroup group, String chainSymbol, String baseUrl) {
    final protocolSymbol = _protocolTokenSymbols[group.key];
    if (protocolSymbol != null) {
      // Fall back to the protocol's initial, NOT the chain logo: a failed
      // protocol-mark load showing the ADA mark is indistinguishable from
      // the wrong-logo bug this resolution exists to fix.
      final fallback = _protocolInitialAvatar(group.displayName);
      return ClipOval(
        child: SizedBox(
          width: 32,
          height: 32,
          child: CachedNetworkImage(
            imageUrl: '$baseUrl/images/token/$protocolSymbol',
            width: 32,
            height: 32,
            fit: BoxFit.cover,
            placeholder: (_, __) => fallback,
            errorWidget: (_, __, ___) => fallback,
          ),
        ),
      );
    }

    for (final position in group.positions) {
      final symbol = position.stakedSymbol.toUpperCase();
      if (symbol.isNotEmpty && symbol != chainSymbol) {
        return _positionLogo(position, chainSymbol, baseUrl);
      }
    }
    return _positionLogo(group.positions.first, chainSymbol, baseUrl);
  }

  Widget _protocolInitialAvatar(String name) {
    return CircleAvatar(
      radius: 16,
      backgroundColor:
          Theme.of(context).colorScheme.primary.withValues(alpha: 0.14),
      child: Text(
        name.isEmpty ? '?' : name.substring(0, 1).toUpperCase(),
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
      ),
    );
  }

  /// One section per protocol: single-position groups render as a plain
  /// position tile; multi-position groups render a collapsed summary row
  /// that expands to the individual positions. Expansion state lives in
  /// [_expanded] keyed by protocol, so silent reloads (which just swap the
  /// data behind the same keyed widgets) never collapse an open group.
  Widget _groupSection(BuildContext context, _ProtocolGroup group) {
    if (group.positions.length == 1) {
      return _positionTile(context, group.positions.first);
    }

    final key = group.key;
    final isExpanded = _expanded.contains(key);
    final chainSymbol =
        _blockchainSymbols[group.positions.first.blockchain.toLowerCase()] ??
            group.positions.first.blockchain.toUpperCase();
    final noun = group.allDelegations ? 'delegations' : 'positions';

    return Container(
      key: ValueKey('staking-group-$key'),
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
              } else {
                _expanded.remove(key);
              }
            });
          },
          title: Row(
            children: [
              _groupLogo(group, chainSymbol, widget.profile.baseUrl),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      group.displayName,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${group.positions.length} $noun',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    if (group.hasEstimatedValue) ...[
                      const SizedBox(height: 2),
                      _estimatedValueBadge(context),
                    ],
                  ],
                ),
              ),
              Text(
                ValueFormatters.usd(group.totalStakedUsd),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
          children: [
            if (isExpanded)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Column(
                  children: [
                    for (final position in group.positions)
                      _positionTile(context, position),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// Subtle marker for positions the backend priced via a fallback source
  /// (priced == false) so estimates can't masquerade as exact valuations.
  Widget _estimatedValueBadge(BuildContext context) {
    final style = Theme.of(context).textTheme.bodySmall;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.info_outline, size: 13, color: style?.color),
        const SizedBox(width: 3),
        Text('value estimated', style: style),
      ],
    );
  }

  Widget _positionTile(BuildContext context, StakingPosition position) {
    final poolName = position.poolName;
    final poolTicker = position.poolTicker;
    final blockchain = position.blockchain;
    final delegated = position.delegatedAmount;
    final delegatedUsd = position.delegatedUsd;
    final rewards = position.rewardsLifetime;
    final rewardsUsd = position.rewardsUsd;
    final apy = position.apy;
    final active = position.active;
    final chainSymbol = _blockchainSymbols[blockchain.toLowerCase()] ??
        blockchain.toUpperCase();

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
              _positionLogo(position, chainSymbol, widget.profile.baseUrl),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  poolTicker.isEmpty ? poolName : '$poolName ($poolTicker)',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              _chip(active ? 'Active' : 'Inactive'),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Text(
                ValueFormatters.titleCase(blockchain),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (!position.priced) ...[
                const SizedBox(width: 8),
                _estimatedValueBadge(context),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  'Delegated: ${ValueFormatters.number(delegated)}',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              Text(ValueFormatters.usd(delegatedUsd)),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: Text('Rewards: ${ValueFormatters.number(rewards)}'),
              ),
              Text(ValueFormatters.usd(rewardsUsd)),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'APY: ${ValueFormatters.percent(apy)}',
            style: const TextStyle(fontWeight: FontWeight.w600),
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

  Widget _chip(String text) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: scheme.surfaceVariant.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text),
    );
  }
}

class _ProtocolGroup {
  _ProtocolGroup(this.key, this.displayName);

  final String key;
  final String displayName;
  final List<StakingPosition> positions = [];

  double get totalStakedUsd =>
      positions.fold(0, (sum, position) => sum + position.delegatedUsd);

  bool get hasEstimatedValue => positions.any((position) => !position.priced);

  bool get allDelegations =>
      positions.every((position) => position.isNativeDelegation);
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
