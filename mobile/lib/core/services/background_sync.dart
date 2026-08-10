import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

import '../models/alert_config.dart';
import '../models/connection_profile.dart';
import '../network/api_client.dart';
import '../storage/alert_repository.dart';
import '../storage/settings_repository.dart';
import 'alert_evaluator.dart';
import 'notification_service.dart';

/// Background task identifier, used as BOTH the Workmanager uniqueName and
/// taskName. On iOS the callback receives the uniqueName (the taskName
/// parameter is ignored there), so the two must be the same string for the
/// dispatcher's task check to hold on both platforms. Must also match
/// BGTaskSchedulerPermittedIdentifiers in ios/Runner/Info.plist and the
/// WorkmanagerPlugin.registerPeriodicTask call in AppDelegate.swift —
/// a mismatch means iOS silently never runs the task.
const String kPortfolioSyncTask = 'com.abct.portfolioSync';

/// Pre-0.9-upgrade Android uniqueName; cancelled on re-registration so
/// devices that enabled sync under the old name don't keep a stale duplicate.
const String _kLegacyUniqueName = 'portfolio-sync';

/// Top-level callback required by Workmanager.
@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask(
    (taskName, inputData) => runPortfolioSyncTask(taskName),
  );
}

/// The background isolate has no Activity, so it must not ask for Android's
/// POST_NOTIFICATIONS grant — the app requests that on launch instead.
Future<void> _initializeForBackground() =>
    NotificationService.initialize(requestPermissions: false);

/// Notification signature shared by [NotificationService.show] and
/// [NotificationService.showPriceAlert].
typedef ShowNotification = Future<void> Function({
  required String title,
  required String body,
  int id,
});

/// Body of the background sync task, extracted from [callbackDispatcher] so
/// tests can drive it with fakes (the dispatcher itself needs a Workmanager
/// platform channel in a background isolate).
///
/// The portfolio fetch always runs and is awaited: warming the shared disk
/// cache that the UI reads on next open is the task's primary product, and
/// notification settings only gate the alerting on top of it.
@visibleForTesting
Future<bool> runPortfolioSyncTask(
  String taskName, {
  ApiClient Function(ConnectionProfile profile) apiClientFactory = ApiClient.new,
  Future<void> Function() initializeNotifications = _initializeForBackground,
  ShowNotification showNotification = NotificationService.show,
  ShowNotification showPriceAlert = NotificationService.showPriceAlert,
}) async {
  try {
    if (taskName != kPortfolioSyncTask) return true;

    final repo = AlertRepository();

    // Load active profile from SharedPreferences.
    final profile = await repo.loadActiveProfile();
    if (profile == null) {
      developer.log(
        'Background sync: no active profile',
        name: 'BackgroundSync',
      );
      return true;
    }

    // Network-first (revalidate) and awaited: the default cache path would
    // instantly serve the hours-old entry and kick a fire-and-forget refresh
    // that iOS could suspend mid-flight, leaving the cache exactly as old as
    // before. refresh stays false — automation must never force the server's
    // expensive upstream recompute; that is reserved for the user's hard pull.
    final api = apiClientFactory(profile);
    final summary = await api.getPortfolioSummary(revalidate: true);
    final currentValue = summary.totalValueUsd;

    final prefs = await SharedPreferences.getInstance();
    final notificationsEnabled =
        prefs.getBool('settings_notifications_enabled_v1') ?? false;

    // Load configs and snapshot.
    final portfolioConfig = await repo.loadPortfolioAlerts();
    final assetAlerts = await repo.loadAssetAlerts();
    final snapshot = await repo.loadSnapshot();

    final now = DateTime.now();
    final newFired = <String, DateTime>{};

    if (notificationsEnabled) {
      // Re-initialize notifications in background isolate.
      await initializeNotifications();

      // Evaluate portfolio alerts.
      final portfolioFired = AlertEvaluator.evaluatePortfolio(
        currentValue: currentValue,
        snapshot: snapshot,
        config: portfolioConfig,
      );

      for (final alert in portfolioFired) {
        await showNotification(
          title: alert.title,
          body: alert.body,
          id: alert.notificationId,
        );
        newFired['portfolio_${alert.notificationId}'] = now;
      }
    }

    // Build updated asset prices from portfolio holdings, evaluating
    // per-asset alerts along the way when notifications are enabled.
    final updatedPrices = <String, double>{
      ...?snapshot?.assetPrices,
    };
    for (final holding in summary.blockchains) {
      if (holding.symbol.isEmpty || holding.nativePriceUsd <= 0) continue;
      final sym = holding.symbol.toLowerCase();
      updatedPrices[sym] = holding.nativePriceUsd;

      if (!notificationsEnabled) continue;
      final alertsForSymbol =
          assetAlerts.where((a) => a.symbol.toLowerCase() == sym).toList();
      if (alertsForSymbol.isEmpty) continue;

      final assetFired = AlertEvaluator.evaluateAssetPrice(
        symbol: sym,
        currentPrice: holding.nativePriceUsd,
        snapshot: snapshot,
        alerts: alertsForSymbol,
      );
      for (final alert in assetFired) {
        if (alert.isHighPriority) {
          await showPriceAlert(
            title: alert.title,
            body: alert.body,
            id: alert.notificationId,
          );
        } else {
          await showNotification(
            title: alert.title,
            body: alert.body,
            id: alert.notificationId,
          );
        }
        newFired['asset_${alert.notificationId}'] = now;
      }
    }

    // The snapshot is saved even with notifications off: it is the baseline
    // the NEXT run's alert evaluation diffs against, and must track reality
    // so re-enabling alerts doesn't fire off week-old numbers.
    final updatedSnapshot = AlertSnapshot(
      portfolioValueUsd: currentValue,
      assetPrices: updatedPrices,
      timestamp: now,
      lastFired: {...?snapshot?.lastFired, ...newFired},
    );
    await repo.saveSnapshot(updatedSnapshot);

    developer.log(
      'Background sync complete: \$${currentValue.toStringAsFixed(2)}, '
      '${newFired.length} alerts fired',
      name: 'BackgroundSync',
    );
  } catch (e, st) {
    developer.log(
      'Background sync failed: $e',
      name: 'BackgroundSync',
      error: e,
      stackTrace: st,
    );
  }
  return true;
}

