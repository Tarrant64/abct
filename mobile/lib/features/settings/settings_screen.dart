import 'package:flutter/material.dart';

import '../../core/ui/section_card.dart';
import '../../theme/app_theme.dart';
import '../profiles/profiles_screen.dart';
import 'settings_scope.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = SettingsScope.of(context);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              SectionCard(
                title: 'Appearance',
                subtitle: 'Choose a theme for the app UI.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Theme',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 10),
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
              SectionCard(
                title: 'Security',
                subtitle: 'Authentication preferences.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SwitchListTile(
                      title: const Text('Biometric Authentication'),
                      subtitle: const Text('Use Face ID / Touch ID to sign in'),
                      value: controller.biometricEnabled,
                      onChanged: (value) =>
                          controller.setBiometricEnabled(value),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              SectionCard(
                title: 'Background Sync',
                subtitle: 'Keep portfolio data up to date.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SwitchListTile(
                      title: const Text('Background Sync'),
                      subtitle: const Text(
                          'Periodic portfolio check with notifications'),
                      value: controller.backgroundSyncEnabled,
                      onChanged: (value) =>
                          controller.setBackgroundSyncEnabled(value),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              SectionCard(
                title: 'Profiles',
                subtitle: 'Manage connection details for sign-in.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    ElevatedButton.icon(
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
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
