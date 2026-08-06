# watchOS Companion (watchOS 10+)

This folder contains a ready-to-integrate SwiftUI watch companion implementation for ABCT, including a full watch app and configurable WidgetKit complications.

## File Structure

### WatchApp/
- `PortfolioWatchApp.swift` — App entry point
- `PortfolioWatchView.swift` — Portfolio overview page (total value, sparkline, actions)
- `PortfolioTabView.swift` — Tab navigation (Overview, Assets, Favorites)
- `AssetListPage.swift` — All assets list view
- `FavoritesPage.swift` — Favorites management + detail views with charts
- `ChartDetailPage.swift` — Full-screen chart with Digital Crown scrubbing
- `PortfolioWatchModel.swift` — Data models (WatchAsset, PortfolioWatchData, formatters)
- `SparklineShape.swift` — Sparkline + fill shapes for charts
- `CachedAssetImage.swift` — Disk-cached async image loader with fallback badges
- `WatchHandoffController.swift` — WatchConnectivity delegate for phone-watch sync
- `SharedPortfolioSnapshotStore.swift` — Reads portfolio data from App Group UserDefaults

### WidgetExtension/
- `PortfolioComplicationWidget.swift` — All WidgetKit complications (two widgets in one bundle)
- `WidgetExtension.entitlements` — App Group entitlement
- `Info.plist` — Widget extension bundle info

## Complications

The widget extension provides **two complications** via a `WidgetBundle`:

### 1. Token Price (Configurable)
Each complication slot on the watch face can be independently configured to show a **specific token** from the portfolio. Uses `AppIntentConfiguration` with `SelectTokenIntent`.

- **Rectangular:** Symbol + price + 24h% change + mini sparkline
- **Circular:** Symbol + compact price colored by trend
- **Inline:** "BTC $97K ↗" compact text
- **Corner:** Symbol + price for corner slots

When adding a Token Price complication to a watch face, the user is prompted to choose which token (BTC, ETH, ADA, etc.) to display. Multiple Token Price complications can coexist on the same face, each showing a different token.

### 2. Portfolio Total (Static)
Shows the aggregate portfolio total value. No configuration needed.

- **Rectangular:** "Portfolio" header + total value + sparkline + 7d% change
- **Circular:** 7-day sparkline in a circular frame
- **Inline:** "ABCT $128K ↗" compact text
- **Corner:** "ABCT" + compact value

### Supported Complication Families
Both complications support all standard watchOS 10+ accessory families:
- `.accessoryRectangular`
- `.accessoryCircular`
- `.accessoryInline`
- `.accessoryCorner`

### Refresh Cadence
Complications refresh every **15 minutes** via WidgetKit's timeline policy. The iOS app also triggers `WidgetCenter.shared.reloadAllTimelines()` whenever new portfolio data arrives from the backend, so complications update immediately when the phone app is active.

## Data Flow

```
ABCT Backend API
       |
       v
Flutter App (Dart) — WatchSyncBridge pushes via MethodChannel
       |
       v
iOS Native Bridge (PortfolioWatchSyncBridge.swift)
       |
       +---> App Group UserDefaults (portfolio_snapshot_v1)
       |         |
       |         +---> WidgetKit Complications (reads snapshot)
       |         +---> Watch App (reads snapshot)
       |
       +---> WatchConnectivity (real-time push when reachable)
       |         |
       |         +---> Watch App (updates on receive)
       |
       +---> WidgetCenter.shared.reloadAllTimelines()
```

### Shared Data Key
- **App Group:** `group.com.teamcata.abct`
- **UserDefaults Key:** `portfolio_snapshot_v1`
- **Favorites Key:** `favoriteSymbols` (Set<String> encoded as JSON)

The snapshot contains:
- `totalValue`, `sevenDayChange`, `percentChange`, `historyPoints` (portfolio level)
- `assets[]` — each with `symbol`, `name`, `nativePriceUsd`, `priceChange24h`, `percentage`, `valueUsd`, `imageUrl`, `sparkline7d`, `sparkline24h`

## Xcode Project Integration (COMPLETED)

All targets are configured in `Runner.xcodeproj`. No manual Xcode setup needed.

### Targets

| Target | Type | SDK | Bundle ID |
|--------|------|-----|-----------|
| **Runner** | iOS App (Flutter) | iphoneos | `teamcata.com.ABCT-Mobile` |
| **ABCT-watchosapp Watch App** | watchOS App | watchos | `teamcata.com.ABCT-Mobile.watchkitapp` |
| **ABCT-widgetextExtension** | watchOS Widget Extension | watchos | `teamcata.com.ABCT-Mobile.watchkitapp.widgetext` |

### Build & Run

1. Open `ios/Runner.xcworkspace` in Xcode (not `.xcodeproj` -- the workspace includes CocoaPods).
2. Select the **Runner** scheme and your paired iPhone as the destination.
3. Pair an Apple Watch in the iOS Simulator (or use a real device with a paired watch).
4. Hit **Build & Run** (Cmd+R).

The Runner target has a "Build & Embed Watch App" build phase that automatically:
- Builds the watchOS app target with `-sdk watchos`
- Embeds it inside the iOS app bundle at `Runner.app/Watch/`
- The watch app target automatically builds and embeds the widget extension

### Simulator Testing

- To test complications in the watchOS Simulator, add a complication to the watch face:
  1. Long-press the watch face in the simulator
  2. Tap "Edit"
  3. Swipe to the complications page
  4. Tap a slot and scroll to find "Token Price" or "Portfolio Total"
- The widget uses **placeholder data** until the iOS app syncs a real snapshot via `WidgetCenter.shared.reloadAllTimelines()`

### Entitlements

All three targets share the `group.com.teamcata.abct` App Group:
- `Runner/Runner.entitlements` (iOS app)
- `watchos_companion/WatchApp/WatchApp.entitlements` (watch app)
- `watchos_companion/WidgetExtension/WidgetExtension.entitlements` (widget extension)

### Signing

- Development Team: set your own team ID (see "Code Signing (Team ID)" in the top-level mobile README)
- Code signing is set to **Automatic** on all targets
- Xcode will auto-provision App Group capabilities; you may need to log in to your Apple Developer account in Xcode > Settings > Accounts if not already configured

### Directory Layout

There are two sets of watch-related directories:

- **`watchos_companion/`** — Contains the real source code (WatchApp/ and WidgetExtension/)
- **`ABCT-watchosapp*/` and `ABCT-widgetext/`** — Xcode-generated scaffolds (placeholder code has been cleared; they provide Assets.xcassets and are used for Xcode's file system sync groups)

The real source files are referenced via explicit PBXBuildFile entries in the project, not via the file system sync groups.

## Security Notes
- No API keys or credentials are stored in the watch extension.
- All price data flows through the existing ABCT backend via the iOS app.
- The watch extension and complications only read from the shared App Group container.
- No network requests are made directly from the watch complication process.
