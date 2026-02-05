# ABCT Mobile App - Xcode 26.3 AI Build Prompt

## Project Overview
Build a universal iOS/iPadOS/macOS/watchOS app that connects to the ABCT (A Better Crypto Tracker) self-hosted backend to display crypto portfolio data. This is a **read-only** portfolio tracker companion app for local network use.

---

## Technical Requirements

### Platform & Tools
- **Xcode Version**: 26.3
- **Language**: Swift 6.0
- **UI Framework**: SwiftUI
- **Minimum Deployment**:
  - iOS/iPadOS: 17.0+
  - macOS: 14.0+
  - watchOS: 10.0+
- **Architecture**: MVVM pattern with Combine for reactive updates

### Universal App Structure
- Single target with platform-specific views
- Shared ViewModels and networking layer
- Platform-adaptive UI components
- iCloud sync for server configuration (UserDefaults)

---

## Core Features

### 1. Server Configuration Screen (Pre-Login)

**Purpose**: Allow users to configure their ABCT server before logging in.

**UI Requirements**:
- Appears **before** login if no server is configured
- Form fields:
  - **Server Address**: TextField (placeholder: "192.168.1.100" or "abct.local")
  - **Port**: TextField with number pad (placeholder: "8081", default: "8081")
  - **Use HTTPS**: Toggle (default: OFF for local networks)
  - **Test Connection**: Button that hits `/api/mobile/status` endpoint
- Show server status badge:
  - Green "Connected" with checkmark if test succeeds
  - Red "Unable to Connect" with error icon if fails
  - Yellow "Testing..." while checking
- **Save** button (enabled only after successful test)
- **Advanced** disclosure group:
  - Request timeout (default: 30 seconds)
  - Custom API path (default: empty, uses standard paths)

**Data Model**:
```swift
struct ServerConfig: Codable {
    var host: String
    var port: Int
    var useHTTPS: Bool
    var timeout: TimeInterval
    var customPath: String?

    var baseURL: String {
        let scheme = useHTTPS ? "https" : "http"
        let path = customPath ?? ""
        return "\(scheme)://\(host):\(port)\(path)"
    }
}
```

**Storage**:
- Save to UserDefaults with key `"ABCTServerConfig"`
- Make editable from Settings screen later

---

### 2. Login Screen

**UI Requirements**:
- Clean, minimal design with ABCT branding
- Form fields:
  - **Username**: TextField with autocorrect disabled
  - **Password**: SecureField
  - **Remember Me**: Toggle (stores username only, not password)
- **Login** button (full-width, primary style)
- **Demo Mode** button (secondary style) - uses username: "demo", password: "demo"
- Show error alert for invalid credentials
- Loading spinner during authentication
- Server indicator at bottom: "Connected to: 192.168.1.100:8081" (small gray text)

**API Endpoint**: `POST /api/auth/login`
```json
// Request
{
    "username": "string",
    "password": "string"
}

// Response (Success)
{
    "message": "Login successful",
    "user_id": 1,
    "username": "admin",
    "is_demo": false,
    "session_token": "abc123..."
}

// Response (Error)
{
    "detail": "Invalid credentials"
}
```

**Session Management**:
- Store `session_token` securely in Keychain
- Include token in all subsequent API calls as cookie: `session=<token>`
- Auto-logout on 401 responses
- Logout endpoint: `POST /api/auth/logout`

---

### 3. Main Dashboard (Portfolio Summary)

**Layout** (Adaptive):
- **iOS/iPadOS**: TabView with tabs at bottom
- **macOS**: Sidebar navigation with content area
- **watchOS**: Simple list navigation

**Dashboard Content**:

#### Total Portfolio Card (Prominent)
- Large text: Total USD value (e.g., "$45,234.67")
- Percentage breakdown pie chart or ring chart
- 24h change indicator (up/down arrow with green/red color)
- Last updated timestamp
- Pull-to-refresh gesture

#### Portfolio Breakdown (4 Cards)
1. **Self-Custody Wallets**
   - Icon: 🔐
   - Value USD
   - Percentage of total
   - Tap → navigates to Wallets tab
2. **Exchange Balances**
   - Icon: 🏦
   - Value USD
   - Percentage of total
   - Tap → navigates to Exchanges tab
