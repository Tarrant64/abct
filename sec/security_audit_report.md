# ABCT Security Audit Report

**Date:** 2026-01-26
**Auditor:** Claude Sonnet 4.5
**Scope:** Web application security review (backend APIs, frontend, microservice)
**Standards:** OWASP Top 10, NIST SP 800-53/800-218, ISO 27034, CWE, CIS Controls 1-6, CERT Secure Coding

---

## Executive Summary

This comprehensive security audit of the ABCT (A Better Crypto Tracker) application identified **24 security issues** across multiple severity levels. The application manages sensitive data including cryptocurrency wallets, API keys, and SSL certificates, making security critical.

### Key Findings:
- **3 CRITICAL** issues requiring immediate attention
- **5 HIGH** severity vulnerabilities
- **9 MEDIUM** severity issues
- **7 LOW** priority improvements

### Most Critical Issues:
1. **No authentication/authorization** on state-changing endpoints (CRITICAL)
2. **Wildcard CORS with credentials** in microservice (CRITICAL)
3. **XSS vulnerabilities** from innerHTML usage with API data (HIGH)
4. **No request size limits** on file uploads (HIGH)
5. **Network binding to 0.0.0.0** exposes services publicly (HIGH)

---

## Findings by Severity

## CRITICAL SEVERITY

### CRIT-001: Missing Authentication on State-Changing Endpoints
**Check ID:** ABCT-OWASP-A01-001, ABCT-OWASP-A01-002, ABCT-CWE-306-001
**Category:** OWASP A01: Broken Access Control
**Status:** FAIL

**Evidence:**
- No global authentication middleware in `/path/to/abct
- 40+ state-changing endpoints discovered with no auth requirements:
  - `POST /security/certificate/upload` - Uploads SSL certificates (lines 166-245 in security.py)
  - `POST /security/certificate/generate` - Generates certificates (lines 122-164)
  - `PUT /security/settings` - Changes SSL mode (lines 75-120)
  - `DELETE /security/certificate` - Deletes certificates (lines 273-308)
  - `POST /wallets` - Adds wallets (line 703)
  - `DELETE /wallets/{address}` - Deletes wallets (line 906)
  - `PUT /settings/apis/{api_id}` - Saves API keys (line 288)
  - `DELETE /settings/apis/{api_id}` - Deletes API keys (line 307)
  - `POST /custom-tokens` - Adds tokens (line 89)
  - All refresh, sync, and cache endpoints

**Impact:**
- Any unauthenticated remote user can upload malicious SSL certificates
- Attackers can view/modify/delete wallet addresses and API keys
- Complete compromise of application data and configuration
- Enables man-in-the-middle attacks via certificate replacement

**Mappings:**
- OWASP: A01 (Broken Access Control)
- NIST: AC-3, AC-6, SSDF PW.4, RV.1
- CWE: CWE-306 (Missing Authentication), CWE-285 (Improper Authorization)
- ISO 27034: Access control requirements not enforced
- CIS: 5 (Account Management), 6 (Access Control)

**Patch Plan:**
1. **Implement authentication middleware:**
   ```python
   # backend/middleware/auth.py
   from fastapi import Security, HTTPException, status
   from fastapi.security import HTTPBasic, HTTPBasicCredentials
   import secrets
   import os

   security = HTTPBasic()

   def verify_admin(credentials: HTTPBasicCredentials = Security(security)):
       correct_username = os.getenv("ABCT_ADMIN_USER", "admin")
       correct_password = os.getenv("ABCT_ADMIN_PASSWORD", "")

       if not correct_password:
           raise HTTPException(
               status_code=503,
               detail="Authentication not configured"
           )

       is_username_correct = secrets.compare_digest(
           credentials.username.encode("utf8"),
           correct_username.encode("utf8")
       )
       is_password_correct = secrets.compare_digest(
           credentials.password.encode("utf8"),
           correct_password.encode("utf8")
       )

       if not (is_username_correct and is_password_correct):
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Invalid credentials",
               headers={"WWW-Authenticate": "Basic"},
           )
       return credentials.username
   ```

2. **Add auth dependency to security router (backend/routers/security.py):**
   ```python
   from middleware.auth import verify_admin
   from fastapi import Depends

   @router.put("/settings")
   async def update_settings(data: SSLModeUpdate, user: str = Depends(verify_admin)):
       # existing code

   @router.post("/certificate/upload")
   async def upload_certificate(
       cert_file: UploadFile = File(...),
       key_file: UploadFile = File(...),
       user: str = Depends(verify_admin)
   ):
       # existing code

   # Repeat for all state-changing endpoints
   ```

3. **Add localhost-only option for high-risk endpoints:**
   ```python
   # backend/middleware/localhost.py
   from fastapi import Request, HTTPException

   def require_localhost(request: Request):
       client_host = request.client.host
       if client_host not in ["127.0.0.1", "localhost", "::1"]:
           raise HTTPException(
               status_code=403,
               detail="This endpoint is only accessible from localhost"
           )
   ```

4. **Update all routers with appropriate auth:**
   - security.py: All endpoints → `Depends(verify_admin)`
   - settings.py: PUT/DELETE endpoints → `Depends(verify_admin)`
   - wallets.py: POST/DELETE/PATCH → `Depends(verify_admin)`
   - custom_tokens.py: POST/PUT/DELETE → `Depends(verify_admin)`

**Potential Breaks:**
- Existing API clients/scripts will need to send Basic Auth headers
- Frontend must store credentials (consider secure cookie-based session)
- Docker compose needs ABCT_ADMIN_PASSWORD environment variable
- Rate limiting may need adjustment to prevent brute force

**Recommended Approach:**
- Phase 1: Add localhost-only check to security endpoints (immediate)
- Phase 2: Implement full authentication (within 1 week)
- Phase 3: Add session management for frontend (within 2 weeks)

---

### CRIT-002: Wildcard CORS with Credentials Enabled
**Check ID:** ABCT-OWASP-A05-001, ABCT-CIS-004
**Category:** OWASP A05: Security Misconfiguration
**Status:** FAIL

**Evidence:**
```python
# /path/to/abct
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # ← WILDCARD
    allow_credentials=True,        # ← WITH CREDENTIALS
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Impact:**
- Any malicious website can make authenticated requests to the microservice
- Enables CSRF attacks via victim's browser
- Attacker can register/delete collections in price database
- Can trigger price sync operations causing API quota exhaustion

