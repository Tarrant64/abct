import 'dart:io' show Platform;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStore {
  SecureStore() : _storage = _createStorage();

  final FlutterSecureStorage _storage;

  static FlutterSecureStorage _createStorage() {
    if (Platform.isMacOS) {
      // Use the legacy file-based keychain on macOS. The Data Protection
      // keychain (useDataProtectionKeyChain: true) requires a proper Apple
      // Developer signing identity and fails with -34018 under ad-hoc signing.
      return const FlutterSecureStorage(
        mOptions: MacOsOptions(
          useDataProtectionKeyChain: false,
        ),
      );
    }
    if (Platform.isAndroid) {
      return const FlutterSecureStorage(
        aOptions: AndroidOptions(encryptedSharedPreferences: true),
      );
    }
    if (Platform.isIOS) {
      return const FlutterSecureStorage(
        iOptions: IOSOptions(
          accessibility: KeychainAccessibility.first_unlock_this_device,
        ),
      );
    }
    return const FlutterSecureStorage();
  }

  Future<String?> read(String key) => _storage.read(key: key);

  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  Future<void> delete(String key) => _storage.delete(key: key);
}
