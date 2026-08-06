import 'package:abct_mobile/core/ui/app_refresh.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  /// Dispatches a lifecycle state through the real platform channel so the
  /// full binding → observer path is exercised.
  Future<void> sendLifecycleState(String state) async {
    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .handlePlatformMessage(
      SystemChannels.lifecycle.name,
      SystemChannels.lifecycle.codec.encodeMessage(state),
      (_) {},
    );
  }

  group('AppRefreshSignal policy', () {
    test('resume notifies listeners', () {
      final signal = AppRefreshSignal(minInterval: Duration.zero);
      addTearDown(signal.stop);
      var notifications = 0;
      signal.addListener(() => notifications++);

      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);

      expect(notifications, 1);
    });

    test('non-resume lifecycle states never notify', () {
      final signal = AppRefreshSignal(minInterval: Duration.zero);
      var notifications = 0;
      signal.addListener(() => notifications++);

      signal.didChangeAppLifecycleState(AppLifecycleState.inactive);
      signal.didChangeAppLifecycleState(AppLifecycleState.hidden);
      signal.didChangeAppLifecycleState(AppLifecycleState.paused);
      signal.didChangeAppLifecycleState(AppLifecycleState.detached);

      expect(notifications, 0);
    });

    test('min-interval guard suppresses rapid successive resumes', () {
      final signal = AppRefreshSignal(); // default 30s guard
      addTearDown(signal.stop);
      var notifications = 0;
      signal.addListener(() => notifications++);

      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);
      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);
      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);

      expect(notifications, 1);
    });

    test('start() seeds the guard so launch-adjacent resumes are skipped', () {
      final signal = AppRefreshSignal();
      var notifications = 0;
      signal.addListener(() => notifications++);

      signal.start();
      addTearDown(signal.stop);
      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);

      expect(notifications, 0);
    });

    test('start()/stop() are idempotent', () {
      final signal = AppRefreshSignal();
      signal.start();
      signal.start();
      expect(signal.isObserving, isTrue);
      expect(signal.isForegroundTimerActive, isTrue);
      signal.stop();
      signal.stop();
      expect(signal.isObserving, isFalse);
      expect(signal.isForegroundTimerActive, isFalse);
    });

    test('timer tick within the min-interval of a resume is coalesced', () {
      final signal = AppRefreshSignal(); // default 30s guard
      var notifications = 0;
      signal.addListener(() => notifications++);

      addTearDown(signal.stop);
      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);
      expect(notifications, 1);

      // A periodic tick landing right after the resume signal must not
      // double-fetch: both run through the same guarded path.
      signal.debugTick();
      expect(notifications, 1);
    });

    test('timer tick past the min-interval notifies', () {
      final signal = AppRefreshSignal(minInterval: Duration.zero);
      var notifications = 0;
      signal.addListener(() => notifications++);

      signal.debugTick();
      signal.debugTick();

      expect(notifications, 2);
    });
  });

  group('AppRefreshSignal foreground timer', () {
    testWidgets('fires at each interval while foregrounded', (tester) async {
      final signal = AppRefreshSignal(
        minInterval: Duration.zero,
        foregroundInterval: const Duration(minutes: 10),
      );
      var notifications = 0;
      signal.addListener(() => notifications++);
      signal.start();
      addTearDown(signal.stop);

      expect(signal.isForegroundTimerActive, isTrue);

      await tester.pump(const Duration(minutes: 10));
      expect(notifications, 1);

      await tester.pump(const Duration(minutes: 20));
      expect(notifications, 3);

      // Cancel before the binding's pending-timer check (teardowns run after
      // it); stop() is idempotent so the tearDown above stays as a safety net.
      signal.stop();
    });

    testWidgets('pauses while backgrounded and restarts on resume',
        (tester) async {
      final signal = AppRefreshSignal(
        minInterval: Duration.zero,
        foregroundInterval: const Duration(minutes: 10),
      );
      var notifications = 0;
      signal.addListener(() => notifications++);
      signal.start();
      addTearDown(signal.stop);

      signal.didChangeAppLifecycleState(AppLifecycleState.paused);
      expect(signal.isForegroundTimerActive, isFalse);

      await tester.pump(const Duration(minutes: 30));
      expect(notifications, 0);

      signal.didChangeAppLifecycleState(AppLifecycleState.resumed);
      expect(signal.isForegroundTimerActive, isTrue);
      expect(notifications, 1); // the resume signal itself

      await tester.pump(const Duration(minutes: 10));
      expect(notifications, 2); // first tick of the restarted cycle

      signal.stop();
    });

    testWidgets('inactive also stops the timer (app switcher peek)',
        (tester) async {
      final signal = AppRefreshSignal(
        minInterval: Duration.zero,
        foregroundInterval: const Duration(minutes: 10),
      );
      signal.start();
      addTearDown(signal.stop);

      signal.didChangeAppLifecycleState(AppLifecycleState.inactive);
      expect(signal.isForegroundTimerActive, isFalse);
    });

    testWidgets('stop() cancels the timer', (tester) async {
      final signal = AppRefreshSignal(
        minInterval: Duration.zero,
        foregroundInterval: const Duration(minutes: 10),
      );
      var notifications = 0;
      signal.addListener(() => notifications++);
      signal.start();
      signal.stop();

      expect(signal.isForegroundTimerActive, isFalse);
      await tester.pump(const Duration(minutes: 30));
      expect(notifications, 0);
    });
  });

  group('AppRefreshSignal lifecycle observation', () {
    testWidgets('receives resume events dispatched through the binding',
        (tester) async {
      final signal = AppRefreshSignal(minInterval: Duration.zero);
      var notifications = 0;
      signal.addListener(() => notifications++);
      signal.start();
      addTearDown(signal.stop);

      await sendLifecycleState('AppLifecycleState.paused');
      expect(notifications, 0);

      await sendLifecycleState('AppLifecycleState.resumed');
      expect(notifications, 1);

      signal.stop();
    });

    testWidgets('stop() unregisters the observer', (tester) async {
      final signal = AppRefreshSignal(minInterval: Duration.zero);
      var notifications = 0;
      signal.addListener(() => notifications++);
      signal.start();

      await sendLifecycleState('AppLifecycleState.paused');
      await sendLifecycleState('AppLifecycleState.resumed');
      expect(notifications, 1);

      signal.stop();
      await sendLifecycleState('AppLifecycleState.paused');
      await sendLifecycleState('AppLifecycleState.resumed');
      expect(notifications, 1);
    });
  });
}