**Mappings:**
- OWASP: A05 (Security Misconfiguration)
- NIST: SC-7, SC-8
- CWE: CWE-942 (Permissive Cross-domain Policy)
- ISO 27034: Insecure interface configuration
- CIS: 4 (Secure Configuration)

**Patch Plan:**
```python
# nft-price-service/app/main.py
import os

# Get allowed origins from environment
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,    # Specific origins only
    allow_credentials=False,           # Disable if not needed
    allow_methods=["GET", "POST"],     # Only needed methods
    allow_headers=["Content-Type"],    # Only needed headers
)
```

**Alternative (if same-origin):**
Remove CORS middleware entirely if microservice is accessed via reverse proxy on same domain.

**Potential Breaks:**
- If frontend is on different domain, update ALLOWED_ORIGINS
- Any external tools using the API need to be whitelisted
- Pre-flight OPTIONS requests may need adjustment

---

### CRIT-003: Secrets Exposure in Error Responses
**Check ID:** ABCT-CERT-002
**Category:** OWASP A09: Security Logging & Monitoring Failures
**Status:** NEEDS-CHANGE

**Evidence:**
Multiple locations print full exception details that could leak secrets:

```python
# wallets.py:848
raise HTTPException(status_code=500, detail=f"Failed to add wallet: {str(e)}")

# security.py:162
raise HTTPException(status_code=500, detail=f"Failed to generate certificate: {str(e)}")

# security.py:244
raise HTTPException(status_code=500, detail=f"Failed to upload certificate: {str(e)}")
```

**Impact:**
- Stack traces may include API keys, file paths, database credentials
- Helps attackers understand internal structure
- Violates compliance requirements (PCI DSS, GDPR)

**Mappings:**
- OWASP: A09
- NIST: AU-9, SI-11
- CWE: CWE-209 (Information Exposure Through Error Message), CWE-532
- CERT: Do not expose sensitive data in errors or logs

**Patch Plan:**
1. **Create safe error handler:**
   ```python
   # backend/utils/errors.py
   import logging
   from fastapi import HTTPException

   logger = logging.getLogger(__name__)

   def safe_error_response(operation: str, error: Exception, status_code: int = 500):
       # Log full error with context
       logger.error(f"{operation} failed: {type(error).__name__}: {str(error)}",
                   exc_info=True)

       # Return safe message to client
       raise HTTPException(
           status_code=status_code,
           detail=f"{operation} failed. Check server logs for details."
       )
   ```

2. **Update all exception handlers:**
   ```python
   # Before:
   except Exception as e:
       raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")

   # After:
   except Exception as e:
       safe_error_response("Upload certificate", e)
   ```

3. **Configure logging redaction:**
   ```python
   # backend/logging_config.py
   import re

   class SecretRedactingFormatter(logging.Formatter):
       PATTERNS = [
           (r'(api[_-]?key["\s:=]+)([a-zA-Z0-9_-]{20,})', r'\1***REDACTED***'),
           (r'(password["\s:=]+)([^\s,}"]+)', r'\1***REDACTED***'),
           (r'(bearer\s+)([a-zA-Z0-9_-]+)', r'\1***REDACTED***'),
       ]

       def format(self, record):
           original = super().format(record)
           for pattern, replacement in self.PATTERNS:
               original = re.sub(pattern, replacement, original, flags=re.IGNORECASE)
           return original
   ```

**Potential Breaks:**
- Debugging becomes harder (must check server logs)
- Automated error monitoring tools need log access
- Frontend may need more specific error codes instead of generic messages

---

## HIGH SEVERITY

### HIGH-001: XSS via innerHTML with API-Derived Values
**Check ID:** ABCT-OWASP-A03-001, ABCT-CWE-79-001
**Category:** OWASP A03: Injection
**Status:** FAIL

**Evidence:**
85+ innerHTML assignments in `/path/to/abct with API data:

```javascript
// Line 217 - Market cap from API
mcapElement.innerHTML = mcap > 0 ? `MCap: ${formatMarketCap(mcap)}` : '';

