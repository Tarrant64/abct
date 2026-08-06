import 'package:flutter/material.dart';

import '../../core/storage/settings_repository.dart';
import '../../theme/app_theme.dart';

class SettingsController extends ChangeNotifier {
  SettingsController({SettingsRepository? repository})
      : _repository = repository ?? SettingsRepository();

  final SettingsRepository _repository;

  AppThemeName _themeName = AppThemeName.light;
  bool _biometricEnabled = false;
  bool _pinEnabled = false;
  bool _backgroundSyncEnabled = false;
  bool _notificationsEnabled = false;
  bool _loaded = false;

  AppThemeName get themeName => _themeName;
  bool get biometricEnabled => _biometricEnabled;
  bool get pinEnabled => _pinEnabled;
  bool get backgroundSyncEnabled => _backgroundSyncEnabled;
  bool get notificationsEnabled => _notificationsEnabled;
  bool get loaded => _loaded;

  /// Derive [ThemeMode] from the selected theme name.
  ThemeMode get themeMode =>
      _themeName == AppThemeName.light ? ThemeMode.light : ThemeMode.dark;

  /// Get the [ThemeData] for the current selection.
  ThemeData get themeData => AppTheme.forName(_themeName);

  Future<void> load() async {
    _themeName = await _repository.loadThemeName();
    _biometricEnabled = await _repository.loadBiometricEnabled();
    _pinEnabled = await _repository.loadPinEnabled();
    _backgroundSyncEnabled = await _repository.loadBackgroundSyncEnabled();
    _notificationsEnabled = await _repository.loadNotificationsEnabled();
    _loaded = true;
    notifyListeners();
  }

  Future<void> setThemeName(AppThemeName name) async {
    if (_themeName == name) return;
    _themeName = name;
    notifyListeners();
    await _repository.saveThemeName(name);
  }

  /// Legacy setter for backward compat (maps to light/dark only).
  Future<void> setThemeMode(ThemeMode mode) async {
    final name = mode == ThemeMode.light ? AppThemeName.light : AppThemeName.dark;
    await setThemeName(name);
  }

  Future<void> setBiometricEnabled(bool enabled) async {
    if (_biometricEnabled == enabled) return;
    _biometricEnabled = enabled;
    notifyListeners();
    await _repository.saveBiometricEnabled(enabled);
  }

  Future<void> setPinEnabled(bool enabled) async {
    if (_pinEnabled == enabled) return;
    _pinEnabled = enabled;
    notifyListeners();
    await _repository.savePinEnabled(enabled);
    if (!enabled) {
      await _repository.savePinCode(null);
    }
  }

  Future<void> setBackgroundSyncEnabled(bool enabled) async {
    if (_backgroundSyncEnabled == enabled) return;
    _backgroundSyncEnabled = enabled;
    notifyListeners();
    await _repository.saveBackgroundSyncEnabled(enabled);
  }

  Future<void> setNotificationsEnabled(bool enabled) async {
    if (_notificationsEnabled == enabled) return;
    _notificationsEnabled = enabled;
    notifyListeners();
    await _repository.saveNotificationsEnabled(enabled);
  }
}
