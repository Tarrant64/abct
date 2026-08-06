import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/foundation.dart';

import '../models/asset_detail.dart';
import '../models/connection_profile.dart';
import '../models/exchanges_summary.dart';
import '../models/market_asset.dart';
import '../models/nft_wall.dart';
import '../models/nfts_summary.dart';
import '../models/portfolio_history.dart';
import '../models/portfolio_instant.dart';
import '../models/portfolio_summary.dart';
import '../models/staking_summary.dart';
import '../models/token_holding.dart';
import '../models/transaction.dart';
import '../models/wallets_summary.dart';
import '../storage/auth_session_store.dart';
import '../storage/auth_token_store.dart';
import 'cache_interceptor.dart';
import 'pinning.dart';

class ApiClient {
  ApiClient(
    this.profile, {
    AuthTokenStore? tokenStore,
    AuthSessionStore? sessionStore,
  })  : _tokenStore = tokenStore ?? AuthTokenStore(),
        _sessionStore = sessionStore ?? AuthSessionStore();

  /// Returns the app-wide client for [profile], creating it on first use.
  ///
  /// Tabs and screens share this instance so the configured Dio — and the
  /// keychain reads behind its auth headers — happen once per profile per
  /// auth generation instead of per construction site and per API call.
  factory ApiClient.shared(ConnectionProfile profile) {
    return _shared.putIfAbsent(_sharedKey(profile), () => ApiClient(profile));
  }

  static final Map<String, ApiClient> _shared = {};

  static String _sharedKey(ConnectionProfile profile) =>
      '${profile.name}|${profile.baseUrl}';

  /// Test hook: forgets all shared instances so tests stay isolated.
  @visibleForTesting
  static void resetSharedForTesting() => _shared.clear();

  final ConnectionProfile profile;
  final AuthTokenStore _tokenStore;
  final AuthSessionStore _sessionStore;

  /// The configured Dio (auth headers applied), built once and reused until
  /// the auth material changes. Caching the future also collapses concurrent
  /// first calls into a single keychain read pair.
  Future<Dio>? _dioFuture;

  /// Drops this instance's cached client and the shared instance's for the
  /// same profile, forcing the next [create] to re-read credentials from the
  /// keychain. Called on every auth mutation (login, logout, external
  /// clearAuthForProfile); only the assembled headers are cached, never the
  /// raw credential values, so nothing outlives this invalidation.
  void _invalidateClientCache() {
    _dioFuture = null;
    _invalidateSharedClientCache(profile);
  }

  static void _invalidateSharedClientCache(ConnectionProfile profile) {
    _shared[_sharedKey(profile)]?._dioFuture = null;
  }

  Future<Dio> create() {
    final cached = _dioFuture;
    if (cached != null) return cached;
    final future = _buildDio();
    _dioFuture = future;
    return future.catchError((Object error) {
      // Don't cache failures (e.g. a keychain hiccup) — retry next call.
      if (identical(_dioFuture, future)) _dioFuture = null;
      throw error;
    });
  }

  Future<Dio> _buildDio() async {
    final token = await _tokenStore.readToken(profile);
    final sessionCookie = await _sessionStore.readSessionCookie(profile);
    final dio = Dio(BaseOptions(
      baseUrl: profile.baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      headers: {
        if (profile.accessClientId.isNotEmpty)
          'CF-Access-Client-Id': profile.accessClientId,
        if (profile.accessClientSecret.isNotEmpty)
          'CF-Access-Client-Secret': profile.accessClientSecret,
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        if (sessionCookie != null && sessionCookie.isNotEmpty)
          'Cookie': sessionCookie,
      },
    ));

    // Single HttpClient factory shared by the primary adapter and the cache
    // interceptor's background revalidation path, so certificate pinning
    // applies identically to both.
    HttpClient httpClientFactory() {
      if (profile.certPins.isEmpty) {
        return HttpClient();
      }
      return createPinnedHttpClient(profile.certPins);
    }

    dio.interceptors.add(CacheInterceptor(httpClientFactory: httpClientFactory));

    (dio.httpClientAdapter as IOHttpClientAdapter).createHttpClient =
        httpClientFactory;

    return dio;
  }