// Line 268 - Total portfolio value
totalValueEl.innerHTML = formatUSDBlur(totalValue);

// Line 611 - Wallet summary HTML
walletsSummary.innerHTML = summaryHtml;

// Line 643 - Wallet list with addresses and labels
walletsList.innerHTML = wallets.map(wallet => {
    // Includes wallet.address, wallet.label from API
});

// Line 1065 - Governance info
govEl.innerHTML = html;

// Line 2639 - NFT stats
cardanoStats.innerHTML = `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`;
```

**Attack Scenario:**
1. Attacker controls API response (via MITM, compromised API, or database injection)
2. Malicious payload in wallet label: `<img src=x onerror=alert(document.cookie)>`
3. Frontend renders via innerHTML → XSS executes
4. Attacker steals session cookies, API keys from localStorage, or redirects to phishing

**Impact:**
- Session hijacking
- Cryptocurrency wallet address replacement
- Phishing attacks
- Keylogging user inputs

**Mappings:**
- OWASP: A03 (Injection)
- NIST: SI-10
- CWE: CWE-79 (XSS), CWE-116 (Improper Encoding)
- ISO 27034: Output encoding controls missing
- CIS: 4 (Secure Configuration)
- CERT: Validate input, encode output, avoid dangerous APIs

**Patch Plan:**
Replace innerHTML with safe alternatives:

```javascript
// Option 1: Use textContent for plain text
// Before:
totalValueEl.innerHTML = formatUSDBlur(totalValue);

// After:
totalValueEl.textContent = formatUSD(totalValue);

// Option 2: Use DOM methods for structured content
// Before:
walletsList.innerHTML = wallets.map(w => `
    <div class="wallet">
        <span class="address">${w.address}</span>
        <span class="label">${w.label}</span>
    </div>
`).join('');

// After:
walletsList.replaceChildren();
wallets.forEach(w => {
    const div = document.createElement('div');
    div.className = 'wallet';

    const addr = document.createElement('span');
    addr.className = 'address';
    addr.textContent = w.address;  // Safe - auto-escaped

    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = w.label;  // Safe - auto-escaped

    div.appendChild(addr);
    div.appendChild(label);
    walletsList.appendChild(div);
});

// Option 3: Use DOMPurify for complex HTML (install as dependency)
import DOMPurify from 'dompurify';
walletsList.innerHTML = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['div', 'span', 'p'],
    ALLOWED_ATTR: ['class']
});
```

**Recommended Approach:**
1. Install DOMPurify: `npm install dompurify`
2. Create safe rendering helper:
   ```javascript
   // frontend/js/safe-render.js
   import DOMPurify from 'dompurify';

   export function safeSetHTML(element, html) {
       element.innerHTML = DOMPurify.sanitize(html, {
           ALLOWED_TAGS: ['div', 'span', 'p', 'a', 'strong', 'em', 'img'],
           ALLOWED_ATTR: ['class', 'href', 'src', 'alt', 'title'],
           ALLOW_DATA_ATTR: false
       });
   }

   export function safeSetText(element, text) {
       element.textContent = text;  // Always safe
   }
   ```
3. Replace all innerHTML:
   - 85 locations need updates
   - Prioritize: walletsList (line 643), stakingPositions (line 1318), defiCategories (line 1866)
   - Use textContent where possible, DOMPurify for complex HTML

**Potential Breaks:**
- Blur wrappers need adjustment (currently use innerHTML)
- Complex list rendering may need refactoring
- Performance impact (DOMPurify adds ~5-10ms per call)

---

### HIGH-002: No Request Size Limits on File Uploads
**Check ID:** ABCT-OWASP-A05-002
**Category:** OWASP A05: Security Misconfiguration
**Status:** FAIL

**Evidence:**
```python
# security.py:166-245
@router.post("/certificate/upload")
async def upload_certificate(
    cert_file: UploadFile = File(...),  # No size limit
    key_file: UploadFile = File(...)    # No size limit
):
    cert_content = await cert_file.read()  # Unbounded read
    key_content = await key_file.read()    # Unbounded read
