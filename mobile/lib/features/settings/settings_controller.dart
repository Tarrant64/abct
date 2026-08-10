import 'package:flutter/material.dart';

import '../../core/services/background_sync.dart';
import '../../core/storage/settings_repository.dart';
import '../../theme/app_theme.dart';

class SettingsController extends ChangeNotifier {
  SettingsController({
    SettingsRepository? repository,
    Future<void> Function()? registerPeriodicSync,
    Future<void> Function()? cancelSync,
  })  : _repository = repository ?? SettingsRepository(),
        _registerPeriodicSync =
            registerPeriodicSync ?? BackgroundSync.registerPeriodicSync,
        _cancelSync = cancelSync ?? BackgroundSync.cancelSync;

  final SettingsRepository _repository;

  /// Injected so unit tests can drive the toggle without a Workmanager
  /// platform channel.
  final Future<void> Function() _registerPeriodicSync;
  final Future<void> Function() _cancelSync;

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

    // Saving the preference is not enough. Only BackgroundSync.reArmIfEnabled()
    // reads it, and that runs once at launch — so without this the toggle would
    // not take effect until the next cold start, and switching it OFF would
    // never cancel work already registered (runPortfolioSyncTask does not
    // re-check the preference, so it would keep syncing indefinitely).
    if (enabled) {
      await _registerPeriodicSync();
    } else {
      await _cancelSync();
    }
  }

  Future<void> setNotificationsEnabled(bool enabled) async {
    if (_notificationsEnabled == enabled) return;
    _notificationsEnabled = enabled;
    notifyListeners();
    await _repository.saveNotificationsEnabled(enabled);
  }
}
