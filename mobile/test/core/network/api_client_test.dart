import 'dart:convert';
import 'dart:io';

import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/core/storage/auth_session_store.dart';
import 'package:abct_mobile/core/storage/auth_token_store.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Keychain-read accounting and auth-cache invalidation for [ApiClient].
///
/// Before MOBILE-5 every API call built a fresh Dio: 2 keychain reads per
/// call. Now the configured client is cached: 2 reads per profile per auth
/// generation, and login/logout/clearAuthForProfile drop the cache.
class CountingTokenStore extends AuthTokenStore {
  int reads = 0;
  String? token;

  @override
  Future<String?> readToken(ConnectionProfile profile) async {
    reads++;
    return token;
  }
}

class CountingSessionStore extends AuthSessionStore {
  int reads = 0;
  String? cookie;

  @override
  Future<String?> readSessionCookie(ConnectionProfile profile) async {
    reads++;
    return cookie;
  }
}

/// TestWidgetsFlutterBinding stubs every HttpClient to return 400; this
/// restores real clients (base HttpOverrides builds the real
/// implementation) so the loopback login test can talk to its server.
class _RealHttpOverrides extends HttpOverrides {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // In-memory stand-in for flutter_secure_storage's platform channel so the
  // real AuthTokenStore/AuthSessionStore work in tests.
  final secureValues = <String, String>{};
  const channel =
      MethodChannel('plugins.it_nomads.com/flutter_secure_storage');

  setUp(() {
    secureValues.clear();
    ApiClient.resetSharedForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      final args =
          (call.arguments as Map?)?.cast<String, dynamic>() ?? const {};
      switch (call.method) {
        case 'read':
          return secureValues[args['key']];
        case 'write':
          secureValues[args['key'] as String] = args['value'] as String;
          return null;
        case 'delete':
          secureValues.remove(args['key']);
          return null;
        case 'readAll':
          return Map<String, String>.from(secureValues);
        case 'deleteAll':
          secureValues.clear();
          return null;
        case 'containsKey':
          return secureValues.containsKey(args['key']);
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  ConnectionProfile profileFor({
    String name = 'test',
    String baseUrl = 'https://example.invalid',
  }) =>
      ConnectionProfile(name: name, baseUrl: baseUrl);

  test('create() reuses one configured Dio: keychain read once, not per call',
      () async {
    final tokens = CountingTokenStore()..token = 'token-1';
    final sessions = CountingSessionStore();
    final client = ApiClient(
      profileFor(),
      tokenStore: tokens,
      sessionStore: sessions,
    );

    final dio1 = await client.create();
    final dio2 = await client.create();
    final dio3 = await client.create();

    expect(identical(dio1, dio2), isTrue);
    expect(identical(dio2, dio3), isTrue);
    expect(tokens.reads, 1);
    expect(sessions.reads, 1);
    expect(dio1.options.headers['Authorization'], 'Bearer token-1');
  });

  test('concurrent first calls collapse into a single keychain read pair',
      () async {
    final tokens = CountingTokenStore()..token = 'token-1';
    final sessions = CountingSessionStore();
    final client = ApiClient(
      profileFor(),
      tokenStore: tokens,
      sessionStore: sessions,
    );

    final dios = await Future.wait([
      client.create(),
      client.create(),
      client.create(),
    ]);

    expect(identical(dios[0], dios[1]), isTrue);
    expect(identical(dios[1], dios[2]), isTrue);
    expect(tokens.reads, 1);
    expect(sessions.reads, 1);
  });

  test('shared() returns one instance per profile', () {
    final a = ApiClient.shared(profileFor());
    final b = ApiClient.shared(profileFor());
    final other = ApiClient.shared(profileFor(name: 'other'));

    expect(identical(a, b), isTrue);
    expect(identical(a, other), isFalse);
  });

  test('clearAuthForProfile invalidates the shared client (logout path)',
      () async {
    final profile = profileFor();
    await AuthTokenStore().saveToken(profile, 'token-1');

    final client = ApiClient.shared(profile);
    final dio1 = await client.create();
    expect(dio1.options.headers['Authorization'], 'Bearer token-1');

    await ApiClient.clearAuthForProfile(profile);

    final dio2 = await client.create();
    expect(identical(dio1, dio2), isFalse);
    expect(dio2.options.headers.containsKey('Authorization'), isFalse);
  });

  test('login() invalidates so the next client carries the new token '
      '(re-auth path)', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({'access_token': 'token-2'}));
      await request.response.close();
    });

    final profile = profileFor(baseUrl: 'http://127.0.0.1:${server.port}');
    await AuthTokenStore().saveToken(profile, 'token-1');

    final client = ApiClient.shared(profile);
    final dio1 = await client.create();
    expect(dio1.options.headers['Authorization'], 'Bearer token-1');

    await HttpOverrides.runWithHttpOverrides(
      () => client.login(username: 'user', password: 'pass'),
      _RealHttpOverrides(),
    );

    final dio2 = await client.create();
    expect(identical(dio1, dio2), isFalse);
    expect(dio2.options.headers['Authorization'], 'Bearer token-2');
  });
}
