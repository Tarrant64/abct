# ABCT Mobile App - Phase 1: Minimal Viable App

## Goal
Build a simple iOS app that connects to ABCT server, logs in, and displays total portfolio value. **That's it.**

---

## Tech Stack
- **Platform**: iOS only (iPhone)
- **Xcode**: 26.3
- **Language**: Swift 6.0
- **UI**: SwiftUI
- **Minimum iOS**: 17.0
- **Architecture**: Simple MVVM (no complex patterns)

---

## What to Build (3 Screens Only)

### Screen 1: Server Setup

**Purpose**: Let user enter their ABCT server address

**UI Elements**:
```
┌─────────────────────────────┐
│                             │
│        ABCT Setup           │
│                             │
│  Server Address:            │
│  ┌─────────────────────┐   │
│  │ 192.168.1.100       │   │
│  └─────────────────────┘   │
│                             │
│  Port:                      │
│  ┌─────────────────────┐   │
│  │ 8081                │   │
│  └─────────────────────┘   │
│                             │
│  [ ] Use HTTPS              │
│                             │
│  ┌─────────────────────┐   │
│  │   Test Connection   │   │
│  └─────────────────────┘   │
│                             │
│  Status: Not tested         │
│                             │
│  ┌─────────────────────┐   │
│  │       Save          │   │
│  └─────────────────────┘   │
└─────────────────────────────┘
```

**Logic**:
1. "Test Connection" button calls `GET http://{host}:{port}/api/mobile/status`
2. If successful, show "✓ Connected" in green
3. If failed, show "✗ Connection failed" in red
4. "Save" button only enabled after successful test
5. Save to UserDefaults with key "serverConfig"
6. Navigate to login screen

**Code Structure**:
```swift
// Model
struct ServerConfig: Codable {
    var host: String = ""
    var port: Int = 8081
    var useHTTPS: Bool = false

    var baseURL: String {
        let scheme = useHTTPS ? "https" : "http"
        return "\(scheme)://\(host):\(port)"
    }
}

// ViewModel
class ServerSetupViewModel: ObservableObject {
    @Published var config = ServerConfig()
    @Published var connectionStatus: String = "Not tested"
    @Published var isConnected: Bool = false

    func testConnection() async {
        // Call /api/mobile/status
        // Update connectionStatus and isConnected
    }

    func save() {
        // Save to UserDefaults
    }
}

// View
struct ServerSetupView: View {
    @StateObject var viewModel = ServerSetupViewModel()

    var body: some View {
        // Form with fields above
    }
}
```

---

### Screen 2: Login

**Purpose**: Authenticate user

**UI Elements**:
```
┌─────────────────────────────┐
│                             │
│         ABCT Login          │
│                             │
│  Username:                  │
│  ┌─────────────────────┐   │
│  │ admin               │   │
│  └─────────────────────┘   │
│                             │
│  Password:                  │
│  ┌─────────────────────┐   │
│  │ ••••••••            │   │
│  └─────────────────────┘   │
│                             │
│  ┌─────────────────────┐   │
│  │       Login         │   │
│  └─────────────────────┘   │
│                             │
│  ┌─────────────────────┐   │
│  │    Demo Account     │   │
│  └─────────────────────┘   │
│                             │
│  Server: 192.168.1.100:8081 │
└─────────────────────────────┘
```

**API Call**:
```
POST {baseURL}/api/auth/login
Content-Type: application/json

{
    "username": "admin",
    "password": "satoshi"
}

Response (Success):
{
    "message": "Login successful",
    "user_id": 1,
    "username": "admin",
    "is_demo": false,
    "session_token": "abc123..."
}

Response (Error):
{
    "detail": "Invalid credentials"
}
```

**Logic**:
1. "Login" button sends POST request
2. If successful, save `session_token` to UserDefaults
3. Navigate to portfolio screen
4. If failed, show alert: "Login failed: Invalid credentials"
5. "Demo Account" button auto-fills "demo" / "demo" and submits

**Code Structure**:
```swift
// Model
struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct LoginResponse: Codable {
    let message: String
    let userId: Int
    let username: String
    let isDemo: Bool
    let sessionToken: String

    enum CodingKeys: String, CodingKey {
        case message
        case userId = "user_id"
        case username
        case isDemo = "is_demo"
        case sessionToken = "session_token"
    }
}

// ViewModel
class LoginViewModel: ObservableObject {
    @Published var username: String = ""
    @Published var password: String = ""
    @Published var errorMessage: String?
    @Published var isLoading: Bool = false
    @Published var isLoggedIn: Bool = false

    var serverConfig: ServerConfig // Passed from previous screen

    func login() async {
        // POST to /api/auth/login
        // Save session_token to UserDefaults
        // Set isLoggedIn = true
    }

    func loginAsDemo() async {
        username = "demo"
        password = "demo"
        await login()
    }
}

// View
struct LoginView: View {
    @StateObject var viewModel: LoginViewModel

    var body: some View {
        // Form with username/password fields
    }
}
```

