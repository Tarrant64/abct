import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../../../core/models/connection_profile.dart';
import '../../../core/models/nft_wall.dart';
import '../../../core/network/api_client.dart';
import '../../../core/ui/app_refresh.dart';
import '../../../core/ui/haptics.dart';
import '../../../core/ui/smart_refresh.dart';
import '../../../core/ui/value_formatters.dart';

class NftsTab extends StatefulWidget {
  const NftsTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<NftsTab> createState() => _NftsTabState();
}

class _NftsTabState extends State<NftsTab> {
  static const int _pageSize = 24;

  late final ApiClient _api;
  late final Uri? _profileBaseUri;
  final ScrollController _scrollController = ScrollController();

  Map<String, String> _imageHeaders = const {};
  final List<NftWallItem> _items = <NftWallItem>[];
  final Set<String> _seen = <String>{};

  int _offset = 0;
  int? _total;
  bool _initialLoading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  String? _errorMessage;

  // Search & filtering
  String _searchQuery = '';
  String? _chainFilter;
  final _searchController = TextEditingController();

  DateTime? _lastLoadStartedAt;

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
    _profileBaseUri = Uri.tryParse(widget.profile.baseUrl);
    _scrollController.addListener(_onScroll);
    _loadInitial();
    AppRefreshSignal.instance.addListener(_onAppRefreshSignal);
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.removeListener(_onAppRefreshSignal);
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    _searchController.dispose();
    super.dispose();
  }

  /// Resume refresh. Reloading resets pagination to the first page, so skip
  /// it when the user has scrolled into the wall — freshness isn't worth
  /// yanking them back to the top.
  void _onAppRefreshSignal() {
    if (!mounted) return;
    if (_scrollController.hasClients && _scrollController.offset > 100) return;
    final last = _lastLoadStartedAt;
    if (last != null &&
        DateTime.now().difference(last) < AppRefreshSignal.minRefreshInterval) {
      return;
    }
    _loadInitial(revalidate: true);
  }

  void _onScroll() {
    if (!_scrollController.hasClients || _loadingMore || !_hasMore) return;
    final position = _scrollController.position;
    if (position.extentAfter < 700) {
      _loadMore();
    }
  }

  Future<void> _loadInitial({bool revalidate = false}) async {
    if (!mounted) return;
    // Only show loading spinner if we have no items to display.
    // This prevents a flash of empty content during pull-to-refresh.
    final isRefresh = _items.isNotEmpty;
    setState(() {
      _initialLoading = !isRefresh;
      _errorMessage = null;
    });

    try {
      _lastLoadStartedAt = DateTime.now();
      _imageHeaders = await _api.imageRequestHeaders();
      final page = await _api.getNftWall(
        limit: _pageSize,
        offset: 0,
        revalidate: revalidate,
      );
      if (!mounted) return;
      setState(() {
        // Clear and rebuild with fresh data.
        _items.clear();
        _seen.clear();
        _thumbnailUrlCache.clear();
        _fullImageUrlCache.clear();
        _offset = 0;
        _total = null;
        _hasMore = true;
        _appendPage(page);
        _initialLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _initialLoading = false;
        _errorMessage = _friendlyError(error);
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || !_hasMore) return;
    setState(() {
      _loadingMore = true;
    });

    try {
      final page = await _api.getNftWall(limit: _pageSize, offset: _offset);
      if (!mounted) return;
      setState(() {
        _appendPage(page);
        _loadingMore = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingMore = false;
      });
    }
  }

  void _appendPage(NftWallPage page) {
    _total = page.total ?? _total;

    for (final item in page.items) {
      if (_seen.add(item.stableKey)) {
        _items.add(item);
      }
    }

    _offset += page.fetchedCount;

    final exhaustedByCount = page.fetchedCount < _pageSize;
    final exhaustedByTotal = _total != null && _items.length >= _total!;
    _hasMore = !(exhaustedByCount || exhaustedByTotal);
  }

  List<NftWallItem> get _filteredItems {
    var filtered = _items.toList();
    if (_chainFilter != null && _chainFilter!.isNotEmpty) {
      filtered = filtered
          .where((item) =>
              item.chain.toLowerCase() == _chainFilter!.toLowerCase())
          .toList();
    }
    if (_searchQuery.isNotEmpty) {
      final q = _searchQuery.toLowerCase();
      filtered = filtered.where((item) {
        return item.name.toLowerCase().contains(q) ||
            (item.collectionName?.toLowerCase().contains(q) ?? false);
      }).toList();
    }
    return filtered;
  }

  List<String> get _distinctChains {
    final chains = _items.map((item) => item.chain).toSet().toList()..sort();
    return chains;
  }

  Future<void> _refresh() async {
    // Manual pull: network-first so the pull never re-serves the cache entry
    // it is refreshing.
    await _loadInitial(revalidate: true);
  }

  @override
  Widget build(BuildContext context) {
    // Stale-while-revalidate: only show spinner on true cold start (no items
    // loaded yet). If we have items from a previous load, keep showing them
    // while the refresh happens in the background.
    if (_initialLoading && _items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null && _items.isEmpty) {
      return _ErrorState(
        message: _errorMessage!,
        onRetry: _loadInitial,
      );
    }

    final filtered = _filteredItems;
    final chains = _distinctChains;

    return SmartRefreshIndicator(
      onRefresh: (hard) => _refresh(),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth;
          final crossAxisCount = width >= 1100
              ? 4
              : width >= 760
                  ? 3
                  : 2;

          return CustomScrollView(
            controller: _scrollController,
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              // Search and filter bar
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _searchController,
                          decoration: InputDecoration(
                            hintText: 'Search NFTs...',
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
                              child: Text('All'),
                            ),
                            for (final chain in chains)
                              DropdownMenuItem(
                                value: chain,
                                child:
                                    Text(ValueFormatters.titleCase(chain)),
                              ),
                          ],
                          onChanged: (value) =>
                              setState(() => _chainFilter = value),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              if (filtered.isEmpty)
                const SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: Text('No NFT images found yet.')),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.all(20),
                  sliver: SliverGrid(
                    delegate: SliverChildBuilderDelegate(
                      (context, index) => _galleryTile(context, filtered[index]),
                      childCount: filtered.length,
                    ),
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: crossAxisCount,
                      mainAxisSpacing: 12,
                      crossAxisSpacing: 12,
                      childAspectRatio: 0.9,
                    ),
                  ),
                ),
              if (_loadingMore)
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.only(bottom: 20),
                    child: Center(child: CircularProgressIndicator()),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  /// Resolved image URLs memoized per item — the grid rebuilds on every
  /// scroll/search/selection setState and URL resolution (encoding + URI
  /// parsing) is pure per item, so derive each once. Cleared on reload in
  /// [_loadInitial].
  final Map<String, String?> _thumbnailUrlCache = {};
  final Map<String, String?> _fullImageUrlCache = {};

  String? _thumbnailUrl(NftWallItem item) {
    return _thumbnailUrlCache.putIfAbsent(item.stableKey, () {
      if (item.chain.isNotEmpty &&
          item.assetId.isNotEmpty &&
          item.chain != 'unknown') {
        return _resolveImageUrl(
          '/nfts/images/${Uri.encodeComponent(item.chain)}/${Uri.encodeComponent(item.assetId)}/thumbnail',
        );
      }
      return _resolveImageUrl(item.thumbnailUrl);
    });
  }

  String? _fullImageUrl(NftWallItem item) {
    return _fullImageUrlCache.putIfAbsent(item.stableKey, () {
      if (item.chain.isNotEmpty &&
          item.assetId.isNotEmpty &&
          item.chain != 'unknown') {
        return _resolveImageUrl(
          '/nfts/images/${Uri.encodeComponent(item.chain)}/${Uri.encodeComponent(item.assetId)}',
        );
      }
      return _resolveImageUrl(item.imageUrl) ??
          _resolveImageUrl(item.thumbnailUrl);
    });
  }

  String? _resolveImageUrl(String? raw) {
    if (raw == null) return null;
    final value = raw.trim();
    if (value.isEmpty) return null;

    if (value.startsWith('ar://')) {
      final path = value.replaceFirst('ar://', '').trim();
      if (path.isEmpty) return null;
      return 'https://arweave.net/$path';
    }

    if (value.startsWith('ipfs://')) {
      final cidPath = value.replaceFirst('ipfs://', '');
      final normalized =
          cidPath.startsWith('ipfs/') ? cidPath : 'ipfs/$cidPath';
      return 'https://ipfs.io/$normalized';
    }

    final uri = Uri.tryParse(value);
    if (uri == null) return null;
    if (uri.hasScheme && (uri.scheme == 'http' || uri.scheme == 'https')) {
      return value;
    }
    if (!uri.hasScheme &&
        (value.startsWith('bafy') || value.startsWith('Qm'))) {
      return 'https://ipfs.io/ipfs/$value';
    }
    if (!uri.hasScheme && value.startsWith('/')) {
      final base = _profileBaseUri;
      if (base == null) return null;
      return base.resolve(value).toString();
    }
    return null;
  }

  Map<String, String>? _headersForUrl(String? imageUrl) {
    if (imageUrl == null || imageUrl.isEmpty) return null;

    final target = Uri.tryParse(imageUrl);
    final base = _profileBaseUri;
    if (target == null || base == null) return null;

    final sameOrigin = target.scheme == base.scheme &&
        target.host == base.host &&
        target.port == base.port;

    if (!sameOrigin || _imageHeaders.isEmpty) {
      return null;
    }
    return _imageHeaders;
  }

  Widget _galleryTile(BuildContext context, NftWallItem item) {
    final thumbnailUrl = _thumbnailUrl(item);
    final fullImageUrl = _fullImageUrl(item);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () {
          Haptics.light();
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => _NftDetailsScreen(
                item: item,
                fullImageUrl: fullImageUrl,
                imageHeaders: _headersForUrl(fullImageUrl),
              ),
            ),
          );
        },
        child: Ink(
          decoration: BoxDecoration(
            border:
                Border.all(color: Theme.of(context).colorScheme.outlineVariant),
            borderRadius: BorderRadius.circular(12),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (thumbnailUrl != null)
                  CachedNetworkImage(
                    imageUrl: thumbnailUrl,
                    fit: BoxFit.cover,
                    httpHeaders: _headersForUrl(thumbnailUrl),
                    memCacheWidth: 300,
                    memCacheHeight: 300,
                    fadeInDuration: const Duration(milliseconds: 120),
                    placeholder: (_, __) => _galleryPlaceholder(context, item),
                    errorWidget: (_, __, ___) =>
                        _galleryPlaceholder(context, item),
                  )
                else
                  _galleryPlaceholder(context, item),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.black.withValues(alpha: 0.04),
                        Colors.black.withValues(alpha: 0.6),
                      ],
                    ),
                  ),
                ),
                Positioned(
                  left: 10,
                  right: 10,
                  bottom: 10,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        item.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (item.collectionName != null &&
                          item.collectionName!.trim().isNotEmpty)
                        Text(
                          item.collectionName!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 12,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _galleryPlaceholder(BuildContext context, NftWallItem item) {
    final scheme = Theme.of(context).colorScheme;
    final initials =
        item.name.trim().isEmpty ? '?' : item.name.trim()[0].toUpperCase();

    return Container(
      color: scheme.surfaceContainerHighest,
      alignment: Alignment.center,
      child: Text(
        initials,
        style: TextStyle(
          fontSize: 36,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface.withValues(alpha: 0.7),
        ),
      ),
    );
  }

  String _friendlyError(Object? error) {
    final message = error?.toString() ?? 'Unable to load NFT data.';
    return message.replaceFirst('Exception: ', '');
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

class _NftDetailsScreen extends StatelessWidget {
  const _NftDetailsScreen({
    required this.item,
    this.fullImageUrl,
    this.imageHeaders,
  });

  final NftWallItem item;
  final String? fullImageUrl;
  final Map<String, String>? imageHeaders;

  @override
  Widget build(BuildContext context) {
    final hasImage = fullImageUrl != null && fullImageUrl!.isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: Text(item.name),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: AspectRatio(
              aspectRatio: 1,
              child: hasImage
                  ? CachedNetworkImage(
                      imageUrl: fullImageUrl!,
                      fit: BoxFit.cover,
                      httpHeaders: imageHeaders,
                      fadeInDuration: const Duration(milliseconds: 120),
                      placeholder: (_, __) =>
                          _detailsPlaceholder(context, item),
                      errorWidget: (_, __, ___) =>
                          _detailsPlaceholder(context, item),
                    )
                  : _detailsPlaceholder(context, item),
            ),
          ),
          const SizedBox(height: 16),
          _detailsRow('Blockchain', ValueFormatters.titleCase(item.chain)),
          _detailsRow('Asset ID', item.assetId),
          if (item.collectionName != null && item.collectionName!.isNotEmpty)
            _detailsRow('Collection', item.collectionName!),
          if (item.detailsUrl != null && item.detailsUrl!.isNotEmpty)
            _detailsRow('Details URL', item.detailsUrl!),
        ],
      ),
    );
  }

  static Widget _detailsPlaceholder(
    BuildContext context,
    NftWallItem item,
  ) {
    return Container(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      alignment: Alignment.center,
      child: Text(
        item.name.trim().isEmpty ? '?' : item.name.trim()[0].toUpperCase(),
        style: TextStyle(
          fontSize: 52,
          fontWeight: FontWeight.w700,
          color:
              Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.65),
        ),
      ),
    );
  }

  static Widget _detailsRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 2),
          Text(value),
        ],
      ),
    );
  }
}
