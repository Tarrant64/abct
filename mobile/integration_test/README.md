# ABCT Mobile — E2E Integration Tests

End-to-end tests that launch the full app in an iOS Simulator with a mock backend and exercise the complete user flow.

## Quick Start

```bash
# From the mobile/ directory:

# Run all E2E tests (auto-selects iOS simulator)
./scripts/run_e2e_tests.sh

# Run on a specific simulator
./scripts/run_e2e_tests.sh "iPhone 16 Pro"

# Run only functional tests
./scripts/run_e2e_tests.sh --functional

# Run only performance tests
./scripts/run_e2e_tests.sh --performance
```

Or use Flutter directly:

```bash
flutter test integration_test/app_test.dart -d "iPhone 16 Pro"
```

## Prerequisites

1. **Xcode** with iOS Simulator runtime installed
   - Verify: `xcode-select -p`
   - Install if missing: `xcode-select --install`
   - Add simulator runtimes: Xcode > Settings > Platforms

2. **Flutter SDK** on PATH
   - Verify: `flutter doctor`

3. **Dependencies resolved**
   - Run: `flutter pub get`

4. **Available iOS Simulator**
   - List available: `xcrun simctl list devices available`
   - The runner script auto-boots a simulator if none is running

## Architecture

```
integration_test/
  app_test.dart              # Main entry point — runs all suites
  README.md                  # This file
  helpers/
    mock_server.dart         # Local HTTP server simulating ABCT backend
    test_app.dart            # App launcher with mock profile injection
  suites/
    functional_test.dart     # Functional E2E tests
    performance_test.dart    # Performance budget tests

test_driver/
  integration_test.dart      # Driver for `flutter drive` (alternative runner)

scripts/
  run_e2e_tests.sh           # Shell runner with simulator management
```

## Mock Server

The tests use a local HTTP server (`MockServer`) that simulates all ABCT backend endpoints. The server:

- Starts on a random available port
- Returns realistic JSON responses for all API endpoints
- Validates session auth (login sets a cookie, subsequent requests check it)
- Accepts test credentials: `test` / `test123`
- No real servers or credentials are used

### Endpoints covered:

| Endpoint | Description |
|----------|-------------|
| `/api/auth/login` | Login with username/password |
| `/auth/logout` | Logout / clear session |
| `/api/mobile/status` | Server health check |
| `/api/mobile/portfolio/summary` | Portfolio overview |
| `/api/mobile/portfolio/instant` | Real-time portfolio value |
| `/api/mobile/chart/portfolio-history` | Historical chart data |
| `/api/mobile/wallets` | Wallet list with balances |
| `/api/mobile/exchanges/summary` | Exchange connections |
| `/api/mobile/defi/staking` | Staking positions |
| `/api/mobile/nfts/summary` | NFT summary |
| `/api/mobile/nfts/wall/nfts` | NFT grid data |
| `/portfolio/all-holdings` | All token holdings |
| `/api/mobile/chart/price/*` | Price charts |
| `/portfolio/asset-detail` | Asset market data |
| `/api/transactions` | Transaction history |

## Test Suites

### Functional Tests (`suites/functional_test.dart`)

| Test | What it verifies |
|------|------------------|
| App launches and shows login screen | AbctApp renders, login UI visible |
| Login screen shows form fields | Username and password TextFormFields exist |
| Successful login navigates to home | Test credentials reach home screen with bottom nav |
| Invalid credentials show error | Wrong creds keep user on login screen |
| Empty credentials trigger validation | Form validation messages appear |
| Bottom nav tabs switch content | All 6 tabs accessible, AppBar title updates |
| Dashboard shows portfolio data | Portfolio values/assets render from mock data |
| Assets tab loads holdings | Holdings/Wallets/Exchanges segments visible |
| Staking tab loads positions | Staking & DeFi sections render |
| Pull-to-refresh reloads data | Fling gesture triggers refresh without crash |

### Performance Tests (`suites/performance_test.dart`)

| Test | Budget | What it measures |
|------|--------|------------------|
| Cold start | 3000ms | Launch to login screen rendered |
| Login flow | 2000ms | Sign-in tap to home screen rendered |
| Tab navigation | 500ms per tab | Tap to content visible (each tab) |
| Data refresh | 2000ms | Pull-to-refresh to data re-rendered |
| Rapid tab switching | 10000ms | 3 cycles through all 6 tabs, no jank |
| Full flow timeline | n/a | Traced via `traceAction` for profiling |

Performance tests print detailed timing results:

```
============================================================
PERF [PASS] Cold Start
  Elapsed: 1250ms
  Budget:  3000ms
  Margin:  1750ms
============================================================
```

Tests **FAIL** if any budget is exceeded.

## Customizing Performance Budgets

Edit the `_Budget` class in `suites/performance_test.dart`:

```dart
class _Budget {
  static const int coldStartMs = 3000;    // Launch to login
  static const int loginFlowMs = 2000;    // Login to home
  static const int tabNavigationMs = 500; // Tab switch
  static const int dataRefreshMs = 2000;  // Pull-to-refresh
}
```

## Adding New Tests

1. Add test groups to the appropriate suite file under `suites/`
2. Use the helper functions:
   - `buildTestApp(server)` — creates the app with mock profile
   - `_loginAndReachHome(tester, server)` — logs in and navigates to home
   - `_suppressOverflowErrors()` — suppresses font-related overflow errors
3. The mock server can be extended by adding new routes in `helpers/mock_server.dart`

## Troubleshooting

### No iOS simulators found
```bash
# Install an iOS Simulator runtime via Xcode:
# Xcode > Settings > Platforms > + > iOS
# Or check available:
xcrun simctl list devices available
```

### Flutter secure storage errors
The tests run on the iOS Simulator, which supports Keychain. If you see keychain errors, ensure the simulator has been booted at least once.

### Test font overflow errors
Tests use the system font instead of SpaceGrotesk, which is wider. Overflow errors are automatically suppressed via `_suppressOverflowErrors()`. These are cosmetic only — they don't affect test validity.

### Tests hang on "waiting for connection"
Kill all simulator instances and retry:
```bash
xcrun simctl shutdown all
./scripts/run_e2e_tests.sh
```
