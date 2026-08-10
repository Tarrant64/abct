import 'package:flutter/material.dart';
import 'package:local_auth/local_auth.dart';

import '../../core/storage/alert_repository.dart';
import '../../core/storage/biometric_credential_store.dart';
import '../../core/ui/biometric_labels.dart';
import '../../core/ui/haptics.dart';
import '../home/home_shell_screen.dart';
import '../settings/settings_scope.dart';
import '../settings/settings_screen.dart';
import 'login_controller.dart';

String get _biometricLabel => biometricLabel;
String get _biometricLabelInline => biometricLabelInline;

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late final LoginController _controller;
  final _credentialStore = BiometricCredentialStore();
  final _formKey = GlobalKey<FormState>();

  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();

  bool _biometricReady = false; // device supports + enabled + creds stored

  @override
  void initState() {
    super.initState();
    _controller = LoginController();
    _controller.load().then((_) {
      if (!mounted) return;
      setState(() {});
      _checkBiometricReady();
    });
  }

  /// Check if we can offer one-tap biometric login.
  Future<void> _checkBiometricReady() async {
    final settings = SettingsScope.maybeOf(context);
    if (settings == null || !settings.biometricEnabled) return;
    if (_controller.profiles.isEmpty) return;
    if (_validateConnection() != null) return;

    final hasCreds = await _credentialStore.hasCredentials(_controller.current);
    if (!mounted) return;
    if (hasCreds) {
      setState(() => _biometricReady = true);
      // Auto-trigger on first load.
      _doBiometricLogin();
    }
  }

  /// Perform the actual biometric → API login flow.
  Future<void> _doBiometricLogin() async {
    final profile = _controller.current;
    final creds = await _credentialStore.readCredentials(profile);
    if (creds == null) return;

    try {
      final localAuth = LocalAuthentication();
      final canAuth = await localAuth.canCheckBiometrics ||
          await localAuth.isDeviceSupported();
      if (!canAuth || !mounted) return;

      final didAuth = await localAuth.authenticate(
        localizedReason: 'Sign in to ABCT',
        options: const AuthenticationOptions(biometricOnly: true),
      );
      if (!didAuth || !mounted) return;

      Haptics.success();
      final ok = await _controller.login(
        username: creds.username,
        password: creds.password,
      );
      if (!mounted) return;
      setState(() {});
      if (ok) {
        await AlertRepository().saveActiveProfile(_controller.current);
        _navigateHome();
      }
    } catch (_) {
      // Biometric cancelled or unavailable — user can sign in manually.
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_controller.profiles.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Add a connection profile in Settings first.'),
        ),
      );
      return;
    }
    if (!_formKey.currentState!.validate()) return;

    final connectionError = _validateConnection();
    if (connectionError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(connectionError)),
      );
      return;
    }

    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    final ok = await _controller.login(
      username: username,
      password: password,
    );
    if (!mounted) return;
    setState(() {});
    if (!ok) return;

    Haptics.success();
    await AlertRepository().saveActiveProfile(_controller.current);

    final settings = SettingsScope.maybeOf(context);

    // If biometric already enabled (e.g. from settings), silently save creds.
    if (settings?.biometricEnabled == true) {
      await _credentialStore.saveCredentials(
        _controller.current,
        username: username,
        password: password,
      );
    } else {
      // Offer to enable biometric login if device supports it.
      if (mounted) {
        final enabled = await _offerBiometricSetup(username, password);
        if (enabled && mounted) {
          settings?.setBiometricEnabled(true);
        }
      }
    }

    if (mounted) _navigateHome();
  }

  /// Show a dialog offering biometric setup after a successful manual login.
  Future<bool> _offerBiometricSetup(
    String username,
    String password,
  ) async {
    try {
      final localAuth = LocalAuthentication();
      final canAuth = await localAuth.canCheckBiometrics ||
          await localAuth.isDeviceSupported();
      if (!canAuth || !mounted) return false;

      final enable = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Enable $_biometricLabel?'),
          content: Text(
            'Use $_biometricLabelInline to sign in next time instead of entering your password.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Not now'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Enable'),
            ),
          ],
        ),
      );
      if (enable != true || !mounted) return false;

      final didAuth = await localAuth.authenticate(
        localizedReason:
            'Verify $_biometricLabelInline to enable biometric sign-in',
        options: const AuthenticationOptions(biometricOnly: true),
      );
      if (!didAuth || !mounted) return false;

      await _credentialStore.saveCredentials(
        _controller.current,
        username: username,
        password: password,
      );
      Haptics.success();
      return true;
    } catch (_) {
      return false;
    }
  }

  void _navigateHome() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => HomeShellScreen(profile: _controller.current),
      ),
    );
  }

  String? _validateConnection() {
    if (_controller.profiles.isEmpty) {
      return 'Add a connection profile in Settings.';
    }
    final profile = _controller.current;
    final url = profile.baseUrl.trim();
    if (url.isEmpty) {
      return 'Enter the server URL.';
    }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      return 'Server URL must start with http:// or https://';
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Colors.black,
      body: Container(
        color: Colors.black,
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: AnimatedBuilder(
                  animation: _controller,
                  builder: (context, _) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Center(
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(28),
                            child: Image.asset(
                              'abct-logo.png',
                              width: 140,
                              height: 140,
                              fit: BoxFit.cover,
                            ),
                          ),
                        ),
                        const SizedBox(height: 20),
                        Center(
                          child: Text(
                            'ABCT',
                            style: theme.textTheme.headlineMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                              color: Colors.white,
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Center(
                          child: Text(
                            'Secure access to your private portfolio server.',
                            style: theme.textTheme.bodyLarge?.copyWith(
                              color: Colors.white70,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Biometric button (shown when biometric is ready)
                        if (_biometricReady) ...[
                          _buildCard(
                            context,
                            child: Column(
                              children: [
                                SizedBox(
                                  width: double.infinity,
                                  child: FilledButton.icon(
                                    onPressed: _controller.loading
                                        ? null
                                        : _doBiometricLogin,
                                    icon: const Icon(Icons.fingerprint),
                                    label: Text(
                                        'Sign in with $_biometricLabelInline'),
                                    style: FilledButton.styleFrom(
                                      padding: const EdgeInsets.symmetric(
                                          vertical: 14),
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  'or sign in with your password below',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: Colors.white38,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 18),
                        ],

                        _buildCard(
                          context,
                          title: 'Login',
                          child: Form(
                            key: _formKey,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                TextFormField(
                                  controller: _usernameController,
                                  decoration: const InputDecoration(
                                    labelText: 'Username',
                                  ),
                                  validator: (value) =>
                                      value == null || value.trim().isEmpty
                                          ? 'Enter a username'
                                          : null,
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: _passwordController,
                                  decoration: const InputDecoration(
                                    labelText: 'Password',
                                  ),
                                  obscureText: true,
                                  validator: (value) =>
                                      value == null || value.isEmpty
                                          ? 'Enter a password'
                                          : null,
                                ),
                                const SizedBox(height: 16),
                                ElevatedButton(
                                  onPressed:
                                      _controller.loading ? null : _submit,
                                  child: _controller.loading
                                      ? const SizedBox(
                                          height: 18,
                                          width: 18,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                          ),
                                        )
                                      : const Text('Sign in'),
                                ),
                                if (_controller.errorMessage != null) ...[
                                  const SizedBox(height: 12),
                                  Text(
                                    _controller.errorMessage!,
                                    style: theme.textTheme.bodySmall?.copyWith(
                                      color: theme.colorScheme.error,
                                    ),
                                  ),
                                ],
                                if (_controller.successMessage != null) ...[
                                  const SizedBox(height: 12),
                                  Text(
                                    _controller.successMessage!,
                                    style: theme.textTheme.bodySmall?.copyWith(
                                      color: theme.colorScheme.primary,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 18),
                        _buildCard(
                          context,
                          title: 'Connection Profile',
                          trailing: TextButton.icon(
                            onPressed: () async {
                              await Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => const SettingsScreen(),
                                ),
                              );
                              await _controller.load();
                              if (mounted) {
                                setState(() {});
                              }
                            },
                            icon: const Icon(Icons.settings_outlined),
                            label: const Text('Settings'),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _buildProfilePicker(),
                              if (_controller.profiles.isEmpty) ...[
                                const SizedBox(height: 8),
                                Text(
                                  'No profiles configured yet. Open Settings to add one.',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: Colors.white54,
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildProfilePicker() {
    if (_controller.profiles.isEmpty) {
      return const SizedBox.shrink();
    }
    return DropdownButtonFormField<int>(
      initialValue: _controller.selectedIndex,
      items: [
        for (var i = 0; i < _controller.profiles.length; i++)
          DropdownMenuItem(
            value: i,
            child: Text(_controller.profiles[i].name),
          )
      ],
      onChanged: (value) {
        if (value == null) return;
        _controller.selectProfile(value).then((_) {
          if (!mounted) return;
          setState(() {});
        });
      },
      decoration: const InputDecoration(
        labelText: 'Active profile',
      ),
    );
  }

  Widget _buildCard(
    BuildContext context, {
    String? title,
    required Widget child,
    Widget? trailing,
  }) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title != null) ...[
            Row(
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                ),
                const Spacer(),
                if (trailing != null) trailing,
              ],
            ),
            const SizedBox(height: 12),
          ],
          child,
        ],
      ),
    );
  }
}
