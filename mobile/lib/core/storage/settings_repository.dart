import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

class SettingsRepository {
  static const _themeModeKey = 'settings_theme_mode_v1';
  static const _themeNameKey = 'settings_theme_name_v1';
  static const _biometricKey = 'settings_biometric_enabled_v1';
  static const _backgroundSyncKey = 'settings_background_sync_v1';
  static const _notificationsEnabledKey = 'settings_notifications_enabled_v1';

  // --- Theme (legacy ThemeMode for backward compat) ---

  Future<ThemeMode> loadThemeMode() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_themeModeKey);
    return _decodeThemeMode(raw);
  }

  Future<void> saveThemeMode(ThemeMode mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_themeModeKey, _encodeThemeMode(mode));
  }

  String _encodeThemeMode(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.dark:
        return 'dark';
      case ThemeMode.light:
        return 'light';
      case ThemeMode.system:
        return 'system';
    }
  }

  ThemeMode _decodeThemeMode(String? raw) {
    switch (raw) {
      case 'dark':
        return ThemeMode.dark;
      case 'system':
        return ThemeMode.system;
      case 'light':
      default:
        return ThemeMode.light;
    }
  }

  // --- Named theme ---

  Future<AppThemeName> loadThemeName() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_themeNameKey);
    if (raw == null) {
      // Migrate from legacy ThemeMode
      final mode = await loadThemeMode();
      return mode == ThemeMode.dark ? AppThemeName.dark : AppThemeName.light;
    }
    return AppThemeName.values.firstWhere(
      (t) => t.name == raw,
      orElse: () => AppThemeName.light,
    );
  }

  Future<void> saveThemeName(AppThemeName name) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_themeNameKey, name.name);
    // Keep legacy key in sync for backward compat.
    final mode = name == AppThemeName.light ? ThemeMode.light : ThemeMode.dark;
    await saveThemeMode(mode);
  }

  // --- Biometric ---

  Future<bool> loadBiometricEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_biometricKey) ?? false;
  }

  Future<void> saveBiometricEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_biometricKey, enabled);
  }

  // --- PIN Lock ---

  static const _pinEnabledKey = 'settings_pin_enabled_v1';
  static const _pinCodeKey = 'settings_pin_code_v1';

  Future<bool> loadPinEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_pinEnabledKey) ?? false;
  }

  Future<void> savePinEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_pinEnabledKey, enabled);
  }

  Future<String?> loadPinCode() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_pinCodeKey);
  }

  Future<void> savePinCode(String? code) async {
    final prefs = await SharedPreferences.getInstance();
    if (code == null) {
      await prefs.remove(_pinCodeKey);
    } else {
      await prefs.setString(_pinCodeKey, code);
    }
  }

  // --- Background Sync ---

  Future<bool> loadBackgroundSyncEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_backgroundSyncKey) ?? false;
  }

  Future<void> saveBackgroundSyncEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_backgroundSyncKey, enabled);
  }

  // --- Notifications ---

  Future<bool> loadNotificationsEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_notificationsEnabledKey) ?? false;
  }

  Future<void> saveNotificationsEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_notificationsEnabledKey, enabled);
  }
}
