# ABCT Mobile App - Development Plan

## Overview

Create an iOS mobile app (iPhone + iPad) that presents the ABCT portfolio dashboard. The app will connect to a containerized ABCT backend service.

---

## Phase 1: Containerize ABCT Dashboard

**Goal:** Create a standalone Docker container of the current ABCT project that can be deployed to a server.

### Step 1.1: Create Docker Configuration

```
abct-docker/
├── Dockerfile
├── docker-compose.yml
├── nginx.conf              # Serve frontend + proxy API
├── .env.example
└── scripts/
    └── entrypoint.sh
```

**Components to containerize:**
- Backend (FastAPI + SQLite)
- Frontend (static HTML/CSS/JS)
- Nginx as reverse proxy

### Step 1.2: Environment Configuration

Required environment variables:
- `BLOCKFROST_API_KEY`
- `TAPTOOLS_API_KEY`
- `COINGECKO_API_KEY` (optional)
- `NFT_PRICE_SERVICE_URL` (optional, for external NFT service)

### Step 1.3: Data Persistence

- Mount volume for SQLite database (`/app/data`)
- Mount volume for API keys/config (`/app/config`)

### Step 1.4: API Endpoints for Mobile

Existing endpoints work, but consider adding:
- `GET /api/mobile/summary` - Optimized single-call dashboard data
- `GET /api/mobile/refresh` - Trigger full refresh
- WebSocket support for real-time updates (optional)

### Step 1.5: Testing

- Build and run container locally
- Verify all endpoints work
- Test from different network (simulate mobile access)

---

## Phase 2: iOS Mobile App

**Goal:** Create a native iOS app that displays the ABCT dashboard.

### Approach Options

| Option | Pros | Cons |
|--------|------|------|
| **A: WKWebView Wrapper** | Fast to build, reuses existing UI | Less "native" feel, limited offline |
| **B: SwiftUI Native** | Native performance, offline capable | More development time |
| **C: Hybrid (WebView + Native)** | Best of both, native navigation | Medium complexity |

**Recommended: Option C (Hybrid)**
- Use SwiftUI for app shell, navigation, settings
- Use WKWebView for dashboard display
- Native components for notifications, biometrics, widgets

### Step 2.1: Create Xcode Project

```bash
# Project structure
ABCT-Mobile/
├── ABCT.xcodeproj
├── ABCT/
│   ├── App/
│   │   ├── ABCTApp.swift           # App entry point
│   │   └── ContentView.swift        # Main view
│   ├── Views/
│   │   ├── DashboardView.swift      # WebView wrapper
│   │   ├── SettingsView.swift       # Server config
│   │   ├── LoadingView.swift
│   │   └── ErrorView.swift
│   ├── Services/
│   │   ├── APIClient.swift          # REST API calls
│   │   ├── WebViewCoordinator.swift # WKWebView handling
│   │   └── KeychainService.swift    # Secure storage
│   ├── Models/
│   │   ├── Portfolio.swift
│   │   ├── Wallet.swift
│   │   └── ServerConfig.swift
│   ├── Resources/
│   │   └── Assets.xcassets
│   └── Info.plist
├── ABCTTests/
└── ABCTUITests/
```

### Step 2.2: Core Features (MVP)

1. **Server Configuration**
   - First-launch setup to enter server URL
   - Store securely in Keychain
   - Test connection before saving

2. **Dashboard Display**
   - WKWebView loading the ABCT frontend
   - Pull-to-refresh functionality
   - Loading states and error handling

3. **Authentication (if needed)**
   - Face ID / Touch ID to unlock app
   - Optional PIN code fallback

4. **Offline Indicator**
   - Show last-updated timestamp
   - Clear indicator when offline

### Step 2.3: iPad Optimization

- Adaptive layout using SwiftUI
- Split view on iPad (sidebar + dashboard)
- Larger touch targets
- Keyboard shortcuts (Cmd+R to refresh)

### Step 2.4: App Configuration

