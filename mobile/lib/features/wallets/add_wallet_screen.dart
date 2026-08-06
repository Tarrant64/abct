import 'dart:developer' as developer;

import 'package:flutter/material.dart';

import '../../core/models/connection_profile.dart';
import '../../core/network/api_client.dart';
import '../../core/ui/haptics.dart';
import '../../core/ui/section_card.dart';

/// Screen for adding a new self-custody wallet.
///
/// The user enters a wallet address and an optional label. The backend
/// auto-detects the blockchain from the address format. A "detect" preview
/// shows which chain was recognised before the user confirms.
class AddWalletScreen extends StatefulWidget {
  const AddWalletScreen({super.key, required this.profile});

  final ConnectionProfile profile;

  @override
  State<AddWalletScreen> createState() => _AddWalletScreenState();
}

class _AddWalletScreenState extends State<AddWalletScreen> {
  late final ApiClient _api;
  final _formKey = GlobalKey<FormState>();
  final _addressController = TextEditingController();
  final _labelController = TextEditingController();

  bool _submitting = false;
  bool _detecting = false;
  String? _detectedChain;
  String? _detectError;

  @override
  void initState() {
    super.initState();
    _api = ApiClient.shared(widget.profile);
  }

  @override
  void dispose() {
    _addressController.dispose();
    _labelController.dispose();
    super.dispose();
  }

  /// Ask the backend what blockchain this address belongs to.
  Future<void> _detect() async {
    final address = _addressController.text.trim();
    if (address.isEmpty) {
      setState(() {
        _detectedChain = null;
        _detectError = null;
      });
      return;
    }

    setState(() {
      _detecting = true;
      _detectError = null;
      _detectedChain = null;
    });

    try {
      final result = await _api.detectBlockchain(address: address);
      if (!mounted) return;

      // The detect endpoint returns something like:
      // {"address": "...", "blockchain": "cardano", "blockchains": ["cardano"]}
      final chain = result['blockchain'] as String?;
      final chains = result['blockchains'];

      if (chain != null && chain.isNotEmpty) {
        setState(() {
          _detectedChain = chain;
          _detecting = false;
        });
      } else if (chains is List && chains.isNotEmpty) {
        setState(() {
          _detectedChain = '${chains.first}';
          _detecting = false;
        });
      } else {
        setState(() {
          _detectError = 'Could not detect blockchain for this address.';
          _detecting = false;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _detectError = 'Detection failed: $e';
        _detecting = false;
      });
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    final address = _addressController.text.trim();
    final label = _labelController.text.trim();

    setState(() => _submitting = true);

    try {
      await _api.addWallet(
        address: address,
        label: label.isNotEmpty ? label : null,
      );

      if (!mounted) return;
      Haptics.success();

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Wallet added successfully.')),
      );

      Navigator.of(context).pop(true); // signal that a wallet was added
    } catch (e) {
      if (!mounted) return;
      Haptics.error();

      developer.log(
        'Failed to add wallet: $e',
        name: 'AddWalletScreen',
      );
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_friendlyError(e)),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String _friendlyError(Object e) {
    final msg = e.toString();
    if (msg.contains('403')) return 'Access denied. Please check your credentials.';
    if (msg.contains('404')) return 'Wallet not found.';
    if (msg.contains('409')) return 'This wallet has already been added.';
    return 'Something went wrong. Please try again.';
  }

  String _titleCase(String value) {
    if (value.isEmpty) return value;
    return value
        .split(RegExp(r'[_\s-]+'))
        .where((part) => part.isNotEmpty)
        .map((part) =>
            '${part[0].toUpperCase()}${part.substring(1).toLowerCase()}')
        .join(' ');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Add Wallet')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            SectionCard(
              title: 'Wallet Address',
              subtitle:
                  'Enter a self-custody wallet address. '
                  'The blockchain will be auto-detected.',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextFormField(
                    controller: _addressController,
                    decoration: const InputDecoration(
                      hintText: 'addr1..., 0x..., bc1..., etc.',
                      labelText: 'Address',
                    ),
                    keyboardType: TextInputType.text,
                    autocorrect: false,
                    enableSuggestions: false,
                    maxLines: 2,
                    minLines: 1,
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Please enter a wallet address.';
                      }
                      if (value.trim().length < 10) {
                        return 'Address seems too short.';
                      }
                      return null;
                    },
                    onChanged: (_) {
                      // Clear stale detection when address changes.
                      if (_detectedChain != null || _detectError != null) {
                        setState(() {
                          _detectedChain = null;
                          _detectError = null;
                        });
                      }
                    },
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _detecting ? null : _detect,
                    icon: _detecting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.search, size: 18),
                    label: Text(_detecting
                        ? 'Detecting...'
                        : 'Detect Blockchain'),
                  ),
                  if (_detectedChain != null) ...[
                    const SizedBox(height: 10),
                    _DetectionResult(
                      chain: _titleCase(_detectedChain!),
                      isError: false,
                    ),
                  ],
                  if (_detectError != null) ...[
                    const SizedBox(height: 10),
                    _DetectionResult(
                      chain: _detectError!,
                      isError: true,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),
            SectionCard(
              title: 'Label (Optional)',
              subtitle: 'Give your wallet a recognisable name.',
              child: TextFormField(
                controller: _labelController,
                decoration: const InputDecoration(
                  hintText: 'e.g. My Cardano Wallet',
                  labelText: 'Label',
                ),
                maxLength: 50,
              ),
            ),
            const SizedBox(height: 16),
            SectionCard(
              title: 'Supported Chains',
              subtitle: 'The backend can auto-detect these chains.',
              child: Wrap(
                spacing: 6,
                runSpacing: 6,
                children: const [
                  _ChainChip('Cardano'),
                  _ChainChip('Bitcoin'),
                  _ChainChip('Ethereum'),
                  _ChainChip('Solana'),
                  _ChainChip('Polygon'),
                  _ChainChip('Base'),
                  _ChainChip('Arbitrum'),
                  _ChainChip('Avalanche'),
                  _ChainChip('BNB Chain'),
                  _ChainChip('Tron'),
                  _ChainChip('XRP'),
                  _ChainChip('Cosmos'),
                  _ChainChip('Polkadot'),
                  _ChainChip('Tezos'),
                  _ChainChip('TON'),
                  _ChainChip('Sui'),
                  _ChainChip('And more...'),
                ],
              ),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: _submitting ? null : _submit,
              icon: _submitting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.add),
              label: Text(_submitting ? 'Adding...' : 'Add Wallet'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }
}

class _DetectionResult extends StatelessWidget {
  const _DetectionResult({required this.chain, required this.isError});

  final String chain;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isError ? theme.colorScheme.error : theme.colorScheme.primary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(
            isError ? Icons.warning_amber_rounded : Icons.check_circle_outline,
            color: color,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isError ? chain : 'Detected: $chain',
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChainChip extends StatelessWidget {
  const _ChainChip(this.name);

  final String name;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        name,
        style: TextStyle(
          fontSize: 12,
          color: scheme.onSurface.withValues(alpha: 0.8),
        ),
      ),
    );
  }
}
