import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:abct_mobile/core/network/cache_interceptor.dart';
import 'package:abct_mobile/core/network/cache_store.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

/// Revalidation-policy matrix for [CacheInterceptor]:
///
/// | Cache state          | Served from | Background revalidation |
/// |----------------------|-------------|-------------------------|
/// | fresh, young         | cache (HIT) | no                      |
/// | fresh, old           | cache (HIT) | yes                     |
/// | stale                | cache STALE | yes                     |
/// | none                 | network     | n/a (cached after)      |
/// | refresh=true         | network     | n/a                     |
/// | revalidate extra     | network     | n/a (cached after)      |
///
/// The `revalidate` extra (soft pull-to-refresh) is network-first regardless
/// of cache state, still writes the response to the cache, and still falls
/// back to cached data on connection errors.
///
/// Uses a real loopback HttpServer and a CacheStore in a temp directory.
void main() {
  late Directory tmpDir;
  late CacheStore store;
  late HttpServer server;
  late int hitCount;
  Duration serverDelay = Duration.zero;

  /// Per-request handler; tests override it for ETag/304 behavior.
  late Future<void> Function(HttpRequest request) respond;

  setUp(() async {
    tmpDir = Directory.systemTemp.createTempSync('cache_interceptor_test_');
    store = CacheStore.forDirectory(tmpDir);
    hitCount = 0;
    serverDelay = Duration.zero;
    respond = (request) async {
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({'value': 'from-network'}));
      await request.response.close();
    };
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      hitCount++;
      if (serverDelay > Duration.zero) {
        await Future<void>.delayed(serverDelay);
      }
      await respond(request);
    });
  });

  tearDown(() async {
    CacheInterceptor.debugCancelFollowUps();
    await server.close(force: true);
    if (tmpDir.existsSync()) {
      tmpDir.deleteSync(recursive: true);
    }
  });

  String urlFor(String path) => 'http://127.0.0.1:${server.port}$path';

  Dio buildDio({
    HttpClient Function()? httpClientFactory,
    Duration staleFollowUpDelay = const Duration(seconds: 35),
  }) {
    final dio = Dio(BaseOptions(baseUrl: 'http://127.0.0.1:${server.port}'));
    dio.interceptors.add(CacheInterceptor(
      store: store,
      httpClientFactory: httpClientFactory,
      staleFollowUpDelay: staleFollowUpDelay,
    ));
    return dio;
  }

  /// Writes a cache entry for [url] whose age and TTL are backdated so the
  /// interceptor sees it as [age] old with the original TTL of [ttl].
  ///
  /// The backdating edits the file on disk, so the store is re-instantiated
  /// afterwards — the writing store's in-memory LRU would otherwise keep
  /// serving the un-backdated entry.
  Future<void> writeAged(
    String url,
    dynamic data, {
    required Duration age,
    required Duration ttl,
    String? etag,
  }) async {
    await store.write(url, data, ttl.inSeconds, etag: etag);
    final file = tmpDir.listSync().whereType<File>().firstWhere((f) {
      final entry = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      return entry['url'] == url;
    });
    final entry = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final now = DateTime.now().millisecondsSinceEpoch;
    entry['cached_at'] = now - age.inMilliseconds;
    entry['expires_at'] = now - age.inMilliseconds + ttl.inMilliseconds;
    file.writeAsStringSync(jsonEncode(entry));
    store = CacheStore.forDirectory(tmpDir);
  }

  Future<void> waitFor(
    bool Function() condition, {
    Duration timeout = const Duration(seconds: 5),
    String description = 'condition',
  }) async {
    final deadline = DateTime.now().add(timeout);
    while (!condition()) {
      if (DateTime.now().isAfter(deadline)) {
        fail('Timed out waiting for $description');
      }
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
  }

  test('young fresh entry is served from cache with no revalidation',
      () async {
    final url = urlFor('/data');
    await store.write(url, {'value': 'cached'}, 300);

    final response = await buildDio().get<dynamic>('/data');

    expect(response.data, {'value': 'cached'});
    expect(response.headers.value('x-cache'), 'HIT');
    // Give any (incorrect) background revalidation time to fire.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(hitCount, 0);
  });

  test('old fresh entry is served from cache and revalidated in background',
      () async {
    final url = urlFor('/data');
    await writeAged(
      url,
      {'value': 'cached'},
      age: const Duration(seconds: 60),
      ttl: const Duration(seconds: 300),
    );

    final revalidated = Completer<dynamic>();
    final dispose = CacheInterceptor.onRevalidated('/data', (fresh) {
      if (!revalidated.isCompleted) revalidated.complete(fresh);
    });
    addTearDown(dispose);

    final response = await buildDio().get<dynamic>('/data');

    // Served instantly from cache...
    expect(response.data, {'value': 'cached'});
    expect(response.headers.value('x-cache'), 'HIT');

    // ...then fresh data arrives via listener and is written to the cache.
    final fresh = await revalidated.future.timeout(const Duration(seconds: 5));
    expect(fresh, {'value': 'from-network'});
    await waitFor(() => hitCount == 1, description: 'one network hit');
    expect(await store.read(url), {'value': 'from-network'});
  });

  test('stale entry is served immediately and revalidated in background',
      () async {
    final url = urlFor('/data');
    await writeAged(
      url,
      {'value': 'stale-cached'},
      age: const Duration(seconds: 400),
      ttl: const Duration(seconds: 300),
    );

    final revalidated = Completer<dynamic>();
    // Pattern is a path substring — callers don't need the full URL.
    final dispose = CacheInterceptor.onRevalidated('/data', (fresh) {
      if (!revalidated.isCompleted) revalidated.complete(fresh);
    });
    addTearDown(dispose);

    final response = await buildDio().get<dynamic>('/data');

    expect(response.data, {'value': 'stale-cached'});
    expect(response.headers.value('x-cache'), 'STALE');

    final fresh = await revalidated.future.timeout(const Duration(seconds: 5));
    expect(fresh, {'value': 'from-network'});
    await waitFor(() => hitCount == 1, description: 'one network hit');
    expect(await store.read(url), {'value': 'from-network'});
  });

  test('refresh=true bypasses cache and goes straight to network', () async {
    final url = urlFor('/data');
    await store.write(url, {'value': 'cached'}, 300);

    final response = await buildDio().get<dynamic>(
      '/data',
      queryParameters: {'refresh': true},
    );

    expect(response.data, {'value': 'from-network'});
    expect(response.headers.value('x-cache'), isNull);
    expect(hitCount, 1);
  });

  test('cache miss goes to network and caches the response', () async {
    final url = urlFor('/data');

    final response = await buildDio().get<dynamic>('/data');

    expect(response.data, {'value': 'from-network'});
    expect(hitCount, 1);
    expect(await store.read(url), {'value': 'from-network'});
  });

  test('background revalidation uses the injected HttpClient factory',
      () async {
    final url = urlFor('/data');
    await writeAged(
      url,
      {'value': 'cached'},
      age: const Duration(seconds: 60),
      ttl: const Duration(seconds: 300),
    );

    var factoryCalls = 0;
    final dio = buildDio(httpClientFactory: () {
      factoryCalls++;
      return HttpClient();
    });

    final response = await dio.get<dynamic>('/data');
    expect(response.headers.value('x-cache'), 'HIT');

    // The primary request never touched the network (cache HIT), so any
    // factory invocation belongs to the revalidation client.
    await waitFor(() => hitCount == 1, description: 'revalidation hit');
    expect(factoryCalls, greaterThanOrEqualTo(1));
  });

  test('concurrent stale hits deduplicate to a single revalidation', () async {
    final url = urlFor('/data');
    serverDelay = const Duration(milliseconds: 300);
    await writeAged(
      url,
      {'value': 'stale-cached'},
      age: const Duration(seconds: 400),
      ttl: const Duration(seconds: 300),
    );

    final dio = buildDio();
    final first = await dio.get<dynamic>('/data');
    final second = await dio.get<dynamic>('/data');
    expect(first.headers.value('x-cache'), 'STALE');
    expect(second.headers.value('x-cache'), 'STALE');

    await waitFor(() => hitCount >= 1, description: 'revalidation hit');
    await Future<void>.delayed(const Duration(milliseconds: 500));
    expect(hitCount, 1);
  });

  test('revalidate extra on a fresh entry is network-first with exactly one '
      'fetch and updates the cache', () async {
    final url = urlFor('/data');
    await store.write(url, {'value': 'cached'}, 300);

    final response = await buildDio().get<dynamic>(
      '/data',
      options: Options(extra: {CacheInterceptor.revalidateExtra: true}),
    );

    // Served from the network, never the cache entry being refreshed.
    expect(response.data, {'value': 'from-network'});
    expect(response.headers.value('x-cache'), isNull);
    expect(await store.read(url), {'value': 'from-network'});

    // Single pull = single fetch: no background revalidation piles on.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(hitCount, 1);
  });

  test('revalidate extra on a stale entry is network-first with exactly one '
      'fetch', () async {
    final url = urlFor('/data');
    await writeAged(
      url,
      {'value': 'stale-cached'},
      age: const Duration(seconds: 400),
      ttl: const Duration(seconds: 300),
    );

    final response = await buildDio().get<dynamic>(
      '/data',
      options: Options(extra: {CacheInterceptor.revalidateExtra: true}),
    );

    expect(response.data, {'value': 'from-network'});
    expect(response.headers.value('x-cache'), isNull);
    expect(await store.read(url), {'value': 'from-network'});
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(hitCount, 1);
  });

  test('revalidate extra with no cache entry fetches and caches', () async {
    final url = urlFor('/data');

    final response = await buildDio().get<dynamic>(
      '/data',
      options: Options(extra: {CacheInterceptor.revalidateExtra: true}),
    );

    expect(response.data, {'value': 'from-network'});
    expect(hitCount, 1);
    expect(await store.read(url), {'value': 'from-network'});
  });

  test('revalidate extra falls back to cached data on connection error',
      () async {
    // Bind then close a listener so the port is known-dead.
    final deadServer =
        await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final deadPort = deadServer.port;
    await deadServer.close(force: true);

    final url = 'http://127.0.0.1:$deadPort/data';
    await writeAged(
      url,
      {'value': 'stale-cached'},
      age: const Duration(seconds: 400),
      ttl: const Duration(seconds: 300),
    );

    final dio = Dio(BaseOptions(
      baseUrl: 'http://127.0.0.1:$deadPort',
      connectTimeout: const Duration(seconds: 2),
    ));
    dio.interceptors.add(CacheInterceptor(store: store));

    final response = await dio.get<dynamic>(
      '/data',
      options: Options(extra: {CacheInterceptor.revalidateExtra: true}),
    );

    expect(response.data, {'value': 'stale-cached'});
    expect(response.headers.value('x-cache'), 'STALE');
  });

  test('client summary TTL does not exceed the server 120s mobile cache TTL',
      () {
    expect(
      CacheInterceptor.ttlForPath('/api/mobile/portfolio/summary'),
      lessThanOrEqualTo(120),
    );
  });

  group('stale-payload follow-up revalidation (PRICE-1)', () {
    /// A payload the server itself served from ITS stale cache: its
    /// last_updated is far older than the /data TTL (120s).
    Map<String, dynamic> echoPayload() => {
          'value': 'server-stale-echo',
          'last_updated': DateTime.now()
              .toUtc()
              .subtract(const Duration(minutes: 10))
              .toIso8601String(),
        };

    test(
        'revalidation that receives a stale server payload schedules exactly '
        'one follow-up — which does not chain', () async {
      final url = urlFor('/data');
      respond = (request) async {
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(echoPayload()));
        await request.response.close();
      };
      await writeAged(
        url,
        {'value': 'client-cached'},
        age: const Duration(seconds: 400),
        ttl: const Duration(seconds: 300),
      );

      final dio =
          buildDio(staleFollowUpDelay: const Duration(milliseconds: 100));
      final response = await dio.get<dynamic>('/data');
      expect(response.headers.value('x-cache'), 'STALE');

      // Background revalidation fires (hit 1) and, because the payload it
      // received is older than the TTL, schedules one follow-up.
      await waitFor(() => hitCount == 1, description: 'revalidation hit');
      await waitFor(
        () => CacheInterceptor.debugPendingFollowUpCount == 1,
        description: 'follow-up scheduled',
      );

      // The follow-up fires (hit 2). Its response is equally stale, but a
      // follow-up's response must not schedule another one — no chain.
      await waitFor(() => hitCount == 2, description: 'follow-up hit');
      await Future<void>.delayed(const Duration(milliseconds: 400));
      expect(hitCount, 2);
      expect(CacheInterceptor.debugPendingFollowUpCount, 0);
    });

    test('pass-through network response with a stale payload also gets the '
        'follow-up', () async {
      respond = (request) async {
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(echoPayload()));
        await request.response.close();
      };

      final dio =
          buildDio(staleFollowUpDelay: const Duration(milliseconds: 100));
      // No cache entry: plain pass-through fetch (hit 1).
      await dio.get<dynamic>('/data');
      expect(hitCount, 1);

      await waitFor(() => hitCount == 2, description: 'follow-up hit');
      await Future<void>.delayed(const Duration(milliseconds: 400));
      expect(hitCount, 2);
    });

    test('fresh payloads schedule no follow-up', () async {
      respond = (request) async {
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({
          'value': 'live',
          'last_updated': DateTime.now().toUtc().toIso8601String(),
        }));
        await request.response.close();
      };

      final dio =
          buildDio(staleFollowUpDelay: const Duration(milliseconds: 100));
      await dio.get<dynamic>('/data');
      expect(hitCount, 1);
      expect(CacheInterceptor.debugPendingFollowUpCount, 0);

      await Future<void>.delayed(const Duration(milliseconds: 400));
      expect(hitCount, 1);
    });

    test('payloads without a parseable last_updated schedule no follow-up',
        () async {
      respond = (request) async {
        request.response.headers.contentType = ContentType.json;
        request.response.write(
            jsonEncode({'value': 'no-timestamp', 'last_updated': 42}));
        await request.response.close();
      };

      final dio =
          buildDio(staleFollowUpDelay: const Duration(milliseconds: 100));
      await dio.get<dynamic>('/data');
      expect(hitCount, 1);
      expect(CacheInterceptor.debugPendingFollowUpCount, 0);
    });
  });

  test('hard refresh (refresh=true) surfaces connection errors instead of '
      'silently answering with cached data', () async {
    // Bind then close a listener so the port is known-dead.
    final deadServer = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final deadPort = deadServer.port;
    await deadServer.close(force: true);

    final url = 'http://127.0.0.1:$deadPort/data?refresh=true';
    await writeAged(
      url,
      {'value': 'stale-cached'},
      age: const Duration(seconds: 400),
      ttl: const Duration(seconds: 300),
    );

    final dio = Dio(BaseOptions(
      baseUrl: 'http://127.0.0.1:$deadPort',
      connectTimeout: const Duration(seconds: 2),
    ));
    dio.interceptors.add(CacheInterceptor(store: store));

    await expectLater(
      dio.get<dynamic>('/data', queryParameters: {'refresh': true}),
      throwsA(isA<DioException>()),
    );
  });

  test('network responses store the ETag and revalidation sends If-None-Match',
      () async {
    final url = urlFor('/data');
    String? receivedIfNoneMatch;
    respond = (request) async {
      receivedIfNoneMatch = request.headers.value('if-none-match');
      request.response.headers.contentType = ContentType.json;
      request.response.headers.set('etag', '"v1"');
      request.response.write(jsonEncode({'value': 'from-network'}));
      await request.response.close();
    };

    // Cache miss: fetched from network, ETag stored with the entry.
    await buildDio().get<dynamic>('/data');
    expect(receivedIfNoneMatch, isNull);
    expect((await store.readWithMeta(url))?.etag, '"v1"');

    // Age the entry past the revalidation threshold, keeping its ETag.
    await writeAged(
      url,
      {'value': 'cached'},
      age: const Duration(seconds: 60),
      ttl: const Duration(seconds: 300),
      etag: '"v1"',
    );

    // Old fresh HIT triggers background revalidation with If-None-Match.
    await buildDio().get<dynamic>('/data');
    await waitFor(() => hitCount == 2, description: 'revalidation hit');
    expect(receivedIfNoneMatch, '"v1"');
  });

  test('304 re-stamps the entry as fresh without notifying listeners',
      () async {
    final url = urlFor('/data');
    respond = (request) async {
      request.response.statusCode = HttpStatus.notModified;
      await request.response.close();
    };

    await writeAged(
      url,
      {'value': 'cached'},
      age: const Duration(seconds: 60),
      ttl: const Duration(seconds: 300),
      etag: '"v1"',
    );

    var listenerCalls = 0;
    final dispose = CacheInterceptor.onRevalidated('/data', (_) {
      listenerCalls++;
    });
    addTearDown(dispose);

    final response = await buildDio().get<dynamic>('/data');
    expect(response.headers.value('x-cache'), 'HIT');

    await waitFor(() => hitCount == 1, description: 'revalidation hit');
    // Give any (incorrect) listener notification time to fire.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(listenerCalls, 0);

    // Entry was re-stamped: data and ETag unchanged, age reset to ~0.
    final meta = await store.readWithMeta(url);
    expect(meta, isNotNull);
    expect(meta!.data, {'value': 'cached'});
    expect(meta.etag, '"v1"');
    expect(meta.isFresh, isTrue);
    expect(meta.age, lessThan(const Duration(seconds: 30)));
  });

  test('200 with a new ETag replaces the entry and notifies listeners',
      () async {
    final url = urlFor('/data');
    respond = (request) async {
      request.response.headers.contentType = ContentType.json;
      request.response.headers.set('etag', '"v2"');
      request.response.write(jsonEncode({'value': 'updated'}));
      await request.response.close();
    };

    await writeAged(
      url,
      {'value': 'cached'},
      age: const Duration(seconds: 60),
      ttl: const Duration(seconds: 300),
      etag: '"v1"',
    );

    final revalidated = Completer<dynamic>();
    final dispose = CacheInterceptor.onRevalidated('/data', (fresh) {
      if (!revalidated.isCompleted) revalidated.complete(fresh);
    });
    addTearDown(dispose);

    final response = await buildDio().get<dynamic>('/data');
    expect(response.data, {'value': 'cached'}); // served instantly

    final fresh = await revalidated.future.timeout(const Duration(seconds: 5));
    expect(fresh, {'value': 'updated'});
    final meta = await store.readWithMeta(url);
    expect(meta!.data, {'value': 'updated'});
    expect(meta.etag, '"v2"');
  });

  test(
      'logout clear() during an in-flight background revalidation discards '
      'its result (cache stays empty, listeners silent)', () async {
    final url = urlFor('/data');
    serverDelay = const Duration(milliseconds: 300);
    await writeAged(
      url,
      {'value': 'old-session'},
      age: const Duration(seconds: 400),
      ttl: const Duration(seconds: 300),
    );

    var listenerCalls = 0;
    final dispose = CacheInterceptor.onRevalidated('/data', (_) {
      listenerCalls++;
    });
    addTearDown(dispose);

    // Stale hit serves instantly and launches the background revalidation…
    final response = await buildDio().get<dynamic>('/data');
    expect(response.headers.value('x-cache'), 'STALE');

    // …then logout clears the cache while that revalidation is on the wire.
    await store.clear();

    await waitFor(() => hitCount == 1, description: 'revalidation hit');
    await Future<void>.delayed(const Duration(milliseconds: 500));

    // The revalidation's result must be fully discarded: nothing in either
    // cache layer, no file re-persisted, no UI listener fed old-session data.
    expect(await store.readStale(url), isNull);
    expect(
      tmpDir.listSync().whereType<File>(),
      isEmpty,
      reason: 'a write landing after logout must not re-persist old data',
    );
    expect(listenerCalls, 0);
  });

  test(
      'logout clear() during an in-flight primary request discards the '
      'response write', () async {
    final url = urlFor('/data');
    serverDelay = const Duration(milliseconds: 300);

    // No cache: the request goes to the network…
    final pending = buildDio().get<dynamic>('/data');
    await Future<void>.delayed(const Duration(milliseconds: 50));
    // …and logout fires while the response is still on the wire.
    await store.clear();
    final response = await pending;

    // The caller still gets its response, but nothing may be cached.
    expect(response.data, {'value': 'from-network'});
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(await store.readStale(url), isNull);
    expect(tmpDir.listSync().whereType<File>(), isEmpty);
  });

  test('revalidation listener matching is exact on the URL path', () async {
    var walletsCalls = 0;
    var summaryCalls = 0;
    final disposeWallets = CacheInterceptor.onRevalidated(
      '/api/mobile/wallets',
      (_) => walletsCalls++,
    );
    final disposeSummary = CacheInterceptor.onRevalidated(
      '/api/mobile/portfolio/summary',
      (_) => summaryCalls++,
    );
    addTearDown(disposeWallets);
    addTearDown(disposeSummary);

    // Exact path with a query string → fires.
    CacheInterceptor.debugNotifyRevalidated(
      'https://h/api/mobile/wallets?include_balances=true',
      const {},
    );
    expect(walletsCalls, 1);

    // Sub-resource path must NOT leak into the collection listener.
    CacheInterceptor.debugNotifyRevalidated(
      'https://h/api/mobile/wallets/123',
      const {},
    );
    expect(walletsCalls, 1);

    // Bare exact path → fires.
    CacheInterceptor.debugNotifyRevalidated(
      'https://h/api/mobile/wallets',
      const {},
    );
    expect(walletsCalls, 2);

    // Dashboard-style deep path listener is unaffected.
    CacheInterceptor.debugNotifyRevalidated(
      'https://h/api/mobile/portfolio/summary?include_sparklines=false',
      const {},
    );
    expect(summaryCalls, 1);
    expect(walletsCalls, 2);
  });

  test('disposed listeners are not notified', () async {
    final url = urlFor('/data');
    await writeAged(
      url,
      {'value': 'cached'},
      age: const Duration(seconds: 60),
      ttl: const Duration(seconds: 300),
    );

    var calls = 0;
    final dispose = CacheInterceptor.onRevalidated('/data', (_) => calls++);
    dispose();

    await buildDio().get<dynamic>('/data');
    await waitFor(() => hitCount == 1, description: 'revalidation hit');
    await Future<void>.delayed(const Duration(milliseconds: 200));
    expect(calls, 0);
  });

  // The interceptor callbacks are async void: an exception escaping them is
  // an uncaught zone error, Dio never advances the handler, and the request
  // future stays pending forever with no timeout. These tests pin the
  // fail-open contract — a defective cache layer degrades to plain network
  // behavior instead of hanging the caller. Each request carries a short
  // explicit timeout so a regression fails fast instead of stalling the run.
  group('fail-open on cache-layer exceptions', () {
    Dio throwingDio(_ThrowingStore throwing) {
      final dio = Dio(BaseOptions(baseUrl: 'http://127.0.0.1:${server.port}'));
      dio.interceptors.add(CacheInterceptor(store: throwing));
      return dio;
    }

    test('cache read throws → request completes with the network response',
        () async {
      final throwing = _ThrowingStore(tmpDir, throwOnRead: true);

      final response = await throwingDio(throwing)
          .get<dynamic>('/data')
          .timeout(const Duration(seconds: 5));

      expect(response.data, {'value': 'from-network'});
      expect(response.headers.value('x-cache'), isNull);
      expect(hitCount, 1);
    });

    test('cache write throws → response is still delivered', () async {
      final throwing = _ThrowingStore(tmpDir, throwOnWrite: true);

      final response = await throwingDio(throwing)
          .get<dynamic>('/data')
          .timeout(const Duration(seconds: 5));

      expect(response.data, {'value': 'from-network'});
      expect(hitCount, 1);
    });

    test('stale-fallback read throws → the original error still surfaces',
        () async {
      // Bind then close a listener so the port is known-dead.
      final deadServer =
          await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final deadPort = deadServer.port;
      await deadServer.close(force: true);

      final throwing = _ThrowingStore(tmpDir, throwOnRead: true);
      final dio = Dio(BaseOptions(
        baseUrl: 'http://127.0.0.1:$deadPort',
        connectTimeout: const Duration(seconds: 2),
      ));
      dio.interceptors.add(CacheInterceptor(store: throwing));

      await expectLater(
        dio.get<dynamic>('/data').timeout(const Duration(seconds: 8)),
        throwsA(isA<DioException>().having(
          (e) => e.type,
          'type',
          DioExceptionType.connectionError,
        )),
      );
    });
  });
}

/// Store whose read/write paths throw, simulating a defective cache layer
/// (corrupt file decode, isolate failure, full disk, …).
class _ThrowingStore extends CacheStore {
  _ThrowingStore(
    Directory directory, {
    this.throwOnRead = false,
    this.throwOnWrite = false,
  }) : super.forDirectory(directory);

  final bool throwOnRead;
  final bool throwOnWrite;

  @override
  Future<CacheEntry?> readWithMeta(String url) {
    if (throwOnRead) throw StateError('injected read failure');
    return super.readWithMeta(url);
  }

  @override
  Future<dynamic> readStale(String url) {
    if (throwOnRead) throw StateError('injected read failure');
    return super.readStale(url);
  }

  @override
  Future<void> write(
    String url,
    dynamic data,
    int ttlSeconds, {
    String? etag,
  }) {
    if (throwOnWrite) throw StateError('injected write failure');
    return super.write(url, data, ttlSeconds, etag: etag);
  }
}