**Info.plist settings:**
```xml
<!-- Allow HTTP for local development -->
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>

<!-- Face ID usage description -->
<key>NSFaceIDUsageDescription</key>
<string>Unlock ABCT to view your portfolio</string>
```

**Minimum Requirements:**
- iOS 16.0+
- iPadOS 16.0+
- Xcode 15+

### Step 2.5: Build & Test

1. Run on Simulator (iPhone + iPad)
2. Test on physical devices
3. Test with container running on:
   - localhost (Simulator only)
   - Local network (physical devices)
   - Remote server (production-like)

---

## Phase 3: Enhanced Features (Post-MVP)

### 3.1: Native Components

- **Widget** - Show total portfolio value on home screen
- **Notifications** - Price alerts, large changes
- **Watch App** - Quick glance at portfolio total

### 3.2: Improved Offline Support

- Cache last portfolio state
- Show cached data when offline
- Background refresh

### 3.3: Native Charts

- Replace web charts with Swift Charts
- Better performance and animations
- Native dark mode support

### 3.4: Biometric Security

- Require Face ID / Touch ID to open
- Hide sensitive values option
- Auto-lock timeout

---

## Implementation Checklist

### Phase 1: Docker Container
- [x] Create Dockerfile for backend
- [x] Create Dockerfile for frontend (nginx)
- [x] Create docker-compose.yml
- [x] Add nginx.conf for reverse proxy
- [x] Create entrypoint script
- [x] Add .env.example with all variables
- [ ] Test container locally
- [x] Document deployment steps
- [ ] Deploy to server (Unraid or other)

### Phase 2: iOS App (MVP)
- [ ] Create Xcode project (SwiftUI)
- [ ] Implement server configuration view
- [ ] Implement Keychain storage
- [ ] Create WKWebView wrapper
- [ ] Add pull-to-refresh
- [ ] Add loading/error states
- [ ] Implement Face ID unlock
- [ ] Add iPad layout support
- [ ] Test on Simulator
- [ ] Test on physical devices
- [ ] Create app icon
- [ ] Configure for App Store (if distributing)

### Phase 3: Enhancements
- [ ] Add home screen widget
- [ ] Implement notifications
- [ ] Add offline caching
- [ ] Native charts integration
- [ ] Watch app (optional)

---

## Technical Decisions

### WebView vs Native API Calls

**For MVP, use WebView because:**
1. Existing dashboard UI is already responsive
2. Faster development time
3. Changes to web UI automatically appear in app
4. Can progressively add native components

**Later, consider native for:**
1. Performance-critical views
2. Offline functionality
3. Native iOS features (widgets, shortcuts)

### Server Discovery

**Options:**
1. **Manual entry** - User types server URL (simplest)
2. **QR code scan** - Server displays QR with URL
3. **Bonjour/mDNS** - Auto-discover on local network

**Recommended:** Start with manual entry, add QR later.

### Security Considerations

1. Store server URL in Keychain (not UserDefaults)
2. Use HTTPS in production
3. Consider adding API key authentication
4. Face ID for app access (optional but recommended)

---

## File Structure Summary

```
ABCT/
├── backend/                 # Existing - unchanged
├── frontend/                # Existing - unchanged
├── Deployment/              # Existing
├── nft-price-service/       # Existing - NFT Docker service
│
├── abct-docker/             # NEW - Phase 1
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── README.md
│
└── abct-mobile/             # NEW - Phase 2
    ├── PLAN.md              # This file
    ├── ABCT-Mobile/         # Xcode project
    │   ├── ABCT.xcodeproj
    │   └── ABCT/
    └── README.md
```

---

## Next Steps

**Ready to proceed?** Here's the order:

1. **Phase 1.1-1.3:** Create Docker container for ABCT
2. **Phase 1.4:** Test container deployment
3. **Phase 2.1:** Create Xcode project structure
4. **Phase 2.2-2.3:** Implement MVP features
5. **Phase 2.5:** Test on devices

Say "proceed with Phase 1" to start containerizing ABCT, or "proceed with Phase 2" if you already have a server running.
