import 'dart:async';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/foundation.dart';

import 'cache_store.dart';

/// Dio interceptor implementing stale-while-revalidate caching.
///
/// On every GET request:
/// 1. If fresh cache exists → return immediately (HIT). Entries older than
///    [revalidateAfter] additionally trigger a background revalidation so
///    the cache (and any [onRevalidated] listeners) get fresh data.
/// 2. If stale cache exists → return immediately (STALE) and trigger a
///    background revalidation.
/// 3. If no cache exists → pass through to the network.
///
/// On network errors for GET requests, falls back to any cached data —
/// except for hard refreshes (`refresh=true`), whose failures surface so the
/// UI can tell the user instead of silently re-showing the cached number.
///
/// This eliminates loading spinners: the UI always gets data immediately
/// (fresh or stale), and background refreshes keep it current. UI layers
/// subscribe via [onRevalidated] to swap in fresh data as soon as a
/// background revalidation lands, instead of waiting for the next request.
class CacheInterceptor extends Interceptor {
  CacheInterceptor({
    CacheStore? store,
    HttpClient Function()? httpClientFactory,
    Duration revalidateAfter = const Duration(seconds: 30),
    Duration staleFollowUpDelay = const Duration(seconds: 35),
  })  : _store = store ?? CacheStore.instance,
        _httpClientFactory = httpClientFactory,
        _revalidateAfter = revalidateAfter,
        _staleFollowUpDelay = staleFollowUpDelay;

  /// Request `Options.extra` key marking a network-first revalidation
  /// (manual pull-to-refresh): the cache is not consulted for serving, so a
  /// pull can never be re-served the entry it is trying to refresh. The
  /// response still updates the cache, and connection errors still fall back
  /// to cached data.
  static const String revalidateExtra = 'revalidate';

  /// Request `Options.extra` key marking a scheduled stale-payload follow-up
  /// (see [_maybeScheduleFollowUp]). Its response never schedules another
  /// follow-up: one delayed retry per stale payload, not a polling chain.
  static const String _followUpExtra = '_staleFollowUp';

  /// Request `Options.extra` key stamped in [onRequest] with the store's
  /// clear-fence generation. [onResponse] drops the cache write if the store
  /// was cleared (logout) while the request was on the wire — otherwise a
  /// response fetched with the previous session's auth would be persisted
  /// into the next session's empty cache.
  static const String generationExtra = '_cacheStoreGeneration';

  final CacheStore _store;

  /// Factory for the [HttpClient] used by background revalidation requests.
  /// Must match the primary client's configuration (certificate pinning);
  /// `ApiClient.create` supplies the pinned factory.
  final HttpClient Function()? _httpClientFactory;

  /// Fresh cache entries younger than this are served without any network
  /// activity; older (but still fresh) entries are served instantly and
  /// revalidated in the background.
  final Duration _revalidateAfter;

  /// Delay before the one-shot follow-up revalidation fired when a network
  /// response's own `last_updated` is older than the path's TTL (the server
  /// answered from ITS stale cache and is recomputing in the background —
  /// PRICE-1). Long enough for the server recompute to land, short enough
  /// that the user is probably still looking at the screen.
  final Duration _staleFollowUpDelay;

  /// Pending one-shot follow-up timers, keyed by full URL string.
  static final Map<String, Timer> _pendingFollowUps = {};

  /// Track in-flight background revalidations to avoid duplicate requests.
  /// Keys are full URL strings; each entry remembers the store generation it
  /// was started under so a doomed pre-logout revalidation neither blocks a
  /// fresh post-login one nor gets its result used.
  static final Map<String, _PendingRevalidation> _pendingRevalidations = {};

  /// Listeners notified when a background revalidation completes with fresh
  /// data. UI layers can subscribe to seamlessly update displayed content.
  /// Key: exact request path. Value: callbacks receiving the fresh response
  /// data.
  static final Map<String, List<void Function(dynamic freshData)>>
      _revalidationListeners = {};

