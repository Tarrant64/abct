import 'package:flutter/material.dart';

import 'settings_controller.dart';

class SettingsScope extends InheritedNotifier<SettingsController> {
  const SettingsScope({
    super.key,
    required SettingsController controller,
    required Widget child,
  }) : super(notifier: controller, child: child);

  static SettingsController of(BuildContext context) {
    final scope =
        context.dependOnInheritedWidgetOfExactType<SettingsScope>();
    assert(scope != null, 'SettingsScope not found in context');
    return scope!.notifier!;
  }

  static SettingsController? maybeOf(BuildContext context) {
    final scope =
        context.dependOnInheritedWidgetOfExactType<SettingsScope>();
    return scope?.notifier;
  }
}
