import 'package:flutter/material.dart';

import '../../core/models/connection_profile.dart';
import '../../core/network/api_client.dart';
import '../../core/network/cache_store.dart';
import '../../core/storage/profiles_repository.dart';

class ProfilesController extends ChangeNotifier {
  ProfilesController({ProfilesRepository? repository})
      : _repository = repository ?? ProfilesRepository();

  final ProfilesRepository _repository;

  List<ConnectionProfile> profiles = [];
  int selectedIndex = 0;
  bool loading = false;
  String? message;

  Future<void> load() async {
    loading = true;
    notifyListeners();

    profiles = await _repository.loadProfiles();
    selectedIndex = await _repository.loadSelectedIndex();
    if (selectedIndex >= profiles.length) {
      selectedIndex = 0;
    }

    loading = false;
    notifyListeners();
  }

  ConnectionProfile get current => profiles[selectedIndex];

  Future<void> selectProfile(int index) async {
    if (index == selectedIndex) return;
    if (profiles.isEmpty) return;

    final previous = current;
    try {
      await ApiClient.shared(previous).logout();
    } catch (_) {
      // Ignore logout failures when switching profile context.
    }
    await ApiClient.clearAuthForProfile(previous);
    await CacheStore.instance.clear();

    selectedIndex = index;
    await _repository.saveSelectedIndex(index);
    await ApiClient.clearAuthForProfile(current);
    notifyListeners();
  }

  void addProfile() {
    profiles.add(ConnectionProfile(
      name: 'Profile ${profiles.length + 1}',
      baseUrl: '',
      connectionType: ConnectionType.local,
    ));
    selectedIndex = profiles.length - 1;
    notifyListeners();
  }

  void updateProfile(int index, ConnectionProfile profile) {
    profiles[index] = profile;
    notifyListeners();
  }

  void removeProfile(int index) {
    if (profiles.length <= 1) {
      message = 'At least one profile is required.';
      notifyListeners();
      return;
    }
    profiles.removeAt(index);
    if (selectedIndex >= profiles.length) {
      selectedIndex = profiles.length - 1;
    }
    notifyListeners();
  }

  Future<void> save() async {
    await _repository.saveProfiles(profiles);
    await _repository.saveSelectedIndex(selectedIndex);
    message = 'Profiles saved.';
    notifyListeners();
  }
}