---

### Screen 3: Portfolio Total

**Purpose**: Show total portfolio value

**UI Elements**:
```
┌─────────────────────────────┐
│                             │
│  Navigation Bar             │
│  Portfolio    [Refresh] [⚙️] │
│                             │
├─────────────────────────────┤
│                             │
│      Total Portfolio        │
│                             │
│      $45,234.67            │
│                             │
│      ▲ $1,234.50 (2.8%)    │
│      Last 24h              │
│                             │
│                             │
│  ───────────────────────    │
│                             │
│  Self-Custody: $30,000      │
│  Exchanges:    $10,000      │
│  NFTs:         $3,000       │
│  Staking:      $2,234       │
│                             │
└─────────────────────────────┘
```

**API Call**:
```
GET {baseURL}/api/mobile/portfolio/summary
Cookie: session={session_token}

Response:
{
    "total_value_usd": 45234.67,
    "breakdown": {
        "self_custody": {
            "value_usd": 30000,
            "percentage": 66.3
        },
        "exchanges": {
            "value_usd": 10000,
            "percentage": 22.1
        },
        "nfts": {
            "value_usd": 3000,
            "percentage": 6.6
        },
        "staking": {
            "value_usd": 2234.67,
            "percentage": 5.0
        }
    },
    "last_updated": "2026-02-04T12:00:00Z"
}
```

**Logic**:
1. Load on appear using session token
2. Display total value in large text
3. Show simple breakdown list
4. "Refresh" button reloads data
5. Settings button (⚙️) goes to settings (just logout for now)

**Code Structure**:
```swift
// Model
struct PortfolioSummary: Codable {
    let totalValueUsd: Double
    let breakdown: Breakdown
    let lastUpdated: String

    enum CodingKeys: String, CodingKey {
        case totalValueUsd = "total_value_usd"
        case breakdown
        case lastUpdated = "last_updated"
    }
}

struct Breakdown: Codable {
    let selfCustody: BreakdownItem
    let exchanges: BreakdownItem
    let nfts: BreakdownItem
    let staking: BreakdownItem

    enum CodingKeys: String, CodingKey {
        case selfCustody = "self_custody"
        case exchanges, nfts, staking
    }
}

struct BreakdownItem: Codable {
    let valueUsd: Double
    let percentage: Double

    enum CodingKeys: String, CodingKey {
        case valueUsd = "value_usd"
        case percentage
    }
}

// ViewModel
class PortfolioViewModel: ObservableObject {
    @Published var summary: PortfolioSummary?
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?

    var serverConfig: ServerConfig
    var sessionToken: String

    func loadPortfolio() async {
        // GET /api/mobile/portfolio/summary with session cookie
        // Parse response and update summary
    }

    func refresh() async {
        await loadPortfolio()
    }
}

// View
struct PortfolioView: View {
    @StateObject var viewModel: PortfolioViewModel

    var body: some View {
        NavigationView {
            VStack {
                if let summary = viewModel.summary {
                    // Display total value and breakdown
                } else if viewModel.isLoading {
                    ProgressView()
                } else if let error = viewModel.errorMessage {
                    Text(error)
                }
            }
            .navigationTitle("Portfolio")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Refresh") {
                        Task { await viewModel.refresh() }
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { /* Show settings */ }) {
                        Image(systemName: "gear")
                    }
                }
            }
        }
        .task {
            await viewModel.loadPortfolio()
        }
    }
}
```

---

## App Structure

```
ABCTApp/
├── ABCTApp.swift                 // Main app entry
├── Models/
│   ├── ServerConfig.swift
│   ├── LoginModels.swift
│   └── PortfolioModels.swift
├── ViewModels/
│   ├── ServerSetupViewModel.swift
│   ├── LoginViewModel.swift
│   └── PortfolioViewModel.swift
├── Views/
│   ├── ServerSetupView.swift
│   ├── LoginView.swift
│   └── PortfolioView.swift
└── Services/
    └── APIClient.swift           // Shared networking
```

---

## Shared API Client (Simple)

