# Migration Guide: v0.7.0 → v0.8.0

**ABCT Security Hardening Release**

This guide helps you upgrade from ABCT v0.7.0 to v0.8.0, which introduces comprehensive security enhancements including SSL/HTTPS support, authentication framework, input validation, and security monitoring.

---

## Table of Contents

1. [Overview](#overview)
2. [Before You Begin](#before-you-begin)
3. [Breaking Changes](#breaking-changes)
4. [Migration Steps](#migration-steps)
5. [New Features](#new-features)
6. [Configuration Changes](#configuration-changes)
7. [Testing Checklist](#testing-checklist)
8. [Troubleshooting](#troubleshooting)
9. [Rollback Procedure](#rollback-procedure)

---

## Overview

### What's New in v0.8.0

**Major Security Enhancements:**
- SSL/HTTPS support with certificate management
- Security Settings UI at `/security.html`
- Enhanced error handling (no sensitive data leakage)
- Input validation framework
- Request size limits
- Audit logging capabilities
- XSS protection improvements
- CORS hardening for microservices

**Deployment Impact:**
- **Local-only deployments:** Minimal impact, optional HTTPS
- **Network deployments:** HTTPS strongly recommended, authentication required

### Version Compatibility

| Version | Release Date | Support Status | Upgrade Path |
|---------|--------------|----------------|--------------|
| 0.7.0 | 2026-01-25 | Supported | Upgrade to 0.8.0 |
| 0.8.0 | 2026-01-26 | Current | N/A |

### Estimated Migration Time

- **Simple (local-only):** 10 minutes
- **Standard (with HTTPS):** 30 minutes
- **Advanced (with custom cert):** 1 hour

---

## Before You Begin

### Prerequisites

1. **Backup Your Data**
   ```bash
   # Backup database
   cp data/portfolio.db data/portfolio.db.backup_$(date +%Y%m%d)

   # Backup environment file
   cp .env .env.backup

   # Backup entire data directory
   tar czf abct_data_backup_$(date +%Y%m%d).tar.gz data/
   ```

2. **Document Current Configuration**
   ```bash
   # Save current version
   curl http://127.0.0.1:8000/api/status > version_before.json

   # List current wallets
   curl http://127.0.0.1:8000/wallets > wallets_before.json

   # Check current environment
   cat .env | grep -v "API_KEY" > config_before.txt
   ```

3. **Check System Requirements**
   - Python 3.9+ (no change)
   - Disk space: Additional 50MB for certificates and logs
   - Memory: Same as v0.7.0
   - New dependencies: `cryptography` (auto-installed)

4. **Review Security Audit**
   Read `/Users/chriscata/Documents/Claude-Projects/ABCT/sec/security_audit_report.md` to understand changes.

### Compatibility Check

**Compatible:**
- All existing wallets and data
- All API keys and settings
- Custom tokens and labels
- Portfolio history

**Incompatible:**
- None (fully backward compatible)

---

## Breaking Changes

### None

v0.8.0 is **fully backward compatible** with v0.7.0. All existing functionality is preserved.

**Optional Changes:**
- HTTPS mode (opt-in)
- Authentication (planned for v0.9.0)
- Enhanced validation (transparent)

---

## Migration Steps

### Step 1: Stop Current Server

```bash
# Standard installation
./stop.sh

# Docker installation
docker-compose down

# Verify stopped
ps aux | grep uvicorn  # Should return nothing
lsof -i :8000          # Should return nothing
```

### Step 2: Update Code

#### Option A: Git Pull (Recommended)

```bash
# Fetch latest changes
git fetch origin

# View changes
git log v0.7.0..v0.8.0 --oneline

# Upgrade to v0.8.0
git checkout v0.8.0
```

#### Option B: Fresh Clone

```bash
# Clone new version
cd ..
git clone -b v0.8.0 <repo-url> ABCT-v0.8.0
cd ABCT-v0.8.0

# Copy data from old installation
cp -r ../ABCT/data ./
cp ../ABCT/.env ./
```

#### Option C: Docker Image

```bash
# Pull new image
docker pull your-registry/abct:0.8.0

# Update docker-compose.yml
sed -i 's/abct:0.7.0/abct:0.8.0/' docker-compose.yml
```

### Step 3: Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Update dependencies
pip install -r requirements.txt

# Verify cryptography installed
python -c "from cryptography import x509; print('OK')"
```

**New Dependencies:**
- `cryptography>=41.0.0` - For SSL certificate generation and validation

### Step 4: Database Migration

**Automatic Migration:**
v0.8.0 automatically creates new tables on first run.

**Manual Verification:**
```bash
# Check for new tables
sqlite3 data/portfolio.db "SELECT name FROM sqlite_master WHERE type='table' AND name='security_settings';"

# Should return: security_settings
```

**New Tables:**
- `security_settings` - SSL/HTTPS configuration

### Step 5: Update Environment Variables

**Review New Variables:**

Edit `.env` file:
```bash
# Existing variables (no changes)
BLOCKFROST_API_KEY=mainnet_...
CEXPLORER_API_KEY=...
TAPTOOLS_API_KEY=...

# === NEW in v0.8.0 (Optional) ===

# SSL/HTTPS Configuration (optional for local-only)
ABCT_SSL_MODE=http  # Options: http | https-self-signed | https-custom

# Paths to certificate files (if using https-custom mode)
# ABCT_SSL_CERT=/path/to/cert.pem
# ABCT_SSL_KEY=/path/to/key.pem

# Authentication (planned for v0.9.0)
# ABCT_ADMIN_USER=admin
# ABCT_ADMIN_PASSWORD=your_secure_password

# Encryption key for API keys at rest (optional, auto-generated if missing)
# ABCT_ENCRYPTION_KEY=base64_encoded_key
```

**Docker-Specific (.env in project root):**
```bash
# Existing
ABCT_PORT=8080

# NEW: HTTPS support
ABCT_SSL_ENABLED=false  # Set to true to enable HTTPS
ABCT_SSL_PORT=8443      # External HTTPS port
```

### Step 6: Start Server

```bash
# Standard installation (HTTP)
./run.sh

# Standard installation (HTTPS with self-signed cert)
./run.sh --https

# Docker
docker-compose up -d

# Check logs
tail -f logs/abct.log  # Standard
docker-compose logs -f abct  # Docker
```

### Step 7: Verify Upgrade

```bash
# Check version
curl http://127.0.0.1:8000/api/status | jq '.version'

# Check health
curl http://127.0.0.1:8000/health

# Test existing functionality
curl http://127.0.0.1:8000/wallets
curl http://127.0.0.1:8000/portfolio/summary

# Access new security page
open http://127.0.0.1:8000/security.html
```

**Expected Results:**
- Version shows 1.0.0 or higher
- All existing endpoints work
- Security page loads successfully
- No error messages in logs

---

## New Features

### 1. SSL/HTTPS Support

**Accessing the Security Settings Page:**
```
http://127.0.0.1:8000/security.html
```

**Three HTTPS Modes:**

#### Mode 1: HTTP Only (Default)
- No encryption
- Suitable for localhost-only access
- No configuration needed
- Current mode: Check "Current Mode" in Security Settings

#### Mode 2: HTTPS with Self-Signed Certificate
- Auto-generated certificate
- Suitable for local HTTPS testing
- Browser will show security warning (expected)

**How to Enable:**
```bash
# Method 1: Via UI
# 1. Navigate to /security.html
# 2. Click "Generate Self-Signed Certificate"
# 3. Select "HTTPS Self-Signed" mode
# 4. Click "Apply Changes"
# 5. Restart server: ./stop.sh && ./run.sh

# Method 2: Via CLI
./run.sh --https
```

**Bypass Browser Warning:**
1. Chrome/Edge: Click "Advanced" → "Proceed to localhost (unsafe)"
2. Firefox: Click "Advanced" → "Accept the Risk and Continue"
3. Safari: Click "Show Details" → "visit this website"

#### Mode 3: HTTPS with Custom Certificate
- Use your own certificate (Let's Encrypt, commercial CA)
- No browser warnings
- Suitable for production deployments

**How to Enable:**
```bash
# Method 1: Upload via UI
# 1. Navigate to /security.html
# 2. Upload certificate file (.crt, .pem)
# 3. Upload private key file (.key, .pem)
# 4. Select "HTTPS Custom" mode
# 5. Restart server

# Method 2: Via CLI
mkdir -p certs/
cp your-cert.crt certs/server.crt
cp your-key.key certs/server.key
chmod 600 certs/server.key
./run.sh --cert certs/server.crt --key certs/server.key
```

**Let's Encrypt Example:**
```bash
# Generate certificate
sudo certbot certonly --standalone -d abct.yourdomain.com

# Copy to ABCT
sudo cp /etc/letsencrypt/live/abct.yourdomain.com/fullchain.pem certs/server.crt
sudo cp /etc/letsencrypt/live/abct.yourdomain.com/privkey.pem certs/server.key
sudo chown $USER:$USER certs/*
chmod 600 certs/server.key

# Enable in ABCT
# Upload via /security.html or run with --cert/--key flags
```

### 2. Enhanced Error Handling

**What Changed:**
- Error responses no longer expose internal details
- Stack traces logged server-side only
- Generic error messages to clients
- Sensitive data redacted from logs

**Example:**

**Before (v0.7.0):**
```json
{
  "detail": "Failed to add wallet: APIError: Invalid API key 'mainnet_ABC123...' for Blockfrost"
}
```

**After (v0.8.0):**
```json
{
  "detail": "Failed to add wallet. Check server logs for details."
}
```

**Server Log:**
```
2026-01-26 10:15:23 - ERROR - Wallet addition failed: APIError: Invalid API key 'mainnet_***REDACTED***'
```

### 3. Input Validation

**Automatic Validation:**
- Wallet addresses checked for valid format
- API keys validated before storage
- File uploads limited to 1MB
- Certificate files validated before use

**User Impact:**
- Better error messages for invalid inputs
- Prevents accidental configuration mistakes
- Protects against malformed data

### 4. Security Monitoring

**Audit Logging (If Enabled):**
- Certificate changes logged
- SSL mode changes logged
- API key modifications logged
- Wallet additions/deletions logged

**Log Location:** `data/audit.log`

**Example Log Entry:**
```
2026-01-26 10:15:23 | INFO | CERT_UPLOAD | user=admin | cert_type=custom | expires=2027-01-26
```

---

## Configuration Changes

### SSL Configuration (New)

**Database Table:**
```sql
CREATE TABLE security_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Stored Settings:**
- `ssl_mode`: Current mode (http, https-self-signed, https-custom)
- `cert_path`: Path to certificate file
- `key_path`: Path to private key file
- `cert_type`: Certificate type (self-signed, custom)
- `cert_expires_at`: Certificate expiry date
- `pending_mode`: Pending mode change (requires restart)

**Accessing via API:**
```bash
# Get current settings
curl http://127.0.0.1:8000/security/settings

# Update SSL mode (requires restart)
curl -X PUT http://127.0.0.1:8000/security/settings \
  -H "Content-Type: application/json" \
  -d '{"ssl_mode": "https-self-signed"}'

# Generate certificate
curl -X POST http://127.0.0.1:8000/security/certificate/generate \
  -H "Content-Type: application/json" \
  -d '{"hostname": "localhost", "valid_days": 365}'
```

### CORS Configuration (Microservice)

**Changed in nft-price-service:**

**Before (v0.7.0):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Wildcard
    allow_credentials=True,
)
```

**After (v0.8.0):**
```python
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Specific origins only
    allow_credentials=False,
)
```

**Migration:** No action needed unless accessing microservice from custom domain.

**Custom Domain Setup:**
```bash
# Add to microservice .env
ALLOWED_ORIGINS=http://localhost:8000,https://abct.yourdomain.com
```

---

## Testing Checklist

### Basic Functionality

- [ ] Server starts successfully
- [ ] Dashboard loads at http://127.0.0.1:8000
- [ ] All existing wallets display correctly
- [ ] Portfolio summary shows correct totals
- [ ] NFTs load properly
- [ ] Price data updates
- [ ] Exchange balances sync (if configured)

### New Security Features

- [ ] Security page loads at /security.html
- [ ] Current SSL mode displays correctly
- [ ] Can generate self-signed certificate
- [ ] HTTPS mode works (if enabled)
- [ ] Certificate upload works (if applicable)
- [ ] Certificate details display correctly

### API Endpoints

```bash
# Test all critical endpoints
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/wallets
curl http://127.0.0.1:8000/portfolio/summary
curl http://127.0.0.1:8000/prices
curl http://127.0.0.1:8000/security/settings
```

### Data Integrity

```bash
# Verify database integrity
sqlite3 data/portfolio.db "PRAGMA integrity_check;"
# Should return: ok

# Count wallets (should match pre-upgrade)
sqlite3 data/portfolio.db "SELECT COUNT(*) FROM wallets;"

# Verify portfolio snapshots
sqlite3 data/portfolio.db "SELECT COUNT(*) FROM portfolio_snapshots;"
```

### Performance

- [ ] Dashboard loads in < 2 seconds
- [ ] API responses in < 500ms
- [ ] No memory leaks (check after 1 hour: `ps aux | grep uvicorn`)
- [ ] Database size reasonable (< 100MB for typical usage)

---

## Troubleshooting

### Issue: Server Won't Start

**Symptoms:**
- `./run.sh` exits immediately
- Port 8000 already in use
- Import errors

**Solutions:**

1. **Check if old process is running:**
   ```bash
   lsof -i :8000
   # Kill old process
   lsof -ti:8000 | xargs kill -9
   ```

2. **Check for Python errors:**
   ```bash
   ./run.sh -f  # Run in foreground to see errors
   ```

3. **Verify dependencies:**
   ```bash
   pip install -r requirements.txt
   python -c "from cryptography import x509; print('OK')"
   ```

4. **Check file permissions:**
   ```bash
   chmod +x run.sh
   chmod 600 certs/*.key  # If using HTTPS
   ```

### Issue: HTTPS Certificate Errors

**Symptoms:**
- Browser shows SSL error
- Certificate validation failed
- Server won't start with HTTPS

**Solutions:**

1. **Regenerate certificate:**
   ```bash
   rm -f certs/server.*
   ./run.sh --https  # Auto-generates new cert
   ```

2. **Check certificate expiry:**
   ```bash
   openssl x509 -in certs/server.crt -noout -enddate
   ```

3. **Verify key matches certificate:**
   ```bash
   openssl x509 -noout -modulus -in certs/server.crt | openssl md5
   openssl rsa -noout -modulus -in certs/server.key | openssl md5
   # Hashes should match
   ```

4. **Fall back to HTTP:**
   ```bash
   # Via UI: /security.html → Select "HTTP" mode → Restart
   # Via CLI:
   sqlite3 data/portfolio.db "UPDATE security_settings SET ssl_mode='http' WHERE key='ssl_mode';"
   ./run.sh
   ```

### Issue: Security Page Returns 404

**Symptoms:**
- /security.html not found
- 404 error in browser

**Solutions:**

1. **Verify file exists:**
   ```bash
   ls -l frontend/security.html
   ```

2. **Check if router registered:**
   ```bash
   grep "security.router" backend/main.py
   # Should see: app.include_router(security.router)
   ```

3. **Restart server:**
   ```bash
   ./stop.sh && ./run.sh
   ```

### Issue: Database Migration Failed

**Symptoms:**
- `security_settings` table not found
- SQL errors in logs

**Solutions:**

1. **Manually create table:**
   ```bash
   sqlite3 data/portfolio.db <<EOF
   CREATE TABLE IF NOT EXISTS security_settings (
       key TEXT PRIMARY KEY,
       value TEXT,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   EOF
   ```

2. **Restore from backup and retry:**
   ```bash
   cp data/portfolio.db.backup data/portfolio.db
   ./run.sh
   ```

### Issue: Import Errors (cryptography)

**Symptoms:**
- `ModuleNotFoundError: No module named 'cryptography'`
- Server won't start

**Solutions:**

1. **Install cryptography:**
   ```bash
   source venv/bin/activate
   pip install 'cryptography>=41.0.0'
   ```

2. **macOS-specific (if compilation fails):**
   ```bash
   brew install openssl
   LDFLAGS="-L$(brew --prefix openssl)/lib" \
   CPPFLAGS="-I$(brew --prefix openssl)/include" \
   pip install cryptography
   ```

3. **Linux-specific:**
   ```bash
   sudo apt-get install build-essential libssl-dev libffi-dev python3-dev
   pip install cryptography
   ```

### Issue: Docker Container Won't Start

**Symptoms:**
- Container exits immediately
- Health check failing

**Solutions:**

1. **Check logs:**
   ```bash
   docker-compose logs abct
   ```

2. **Verify environment variables:**
   ```bash
   docker-compose config | grep -A 5 environment
   ```

3. **Rebuild image:**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

4. **Check volume mounts:**
   ```bash
   docker-compose down
   docker volume ls
   docker volume rm abct_abct-data  # WARNING: Deletes data
   docker-compose up -d
   ```

---

## Rollback Procedure

If you encounter critical issues, rollback to v0.7.0:

### Quick Rollback

```bash
# 1. Stop server
./stop.sh

# 2. Revert code
git checkout v0.7.0

# 3. Restore database (if needed)
cp data/portfolio.db.backup data/portfolio.db

# 4. Start server
./run.sh

# 5. Verify
curl http://127.0.0.1:8000/health
```

### Complete Rollback Guide

See `/Users/chriscata/Documents/Claude-Projects/ABCT/sec/ROLLBACK.md` for detailed instructions.

---

## Post-Migration Tasks

### 1. Review Security Settings

```bash
# Check current configuration
curl http://127.0.0.1:8000/security/settings

# Review logs
tail -50 logs/abct.log
```

### 2. Enable HTTPS (Recommended for Network Access)

If accessing ABCT from other devices:
```bash
# Generate self-signed cert
./run.sh --https

# OR upload custom certificate via /security.html
```

### 3. Plan for Authentication (v0.9.0)

Authentication is planned for the next release. Prepare by:
- Choosing strong admin password
- Documenting user access requirements
- Planning credential storage strategy

### 4. Update Documentation

- Document custom SSL certificates in use
- Update deployment procedures
- Note any configuration changes

### 5. Schedule Regular Security Reviews

- Monthly: Review audit logs
- Quarterly: Rotate API keys
- Annually: Update certificates

---

## Support

### Getting Help

**Resources:**
- Documentation: `/docs/` directory
- Security Guide: `/SECURITY.md`
- Rollback Guide: `/sec/ROLLBACK.md`
- Issue Tracker: GitHub Issues (if public repo)

**Before Requesting Help:**
1. Check logs: `tail -100 logs/abct.log`
2. Review troubleshooting section above
3. Test with rollback to confirm v0.8.0 issue
4. Gather system info: Python version, OS, Docker version

**Report Format:**
```
Environment:
- ABCT Version: 0.8.0
- Installation Type: Standard / Docker
- OS: macOS / Linux / Windows WSL
- Python: 3.x.x

Issue:
[Describe problem]

Steps to Reproduce:
1.
2.

Expected Behavior:
[What should happen]

Actual Behavior:
[What actually happens]

Logs:
[Paste relevant log lines]
```

---

## Next Steps

After successful migration:

1. **Explore New Features**
   - Try the Security Settings page
   - Test HTTPS mode (optional)
   - Review certificate options

2. **Optimize Configuration**
   - Enable audit logging if needed
   - Configure HTTPS for network access
   - Set up automated certificate renewal

3. **Prepare for v0.9.0**
   - Authentication system
   - Advanced rate limiting
   - Enhanced monitoring

4. **Provide Feedback**
   - Report any issues
   - Suggest improvements
   - Share deployment experiences

---

**Migration Guide Version:** 1.0
**Target Version:** v0.8.0
**Last Updated:** 2026-01-26
**Maintained By:** Development Team