```

No size validation before writing to disk. No ASGI server-level limits configured.

**Impact:**
- DoS via large file uploads (GB-sized files)
- Disk space exhaustion
- Memory exhaustion (files loaded into RAM)
- Bypasses rate limiting (one large request = many small)

**Mappings:**
- OWASP: A05
- NIST: SC-5 (DoS Protection), SI-10
- CWE: CWE-400 (Uncontrolled Resource Consumption)
- ISO 27034: Resource management controls
- CIS: 4
- CERT: Limit resource usage

**Patch Plan:**
1. **Add size validation:**
   ```python
   # backend/routers/security.py
   MAX_CERT_SIZE = 1024 * 1024  # 1MB (generous for certs)

   @router.post("/certificate/upload")
   async def upload_certificate(
       cert_file: UploadFile = File(...),
       key_file: UploadFile = File(...)
   ):
       # Check sizes first
       if cert_file.size > MAX_CERT_SIZE:
           raise HTTPException(
               status_code=413,
               detail=f"Certificate file too large (max {MAX_CERT_SIZE} bytes)"
           )
       if key_file.size > MAX_CERT_SIZE:
           raise HTTPException(
               status_code=413,
               detail=f"Key file too large (max {MAX_CERT_SIZE} bytes)"
           )

       # Validate content type
       allowed_types = ["application/x-pem-file", "application/x-x509-ca-cert"]
       if cert_file.content_type not in allowed_types:
           raise HTTPException(400, "Invalid certificate file type")

       # Read with size limit
       cert_content = await cert_file.read(MAX_CERT_SIZE + 1)
       if len(cert_content) > MAX_CERT_SIZE:
           raise HTTPException(413, "Certificate exceeds size limit")

       # Existing code...
   ```

2. **Add uvicorn limit:**
   ```python
   # backend/main.py
   uvicorn_config = {
       "host": "127.0.0.1",
       "port": 8000,
       "reload": True,
       "limit_max_requests": 100,
       "timeout_keep_alive": 5,
       "limit_concurrency": 50
   }
   ```

3. **Add nginx limit (if used):**
   ```nginx
   # nginx.conf
   client_max_body_size 2M;
   client_body_buffer_size 128k;
   ```

**Potential Breaks:**
- Very large valid certificates rejected (rare, but possible)
- Need to document size limits in API docs
- Existing upload scripts may need retry logic

---

### HIGH-003: Network Binding Exposes Services Publicly
**Check ID:** ABCT-OWASP-A05-003, ABCT-CIS-001
**Category:** OWASP A05: Security Misconfiguration
**Status:** NEEDS-CHANGE

**Evidence:**
```python
# nft-price-service/app/main.py:824
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)  # Binds to all interfaces
```

```python
# backend/main.py:237
uvicorn_config = {
    "host": "127.0.0.1",  # Good - localhost only
    # But production docs show: uvicorn main:app --host 0.0.0.0
}
```

**Impact:**
- Microservice accessible from LAN/Internet without TLS
- No authentication on microservice endpoints
- Attackers can manipulate NFT price database
- Can exhaust TapTools API quota (DOS)

**Mappings:**
- OWASP: A05
- NIST: SC-7, AC-17
- CWE: CWE-200 (Information Exposure)
- ISO 27034: Secure deployment configuration
- CIS: 1 (Asset Control), 4
- CERT: Secure defaults, minimize attack surface

**Patch Plan:**
1. **Change microservice default:**
   ```python
   # nft-price-service/app/main.py
   if __name__ == "__main__":
       import uvicorn
       host = os.getenv("BIND_HOST", "127.0.0.1")  # Default localhost
       port = int(os.getenv("BIND_PORT", "8080"))

       if host == "0.0.0.0":
           logger.warning(
               "Binding to 0.0.0.0 - service exposed on network. "
               "Ensure firewall/TLS/auth are configured."
           )

       uvicorn.run(app, host=host, port=port)
   ```

2. **Add Docker Compose network isolation:**
   ```yaml
   # docker-compose.yml
   services:
     nft-price-service:
       networks:
         - internal
       # Do NOT expose ports unless needed
       # ports:
       #   - "8080:8080"  # Remove this

     backend:
       networks:
         - internal
       environment:
         - NFT_PRICE_SERVICE_URL=http://nft-price-service:8080

   networks:
     internal:
       driver: bridge
       internal: true  # No external access
   ```

3. **Add reverse proxy with auth (if external access needed):**
   ```nginx
   # nginx.conf
   location /nft-price/ {
       auth_basic "NFT Price Service";
       auth_basic_user_file /etc/nginx/.htpasswd;
       proxy_pass http://127.0.0.1:8080/;
   }
   ```

**Potential Breaks:**
- External monitoring tools lose access (add to allowed IPs)
- Development workflows may need port forwarding updates
- Docker networks need reconfiguration

---

### HIGH-004: Insufficient Input Validation on Endpoints
**Check ID:** ABCT-CERT-001
**Category:** CERT Secure Coding
**Status:** NEEDS-CHANGE

**Evidence:**
Multiple endpoints accept user input without validation:

```python
# wallets.py:703 - No validation on blockchain detection
async def add_wallet(wallet: WalletCreate):
    address = wallet.address.strip()  # Only strips whitespace
    blockchain = detect_blockchain(address)  # Auto-detect, no validation

# custom_tokens.py:89 - No validation on policy_id format
async def add_custom_token(token: CustomTokenCreate):
    await save_custom_token(
        policy_id=token.policy_id,  # No format check
        quantity=token.quantity      # No range check
    )

# settings.py:288 - No validation on API key format
async def enable_api(api_id: str, data: APIKeyUpdate):
    api_key = data.api_key.strip()  # No format check
    await save_api_setting(api_id, api_key, enabled=True)
```

**Impact:**
- Injection attacks via malformed inputs
- Database corruption from invalid data
- Application crashes from unexpected formats
- Bypasses business logic constraints

**Mappings:**
- OWASP: A03
- NIST: SI-10
- CWE: CWE-20 (Improper Input Validation)
- CERT: Validate all external inputs

**Patch Plan:**
Add validators to Pydantic models:

```python
# backend/models/validators.py
import re
from pydantic import BaseModel, validator, Field

