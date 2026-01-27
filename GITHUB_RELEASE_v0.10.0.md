## 🎉 What's New in v0.10.0

### 🔄 Backup & Restore System
Export and import your entire ABCT configuration with one click!

- 📤 Export all settings, wallets, and data to JSON
- 📥 Import on any ABCT installation (migrate servers easily)
- 🔒 Security controls (choose what to include)
- 👁️ Preview before import (dry-run validation)
- 🔄 Two modes: Merge (safe) or Replace (full restore)

**Access:** Dashboard → ⋮⋮⋮ Menu → "Backup & Restore"

### ⏰ NFT Background Scheduler (v0.9.0)
**Single container deployment!** NFT price service now integrated.

- 🔄 Automatic 24/7 NFT floor price updates
- ⚖️ Smart rate limiting (95 calls/day)
- 💾 State persistence (resumes after restart)
- 🎚️ Control from Services page UI

**No more separate container needed!**

## 🐛 Bug Fixes

- ✅ Fixed NFT scheduler 404 errors in Docker
- ✅ Fixed wallet dropdown not expanding
- ✅ Fixed auth blocking localhost testing
- ✅ Real-time deployment progress (no more silent hangs)

## 🚀 Quick Start

### Docker Deployment
```bash
git clone https://github.com/Tarrant64/abct.git
cd abct
./abct-docker/update-unraid.sh <unraid-ip> <port>
```

### Local Development
```bash
git clone https://github.com/Tarrant64/abct.git
cd abct
cp .env.example .env
# Edit .env with your API keys
./run.sh
```

## 📦 What's Included

**Backup System:**
- Wallets, API keys, custom tokens, NFT collections
- Version compatibility checking
- Security warnings for sensitive data

**NFT Scheduler:**
- Continuous background updates
- Priority queue system
- Real-time statistics dashboard

## ⚠️ Migration from v0.8.x

If running standalone `nft-price-service`:
1. Stop old container: `docker stop nft-price-service`
2. Deploy new unified container
3. Enable scheduler in Settings or via `NFT_SCHEDULER_ENABLED=true`

Your data is preserved automatically.

## 📊 Stats
- **5,200+ lines** of new/modified code
- **4 new features**, **4 critical fixes**
- **Single container** deployment (down from 2)

## 🔗 Resources
- [Full Release Notes](RELEASE_NOTES_v0.10.0.md)
- [Backup & Restore Guide](docs/BACKUP_RESTORE_GUIDE.md)
- [Changelog](CHANGELOG.md)

---

**Version:** v0.10.0 (BUILD 1769498491)
