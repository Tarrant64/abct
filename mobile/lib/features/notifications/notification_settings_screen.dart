import 'package:flutter/material.dart';

import '../../core/models/alert_config.dart';
import '../../core/services/notification_service.dart';
import '../../core/storage/alert_repository.dart';
import '../../core/ui/section_card.dart';

class NotificationSettingsScreen extends StatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  State<NotificationSettingsScreen> createState() =>
      _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState
    extends State<NotificationSettingsScreen> {
  final _repo = AlertRepository();
  PortfolioAlertConfig _portfolioConfig = PortfolioAlertConfig();
  List<AssetPriceAlert> _assetAlerts = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final config = await _repo.loadPortfolioAlerts();
    final alerts = await _repo.loadAssetAlerts();
    if (!mounted) return;
    setState(() {
      _portfolioConfig = config;
      _assetAlerts = alerts;
      _loading = false;
    });
  }

  Future<void> _toggleThreshold(double threshold, bool enabled) async {
    final thresholds = Set<double>.from(_portfolioConfig.enabledThresholds);
    if (enabled) {
      thresholds.add(threshold);
    } else {
      thresholds.remove(threshold);
    }
    final updated = PortfolioAlertConfig(enabledThresholds: thresholds);
    setState(() => _portfolioConfig = updated);
    await _repo.savePortfolioAlerts(updated);
  }

  Future<void> _removeAssetAlert(String id) async {
    await _repo.removeAssetAlert(id);
    setState(() {
      _assetAlerts.removeWhere((a) => a.id == id);
    });
  }

  String _alertDescription(AssetPriceAlert alert) {
    if (alert.type == AlertType.assetPriceThreshold) {
      final direction = alert.above ? 'above' : 'below';
      return 'Notify when $direction \$${alert.threshold.toStringAsFixed(2)}';
    }
    return 'Notify on ${alert.threshold.toStringAsFixed(0)}% change';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Alert Settings')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                // --- Portfolio alerts ---
                SectionCard(
                  title: 'Portfolio Alerts',
                  subtitle:
                      'Get notified when your total portfolio moves by these percentages.',
                  child: Column(
                    children: [
                      for (final threshold
                          in PortfolioAlertConfig.availableThresholds)
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                              '${threshold.toStringAsFixed(0)}% change'),
                          subtitle: Text(
                            'Alert when portfolio moves ${threshold.toStringAsFixed(0)}% or more',
                            style: theme.textTheme.bodySmall,
                          ),
                          value: _portfolioConfig.enabledThresholds
                              .contains(threshold),
                          onChanged: (value) =>
                              _toggleThreshold(threshold, value ?? false),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // --- Asset price alerts ---
                SectionCard(
                  title: 'Price Alerts',
                  subtitle:
                      'Per-asset alerts you\'ve configured from the asset detail screen.',
                  child: _assetAlerts.isEmpty
                      ? Padding(
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          child: Text(
                            'No price alerts configured.\nAdd them from the asset detail screen using the bell icon.',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.6),
                            ),
                            textAlign: TextAlign.center,
                          ),
                        )
                      : Column(
                          children: [
                            for (final alert in _assetAlerts)
                              Dismissible(
                                key: Key(alert.id),
                                direction: DismissDirection.endToStart,
                                background: Container(
                                  alignment: Alignment.centerRight,
                                  padding:
                                      const EdgeInsets.only(right: 16),
                                  color: theme.colorScheme.error,
                                  child: Icon(
                                    Icons.delete,
                                    color: theme.colorScheme.onError,
                                  ),
                                ),
                                onDismissed: (_) =>
                                    _removeAssetAlert(alert.id),
                                child: ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  leading: CircleAvatar(
                                    backgroundColor:
                                        theme.colorScheme.primaryContainer,
                                    child: Text(
                                      alert.symbol.isNotEmpty
                                          ? alert.symbol[0].toUpperCase()
                                          : '?',
                                      style: TextStyle(
                                        color: theme
                                            .colorScheme.onPrimaryContainer,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                  title: Text(
                                      alert.symbol.toUpperCase()),
                                  subtitle:
                                      Text(_alertDescription(alert)),
                                  trailing: IconButton(
                                    icon: const Icon(Icons.close,
                                        size: 18),
                                    onPressed: () =>
                                        _removeAssetAlert(alert.id),
                                  ),
                                ),
                              ),
                          ],
                        ),
                ),
                const SizedBox(height: 24),

                // --- Test notification ---
                OutlinedButton.icon(
                  icon: const Icon(Icons.notifications_active_outlined),
                  label: const Text('Send Test Notification'),
                  onPressed: () async {
                    await NotificationService.showPriceAlert(
                      title: 'Test Alert',
                      body:
                          "Notifications are working! You'll see alerts like this when your thresholds are triggered.",
                      id: 99999,
                    );
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content:
                              Text('Test notification sent — check your notification center'),
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                    }
                  },
                ),
              ],
            ),
    );
  }
}