3. **NFT Holdings**
   - Icon: 🖼️
   - Value USD (floor price)
   - Percentage of total
   - Tap → navigates to NFTs tab
4. **Staking/DeFi**
   - Icon: 📈
   - Value USD
   - Percentage of total
   - Tap → navigates to Staking tab

#### Blockchain Breakdown (List)
- List of blockchains with holdings
- Each row shows:
  - Blockchain icon/logo
  - Blockchain name (Cardano, Bitcoin, Ethereum, etc.)
  - Native amount (e.g., "1,234.56 ADA")
  - USD value
  - Percentage bar graph
- Sorted by USD value descending

**API Endpoint**: `GET /api/mobile/portfolio/summary`
```json
{
    "total_value_usd": 45234.67,
    "total_native": {
        "ada": 12345.67,
        "btc": 0.5,
        "eth": 2.34
    },
    "breakdown": {
        "self_custody": {"value_usd": 30000, "percentage": 66.3},
        "exchanges": {"value_usd": 10000, "percentage": 22.1},
        "nfts": {"value_usd": 3000, "percentage": 6.6},
        "staking": {"value_usd": 2234.67, "percentage": 5.0}
    },
    "blockchains": [
        {
            "name": "cardano",
            "symbol": "ADA",
            "value_usd": 15000,
            "native_amount": 12345.67,
            "native_price_usd": 1.21,
            "wallet_count": 3,
            "percentage": 33.2
        }
    ],
    "last_updated": "2026-02-04T12:00:00Z",
    "from_cache": false
}
```

---

### 4. Wallets Tab

**UI Structure**:
- Filter buttons at top: "All" | "Cardano" | "Bitcoin" | "Ethereum" | "Solana" | "Polygon" | "Base"
- List of wallets grouped by blockchain (collapsible sections)
- Each wallet card shows:
  - Label (user-defined name) or truncated address
  - Blockchain badge/icon
  - Native balance (e.g., "123.45 ADA")
  - USD value
  - Token count badge (if > 0)
- Tap wallet → navigate to Wallet Detail screen
- Search bar to filter by label/address
- Pull-to-refresh

**API Endpoint**: `GET /api/mobile/wallets?blockchain={blockchain}&include_balances=true`
```json
{
    "total_wallets": 5,
    "wallets": [
        {
            "id": 1,
            "blockchain": "cardano",
            "address": "addr1q9...",
            "label": "Main Wallet",
            "balance": {
                "native": 1234.56,
                "native_symbol": "ADA",
                "usd_value": 1493.21,
                "last_updated": "2026-02-04T12:00:00Z"
            },
            "token_count": 5,
            "nft_count": 12
        }
    ],
    "total_value_usd": 45000,
    "last_updated": "2026-02-04T12:00:00Z"
}
```

---

### 5. Wallet Detail Screen

**UI Structure**:
- Header:
  - Wallet label (editable icon to change label - future feature)
  - Full address with copy button
  - Blockchain badge
- Native Balance Card:
  - Large text: Amount and symbol
  - USD value below
  - Current price per token
- Tokens List (if any):
  - Each token row:
    - Token logo (from logokit.com)
    - Symbol and name
    - Quantity
    - Price per token (native and USD)
    - Total value USD
  - Sorted by USD value descending
- Chart section (if supported):
  - Placeholder for future balance history chart

**API Endpoint**: `GET /api/mobile/wallets/{wallet_id}`
```json
{
    "id": 1,
    "blockchain": "cardano",
    "address": "addr1q9...",
    "label": "Main Wallet",
    "balance": {
        "native": 1234.56,
        "native_symbol": "ADA",
        "usd_value": 1493.21
    },
    "tokens": [
        {
            "symbol": "SUNDAE",
            "name": "SundaeSwap Token",
            "quantity": 10000,
            "price_native": 0.005,
            "price_usd": 0.00605,
            "value_usd": 60.50,
            "logo_url": "https://img.logokit.com/crypto/SUNDAE?size=32"
        }
    ],
    "nfts": [],
    "last_updated": "2026-02-04T12:00:00Z"
}
```

---

### 6. Exchanges Tab

**UI Structure**:
- List of configured exchanges
- Each exchange card:
  - Exchange logo and name
  - Status indicator:
    - Green "Connected" if configured
    - Gray "Not Configured" if no API keys
  - Total USD value
  - Asset count
  - Last sync timestamp
