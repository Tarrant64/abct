import 'package:flutter/material.dart';

import '../../core/models/connection_profile.dart';

class StatusScreen extends StatelessWidget {
  const StatusScreen({super.key, required this.profile});

  final ConnectionProfile profile;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Connection Status'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Connected',
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Session established for ${profile.name}.',
              style: theme.textTheme.bodyLarge,
            ),
            const SizedBox(height: 24),
            _infoRow('Server', profile.baseUrl),
            _infoRow('Access Client', _obfuscated(profile.accessClientId)),
            _infoRow('Pinned certs', profile.certPins.length.toString()),
            const Spacer(),
            ElevatedButton.icon(
              onPressed: () {
                Navigator.of(context).pop();
              },
              icon: const Icon(Icons.logout),
              label: const Text('Back to login'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          SizedBox(
            width: 140,
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  String _obfuscated(String value) {
    if (value.length <= 6) return value;
    return '${value.substring(0, 3)}…${value.substring(value.length - 3)}';
  }
}
