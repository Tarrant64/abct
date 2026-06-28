# ABCT Security Policy

**Version:** 0.8.0
**Last Updated:** 2026-01-26

---

## Table of Contents

1. [Security Model](#security-model)
2. [Reporting Security Issues](#reporting-security-issues)
3. [Authentication Requirements](#authentication-requirements)
4. [Data Protection](#data-protection)
5. [Network Security](#network-security)
6. [SSL/HTTPS Configuration](#sslhttps-configuration)
7. [Environment Variables Reference](#environment-variables-reference)
8. [Security Best Practices](#security-best-practices)
9. [Logging and Monitoring](#logging-and-monitoring)
10. [Compliance](#compliance)

---

## Security Model

### Deployment Modes

ABCT supports two primary deployment modes with different security profiles:

#### 1. Local-Only Mode (Default)

**Intended Use:** Personal use on a single machine

**Security Profile:**
- Server binds to `127.0.0.1` (localhost only)
- No authentication required
- HTTP protocol (no encryption)
- Not accessible from network
- Suitable for: Single-user desktop installations

**Configuration:**
```bash
# run.sh defaults
uvicorn main:app --host 127.0.0.1 --port 8000
```

**Security Level:** ⭐⭐⭐ (Good for local use)

#### 2. Network/Remote Mode

**Intended Use:** Access from multiple devices or remote locations

**Security Profile:**
- Server binds to `0.0.0.0` (all interfaces) or specific IP
- Authentication REQUIRED
- HTTPS REQUIRED
- Firewall configuration REQUIRED
- Suitable for: Home networks, VPN access, self-hosted servers

**Configuration:**
```bash
# Production deployment
uvicorn main:app --host 0.0.0.0 --port 8000 \
  --ssl-certfile /path/to/cert.pem \
  --ssl-keyfile /path/to/key.pem
```

**Security Level:** ⭐⭐⭐⭐⭐ (Production-ready with all features enabled)

### Threat Model

**Assets Protected:**
- Cryptocurrency wallet addresses
- API keys (Blockfrost, CExplorer, TapTools, etc.)
- Portfolio value data
- Transaction history
- NFT metadata

**Note:** ABCT is a **read-only** portfolio tracker:
- Cannot move funds or sign transactions
- Cannot access private keys
- Only displays balances and history
- View-only API credentials

**Threats Considered:**
1. Unauthorized access to portfolio data
2. API key theft enabling account takeover
3. Man-in-the-middle attacks on HTTP connections
4. XSS attacks stealing session data
5. CSRF attacks modifying configuration

**Threats NOT Considered:**
- Private key compromise (ABCT doesn't store private keys)
- Blockchain attacks (read-only access)
- DNS poisoning (use HTTPS with certificate validation)

---

## Reporting Security Issues

### Responsible Disclosure

We take security seriously. If you discover a security vulnerability:

**DO:**
- Email security details to: `security@yourdomain.com` (replace with actual contact)
- Provide detailed reproduction steps
- Allow 90 days for patch before public disclosure
- Encrypt sensitive reports using our PGP key (if available)

**DON'T:**
- Publicly disclose before patch is available
- Exploit vulnerabilities in production systems
- Attempt to access other users' data

### Reporting Format

```
Subject: [SECURITY] Brief vulnerability description

1. Vulnerability Type: (XSS, Auth Bypass, etc.)
2. Affected Version: (e.g., v0.7.0, v0.8.0)
3. Severity: (Critical, High, Medium, Low)
4. Steps to Reproduce:
   - Step 1
   - Step 2
5. Impact: (What can an attacker do?)
6. Proof of Concept: (Code, screenshots)
7. Suggested Fix: (Optional)
```

### Security Updates

Security patches are released as:
- **Critical:** Immediate patch release (same day)
- **High:** Patch within 7 days
- **Medium:** Included in next release
- **Low:** Included in next major version

Check for updates:
```bash
# Check current version
curl http://127.0.0.1:8000/api/status

# Watch releases
# GitHub: https://github.com/your-repo/releases
# Docker: docker pull your-registry/abct:latest
```

---

## Authentication Requirements

### Current Status (v0.8.0)

**Local-Only Deployments:**
- No authentication implemented
- Not required (localhost binding only)

**Network Deployments:**
- Authentication implementation planned for v0.9.0
- Current workaround: Use reverse proxy with auth (nginx, Caddy)

### Planned Authentication (v0.9.0+)

#### HTTP Basic Authentication

Simple username/password auth for admin operations:

```bash
# Environment variables
ABCT_ADMIN_USER=admin
ABCT_ADMIN_PASSWORD=your_secure_password
```

**Protected Endpoints:**
- All POST/PUT/DELETE operations
- API key management
- Certificate upload/generation
- Wallet management
- Settings changes

**Public Endpoints:**
- GET /health
- GET /api/status
- GET /wallets (read-only)
- GET /portfolio/* (read-only)

#### Session Management

- Session timeout: 30 minutes inactive, 8 hours absolute
- Secure cookie flags: HttpOnly, Secure, SameSite=Strict
- Logout invalidates session server-side
- No persistent "remember me" option

### Interim Authentication (Current)

Until built-in auth is available, use reverse proxy:

**Nginx Example:**
```nginx
location / {
    auth_basic "ABCT Portfolio Tracker";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://127.0.0.1:8000;
}
```

**Caddy Example:**
```
abct.yourdomain.com {
    basicauth {
        admin $2a$14$...  # bcrypt hash
    }
    reverse_proxy localhost:8000
}
```

---

## Data Protection

### Data at Rest

#### API Keys Storage

**Current (v0.7.0):** Cleartext in SQLite database
**Future (v0.8.0+):** AES-256 encryption

```bash
# Environment variable for encryption key
ABCT_ENCRYPTION_KEY=base64_encoded_32_byte_key
```

**Key Management:**
- Generate once, store securely
- Lost key = all API keys unrecoverable
- Backup key separately from database
- Rotate annually or after suspected compromise

#### Database Encryption

SQLite database stored in `data/portfolio.db`:
- File permissions: 600 (owner read/write only)
- Location: Inside Docker volume (isolated)
- Backup encryption: Use `gpg` or `age` for backups

**Backup Example:**
```bash
# Encrypted backup
sqlite3 data/portfolio.db .dump | gpg -c > backup.sql.gpg

# Restore
gpg -d backup.sql.gpg | sqlite3 data/portfolio_restored.db
```

#### Certificate Storage

SSL certificates stored in `certs/` directory:
- Private key permissions: 600 (critical)
- Certificate permissions: 644 (public)
- Directory permissions: 700

```bash
chmod 700 certs/
chmod 600 certs/*.key
chmod 644 certs/*.crt
```

### Data in Transit

#### HTTPS/SSL

**Status:** Optional (v0.8.0+)

**Modes:**
1. **HTTP Only** (default): Localhost only, no encryption needed
2. **HTTPS Self-Signed**: Auto-generated cert for local HTTPS
3. **HTTPS Custom**: User-provided certificate (Let's Encrypt, commercial CA)

**Configuration:** See [SSL/HTTPS Configuration](#sslhttps-configuration)

#### API Communication

All external API calls use HTTPS:
- Blockfrost: `https://cardano-mainnet.blockfrost.io`
- CoinGecko: `https://api.coingecko.com`

Certificate validation enabled by default. Do not disable:
```python
# WRONG - disables cert validation
requests.get(url, verify=False)

# CORRECT - validates certificates
requests.get(url, verify=True)
```

### Data in Memory

**Sensitive Data Handling:**
- API keys loaded once at startup
- Not logged or printed
- Cleared on process exit
- Memory dumps may contain keys (use encrypted swap)

**Privacy Mode:**
- Frontend blur feature (cosmetic only)
- Does not encrypt data
- Does not prevent API access
- Useful for screenshots/demos

---

## Network Security

### Firewall Configuration

#### Local-Only Mode
No firewall changes needed (localhost binding).

#### Network Mode
Restrict access to trusted networks:

**UFW (Ubuntu/Debian):**
```bash
# Allow only from home network
sudo ufw allow from 192.168.x.x/24 to any port 8000

# Allow only from VPN
sudo ufw allow from 10.8.0.0/24 to any port 8000

# Block all other
sudo ufw enable
```

**firewalld (RHEL/CentOS):**
```bash
firewall-cmd --permanent --zone=home --add-source=192.168.x.x/24
firewall-cmd --permanent --zone=home --add-port=8000/tcp
firewall-cmd --reload
```

**iptables:**
```bash
# Allow from local network only
iptables -A INPUT -p tcp --dport 8000 -s 192.168.x.x/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j DROP
```

### Port Security

**Default Ports:**
- 8000: ABCT Dashboard (HTTP)
- 8443: ABCT Dashboard (HTTPS, if enabled)
- 8080: NFT Price Service (internal only)

**Docker Port Mapping:**
```yaml
# Expose only to localhost
ports:
  - "127.0.0.1:8000:80"

# Expose to network (requires auth + HTTPS)
ports:
  - "8000:80"
```

### CORS Policy

**Main Application:** Same-origin only (no CORS)

**NFT Price Service:**
- **Hardened (v0.8.0):** Specific origins only
- **Permissive (v0.7.0):** Wildcard (insecure)

```python
# Recommended configuration
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://abct.yourdomain.com"
]
```

### Network Isolation (Docker)

Use internal Docker networks:
```yaml
networks:
  internal:
    driver: bridge
    internal: true  # No external access

services:
  abct:
    networks:
      - internal
  nft-price-service:
    networks:
      - internal
```

---

## SSL/HTTPS Configuration

### Enabling HTTPS

#### Option 1: Self-Signed Certificate (Quick Start)

**Use Case:** Local HTTPS testing, bypassing browser warnings

```bash
# Generate certificate via UI
# 1. Navigate to /security.html
# 2. Click "Generate Self-Signed Certificate"
# 3. Select HTTPS mode and restart

# OR via CLI
./run.sh --https
```

**Browser Warning:** Self-signed certs trigger warnings. Click "Advanced" → "Proceed to localhost (unsafe)".

#### Option 2: Custom Certificate (Production)

**Use Case:** Production deployment with valid CA certificate

**Using Let's Encrypt:**
```bash
# Install certbot
sudo apt install certbot

# Generate certificate
sudo certbot certonly --standalone -d abct.yourdomain.com

# Copy to ABCT
mkdir -p certs/
sudo cp /etc/letsencrypt/live/abct.yourdomain.com/fullchain.pem certs/server.crt
sudo cp /etc/letsencrypt/live/abct.yourdomain.com/privkey.pem certs/server.key
sudo chown $USER:$USER certs/*
chmod 600 certs/server.key

# Enable HTTPS
./run.sh --cert certs/server.crt --key certs/server.key
```

**Using Commercial CA:**
1. Purchase certificate from CA (DigiCert, Sectigo, etc.)
2. Upload via `/security.html` UI
3. Select "HTTPS Custom" mode
4. Restart server

#### Option 3: Reverse Proxy (Recommended)

**Use Case:** Production deployment with centralized SSL termination

**Caddy (Automatic HTTPS):**
```
abct.yourdomain.com {
    reverse_proxy localhost:8000
}
```

**Nginx:**
```nginx
server {
    listen 443 ssl http2;
    server_name abct.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/abct.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/abct.yourdomain.com/privkey.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Certificate Requirements

**Minimum Standards:**
- Key size: 2048-bit RSA (4096-bit recommended)
- Signature algorithm: SHA-256 or better
- Validity: Not expired
- SAN: Include all hostnames (localhost, 127.0.0.1, domain)

**Certificate Validation:**
```bash
# Check certificate details
openssl x509 -in certs/server.crt -text -noout

# Verify key matches certificate
openssl x509 -noout -modulus -in certs/server.crt | openssl md5
openssl rsa -noout -modulus -in certs/server.key | openssl md5
# Hashes should match
```

### HTTPS Best Practices

1. **Always use HTTPS for network deployments**
2. **Use valid CA certificates in production**
3. **Enable HSTS header** (reverse proxy)
4. **Redirect HTTP to HTTPS**
5. **Renew certificates before expiry** (Let's Encrypt: 90 days)
6. **Monitor certificate expiration**

---

## Environment Variables Reference

### Required Variables

```bash
# Cardano blockchain access (required)
BLOCKFROST_API_KEY=mainnet_your_api_key_here
```

### Optional Security Variables

```bash
# SSL/HTTPS Configuration
ABCT_SSL_MODE=http                          # http | https-self-signed | https-custom
ABCT_SSL_CERT=/app/certs/server.crt         # Path to SSL certificate
ABCT_SSL_KEY=/app/certs/server.key          # Path to SSL private key
ABCT_SSL_ENABLED=true                       # Enable HTTPS in Docker
ABCT_SSL_PORT=8443                          # HTTPS port (Docker)

# Authentication (v0.9.0+)
ABCT_ADMIN_USER=admin                       # Admin username
ABCT_ADMIN_PASSWORD=secure_password_here    # Admin password (hash recommended)
ABCT_ENCRYPTION_KEY=base64_encoded_key      # For API key encryption

# Network Configuration
BIND_HOST=127.0.0.1                         # Bind address (default: localhost)
BIND_PORT=8000                              # HTTP port

# CORS (NFT Price Service)
ALLOWED_ORIGINS=http://localhost:8000,https://abct.example.com

# Session Management (v0.9.0+)
SESSION_TIMEOUT_MINUTES=30                  # Inactive session timeout
SESSION_MAX_AGE_HOURS=8                     # Absolute session limit
CSRF_SECRET=random_32_byte_key              # CSRF token secret
```

### Docker-Specific Variables

```bash
# Environment file: .env (project root)
ABCT_PORT=8080                              # External HTTP port
ABCT_SSL_PORT=8443                          # External HTTPS port
ABCT_SSL_ENABLED=true                       # Enable SSL in container
```

### Security Environment File Example

**`.env`:**
```bash
# Required
BLOCKFROST_API_KEY=mainnet_ABC123...

# Security (production)
ABCT_SSL_ENABLED=true
ABCT_ADMIN_USER=admin
ABCT_ADMIN_PASSWORD=use_strong_password_here
ABCT_ENCRYPTION_KEY=generate_with_openssl_rand

# Network (restrict to VPN)
BIND_HOST=10.8.0.1  # VPN interface only

# Optional
CEXPLORER_API_KEY=your_key
```

**Security Notes:**
- Never commit `.env` to version control
- Use `.gitignore` to exclude `.env`
- Set file permissions: `chmod 600 .env`
- Rotate passwords/keys regularly

---

## Security Best Practices

### Deployment

#### Development/Testing
```bash
# Local machine only
./run.sh  # Binds to 127.0.0.1, HTTP
```

#### Home Network
```bash
# Require HTTPS + authentication
ABCT_SSL_ENABLED=true
ABCT_ADMIN_USER=admin
ABCT_ADMIN_PASSWORD=strong_password

# Bind to internal IP
BIND_HOST=192.168.x.x

# Run with restrictions
./run.sh --cert certs/server.crt --key certs/server.key
```

#### Production/Cloud
```bash
# Use reverse proxy (Caddy/Nginx)
# Let reverse proxy handle:
# - HTTPS termination
# - Authentication
# - Rate limiting
# - WAF (Web Application Firewall)

# ABCT runs on localhost only
uvicorn main:app --host 127.0.0.1 --port 8000
```

### API Key Management

**Best Practices:**
1. **Never commit API keys to git**
   - Use `.gitignore` for `.env`
   - Use `.env.example` with placeholders

2. **Use least-privilege API keys**
   - Blockfrost: Read-only project keys
   - Coinbase: View-only permissions
   - No withdraw/trade permissions needed

3. **Rotate keys periodically**
   - Quarterly rotation recommended
   - Immediately after suspected compromise

4. **Monitor API usage**
   - Check for unexpected spikes
   - Set up usage alerts
   - Review API logs monthly

### Password Security

**Creating Strong Passwords:**
```bash
# Generate random password
openssl rand -base64 32

# Generate encryption key
openssl rand -base64 32

# Hash password (for storage)
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()))"
```

**Requirements:**
- Minimum 16 characters
- Mix of letters, numbers, symbols
- No dictionary words
- Unique per service

### Update Management

**Stay Updated:**
```bash
# Check current version
curl http://127.0.0.1:8000/api/status

# Update to latest
git pull origin main
./stop.sh
./run.sh

# Docker
docker-compose pull
docker-compose up -d
```

**Subscribe to Security Advisories:**
- GitHub: Watch repository for releases
- Email: Subscribe to security mailing list
- RSS: Follow release feed

### Backup Security

**Backup Strategy:**
```bash
# Daily automated backup
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/secure/backups/abct"

# Backup database
cp data/portfolio.db "$BACKUP_DIR/portfolio_$DATE.db"

# Encrypt backup
gpg --symmetric --cipher-algo AES256 \
    --output "$BACKUP_DIR/portfolio_$DATE.db.gpg" \
    "$BACKUP_DIR/portfolio_$DATE.db"

# Remove unencrypted
rm "$BACKUP_DIR/portfolio_$DATE.db"

# Keep last 30 days
find "$BACKUP_DIR" -name "*.gpg" -mtime +30 -delete
```

**Backup Checklist:**
- ✓ Daily automated backups
- ✓ Encrypted at rest
- ✓ Stored off-site (cloud, external drive)
- ✓ Tested restore procedure monthly
- ✓ Retention: 30 days minimum

---

## Logging and Monitoring

### Application Logs

**Log Locations:**
- Development: Console output (`./run.sh -f`)
- Production: `logs/abct.log`
- Docker: `docker-compose logs abct`

**Log Levels:**
```python
# backend/main.py
logging.basicConfig(
    level=logging.INFO,  # INFO for production, DEBUG for dev
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Security Events to Log

**Critical Events:**
- Authentication failures
- Certificate changes
- SSL mode changes
- API key additions/deletions
- Wallet additions/deletions

**Audit Log Format:**
```
2026-01-26 10:15:23 | INFO | CERT_UPLOAD | user=admin | cert_type=custom | path=/app/certs/custom.crt
2026-01-26 10:16:45 | INFO | SSL_MODE_CHANGE | user=admin | old_mode=http | new_mode=https-custom
2026-01-26 10:20:10 | WARN | AUTH_FAILURE | user=unknown | ip=192.168.x.x | endpoint=/security/settings
```

### Log Retention

**Recommendations:**
- Application logs: 30 days
- Audit logs: 90 days minimum (1 year for compliance)
- Error logs: 90 days
- Access logs: 7 days

**Log Rotation:**
```bash
# /etc/logrotate.d/abct
/path/to/abct/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 abct abct
}
```

### Monitoring Alerts

**Metrics to Monitor:**
1. Failed authentication attempts (> 5 in 15 min)
2. Certificate expiration (< 30 days remaining)
3. Unusual API key usage (spike in calls)
4. Database file size (growth rate)
5. Service uptime/downtime

**Example Alert (Prometheus + Alertmanager):**
```yaml
groups:
  - name: abct_security
    rules:
      - alert: CertificateExpiringSoon
        expr: abct_cert_days_remaining < 30
        labels:
          severity: warning
        annotations:
          summary: "SSL certificate expires in {{ $value }} days"
```

### Intrusion Detection

**Indicators of Compromise:**
- Multiple failed auth attempts from same IP
- Unusual API endpoints accessed
- Large file uploads (if limits disabled)
- Database file modified externally
- Unexpected SSL certificate changes

**Response Procedures:**
1. Block offending IP address
2. Review audit logs
3. Rotate compromised credentials
4. Scan for malware
5. Restore from clean backup if needed

---

## Compliance

### Data Privacy

**GDPR Considerations:**
ABCT is designed for **personal use** and typically does not process others' personal data. If you track wallets belonging to others:

1. **Obtain consent** before tracking addresses
2. **Purpose limitation**: Only track for agreed purposes
3. **Right to erasure**: Implement wallet deletion on request
4. **Data minimization**: Only store necessary data
5. **Security measures**: Encrypt, access control, backups

**Compliance Mode:**
```bash
# Enable audit logging
ENABLE_AUDIT_LOG=true

# Encrypt sensitive data
ABCT_ENCRYPTION_KEY=your_key_here

# Restrict network access
BIND_HOST=127.0.0.1
```

### PCI DSS

**Not Applicable:** ABCT does not process credit card transactions or payment data.

### SOC 2

For enterprise deployments tracking organizational funds:

**Type II Controls:**
- **CC6.1**: Logical access controls (authentication)
- **CC6.6**: Encryption in transit (HTTPS)
- **CC6.7**: Encryption at rest (API keys)
- **CC7.2**: Detection of security events (audit logs)

### Industry Best Practices

**NIST Cybersecurity Framework:**
- Identify: Asset inventory (wallets, API keys)
- Protect: Encryption, auth, network controls
- Detect: Logging, monitoring, alerts
- Respond: Incident response plan
- Recover: Backups, rollback procedures

**OWASP Top 10 Compliance:**
- A01 Broken Access Control: Auth required for state-changing ops
- A02 Cryptographic Failures: HTTPS, encrypted storage
- A03 Injection: Input validation, parameterized queries
- A05 Security Misconfiguration: Secure defaults
- A07 Auth Failures: Strong passwords, session mgmt
- A09 Logging Failures: Audit logs, monitoring

---

## Security Checklist

### Pre-Deployment

- [ ] Change default passwords
- [ ] Generate encryption keys
- [ ] Configure firewall rules
- [ ] Enable HTTPS (if network deployment)
- [ ] Set up authentication (if network deployment)
- [ ] Configure backups
- [ ] Review environment variables
- [ ] Test security settings
- [ ] Document deployment configuration

### Post-Deployment

- [ ] Verify HTTPS works
- [ ] Test authentication
- [ ] Confirm firewall blocks unauthorized IPs
- [ ] Monitor logs for errors
- [ ] Set up alerts
- [ ] Schedule security reviews
- [ ] Train users on security practices

### Ongoing Maintenance

- [ ] Monthly: Review audit logs
- [ ] Monthly: Test backup restore
- [ ] Quarterly: Rotate API keys
- [ ] Quarterly: Update dependencies
- [ ] Annually: Security audit
- [ ] Annually: Rotate encryption keys
- [ ] As needed: Apply security patches

---

## Additional Resources

### Security Tools

**Scanning:**
- `bandit` - Python security linter
- `safety` - Dependency vulnerability scanner
- `gitleaks` - Secret scanning

**Testing:**
- OWASP ZAP - Web application security scanner
- Burp Suite - Manual security testing
- `sqlmap` - SQL injection testing

**Monitoring:**
- Fail2ban - Intrusion prevention
- OSSEC - Host-based intrusion detection
- Prometheus + Grafana - Metrics and alerting

### Documentation

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CIS Controls](https://www.cisecurity.org/controls)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

---

**Document Version:** 1.0
**Last Reviewed:** 2026-01-26
**Next Review:** 2026-04-26
**Maintained By:** Security Team