- Tap exchange → navigate to Exchange Detail screen
- Shows placeholder message if no exchanges configured: "No exchanges configured. Add API keys in the web dashboard."

**API Endpoint**: `GET /api/mobile/exchanges/summary`
```json
{
    "total_exchanges": 3,
    "total_value_usd": 15234.50,
    "exchanges": [
        {
            "name": "coinbase",
            "display_name": "Coinbase",
            "configured": true,
            "value_usd": 10000,
            "asset_count": 5,
            "logo_url": "https://www.coinbase.com/favicon.ico",
            "last_sync": "2026-02-04T12:00:00Z"
        }
    ],
    "last_updated": "2026-02-04T12:00:00Z"
}
```

---

### 7. Exchange Detail Screen

**UI Structure**:
- Header with exchange name and logo
- Total value card
- Assets list:
  - Each asset row:
    - Crypto logo
    - Symbol and name
    - Balance
    - USD value
    - Current price
  - Sorted by USD value descending

**API Endpoint**: `GET /api/mobile/exchanges/{exchange_name}`
```json
{
    "exchange": "coinbase",
    "display_name": "Coinbase",
    "configured": true,
    "total_usd": 10000,
    "asset_count": 5,
    "assets": [
        {
            "symbol": "BTC",
            "name": "Bitcoin",
            "balance": 0.25,
            "usd_value": 8500,
            "usd_price": 34000,
            "change_24h": 2.5,
            "logo_url": "https://img.logokit.com/crypto/BTC?size=32"
        }
    ],
    "last_sync": "2026-02-04T12:00:00Z",
    "from_cache": false
}
```

---

### 8. Staking/DeFi Tab

**UI Structure**:
- Summary card at top:
  - Total staked value USD
  - Total rewards earned USD
- Positions list:
  - Group by blockchain
  - Each position card:
    - Stake pool name/ticker (for Cardano) or protocol name
    - Staked amount and symbol
    - Staked USD value
    - Rewards earned
    - APY percentage
    - Active status badge

**API Endpoint**: `GET /api/mobile/defi/staking`
```json
{
    "total_staked_usd": 15000,
    "total_rewards_usd": 450.50,
    "positions": [
        {
            "blockchain": "cardano",
            "stake_key": "stake1u9...",
            "pool_id": "pool1abc...",
            "pool_name": "Example Pool",
            "pool_ticker": "POOL",
            "delegated_amount": 12345.67,
            "delegated_usd": 14950.50,
            "rewards_lifetime": 372.15,
            "rewards_usd": 450.50,
            "apy": 4.5,
            "active": true
        }
    ],
    "last_updated": "2026-02-04T12:00:00Z"
}
```

---

### 9. NFTs Tab

**UI Structure**:
- Filter by blockchain at top
- Collections list:
  - Each collection card:
    - Collection thumbnail/logo
    - Collection name
    - NFT count
    - Floor price (native + USD)
    - Total floor value USD
  - Grid layout on iPad/macOS
  - List layout on iPhone/watchOS

**API Endpoint**: `GET /api/mobile/nfts/summary?blockchain={blockchain}`
```json
{
    "total_nfts": 47,
    "total_collections": 3,
    "total_floor_value_usd": 2850,
    "collections": [
        {
            "name": "Clay Nation",
            "blockchain": "cardano",
            "nft_count": 15,
            "floor_price_native": 120,
            "floor_price_usd": 145.20,
            "total_floor_value_usd": 2178,
            "logo_url": "https://...",
            "policy_id": "40fa..."
        }
    ],
    "last_updated": "2026-02-04T12:00:00Z"
}
```

---

### 10. Charts (Future Enhancement)

**Portfolio History Chart**:
- Line chart showing portfolio value over time
- Time range selector: 7D | 1M | 3M | 1Y | ALL
- API: `GET /api/mobile/chart/portfolio-history?range={range}`

**Price Charts**:
- Candlestick/line charts for individual cryptocurrencies
- API: `GET /api/mobile/chart/price/{symbol}?range={range}`

---

### 11. watchOS Complications

**Glance View** (Main App):
- Total portfolio value (large text)
- 24h change (green/red with arrow)
- Last updated time

**Complications** (Watch Face):
- **Circular**: Portfolio value
- **Rectangular**: Portfolio value + change %
- **Corner**: Value with up/down arrow
- **Graphic Circular**: Ring chart showing breakdown