  Future<void> login(
      {required String username, required String password}) async {
    await clearAuthForProfile(profile);
    _invalidateClientCache();
    // Unauthenticated one-shot client for the login POST itself; the cache
    // is invalidated again after credentials are saved so the next create()
    // picks up the new auth headers.
    final dio = await _buildDio();
    final response = await _postLogin(
      dio: dio,
      username: username,
      password: password,
    );

    final status = response.statusCode ?? 0;
    if (status >= 300 && status < 400) {
      final location = response.headers.value('location') ?? 'unknown';
      if (location.contains('cloudflareaccess.com')) {
        throw Exception(
          'Cloudflare Access rejected the service token. Check Client ID/Secret policy.',
        );
      }
      throw Exception('Login redirected ($status) to $location');
    }
    if (status == 401 || status == 403) {
      final detail = _detailFromBody(response.data);
      throw Exception(detail ?? 'Invalid credentials.');
    }
    if (status != 200) {
      throw Exception('Login failed with status $status');
    }

    final token = _extractToken(response.data);
    if (token != null && token.isNotEmpty) {
      await _tokenStore.saveToken(profile, token);
    }

    final sessionCookie = _extractSessionCookie(
      response.headers.map['set-cookie'],
    );
    if (sessionCookie != null && sessionCookie.isNotEmpty) {
      await _sessionStore.saveSessionCookie(profile, sessionCookie);
    }

    // New credentials are in the keychain: drop any client built without
    // them so subsequent requests authenticate with the fresh material.
    _invalidateClientCache();

    if ((token == null || token.isEmpty) &&
        (sessionCookie == null || sessionCookie.isEmpty)) {
      developer.log(
        'Login 200 but no token/cookie found. '
        'Body type: ${response.data.runtimeType}, '
        'Header keys: ${response.headers.map.keys.toList()}',
        name: 'ApiClient',
      );
      throw Exception(
        'Login succeeded but no bearer token or session cookie was returned.',
      );
    }
  }

  Future<String> testConnection() async {
    final dio = await create();
    final response = await dio.get(
      '/api/mobile/status',
      options: Options(
        validateStatus: (status) => status != null,
      ),
    );

    final status = response.statusCode ?? 0;
    if (status >= 200 && status < 400) {
      return 'Access granted. Server responded with $status.';
    }
    if (status == 401 || status == 403) {
      throw Exception('Access denied. Check CF Access credentials.');
    }
    if (status >= 400 && status < 500) {
      return 'Connected. Server responded with $status.';
    }
    throw Exception('Server error: $status');
  }

  Future<void> logout() async {
    try {
      final dio = await create();
      await dio.post(
        '/auth/logout',
        options: Options(validateStatus: (status) => status != null),
      );
    } finally {
      await clearAuthForProfile(profile);
      _invalidateClientCache();
    }
  }

  static Future<void> clearAuthForProfile(ConnectionProfile profile) async {
    await AuthTokenStore().clearToken(profile);
    await AuthSessionStore().clearSessionCookie(profile);
    // Credentials are gone; a cached shared client would keep sending the
    // old Authorization/Cookie headers until invalidated.
    _invalidateSharedClientCache(profile);
  }

  Future<PortfolioSummary> getPortfolioSummary({
    bool refresh = false,
    bool revalidate = false,
    bool includeSparklines = true,
  }) async {
    final params = <String, dynamic>{};
    if (refresh) params['refresh'] = true;
    if (!includeSparklines) params['include_sparklines'] = false;
    final json = await _getJsonMap(
      '/api/mobile/portfolio/summary',
      queryParameters: params.isNotEmpty ? params : null,
      revalidate: revalidate,
    );
    return PortfolioSummary.fromJson(json);
  }

  Future<PortfolioInstant> getPortfolioInstant({bool revalidate = false}) async {
    final json = await _getJsonMap(
      '/api/mobile/portfolio/instant',
      revalidate: revalidate,
    );
    return PortfolioInstant.fromJson(json);
  }

  Future<PortfolioHistory> getPortfolioHistory({
    required String range,
    bool revalidate = false,
  }) async {
    const path = '/api/mobile/chart/portfolio-history';
    return PortfolioHistory.fromJson(
      await _getHistoryJson(path: path, range: range, revalidate: revalidate),
    );
  }

