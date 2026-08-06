import 'package:flutter/material.dart';

import '../../core/models/connection_profile.dart';
import '../../core/network/api_client.dart';
import '../../core/network/cache_store.dart';
import '../../core/storage/profiles_repository.dart';

class LoginController extends ChangeNotifier {
  LoginController({ProfilesRepository? repository})
      : _repository = repository ?? ProfilesRepository();

  final ProfilesRepository _repository;

  List<ConnectionProfile> profiles = [];
  int selectedIndex = 0;
  bool loading = false;
  String? errorMessage;
  String? successMessage;

  Future<void> load() async {
    profiles = await _repository.loadProfiles();
    selectedIndex = await _repository.loadSelectedIndex();
    if (selectedIndex >= profiles.length) {
      selectedIndex = 0;
    }
    notifyListeners();
  }

  ConnectionProfile get current => profiles[selectedIndex];

  void updateCurrent(ConnectionProfile updated) {
    profiles[selectedIndex] = updated;
    notifyListeners();
  }

  Future<void> saveProfiles() async {
    await _repository.saveProfiles(profiles);
    await _repository.saveSelectedIndex(selectedIndex);
  }

  Future<void> selectProfile(int index) async {
    if (index == selectedIndex) return;
    if (profiles.isEmpty) return;

    final previous = current;
    try {
      await ApiClient.shared(previous).logout();
    } catch (_) {
      // Ignore logout failure and still clear local auth state.
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

  Future<bool> login({
    required String username,
    required String password,
  }) async {
    loading = true;
    errorMessage = null;
    successMessage = null;
    notifyListeners();

    try {
      await saveProfiles();
      final api = ApiClient.shared(current);
      await api.login(username: username, password: password);
      successMessage = 'Login successful.';
      return true;
    } catch (e) {
      errorMessage = e.toString();
      return false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<String> testConnection() async {
    loading = true;
    errorMessage = null;
    successMessage = null;
    notifyListeners();

    try {
      await saveProfiles();
      final api = ApiClient.shared(current);
      final message = await api.testConnection();
      successMessage = message;
      return message;
    } catch (e) {
      errorMessage = e.toString();
      rethrow;
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
