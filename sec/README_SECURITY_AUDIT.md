# ABCT Security Audit System

Automated security audit system that runs before git pushes to prevent vulnerable code from reaching production.

## Overview

This security audit system provides:

- **Automated vulnerability scanning** before every git push
- **Severity-based blocking**: Critical/High issues block pushes (with user override)
- **Privacy protection**: Generic commit messages with no vulnerability details
- **Multiple operation modes**: Pre-push hook, manual audit, CI/CD integration
- **Comprehensive checks**: Authentication, XSS, CORS, input validation, error disclosure, and more

## Quick Start

### 1. Install the Pre-Push Hook

```bash
cd /path/to/ABCT
./sec/install_security_hook.sh
```

This will:
- Initialize git if needed
- Install the pre-push hook
- Make all security scripts executable
- Test the audit setup

### 2. Test the Setup

Try running an audit manually:

```bash
python3 sec/security_agent.py --mode audit
```

### 3. Normal Git Workflow

The audit runs automatically on every push:

```bash
git add .
git commit -m "Your commit message"
git push  # Security audit runs here
```

## How It Works

### Pre-Push Workflow

```
┌─────────────┐
│  git push   │
└──────┬──────┘
       │
       v
┌─────────────────────┐
│ Run Security Audit  │
│ (9 automated checks)│
└──────┬──────────────┘
       │
       v
┌─────────────────────┐     YES      ┌──────────────┐
│ CRITICAL/HIGH found?├──────────────>│ Prompt user  │
└──────┬──────────────┘               └──────┬───────┘
       │ NO                                   │
       │                              ┌───────┴────────┐
       │                              │ Fix now?       │
       │                              └───────┬────────┘
       │                                      │
       │                           YES ┌──────┴──────┐ NO
       │                              │ Block push  │   │
       v                              └─────────────┘   v
┌─────────────────────┐                          ┌─────────────┐
│ MEDIUM/LOW found?   │                          │ Override?   │
└──────┬──────────────┘                          └──────┬──────┘
       │                                                │
       v                                         YES    v    NO
┌─────────────────────┐                          ┌─────────────┐
│ Show warnings       │                          │ Block push  │
│ Continue with push  │<─────────────────────────┴─────────────┘
└─────────────────────┘
```

### Severity Levels

| Severity | Behavior | Example Issues |
|----------|----------|----------------|
| **CRITICAL** | Block push, prompt to fix | Missing authentication, wildcard CORS with credentials |
| **HIGH** | Block push, prompt to fix | XSS vulnerabilities, request size limits, error disclosure |
| **MEDIUM** | Warn, continue push | Network binding to 0.0.0.0, insufficient validation |
| **LOW** | Warn, continue push | Minor configuration issues, optimization opportunities |

## Security Checks Performed

### 1. Authentication on Endpoints (CRIT-001)
- **What**: Checks for state-changing endpoints (POST/PUT/DELETE/PATCH) without authentication
- **Why**: Prevents unauthorized modifications to data
- **Fix**: Add `user: str = Depends(verify_admin)` parameter

### 2. XSS Vulnerabilities (HIGH-001)
- **What**: Detects unsafe `innerHTML` usage without sanitization
- **Why**: Prevents cross-site scripting attacks
- **Fix**: Use `setSafeHTML()` or `DOMPurify.sanitize()`

### 3. DOMPurify Library (HIGH-001-DEP)
- **What**: Ensures XSS protection library is loaded
- **Why**: Required for client-side sanitization
- **Fix**: Add DOMPurify CDN script tag

### 4. CORS Configuration (CRIT-002)
- **What**: Checks for wildcard CORS or credentials with wildcard origins
- **Why**: Prevents unauthorized cross-origin access
- **Fix**: Restrict `allow_origins` to specific domains

### 5. Error Disclosure (CRIT-003)
- **What**: Detects detailed error messages exposed to clients
- **Why**: Prevents information leakage
- **Fix**: Log full errors, return generic messages

### 6. Request Size Limits (HIGH-002)
- **What**: Checks for request body size limiting
- **Why**: Prevents DoS attacks via large uploads
- **Fix**: Add size limit middleware

### 7. Network Binding (HIGH-003)
- **What**: Checks for services binding to 0.0.0.0
- **Why**: Prevents external network exposure
- **Fix**: Bind to 127.0.0.1 or use environment variable

### 8. Input Validation (MED-004)
- **What**: Checks file upload endpoints for validation
- **Why**: Prevents malicious file uploads
- **Fix**: Validate file extensions and MIME types

### 9. Hardcoded Secrets (MED-SEC)
- **What**: Detects potential hardcoded passwords/API keys
- **Why**: Prevents credential exposure
- **Fix**: Use environment variables

## Usage Examples

### Manual Audit

