# Security Audit Quick Reference

## Installation (One-Time)

```bash
cd /path/to/ABCT
./sec/install_security_hook.sh
```

## Daily Usage

### Normal Git Workflow
```bash
git add .
git commit -m "Your changes"
git push  # Audit runs automatically
```

### Manual Audit
```bash
python3 sec/security_agent.py --mode audit
```

### Bypass Check (Emergency Only)
```bash
git push --no-verify
```

## What Happens During Push

| Finding | Action | Can Override? |
|---------|--------|---------------|
| CRITICAL/HIGH | **Blocks push** + prompts to fix | ✓ (with confirmation) |
| MEDIUM | **Warns** but continues | N/A (auto-continues) |
| LOW | **Warns** but continues | N/A (auto-continues) |

## Common Scenarios

### ✅ No Issues Found
```
✓ No security issues found. Safe to push!
[Push continues automatically]
```

### ⚠️ High Severity Issues
```
⚠️  CRITICAL/HIGH severity issues found!

Would you like to fix these issues before pushing? (y/n): y
[Push blocked - fix issues and try again]
```

### ℹ️ Medium/Low Issues
```
ℹ️  Found 3 medium and 2 low severity issues.
[Shows warnings but continues with push]
```

## Security Checks (9 Total)

| Check | Severity | Detects |
|-------|----------|---------|
| Authentication | CRITICAL | Missing auth on POST/PUT/DELETE |
| CORS | CRITICAL | Wildcard origins with credentials |
| XSS | HIGH | Unsafe innerHTML usage |
| Error Disclosure | HIGH | Detailed errors in responses |
| Request Limits | HIGH | Missing size limits |
| DOMPurify | HIGH | Missing XSS protection library |
| Network Binding | MEDIUM | Services on 0.0.0.0 |
| Input Validation | MEDIUM | Unvalidated file uploads |
| Secrets | MEDIUM | Hardcoded passwords/keys |

## Fix Examples

### Missing Authentication
```python
# Before
@router.post("/api/endpoint")
async def my_endpoint():
    pass

# After
@router.post("/api/endpoint")
async def my_endpoint(user: str = Depends(verify_admin)):
    pass
```

### XSS Vulnerability
```javascript
// Before
element.innerHTML = userData;

// After
setSafeHTML(element, userData);
```

### CORS Configuration
```python
# Before
allow_origins=["*"]

# After
allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"]
```

## Files

```
sec/
├── security_audit.py         # Core audit engine
├── security_agent.py         # Interactive agent
├── pre-push-hook.sh          # Git hook
├── install_security_hook.sh  # Installer
├── README_SECURITY_AUDIT.md  # Full docs
└── SECURITY_AUDIT_QUICKREF.md  # This file
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hook doesn't run | `chmod +x .git/hooks/pre-push` |
| Python not found | Install Python 3 |
| False positive | Use `--no-verify` or update audit script |
| Too slow | Audit should be < 5 seconds; check for large files |

## Support Commands

```bash
# Test installation
python3 sec/security_audit.py --project-root . --format text

# View last audit
cat sec/last_audit.json | python3 -m json.tool

# Uninstall hook
rm .git/hooks/pre-push

# Reinstall hook
./sec/install_security_hook.sh
```

## Privacy Note

**Commit messages NEVER include vulnerability details.**

✅ Safe commit message:
```
Security: Enhanced security controls
- backend: authentication, error handling
- frontend: input sanitization
```

❌ Never exposed:
- Specific vulnerability types
- File paths or line numbers
- Attack vectors or exploitation methods

## Remember

- **CRITICAL/HIGH**: Fix before push (or override with good reason)
- **MEDIUM/LOW**: Note for future fix
- **Emergency**: Use `--no-verify` only when necessary
- **Reports**: Saved locally, never committed to git
