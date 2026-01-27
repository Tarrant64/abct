# ABCT Changelog

All notable changes to ABCT (A Better Crypto Tracker) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.10.0] - 2026-01-26

### Added - Backup & Restore Feature (Major Feature)
- **Comprehensive Backup System**: Export and import all ABCT configurations
  - Export all user configurations to a single JSON file
  - Includes: wallets, API keys, security settings, custom tokens, NFT collections
  - Excludes: pricing data, portfolio snapshots (regenerable time-series data)
  - Encrypted backup file format with version tracking
  - Filename format: `abct-backup-YYYY-MM-DD-HHMMSS.json`

- **Export Options**:
  - Selectively include/exclude sensitive data (API keys, security settings)
  - Include/exclude custom tokens and NFT collection tracking
  - Security warnings displayed when sensitive data is included
  - One-click download of backup file
  - Real-time statistics showing what data will be backed up

- **Import with Validation**:
  - Comprehensive backup file validation before import
  - Version compatibility checking
  - Two import modes:
    - **Merge Mode**: Keep existing data and add/update from backup (safe)
    - **Replace Mode**: Delete all existing data first, then import (destructive)
  - Preview functionality (dry-run) shows exactly what will be imported
  - Skip options for API keys and security settings
  - Detailed warnings about data that will be overwritten

- **New API Endpoints** (`/api/backup/*`):
  - `POST /export` - Generate and download backup file
  - `POST /preview` - Preview import (validate and show summary)
  - `POST /import` - Import configuration from backup file
  - `GET /info` - Get backup statistics and current data status

- **Web UI** (`backup.html`):
  - Clean, modern interface with export and import sections
  - Real-time data statistics showing records per table
  - Drag-and-drop file upload for backup files
  - Checkbox options for export (include API keys, security, tokens, NFTs)
  - Radio button selection for import mode (merge vs replace)
  - Color-coded alerts for warnings and errors
  - Preview panel showing backup contents before import
  - Sensitive data clearly marked with lock icons
  - Progress indicators and status messages

- **Security Features**:
  - Prominent warnings when API keys are included in backups
  - Recommendations to store backups securely
  - Option to exclude API keys from export (add manually after import)
  - Security settings excluded by default on import
  - Clear indication of sensitive vs non-sensitive data
  - Admin authentication required for all backup operations

- **Data Coverage**:
  - **Included Tables**:
    - `wallets` - All wallet addresses and labels
    - `api_settings` - API keys and configuration
    - `security_settings` - SSL/HTTPS configuration
    - `custom_tokens` - Manually added custom tokens
    - `token_metadata` - Token metadata and tracking settings
    - `nft_scheduler_collections` - NFT collections being tracked
    - `api_rate_limits` - Custom API rate limits
  - **Excluded Tables** (regenerable):
    - `portfolio_snapshots` - Historical portfolio data
    - `nft_floor_prices` - NFT price history
    - `cache` - Temporary cached data
    - `balances`, `native_assets` - Refreshed from blockchain
    - `api_usage` - Usage logs
    - `nft_scheduler_state` - Runtime state
    - `nft_scheduler_api_calls` - API call logs

- **Use Cases**:
  - Migrate ABCT to a new server or computer
  - Recover from data loss or corruption
  - Test configuration changes safely (backup first)
  - Share wallet configuration across multiple ABCT instances
  - Regular backups as part of data protection strategy
  - Clone configuration for multiple users (without sharing API keys)

### Navigation
- Added "Backup & Restore" to waffle menu in dashboard (📦 icon)

### Documentation
- Added comprehensive inline help text and tooltips
- Clear warnings about sensitive data handling
- Mode selection with detailed descriptions
- Security best practices displayed in UI

---

## [0.9.0] - 2026-01-26

### Added - NFT Background Scheduler (Major Feature)
- **Integrated NFT Scheduler**: Consolidated standalone `nft-price-service` into main application
  - Single container deployment (eliminates need for separate NFT service container)
  - Optional background service controlled via environment variable or UI
  - Continuous NFT floor price collection spread across 24 hours
  - Respects TapTools API rate limits (95 calls/day with safety buffer)

- **Progress Tracking & State Persistence**:
  - All scheduler state saved to database for graceful restarts
  - Picks up exactly where it left off after server restart
  - Tracks last update time per collection
  - Logs API calls for daily rate limit tracking
  - Collections marked as "stale" after 1 hour without update

- **Priority System**:
  - Collections assigned priority levels (0-10)
  - Higher priority collections updated first
  - User-owned NFTs can be marked high priority
  - Oldest stale collections updated before fresh ones

- **Smart Scheduling**:
  - Runs every 15 minutes by default (configurable)
  - Updates 1 collection per cycle by default (96/day max)
  - Automatic rate limit management with daily reset
  - Sets `rate_limited_until` when limit reached

