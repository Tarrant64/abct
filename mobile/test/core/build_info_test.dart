import 'package:abct_mobile/core/build_info.dart';
import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/features/home/tabs/settings_tab.dart';
import 'package:abct_mobile/features/settings/settings_controller.dart';
import 'package:abct_mobile/features/settings/settings_scope.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BuildInfo.labelFor', () {
    test('clean tree shows the bare SHA', () {
      expect(BuildInfo.labelFor('3472d69', false), '3472d69');
    });

    test('dirty tree is called out next to the SHA', () {
      expect(BuildInfo.labelFor('3472d69', true), '3472d69 (dirty tree)');
    });

    test('missing provenance is explicit, not blank', () {
      expect(BuildInfo.labelFor('unknown', false), contains('unknown'));
      expect(
        BuildInfo.labelFor('unknown', false),
        contains('build_device.sh'),
      );
      expect(BuildInfo.labelFor('', true), contains('unknown'));
    });

    test('label reflects the compile-time defines', () {
      // Tests run without --dart-define, so this pins the "unrecognizable
      // binary" presentation the Settings screen would show for such builds.
      expect(BuildInfo.label, BuildInfo.labelFor(BuildInfo.gitSha, BuildInfo.gitDirty));
    });
  });

  testWidgets('Settings About card shows the build provenance label',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    final controller = SettingsController();
    await controller.load();
    final profile = ConnectionProfile(
      name: 'test',
      baseUrl: 'https://example.invalid',
    );

    await tester.pumpWidget(
      SettingsScope(
        controller: controller,
        child: MaterialApp(
          home: Scaffold(
            body: SettingsTab(
              profile: profile,
              apiClient: ApiClient(profile),
            ),
          ),
        ),
      ),
    );

    await tester.scrollUntilVisible(find.text('Build'), 200);
    expect(find.text('Build'), findsOneWidget);
    expect(find.text(BuildInfo.label), findsOneWidget);
  });
}