Run a one-time security audit:

```bash
# Text output
python3 sec/security_agent.py --mode audit

# JSON output with report
python3 sec/security_audit.py --format json --output sec/audit_report.json

# Check specific directory
python3 sec/security_audit.py --project-root /path/to/ABCT
```

### Pre-Push with Report

The pre-push hook automatically saves reports:

```bash
git push  # Audit runs, report saved to sec/last_audit.json
```

View the last audit report:

```bash
cat sec/last_audit.json | python3 -m json.tool
```

### Bypass Security Check (Not Recommended)

In emergency situations, you can skip the check:

```bash
git push --no-verify
```

**Warning**: Only use this for non-production pushes or when you've manually verified security.

### CI/CD Integration

Add to your CI/CD pipeline:

```yaml
# Example GitHub Actions workflow
- name: Security Audit
  run: |
    python3 sec/security_audit.py \
      --format json \
      --output audit_report.json \
      --exit-code

- name: Upload Audit Report
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: security-audit
    path: audit_report.json
```

## Configuration

### Environment Variables

None required. The audit runs with default settings.

### Customization

Edit `sec/security_audit.py` to add custom checks:

```python
def check_my_custom_rule(self):
    """Custom security check"""
    check_id = "CUSTOM-001"
    check_name = "My Custom Security Check"

    for py_file in self.python_files:
        # Your check logic here
        if condition_met:
            self.add_finding(
                severity="HIGH",
                check_id=check_id,
                check_name=check_name,
                file_path=py_file,
                line_number=line_num,
                description="What's wrong",
                recommendation="How to fix"
            )
```

Then register it in `run_all_checks()`:

```python
checks = [
    # ... existing checks ...
    ("My custom check", self.check_my_custom_rule),
]
```

## Troubleshooting

### "Security agent not found"

Ensure you're running from the project root:

```bash
cd /path/to/ABCT
git push
```

### "python3 not found"

Install Python 3:

```bash
# macOS
brew install python3

# Ubuntu/Debian
sudo apt-get install python3
```

### Hook doesn't run

Make sure it's executable:

```bash
chmod +x .git/hooks/pre-push
```

Verify installation:

```bash
ls -la .git/hooks/pre-push
```

### False positives

If the audit reports false positives:

1. Review the finding details
2. If it's truly a false positive, you can:
   - Add comments in code to clarify security (e.g., `# Safe: controlled input`)
   - Modify the audit script to exclude that pattern
   - Use `--no-verify` for that specific push

### Audit is too slow

The audit typically runs in < 5 seconds. If it's slow:

1. Check for very large files in the project
2. Add file size limits in `security_audit.py`
3. Exclude additional directories in `exclude_patterns`

## Privacy & Security

### No Vulnerability Details in Git

The system generates **generic commit messages** that never expose:

- Specific vulnerability types
- File paths or line numbers
- Attack vectors or exploitation methods
- Security check IDs

Example safe commit message:

```
Security: Enhanced security controls

- backend: authentication, error handling
- frontend: input sanitization
- NFT service: CORS configuration

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### Audit Reports (local only)

Detailed audit reports are saved locally at `sec/last_audit.json` but are **never committed to git**.

Add to `.gitignore`:

```
sec/last_audit.json
sec/audit_report_*.json
```

## Files

| File | Purpose |
|------|---------|
| `security_audit.py` | Core audit engine with 9 security checks |
| `security_agent.py` | Interactive agent for pre-push workflow |
| `pre-push-hook.sh` | Git pre-push hook script |
| `install_security_hook.sh` | One-click installer |
| `README_SECURITY_AUDIT.md` | This documentation |

## Compliance

The security audit checks align with:

- **OWASP Top 10** (A01, A03, A05, A07, A08, A09)
- **NIST SP 800-53** (AC-3, AC-6, SI-10, SC-7, AU-2, AU-6)
- **CWE** (CWE-79, CWE-306, CWE-942, CWE-209, CWE-400)
- **CIS Controls** (1-6)
- **CERT Secure Coding Standards**

See `sec/security_audit_report.md` for detailed compliance mapping.

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review audit output for specific error messages
3. Run manual audit with `--format text` for detailed findings
4. Check `sec/last_audit.json` for full details

## Uninstallation

To remove the security hook:

```bash
rm .git/hooks/pre-push
```

To completely remove all security audit files:

```bash
rm -rf sec/security_audit.py
rm -rf sec/security_agent.py
rm -rf sec/pre-push-hook.sh
rm -rf sec/install_security_hook.sh
rm -rf sec/last_audit.json
```

## Version History

### v1.0.0 (2026-01-26)
- Initial release
- 9 automated security checks
- Pre-push hook integration
- Severity-based blocking
- Privacy-preserving commit messages
- Manual audit mode
- CI/CD support
