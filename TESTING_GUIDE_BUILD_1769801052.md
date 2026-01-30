# 🎯 Testing Guide - Build 1769801052

## ⚠️ CRITICAL: Verify Build Number First!

**YOU MUST SEE THIS BUILD NUMBER**: `v0.12.0 (BUILD 1769801052)`

If you see any other build number, the fixes are NOT loaded. Follow the cache clearing steps below.

---

## 🧹 Clear Browser Cache (DO THIS FIRST!)

### Method 1: Hard Refresh (Recommended)
1. Open http://localhost:8000
2. Press **Cmd+Shift+R** (Mac) or **Ctrl+Shift+R** (Windows)
3. Check footer - must say: **BUILD 1769801052**

### Method 2: Clear Site Data (If hard refresh doesn't work)
**Chrome/Edge**:
1. Open DevTools (F12)
2. Right-click on the refresh button
3. Click "Empty Cache and Hard Reload"
4. Close DevTools
5. Check footer: **BUILD 1769801052**

**Firefox**:
1. Press Cmd+Shift+Delete
2. Select "Cache"
3. Select "Last Hour"
4. Click "Clear Now"
5. Refresh page (Cmd+R)
6. Check footer: **BUILD 1769801052**

### Method 3: Nuclear Option (If nothing else works)
1. Close all browser windows
2. Open browser
3. Go to Settings → Privacy → Clear browsing data
4. Select "Cached images and files" only
5. Select "All time"
6. Click "Clear data"
7. Restart browser
8. Go to http://localhost:8000
9. Check footer: **BUILD 1769801052**

---

## 🧪 Test 1: Verify Build Number

**Location**: Look at the bottom of any page

**Expected**: `Phase 1 | v0.12.0 (BUILD 1769801052)`

**If you see**: `BUILD 1769800723` or `BUILD 1769740718` → Old build, clear cache again

---

## 🧪 Test 2: Wallets Page - Button Functionality

### Step 1: Navigate to Wallets Page
1. Click "Wallets" in the navigation menu
2. Check footer: **BUILD 1769801052**

### Step 2: Locate Your Wallets
You should see two types of wallet displays:

**A. Cardano Stake Key Groups** (if you have Cardano wallets):
- Blue "cardano" badge
- `stake1u...` address display
- Summary line showing: wallet count, total ADA, token count
- Expand arrow icon (▶)

**B. Individual Wallets** (non-Cardano or enterprise):
- Blockchain badge (bitcoin, ethereum, solana, etc.)
- Wallet address (truncated)
- Balance amount
- **Edit** and **Delete** buttons on the right

### Step 3: Test Individual Wallet Buttons
**For each individual wallet you should see**:
1. **Edit button** (gray, on the right side)
   - Click it
   - Should open a modal to edit wallet label
   - Type a new label
   - Click Save
   - Modal should close and label should update

