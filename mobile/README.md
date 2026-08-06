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
export ABCT_DEVICE_ID=<udid>              # or pass --device on each run
./scripts/build_device.sh                 # build HEAD, re-sign, install
./scripts/build_device.sh --allow-dirty   # explicit override for WIP builds
./scripts/build_device.sh --no-install    # build + re-sign only (no device needed)
./scripts/build_device.sh --device <udid> # target an explicit device
```

The target device UDID is **required** for installs (`xcrun devicectl list
devices` shows connected devices); the script exits with an error if neither
`ABCT_DEVICE_ID` nor `--device` is given.

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

## Apple Watch Complications

The app includes a watchOS companion with configurable watch face complications:

- **Token Price Complication** — Each slot independently configurable to show any token from the portfolio (e.g., "BTC $97K", "ADA $0.74"). Supports rectangular, circular, inline, and corner families.
- **Portfolio Total Complication** — Shows aggregate portfolio value with a 7-day sparkline.
- **15-minute refresh cadence** via WidgetKit timelines, plus immediate updates when the iOS app syncs.

See `ios/watchos_companion/README.md` for architecture details and Xcode integration steps.

## Notes
- Session auth is cookie-based; cookies are persisted on device.
- For stronger security in the future, consider per-user auth + Access JWTs instead of service tokens.