- **New API Endpoints** (`/api/nft-scheduler/*`):
  - `GET /status` - Detailed scheduler status and statistics
  - `POST /enable` - Enable and start the scheduler
  - `POST /disable` - Disable and stop the scheduler
  - `POST /trigger` - Manually trigger an update cycle
  - `POST /register` - Register a collection for tracking
  - `POST /register-batch` - Bulk register multiple collections
  - `GET /collections` - List all tracked collections

- **Web UI Integration** (`services.html`):
  - NFT Background Scheduler section with real-time status
  - Enable/Disable toggle button
  - Manual "Trigger Now" button (when enabled)
  - Live statistics: status, next run time, collections count
  - API call tracking: today's usage, remaining calls, daily limit
  - 24-hour progress bar showing update completion
  - Auto-refreshes every 3 seconds with page status

- **Database Tables** (3 new tables):
  - `nft_scheduler_state` - Scheduler status and statistics (single row)
  - `nft_scheduler_collections` - Collections being monitored with priority
  - `nft_scheduler_api_calls` - API call log for rate limit tracking

- **Configuration Variables**:
  - `NFT_SCHEDULER_ENABLED` - Enable/disable scheduler (default: false)
  - `NFT_UPDATE_INTERVAL_MINUTES` - Update frequency (default: 15)
  - `NFT_CALLS_PER_UPDATE` - Collections per cycle (default: 1)
  - `NFT_MAX_DAILY_CALLS` - Daily limit with safety buffer (default: 95)

### Changed
- **Deployment Architecture**: Single container now handles both main app and NFT scheduler
  - Simplified from 2-container to 1-container deployment
  - No more port conflicts (was ports 8000 + 8080, now just 8000)
  - Unified configuration and logging
  - Shared database and caching layer
  - Same security middleware applies to scheduler

### Dependencies
- **Added**: `apscheduler==3.10.4` - Background job scheduling

### Deprecated
- **Standalone nft-price-service**: The separate NFT price microservice is now deprecated
  - Integrated scheduler provides same functionality in main container
  - Migration guide provided in `NFT_SCHEDULER_INTEGRATION_COMPLETE.md`
  - Standalone service will be removed in v1.0.0
  - Existing users can continue using it or migrate to integrated scheduler

### Documentation
- Added comprehensive integration guide: `NFT_SCHEDULER_INTEGRATION_COMPLETE.md`
- Updated `.env.example` with scheduler configuration variables
- Updated architecture diagram to v0.9.0 (reflects single-container design)

---

## [0.8.5] - 2026-01-26

### Added
- **Rate Limiting**: Fully activated rate limiting middleware
  - Installed slowapi==0.1.9 library
  - Rate limiting now active with in-memory storage
  - Global limits: 1000/day, 100/hour per IP
  - Specific limits for sensitive endpoints:
    - Certificate uploads: 5/hour
    - Certificate generation: 10/hour
    - Settings updates: 20/hour
    - Wallet operations: 100/hour
  - Rate limit headers enabled in responses

### Verified
- **Pre-Push Security Hook**: Confirmed security hook is installed and active
  - Runs automated security audit before git push
  - Blocks push on CRITICAL/HIGH issues
  - Warns on MEDIUM/LOW issues
  - Located at `.git/hooks/pre-push`

### Infrastructure
- **Security Middleware Stack**: Complete security layer operational
  - Request size limiting: 10MB default, 5MB for uploads
  - Rate limiting: Per-IP with configurable limits
  - Ready for authentication layer (v0.9.0)

---

## [0.8.4] - 2026-01-26

### Added
- **Favicon Support**: Added application favicon and touch icons
  - Created favicon.ico from abct-logo.png
  - Added apple-touch-icon.png for iOS devices
  - Linked favicon on all 7 HTML pages
  - Eliminates 404 errors for favicon requests

### Fixed
- **wallets.html Syntax Error**: Fixed missing closing parenthesis in setSafeHTML call (line 1699)
  - Wallet management page now loads correctly
  - Displays all wallet data without errors
- **logs.html Syntax Error**: Fixed missing closing parenthesis in setSafeHTML call (line 629)
  - Logs page now renders log entries correctly
- **services.html Status Loading**: Fixed undeclared htmlContent variable
  - Added variable declaration before forEach loop
  - Added setSafeHTML call to render API status
  - Services page now displays all API statuses correctly
  - No more "Error loading status" console errors

### Changed
- **Semantic Versioning**: Implemented v0.8.4 (BUILD timestamp) format
  - Syncs with CHANGELOG version numbers
  - Build timestamps for development iteration tracking

### Infrastructure
- **Chrome DevTools MCP Integration**: Enabled automated browser testing
  - Direct console error detection
  - Real-time debugging capabilities
  - Network request monitoring
  - Automated testing workflow

---

## [0.8.3] - 2026-01-26

### Fixed
- **HTML Inline JavaScript Syntax Errors**: Fixed setSafeHTML() calls across all submenu pages
  - Fixed recursive setSafeHTML call in function definitions (6 files)
  - Fixed missing closing parentheses in 15+ setSafeHTML calls
  - Affected pages: wallets.html, apis.html, services.html, logs.html, security.html, nft-wall.html
  - Resolved "Uncaught SyntaxError: missing ) after argument list" errors
  - All page functionality now operational