2. **Delete button** (red, next to Edit)
   - Click it
   - Should show confirmation dialog
   - Click Cancel to test (don't actually delete yet)

### Step 4: Test Stake Key Groups (Cardano only)
**If you have Cardano wallets grouped by stake key**:

1. **Find a stake key group** - looks like:
   ```
   ▶ cardano stake1u...xyz  2 wallets  1,500 ADA  25 tokens
   ```

2. **Click anywhere on the header** (the whole line)
   - Should expand to show individual wallets underneath
   - Icon should rotate from ▶ to ▼
   - Wallets slide down with smooth animation

3. **Click the header again**
   - Should collapse back
   - Icon rotates back to ▶
   - Wallets slide up and hide

4. **Each wallet under the stake key should have**:
   - Wallet address
   - Balance (ADA amount)
   - Token count badge (if wallet has tokens)
   - **Edit** and **Delete** buttons

### Step 5: Test Token Count Badge
**If a wallet shows a token badge** (e.g., "5 tokens ▼"):

1. **Click on the token badge**
   - Should expand to show list of individual tokens
   - Each token shows name and quantity
   - Displays in a gray container under the wallet

2. **Click the badge again**
   - Should collapse and hide the token list

---

## 🧪 Test 3: NFT Page

### Step 1: Navigate to NFT Page
1. Click "NFTs" in navigation
2. Check footer: **BUILD 1769801052**

### Step 2: Wait for NFTs to Load
- **First load**: May take 30-60 seconds
- You should see a loading indicator
- **Expected**: 279 NFTs should display

### Step 3: Verify NFT Display
Each NFT card should show:
- NFT image (if available)
- Asset name
- Collection name
- Floor price (if available)
- Wallet it's in

### Step 4: Check Browser Console
1. Open DevTools (F12)
2. Go to Console tab
3. Should NOT see any errors like:
   - "AttributeError"
   - "500 Internal Server Error"
   - "Failed to load resource: 401"

4. Look for success messages like:
   - "Loaded X NFTs"
   - "Fetching collection data"

---

## 🧪 Test 4: Dashboard Portfolio Summary

### Step 1: Go to Dashboard
1. Click "Dashboard" or "Home"
2. Check footer: **BUILD 1769801052**

### Step 2: Verify Balance Display
**Self-Custody Assets section**:
- Should show Cardano, Bitcoin, Ethereum cards
- Each card should display:
  - Blockchain name
  - ADA/BTC/ETH amount (NOT 0.00)
  - USD value
  - Wallet count
  - Token/asset count

### Step 3: Test Refresh Balances
1. Click "Refresh Balances" button
2. Wait 10-30 seconds
3. Balances should update
4. Check that ADA/BTC/ETH amounts change (if you've made transactions)

---

## ✅ Success Criteria

### Wallets Page ✅
- [ ] Build shows **1769801052**
- [ ] Edit buttons are visible and clickable
- [ ] Delete buttons are visible and clickable
- [ ] Edit modal opens when clicking Edit
- [ ] Stake key groups expand/collapse on click (Cardano)
- [ ] Expand icon rotates (▶ to ▼)
- [ ] Token badges expand to show asset lists
- [ ] Hover effects work (background changes)

### NFT Page ✅
- [ ] Build shows **1769801052**
- [ ] NFTs display (279 total expected)
- [ ] Collection names show
- [ ] Floor prices display where available
- [ ] No console errors
- [ ] No 401 or 500 errors

### Dashboard ✅
- [ ] Build shows **1769801052**
- [ ] Balances show actual amounts (not 0.00)
- [ ] Refresh Balances works
- [ ] Portfolio summary displays correctly

---

## ❌ Known Issues to Watch For

### Issue 1: Old Build Cached
**Symptom**: Build still shows 1769800723 or 1769740718
**Fix**: Clear cache more aggressively (Method 2 or 3)

### Issue 2: Buttons Still Not Visible
**Symptom**: Can't see Edit/Delete buttons
**Possible causes**:
- Cache not cleared
- CSS file not loading
- Browser dev tools showing 304 (cached) for styles.css

**Fix**:
1. Open DevTools (F12)
2. Go to Network tab
3. Refresh page
4. Look for "styles.css"
5. Should show "200" status (not "304")
6. If showing "304", disable cache in DevTools:
   - Check "Disable cache" checkbox in Network tab
   - Refresh page again

### Issue 3: NFTs Not Loading
**Symptom**: NFT page shows "Loading..." forever or "0 NFTs"
**Check**:
1. Open DevTools Console
2. Look for errors
3. Check Network tab for failed requests to `/nfts`

**If you see 401 Unauthorized**:
- Your session expired
- Log out and log back in
- Try NFT page again

---

## 🐛 Reporting Issues

If tests fail, please provide:

1. **Build number you see** (from footer)
2. **Which test failed** (Wallets/NFT/Dashboard)
3. **Browser console errors** (F12 → Console tab)
4. **Screenshot** if possible
5. **Network tab errors** (F12 → Network tab, filter by "XHR")

---

## 📊 What Was Fixed in This Build

### Build 1769801052 Changes:
1. ✅ Added missing CSS for wallet-actions (Edit/Delete buttons)
2. ✅ Added missing CSS for wallet-assets-container (token lists)
3. ✅ Fixed NFT service method error (_get_floor_price_from_db)
4. ✅ Added stake group expand/collapse CSS
5. ✅ Fixed token count badge styling and functionality
6. ✅ Cleared stale NFT cache

### Previous Builds (Should Not See These):
- 1769800723: Added stake group CSS only
- 1769740718: Balance fixes (old)

---

**Current Server**: Running on http://localhost:8000 (PID: 76720)
**Required Build**: v0.12.0 (BUILD 1769801052)
**Testing Date**: 2026-01-30

Good luck testing! 🚀
