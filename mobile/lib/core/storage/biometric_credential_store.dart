import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../models/connection_profile.dart';
import 'secure_store.dart';

/// Stores login credentials (username + password) in secure storage
/// for biometric-authenticated auto-login.
class BiometricCredentialStore {
  BiometricCredentialStore({SecureStore? secureStore})
      : _secureStore = secureStore ?? SecureStore();

  final SecureStore _secureStore;

  Future<({String username, String password})?> readCredentials(
    ConnectionProfile profile,
  ) async {
    final raw = await _secureStore.read(_key(profile));
    if (raw == null || raw.isEmpty) return null;
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;
      final username = json['username'] as String?;
      final password = json['password'] as String?;
      if (username == null ||
          username.isEmpty ||
          password == null ||
          password.isEmpty) {
        return null;
      }
      return (username: username, password: password);
    } catch (_) {
      return null;
    }
  }

  Future<void> saveCredentials(
    ConnectionProfile profile, {
    required String username,
    required String password,
  }) {
    final json = jsonEncode({'username': username, 'password': password});
    return _secureStore.write(_key(profile), json);
  }

  Future<void> clearCredentials(ConnectionProfile profile) {
    return _secureStore.delete(_key(profile));
  }

  /// Check if credentials exist without reading them.
  Future<bool> hasCredentials(ConnectionProfile profile) async {
    final raw = await _secureStore.read(_key(profile));
    return raw != null && raw.isNotEmpty;
  }

  String _key(ConnectionProfile profile) {
    final raw = [
      profile.baseUrl.trim().toLowerCase(),
      profile.accessClientId.trim(),
      profile.name.trim().toLowerCase(),
    ].join('|');
    final digest = sha256.convert(utf8.encode(raw)).toString();
    return 'bio_cred_${digest.substring(0, 24)}';
  }
}