---

## [0.8.2] - 2026-01-26

### Added
- **Version Display Footer**: Live version number at page bottom for troubleshooting
  - Timestamp-based versioning (e.g., v1769476120)
  - Instantly verify which code version is deployed
  - Helps diagnose cache issues during development

### Fixed
- **Critical Cache Bug**: Portfolio data not refreshing after balance updates
  - Root cause: Cache invalidation missing in refresh endpoint
  - Fix: Clear and repopulate cache after wallet refresh
  - Result: Page refreshes now show updated values immediately
- **Privacy Mode Blur**: Increased blur strength 2.5x for better privacy
  - Main values: 8px → 20px blur
  - Charts: 10px → 25px blur
  - History info: 4px → 10px blur
  - Numbers now truly unreadable in privacy mode
- **JavaScript Error**: Fixed null reference in event listener setup
  - Added null check for `addWalletForm` element
  - Prevents console errors on main dashboard page
- **XSS Protection Syntax Errors**: Fixed 106 setSafeHTML() calls
  - Restored from backup after corruption
  - All innerHTML sanitization now working correctly
  - Comprehensive fix applied to all HTML/JS files

### Changed
- **Cache Warming on Startup**: Portfolio cache pre-populated at server start
  - Eliminates "$0.00" display on first page load
  - Data available instantly when page opens
  - Background task completes within 1-2 seconds
- **Debug Logging**: Added console logging for troubleshooting
  - `[Prices] Loaded:` - Shows price data and count
  - `[Portfolio] Data loaded:` - Shows cache status and timestamp
  - Helps diagnose loading issues in development

### Infrastructure
- **Deployment Synchronization**: All directories now fully synced
  - Main: `/ABCT/`
  - Deployment: `/Deployment/`
  - Docker: Dockerfile updated with security audit system
- **Dependencies**: Added `python-multipart` for file upload support
  - Required for certificate upload in Security settings
  - FastAPI file handling now operational

---

## [0.8.1] - 2026-01-26

### Added
- **Automated Security Audit System**: Pre-push security validation
  - 9 automated security checks (authentication, XSS, CORS, input validation, etc.)
  - Git pre-push hook integration with severity-based blocking
  - CRITICAL/HIGH issues prompt user to fix before push
  - MEDIUM/LOW issues show warnings but allow push
  - Privacy-preserving commit messages (no vulnerability details exposed)
  - Manual audit mode with JSON/text reports
  - CI/CD integration support
  - Comprehensive documentation at `sec/README_SECURITY_AUDIT.md`
- **Security Audit Scripts**:
  - `sec/security_audit.py` - Core audit engine with 9 security checks
  - `sec/security_agent.py` - Interactive agent for pre-push workflow
  - `sec/pre-push-hook.sh` - Git pre-push hook
  - `sec/install_security_hook.sh` - One-click installer
  - `sec/SECURITY_AUDIT_QUICKREF.md` - Quick reference guide
- **Portfolio Cache Improvements**: Enhanced data persistence
  - Increased cache TTL from 5 minutes to 7 days (604,800 seconds)
  - Added "Last updated: X ago" timestamp display in dashboard
  - Native assets cache extended to 7 days
  - Prevents $0.00 display on first page load

### Changed
- **Portfolio Cache Strategy**: Extended cache duration for better UX
  - Portfolio data cached for 7 days instead of 5 minutes
  - Timestamp tracking with user-friendly display
  - Cached data persists across browser sessions

---

## [0.8.0] - 2026-01-26

### Added
- **Comprehensive Security Hardening**: Major security improvements based on OWASP, NIST, and CWE standards
- **Centralized Logging System**: New logging service with web UI
  - In-memory circular buffer (1000 entries) for recent logs
  - SQLite persistence for ERROR and WARNING levels
  - Real-time log streaming via Server-Sent Events (SSE)
  - Automatic sanitization of sensitive data (API keys, wallet addresses, file paths)
  - Log filtering by level and source component
  - Color-coded log entries in web UI at `/logs.html`
- **Enhanced Error Handling**: Protection against information disclosure
  - Generic error messages sent to clients
  - Full error details logged internally with sanitized tracebacks
  - Global exception handlers for consistent error responses
- **Input Validation Framework**: Enhanced validation for all user inputs
  - Request size limits (1MB for file uploads)
  - Wallet address format validation
  - API key format validation
  - Certificate validation before storage
- **CORS Security Hardening**: Microservice security improvements
  - NFT price service: Specific origin whitelist (replaces wildcard)
  - Credential-less CORS for enhanced security
  - Configurable via ALLOWED_ORIGINS environment variable
- **Network Security**: Improved binding configuration
  - Default localhost binding for microservices
  - Warning logs when binding to 0.0.0.0
  - Configurable via BIND_HOST environment variable
