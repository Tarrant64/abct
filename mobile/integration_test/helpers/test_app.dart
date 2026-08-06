/// Test app launcher that configures the app to use the mock backend.
///
/// This saves a connection profile pointing at the mock server into the
/// encrypted profile store, then launches the real AbctApp.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:abct_mobile/app.dart';
import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/storage/profiles_repository.dart';

import 'mock_server.dart';

/// Test credentials accepted by the mock server.
const testUsername = 'test';
const testPassword = 'test123';

/// Pre-populates the profile store with a test profile pointing at the
/// mock server, then returns the AbctApp widget ready for pumping.
///
/// Call [MockServer.start()] before this and pass the instance.
Future<Widget> buildTestApp(MockServer server) async {
  // Initialize SharedPreferences with empty defaults for settings.
  SharedPreferences.setMockInitialValues({
    'settings_theme_name_v1': 'dark',
    'settings_theme_mode_v1': 'dark',
    'settings_biometric_enabled_v1': false,
    'settings_pin_enabled_v1': false,
    'settings_background_sync_v1': false,
    'settings_notifications_enabled_v1': false,
    'profiles_selected_index_v1': 0,
  });

  // Save a test profile pointing at the mock server via the same path
  // the app uses. This writes the encrypted blob that loadProfiles() reads.
  final repo = ProfilesRepository();
  await repo.saveProfiles([
    ConnectionProfile(
      name: 'Test',
      baseUrl: server.baseUrl,
      connectionType: ConnectionType.local,
      accessClientId: '',
      accessClientSecret: '',
      certPins: const [],
    ),
  ]);
  await repo.saveSelectedIndex(0);

  return const AbctApp();
}