```swift
class APIClient {
    static let shared = APIClient()

    var baseURL: String = ""
    var sessionToken: String?

    func get<T: Codable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        if let token = sessionToken {
            request.setValue("session=\(token)", forHTTPHeaderField: "Cookie")
        }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }

        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }

    func post<T: Codable, R: Codable>(_ path: String, body: T) async throws -> R {
        guard let url = URL(string: baseURL + path) else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }

        let decoder = JSONDecoder()
        return try decoder.decode(R.self, from: data)
    }
}
```

---

## Main App Entry Point

```swift
@main
struct ABCTApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            if !appState.hasServerConfig {
                ServerSetupView()
            } else if !appState.isLoggedIn {
                LoginView(serverConfig: appState.serverConfig)
            } else {
                PortfolioView(
                    serverConfig: appState.serverConfig,
                    sessionToken: appState.sessionToken
                )
            }
        }
    }
}

class AppState: ObservableObject {
    @Published var hasServerConfig: Bool = false
    @Published var isLoggedIn: Bool = false
    @Published var serverConfig: ServerConfig = ServerConfig()
    @Published var sessionToken: String = ""

    init() {
        // Load from UserDefaults
        if let data = UserDefaults.standard.data(forKey: "serverConfig"),
           let config = try? JSONDecoder().decode(ServerConfig.self, from: data) {
            self.serverConfig = config
            self.hasServerConfig = true
        }

        if let token = UserDefaults.standard.string(forKey: "sessionToken") {
            self.sessionToken = token
            self.isLoggedIn = true
        }
    }
}
```

---

## Info.plist Requirements

Add these keys to allow HTTP connections (for local network):

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

---

## Build Instructions

1. Create new iOS App project in Xcode 26.3
2. Select SwiftUI for interface
3. Minimum deployment: iOS 17.0
4. Copy the code structures above into appropriate files
5. Add Info.plist entries
6. Build and run on simulator

---

## Testing Steps

1. **Launch app** → should show Server Setup screen
2. **Enter server** (e.g., "192.168.50.225" and "8081")
3. **Tap Test Connection** → should show "✓ Connected"
4. **Tap Save** → navigates to Login
5. **Enter credentials** (admin/satoshi or demo/demo)
6. **Tap Login** → navigates to Portfolio
7. **See total value** displayed from API
8. **Tap Refresh** → reloads data

---

## Success Criteria for Phase 1

✅ App launches without crashes
✅ Can configure server address
✅ Can test connection to ABCT backend
✅ Can login with credentials
✅ Can see total portfolio value
✅ Session persists across app restarts
✅ Refresh button reloads data

---

## What We're NOT Building in Phase 1

❌ Wallets list
❌ Exchange details
❌ Charts
❌ NFT collections
❌ Staking info
❌ watchOS app
❌ macOS app
❌ Settings screen (except logout)
❌ Pull to refresh
❌ Complex error handling

**Keep it simple. Just get the basics working first.**

---

## Next Phases (After Phase 1 Works)

- **Phase 2**: Add Wallets tab (list only, no detail)
- **Phase 3**: Add wallet detail screen with tokens
- **Phase 4**: Add other tabs (exchanges, staking, NFTs)
- **Phase 5**: Polish UI and add charts
- **Phase 6**: watchOS app

---

## Common Pitfalls to Avoid

1. **Don't overcomplicate ViewModels** - just basic @Published properties
2. **Don't add navigation complexity** - simple if/else in App entry
3. **Don't worry about perfect error messages** - just show basic alerts
4. **Don't add animations yet** - focus on functionality
5. **Don't try to make it pretty** - use default SwiftUI styling

---

## Prompt for Xcode AI (Copy This)

```
Build a simple iOS app with 3 screens:

1. Server Setup screen with host/port text fields and "Test Connection" button
   - Test by calling GET http://{host}:{port}/api/mobile/status
   - Save to UserDefaults when successful

2. Login screen with username/password fields
   - POST to /api/auth/login with JSON body
   - Save session_token from response to UserDefaults
   - Demo button auto-fills "demo"/"demo"

3. Portfolio screen showing total value
   - GET /api/mobile/portfolio/summary with session cookie
   - Display total_value_usd in large text
   - Show breakdown list (self-custody, exchanges, nfts, staking)
   - Refresh button to reload data
   - Settings button for logout

Use SwiftUI, MVVM pattern, iOS 17+.
Keep it simple - no complex navigation, no fancy UI, just working functionality.
Store server config and session token in UserDefaults.
Use URLSession for networking with async/await.
```

---

**This is the absolute minimum to get a working app. Build this first, then iterate!**