- **Security Documentation**:
  - `/SECURITY.md` - Complete security policy and best practices
  - `/sec/ROLLBACK.md` - Detailed rollback procedures for all changes
  - `/docs/MIGRATION_v0.8.md` - Step-by-step upgrade guide
  - `/sec/security_audit_report.md` - Comprehensive security audit findings

### Changed
- **Error Response Format**: All error responses now follow consistent safe format
  - Sensitive information removed from client-facing errors
  - Detailed errors logged server-side only
  - Stack traces sanitized to remove file paths and secrets
- **NFT Price Service CORS**: Restricted to specific origins (security fix)
  - Default: `http://localhost:8000,http://127.0.0.1:8000`
  - Breaking change for custom domains (must configure ALLOWED_ORIGINS)
- **Logging Architecture**: Replaced print statements with centralized logging
  - Consistent log format across all components
  - Log levels: ERROR, WARNING, INFO, DEBUG
  - Automatic log rotation and cleanup

### Security Fixes
- **CRIT-003**: Fixed information disclosure in error messages
  - Stack traces no longer exposed to clients
  - API keys redacted from logs
  - File paths sanitized in error responses
- **CRIT-002**: Fixed wildcard CORS with credentials (NFT microservice)
  - Prevents CSRF attacks via cross-origin requests
  - Restricts access to trusted origins only
- **HIGH-002**: Added request size limits on file uploads
  - Prevents DoS via large file uploads
  - 1MB limit for certificate uploads
  - Memory exhaustion protection
- **HIGH-003**: Fixed network binding exposure
  - Microservices default to localhost only
  - Network access requires explicit configuration
  - Security warnings for public binding
- **MED-004**: Implemented comprehensive audit logging
  - All security-sensitive operations logged
  - Tamper-evident log storage
  - 90-day retention for compliance

### Infrastructure
- New `logs` database table for persistent log storage
- New `/logs/*` API endpoints for log management
- New `/logs.html` frontend page for log viewing
- Global exception handlers in FastAPI application
- Logging service with async operations and sanitization
- Enhanced Docker configurations with security settings

### Documentation
- Security audit report with 24 findings addressed
- Complete rollback procedures for all changes
- Migration guide for v0.7.0 → v0.8.0 upgrade
- Security policy with authentication requirements and best practices
- Environment variable reference for security settings

---

## [0.7.0] - 2026-01-25

### Added
- **New CSS Themes**: Three new visual themes added to the theme selector
  - **Green Terminal**: Classic black background with green text, monospace font (no glow effects)
  - **Ocean Depths**: Deep blue oceanic palette with aqua/teal accents
  - **Sunset Horizon**: Warm orange/purple gradient theme with animated effects
- **API Utilization Tracker**: Monitor API usage and rate limits
  - New collapsible "API Utilization" section on the APIs page
  - Progress bars showing usage percentage with color coding (green/yellow/red)
  - Usage display showing calls made vs limit (e.g., "450 / 50,000")
  - "N/A" shown for APIs without documented daily limits
  - Custom limit setting for any API via modal
  - Auto-refresh every 60 seconds
  - Database tracking of API calls per period
- **Manual Tokens Tab**: Added to the Manage Assets page
  - Track tokens not held in connected wallets
  - Add tokens by ticker or policy ID
  - Edit quantity and labels
  - Separate "Manual Tokens" tab alongside "Wallets" tab
- **Portfolio Data Caching**: Dashboard now shows last cached values on load
  - Portfolio cache persists for 7 days (instead of 5 minutes)
  - "Last updated" timestamp shown below total portfolio value
  - User-friendly time display: "5 minutes ago", "2 hours ago", "3 days ago"
  - No more zeros on page load - cached data displays immediately

### Changed
- **Header Menu Optimization**: Reduced horizontal scrolling with waffle menu
  - New 3x3 grid waffle menu button containing: Manage Assets, APIs, Services, Security
  - Crypto/USD display toggle moved next to "Portfolio Summary" heading (compact style)
  - Header now shows: Privacy Mode, Expand All, Theme selector, Refresh Balances, Waffle Menu
- **Manage Assets Page**: Renamed from "Wallet Manager"
  - Added tabbed interface for Wallets and Manual Tokens
  - Separate header actions per tab
- **Removed Add Wallet/Token section** from main dashboard (now in Manage Assets)

### Security
- **PII Cleanup**: Removed personal identifiable information from repository
  - Replaced real wallet addresses in README examples with fake placeholders
  - Removed default Unraid IP (192.168.1.100) from all scripts
  - Changed sync scripts to use localhost defaults instead of private IPs
  - Sanitized cdp_api_key.json.template (removed PEM markers)

### Infrastructure
- New `api_usage` database table for tracking API call counts
- New `api_rate_limits` database table for custom rate limits
- New utilization endpoints: `GET/PUT/DELETE /settings/api-utilization/*`
- Waffle menu CSS and JavaScript components

---

## [0.6.0] - 2026-01-25