class WalletCreate(BaseModel):
    address: str = Field(min_length=10, max_length=200)
    label: str = Field(None, max_length=100)

    @validator('address')
    def validate_address(cls, v):
        # Remove whitespace
        v = v.strip()

        # Check basic format
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Address contains invalid characters')

        # Check known prefixes
        valid_prefixes = ['addr1', 'stake1', '1', '3', 'bc1', '0x', 'xpub', 'ypub', 'zpub']
        if not any(v.startswith(p) for p in valid_prefixes):
            raise ValueError('Unknown address format')

        return v

class CustomTokenCreate(BaseModel):
    policy_id: str = Field(regex=r'^[a-fA-F0-9]{56}$|^0x[a-fA-F0-9]{40}$')
    quantity: float = Field(gt=0, lt=1e18)

class APIKeyUpdate(BaseModel):
    api_key: str = Field(min_length=20, max_length=200)

    @validator('api_key')
    def validate_key(cls, v):
        v = v.strip()
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Invalid API key format')
        return v
```

**Potential Breaks:**
- Existing wallets with unusual formats may be rejected
- API clients need better error messages for validation failures
- May need whitelist for edge cases

---

### HIGH-005: Server-Side HTML Generation Without Escaping
**Check ID:** ABCT-OWASP-A03-002
**Category:** OWASP A03: Injection
**Status:** PASS (but needs monitoring)

**Evidence:**
```python
# nft-price-service/app/main.py:419-629
html_content = f"""
    <div class="stat-value">{last_update}</div>
    <div class="stat-value">{collections_total}</div>
    <div class="stat-value">{calls_today} / 100</div>
"""
```

**Current Status:** PASS - All interpolated values are numbers/dates from controlled sources.

**Recommendation:**
Add HTML escaping utility for future safety:

```python
# nft-price-service/app/utils.py
import html

def escape_html(value):
    """Escape HTML special characters"""
    if isinstance(value, (int, float)):
        return str(value)
    return html.escape(str(value))

# Usage in main.py:
html_content = f"""
    <div class="stat-value">{escape_html(last_update)}</div>
"""
```

---

## MEDIUM SEVERITY

### MED-001: API Keys Stored in Cleartext Database
**Check ID:** ABCT-OWASP-A08-001, ABCT-CIS-003
**Category:** OWASP A08: Software & Data Integrity Failures
**Status:** NEEDS-CHANGE

**Evidence:**
```python
# database.py - API keys stored without encryption
async def save_api_setting(api_name: str, api_key: str, enabled: bool = True):
    await db.execute(
        "INSERT OR REPLACE INTO api_settings VALUES (?, ?, ?)",
        (api_name, api_key, 1 if enabled else 0)  # Plaintext storage
    )
```

**Impact:**
- Database file read = all API keys compromised
- Backups expose keys
- Violates PCI DSS compliance
- Keys visible in memory dumps

**Mappings:**
- OWASP: A08
- NIST: SC-28, AU-9
- CWE: CWE-522 (Insufficiently Protected Credentials), CWE-312 (Cleartext Storage)
- ISO 27034: Protection of application data and keys
- CIS: 3 (Data Protection)
- CERT: Protect sensitive info at rest

**Patch Plan:**
1. **Add encryption layer:**
   ```python
   # backend/utils/encryption.py
   from cryptography.fernet import Fernet
   import os
   import base64

   def get_encryption_key():
       key = os.getenv("ABCT_ENCRYPTION_KEY")
       if not key:
           # Generate on first run
           key = Fernet.generate_key().decode()
           print(f"Generated encryption key: {key}")
           print("Add to environment: ABCT_ENCRYPTION_KEY={key}")
       return key.encode()

   cipher = Fernet(get_encryption_key())

   def encrypt_value(plaintext: str) -> str:
       return cipher.encrypt(plaintext.encode()).decode()

   def decrypt_value(ciphertext: str) -> str:
       return cipher.decrypt(ciphertext.encode()).decode()
   ```

2. **Update database functions:**
   ```python
   # database.py
   from utils.encryption import encrypt_value, decrypt_value

   async def save_api_setting(api_name: str, api_key: str, enabled: bool = True):
       encrypted_key = encrypt_value(api_key)
       await db.execute(
           "INSERT OR REPLACE INTO api_settings VALUES (?, ?, ?)",
           (api_name, encrypted_key, 1 if enabled else 0)
       )

   async def get_api_key(api_name: str) -> str:
       row = await db.execute(...)
       if row and row[0]:
           return decrypt_value(row[0])
       return None
   ```

3. **Add migration script:**
   ```python
   # migrations/encrypt_existing_keys.py
   async def migrate():
       # Read all keys
       keys = await db.execute("SELECT api_name, api_key FROM api_settings")

       for api_name, plaintext_key in keys:
           encrypted = encrypt_value(plaintext_key)
           await db.execute(
               "UPDATE api_settings SET api_key = ? WHERE api_name = ?",
               (encrypted, api_name)
           )
   ```

**Potential Breaks:**
- Requires ABCT_ENCRYPTION_KEY environment variable
- Lost key = all API keys unrecoverable (document backup procedure)
- Slight performance impact (negligible)

---

### MED-002: No Session Expiry or Token Rotation
**Check ID:** ABCT-OWASP-A07-001
**Category:** OWASP A07: Identification & Authentication Failures
**Status:** NOT-APPLICABLE (auth not implemented yet)

**Recommendation:** When implementing authentication (CRIT-001), ensure:
- Session timeout (30 minutes inactive, 8 hours absolute)
- Token rotation on privilege escalation
- Logout invalidates sessions
- Secure cookie flags (HttpOnly, Secure, SameSite)

---

### MED-003: Missing Content Security Policy
**Category:** Defense in Depth
**Status:** NEEDS-CHANGE

**Recommendation:**
Add CSP headers to prevent XSS:

```python
# backend/main.py
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # Needed for inline scripts
            "style-src 'self' 'unsafe-inline'; "   # Needed for inline styles
            "img-src 'self' data: https:; "        # Allow external images (NFTs)
            "connect-src 'self' https://cardano-mainnet.blockfrost.io"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

