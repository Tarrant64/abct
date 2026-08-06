import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../models/connection_profile.dart';
import 'secure_store.dart';

class AuthSessionStore {
  AuthSessionStore({SecureStore? secureStore})
      : _secureStore = secureStore ?? SecureStore();

  final SecureStore _secureStore;

  Future<String?> readSessionCookie(ConnectionProfile profile) {
    return _secureStore.read(_sessionKey(profile));
  }

  Future<void> saveSessionCookie(ConnectionProfile profile, String cookie) {
    return _secureStore.write(_sessionKey(profile), cookie);
  }

  Future<void> clearSessionCookie(ConnectionProfile profile) {
    return _secureStore.delete(_sessionKey(profile));
  }

  String _sessionKey(ConnectionProfile profile) {
    final raw = [
      profile.baseUrl.trim().toLowerCase(),
      profile.accessClientId.trim(),
      profile.name.trim().toLowerCase(),
    ].join('|');
    final digest = sha256.convert(utf8.encode(raw)).toString();
    return 'auth_session_${digest.substring(0, 24)}';
  }
}