### Added
- **HTTPS/SSL Support**: Optional HTTPS encryption for Docker deployments
  - New nginx-ssl.conf configuration with TLS 1.2/1.3 support
  - Certificate mounting via Docker volume (`./certs:/app/certs:ro`)
  - HTTP to HTTPS redirect when SSL enabled
  - Environment variable `ABCT_SSL_ENABLED=true` to enable
  - Configurable HTTPS port via `ABCT_SSL_PORT` (default: 8443)
- **Security Settings Page**: New `/security.html` page for SSL configuration
  - View current SSL mode and certificate status
  - SSL mode selector (HTTP / HTTPS Self-Signed / HTTPS Custom)
  - Certificate management (generate self-signed, upload custom)
  - Certificate details display (expiry, issuer, SANs)
  - Restart required banner when mode changes
  - Browser warning guide for self-signed certificates
- **Security Router**: New `/security/*` API endpoints
  - `GET /security/settings` - Get current SSL configuration
  - `PUT /security/settings` - Update SSL mode
  - `POST /security/certificate/generate` - Generate self-signed certificate
  - `POST /security/certificate/upload` - Upload custom certificate
  - `GET /security/certificate/info` - Get certificate details
  - `DELETE /security/certificate` - Delete certificate and reset to HTTP
- **SSL Service**: New `ssl_service.py` for certificate management
  - RSA 2048-bit key generation with SHA-256 signatures
  - Subject Alternative Names (SAN) for localhost and 127.0.0.1
  - Certificate validation (expiry, key matching)
  - 365-day default validity for self-signed certs

### Changed
- **run.sh**: Background mode (`-b`) is now the default
  - Use `-f` or `--foreground` to see logs in real-time
  - Added `--https` flag for local HTTPS with auto-generated certificate
  - Added `--cert` and `--key` flags for custom certificates
  - Displays browser warning guidance when using self-signed certs
- Navigation header now includes "Security" link

### Infrastructure
- New `security_settings` database table for SSL configuration
- New `security.py` router with SSL management endpoints
- Docker: nginx-ssl.conf for HTTPS-enabled deployments
- Docker: Exposed port 443 in Dockerfile
- Docker: Certificate volume mount in docker-compose.yml
- Docker: entrypoint.sh handles SSL configuration at startup

---

## [0.5.0] - 2026-01-25

### Added
- **API Management Page**: New `/apis.html` page for managing API keys through the UI
  - Lists all supported APIs grouped by category (Cardano, EVM, Solana, Pricing)
  - Enable/disable APIs with stored keys in database
  - API keys stored in SQLite database, override environment variables
  - Shows FREE or PAID pricing tier for each API
  - Links to API documentation for obtaining keys
  - Status indicators showing configured vs unconfigured APIs
- **Settings Router**: New `/settings/apis` endpoints for API key management
  - `GET /settings/apis` - List all APIs with status
  - `GET /settings/apis/{id}` - Get specific API status
  - `PUT /settings/apis/{id}` - Enable API and save key
  - `DELETE /settings/apis/{id}` - Disable API and remove key
  - `GET /settings/apis/{id}/test` - Test API key validity
- **Wallet Manager Stake Key Grouping**: Cardano wallets grouped by stake key
  - Collapsible sections showing wallet count, total ADA, and token count per stake key
  - Expandable to show individual wallets within each stake group
  - Improved organization for users with multiple addresses under same stake key
- **Bitcoin xpub Support**: Extended public key support for Bitcoin wallets
  - Derives and tracks first 20 addresses from xpub
  - Aggregates balance across all derived addresses

### Fixed
- **Docker Build Failure**: Added `gcc` and `build-essential` to Dockerfile for `bip_utils` compilation
  - Fixed `ed25519-blake2b` wheel build error on fresh Docker builds

### Changed
- Error messages now link to API Management page instead of showing generic warnings
- Navigation links added between Dashboard, Manage Wallets, and Manage APIs pages

### Infrastructure
- New `api_settings` database table for storing API keys and enabled status
- New `settings.py` router with API registry containing metadata for all supported APIs
- Database functions: `get_api_setting()`, `save_api_setting()`, `delete_api_setting()`, `get_api_key()`
- `get_effective_api_key()` helper checks database first, falls back to environment variable

---

## [0.4.0] - 2026-01-25

### Added
- **NFT Image Caching**: Local caching system for NFT images
  - Separate SQLite database (`data/nft_images.db`) to keep binary data isolated
  - Automatic thumbnail generation (150x150 JPEG) for fast loading
  - IPFS gateway support with fallback URLs
  - Cardano CIP-25 metadata extraction via Blockfrost API for image URLs
  - Frontend toggle in NFT section to enable/disable caching (all chains)
  - API endpoints for image retrieval, caching, and management
  - Batch processing with concurrency control
  - Configuration via environment variables or API
