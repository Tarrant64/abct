import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/models/connection_profile.dart';
import '../../core/ui/section_card.dart';
import 'profiles_controller.dart';

class ProfilesScreen extends StatefulWidget {
  const ProfilesScreen({super.key});

  @override
  State<ProfilesScreen> createState() => _ProfilesScreenState();
}

class _ProfilesScreenState extends State<ProfilesScreen> {
  final _controller = ProfilesController();

  final _nameController = TextEditingController();
  final _baseUrlController = TextEditingController();
  final _clientIdController = TextEditingController();
  final _clientSecretController = TextEditingController();
  final _pinController = TextEditingController();
  List<String> _certPins = [];
  ConnectionType _connectionType = ConnectionType.cloudflare;

  @override
  void initState() {
    super.initState();
    _controller.load().then((_) {
      _syncFields();
      setState(() {});
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _nameController.dispose();
    _baseUrlController.dispose();
    _clientIdController.dispose();
    _clientSecretController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  void _syncFields() {
    if (_controller.profiles.isEmpty) return;
    final profile = _controller.current;
    _nameController.text = profile.name;
    _baseUrlController.text = profile.baseUrl;
    _clientIdController.text = profile.accessClientId;
    _clientSecretController.text = profile.accessClientSecret;
    _certPins = List<String>.from(profile.certPins);
    _connectionType = profile.connectionType;
  }

  ConnectionProfile _profileFromFields() {
    return ConnectionProfile(
      name: _nameController.text.trim().isEmpty
          ? 'Default'
          : _nameController.text.trim(),
      baseUrl: _baseUrlController.text.trim(),
      connectionType: _connectionType,
      accessClientId: _clientIdController.text.trim(),
      accessClientSecret: _clientSecretController.text.trim(),
      certPins: List<String>.from(_certPins),
    );
  }

  Future<void> _save() async {
    _controller.updateProfile(_controller.selectedIndex, _profileFromFields());
    await _controller.save();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Profiles saved.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Connection Profiles'),
        actions: [
          IconButton(
            onPressed: _save,
            icon: const Icon(Icons.save_outlined),
          )
        ],
      ),
      body: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          if (_controller.loading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (_controller.profiles.isEmpty) {
            return ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Text(
                  'No profiles yet.',
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 12),
                ElevatedButton.icon(
                  onPressed: () {
                    _controller.addProfile();
                    _syncFields();
                    setState(() {});
                  },
                  icon: const Icon(Icons.add),
                  label: const Text('Add profile'),
                ),
              ],
            );
          }

          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Text(
                'Choose a profile',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                initialValue: _controller.selectedIndex,
                items: [
                  for (var i = 0; i < _controller.profiles.length; i++)
                    DropdownMenuItem(
                      value: i,
                      child: Text(_controller.profiles[i].name),
                    )
                ],
                onChanged: (value) async {
                  if (value == null) return;
                  await _controller.selectProfile(value);
                  _syncFields();
                  if (!mounted) return;
                  setState(() {});
                },
                decoration: const InputDecoration(
                  labelText: 'Active profile',
                ),
              ),
              const SizedBox(height: 20),
              SectionCard(
                title: 'Details',
                child: Column(
                  children: [
                    DropdownButtonFormField<ConnectionType>(
                      value: _connectionType,
                      items: [
                        for (final type in ConnectionType.values)
                          DropdownMenuItem(
                            value: type,
                            child: Text(type.displayName),
                          ),
                      ],
                      onChanged: (value) {
                        if (value == null) return;
                        setState(() => _connectionType = value);
                      },
                      decoration: const InputDecoration(
                        labelText: 'Connection type',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _nameController,
                      decoration: const InputDecoration(
                        labelText: 'Profile name',
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _baseUrlController,
                      decoration: InputDecoration(
                        labelText: 'Server URL',
                        hintText: _connectionType == ConnectionType.local
                            ? 'http://192.168.1.100:8000'
                            : 'https://abct.example.com',
                      ),
                      keyboardType: TextInputType.url,
                      inputFormatters: [
                        FilteringTextInputFormatter.deny(' '),
                      ],
                    ),
                    if (_connectionType == ConnectionType.cloudflare) ...[
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: _clientIdController,
                        decoration: const InputDecoration(
                          labelText: 'CF Access Client ID (optional)',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: _clientSecretController,
                        decoration: const InputDecoration(
                          labelText: 'CF Access Client Secret (optional)',
                        ),
                        obscureText: true,
                      ),
                    ],
                  ],
                ),
              ),
              if (_connectionType == ConnectionType.cloudflare) ...[
                const SizedBox(height: 16),
                SectionCard(
                  title: 'TLS Certificate Pins',
                  subtitle: 'SHA-256 hashes for certificate pinning.',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_certPins.isEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Text(
                            'No pins configured. Connection will use default trust.',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.6),
                            ),
                          ),
                        ),
                      for (var i = 0; i < _certPins.length; i++)
                        ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            _certPins[i],
                            style: theme.textTheme.bodySmall?.copyWith(
                              fontFamily: 'monospace',
                              fontSize: 11,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.delete_outline, size: 20),
                            onPressed: () {
                              setState(() => _certPins.removeAt(i));
                            },
                          ),
                        ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Expanded(
                            child: TextFormField(
                              controller: _pinController,
                              decoration: const InputDecoration(
                                hintText: 'Base64 SHA-256 pin (44 chars)',
                                isDense: true,
                                contentPadding: EdgeInsets.symmetric(
                                    vertical: 10, horizontal: 12),
                              ),
                              style: theme.textTheme.bodySmall?.copyWith(
                                fontFamily: 'monospace',
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          IconButton(
                            icon: const Icon(Icons.add_circle_outline),
                            onPressed: () {
                              final pin = _pinController.text.trim();
                              if (pin.isEmpty) return;
                              if (pin.length != 44) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                        'Pin should be 44 characters (base64 SHA-256).'),
                                  ),
                                );
                                return;
                              }
                              setState(() {
                                _certPins.add(pin);
                                _pinController.clear();
                              });
                            },
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        _controller.addProfile();
                        _syncFields();
                        setState(() {});
                      },
                      icon: const Icon(Icons.add),
                      label: const Text('Add profile'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        _controller.removeProfile(_controller.selectedIndex);
                        _syncFields();
                        setState(() {});
                      },
                      icon: const Icon(Icons.delete_outline),
                      label: const Text('Remove'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: _save,
                child: const Text('Save profiles'),
              ),
            ],
          );
        },
      ),
    );
  }
}