**Data Refresh**:
- Background updates every 15 minutes (when on wrist)
- Manual refresh with Digital Crown scroll

---

## Networking Layer

### API Client Structure

```swift
class ABCTAPIClient: ObservableObject {
    @Published var serverConfig: ServerConfig
    @Published var isAuthenticated: Bool = false

    private var sessionToken: String?

    func login(username: String, password: String) async throws -> LoginResponse
    func logout() async throws
    func fetchPortfolioSummary(refresh: Bool = false) async throws -> PortfolioSummary
    func fetchWallets(blockchain: String? = nil) async throws -> WalletsResponse
    func fetchWalletDetail(id: Int) async throws -> WalletDetail
    func fetchExchangesSummary() async throws -> ExchangesSummary
    func fetchExchangeDetail(name: String) async throws -> ExchangeDetail
    func fetchStaking() async throws -> StakingResponse
    func fetchNFTs(blockchain: String? = nil) async throws -> NFTResponse
    func testConnection() async -> Bool
}
```

### Authentication Flow

1. **Login**:
   - POST to `/api/auth/login` with credentials
   - Receive `session_token` in response
   - Store token in Keychain
   - Set authentication cookie for subsequent requests
2. **Authenticated Requests**:
   - Include cookie: `session={token}`
   - Handle 401 responses → auto-logout
3. **Logout**:
   - POST to `/api/auth/logout`
   - Clear session token from Keychain
   - Navigate back to login screen

### Error Handling

- Network errors: Show retry button with message
- 401 Unauthorized: Auto-logout and show login screen
- 404 Not Found: Show "No data available" placeholder
- 500 Server Error: Show "Server error" with support message
- Timeout: Show "Request timed out" with retry option

---

## Data Models

### Core Models (Swift Codable)

```swift
// Server Configuration
struct ServerConfig: Codable {
    var host: String
    var port: Int
    var useHTTPS: Bool
    var timeout: TimeInterval
    var customPath: String?
}

// Authentication
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

// Portfolio Summary
struct PortfolioSummary: Codable {
    let totalValueUsd: Double
    let totalNative: [String: Double]
    let breakdown: PortfolioBreakdown
    let blockchains: [BlockchainSummary]
    let lastUpdated: String
    let fromCache: Bool

    enum CodingKeys: String, CodingKey {
        case totalValueUsd = "total_value_usd"
        case totalNative = "total_native"
        case breakdown, blockchains
        case lastUpdated = "last_updated"
        case fromCache = "from_cache"
    }
}

struct PortfolioBreakdown: Codable {
    let selfCustody: PortfolioComponent
    let exchanges: PortfolioComponent
    let nfts: PortfolioComponent
    let staking: PortfolioComponent

    enum CodingKeys: String, CodingKey {
        case selfCustody = "self_custody"
        case exchanges, nfts, staking
    }
}

struct PortfolioComponent: Codable {
    let valueUsd: Double
    let percentage: Double

    enum CodingKeys: String, CodingKey {
        case valueUsd = "value_usd"
        case percentage
    }
}

struct BlockchainSummary: Codable, Identifiable {
    var id: String { name }
    let name: String
    let symbol: String
    let valueUsd: Double
    let nativeAmount: Double
    let nativePriceUsd: Double
    let walletCount: Int
    let percentage: Double

    enum CodingKeys: String, CodingKey {
        case name, symbol
        case valueUsd = "value_usd"
        case nativeAmount = "native_amount"
        case nativePriceUsd = "native_price_usd"
        case walletCount = "wallet_count"
        case percentage
    }
}

// Wallets
struct WalletsResponse: Codable {
    let totalWallets: Int
    let wallets: [Wallet]
    let totalValueUsd: Double
    let lastUpdated: String

    enum CodingKeys: String, CodingKey {
        case totalWallets = "total_wallets"
        case wallets
        case totalValueUsd = "total_value_usd"
        case lastUpdated = "last_updated"
    }
}

struct Wallet: Codable, Identifiable {
    let id: Int
    let blockchain: String
    let address: String
    let label: String?
    let balance: WalletBalance?
    let tokenCount: Int?
    let nftCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, blockchain, address, label, balance
        case tokenCount = "token_count"
        case nftCount = "nft_count"
    }
}

struct WalletBalance: Codable {
    let native: Double
    let nativeSymbol: String
    let usdValue: Double
    let lastUpdated: String

    enum CodingKeys: String, CodingKey {
        case native
        case nativeSymbol = "native_symbol"
        case usdValue = "usd_value"
        case lastUpdated = "last_updated"
    }
}

// ... Additional models for other endpoints
```