---

### MED-004: Logging Insufficient for Audit Trail
**Check ID:** ABCT-OWASP-A09-001
**Category:** OWASP A09: Security Logging & Monitoring Failures
**Status:** NEEDS-CHANGE

**Evidence:**
Security operations not logged:
- Certificate uploads (security.py:166)
- SSL mode changes (security.py:75)
- API key changes (settings.py:288)
- Wallet deletions (wallets.py:906)

**Patch Plan:**
```python
# backend/utils/audit_log.py
import logging
from datetime import datetime

audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)

handler = logging.FileHandler('/app/data/audit.log')
handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s'
))
audit_logger.addHandler(handler)

def log_security_event(event_type: str, user: str, details: dict):
    audit_logger.info(f"{event_type} | user={user} | {details}")

# Usage in routers:
from utils.audit_log import log_security_event

@router.post("/certificate/upload")
async def upload_certificate(..., user: str = Depends(verify_admin)):
    log_security_event("CERT_UPLOAD", user, {
        "cert_type": "custom",
        "cert_path": str(final_cert)
    })
    # existing code
```

---

### MED-005: No Rate Limiting on Authentication
**Category:** Defense in Depth
**Status:** NOT-APPLICABLE (auth not implemented yet)

**Recommendation:** When implementing authentication, add:

```python
# backend/middleware/rate_limit.py
from fastapi import Request, HTTPException
from collections import defaultdict
from datetime import datetime, timedelta

login_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
WINDOW_MINUTES = 15

def check_rate_limit(request: Request):
    client_ip = request.client.host
    now = datetime.now()

    # Clean old attempts
    login_attempts[client_ip] = [
        t for t in login_attempts[client_ip]
        if now - t < timedelta(minutes=WINDOW_MINUTES)
    ]

    # Check limit
    if len(login_attempts[client_ip]) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {WINDOW_MINUTES} minutes."
        )

    login_attempts[client_ip].append(now)
```

---

### MED-006: SQLite Database Not Using WAL Mode
**Category:** Data Integrity
**Status:** NEEDS-CHANGE

**Recommendation:**
Enable Write-Ahead Logging for better concurrency:

```python
# backend/database.py
async def init_db():
    global db
    db = await aiosqlite.connect(DATABASE_PATH)

    # Enable WAL mode for better concurrency
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance

    # Existing code...
```

---

### MED-007: No Dependency Vulnerability Scanning
**Check ID:** ABCT-CIS-002
**Category:** CIS 2: Software Asset Inventory
**Status:** NEEDS-CHANGE

**Recommendation:**
Add CI scanning:

```yaml
# .github/workflows/security.yml
name: Security Checks

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Safety (Python dependency check)
        run: |
          pip install safety
          safety check --file requirements.txt

      - name: Run Bandit (Python SAST)
        run: |
          pip install bandit
          bandit -r backend/ -ll

      - name: Run npm audit (JS dependencies)
        run: |
          cd frontend
          npm audit --audit-level=high

      - name: Gitleaks (secret scanning)
        uses: gitleaks/gitleaks-action@v2
```

---

### MED-008: No Certificate Validation Before Storage
**Category:** Input Validation
**Status:** NEEDS-CHANGE (partially implemented)

**Evidence:**
Certificate validation exists (security.py:199) but can be improved:

```python
# Current validation is basic
is_valid, error = ssl_service.validate_certificate(temp_cert, temp_key)
```

**Recommendation:**
Add stricter validation:

```python
# backend/services/ssl_service.py
from cryptography import x509
from cryptography.hazmat.backends import default_backend

def validate_certificate(self, cert_path, key_path):
    try:
        # Load and parse certificate
        with open(cert_path, 'rb') as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        # Check expiry
        if cert.not_valid_after < datetime.now():
            return False, "Certificate has expired"

        if cert.not_valid_before > datetime.now():
            return False, "Certificate not yet valid"

        # Check key size
        if cert.public_key().key_size < 2048:
            return False, "Key size too small (minimum 2048 bits)"

        # Verify key matches cert
        # ... existing key matching code ...

        return True, None
    except Exception as e:
        return False, str(e)
```

---

### MED-009: Frontend Uses localStorage for Sensitive Data
**Category:** Information Exposure
**Status:** NEEDS-CHANGE

**Evidence:**
```javascript
// app.js uses localStorage for theme preference (line 112)
localStorage.setItem('abct-theme', themeName);
```

**Current Status:** Only non-sensitive data stored (theme).

