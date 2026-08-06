import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:abct_mobile/core/storage/settings_repository.dart';
import 'package:abct_mobile/features/settings/settings_controller.dart';
import 'package:abct_mobile/theme/app_theme.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SettingsController', () {
    late SettingsController controller;

    setUp(() {
      SharedPreferences.setMockInitialValues({});
      controller = SettingsController(repository: SettingsRepository());
    });

    test('initial state before load', () {
      expect(controller.themeName, AppThemeName.light);
      expect(controller.biometricEnabled, isFalse);
      expect(controller.backgroundSyncEnabled, isFalse);
      expect(controller.loaded, isFalse);
    });

    test('load sets loaded to true', () async {
      await controller.load();
      expect(controller.loaded, isTrue);
    });

    test('defaults to light theme on fresh load', () async {
      await controller.load();
      expect(controller.themeName, AppThemeName.light);
      expect(controller.themeMode, ThemeMode.light);
    });

    test('setThemeName updates theme and notifies', () async {
      await controller.load();

      int notifyCount = 0;
      controller.addListener(() => notifyCount++);

      await controller.setThemeName(AppThemeName.cypherpunk);
      expect(controller.themeName, AppThemeName.cypherpunk);
      expect(controller.themeMode, ThemeMode.dark); // non-light = dark
      expect(notifyCount, 1);
    });

    test('setThemeName with same value does not notify', () async {
      await controller.load();

      int notifyCount = 0;
      controller.addListener(() => notifyCount++);

      await controller.setThemeName(AppThemeName.light); // same as default
      expect(notifyCount, 0);
    });

    test('setThemeMode maps to named theme', () async {
      await controller.load();

      await controller.setThemeMode(ThemeMode.dark);
      expect(controller.themeName, AppThemeName.dark);

      await controller.setThemeMode(ThemeMode.light);
      expect(controller.themeName, AppThemeName.light);
    });

    test('theme persists across loads', () async {
      await controller.load();
      await controller.setThemeName(AppThemeName.oceanDepths);

      // Create new controller with same prefs
      final controller2 = SettingsController(repository: SettingsRepository());
      await controller2.load();
      expect(controller2.themeName, AppThemeName.oceanDepths);
    });

    test('setBiometricEnabled updates and notifies', () async {
      await controller.load();

      int notifyCount = 0;
      controller.addListener(() => notifyCount++);

      await controller.setBiometricEnabled(true);
      expect(controller.biometricEnabled, isTrue);
      expect(notifyCount, 1);

      // Same value — no notify
      await controller.setBiometricEnabled(true);
      expect(notifyCount, 1);
    });

    test('setBackgroundSyncEnabled updates and notifies', () async {
      await controller.load();

      int notifyCount = 0;
      controller.addListener(() => notifyCount++);

      await controller.setBackgroundSyncEnabled(true);
      expect(controller.backgroundSyncEnabled, isTrue);
      expect(notifyCount, 1);
    });

    test('forName covers all AppThemeName values', () {
      // Verify every enum value is handled (no missing switch cases).
      for (final name in AppThemeName.values) {
        expect(name.displayName, isNotEmpty,
            reason: '${name.name} should have a display name');
      }
      // Verify the enum has the expected count.
      expect(AppThemeName.values.length, 5);
    });

    test('themeMode is light only for light theme', () async {
      await controller.load();

      await controller.setThemeName(AppThemeName.light);
      expect(controller.themeMode, ThemeMode.light);

      for (final name in [
        AppThemeName.dark,
        AppThemeName.oceanDepths,
        AppThemeName.sunsetHorizon,
        AppThemeName.cypherpunk,
      ]) {
        await controller.setThemeName(name);
        expect(controller.themeMode, ThemeMode.dark,
            reason: '${name.name} should use dark mode');
      }
    });
  });
}
