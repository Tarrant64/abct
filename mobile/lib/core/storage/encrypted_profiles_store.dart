import 'dart:convert';
import 'dart:math';

import 'package:cryptography/cryptography.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/connection_profile.dart';
import 'secure_store.dart';

class EncryptedProfilesStore {
  EncryptedProfilesStore({
    SecureStore? secureStore,
  }) : _secureStore = secureStore ?? SecureStore();

  static const _profilesKey = 'profiles_blob_v1';
  static const _encryptionKey = 'enc_key_v1';

  final SecureStore _secureStore;
  final AesGcm _cipher = AesGcm.with256bits();

  Future<List<ConnectionProfile>> loadProfiles() async {
    final prefs = await SharedPreferences.getInstance();
    final payload = prefs.getString(_profilesKey);
    if (payload == null || payload.isEmpty) {
      return [
        ConnectionProfile(
          name: 'Default',
          baseUrl: '',
          accessClientId: '',
          accessClientSecret: '',
          certPins: const [],
        )
      ];
    }

    final key = await _loadOrCreateKey();
    final decoded = jsonDecode(payload) as Map<String, dynamic>;
    final secretBox = SecretBox(
      base64Decode(decoded['ciphertext'] as String),
      nonce: base64Decode(decoded['nonce'] as String),
      mac: Mac(base64Decode(decoded['mac'] as String)),
    );

    final clear = await _cipher.decrypt(secretBox, secretKey: key);
    final clearJson = jsonDecode(utf8.decode(clear)) as Map<String, dynamic>;
    final list = (clearJson['profiles'] as List<dynamic>? ?? [])
        .map((e) => ConnectionProfile.fromJson(e as Map<String, dynamic>))
        .toList();

    return list.isEmpty
        ? [
            ConnectionProfile(
              name: 'Default',
              baseUrl: '',
              accessClientId: '',
              accessClientSecret: '',
              certPins: const [],
            )
          ]
        : list;
  }

  Future<void> saveProfiles(List<ConnectionProfile> profiles) async {
    final prefs = await SharedPreferences.getInstance();
    final key = await _loadOrCreateKey();

    final payload = jsonEncode({
      'profiles': profiles.map((p) => p.toJson()).toList(),
    });

    final secretBox = await _cipher.encrypt(
      utf8.encode(payload),
      secretKey: key,
      nonce: _randomNonce(),
    );

    final blob = jsonEncode({
      'nonce': base64Encode(secretBox.nonce),
      'ciphertext': base64Encode(secretBox.cipherText),
      'mac': base64Encode(secretBox.mac.bytes),
    });

    await prefs.setString(_profilesKey, blob);
  }

  Future<SecretKey> _loadOrCreateKey() async {
    final existing = await _secureStore.read(_encryptionKey);
    if (existing != null && existing.isNotEmpty) {
      return SecretKey(base64Decode(existing));
    }

    final bytes = List<int>.generate(32, (_) => Random.secure().nextInt(256));
    final encoded = base64Encode(bytes);
    await _secureStore.write(_encryptionKey, encoded);
    return SecretKey(bytes);
  }

  List<int> _randomNonce() =>
      List<int>.generate(12, (_) => Random.secure().nextInt(256));
}
