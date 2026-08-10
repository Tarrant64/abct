import 'package:flutter/material.dart';
import 'package:local_auth/local_auth.dart';

import '../../../core/build_info.dart';
import '../../../core/models/connection_profile.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/cache_store.dart';
import '../../../core/storage/alert_repository.dart';
import '../../../core/storage/biometric_credential_store.dart';
import '../../../core/ui/biometric_labels.dart';
import '../../../core/ui/haptics.dart';
import '../../../core/ui/section_card.dart';
import '../../../theme/app_theme.dart';
import '../../login/login_screen.dart';
import '../../notifications/notification_settings_screen.dart';
import '../../profiles/profiles_screen.dart';
import '../../settings/settings_controller.dart';
import '../../settings/settings_scope.dart';

class SettingsTab extends StatefulWidget {
  const SettingsTab({super.key, required this.profile, this.apiClient});

  final ConnectionProfile profile;

  /// Injectable for tests; defaults to the shared per-profile client.
  final ApiClient? apiClient;

  @override
  State<SettingsTab> createState() => _SettingsTabState();
}

class _SettingsTabState extends State<SettingsTab> {
  late final ApiClient _api;

  @override
  void initState() {
    super.initState();
    _api = widget.apiClient ?? ApiClient.shared(widget.profile);
  }

  Future<void> _logout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text('Are you sure you want to sign out?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Sign Out'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      await _api.logout();
    } catch (_) {
      // Ignore logout API failures.
    }
    await AlertRepository().clearActiveProfile();
    await BiometricCredentialStore().clearCredentials(widget.profile);
    await CacheStore.instance.clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  Future<void> _toggleBiometric(
      SettingsController controller, bool enable) async {
    if (enable) {
      try {
        final localAuth = LocalAuthentication();
        final canCheck = await localAuth.canCheckBiometrics;
        if (!mounted) return;
        final isSupported = await localAuth.isDeviceSupported();
        if (!mounted) return;

        if (!canCheck && !isSupported) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                  'Biometric authentication is not available on this device.'),
            ),
          );
          return;
        }

        final didAuth = await localAuth.authenticate(
          localizedReason: 'Verify your identity to enable biometric login',
          options: const AuthenticationOptions(
            biometricOnly: false,
            stickyAuth: true,
          ),
        );
        if (!mounted) return;
        if (!didAuth) return;
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Biometric setup failed: $e')),
        );
        return;
      }

      controller.setBiometricEnabled(true);
      Haptics.light();

      if (!mounted) return;
      final bioLabel = biometricLabel;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '$bioLabel enabled. Sign out and back in to save your credentials.',
          ),
        ),
      );
    } else {
      // Disabling — clear stored credentials.
      await BiometricCredentialStore().clearCredentials(widget.profile);
      controller.setBiometricEnabled(false);
      Haptics.light();
    }
  }

  @override
  Widget build(BuildContext context) {
    // settings_scope import provides SettingsController via typedef
    final controller = SettingsScope.of(context);
    final theme = Theme.of(context);

    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            // --- Security section ---
            SectionCard(
              title: 'Security',
              subtitle: 'Control how you access the app.',
              child: Column(
                children: [
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: Text(biometricSettingLabel),
                    subtitle:
                        const Text('Sign in with biometrics instead of password'),
                    value: controller.biometricEnabled,
                    onChanged: (value) => _toggleBiometric(controller, value),
                    secondary: const Icon(Icons.fingerprint),
                  ),
                  const Divider(height: 1),
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('PIN Lock'),
                    subtitle: const Text('Require a PIN code to open the app'),
                    value: controller.pinEnabled,
                    onChanged: (value) {
                      Haptics.light();
                      controller.setPinEnabled(value);
                    },
                    secondary: const Icon(Icons.pin_outlined),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // --- Appearance section ---
            SectionCard(
              title: 'Appearance',
              subtitle: 'Choose a theme for the app.',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final name in AppThemeName.values)
                    RadioListTile<AppThemeName>(
                      title: Text(name.displayName),
                      value: name,
                      groupValue: controller.themeName,
                      onChanged: (value) {
                        if (value != null) controller.setThemeName(value);
                      },
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                    ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // --- Sync section ---
            SectionCard(
              title: 'Background Sync',
              subtitle: 'Keep portfolio data up to date.',
              child: SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('Background Sync'),
                subtitle: const Text(
                    'Periodic portfolio check with notifications'),
                value: controller.backgroundSyncEnabled,
                onChanged: controller.setBackgroundSyncEnabled,
              ),
            ),
            const SizedBox(height: 16),

            // --- Notifications section ---
            SectionCard(
              title: 'Notifications',
              subtitle: 'Configure portfolio and price alerts.',
              child: Column(
                children: [
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Enable Notifications'),
                    subtitle: const Text(
                        'Receive alerts for portfolio and price changes'),
                    value: controller.notificationsEnabled,
                    onChanged: (value) {
                      Haptics.light();
                      controller.setNotificationsEnabled(value);
                    },
                    secondary:
                        const Icon(Icons.notifications_outlined),
                  ),
                  if (controller.notificationsEnabled) ...[
                    const Divider(height: 1),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) =>
                                  const NotificationSettingsScreen(),
                            ),
                          );
                        },
                        icon: const Icon(Icons.tune),
                        label: const Text('Configure Alerts'),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),

            // --- Profiles section ---
            SectionCard(
              title: 'Profiles',
              subtitle: 'Manage connection details for sign-in.',
              child: ElevatedButton.icon(
                onPressed: () async {
                  await Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const ProfilesScreen(),
                    ),
                  );
                },
                icon: const Icon(Icons.manage_accounts_outlined),
                label: const Text('Manage Profiles'),
              ),
            ),
            const SizedBox(height: 16),

            // --- About section ---
            SectionCard(
              title: 'About',
              subtitle: 'Which code this install was built from.',
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.commit),
                title: const Text('Build'),
                subtitle: Text(BuildInfo.label),
              ),
            ),
            const SizedBox(height: 24),

            // --- Sign out ---
            FilledButton.icon(
              onPressed: _logout,
              icon: const Icon(Icons.logout),
              label: const Text('Sign Out'),
              style: FilledButton.styleFrom(
                backgroundColor: theme.colorScheme.error,
                foregroundColor: theme.colorScheme.onError,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 32),
          ],
        );
      },
    );
  }
}
