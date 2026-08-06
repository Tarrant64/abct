import 'package:shared_preferences/shared_preferences.dart';

import '../models/connection_profile.dart';
import 'encrypted_profiles_store.dart';

class ProfilesRepository {
  ProfilesRepository({EncryptedProfilesStore? store})
      : _store = store ?? EncryptedProfilesStore();

  static const _selectedIndexKey = 'profiles_selected_index_v1';

  final EncryptedProfilesStore _store;

  Future<List<ConnectionProfile>> loadProfiles() => _store.loadProfiles();

  Future<void> saveProfiles(List<ConnectionProfile> profiles) =>
      _store.saveProfiles(profiles);

  Future<int> loadSelectedIndex() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_selectedIndexKey) ?? 0;
  }

  Future<void> saveSelectedIndex(int index) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_selectedIndexKey, index);
  }
}