---

## UI Design Guidelines

### Color Scheme
- **Primary**: Blue (#007AFF for iOS, adaptive)
- **Success**: Green (#34C759)
- **Danger**: Red (#FF3B30)
- **Warning**: Orange (#FF9500)
- **Background**: System background (adaptive light/dark)
- **Secondary Background**: System secondary background

### Typography
- **Large Title**: Portfolio totals, main headings
- **Title**: Section headers
- **Headline**: Card titles
- **Body**: Main content
- **Caption**: Timestamps, secondary info
- **Footnote**: Smallest text

### Icons
- Use SF Symbols where applicable
- Custom blockchain logos loaded from URLs
- Fallback to emoji/initials for missing logos

### Animations
- Smooth transitions between screens
- Loading spinners during network requests
- Pull-to-refresh bounce animation
- Success/error toast messages (SwiftUI alerts)

---

## Settings Screen

**Access**: Gear icon in navigation bar

**Options**:
- **Server Configuration**:
  - Edit server address/port
  - Test connection button
  - Show server status
- **Account**:
  - Username (read-only)
  - Logout button
- **Display**:
  - Dark/Light mode toggle (or System)
  - Currency format (USD only for now)
- **Refresh**:
  - Auto-refresh interval (Off, 1min, 5min, 15min)
  - Clear cache button
- **About**:
  - App version
  - Build number
  - Link to ABCT GitHub
  - Privacy policy placeholder

---

## Platform-Specific Features

### iOS/iPadOS
- Tab bar navigation (bottom)
- iPad: Split view with sidebar for large screens
- Haptic feedback on interactions
- Share sheet for exporting data (future)
- Shortcuts support (future)

### macOS
- Sidebar navigation (left)
- Menu bar integration
- Keyboard shortcuts (Cmd+R for refresh, Cmd+Q for quit)
- Window resizing with adaptive layouts
- Touch Bar support (if applicable)

### watchOS
- Simple list navigation
- Digital Crown scrolling
- Force Touch menu (settings)
- Complications for watch face
- Background refresh every 15 minutes

---

## Security Considerations

1. **Session Token Storage**:
   - Use Keychain for secure storage
   - Never log tokens or passwords
   - Clear on logout
2. **Network Security**:
   - Support both HTTP (local network) and HTTPS
   - Certificate pinning optional (for HTTPS servers)
   - Warn user if using HTTP (local network disclaimer)
3. **Data Privacy**:
   - No data sent to third parties
   - All data stored locally or on user's server
   - No analytics or tracking
4. **Local Network Privacy** (iOS 14+):
   - Add `NSLocalNetworkUsageDescription` to Info.plist
   - Add `NSBonjourServices` for local network discovery

---

## Testing Requirements

### Unit Tests
- API client methods (mocked responses)
- Data model encoding/decoding
- Server configuration validation
- Number formatting helpers

### UI Tests
- Login flow (success and error)
- Navigation between tabs
- Pull-to-refresh actions
- Server configuration screen

### Integration Tests
- End-to-end login and data fetching
- Session persistence and logout
- Error handling and retry logic

---

## Build Instructions

1. **Create New Project**:
   - Multiplatform App template
   - SwiftUI interface
   - Swift language
   - Minimum deployments: iOS 17, macOS 14, watchOS 10
2. **Add Capabilities**:
   - Keychain Sharing (for session token)
   - Background Modes (watchOS only: Background App Refresh)
3. **Info.plist Additions**:
   - `NSLocalNetworkUsageDescription`: "ABCT needs local network access to connect to your self-hosted portfolio tracker."
   - `NSAppTransportSecurity` > `NSAllowsArbitraryLoads`: true (for HTTP support)
4. **Dependencies**:
   - No external packages required (use URLSession)
   - Optional: SwiftUICharts for chart visualizations

---

## Development Phases

### Phase 1: Core Foundation (MVP)
- ✅ Server configuration screen
- ✅ Login/logout flow
- ✅ Session management
- ✅ Portfolio summary dashboard
- ✅ Wallets list and detail
- ✅ Basic error handling

### Phase 2: Extended Features
- ✅ Exchanges tab and detail
- ✅ Staking/DeFi tab
- ✅ NFTs tab
- ✅ Pull-to-refresh
- ✅ Settings screen

### Phase 3: Platform Extensions
- ✅ watchOS app with complications
- ✅ macOS sidebar navigation
- ✅ iPad split view optimization

### Phase 4: Polish & Enhancements
- Charts integration
- Widgets (iOS 14+)
- App Shortcuts
- Export/share features
- Haptic feedback
- Animations and transitions

---

## API Endpoints Reference (Quick Reference)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/login` | POST | Authenticate user |
| `/api/auth/logout` | POST | End session |
| `/api/mobile/status` | GET | Health check (no auth) |
| `/api/mobile/portfolio/summary` | GET | Main dashboard data |
| `/api/mobile/wallets` | GET | List of wallets |
| `/api/mobile/wallets/{id}` | GET | Wallet details with tokens |
| `/api/mobile/exchanges/summary` | GET | All exchanges overview |
| `/api/mobile/exchanges/{name}` | GET | Specific exchange holdings |
| `/api/mobile/defi/staking` | GET | Staking positions |
| `/api/mobile/nfts/summary` | GET | NFT collections |
| `/api/mobile/chart/portfolio-history` | GET | Historical portfolio value |
| `/api/mobile/chart/price/{symbol}` | GET | OHLCV price data |

**Query Parameters**:
- `refresh=true`: Force cache bypass
- `blockchain={name}`: Filter by blockchain
- `range={period}`: Chart time range (7d, 30d, 1y, etc.)

**Authentication**:
- All endpoints except `/status` and `/login` require authentication
- Include session cookie: `session={token}`
- 401 response → auto-logout

---

## Example App Flow (User Journey)

1. **First Launch**:
   - User sees server configuration screen
   - Enters "192.168.1.100" and port "8081"
   - Taps "Test Connection" → green checkmark appears
   - Taps "Save" → navigates to login screen
2. **Login**:
   - User enters "admin" and "satoshi"
   - Taps "Login" → authenticates
   - Navigates to Dashboard tab
3. **Dashboard**:
   - Sees total portfolio value: "$45,234.67"
   - Views breakdown: 66% self-custody, 22% exchanges, etc.
   - Scrolls down to see blockchain breakdown
   - Pulls down to refresh data
4. **Wallets**:
   - Taps Wallets tab
   - Filters to "Cardano" only
   - Taps "Main Wallet" card
   - Views wallet detail with tokens
   - Copies address using copy button
5. **Settings**:
   - Taps gear icon
   - Changes auto-refresh to "5 minutes"
   - Taps "Logout"
   - Returns to login screen

---

## Additional Notes for AI

- **Use modern Swift concurrency**: async/await, not completion handlers
- **SwiftUI best practices**: @StateObject for ViewModels, @Published for reactive properties
- **Codable for JSON**: Snake_case to camelCase mapping with CodingKeys
- **Error handling**: Do-try-catch with user-friendly error messages
- **Accessibility**: VoiceOver labels, Dynamic Type support
- **Preview providers**: Include sample data for Xcode previews
- **Documentation**: Add inline comments for complex logic
- **Naming conventions**: Swift API Design Guidelines
- **Platform conditionals**: Use `#if os(iOS)`, `#if os(macOS)`, etc. for platform-specific code
- **Reusable components**: Extract common UI elements (cards, list rows) into separate views

---

## Success Criteria

The app is considered complete when:
- ✅ User can configure server, login, and view portfolio on all platforms
- ✅ All tabs display correct data from API
- ✅ Pull-to-refresh works on all list views
- ✅ Session persists across app launches
- ✅ Logout clears session and returns to login
- ✅ Error states show helpful messages
- ✅ watchOS app shows portfolio value in complications
- ✅ App handles network errors gracefully
- ✅ UI is responsive and polished on all platforms

---

## Go Build! 🚀

This prompt provides complete specifications for the ABCT mobile companion app. Use Xcode 26.3's AI programming features to generate the SwiftUI views, ViewModels, networking layer, and data models. Focus on clean architecture, proper error handling, and delightful user experience across all Apple platforms.
