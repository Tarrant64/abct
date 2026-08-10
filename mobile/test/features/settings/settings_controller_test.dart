import 'dart:io';

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
    late List<String> syncCalls;

    setUp(() {
      SharedPreferences.setMockInitialValues({});
      // Fakes stand in for Workmanager, which has no platform channel here.
      syncCalls = <String>[];
      controller = SettingsController(
        repository: SettingsRepository(),
        registerPeriodicSync: () async => syncCalls.add('register'),
        cancelSync: () async => syncCalls.add('cancel'),
      );
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

    test('setBackgroundSyncEnabled schedules and cancels the periodic work',
        () async {
      // Persisting the preference alone is not enough: reArmIfEnabled() only
      // runs at launch, so the toggle has to touch WorkManager itself. A
      // missing cancel is the worse half — runPortfolioSyncTask does not
      // re-check the preference, so orphaned work syncs forever.
      await controller.load();

      await controller.setBackgroundSyncEnabled(true);
      expect(syncCalls, ['register']);

      await controller.setBackgroundSyncEnabled(false);
      expect(syncCalls, ['register', 'cancel']);
    });

    test('setBackgroundSyncEnabled with same value touches nothing', () async {
      await controller.load();

      await controller.setBackgroundSyncEnabled(false); // already false
      expect(syncCalls, isEmpty);
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

  group('background sync single-writer contract', () {
    test('the settings tab defers scheduling entirely to the controller', () {
      // The tab used to call BackgroundSync.registerPeriodicSync/cancelSync at
      // the call site as well, so flipping the switch hit WorkManager twice.
      // Idempotent, but two writers is the kind of duplication that drifts —
      // the controller is the only one that may schedule.
      final source = File('lib/features/home/tabs/settings_tab.dart')
          .readAsStringSync();

      // \b...\. matches a call on the BackgroundSync class without tripping on
      // the controller's setBackgroundSyncEnabled.
      expect(
        RegExp(r'\bBackgroundSync\.').hasMatch(source),
        isFalse,
        reason: 'settings_tab must route scheduling through SettingsController',
      );
      expect(
        source.contains('services/background_sync.dart'),
        isFalse,
        reason: 'the import should have gone with the call',
      );
      expect(source, contains('controller.setBackgroundSyncEnabled'));
    });
  });
}