class BackgroundSync {
  /// Workmanager only ships iOS and Android implementations, so every entry
  /// point below is a no-op elsewhere. The repo carries linux/, macos/, web/
  /// and windows/ runner scaffolds, and on those the plugin throws
  /// UnimplementedError ('No implementation found for workmanager on this
  /// platform') — from the settings toggle that would land AFTER the
  /// preference was saved and the switch repainted, leaving the UI claiming a
  /// sync that was never scheduled.
  ///
  /// [kIsWeb] is checked separately because on web [defaultTargetPlatform]
  /// reports the platform the BROWSER is running on — it happily returns
  /// android or iOS there.
  @visibleForTesting
  static bool get isSupportedPlatform =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  static Future<void> initialize() async {
    if (!isSupportedPlatform) return;
    await Workmanager().initialize(callbackDispatcher);
  }

  static Future<void> registerPeriodicSync() async {
    if (!isSupportedPlatform) return;
    // Clear any registration made under the pre-upgrade uniqueName; the
    // replace policy below only covers work with the CURRENT name.
    await Workmanager().cancelByUniqueName(_kLegacyUniqueName);
    await Workmanager().registerPeriodicTask(
      kPortfolioSyncTask,
      kPortfolioSyncTask,
      // Android honors this directly. iOS ignores it — the 1h cadence there
      // comes from the frequency in AppDelegate's registerPeriodicTask call,
      // and even that is only a floor: iOS runs BGAppRefreshTasks
      // opportunistically on its own schedule.
      frequency: const Duration(hours: 1),
      constraints: Constraints(
        networkType: NetworkType.connected,
      ),
      existingWorkPolicy: ExistingPeriodicWorkPolicy.update,
    );
  }

  static Future<void> cancelSync() async {
    if (!isSupportedPlatform) return;
    await Workmanager().cancelByUniqueName(kPortfolioSyncTask);
  }

  /// Re-arms the periodic task on app launch when the user has Background
  /// Sync enabled.
  ///
  /// iOS only submits a BGAppRefreshTask request when the settings toggle
  /// flips or when a run self-reschedules the next one; nothing re-submits
  /// at launch. A chain broken by a force-quit or an expired request would
  /// therefore stay dead until the user re-toggled the setting. Safe to
  /// repeat: Android updates the existing work in place, iOS replaces the
  /// pending request for the same identifier.
  static Future<void> reArmIfEnabled() async {
    final enabled = await SettingsRepository().loadBackgroundSyncEnabled();
    if (enabled) {
      await registerPeriodicSync();
    }
  }
}