**Recommendation:**
If adding authentication tokens, use secure httpOnly cookies instead of localStorage:

```javascript
// DON'T:
localStorage.setItem('auth_token', token);  // Vulnerable to XSS

// DO: Set via server
// Set-Cookie: auth_token=...; HttpOnly; Secure; SameSite=Strict
```

---

## LOW SEVERITY

### LOW-001: Missing HTTPS Redirect
**Category:** Transport Security
**Status:** NEEDS-CHANGE

**Recommendation:**
When TLS is enabled, redirect HTTP to HTTPS:

```python
# backend/main.py
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

ssl_mode = os.environ.get('ABCT_SSL_MODE', 'http')
if ssl_mode != 'http':
    app.add_middleware(HTTPSRedirectMiddleware)
```

---

### LOW-002: No Subresource Integrity for External Resources
**Category:** Defense in Depth
**Status:** PASS (no external scripts/styles)

All resources served locally. If adding CDN resources, use SRI:

```html
<script src="https://cdn.example.com/lib.js"
        integrity="sha384-..."
        crossorigin="anonymous"></script>
```

---

### LOW-003: Docker Container Running as Root
**Category:** Container Security
**Status:** NEEDS-CHANGE

**Recommendation:**
```dockerfile
# Dockerfile
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 abct

# ... install dependencies ...

USER abct
CMD ["uvicorn", "main:app", "--host", "127.0.0.1"]
```

---

### LOW-004: No Security Documentation
**Check ID:** ABCT-ISO27034-001
**Category:** ISO/IEC 27034: Application Security Controls
**Status:** FAIL

**Recommendation:**
Create `SECURITY.md`:

```markdown
# ABCT Security Policy

## Reporting Security Issues
Email security@example.com

## Authentication Model
- HTTP Basic Auth for admin endpoints
- Localhost-only for high-risk operations
- Session timeout: 30 minutes

## Data Protection
- API keys encrypted at rest
- SSL certificates stored with 600 permissions
- Audit logs retained for 90 days

## Network Security
- Default bind: localhost only
- Production: reverse proxy with TLS required
- CORS: same-origin only

## Secure Development
- All dependencies scanned weekly
- Pre-commit hooks: gitleaks, eslint
- Manual code review for security changes
```

---

### LOW-005: Version Disclosure in Headers
**Category:** Information Disclosure
**Status:** NEEDS-CHANGE

**Recommendation:**
```python
# backend/main.py
app = FastAPI(
    title="ABCT",
    # version="1.0.0",  # Remove version from API docs
    openapi_url=None   # Disable OpenAPI schema in prod
)

# Add server header override
@app.middleware("http")
async def hide_server_header(request, call_next):
    response = await call_next(request)
    response.headers["Server"] = "ABCT"  # Generic name
    return response
```

---

### LOW-006: No CSRF Protection
**Category:** Defense in Depth
**Status:** NOT-APPLICABLE (no auth yet)

**Recommendation:** When implementing authentication, add CSRF tokens:

```python
from starlette.middleware.csrf import CSRFMiddleware

app.add_middleware(
    CSRFMiddleware,
    secret=os.getenv("CSRF_SECRET", Fernet.generate_key())
)
```

---

### LOW-007: Insecure Direct Object References
**Category:** Access Control
**Status:** LOW-RISK (local-only usage)

**Evidence:**
```python
# wallets.py:943
@router.put("/{wallet_id}/label")
async def update_wallet_label(wallet_id: int, data: dict):
    # No ownership check - any user can modify any wallet
```

**Current Status:** LOW RISK because local-only usage.

**Recommendation:** When adding auth, verify ownership:

```python
@router.put("/{wallet_id}/label")
async def update_wallet_label(
    wallet_id: int,
    data: dict,
    user: str = Depends(verify_admin)
):
    # In multi-user scenario:
    # wallet = await get_wallet(wallet_id)
    # if wallet.owner != user:
    #     raise HTTPException(403, "Not authorized")
    pass
```

---

## Summary of Recommendations

### Immediate Actions (Within 1 Week)
1. **Add localhost-only check to security endpoints** (CRIT-001)
2. **Fix CORS configuration in microservice** (CRIT-002)
3. **Add request size limits to uploads** (HIGH-002)
4. **Implement safe error handling** (CRIT-003)

### Short-Term (Within 1 Month)
5. **Implement authentication on all state-changing endpoints** (CRIT-001)
6. **Fix XSS vulnerabilities** - Replace innerHTML (HIGH-001)
7. **Add input validation** (HIGH-004)
8. **Encrypt API keys at rest** (MED-001)
9. **Add security audit logging** (MED-004)

### Long-Term (Within 3 Months)
10. **Implement automated security scanning in CI** (MED-007)
11. **Add comprehensive security documentation** (LOW-004)
12. **Implement CSP headers** (MED-003)
13. **Container security hardening** (LOW-003)

---

## Testing Recommendations