  Future<Map<String, dynamic>> _getHistoryJson({
    required String path,
    required String range,
    bool revalidate = false,
  }) async {
    return _getJsonMap(
      path,
      queryParameters: {
        'range': range,
        // Server-side slim contract (dashboard D4): top-level fields
        // unchanged, chart points reduced to exactly
        // {"timestamp","total_value_usd"} — the only per-point fields any
        // mobile consumer (chart or watch sync) reads. ~74% smaller payload.
        'slim': true,
      },
      revalidate: revalidate,
    );
  }

  Future<WalletsSummary> getWallets({
    String? blockchain,
    bool includeBalances = true,
    bool refresh = false,
    bool revalidate = false,
  }) async {
    final json = await _getJsonMap(
      '/api/mobile/wallets',
      queryParameters: {
        if (blockchain != null && blockchain.isNotEmpty)
          'blockchain': blockchain,
        'include_balances': includeBalances,
        if (refresh) 'refresh': true,
      },
      revalidate: revalidate,
    );
    return WalletsSummary.fromJson(json);
  }

  Future<ExchangesSummary> getExchangesSummary({
    bool refresh = false,
    bool revalidate = false,
  }) async {
    final json = await _getJsonMap(
      '/api/mobile/exchanges/summary',
      queryParameters: refresh ? {'refresh': true} : null,
      revalidate: revalidate,
    );
    return ExchangesSummary.fromJson(json);
  }

  Future<ExchangeDetail> getExchangeDetail({
    required String exchangeName,
    bool refresh = false,
  }) async {
    final encoded = Uri.encodeComponent(exchangeName);
    final json = await _getJsonMap(
      '/api/mobile/exchanges/$encoded',
      queryParameters: refresh ? {'refresh': true} : null,
    );
    return ExchangeDetail.fromJson(json);
  }

  Future<StakingSummary> getStaking({
    bool refresh = false,
    bool revalidate = false,
  }) async {
    final json = await _getJsonMap(
      '/api/mobile/defi/staking',
      queryParameters: refresh ? {'refresh': true} : null,
      revalidate: revalidate,
    );
    return StakingSummary.fromJson(json);
  }

  Future<NftsSummary> getNftsSummary({String? blockchain}) async {
    final dio = await create();
    final response = await dio.get(
      '/api/mobile/nfts/summary',
      queryParameters: {
        if (blockchain != null && blockchain.isNotEmpty)
          'blockchain': blockchain,
      },
      options: Options(validateStatus: (status) => status != null),
    );

    final status = response.statusCode ?? 0;
    if (status == 204 || status == 404) {
      return NftsSummary.empty();
    }

    final json = _unwrapResponse('/api/mobile/nfts/summary', response);
    return NftsSummary.fromJson(json);
  }

