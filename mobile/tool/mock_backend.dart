/// Runs the integration-test MockServer as a standalone host process.
///
/// The emulator has no route to a real ABCT server, so this serves the same
/// canned responses the E2E suite uses. Pair it with `adb reverse` so the
/// device's own localhost reaches it:
///
///   dart run tool/mock_backend.dart &
///   adb -s emulator-5554 reverse tcp:8899 tcp:8899
///
/// Then add a profile in the app pointing at http://localhost:8899 and sign
/// in with the mock credentials (test / test123).
///
/// scripts/android_run.sh --mock does both steps for you.
library;

import 'dart:io';

import '../integration_test/helpers/mock_server.dart';

Future<void> main(List<String> args) async {
  final port = args.isEmpty ? 8899 : int.parse(args.first);
  final server = await MockServer.start(port: port);

  stdout.writeln('ABCT mock backend listening on ${server.baseUrl}');
  stdout.writeln('Credentials: test / test123');
  stdout.writeln('Stop with Ctrl-C.');

  // Keep the isolate alive until interrupted.
  await ProcessSignal.sigint.watch().first;
  await server.stop();
  stdout.writeln('\nmock backend stopped');
}