- **NFT Wall Gallery**: Visual NFT browser at `/nft-wall.html`
  - Displays all NFTs with cached images in a grid layout
  - Chain tabs to filter by blockchain (Cardano, Ethereum, Solana, Polygon, Base)
  - "All Chains" consolidated view option
  - Click-to-expand modal for full-size images
  - Shows floor prices in native token and USD
  - Cache status tracking with progress indicators
  - "Cache Images" button to download NFT images in batches
  - Accessible via "NFT Wall" button in dashboard NFT section
- **Parallel Wallet Refresh**: Improved performance for wallet sync
  - Wallet balances now refresh in parallel (up to 5 concurrent)
  - Significantly faster sync for multi-wallet portfolios
- **Base Blockchain Support**: Full Base chain wallet and NFT tracking via Alchemy API
  - Native ETH balance tracking on Base
  - ERC-20 token tracking on Base
  - NFT support with intelligent spam filtering
  - Whitelist-based filtering for legitimate NFTs (book.io digital books)
  - Blacklist-based filtering for known scam patterns (airdrops, vouchers, etc.)
- **Polygon Blockchain Support**: Full Polygon chain wallet and NFT tracking via Alchemy API
  - Native POL balance tracking (formerly MATIC)
  - ERC-20 token tracking on Polygon
  - NFT support with spam filtering
- **Etherscan API Integration**: New service supporting multiple EVM chains
  - Transaction history fetching
  - Token transfer history
  - Gas price tracking
  - Works with Etherscan (Ethereum), Basescan (Base), and Polygonscan (Polygon)
- **Solana NFT Support**: NFT tracking for Solana via Helius API
  - Collection metadata and floor prices
  - Spam filtering for common Solana NFT scams
  - Links to Magic Eden marketplace
- **CoinMarketCap Pricing Integration**: Added CMC as fallback pricing source
  - Rich market data: price, 1h/24h change, market cap, 24h volume
  - Supports major coins with POL symbol for Polygon
- **Enhanced Pricing Fallback Chain**: Multiple redundant price sources
  - CoinGecko (primary) → CoinMarketCap → Coinbase → DefiLlama → TapTools
  - DefiLlama now supports all chains via `coingecko:` prefix
  - Coinbase public API as free fallback (no key required)
- **Architecture Documentation**: Added system architecture diagram
  - PDF and PNG formats in `docs/` folder
  - Shows Docker containers, services, routers, and external APIs

### Changed
- **Standardized Wallet File Format**: All wallets now use explicit `chain:address` format
  - Format: `cardano:addr1...`, `bitcoin:bc1...`, `ethereum:0x...`, `base:0x...`, `solana:...`
  - Same 0x address can be tracked on multiple EVM chains (Ethereum, Polygon, Base)
  - Removed auto-detection in favor of explicit chain specification
  - Updated documentation with format examples
- **Multi-Chain NFT Tabs**: Expanded NFT section to support multiple chains
  - Tabs for Cardano, Ethereum, Polygon, Base, and Solana NFTs
  - Chain-specific marketplace links (JPG Store, OpenSea, Magic Eden)
- **Polygon Rebrand**: Updated MATIC to POL throughout the application
  - Display now shows "POL" instead of "MATIC"
  - Updated CoinGecko ID from `matic-network` to `polygon-ecosystem-token`
  - Backend maintains MATIC key for API compatibility

### Fixed
- **MATIC Price $0 Bug**: Fixed Polygon price showing $0 due to CoinGecko ID change
- **TapTools Documentation**: Corrected pricing info (paid tier only, $9/mo+)

### Infrastructure
- New `NFTImageService` class for image caching with Pillow integration
- New `nft_image_database.py` module for image storage
- New `EtherscanService` class with multi-chain support
- New `BaseService` class for Base chain operations
- New `PolygonService` class for Polygon chain operations
- Enhanced Solana service with NFT support
- Enhanced `PricingService` with CMC, Coinbase, and DefiLlama fallbacks
- Database caching for all new chain services
- Parallel wallet refresh with asyncio semaphore for rate limiting

---

## [0.3.0] - 2026-01-25

### Added
- **Ethereum NFT Support**: Full Ethereum NFT tracking via Alchemy API
  - Fetch NFTs for all Ethereum wallets with metadata
  - Floor prices from OpenSea data embedded in Alchemy response
  - Persistent database caching (30-day TTL) to reduce API calls
  - NFT chain tabs to switch between Cardano and Ethereum NFTs
  - Links to OpenSea and Etherscan for each NFT
- **Solana Wallet Support**: Basic SOL balance tracking via Helius API
  - Auto-detection of Solana addresses (base58, 32-44 chars)
  - SOL balance display in portfolio summary
- **Privacy/Blur Mode Enhancement**: Improved blur behavior
  - Only blur numeric values, keeping labels (ADA, BTC, ETH, SOL) visible
  - Added helper functions: `blurValue()`, `formatUSDBlur()`, `formatCryptoBlur()`
  - Applied to all sections: wallets, exchanges, staking, DeFi, governance, NFTs
  - NFT collection names are blurred but total count remains visible