  Future<NftWallPage> getNftWall({
    required int limit,
    required int offset,
    bool revalidate = false,
  }) async {
    final dio = await create();
    const paths = ['/nfts/wall/nfts', '/api/mobile/nfts/wall/nfts'];

    Response<dynamic>? response;
    String? usedPath;
    for (final path in paths) {
      final candidate = await dio.get(
        path,
        queryParameters: {
          'limit': limit,
          'offset': offset,
        },
        options: Options(
          validateStatus: (status) => status != null,
          extra: {
            if (revalidate) CacheInterceptor.revalidateExtra: true,
          },
        ),
      );
      if ((candidate.statusCode ?? 0) != 404) {
        response = candidate;
        usedPath = path;
        break;
      }
    }

    if (response == null || usedPath == null) {
      throw Exception('NFT wall endpoint not found.');
    }

    final status = response.statusCode ?? 0;
    if (status == 204) {
      return const NftWallPage(items: [], fetchedCount: 0);
    }
    if (status == 401) {
      throw Exception('Session expired. Please sign in again.');
    }
    if (status == 403) {
      throw Exception('Access denied for $usedPath.');
    }
    if (status < 200 || status >= 300) {
      final detail = _detailFromBody(response.data);
      throw Exception(detail ?? 'Request failed ($status) for $usedPath');
    }

    final body = response.data;
    final maps = <Map<String, dynamic>>[];
    int? total;

    int? readOptionalInt(Map<String, dynamic> json, String key) {
      if (!json.containsKey(key)) return null;
      final value = json[key];
      if (value is int) return value;
      if (value is num) return value.toInt();
      if (value is String) return int.tryParse(value);
      return null;
    }

    if (body is List) {
      for (final item in body) {
        if (item is Map<String, dynamic>) {
          maps.add(item);
        } else if (item is Map) {
          maps.add(item.map((k, v) => MapEntry('$k', v)));
        }
      }
    } else if (body is Map<String, dynamic>) {
      total = readOptionalInt(body, 'total') ??
          readOptionalInt(body, 'total_nfts') ??
          readOptionalInt(body, 'count');
      final list = body['nfts'] ?? body['items'] ?? body['data'] ?? [];
      if (list is List) {
        for (final item in list) {
          if (item is Map<String, dynamic>) {
            maps.add(item);
          } else if (item is Map) {
            maps.add(item.map((k, v) => MapEntry('$k', v)));
          }
        }
      }
    } else if (body is Map) {
      final normalized = body.map((k, v) => MapEntry('$k', v));
      total = readOptionalInt(normalized, 'total') ??
          readOptionalInt(normalized, 'total_nfts') ??
          readOptionalInt(normalized, 'count');
      final list =
          normalized['nfts'] ?? normalized['items'] ?? normalized['data'] ?? [];
      if (list is List) {
        for (final item in list) {
          if (item is Map<String, dynamic>) {
            maps.add(item);
          } else if (item is Map) {
            maps.add(item.map((k, v) => MapEntry('$k', v)));
          }
        }
      }
    }

    final items = maps
        .map(NftWallItem.fromJson)
        .where((item) => item.assetId.isNotEmpty)
        .toList(growable: false);

    return NftWallPage(
      items: items,
      fetchedCount: items.length,
      total: total,
    );
  }

  Future<TransactionHistory> getTransactions({
    int days = 30,
    String? blockchain,
    String? direction,
    String? search,
    bool revalidate = false,
  }) async {
    final json = await _getJsonMap(
      '/api/transactions',
      queryParameters: {
        'days': days,
        if (blockchain != null && blockchain.isNotEmpty)
          'blockchain': blockchain,
        if (direction != null && direction.isNotEmpty) 'direction': direction,
        if (search != null && search.isNotEmpty) 'search': search,
      },
      revalidate: revalidate,
    );
    return TransactionHistory.fromJson(json);
  }

  Future<AllHoldingsResponse> getAllHoldings({
    bool refresh = false,
    bool revalidate = false,
  }) async {
    final json = await _getJsonMap(
      '/portfolio/all-holdings',
      queryParameters: refresh ? {'refresh': true} : null,
      revalidate: revalidate,
    );
    return AllHoldingsResponse.fromJson(json);
  }

  Future<Map<String, dynamic>> getAssetPriceChart({
    required String symbol,
    String range = '7d',
  }) async {
    final encoded = Uri.encodeComponent(symbol.toLowerCase());
    return _getJsonMap(
      '/api/mobile/chart/price/$encoded',
      queryParameters: {'range': range},
    );
  }

  /// Top assets by market cap for watch complication tracking. Returns an
  /// empty list when the endpoint is unavailable (it is additive server-side)
  /// — the watch gallery then degrades to favorites + holdings only.
  Future<List<MarketAsset>> getTopAssets({int limit = 20}) async {
    try {
      final json = await _getJsonMap(
        '/prices/top-assets',
        queryParameters: {'limit': limit},
      );
      final raw = json['assets'];
      if (raw is! List) return const [];
      return raw
          .whereType<Map<String, dynamic>>()
          .map(MarketAsset.fromJson)
          .where((a) => a.symbol.isNotEmpty && a.priceUsd > 0)
          .toList();
    } catch (error, stack) {
      developer.log(
        'Top assets fetch failed (watch gallery degrades gracefully)',
        name: 'ApiClient',
        error: error,
        stackTrace: stack,
      );
      return const [];
    }
  }

  Future<AssetMarketData> getAssetMarketData({
    required String symbol,
  }) async {
    final encoded = Uri.encodeComponent(symbol.toUpperCase());
    final json = await _getJsonMap(
      '/portfolio/asset-detail',
      queryParameters: {'symbol': encoded},
    );
    return AssetMarketData.fromJson(json);
  }

