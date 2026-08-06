import 'package:abct_mobile/core/ui/smart_refresh.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Regression tests for the [SmartRefreshIndicator] hard/soft verdict.
///
/// RefreshIndicator invokes onRefresh asynchronously, after its snap
/// animation — long after the ScrollEndNotification. The original
/// implementation reset the hard flag on a 50ms timer after scroll end,
/// racing that callback: a hard pull could be downgraded to soft. These
/// tests drive the notification protocol directly (synthetic notifications
/// + RefreshIndicatorState.show()) so the orderings are deterministic and
/// independent of platform scroll physics.
void main() {
  const hardThreshold = 140.0;

  late List<bool> refreshCalls;

  Widget buildHarness() {
    refreshCalls = [];
    return MaterialApp(
      home: Scaffold(
        body: SmartRefreshIndicator(
          hardThreshold: hardThreshold,
          onRefresh: (hard) async {
            refreshCalls.add(hard);
          },
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: const [SizedBox(height: 40, child: Text('row'))],
          ),
        ),
      ),
    );
  }

  ScrollMetrics metricsWithPixels(double pixels) {
    return FixedScrollMetrics(
      minScrollExtent: 0,
      maxScrollExtent: 1000,
      pixels: pixels,
      viewportDimension: 600,
      axisDirection: AxisDirection.down,
      devicePixelRatio: 3.0,
    );
  }

  /// Dispatches a full drag sequence (start → overscroll update → end) from
  /// inside the SmartRefreshIndicator's child, as a real pull would.
  void dispatchPull(WidgetTester tester, {required double overscroll}) {
    final context = tester.element(find.text('row'));
    ScrollStartNotification(
      metrics: metricsWithPixels(0),
      context: context,
    ).dispatch(context);
    ScrollUpdateNotification(
      metrics: metricsWithPixels(-overscroll),
      context: context,
    ).dispatch(context);
    ScrollEndNotification(
      metrics: metricsWithPixels(0),
      context: context,
    ).dispatch(context);
  }

  Future<void> triggerRefresh(WidgetTester tester) async {
    final state = tester.state<RefreshIndicatorState>(
      find.byType(RefreshIndicator),
    );
    final done = state.show();
    await tester.pumpAndSettle();
    await done;
  }

  testWidgets('pull below the threshold reports a soft refresh',
      (tester) async {
    await tester.pumpWidget(buildHarness());

    dispatchPull(tester, overscroll: hardThreshold - 40);
    await tester.pump();
    await triggerRefresh(tester);

    expect(refreshCalls, [false]);
  });

  testWidgets(
      'pull past the threshold reports hard even when onRefresh fires long '
      'after scroll end (timer-reset race regression)', (tester) async {
    await tester.pumpWidget(buildHarness());

    dispatchPull(tester, overscroll: hardThreshold + 60);
    // The old implementation reset the hard flag 50ms after scroll end;
    // RefreshIndicator's onRefresh fires later than that (snap animation).
    await tester.pump(const Duration(milliseconds: 200));
    await triggerRefresh(tester);

    expect(refreshCalls, [true]);
  });

  testWidgets(
      'hard pull that never triggers a refresh does not contaminate the '
      'next soft pull', (tester) async {
    await tester.pumpWidget(buildHarness());

    // Hard pull, pushed back and released: no refresh follows.
    dispatchPull(tester, overscroll: hardThreshold + 60);
    await tester.pump(const Duration(milliseconds: 200));

    // Next gesture is a soft pull that does trigger a refresh.
    dispatchPull(tester, overscroll: hardThreshold - 40);
    await tester.pump();
    await triggerRefresh(tester);

    expect(refreshCalls, [false]);
  });

  testWidgets('hard verdict is consumed by the refresh it belongs to',
      (tester) async {
    await tester.pumpWidget(buildHarness());

    dispatchPull(tester, overscroll: hardThreshold + 60);
    await tester.pump(const Duration(milliseconds: 200));
    await triggerRefresh(tester);
    expect(refreshCalls, [true]);

    // A subsequent soft pull is not stuck hard.
    dispatchPull(tester, overscroll: hardThreshold - 40);
    await tester.pump();
    await triggerRefresh(tester);
    expect(refreshCalls, [true, false]);
  });
}