- **NFT Counts in Summary Cards**: Display NFT totals alongside wallet counts
  - Shows "X NFTs" for Cardano and Ethereum in blockchain summary cards
  - Real-time updates when NFT data loads
- **Portfolio History Improvements**:
  - `POST /portfolio/history/backfill` - Backfill historical snapshots with component values
  - Today's value now calculated in real-time when no snapshot exists
  - Chart includes current portfolio value for "today" even before daily snapshot
- **4-Hour Snapshot Updates**: More frequent portfolio snapshots
  - Changed from daily at 12PM CT to every 4 hours
  - Keeps one snapshot per day but updates it throughout the day

### Fixed
- **DRep Governance Display**: Fixed DRep name to show delegated representative name
  - Fetches metadata from IPFS when DRep has registered metadata
  - Displays human-readable name (e.g., "Chris Cata") instead of raw DRep ID
- **NFT Floor Price Loading**: Fixed database floor prices not displaying
  - `load_floor_prices_from_db()` now properly merges DB prices into existing cache
  - Added `_update_nft_collection_data()` to refresh embedded collection data in NFTs
  - Now correctly showing 89+ collections with prices (was showing only 3)
- **Portfolio Chart $0.00 Bug**: Fixed today showing $0.00 in history chart
  - Calculates current portfolio value when snapshot is missing or zero
  - Includes all components: wallets, staking, DeFi, exchanges, NFTs, tracked tokens
- **Ethereum NFT "API Not Configured" Error**: Added ALCHEMY_API_KEY to environment

### Changed
- Portfolio snapshots now update every 4 hours instead of once daily
- Historical chart values now include exchange, NFT, and tracked token components
- NFT section tabs for switching between Cardano and Ethereum NFT views

### Infrastructure
- Added `get_latest_snapshot_time()` database function for 4-hour snapshot logic
- Ethereum NFT service with persistent database caching pattern
- Helius API integration for Solana blockchain support

---

## [0.2.0] - 2026-01-24

### Added
- **Native Assets Consolidation**: Merged "Native Assets (Cardano)" and "Native Tokens" into single unified section
- **Real-time Toggle Updates**: Token toggles now update portfolio totals instantly without page reload
- **Custom Tokens Toggle**: Custom tokens now have include/exclude toggle for portfolio totals
- **Flow Lending (FLOW)**: Added support for FLOW token with liquid staking recognition
- **Midnight (NIGHT)**: Added pricing support for Midnight network token
- **Xerberus (XER)**: Added XER token to pricing service
- **Iagon (IAG) Staking**: Track staked IAG positions via transaction history analysis
- **TapTools Balance Verification**: New service to cross-check wallet balances against TapTools API
  - `GET /portfolio/verify/{address}` - Compare single wallet with TapTools data
  - `GET /portfolio/taptools/summary` - Full portfolio comparison grouped by stake key
  - Identifies discrepancies from DeFi positions, stake key aggregation, or missing UTXOs
- **Stake Key Discovery**: Auto-discover all addresses under a stake key
  - `GET /portfolio/stake/discover/{address}` - Find all addresses sharing the stake key
  - `POST /portfolio/stake/sync` - Add missing addresses to tracking
  - Shows tracked vs missing addresses with ADA balances
- **DeFi Analysis**: Deep analysis of locked ADA and DeFi positions
  - `GET /portfolio/defi/analysis/{address}` - Investigate DeFi-locked ADA
  - Detects staking positions across Indigo, Strike, Liqwid, Iagon
  - Compares local balance with TapTools including staking rewards

### Fixed
- **AGIX Token**: Corrected policy ID to SingularityNET contract with 8 decimals
- **Toggle Race Conditions**: Prevented concurrent toggle operations causing state reversion
- **Custom Tokens NoneType Error**: Fixed ticker lookup when ticker is None vs empty string
- **NIGHT Decimals**: Native NIGHT token now displays correctly with 6 decimals

### Changed
- Native tokens section moved to bottom half of page
- Collapsible sections for Native Assets and Custom Tokens
- Improved token display with section headers ("Tokens with Value" / "Other Tokens")

---

## [0.1.0] - 2026-01-23

### Added
- Initial release of ABCT Portfolio Tracker
- **Multi-chain Support**: Cardano, Bitcoin, Ethereum wallet tracking
- **Exchange Integration**: Coinbase portfolio sync via CDP API
- **DeFi Tracking**:
  - Indigo Protocol (INDY staking, iAssets)
  - Liqwid Finance (LQ staking)
  - Strike Finance (STRIKE staking)
  - Minswap, SundaeSwap, WingRiders LP tokens
- **Staking Rewards**: ADA delegation rewards tracking via CExplorer
- **NFT Support**: Cardano NFT tracking with floor prices via TapTools
- **Native Assets**: Track all Cardano native tokens with pricing
- **Custom Tokens**: Manually add tokens not auto-detected
- **Portfolio History**: 7-day value chart with daily snapshots
- **Price Service**: CoinGecko integration with TapTools/DefiLlama fallback

