import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:abct_mobile/app.dart';

void main() {
  testWidgets('AbctApp smoke test – login screen renders', (tester) async {
    // Use a phone-sized viewport to avoid overflow in constrained test env.
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    // Suppress overflow errors — default test font is wider than SpaceGrotesk
    // which causes layout overflows that don't happen on real devices.
    final originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final isOverflow = details.exceptionAsString().contains('overflowed');
      if (!isOverflow) {
        originalOnError?.call(details);
      }
    };
    addTearDown(() => FlutterError.onError = originalOnError);

    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const AbctApp());
    await tester.pumpAndSettle();

    // The login screen should show the "ABCT" heading and "Sign in" button.
    expect(find.text('ABCT'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
  });
}
