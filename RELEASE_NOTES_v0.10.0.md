# ABCT v0.10.0 - Backup & Restore Release

**Release Date:** January 27, 2026
**Build:** 1769498491

---

## 🎉 What's New

### 🔄 Backup & Restore System (v0.10.0)

Take complete control of your ABCT configuration with the new **Backup & Restore** feature!

**Key Features:**
- 📤 **Export Configuration** - Download all your settings, wallets, and custom data as a single JSON file
- 📥 **Import Configuration** - Restore from backup on any ABCT installation
- 🔒 **Security Controls** - Choose what to include (API keys, security settings, etc.)
- 👁️ **Preview Before Import** - Dry-run validation shows exactly what will be imported
- 🔄 **Two Import Modes:**
  - **Merge** (Safe) - Adds/updates data while keeping existing entries
  - **Replace** (Full Restore) - Wipes all data and restores from backup
- 📋 **Version Compatibility** - Automatic format validation and version checking

**What Gets Backed Up:**
- ✅ All wallet addresses and labels
- ✅ API keys and configuration (optional)
- ✅ Security settings (SSL/HTTPS config)
- ✅ Custom tokens and metadata
- ✅ NFT collections being tracked
- ❌ Pricing data (excluded - regenerated from APIs)
- ❌ Portfolio snapshots (excluded - too large)

**Access:** Dashboard → ⋮⋮⋮ Menu → "Backup & Restore" or navigate to `/backup.html`

---

### ⏰ NFT Background Scheduler Integration (v0.9.0)

**Single Container Deployment!** The NFT price service is now integrated into the main ABCT application.

**Before:** Required 2 separate Docker containers
**After:** Single unified container with optional NFT scheduler

**Features:**
- 🔄 **Continuous Updates** - Automatic NFT floor price collection 24/7
- ⚖️ **Smart Rate Limiting** - Spreads 95 API calls across 24 hours (TapTools limit)
- 💾 **State Persistence** - Picks up exactly where it left off after restarts
- 🎚️ **UI Controls** - Enable/disable from Services page
- 📊 **Real-time Statistics** - View update progress, API usage, collection status
- 🎯 **Priority Queue** - Updates high-priority collections first

**Configuration:**
```bash
# Enable in .env or Docker environment variables
NFT_SCHEDULER_ENABLED=true
NFT_UPDATE_INTERVAL_MINUTES=15  # Update every 15 minutes
NFT_CALLS_PER_UPDATE=1          # Collections per cycle
NFT_MAX_DAILY_CALLS=95          # Safety limit
```

**Access:** Dashboard → Services → "NFT Background Scheduler"

---

## 🐛 Bug Fixes

### Critical Fixes
- **NFT Scheduler API 404 Errors** - Fixed router prefix mismatch in Docker nginx proxy
- **Wallet Dropdown Not Working** - Fixed DOMPurify stripping click handlers on Cardano stake groups
- **Authentication Blocking Localhost** - Added `ABCT_REQUIRE_AUTH=false` option for local development

### UX Improvements
- **Real-time Build Progress** - Update script now shows live Docker build output (no more 33-second silent hang)
- **Version Display** - Deployment script shows deployed version after completion
- **Rate Limit Adjustments** - Increased status endpoint limits to prevent 429 errors on auto-refresh

---

## 🚀 Deployment

### Docker (Single Container)
```bash
# Clone repository
git clone https://github.com/Tarrant64/abct.git
cd abct

# Deploy to Unraid/Docker
./abct-docker/update-unraid.sh <unraid-ip> <port>

# Example:
./abct-docker/update-unraid.sh 192.168.1.100 8081
```

### Local Development
```bash
# Clone and setup
git clone https://github.com/Tarrant64/abct.git
cd abct

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run
./run.sh
# Access at http://127.0.0.1:8000
```

---

## 📋 Configuration

### New Environment Variables (v0.10.0)

```bash
# Authentication Control
ABCT_REQUIRE_AUTH=false  # Set to false for localhost-only development
                         # Set to true (or omit) for production with auth

# Admin Credentials (required if ABCT_REQUIRE_AUTH is true)
ABCT_ADMIN_USER=admin
ABCT_ADMIN_PASSWORD=your_secure_password_here
```

### NFT Scheduler Variables (v0.9.0)

```bash
# Enable/disable NFT background scheduler
NFT_SCHEDULER_ENABLED=false  # Set to true to enable

# Scheduler configuration
NFT_UPDATE_INTERVAL_MINUTES=15  # How often to check for updates
NFT_CALLS_PER_UPDATE=1          # Collections to update per cycle
NFT_MAX_DAILY_CALLS=95          # Daily API call safety limit
```

---

## 🔧 Breaking Changes

### Migration from v0.8.x

**NFT Price Service Users:**
If you were running the standalone `nft-price-service` container:

1. **Stop the old container:**
   ```bash
   docker stop nft-price-service
   docker rm nft-price-service
   ```

2. **Deploy unified ABCT container** (includes NFT scheduler)

3. **Enable NFT scheduler** via environment variable or Services page UI

4. **Collections are preserved** - Existing NFT collections in your database will be automatically picked up by the integrated scheduler

**No data loss** - Your portfolio, wallets, and NFT data remain intact.

---

## 📊 Statistics

**Lines of Code Changed:**
- v0.9.0: ~2,600+ lines (NFT scheduler integration)
- v0.10.0: ~2,600+ lines (Backup & Restore feature)
- **Total:** 5,200+ lines of new/modified code

**Files Added:**
- `backend/routers/backup.py` - Backup API endpoints
- `backend/services/nft_scheduler.py` - NFT scheduler service
- `backend/routers/nft_scheduler.py` - NFT scheduler API
- `frontend/backup.html` - Backup & Restore UI
- `docs/BACKUP_RESTORE_GUIDE.md` - User documentation

**Files Modified:**
- All frontend HTML files (version bump)
- `backend/main.py` - NFT scheduler lifecycle integration
- `backend/middleware/auth.py` - Optional auth support
- `abct-docker/update-unraid.sh` - Real-time output, version reporting

---

## 🙏 Acknowledgments

This release represents a major milestone in ABCT's evolution:
- **Single-container architecture** simplifies deployment
- **Backup & Restore** enables easy migration and disaster recovery
- **Production-ready features** for self-hosted portfolio tracking

Special thanks to the community for feedback and testing!

---

## 🔗 Links

- **Repository:** https://github.com/Tarrant64/abct
- **Documentation:** See `/docs` directory
- **Issues:** https://github.com/Tarrant64/abct/issues
- **Changelog:** See `CHANGELOG.md` for detailed version history

---

## 📝 Full Changelog

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

**Previous Release:** v0.8.4
**Current Release:** v0.10.0

---

**Note:** This is a self-hosted application designed for localhost use. The optional authentication feature (`ABCT_REQUIRE_AUTH`) allows running without credentials on trusted localhost installations, or with Basic Auth for network-exposed deployments.
