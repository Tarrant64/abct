# Post-Deployment Verification Checklist
**Date:** 2026-01-28
**Build:** 1769603933
**Deployment Target:** http://192.168.1.100:8081

## Pre-Deployment Status
- ✅ Source files fixed locally
- ✅ Changes committed to git (commit d3fb96c)
- ⏳ Deployment script running (`./abct-docker/update-unraid.sh 192.168.1.100 8081`)

## Verification Steps

### 1. Check Build Numbers
Verify that the deployed files show the correct build number in the footer:

- [ ] **index.html** - http://192.168.1.100:8081/
  - Expected: Any build (index.html wasn't changed)
  - Check: Footer shows version number

- [ ] **wallets.html** - http://192.168.1.100:8081/wallets.html
  - Expected: `v0.10.0 (BUILD 1769603933)`
  - Check: Footer shows correct build number
  - Previous broken build: 1769575984

- [ ] **apis.html** - http://192.168.1.100:8081/apis.html
  - Expected: `v0.10.0 (BUILD 1769603933)`
  - Check: Footer shows correct build number
  - Previous broken build: 1769575984

### 2. Test Waffle Menu Functionality
For each page, click the waffle menu (9 dots icon) and verify it opens correctly:

- [ ] **index.html**
  - Open: http://192.168.1.100:8081/
  - Click: Waffle menu button (top right)
  - Expected: Menu appears with 8 items (Dashboard, Manage Assets, APIs, Services, Security, Backup & Restore, NFT Wall, System Logs)
  - Previous status: ✅ Working

- [ ] **wallets.html**
  - Open: http://192.168.1.100:8081/wallets.html
  - Click: Waffle menu button
  - Expected: Menu appears with "Manage Assets" highlighted
  - Previous status: ❌ Broken (CSS class mismatch)

- [ ] **apis.html**
  - Open: http://192.168.1.100:8081/apis.html
  - Click: Waffle menu button
  - Expected: Menu appears with "APIs" highlighted
  - Previous status: ❌ Broken (CSS class mismatch)

- [ ] **services.html**
  - Open: http://192.168.1.100:8081/services.html
  - Click: Waffle menu button
  - Expected: Menu appears with "Services" highlighted
  - Previous status: ✅ Working

- [ ] **security.html**
  - Open: http://192.168.1.100:8081/security.html
  - Click: Waffle menu button
  - Expected: Menu appears with "Security" highlighted
  - Previous status: ✅ Working

- [ ] **backup.html**
  - Open: http://192.168.1.100:8081/backup.html
  - Click: Waffle menu button
  - Expected: Menu appears with "Backup & Restore" highlighted
  - Previous status: ✅ Working

- [ ] **nft-wall.html**
  - Open: http://192.168.1.100:8081/nft-wall.html
  - Click: Waffle menu button
  - Expected: Menu appears with "NFT Wall" highlighted
  - Previous status: ❌ Broken (Duplicate API_BASE declaration)

- [ ] **logs.html**
  - Open: http://192.168.1.100:8081/logs.html
  - Click: Waffle menu button
  - Expected: Menu appears with "System Logs" highlighted
  - Previous status: ✅ Working

### 3. Check Console for Errors
Open browser DevTools console (F12) and check for JavaScript errors:

- [ ] **wallets.html**
  - Expected: No "initializePrivacyMode is not defined" error
  - Expected: Waffle menu works without errors

- [ ] **apis.html**
  - Expected: No "initializePrivacyMode is not defined" error
  - Expected: Waffle menu works without errors

- [ ] **nft-wall.html**
  - Expected: No "Identifier 'API_BASE' has already been declared" error
  - Expected: No "toggleWaffleMenu is not defined" error
  - Expected: Waffle menu works without errors

### 4. Test Navigation Flow
Click through all waffle menu items to ensure navigation works:

- [ ] Start at index.html
- [ ] Click waffle menu → "Manage Assets" → Should navigate to wallets.html
- [ ] Click waffle menu → "APIs" → Should navigate to apis.html
- [ ] Click waffle menu → "Services" → Should navigate to services.html
- [ ] Click waffle menu → "Security" → Should navigate to security.html
- [ ] Click waffle menu → "Backup & Restore" → Should navigate to backup.html
- [ ] Click waffle menu → "NFT Wall" → Should navigate to nft-wall.html
- [ ] Click waffle menu → "System Logs" → Should navigate to logs.html
- [ ] Click waffle menu → "Dashboard" → Should navigate back to index.html

### 5. Test Menu Close Behavior
Verify the menu closes correctly:

- [ ] Open waffle menu → Click outside menu → Menu closes
- [ ] Open waffle menu → Click menu button again → Menu closes
- [ ] Open waffle menu → Click a menu item → Navigate to page and menu closes

## Deployment Issues (If Any)

### If Deployment Script Fails
Check:
1. SSH access to Unraid server
2. Docker daemon running on Unraid
3. Sufficient disk space on Unraid
4. Port 8081 not in use by another service

### If Waffle Menu Still Broken After Deployment
Possible causes:
1. Browser cache - Do hard refresh (Ctrl+F5 or Cmd+Shift+R)
2. Old files still deployed - Check build numbers in footer
3. Docker image not rebuilt - Verify container image date
4. Wrong files synced - Check file timestamps on server

### Rollback Procedure (If Needed)
If the deployment causes issues:
```bash
# SSH to Unraid
ssh root@192.168.1.100

# Stop current container
docker stop abct-dashboard
docker rm abct-dashboard

# Pull previous working image (if available)
docker run -d --name abct-dashboard [previous image]
```

## Success Criteria
✅ All pages accessible
✅ All waffle menus open correctly
✅ No JavaScript errors in console
✅ Build numbers match expected values
✅ Navigation between pages works

## Notes
- The main fix was changing `.waffle-menu-dropdown.show` to `.waffle-menu-dropdown.active` in the inline CSS of wallets.html and apis.html
- The JavaScript `toggleWaffleMenu()` function in app.js toggles the `.active` class, not `.show`
- All other pages use styles.css which already has the correct `.active` class
- nft-wall.html had a separate issue with duplicate `API_BASE` declaration that should also be fixed by this deployment
