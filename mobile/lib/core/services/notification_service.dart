import 'dart:io' show Platform;

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  /// Set up the plugin. [requestPermissions] must stay false when called from
  /// a background isolate — there is no Activity there to host a permission
  /// dialog, and the request would fail rather than prompt.
  static Future<void> initialize({bool requestPermissions = true}) async {
    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    const settings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
      macOS: iosSettings,
    );
    await _plugin.initialize(settings);
    if (requestPermissions) await _requestAndroidPermissions();
  }

  /// iOS asks for notification permission through the Darwin init settings
  /// above. Android 13 (API 33) made POST_NOTIFICATIONS a runtime grant, and
  /// the plugin does not ask on its own — without this, every notification the
  /// app posts is dropped silently.
  static Future<void> _requestAndroidPermissions() async {
    if (!Platform.isAndroid) return;
    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await android?.requestNotificationsPermission();
  }

  static Future<void> show({
    required String title,
    required String body,
    int id = 0,
  }) async {
    const androidDetails = AndroidNotificationDetails(
      'abct_portfolio',
      'Portfolio Updates',
      channelDescription: 'Notifications about portfolio value changes',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    );
    const iosDetails = DarwinNotificationDetails();
    const details = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
      macOS: iosDetails,
    );
    await _plugin.show(id, title, body, details);
  }

  static Future<void> showPriceAlert({
    required String title,
    required String body,
    int id = 0,
  }) async {
    const androidDetails = AndroidNotificationDetails(
      'abct_price_alerts',
      'Price Alerts',
      channelDescription: 'High-priority price movement and threshold alerts',
      importance: Importance.high,
      priority: Priority.high,
    );
    const iosDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );
    const details = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
      macOS: iosDetails,
    );
    await _plugin.show(id, title, body, details);
  }
}
