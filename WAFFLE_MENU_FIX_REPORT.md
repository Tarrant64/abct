# Waffle Menu Fix Report
**Date:** 2026-01-28
**Build:** 1769603933

## Summary
The waffle menu is broken on **wallets.html** and **apis.html** on the Unraid deployment at `http://192.168.1.100:8081`. Additionally, **nft-wall.html** has a separate JavaScript error preventing the waffle menu from working.

## Root Cause Analysis

### Issue 1: CSS Class Mismatch (wallets.html & apis.html)
- **Problem:** The inline CSS in these pages uses `.waffle-menu-dropdown.show` but the JavaScript function `toggleWaffleMenu()` toggles the `.active` class.
- **Location:**
  - `/frontend/wallets.html` lines 106-110
  - `/frontend/apis.html` lines 93-97
- **Fix Applied:** Changed `.waffle-menu-dropdown.show` to `.waffle-menu-dropdown.active` in both files
- **Status:** FIXED in commit d3fb96c (not yet deployed)

### Issue 2: Duplicate API_BASE Declaration (nft-wall.html)
- **Problem:** The deployed version of `nft-wall.html` has an inline script declaring `const API_BASE = '';` which conflicts with the same declaration in `app.js`, causing a fatal JavaScript error that prevents all subsequent scripts from loading.
- **Error:** `Identifier 'API_BASE' has already been declared`
- **Impact:** This prevents `toggleWaffleMenu()` and `initializePrivacyMode()` from being defined, breaking the waffle menu and other functionality.
- **Status:** The local source file does NOT have this issue, which means the deployed version is outdated.

### Issue 3: Deployment Issue
- **Problem:** The Unraid server is serving OLD versions of the HTML files that don't have the fixes from previous commits.
- **Evidence:**
  - Deployed versions show: `BUILD 1769575984`
  - Local fixed versions show: `BUILD 1769590093` (before this fix), `BUILD 1769603933` (after this fix)
  - The deployed nft-wall.html still has the API_BASE bug that should have been fixed earlier

## Test Results on Deployed Unraid Server

| Page | Waffle Menu Works? | Issue | Build on Server |
|------|-------------------|-------|-----------------|
| index.html | ✅ YES | None | - |
| wallets.html | ❌ NO | CSS class mismatch (.show vs .active) | 1769575984 |
| apis.html | ❌ NO | CSS class mismatch (.show vs .active) | 1769575984 |
| services.html | ✅ YES | None | - |
| security.html | ✅ YES | None | - |
| backup.html | ✅ YES | None | - |
| nft-wall.html | ❌ NO | Duplicate API_BASE declaration causes JS error | OLD |
| logs.html | ✅ YES | None | - |

## Files Changed in This Fix

1. `/frontend/wallets.html`
   - Line 106: Changed `.waffle-menu-dropdown.show` to `.waffle-menu-dropdown.active`
   - Line 2197: Updated BUILD to 1769603933

2. `/frontend/apis.html`
   - Line 93: Changed `.waffle-menu-dropdown.show` to `.waffle-menu-dropdown.active`
   - Line 1346: Updated BUILD to 1769603933

## Deployment Required

**CRITICAL:** The fixed files in `/Users/chriscata/Documents/Claude-Projects/ABCT/frontend/` must be deployed to the Unraid server to fix these issues.

### Automated Deployment (Recommended)
Use the provided Unraid deployment script:
```bash
cd /Users/chriscata/Documents/Claude-Projects/ABCT
./abct-docker/update-unraid.sh 192.168.1.100 8081
```

This script will:
1. Sync all files to the Unraid server
2. Stop the existing container
3. Rebuild the Docker image with the updated files
4. Start the new container
5. Verify the service is healthy

### Manual Deployment (Alternative)
If the script fails, manually deploy:
1. SSH to Unraid: `ssh root@192.168.1.100`
2. Stop container: `docker stop abct-dashboard`
3. Copy files from local machine to Unraid (use rsync or scp)
4. Rebuild: `cd /mnt/user/appdata/ABCT && docker build -t abct-dashboard:latest -f abct-docker/Dockerfile .`
5. Start container (see script for full docker run command)

### Verification After Deployment:
1. Navigate to `http://192.168.1.100:8081/wallets.html`
2. Check build number in footer should be: BUILD 1769603933
3. Click the waffle menu button (9 dots) in the top right
4. Menu should appear with all navigation options
5. Repeat for apis.html
6. Test nft-wall.html (should also be fixed by deployment)

## Technical Details

### The CSS Class Issue
The waffle menu styling uses two different class names:
- **styles.css (correct):** `.waffle-menu-dropdown.active { display: flex; }`
- **Inline CSS in wallets.html & apis.html (wrong):** `.waffle-menu-dropdown.show { opacity: 1; ... }`

The JavaScript in app.js uses:
```javascript
function toggleWaffleMenu() {
    const menu = document.getElementById('waffleMenu');
    menu.classList.toggle('active');  // <-- Uses 'active', not 'show'
}
```

This mismatch meant clicking the button added the `.active` class but the CSS was looking for `.show`, so the menu stayed hidden.

### The API_BASE Issue
The deployed nft-wall.html contains:
```javascript
const API_BASE = '';
```

But app.js also declares:
```javascript
const API_BASE = '';
```

When both scripts load, the browser throws an error and stops executing, preventing critical functions from being defined.

## Commit Information
- **Commit:** d3fb96c
- **Message:** fix: Correct waffle menu CSS class from .show to .active
- **Files Changed:** 2 (wallets.html, apis.html)
- **Lines Changed:** 4 (2 CSS changes, 2 build number updates)

## Next Steps
1. ✅ Source files fixed locally
2. ✅ Changes committed to git
3. ⏳ Deploy files to Unraid server
4. ⏳ Verify waffle menu works on all pages
5. ⏳ Verify build numbers match on deployed server
