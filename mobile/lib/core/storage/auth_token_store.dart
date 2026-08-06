import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../models/connection_profile.dart';
import 'secure_store.dart';

class AuthTokenStore {
  AuthTokenStore({SecureStore? secureStore})
      : _secureStore = secureStore ?? SecureStore();

  final SecureStore _secureStore;

  Future<String?> readToken(ConnectionProfile profile) {
    return _secureStore.read(_tokenKey(profile));
  }

  Future<void> saveToken(ConnectionProfile profile, String token) {
    return _secureStore.write(_tokenKey(profile), token);
  }

  Future<void> clearToken(ConnectionProfile profile) {
    return _secureStore.delete(_tokenKey(profile));
  }

  String _tokenKey(ConnectionProfile profile) {
    final raw = [
      profile.baseUrl.trim().toLowerCase(),
      profile.accessClientId.trim(),
      profile.name.trim().toLowerCase(),
    ].join('|');
    final digest = sha256.convert(utf8.encode(raw)).toString();
    return 'auth_token_${digest.substring(0, 24)}';
  }
}
