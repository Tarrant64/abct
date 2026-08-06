import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/alert_config.dart';
import '../models/connection_profile.dart';

class AlertRepository {
  static const _portfolioAlertsKey = 'alert_portfolio_config_v1';
  static const _assetAlertsKey = 'alert_asset_configs_v1';
  static const _snapshotKey = 'alert_snapshot_v1';
  static const _activeProfileKey = 'alert_active_profile_v1';

  // --- Portfolio alerts ---

  Future<PortfolioAlertConfig> loadPortfolioAlerts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_portfolioAlertsKey);
    if (raw == null) return PortfolioAlertConfig();
    try {
      return PortfolioAlertConfig.fromJson(
        jsonDecode(raw) as Map<String, dynamic>,
      );
    } catch (_) {
      return PortfolioAlertConfig();
    }
  }

  Future<void> savePortfolioAlerts(PortfolioAlertConfig config) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_portfolioAlertsKey, jsonEncode(config.toJson()));
  }

  // --- Asset price alerts ---

  Future<List<AssetPriceAlert>> loadAssetAlerts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_assetAlertsKey);
    if (raw == null) return [];
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list
          .whereType<Map<String, dynamic>>()
          .map(AssetPriceAlert.fromJson)
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> saveAssetAlerts(List<AssetPriceAlert> alerts) async {
    final prefs = await SharedPreferences.getInstance();
    final json = alerts.map((a) => a.toJson()).toList();
    await prefs.setString(_assetAlertsKey, jsonEncode(json));
  }

  Future<void> addAssetAlert(AssetPriceAlert alert) async {
    final alerts = await loadAssetAlerts();
    alerts.add(alert);
    await saveAssetAlerts(alerts);
  }

  Future<void> removeAssetAlert(String id) async {
    final alerts = await loadAssetAlerts();
    alerts.removeWhere((a) => a.id == id);
    await saveAssetAlerts(alerts);
  }

  /// Load alerts for a specific symbol.
  Future<List<AssetPriceAlert>> loadAlertsForSymbol(String symbol) async {
    final all = await loadAssetAlerts();
    final lower = symbol.toLowerCase();
    return all.where((a) => a.symbol.toLowerCase() == lower).toList();
  }

  // --- Snapshot ---

  Future<AlertSnapshot?> loadSnapshot() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_snapshotKey);
    if (raw == null) return null;
    try {
      return AlertSnapshot.fromJson(
        jsonDecode(raw) as Map<String, dynamic>,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> saveSnapshot(AlertSnapshot snapshot) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_snapshotKey, jsonEncode(snapshot.toJson()));
  }

  // --- Active profile (for background isolate) ---

  Future<void> saveActiveProfile(ConnectionProfile profile) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_activeProfileKey, jsonEncode(profile.toJson()));
  }

  Future<ConnectionProfile?> loadActiveProfile() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_activeProfileKey);
    if (raw == null) return null;
    try {
      return ConnectionProfile.fromJson(
        jsonDecode(raw) as Map<String, dynamic>,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> clearActiveProfile() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_activeProfileKey);
  }
}