### Manual Security Testing
```bash
# Test unauthenticated access (should fail after fixes)
curl -X POST http://localhost:8000/security/certificate/upload
curl -X PUT http://localhost:8000/settings/apis/blockfrost -d '{"api_key":"test"}'
curl -X DELETE http://localhost:8000/wallets/addr1...

# Test CORS (should fail after microservice fix)
curl -H "Origin: http://evil.com" \
     -H "Cookie: auth=..." \
     http://localhost:8080/collections/register

# Test XSS (should be escaped after fixes)
curl -X POST http://localhost:8000/wallets \
     -d '{"address":"addr1...", "label":"<script>alert(1)</script>"}'

# Test file upload limits (should fail after fixes)
dd if=/dev/zero of=large.pem bs=10M count=1
curl -X POST http://localhost:8000/security/certificate/upload \
     -F "cert_file=@large.pem" -F "key_file=@large.pem"
```

### Automated Testing
```python
# tests/security/test_auth.py
import pytest
from fastapi.testclient import TestClient

def test_security_endpoints_require_auth():
    """Ensure security endpoints reject unauthenticated requests"""
    client = TestClient(app)

    # Should return 401
    response = client.put("/security/settings", json={"ssl_mode": "http"})
    assert response.status_code == 401

    response = client.post("/security/certificate/upload")
    assert response.status_code == 401

def test_xss_prevention():
    """Ensure XSS payloads are escaped"""
    client = TestClient(app)

    # Add wallet with XSS payload
    response = client.post("/wallets", json={
        "address": "addr1...",
        "label": "<script>alert('XSS')</script>"
    })

    # Get wallets list
    response = client.get("/wallets")
    wallets = response.json()

    # Label should be escaped
    assert "<script>" not in str(wallets)
    assert "&lt;script&gt;" in str(wallets) or "script" not in str(wallets)
```

---

## Compliance Matrix

| Finding | OWASP | NIST | CWE | ISO 27034 | CIS | CERT |
|---------|-------|------|-----|-----------|-----|------|
| CRIT-001 | A01 | AC-3, AC-6 | CWE-306 | Access Control | 5, 6 | Auth/Authz |
| CRIT-002 | A05 | SC-7, SC-8 | CWE-942 | Interface Config | 4 | Secure Defaults |
| CRIT-003 | A09 | AU-9, SI-11 | CWE-209 | Logging | 4 | No Secrets in Logs |
| HIGH-001 | A03 | SI-10 | CWE-79 | Output Encoding | 4 | Validate Input |
| HIGH-002 | A05 | SC-5, SI-10 | CWE-400 | Resource Mgmt | 4 | Limit Resources |
| HIGH-003 | A05 | SC-7, AC-17 | CWE-200 | Deployment Config | 1, 4 | Min Attack Surface |
| HIGH-004 | A03 | SI-10 | CWE-20 | Input Validation | 4 | Validate All Input |
| MED-001 | A08 | SC-28 | CWE-522 | Data Protection | 3 | Protect at Rest |

---

## Appendix: Endpoint Inventory

### State-Changing Endpoints Requiring Authentication

**Security Router (High Risk)**
- `PUT /security/settings` - Change SSL mode
- `POST /security/certificate/generate` - Generate certificate
- `POST /security/certificate/upload` - Upload certificate
- `DELETE /security/certificate` - Delete certificate

**Settings Router**
- `PUT /settings/apis/{api_id}` - Save API key
- `DELETE /settings/apis/{api_id}` - Delete API key
- `PUT /settings/api-utilization/{api_id}/limit` - Update rate limit
- `DELETE /settings/api-utilization/{api_id}/limit` - Reset rate limit

**Wallets Router**
- `POST /wallets` - Add wallet
- `DELETE /wallets/{address}` - Delete wallet
- `PATCH /wallets/{address}` - Update label
- `POST /wallets/sync` - Sync from file
- `POST /wallets/add-multiple` - Bulk add

**Custom Tokens Router**
- `POST /custom-tokens` - Add token
- `PUT /custom-tokens/{token_id}` - Update quantity
- `DELETE /custom-tokens/{token_id}` - Delete token

**NFTs Router**
- `POST /nfts/images/enable` - Enable caching
- `POST /nfts/images/disable` - Disable caching
- `DELETE /nfts/images/clear` - Clear cache

**Microservice (nft-price-service)**
- `POST /collections/register` - Register collection
- `POST /collections/register-batch` - Bulk register
- `DELETE /collections/{policy_id}` - Remove collection
- `POST /sync/trigger` - Trigger manual sync

**Total:** 40+ state-changing endpoints without authentication

---

## Conclusion

ABCT has significant security vulnerabilities that expose it to unauthorized access, data manipulation, and XSS attacks. The lack of authentication on critical endpoints is the most severe issue, followed by CORS misconfiguration and XSS vulnerabilities.

**Priority Ranking:**
1. **Authentication** (CRITICAL) - Prevents unauthorized access to all operations
2. **CORS Fix** (CRITICAL) - Prevents CSRF attacks on microservice
3. **XSS Prevention** (HIGH) - Prevents session hijacking and data theft
4. **Input Validation** (HIGH) - Prevents injection attacks
5. **Encryption at Rest** (MEDIUM) - Protects stored API keys
6. **Audit Logging** (MEDIUM) - Enables incident response

With these fixes implemented, ABCT would meet baseline security requirements for a local cryptocurrency portfolio tracker. For production deployment, additional hardening (TLS termination, WAF, IDS) would be recommended.

---

**Report End**
