# ABCT Mobile

Cross-platform Flutter client for a private crypto portfolio backend behind Cloudflare Tunnel + Access.

## Setup
1. Install Flutter (stable) and ensure `flutter` is on PATH.
2. Install CocoaPods (macOS/iOS builds):
   - `brew install cocoapods`
   - or `sudo gem install cocoapods`
3. From this repo root, generate platform folders:
   - `flutter create .`
4. Fetch dependencies:
   - `flutter pub get`
5. Run:
   - `flutter run`

## Code Signing (Team ID)

The project ships with **no development team configured** — `DEVELOPMENT_TEAM` is
intentionally blank in `ios/Runner.xcodeproj/project.pbxproj`,
`macos/Runner.xcodeproj/project.pbxproj`, and
`macos/Runner/Configs/AppInfo.xcconfig`. To build for a device you must set your
own Apple Developer Team ID (found at
[developer.apple.com/account](https://developer.apple.com/account) under
Membership) in one of two ways:

- **Xcode UI (simplest)**: open `ios/Runner.xcworkspace`, select each target
  (Runner, the watch app, the widget extension) → *Signing & Capabilities* →
  choose your Team with *Automatically manage signing* enabled. Repeat in
  `macos/Runner.xcworkspace` for macOS builds. Xcode writes the team into the
  project file — avoid committing that change.
- **Command line**: pass it per build, e.g.
  `xcodebuild ... DEVELOPMENT_TEAM=YOURTEAMID`, or set it in a local,
  untracked xcconfig you include from the Runner configs.

The bundle identifiers and App Group are part of the app's design; if you fork
this app for your own backend, change them to identifiers under your own team.

Android release signing works the same way: no keystore ships with this repo, so
release builds fall back to debug signing with a warning until you supply your
own. See [`android/README-signing.md`](android/README-signing.md).

## Connection Profiles
The app stores connection profiles encrypted at rest. Each profile includes:
- Server URL (Cloudflare hostname)
- CF Access Client ID / Secret (service token)
- TLS certificate pins (base64 SHA-256)

Profiles are encrypted with AES-256-GCM using a per-device key stored in Keychain/Keystore.

## TLS Pinning
Pins are SHA-256 hashes of the PEM certificate string, encoded in base64. Add at least two pins to allow rotation.

Example to compute a pin (macOS):
```bash
openssl s_client -servername abct.example.com -connect abct.example.com:443 </dev/null 2>/dev/null | \
  openssl x509 -outform PEM | \
  openssl dgst -sha256 -binary | \
  openssl base64
```

Paste the output into the `TLS Cert Pins` field (comma-separated for multiple pins).

## Cloudflare Access
- Create a self-hosted Access application for your hostname.
- Create a Service Token and add a `Service Auth` policy for the app.
- Enable `Enforce Access JSON Web Token (JWT) validation` on the tunnel hostname.

The app sends `CF-Access-Client-Id` and `CF-Access-Client-Secret` headers on every request.

## Refresh & Caching Architecture

Data freshness is handled by three cooperating layers (all under `lib/core/`):

**Cache store** (`network/cache_store.dart`) — disk cache with an in-memory
LRU layer (32 entries). All file I/O is async; JSON over 64KB is
decoded/encoded off the UI isolate; writes are atomic (tmp file + rename).
Entries carry the server ETag. `clear()` wipes both layers and is called on
logout — do not weaken this.

**Cache interceptor** (`network/cache_interceptor.dart`) — stale-while-
revalidate on every GET:
- Fresh entry → served instantly (`x-cache: HIT`); if older than 30s it also
  revalidates in the background.
- Stale entry → served instantly (`x-cache: STALE`) + background revalidation.
- Background revalidations send `If-None-Match`; a `304` re-stamps the entry
  fresh without re-downloading and deliberately does NOT notify UI listeners.
- UI code subscribes via `CacheInterceptor.onRevalidated(path, cb)` to swap
  in fresh data the moment a revalidation lands (dispose the returned
  callback in `dispose()`). Matching is EXACT on the URL path (query ignored):
  `/api/mobile/wallets` never receives `/api/mobile/wallets/123` events.
- Logout safety: `CacheStore.clear()` bumps a generation fence; writes,
  touches, and interceptor requests in flight across the clear abandon their
  results instead of re-persisting the previous session's data.
- Request escape hatches: `refresh=true` query param = hard refresh (bypasses
  client cache AND busts the server cache); `Options.extra['revalidate']` =
  network-first soft refresh (bypasses cache serving, still updates the cache,
  still falls back to cache offline).

**Refresh signals** (`ui/app_refresh.dart`, `ui/smart_refresh.dart`) —
`AppRefreshSignal` emits when the app returns to the foreground (30s
min-interval); every data tab subscribes and silently reloads, keeping current
content on screen until new data arrives. `SmartRefreshIndicator` distinguishes
soft pulls (network-first revalidate) from hard pulls past 140px (server-side
refresh, amber indicator).

**API client** (`network/api_client.dart`) — use `ApiClient.shared(profile)`;
it caches the configured Dio so auth headers cost one keychain read pair per
auth generation instead of two reads per call. The cache is invalidated by
`login()`, `logout()`, and `clearAuthForProfile()` — any new code path that
mutates credentials must invalidate it too. Certificate pinning uses one
`HttpClient` factory shared by the primary adapter and the interceptor's
background revalidation path. Tabs accept an optional `apiClient` constructor
parameter for tests.

Portfolio-history fetches request `?slim=true` (server D4 contract): chart
points carry exactly `{"timestamp","total_value_usd"}`, ~74% smaller payloads.
Nothing in the app (chart or watch sync) reads the dropped per-point fields.

### Performance refactor changelog (2026-07)

Branch `refactor/fable-performance`, phases MOBILE-1..7:
1. Lifecycle-aware auto-refresh; revalidation propagation to the dashboard;
   fixed a pinning bypass on the background revalidation path.
2. Network-first soft pull (never re-serves the entry it refreshes); client
   summary TTL aligned to the server's 120s; refresh signal rolled out to all
   tabs.
3. No cache-nulling during refresh (content stays visible; errors fall back
   to cached content); deduped instant/watch-sync fetches; fixed a 50ms timer
   race that downgraded hard pulls to soft.
4. Async cache store with LRU + ETag/304 conditional revalidation.
5. Shared API client with cached auth headers (keychain reads: 2-per-call →
   2-per-auth-generation); client injectable into tabs for widget tests.
6. Value-equality chart repaints + RepaintBoundary; slim history payloads.
7. Dead code removal, NFT URL + holdings sort memoization, e2e login-tap fix,
   this documentation.

## E2E Tests

```bash
./scripts/run_e2e_tests.sh                    # combined suite, auto-selects a simulator
./scripts/run_e2e_tests.sh --functional       # functional suite only
./scripts/run_e2e_tests.sh "iPhone 17 Pro"    # specific simulator
```

## Installing on a Physical iPhone

Always push to a device with the build script — not a bare `flutter build` /
`flutter run`:

```bash
./scripts/build_device.sh                 # build HEAD, re-sign, install
./scripts/build_device.sh --allow-dirty   # explicit override for WIP builds
./scripts/build_device.sh --no-install    # build + re-sign only
./scripts/build_device.sh --device <udid> # non-default device
```

The script:
- refuses to build from a dirty tree (`--allow-dirty` to override), so the
  binary on the phone always corresponds to a known commit;
- embeds the git SHA and dirty flag via `--dart-define` — verify any install
  in the app under **Settings → About → Build**;
- re-signs all embedded frameworks with the development identity (Flutter's
  native-assets `objective_c.framework` is otherwise ad-hoc signed and
  physical devices reject the install) and re-seals the watch app and
  `Runner.app` with their original entitlements;
- verifies the watch app is present in the bundle before installing and that
  the app is present on the device afterwards.

A build made any other way shows `unknown — built without
scripts/build_device.sh` in Settings → About and should not be used to judge
app behavior.

## Android

The Android build targets phones running Android 7.0 (API 24) or newer and is
built against the SDK 36 platform. Application ID is `com.teamcata.abct`.

### Build prerequisites

Flutter does not pick up a Homebrew-installed Android SDK on its own, and there
is no system JVM on this machine. Point Flutter at the SDK once:

```bash
flutter config --android-sdk /opt/homebrew/share/android-commandlinetools
```

Then export these in any shell that runs a Gradle build — without `JAVA_HOME`,
Gradle dies in non-login shells:

```bash
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
```

Required SDK packages (`sdkmanager --install ...`): `platforms;android-36`,
`build-tools;36.0.0`, `platform-tools`. The Gradle wrapper pins
`gradle-8.14-all`, so the first build downloads ~220MB and takes 10-20 minutes;
subsequent builds are under a minute. Gradle also pulls the NDK and CMake on
first run even though no plugin in this project ships native code.

Verify with `flutter doctor -v` — the Android toolchain line must be green
before building.

### Building and installing

```bash
flutter build apk --debug      # build/app/outputs/flutter-apk/app-debug.apk
flutter build apk --release    # build/app/outputs/flutter-apk/app-release.apk
adb install -r <path-to-apk>
```

`scripts/android_run.sh` (below) wraps this. Note that
`scripts/build_device.sh` is iOS-only, so Android builds do not stamp the git
SHA into **Settings → About → Build**.

### Android emulator / testing

There is no physical Android device, so **an emulator is the only Android test
target** and the setup below is the supported path.

#### One-time setup

Install the SDK, a JDK 17, and the API 35 arm64 system image:

```bash
brew install --cask android-commandlinetools
brew install openjdk@17
sdkmanager --install "system-images;android-35;google_apis;arm64-v8a" \
                     "platforms;android-36" "build-tools;36.0.0" "platform-tools" "emulator"
```

Create the AVDs (the helper scripts export `JAVA_HOME`/`ANDROID_HOME`
themselves, so you only need them for `avdmanager`):

```bash
avdmanager create avd -n abct_pixel  -k "system-images;android-35;google_apis;arm64-v8a" -d pixel_6
avdmanager create avd -n abct_tablet -k "system-images;android-35;google_apis;arm64-v8a" -d pixel_tablet
```

| AVD | Profile | Why |
|-----|---------|-----|
| `abct_pixel` | Pixel 6, 1080x2400 | Default. Phone-sized target for everyday work. |
| `abct_tablet` | Pixel Tablet, 2560x1600 | Large-screen layout checks. Reuses the same system image, so it costs no extra download. |

The tablet AVD has already earned its keep: the app **runs** correctly at
2560x1600 (login, sign-in, dashboard, charts and all six tabs work) but has no
large-screen adaptation, and the layout problems are only visible there:

- No max-width constraint outside the login card. On the dashboard the value
  hugs the far-left edge while the range selector stays centred, and the chart
  is stretched across the full 2560px.
- Settings and Connection Profiles put their labels at the extreme left and
  their switches at the extreme right, ~2400px apart, which is hard to scan.
- Landscape has much less vertical room, so the bottom of the dashboard list
  is clipped behind the navigation bar.

None of this is a crash and none of it reproduces on `abct_pixel`. Treat it as
known cosmetic debt, and re-check on the tablet before claiming a layout fix.

Both run **API 35**. There is deliberately no lower-API AVD: `minSdk` is 24, so
an API 24-34 gap does exist, but covering it means downloading another ~1.5GB
image, and the Android behaviors this app actually depends on
(`POST_NOTIFICATIONS`, the biometric prompt) are API 33+ features already
exercised on 35. Add one if an API-level regression is ever suspected.

> **`emulator -list-avds` may show AVDs that are not this project's.** Any
> whose system image lives in a different SDK will show as "could not be
> loaded" here. Never start, wipe or delete one you did not create for this
> app.

#### Helper scripts

```bash
./scripts/android_emu.sh start              # boot abct_pixel, wait for boot_completed
./scripts/android_emu.sh start --headless    # no window (CI-ish runs)
./scripts/android_emu.sh start --avd abct_tablet
./scripts/android_emu.sh status              # AVDs defined + emulators running
./scripts/android_emu.sh stop                # clean `emu kill`
```

```bash
./scripts/android_run.sh                     # debug, attached (hot reload)
./scripts/android_run.sh --release           # build + install + launch + tail logcat
./scripts/android_run.sh --mock              # also serve the E2E mock backend
./scripts/android_run.sh --test              # integration suite via `flutter test`
./scripts/android_run.sh --drive             # integration suite via `flutter drive`
./scripts/android_run.sh --logs              # tail this app's logcat only
./scripts/android_run.sh --perf-scale 40     # loosen the perf budgets further
```

Both start the emulator if it isn't already up and resolve the SDK/JDK paths
themselves — no shell-profile exports needed.

#### Running the app without a backend

The emulator cannot reach a real ABCT server. `tool/mock_backend.dart` serves
the same canned responses the E2E suite uses:

```bash
./scripts/android_run.sh --mock
```

That runs the mock on the host and `adb reverse`s port 8899, so inside the app
you add a **local** profile pointing at `http://localhost:8899` and sign in
with `test` / `test123`.

#### Integration tests

```bash
./scripts/android_run.sh --drive    # recommended: all tests pass
./scripts/android_run.sh --test     # 15/16 — see the timeline caveat below
```

**Use `--drive` on Android.** The "full flow timeline" test calls
`binding.traceAction()`, which needs a VM Service connection that `flutter
test` does not expose, so under `--test` that one test always fails with
`Bad state: Failed to connect to VM Service`. `--drive` runs the same suite
through `flutter drive --no-dds`, which provides the connection; `--no-dds` is
required, because with DDS in the way the connection is refused there too.
Last full run on `abct_pixel`: **17/17 via `--drive`**, **15/16 via `--test`**.

Three things make the suites portable across the iOS Simulator and an Android
emulator, all in `integration_test/helpers/test_app.dart`:

- `dismissBiometricOfferIfShown()` — once a fingerprint is enrolled, the login
  screen offers to enable biometric sign-in, and that dialog covers the home
  screen every post-login assertion looks for. A bare iOS Simulator never
  shows it, so the suite silently assumed it away.
- `navTab()` / `tapNavTab()` — a bare `find.text('Wallets')` is ambiguous once
  a tab body puts the same word on screen (the Assets tab's segmented control
  is Holdings / Wallets / Exchanges), which threw "ambiguously found multiple
  matching widgets" on three tests. Both helpers scope the finder to the
  `NavigationBar`.
- `--dart-define=ABCT_PERF_SCALE=<n>` multiplies every performance budget.
  The budgets are calibrated for a release-mode iOS Simulator run; a debug
  build on the emulator is roughly 10x slower (cold start ~15s against a 3s
  budget, data refresh ~21s against 2s), so unscaled they fail
  unconditionally. `android_run.sh` passes 30 by default. **A scaled run is a
  crash/regression check, not a performance measurement** — the numbers are
  comparable only to other runs at the same scale, never to the iOS figures.
  The tab-navigation figure is additionally quantised by the suite's own 5s
  `pumpAndSettle`, so it reads 5s or 10s regardless of real render time.

#### Exercising biometrics

`local_auth` needs an enrolled fingerprint, which needs a device credential:

```bash
adb -s emulator-5554 shell locksettings set-pin 1234
adb -s emulator-5554 shell am start -a android.settings.FINGERPRINT_ENROLL
# walk the wizard, then simulate touches until "Fingerprint added":
adb -s emulator-5554 emu finger touch 1
```

Verify with `adb shell dumpsys fingerprint` — look for `"count":1`. The same
`emu finger touch 1` satisfies the app's `BiometricPrompt` at runtime.

Both biometric paths have been driven end to end on `abct_pixel`: enabling the
toggle from the post-login offer, and unlocking at launch (the prompt appears
on its own, the touch is accepted, and the app signs in from stored
credentials without a password). Two notes for whoever repeats it:

- `adb exec-out screencap` returns an **all-black image** while a
  `BiometricPrompt` is up — it is a secure surface. Confirm the prompt with
  `adb shell dumpsys biometric` (look for `CurrentSession` with
  `BiometricRequested: true`) and confirm the touch landed by watching
  `accept` climb in `adb shell dumpsys fingerprint`.
- The offer dialog also appears on a device with **no** enrolled print,
  because the app accepts `isDeviceSupported()` as well as
  `canCheckBiometrics`.

#### Forcing background sync

WorkManager registers the periodic task via `BackgroundSync.registerPeriodicSync()`
— from the Settings toggle, and again at launch through `reArmIfEnabled()`.
Either way it shows up in logcat as
`WM-SystemJobScheduler: Scheduling work ID <uuid> Job ID <n>`. The job is
namespaced, so a forced run needs `-n`, and the job id is the one from that
log line:

```bash
adb -s emulator-5554 shell cmd jobscheduler run -f \
    -n androidx.work.systemjobscheduler com.teamcata.abct <jobid>
```

On its own that only proves dispatch. WorkManager refuses to run a periodic
worker before its interval has elapsed:

```
WM-WorkerWrapper: Delaying execution for ...BackgroundWorker because it is being executed before schedule.
WM-WorkerWrapper: Status for <uuid> is ENQUEUED; not doing any work and rescheduling for later execution
```

To actually execute the task body, push the device clock past the 1h period
first:

```bash
adb -s emulator-5554 root
adb -s emulator-5554 shell settings put global auto_time 0
adb -s emulator-5554 shell "date $(date -v+2H '+%m%d%H%M%Y.%S')"
# ...force the job again, then restore:
adb -s emulator-5554 shell settings put global auto_time 1
```

The body then really runs — `WM-WorkerWrapper: Starting work for
dev.fluttercommunity.workmanager.BackgroundWorker`, a background Flutter
isolate spins up, and it finishes `Worker result SUCCESS`. With a mock backend
reachable it issues the expected `GET /api/mobile/portfolio/summary`; with the
server unreachable it still returns SUCCESS and does not crash the app, which
is the graceful-degradation path `runPortfolioSyncTask` is written for.

#### What an emulator cannot verify

- **Real biometric hardware** — the emulator's fingerprint HAL always accepts
  the simulated touch. Rejection, lockout after repeated failures, and
  device-credential fallback are not meaningfully exercised.
- **OEM battery managers** — the throttling described under Known limitations
  is Samsung/Xiaomi/OnePlus behavior that stock emulator images do not
  reproduce, so the real-world background-sync cadence is unknown.
- **Push/notification delivery under Doze** at real-world timescales.
- **Performance** — the emulator is not a phone; the E2E performance budgets
  are only meaningful relative to other emulator runs.
- **Play Store signing and install flow** — release builds here are debug-key
  signed and sideloaded.
- **Hardware-backed keystore guarantees** for `flutter_secure_storage`; the
  emulator's keystore is software-backed.

#### Gotchas

- A **debug APK installed standalone** (`adb install app-debug.apk`) hangs on
  the launch screen — it waits for the Dart VM service. Use
  `./scripts/android_run.sh` (attached) for debug work, or `--release` for a
  build that runs on its own.
- `uiautomator dump` returns nothing useful for a Flutter app; drive the UI
  with screenshots (`adb exec-out screencap -p`) and `input tap` coordinates.
  Re-screenshot after every tap — the soft keyboard shifts the layout, and a
  tap aimed at a stale coordinate silently lands on the previous field. Moving
  between text fields with `input keyevent 61` (TAB) avoids the problem.
- `flutter test integration_test/...` **uninstalls the app afterwards**, so
  anything it registers with WorkManager does not persist.
- The system images have **no `curl`**, so check host reachability from the
  host side; `adb reverse` either works or the app reports a connection error.

### Known limitations

- **Release builds are signed with the debug key.** `android/app/build.gradle.kts`
  still points the release build type at `signingConfigs.debug`, which is fine
  for sideloading but must be replaced with a real keystore before any
  distribution. Do not commit the keystore.
- **No home-screen widget.** The watchOS complications have no Android
  counterpart yet; `watch_sync` no-ops safely on Android rather than failing.
- **Background sync is subject to OEM throttling.** WorkManager honors the
  15-minute cadence on stock Android, but Samsung, Xiaomi, OnePlus and others
  ship aggressive battery managers that suspend background work for apps the
  user has not exempted. Treat the sync interval as a ceiling, not a guarantee.
- **Launcher icon is legacy-only.** `flutter_launcher_icons` is configured
  without an adaptive-icon foreground/background, so Android renders the square
  icon inside the system mask.

### Android-specific implementation notes

- `MainActivity` extends `FlutterFragmentActivity`, not `FlutterActivity` —
  `local_auth` hosts its biometric prompt in a fragment and throws
  `no_fragment_activity` otherwise.
- Core library desugaring is enabled because `flutter_local_notifications`
  needs `java.time` below API 26.
- The root `build.gradle.kts` raises any subproject's Kotlin language/API
  version to 1.8. `sentry_flutter` 8.14.2 hardcodes 1.6, which the Kotlin 2.2
  compiler bundled with Flutter 3.41 refuses to compile.
- Backup and device-to-device transfer are disabled
  (`allowBackup="false"` plus `res/xml/data_extraction_rules.xml`) because
  credentials live in `EncryptedSharedPreferences` under device-bound keys that
  do not survive a restore.

## Apple Watch Complications

The app includes a watchOS companion with configurable watch face complications:

- **Token Price Complication** — Each slot independently configurable to show any token from the portfolio (e.g., "BTC $97K", "ADA $0.74"). Supports rectangular, circular, inline, and corner families.
- **Portfolio Total Complication** — Shows aggregate portfolio value with a 7-day sparkline.
- **15-minute refresh cadence** via WidgetKit timelines, plus immediate updates when the iOS app syncs.

See `ios/watchos_companion/README.md` for architecture details and Xcode integration steps.

## Notes
- Session auth is cookie-based; cookies are persisted on device.
- For stronger security in the future, consider per-user auth + Access JWTs instead of service tokens.