  Future<WalletBreakdownResponse> getAssetWalletBreakdown({
    required String symbol,
  }) async {
    final encoded = Uri.encodeComponent(symbol.toUpperCase());
    final json = await _getJsonMap('/api/mobile/asset/$encoded/wallet-breakdown');
    return WalletBreakdownResponse.fromJson(json);
  }

  /// Add a new self-custody wallet to the dashboard.
  ///
  /// The backend auto-detects the blockchain from the [address] format.
  /// Optionally supply a human-readable [label].
  Future<Map<String, dynamic>> addWallet({
    required String address,
    String? label,
  }) async {
    final dio = await create();
    final response = await dio.post(
      '/wallets',
      data: {
        'address': address,
        if (label != null && label.trim().isNotEmpty) 'label': label.trim(),
      },
      options: Options(validateStatus: (status) => status != null),
    );
    return _unwrapResponse('/wallets', response);
  }

  /// Delete a wallet by its address.
  ///
  /// The [address] may include a chain prefix (e.g. "polygon:0x...") or be raw.
  Future<Map<String, dynamic>> deleteWallet({required String address}) async {
    final dio = await create();
    final encoded = Uri.encodeComponent(address);
    final response = await dio.delete(
      '/wallets/$encoded',
      options: Options(validateStatus: (status) => status != null),
    );
    return _unwrapResponse('/wallets/$encoded', response);
  }

  /// Detect which blockchain(s) an address belongs to.
  ///
  /// Returns a map with detection results from the backend.
  Future<Map<String, dynamic>> detectBlockchain({
    required String address,
  }) async {
    return _getJsonMap(
      '/wallets/detect',
      queryParameters: {'address': address},
    );
  }

  Future<Map<String, String>> imageRequestHeaders() async {
    final token = await _tokenStore.readToken(profile);
    final sessionCookie = await _sessionStore.readSessionCookie(profile);
    return {
      if (profile.accessClientId.isNotEmpty)
        'CF-Access-Client-Id': profile.accessClientId,
      if (profile.accessClientSecret.isNotEmpty)
        'CF-Access-Client-Secret': profile.accessClientSecret,
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      if (sessionCookie != null && sessionCookie.isNotEmpty)
        'Cookie': sessionCookie,
    };
  }

  Future<Map<String, dynamic>> _getJsonMap(
    String path, {
    Map<String, dynamic>? queryParameters,
    bool revalidate = false,
  }) async {
    final dio = await create();
    try {
      final response = await dio.get(
        path,
        queryParameters: queryParameters,
        options: Options(
          validateStatus: (status) => status != null,
          extra: {
            if (revalidate) CacheInterceptor.revalidateExtra: true,
          },
        ),
      );
      return _unwrapResponse(path, response);
    } on DioException catch (error, stack) {
      _logTransportError(path, error, stack);
      rethrow;
    } catch (error, stack) {
      developer.log(
        'Unexpected API error for $path',
        name: 'ApiClient',
        error: error,
        stackTrace: stack,
      );
      rethrow;
    }
  }

  Map<String, dynamic> _unwrapResponse(
    String path,
    Response<dynamic> response,
  ) {
    final status = response.statusCode ?? 0;
    if (status == 401) {
      throw Exception('Session expired. Please sign in again.');
    }
    if (status == 403) {
      throw Exception('Access denied for $path.');
    }
    if (status >= 300 && status < 400) {
      final location = response.headers.value('location') ?? 'unknown';
      _logResponseFailure(path, response);
      throw Exception('Request redirected ($status) to $location');
    }
    if (status < 200 || status >= 300) {
      final detail = _detailFromBody(response.data);
      _logResponseFailure(path, response);
      throw Exception(detail ?? 'Request failed ($status) for $path');
    }

    final data = response.data;
    if (data is Map<String, dynamic>) {
      return data;
    }
    throw Exception('Unexpected response format from $path');
  }

  void _logTransportError(String path, DioException error, StackTrace stack) {
    final response = error.response;
    if (response != null) {
      _logResponseFailure(path, response, error: error, stack: stack);
      return;
    }
    developer.log(
      'Transport error for $path: ${error.message}',
      name: 'ApiClient',
      error: error,
      stackTrace: stack,
    );
  }