### Infrastructure
- FastAPI backend with async SQLite database
- Vanilla HTML/CSS/JS frontend (no build required)
- Local-first architecture - all data stays on your machine
- Cross-platform support (macOS, Linux, Windows WSL)

---

## Version History Summary

| Version | Date | Description |
|---------|------|-------------|
| 0.6.0 | 2026-01-25 | HTTPS/SSL support, Security Settings page, run.sh improvements |
| 0.5.0 | 2026-01-25 | API Management page, stake key wallet grouping, Bitcoin xpub support |
| 0.4.0 | 2026-01-25 | Base/Polygon support, CMC pricing, Etherscan API, POL rebrand, architecture docs |
| 0.3.0 | 2026-01-25 | Ethereum NFTs, Solana support, privacy mode improvements, chart fixes |
| 0.2.0 | 2026-01-24 | Native assets consolidation, real-time toggles, new tokens |
| 0.1.0 | 2026-01-23 | Initial release |

---

## Upgrade Notes

### Upgrading to 0.6.0
No database migrations required. The new `security_settings` table is created automatically on first run.

**New Features:**
- Navigate to `/security.html` or click "Security" from the dashboard to configure SSL
- For local development, continue using HTTP (no changes needed)
- For Docker deployments with HTTPS, see below

**Enabling HTTPS in Docker:**
Certificates are auto-generated on container startup if not provided:
```bash
# Just add one line to .env:
echo "ABCT_SSL_ENABLED=true" >> .env

# Restart container:
docker-compose down && docker-compose up -d

# Access at https://localhost:8443
```

**Using custom certificates (optional):**
```bash
mkdir -p certs
cp your-cert.crt certs/server.crt
cp your-key.key certs/server.key
# Then enable SSL and restart as above
```

**run.sh Changes:**
- Background mode is now the default (no `-b` flag needed)
- Use `-f` or `--foreground` to see logs in terminal
- Use `--https` to run with auto-generated self-signed certificate locally

**Breaking Changes:** None. Existing HTTP functionality preserved.

---

### Upgrading to 0.5.0
No database migrations required. The new `api_settings` table is created automatically on first run.

**New Features:**
- Navigate to `/apis.html` or click "Manage APIs" from the dashboard to configure API keys
- API keys saved through the UI are stored in the database and override environment variables
- Cardano wallets in the Wallet Manager are now grouped by stake key for easier organization

**Breaking Changes:** None. Existing functionality preserved. Environment variable API keys continue to work.

---

### Upgrading to 0.4.0
No database migrations required. New API keys enable additional features:

**Environment Variables** (add to `.env`):
```bash
# Etherscan API (optional - for transaction history on Ethereum/Base/Polygon)
ETHERSCAN_API_KEY=your_etherscan_api_key

# CoinMarketCap API (optional - fallback pricing source)
CMC_API_KEY=your_coinmarketcap_api_key
```

**Wallet File Format Change:**
Update your `data/wallets.txt` to use the new standardized format:
```
# Old format (auto-detect) - no longer recommended
addr1q82aa2gjsd...
0xcb11eede3d71...

# New format (explicit chain prefix) - required
cardano:addr1q82aa2gjsd...
ethereum:0xcb11eede3d71...
base:0xba40f354b775...
```

**Multi-Chain EVM Wallets:**
The same 0x address can now be tracked on multiple EVM chains by adding separate entries:
```
ethereum:0x0000000000000000000000000000000000000000
polygon:0x0000000000000000000000000000000000000000
base:0x0000000000000000000000000000000000000000
```

**After Upgrade:**
1. Update `data/wallets.txt` to use explicit chain prefixes
2. Restart the server: `./run.sh`
3. Refresh wallets to fetch data for new chains

**Breaking Changes:** Auto-detection of wallet chains is deprecated. Wallets should use explicit `chain:address` format.

---

### Upgrading to 0.3.0
No database migrations required. New API keys are needed for full functionality:

**Environment Variables** (add to `.env`):
```bash
# Ethereum NFTs (required for Ethereum NFT support)
ALCHEMY_API_KEY=your_alchemy_api_key

# Solana (required for Solana wallet support)
HELIUS_API_KEY=your_helius_api_key
```

**After Upgrade:**
1. Restart the server: `./run.sh`
2. Backfill historical chart data (optional but recommended):
   ```bash
   curl -X POST http://127.0.0.1:8000/portfolio/history/backfill
   ```
   This updates historical snapshots to include NFT, exchange, and tracked token values.

**Breaking Changes:** None. Existing functionality preserved.

---

### Upgrading to 0.2.0
No database migrations required. New features are automatically available after updating code and restarting the server.

```bash
./stop.sh
# Update code (git pull or copy files)
./run.sh
```

Token tracking preferences are preserved. New tokens (FLOW, NIGHT, XER) will appear in Native Assets section and can be toggled for portfolio inclusion.
