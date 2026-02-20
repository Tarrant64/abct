# .env File Backup Guide

**Build:** 1769648168
**Feature:** Separate API Keys Export/Import

---

## Overview

API keys in ABCT are stored in **environment variables** (`.env` file), not in the database. This means the regular backup/restore feature doesn't include them.

This new feature adds a **separate, highly secure export** specifically for your API keys.

---

## 🔥 Security Warnings

**EXTREMELY SENSITIVE DATA:**
- This exports ALL your API keys in PLAIN TEXT
- Never commit to Git or version control
- Never share with anyone
- Never store in cloud storage (Dropbox, Google Drive, etc.)
- Delete immediately after use
- Store only in encrypted password manager

**Use ONLY for:**
- Migrating to a new server
- Disaster recovery (if stored securely)

---

## How to Export API Keys

### Step 1: Access Backup Page

Navigate to: `http://your-server:port/backup.html`

### Step 2: Find API Keys Section

Scroll to the **"API Keys Backup (.env File)"** section (orange warning box).

### Step 3: Export

1. Click **"Export API Keys (.env)"** button
2. **First confirmation**: Click OK on security warning
3. File downloads as `abct-env-YYYY-MM-DD-HHMMSS.txt`
4. **Second reminder**: Click OK on deletion reminder

### Step 4: Secure the File

**IMMEDIATELY:**
1. Open your password manager (1Password, Bitwarden, KeePass, etc.)
2. Create new secure note
3. Copy the file contents
4. **DELETE the downloaded file** from your downloads folder
5. Empty trash/recycle bin

---

## What Gets Exported

The export includes ALL environment variables from your `.env` file:

**Blockchain APIs:**
- BLOCKFROST_API_KEY (Cardano)
- TAPTOOLS_API_KEY (Cardano NFTs)
- CEXPLORER_API_KEY (Cardano Staking)
- MAESTRO_API_KEY (Cardano)
- ETHERSCAN_API_KEY (Ethereum)
- ALCHEMY_API_KEY (Multi-chain)
- HELIUS_API_KEY (Solana)

**Pricing APIs:**
- COINGECKO_API_KEY
- CMC_API_KEY

**Configuration:**
- NFT_SCHEDULER_ENABLED
- ABCT_REQUIRE_AUTH
- ABCT_ADMIN_USER
- ABCT_ADMIN_PASSWORD
- All other environment variables

---

## How to Import API Keys

### On New Server (Local Development)

1. Copy API keys from your password manager
2. Create `.env` file in project root:
   ```bash
   cd /Users/you/ABCT
   nano .env
   ```
3. Paste the API keys
4. Save and exit (Ctrl+X, Y, Enter)
5. Restart ABCT:
   ```bash
   ./stop.sh
   ./run.sh
   ```

### On Docker Deployment

**Option 1: Environment Variables (Recommended)**

Set each key when starting the container:

```bash
docker run -d \
  --name abct-dashboard \
  -p 8081:80 \
  -v /path/to/data:/app/data \
  -e "BLOCKFROST_API_KEY=mainnetXXXXXXXXX" \
  -e "TAPTOOLS_API_KEY=your_key_here" \
  -e "CEXPLORER_API_KEY=your_key_here" \
  -e "ETHERSCAN_API_KEY=your_key_here" \
  -e "ALCHEMY_API_KEY=your_key_here" \
  -e "HELIUS_API_KEY=your_key_here" \
  -e "COINGECKO_API_KEY=your_key_here" \
  -e "ABCT_REQUIRE_AUTH=false" \
  abct-dashboard:latest
```

**Option 2: docker-compose.yml**

Create/edit `docker-compose.yml`:

```yaml
version: '3.8'
services:
  abct-dashboard:
    image: abct-dashboard:latest
    environment:
      - BLOCKFROST_API_KEY=mainnetXXXXXXXXX
      - TAPTOOLS_API_KEY=your_key_here
      - CEXPLORER_API_KEY=your_key_here
      # ... etc
```

**Option 3: .env File in Docker Context**

1. SSH to your Docker host
2. Create `.env` file in `/mnt/user/appdata/ABCT/` (or wherever your Docker context is)
3. Paste API keys
4. Update docker-compose.yml to use `env_file`:
   ```yaml
   services:
     abct-dashboard:
       env_file: .env
   ```

---

## Verification

After importing, verify API keys are loaded:

### Local Development
```bash
# Check environment
source .env
echo $BLOCKFROST_API_KEY
# Should show your key

# Check ABCT recognizes it
curl http://127.0.0.1:8000/api/status | jq '.apis'
```

### Docker
```bash
# Check container environment
docker exec abct-dashboard printenv BLOCKFROST_API_KEY
# Should show your key

# Check ABCT recognizes it
curl http://your-server:8081/api/status | jq '.apis'
```

### Via Web UI
1. Navigate to `/apis.html`
2. Check **"API Status"** section
3. Green checkmarks = API keys loaded correctly
4. Red X = API key missing or invalid

---

## Troubleshooting

### "Export failed: .env file not found"

**Cause:** You're running ABCT with environment variables directly (Docker), not using a `.env` file.

**Solution:** API keys are already in your Docker environment variables. No need to export - just document which keys you set.

### "Import doesn't work / Keys not recognized"

**Cause:** The import endpoint only *previews* the keys, it doesn't write them to disk (for security).

**Solution:** You must manually create the `.env` file or set environment variables as shown above.

### "Keys work locally but not in Docker"

**Cause:** Docker doesn't automatically read `.env` files from the filesystem.

**Solution:** Pass keys via `-e` flags or `docker-compose.yml` as shown above.

---

## Security Best Practices

### DO:
✅ Store in password manager
✅ Encrypt with strong password
✅ Use for server migration only
✅ Delete files immediately after use
✅ Verify file is deleted from trash

### DON'T:
❌ Email to yourself
❌ Store in cloud drives
❌ Commit to Git
❌ Share with others
❌ Leave in downloads folder
❌ Save on USB drives (unless encrypted)

---

## Example Migration Workflow

### Migrating from Local to Docker

1. **On Local Mac:**
   ```bash
   # Navigate to backup page
   open http://127.0.0.1:8000/backup.html

   # Export API keys
   # Click "Export API Keys (.env)"
   # Save to password manager
   # DELETE downloaded file
   ```

2. **On New Docker Server:**
   ```bash
   # SSH to server
   ssh root@<YOUR_SERVER_IP>

   # Copy API keys from password manager
   # Edit docker run command with -e flags
   # Or create docker-compose.yml with environment section

   # Start container
   docker-compose up -d

   # Verify
   docker exec abct-dashboard printenv | grep API_KEY
   ```

3. **Verify in Web UI:**
   ```
   http://<YOUR_SERVER_IP>:8081/apis.html
   # Check all APIs show green checkmarks
   ```

---

## Additional Notes

- The regular backup (`/backup/export`) **does NOT include API keys**
- Use regular backup for: wallets, settings, NFT collections
- Use .env backup for: API keys only
- Both are needed for complete disaster recovery
- Keep both in separate secure locations

---

## Support

If you have issues:
1. Check Docker logs: `docker logs abct-dashboard`
2. Check API status: `/apis.html`
3. Verify environment: `docker exec abct-dashboard printenv`
4. Check `.env` file exists and has correct format

---

**Last Updated:** January 2026
**Build:** 1769648168
