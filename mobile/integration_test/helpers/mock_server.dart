/// Local HTTP mock server that simulates the ABCT backend.
///
/// Starts on a random available port and serves realistic JSON responses
/// for all mobile API endpoints. No real credentials or servers are used.
library;

import 'dart:convert';
import 'dart:io';

/// A lightweight HTTP server that fakes the ABCT backend responses.
///
/// The server is stateful: calling [login] with the test credentials
/// sets a session cookie, which subsequent requests validate.
class MockServer {
  MockServer._();

  HttpServer? _server;
  String? _sessionToken;
  int _loginCount = 0;

  /// The base URL the test app should connect to (e.g. http://localhost:XXXXX).
  String get baseUrl => 'http://localhost:${_server!.port}';

  /// The port the server is listening on.
  int get port => _server!.port;

  /// Number of times the login endpoint was hit.
  int get loginCount => _loginCount;

  /// Start the mock server on a random available port.
  static Future<MockServer> start() async {
    final mock = MockServer._();
    mock._server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    mock._server!.listen(mock._handleRequest);
    return mock;
  }

  /// Stop the mock server.
  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }

  void _handleRequest(HttpRequest request) async {
    try {
      final path = request.uri.path;
      final method = request.method;

      // CORS headers for all responses.
      request.response.headers
        ..add('Access-Control-Allow-Origin', '*')
        ..add('Content-Type', 'application/json');

      if (method == 'OPTIONS') {
        request.response
          ..statusCode = 200
          ..close();
        return;
      }

      // Route matching.
      if (path == '/api/auth/login' || path == '/auth/login') {
        await _handleLogin(request);
      } else if (path == '/auth/logout') {
        _handleLogout(request);
      } else if (path == '/api/mobile/status') {
        _handleStatus(request);
      } else if (path == '/api/mobile/portfolio/summary') {
        _requireAuth(request, () => _handlePortfolioSummary(request));
      } else if (path == '/api/mobile/portfolio/instant') {
        _requireAuth(request, () => _handlePortfolioInstant(request));
      } else if (path == '/api/mobile/chart/portfolio-history') {
        _requireAuth(request, () => _handlePortfolioHistory(request));
      } else if (path == '/api/mobile/wallets') {
        _requireAuth(request, () => _handleWallets(request));
      } else if (path == '/api/mobile/exchanges/summary') {
        _requireAuth(request, () => _handleExchangesSummary(request));
      } else if (path == '/api/mobile/defi/staking') {
        _requireAuth(request, () => _handleStaking(request));
      } else if (path == '/api/mobile/nfts/summary') {
        _requireAuth(request, () => _handleNftsSummary(request));
      } else if (path == '/api/mobile/nfts/wall/nfts' ||
          path == '/nfts/wall/nfts') {
        _requireAuth(request, () => _handleNftWall(request));
      } else if (path == '/portfolio/all-holdings') {
        _requireAuth(request, () => _handleAllHoldings(request));
      } else if (path.startsWith('/api/mobile/chart/price/')) {
        _requireAuth(request, () => _handlePriceChart(request));
      } else if (path.startsWith('/api/mobile/asset/') &&
          path.endsWith('/wallet-breakdown')) {
        _requireAuth(request, () => _handleWalletBreakdown(request));
      } else if (path == '/portfolio/asset-detail') {
        _requireAuth(request, () => _handleAssetDetail(request));
      } else if (path == '/api/transactions') {
        _requireAuth(request, () => _handleTransactions(request));
      } else {
        request.response
          ..statusCode = 404
          ..write(jsonEncode({'error': 'Not found: $path'}))
          ..close();
      }
    } catch (e) {
      request.response
        ..statusCode = 500
        ..write(jsonEncode({'error': e.toString()}))
        ..close();
    }
  }

  void _requireAuth(HttpRequest request, void Function() handler) {
    final cookie = request.headers.value('cookie') ?? '';
    final authHeader = request.headers.value('authorization') ?? '';

    if (_sessionToken != null &&
        (cookie.contains(_sessionToken!) ||
            authHeader.contains(_sessionToken!))) {
      handler();
    } else {
      request.response
        ..statusCode = 401
        ..write(jsonEncode({'error': 'Session expired. Please sign in again.'}))
        ..close();
    }
  }

  Future<void> _handleLogin(HttpRequest request) async {
    _loginCount++;
    final body = await utf8.decodeStream(request);
    final data = jsonDecode(body) as Map<String, dynamic>;

    final username = data['username'] as String? ?? '';
    final password = data['password'] as String? ?? '';

    // Test credentials: test / test123
    if (username == 'test' && password == 'test123') {
      _sessionToken = 'mock-session-${DateTime.now().millisecondsSinceEpoch}';
      request.response
        ..statusCode = 200
        ..headers.add(
          'set-cookie',
          'session=$_sessionToken; Path=/; HttpOnly',
        )
        ..write(jsonEncode({
          'access_token': _sessionToken,
          'message': 'Login successful',
        }))
        ..close();
    } else {
      request.response
        ..statusCode = 401
        ..write(jsonEncode({'error': 'Invalid credentials.'}))
        ..close();
    }
  }

  void _handleLogout(HttpRequest request) {
    _sessionToken = null;
    request.response
      ..statusCode = 200
      ..write(jsonEncode({'message': 'Logged out'}))
      ..close();
  }

  void _handleStatus(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'status': 'ok',
        'version': '0.10.0',
        'uptime': 86400,
      }))
      ..close();
  }

  void _handlePortfolioSummary(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total_value_usd': 125432.67,
        'change_24h_usd': 2341.89,
        'change_24h_percent': 1.90,
        'last_updated': DateTime.now().toIso8601String(),
        'top_assets': [
          {
            'ticker': 'BTC',
            'asset_name': 'Bitcoin',
            'value_usd': 68420.50,
            'change_24h': 2.1,
            'quantity': 1.05,
            'sparkline': [67000, 67500, 68000, 68200, 68420],
          },
          {
            'ticker': 'ETH',
            'asset_name': 'Ethereum',
            'value_usd': 24150.00,
            'change_24h': -0.8,
            'quantity': 7.25,
            'sparkline': [3400, 3380, 3350, 3330, 3310],
          },
          {
            'ticker': 'ADA',
            'asset_name': 'Cardano',
            'value_usd': 15890.30,
            'change_24h': 4.5,
            'quantity': 23400.0,
            'sparkline': [0.65, 0.66, 0.67, 0.68, 0.679],
          },
          {
            'ticker': 'SOL',
            'asset_name': 'Solana',
            'value_usd': 8932.10,
            'change_24h': 1.2,
            'quantity': 52.8,
            'sparkline': [168, 169, 170, 169, 169.2],
          },
        ],
        'chain_allocation': {
          'Bitcoin': 54.6,
          'Ethereum': 19.3,
          'Cardano': 12.7,
          'Solana': 7.1,
          'Other': 6.3,
        },
      }))
      ..close();
  }

  void _handlePortfolioInstant(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total_value_usd': 125432.67,
        'change_24h_usd': 2341.89,
        'change_24h_percent': 1.90,
        'last_updated': DateTime.now().toIso8601String(),
      }))
      ..close();
  }

  void _handlePortfolioHistory(HttpRequest request) {
    final range = request.uri.queryParameters['range'] ?? '1d';
    final points = <Map<String, dynamic>>[];
    final now = DateTime.now();
    final count = switch (range) {
      '1d' => 24,
      '7d' => 168,
      '30d' => 30,
      '90d' => 90,
      '1y' => 365,
      _ => 24,
    };

    for (int i = count; i >= 0; i--) {
      points.add({
        'timestamp': now
            .subtract(Duration(hours: range == '1d' ? i : i * 24))
            .toIso8601String(),
        'value_usd': 120000 + (i * 50.0) + (i % 7) * 200,
      });
    }

    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'range': range,
        'points': points,
      }))
      ..close();
  }

  void _handleWallets(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total_wallets': 5,
        'last_updated': DateTime.now().toIso8601String(),
        'wallets': [
          {
            'address': 'addr1q9test...cardano',
            'label': 'Cardano Main',
            'blockchain': 'cardano',
            'balance': {
              'native': 23400.0,
              'native_symbol': 'ADA',
              'usd_value': 15890.30,
            },
            'token_count': 12,
            'nft_count': 45,
          },
          {
            'address': '0xtest...ethereum',
            'label': 'ETH Primary',
            'blockchain': 'ethereum',
            'balance': {
              'native': 7.25,
              'native_symbol': 'ETH',
              'usd_value': 24150.00,
            },
            'token_count': 8,
            'nft_count': 3,
          },
        ],
      }))
      ..close();
  }

  void _handleExchangesSummary(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total_exchanges': 3,
        'total_value_usd': 45231.00,
        'last_updated': DateTime.now().toIso8601String(),
        'exchanges': [
          {
            'name': 'coinbase',
            'display_name': 'Coinbase',
            'configured': true,
            'value_usd': 28400.00,
            'asset_count': 15,
            'last_sync': DateTime.now().toIso8601String(),
          },
          {
            'name': 'binance',
            'display_name': 'Binance',
            'configured': true,
            'value_usd': 12831.00,
            'asset_count': 22,
            'last_sync': DateTime.now().toIso8601String(),
          },
        ],
      }))
      ..close();
  }

  void _handleStaking(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total_staked_usd': 18500.00,
        'total_rewards_usd': 1250.30,
        'last_updated': DateTime.now().toIso8601String(),
        'positions': [
          {
            'pool_name': 'BLOOM Pool',
            'pool_ticker': 'BLOOM',
            'blockchain': 'cardano',
            'delegated_amount': 20000.0,
            'delegated_usd': 13600.00,
            'rewards_lifetime': 850.0,
            'rewards_usd': 578.00,
            'apy': 4.2,
            'active': true,
            'staked_symbol': 'ADA',
            'logo_url': '',
          },
          {
            'pool_name': 'Lido',
            'pool_ticker': 'stETH',
            'blockchain': 'ethereum',
            'delegated_amount': 1.5,
            'delegated_usd': 4900.00,
            'rewards_lifetime': 0.12,
            'rewards_usd': 672.30,
            'apy': 3.8,
            'active': true,
            'staked_symbol': 'stETH',
            'logo_url': '',
          },
        ],
      }))
      ..close();
  }

  void _handleNftsSummary(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total_nfts': 48,
        'total_value_usd': 5200.00,
        'blockchains': ['cardano', 'ethereum'],
        'last_updated': DateTime.now().toIso8601String(),
      }))
      ..close();
  }

  void _handleNftWall(HttpRequest request) {
    final limit =
        int.tryParse(request.uri.queryParameters['limit'] ?? '24') ?? 24;
    final offset =
        int.tryParse(request.uri.queryParameters['offset'] ?? '0') ?? 0;

    final items = <Map<String, dynamic>>[];
    for (int i = 0; i < limit && (offset + i) < 48; i++) {
      items.add({
        'asset_id': 'nft-${offset + i}',
        'name': 'Test NFT #${offset + i}',
        'collection_name': 'Test Collection',
        'blockchain': i % 2 == 0 ? 'cardano' : 'ethereum',
        'image_url': '',
        'value_usd': 100.0 + i * 10,
      });
    }

    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'total': 48,
        'nfts': items,
      }))
      ..close();
  }

  void _handleAllHoldings(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'holdings': [
          {
            'ticker': 'BTC',
            'asset_name': 'Bitcoin',
            'display_name': 'Bitcoin',
            'total_quantity': 1.05,
            'value_usd': 68420.50,
            'price_usd': 65162.38,
            'change_24h': 2.1,
          },
          {
            'ticker': 'ETH',
            'asset_name': 'Ethereum',
            'display_name': 'Ethereum',
            'total_quantity': 7.25,
            'value_usd': 24150.00,
            'price_usd': 3331.03,
            'change_24h': -0.8,
          },
          {
            'ticker': 'ADA',
            'asset_name': 'Cardano',
            'display_name': 'Cardano',
            'total_quantity': 23400.0,
            'value_usd': 15890.30,
            'price_usd': 0.679,
            'change_24h': 4.5,
          },
          {
            'ticker': 'SOL',
            'asset_name': 'Solana',
            'display_name': 'Solana',
            'total_quantity': 52.8,
            'value_usd': 8932.10,
            'price_usd': 169.17,
            'change_24h': 1.2,
          },
        ],
      }))
      ..close();
  }

  void _handlePriceChart(HttpRequest request) {
    final range = request.uri.queryParameters['range'] ?? '7d';
    final points = <Map<String, dynamic>>[];
    final now = DateTime.now();
    for (int i = 30; i >= 0; i--) {
      points.add({
        'timestamp': now.subtract(Duration(hours: i * 8)).toIso8601String(),
        'price': 65000.0 + (i * 100) + (i % 5) * 50,
      });
    }

    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'range': range,
        'points': points,
      }))
      ..close();
  }

  void _handleWalletBreakdown(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'symbol': 'BTC',
        'wallets': [
          {
            'address': 'bc1q...test',
            'label': 'Cold Storage',
            'quantity': 0.85,
            'value_usd': 55380.00,
          },
          {
            'address': 'Coinbase',
            'label': 'Coinbase',
            'quantity': 0.20,
            'value_usd': 13040.50,
          },
        ],
      }))
      ..close();
  }

  void _handleAssetDetail(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'symbol': 'BTC',
        'name': 'Bitcoin',
        'price_usd': 65162.38,
        'market_cap': 1280000000000,
        'volume_24h': 28500000000,
        'change_24h': 2.1,
        'high_24h': 66000.00,
        'low_24h': 64500.00,
        'ath': 73750.00,
        'ath_date': '2024-03-14',
      }))
      ..close();
  }

  void _handleTransactions(HttpRequest request) {
    request.response
      ..statusCode = 200
      ..write(jsonEncode({
        'transactions': [
          {
            'hash': '0xtesthash1',
            'blockchain': 'ethereum',
            'direction': 'received',
            'amount': 0.5,
            'symbol': 'ETH',
            'value_usd': 1665.00,
            'timestamp': DateTime.now()
                .subtract(const Duration(hours: 2))
                .toIso8601String(),
          },
          {
            'hash': '0xtesthash2',
            'blockchain': 'cardano',
            'direction': 'sent',
            'amount': 1000.0,
            'symbol': 'ADA',
            'value_usd': 679.00,
            'timestamp': DateTime.now()
                .subtract(const Duration(days: 1))
                .toIso8601String(),
          },
        ],
        'total': 2,
      }))
      ..close();
  }
}
