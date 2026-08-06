import 'package:flutter/material.dart';

import 'core/ui/app_refresh.dart';
import 'features/login/login_screen.dart';
import 'features/settings/settings_controller.dart';
import 'features/settings/settings_scope.dart';
import 'theme/app_theme.dart';

class AbctApp extends StatefulWidget {
  const AbctApp({super.key});

  @override
  State<AbctApp> createState() => _AbctAppState();
}

class _AbctAppState extends State<AbctApp> {
  late final SettingsController _settingsController;

  @override
  void initState() {
    super.initState();
    _settingsController = SettingsController();
    _settingsController.load();
    // Emit app-wide refresh signals when the app returns to the foreground
    // so data tabs silently re-fetch instead of showing stale balances.
    AppRefreshSignal.instance.start();
  }

  @override
  void dispose() {
    AppRefreshSignal.instance.stop();
    _settingsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SettingsScope(
      controller: _settingsController,
      child: AnimatedBuilder(
        animation: _settingsController,
        builder: (context, _) {
          final isLight = _settingsController.themeName == AppThemeName.light;
          return MaterialApp(
            title: 'ABCT',
            theme: isLight ? _settingsController.themeData : AppTheme.light(),
            darkTheme:
                isLight ? AppTheme.dark() : _settingsController.themeData,
            themeMode: _settingsController.themeMode,
            debugShowCheckedModeBanner: false,
            home: const LoginScreen(),
          );
        },
      ),
    );
  }
}