  /// Register a callback invoked when a background revalidation completes
  /// with fresh data for a request whose URL path is exactly [path].
  ///
  /// Matching is on the request's URL path component only — no host, no
  /// query string — and is EXACT: `/api/mobile/wallets` receives events for
  /// `/api/mobile/wallets?include_balances=true` but NOT for
  /// `/api/mobile/wallets/123`. Register a separate listener per endpoint;
  /// there is deliberately no prefix matching, so a payload-consuming
  /// callback can never be handed a different endpoint's body.
  ///
  /// Returns a disposal function that removes the listener.
  static void Function() onRevalidated(
      String path, void Function(dynamic freshData) callback) {
    _revalidationListeners.putIfAbsent(path, () => []).add(callback);
    return () {
      _revalidationListeners[path]?.remove(callback);
      if (_revalidationListeners[path]?.isEmpty ?? false) {
        _revalidationListeners.remove(path);
      }
    };
  }

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    // FAIL-OPEN INVARIANT: this callback is async void, so an exception
    // escaping after an await is an uncaught zone error — Dio never sees it,
    // the handler is never advanced, and the request future stays pending
    // forever (no Dio timeout applies before dispatch). Any cache-layer
    // failure must therefore degrade to a plain network request, not a hang.
    try {
      if (options.method.toUpperCase() != 'GET') {
        return handler.next(options);
      }

      // Stamp the clear-fence generation so onResponse can tell whether the
      // store was cleared (logout) while this request was on the wire.
      options.extra[generationExtra] = _store.generation;

      // Allow explicit cache bypass (hard refresh).
      final refresh = options.queryParameters['refresh'];
      if (refresh == true || refresh == 'true') {
        return handler.next(options);
      }

      // Network-first revalidation (soft pull-to-refresh): skip cache serving
      // so the pull always fetches, while onResponse still updates the cache
      // and onError still falls back to cached data when offline.
      if (options.extra[revalidateExtra] == true) {
        return handler.next(options);
      }

      final url = options.uri.toString();
      final entry = await _store.readWithMeta(url);

      if (entry != null) {
        if (entry.isFresh) {
          // Fresh cache hit — return immediately. Entries older than the
          // revalidation threshold still refresh in the background so the UI
          // (via onRevalidated listeners) converges on live data instead of
          // showing balances up to a full TTL old on app open.
          if (entry.age >= _revalidateAfter) {
            _backgroundRevalidate(options);
          }
          return handler.resolve(
            Response(
              requestOptions: options,
              statusCode: 200,
              data: entry.data,
              headers: Headers.fromMap({
                'x-cache': ['HIT'],
                'x-cache-age': ['${entry.age.inSeconds}'],
              }),
            ),
            true,
          );
        }

        // Stale cache — return immediately, revalidate in the background.
        // This is the key to eliminating loading spinners: the UI gets data
        // now, and fresh data updates the cache for the next access.
        _backgroundRevalidate(options);

        return handler.resolve(
          Response(
            requestOptions: options,
            statusCode: 200,
            data: entry.data,
            headers: Headers.fromMap({
              'x-cache': ['STALE'],
              'x-cache-age': ['${entry.age.inSeconds}'],
            }),
          ),
          true,
        );
      }

      // No cache at all — must go to network.
      handler.next(options);
    } catch (error, stackTrace) {
      developer.log(
        'Cache lookup failed for ${options.uri} — passing through to network',
        name: 'CacheInterceptor',
        error: error,
        stackTrace: stackTrace,
      );
      if (!handler.isCompleted) handler.next(options);
    }
  }

  @override
  void onResponse(
    Response response,
    ResponseInterceptorHandler handler,
  ) async {
    // The cache write happens BEFORE handler.next so the entry is readable
    // the moment the caller has the response — but a failed write must never
    // withhold a response the network already delivered (see the fail-open
    // note on [onRequest]), so it is fenced off from the handler call.
    try {
      final method = response.requestOptions.method.toUpperCase();
      final status = response.statusCode ?? 0;

      // Responses served from this cache carry an x-cache header (see
      // onRequest). Never re-write those: doing so would re-stamp stale data
      // as fresh for a full TTL, deferring revalidation indefinitely.
      final servedFromCache = response.headers.value('x-cache') != null;

      // Drop the write if the store was cleared (logout) after this request
      // started: the body was fetched under the previous session and must not
      // seed the next session's cache.
      final requestGeneration =
          response.requestOptions.extra[generationExtra] as int?;
      final clearedMidFlight =
          requestGeneration != null && requestGeneration != _store.generation;

      if (method == 'GET' &&
          status >= 200 &&
          status < 300 &&
          !servedFromCache &&
          !clearedMidFlight) {
        final url = response.requestOptions.uri.toString();
        final ttl = _ttlForPath(response.requestOptions.path);
        await _store.write(
          url,
          response.data,
          ttl,
          etag: response.headers.value('etag'),
        );
        _maybeScheduleFollowUp(response.requestOptions, response.data);
      }
    } catch (error, stackTrace) {
      developer.log(
        'Cache write failed for ${response.requestOptions.uri} — '
        'delivering response uncached',
        name: 'CacheInterceptor',
        error: error,
        stackTrace: stackTrace,
      );
    }

    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    // A failed stale-fallback lookup must surface the ORIGINAL network error
    // rather than leave the request future pending (see the fail-open note
    // on [onRequest]).
    try {
      final method = err.requestOptions.method.toUpperCase();
      if (method != 'GET') {
        return handler.next(err);
      }

      // Only attempt stale fallback for connection-level errors.
      final isConnError = err.type == DioExceptionType.connectionTimeout ||
          err.type == DioExceptionType.receiveTimeout ||
          err.type == DioExceptionType.sendTimeout ||
          err.type == DioExceptionType.connectionError;

      if (!isConnError) {
        return handler.next(err);
      }

      // A hard refresh (refresh=true) is the user explicitly demanding live
      // data. Answering its failure with the cached payload makes an
      // unreachable server indistinguishable from a working refresh — the
      // number "just never changes". Surface the error; soft paths below
      // keep the silent fallback.
      final refresh = err.requestOptions.queryParameters['refresh'];
      if (refresh == true || refresh == 'true') {
        return handler.next(err);
      }

      final url = err.requestOptions.uri.toString();
      final stale = await _store.readStale(url);
      if (stale != null) {
        return handler.resolve(
          Response(
            requestOptions: err.requestOptions,
            statusCode: 200,
            data: stale,
            headers: Headers.fromMap({
              'x-cache': ['STALE'],
            }),
          ),
        );
      }

      handler.next(err);
    } catch (error, stackTrace) {
      developer.log(
        'Stale fallback failed for ${err.requestOptions.uri} — '
        'surfacing the original error',
        name: 'CacheInterceptor',
        error: error,
        stackTrace: stackTrace,
      );
      if (!handler.isCompleted) handler.next(err);
    }
  }

  /// Trigger a background network request to refresh the cache for [options].
  ///
  /// The result is written to the cache store so the next request gets fresh
  /// data. If listeners are registered, they are notified with the fresh data
  /// so the UI can seamlessly update without a visible refresh.
  void _backgroundRevalidate(RequestOptions options) {
    final url = options.uri.toString();
    final generation = _store.generation;

    // Don't duplicate an already in-flight revalidation — unless it was
    // started before a clear() and is therefore doomed to abandon its result.
    final pending = _pendingRevalidations[url];
    if (pending != null && pending.generation == generation) return;

    final future = _doRevalidate(options, url, generation);
    _pendingRevalidations[url] = _PendingRevalidation(generation, future);
    // Clean up tracking when done (success or failure), unless a newer
    // revalidation has already replaced this slot.
    unawaited(future.whenComplete(() {
      if (identical(_pendingRevalidations[url]?.future, future)) {
        _pendingRevalidations.remove(url);
      }
    }));
  }

  /// Schedule ONE delayed revalidation when a network response carries a
  /// payload the SERVER itself served stale (PRICE-1 echo loop).
  ///
  /// The server's summary SWR answers an expired-cache request with the old
  /// row and recomputes in the background; without a follow-up nothing ever
  /// fetches that recompute, so a sparse client is permanently one visit
  /// behind. A payload whose `last_updated` is older than the path's TTL is
  /// exactly that case: revalidate once more after [_staleFollowUpDelay].
  ///
  /// Single-shot and deduped: one pending follow-up per URL, and a follow-up's
  /// own response never schedules another (no polling chain). Cancelled by
  /// the store's clear-fence — a logout between scheduling and firing
  /// abandons the timer's work.
  void _maybeScheduleFollowUp(RequestOptions options, dynamic data) {
    if (options.extra[_followUpExtra] == true) return;
    if (data is! Map) return;
    final lastUpdatedRaw = data['last_updated'];
    if (lastUpdatedRaw is! String) return;
    final lastUpdated = DateTime.tryParse(lastUpdatedRaw);
    if (lastUpdated == null) return;

    final age = DateTime.now().toUtc().difference(lastUpdated.toUtc());
    final ttl = Duration(seconds: _ttlForPath(options.path));
    if (age <= ttl) return;

    final url = options.uri.toString();
    if (_pendingFollowUps.containsKey(url)) return;

    final generation = _store.generation;
    _pendingFollowUps[url] = Timer(_staleFollowUpDelay, () {
      _pendingFollowUps.remove(url);
      if (generation != _store.generation) return;
      final followUpOptions = options.copyWith(
        extra: {...options.extra, _followUpExtra: true},
      );
      _backgroundRevalidate(followUpOptions);
    });
  }

  /// Test hook: cancels all pending follow-up timers (they are static and
  /// would otherwise leak across tests).
  @visibleForTesting
  static void debugCancelFollowUps() {
    for (final timer in _pendingFollowUps.values) {
      timer.cancel();
    }
    _pendingFollowUps.clear();
  }

  /// Test hook: number of pending follow-up revalidations.
  @visibleForTesting
  static int get debugPendingFollowUpCount => _pendingFollowUps.length;

  Future<void> _doRevalidate(
    RequestOptions options,
    String url,
    int generation,
  ) async {
    try {
      // Create a fresh Dio instance without this interceptor to avoid
      // infinite recursion. Copy the base config from the original request.
      final revalidationDio = Dio(BaseOptions(
        baseUrl: options.baseUrl,
        connectTimeout: options.connectTimeout,
        receiveTimeout: options.receiveTimeout,
        headers: Map<String, dynamic>.from(options.headers),
      ));

      // Revalidation must use the same HttpClient configuration as the
      // primary client — in particular certificate pinning must not be
      // bypassed on this background path.
      final httpClientFactory = _httpClientFactory;
      if (httpClientFactory != null) {
        (revalidationDio.httpClientAdapter as IOHttpClientAdapter)
            .createHttpClient = httpClientFactory;
      }

      // Conditional revalidation: sending the cached entry's ETag lets the
      // server answer 304 Not Modified when nothing changed, moving no body.
      final cachedEtag = (await _store.readWithMeta(url))?.etag;

      final response = await revalidationDio.get(
        options.path,
        queryParameters: options.queryParameters,
        options: Options(
          headers: {
            if (cachedEtag != null) 'If-None-Match': cachedEtag,
          },
          validateStatus: (status) =>
              status != null && (status < 300 || status == 304),
        ),
      );

      final status = response.statusCode ?? 0;
      final ttl = _ttlForPath(options.path);

      // The store was cleared (logout) while this revalidation was on the
      // wire: its result belongs to the previous session. Don't write it,
      // don't re-stamp it, and don't hand it to UI listeners.
      if (generation != _store.generation) return;

      if (status == 304) {
        // Payload unchanged: re-stamp the entry as fresh and stop. Listeners
        // are NOT notified — the UI already shows this data; replaying it as
        // fresh content would only churn widgets. The confirmed payload may
        // itself be a stale server-side echo, so it still gets the follow-up
        // check.
        await _store.touch(url, ttl);
        _maybeScheduleFollowUp(
            options, (await _store.readWithMeta(url))?.data);
        return;
      }

      if (status >= 200 && status < 300) {
        await _store.write(
          url,
          response.data,
          ttl,
          etag: response.headers.value('etag'),
        );

        // Notify listeners whose pattern matches this URL that fresh data
        // is available.
        _notifyRevalidationListeners(url, response.data);
        _maybeScheduleFollowUp(options, response.data);
      }
    } catch (e) {
      // Background revalidation failures are silent — the user already has
      // stale data and will get fresh data on the next request.
      developer.log(
        'Background revalidation failed for $url',
        name: 'CacheInterceptor',
        error: e,
      );
    }
  }

  static void _notifyRevalidationListeners(String url, dynamic freshData) {
    // Exact path match (see [onRevalidated]): substring/prefix matching
    // could route one endpoint's body to another endpoint's listener
    // (e.g. /wallets/123 into a /wallets payload consumer).
    final String path;
    try {
      path = Uri.parse(url).path;
    } catch (_) {
      return;
    }
    for (final entry in _revalidationListeners.entries.toList()) {
      if (path != entry.key) continue;
      for (final callback in List.of(entry.value)) {
        try {
          callback(freshData);
        } catch (e) {
          developer.log(
            'Revalidation listener error for $url',
            name: 'CacheInterceptor',
            error: e,
          );
        }
      }
    }
  }

  /// Test hook: delivers [freshData] to [onRevalidated] listeners matching
  /// [url] exactly as a completed background revalidation would.
  @visibleForTesting
  static void debugNotifyRevalidated(String url, dynamic freshData) =>
      _notifyRevalidationListeners(url, freshData);

  @visibleForTesting
  static int ttlForPath(String path) => _ttlForPath(path);

  static int _ttlForPath(String path) {
    if (path.contains('/portfolio/instant')) return 60;
    // Must not exceed the server's 120s mobile cache TTL — a longer client
    // TTL keeps serving values the server has already discarded.
    if (path.contains('/portfolio/summary')) return 120;
    // Top-of-market list changes slowly; 15 min keeps the watch-sync
    // piggyback fetch nearly free without a timer of its own.
    if (path.contains('/prices/top-assets')) return 900;
    if (path.contains('/chart/')) return 900;
    if (path.contains('/wallets')) return 300;
    if (path.contains('/exchanges/')) return 300;
    if (path.contains('/nfts/')) return 600;
    if (path.contains('/transactions')) return 120;
    return 120;
  }
}

/// An in-flight background revalidation and the store generation it started
/// under.
class _PendingRevalidation {
  _PendingRevalidation(this.generation, this.future);

  final int generation;
  final Future<void> future;
}