  void _logResponseFailure(
    String path,
    Response<dynamic> response, {
    Object? error,
    StackTrace? stack,
  }) {
    final status = response.statusCode ?? 0;
    final data = _safeBody(response.data);
    developer.log(
      'API failure $status for $path. Body: $data',
      name: 'ApiClient',
      error: error,
      stackTrace: stack,
    );
  }

  String _safeBody(dynamic body) {
    if (body == null) return '<empty>';
    String text;
    try {
      if (body is Map || body is List) {
        text = jsonEncode(body);
      } else {
        text = body.toString();
      }
    } catch (_) {
      text = body.toString();
    }
    if (text.length <= 2000) return text;
    return '${text.substring(0, 2000)}…(truncated)';
  }

  String? _detailFromBody(dynamic body) {
    if (body is Map<String, dynamic>) {
      final error = body['error'];
      if (error is String && error.trim().isNotEmpty) {
        return error;
      }
      final detail = body['detail'];
      if (detail is String && detail.trim().isNotEmpty) {
        return detail;
      }
      final message = body['message'];
      if (message is String && message.trim().isNotEmpty) {
        return message;
      }
      final errors = body['errors'];
      if (errors is List && errors.isNotEmpty) {
        final first = errors.first;
        if (first is String && first.trim().isNotEmpty) {
          return first;
        }
      }
    }
    return null;
  }

  String? _extractToken(dynamic body) {
    final map = _mapFromBody(body);
    if (map == null) return null;

    String? readTokenFrom(Map<String, dynamic> source) {
      const keys = ['access_token', 'token', 'jwt', 'id_token', 'bearer_token'];
      for (final key in keys) {
        final value = source[key];
        if (value is String && value.trim().isNotEmpty) {
          return value.trim();
        }
      }
      return null;
    }

    final direct = readTokenFrom(map);
    if (direct != null) return direct;

    for (final nestedKey in ['data', 'result', 'auth']) {
      final nested = map[nestedKey];
      if (nested is Map<String, dynamic>) {
        final token = readTokenFrom(nested);
        if (token != null) return token;
      }
      if (nested is Map) {
        final normalized = nested.map((k, v) => MapEntry('$k', v));
        final token = readTokenFrom(normalized);
        if (token != null) return token;
      }
    }
    return null;
  }

  Map<String, dynamic>? _mapFromBody(dynamic body) {
    if (body is Map<String, dynamic>) {
      return body;
    }
    if (body is Map) {
      return body.map((k, v) => MapEntry('$k', v));
    }
    if (body is String) {
      final trimmed = body.trim();
      if (trimmed.isEmpty) return null;
      try {
        final decoded = jsonDecode(trimmed);
        if (decoded is Map<String, dynamic>) {
          return decoded;
        }
        if (decoded is Map) {
          return decoded.map((k, v) => MapEntry('$k', v));
        }
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  Future<Response<dynamic>> _postLogin({
    required Dio dio,
    required String username,
    required String password,
  }) async {
    const paths = ['/api/auth/login', '/auth/login'];
    Response<dynamic>? fallbackResponse;

    for (final path in paths) {
      final response = await dio.post(
        path,
        data: {
          'username': username,
          'password': password,
        },
        options: Options(
          followRedirects: false,
          maxRedirects: 0,
          validateStatus: (status) => status != null,
        ),
      );

      final status = response.statusCode ?? 0;
      if (status != 404) {
        return response;
      }
      fallbackResponse = response;
    }

    return fallbackResponse ??
        Response<dynamic>(
          requestOptions: RequestOptions(path: paths.first),
          statusCode: 404,
        );
  }

  String? _extractSessionCookie(List<String>? setCookieValues) {
    if (setCookieValues == null || setCookieValues.isEmpty) {
      return null;
    }

    final cookies = <String>[];
    for (final raw in setCookieValues) {
      if (raw.trim().isEmpty) continue;
      try {
        final cookie = Cookie.fromSetCookieValue(raw);
        if (cookie.name.isNotEmpty) {
          cookies.add('${cookie.name}=${cookie.value}');
        }
      } catch (_) {
        final part = raw.split(';').first.trim();
        if (part.contains('=') && part.isNotEmpty) {
          cookies.add(part);
        }
      }
    }

    if (cookies.isEmpty) return null;
    return cookies.join('; ');
  }
}
