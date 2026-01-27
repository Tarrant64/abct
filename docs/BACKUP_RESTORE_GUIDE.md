# Backup & Restore Guide

## Overview

The Backup & Restore feature allows you to export your entire ABCT configuration to a single JSON file and import it later. This is essential for:

- **Migration**: Moving ABCT to a new server or computer
- **Disaster Recovery**: Recovering from data loss or corruption
- **Testing**: Safely trying configuration changes (backup first!)
- **Cloning**: Setting up multiple ABCT instances with the same configuration
- **Regular Backups**: Part of your data protection strategy

## What Gets Backed Up?

### ✅ Included in Backup

The backup includes all user-created configuration and data:

| Table | Description | Sensitive? |
|-------|-------------|------------|
| `wallets` | All wallet addresses and labels | No |
| `api_settings` | API keys and configuration | **Yes** 🔒 |
| `security_settings` | SSL/HTTPS configuration (paths only) | **Yes** 🔒 |
| `custom_tokens` | Manually added custom tokens | No |
| `token_metadata` | Token metadata and tracking settings | No |
| `nft_scheduler_collections` | NFT collections being tracked | No |
| `api_rate_limits` | Custom API rate limits | No |

### ❌ Excluded from Backup

These tables contain regenerable data or temporary state:

- `portfolio_snapshots` - Historical portfolio data (too large, can regenerate)
- `nft_floor_prices` - NFT price history (regenerated from APIs)
- `cache` - Temporary cached API responses
- `balances` - Wallet balances (refreshed from blockchain)
- `native_assets` - Assets in wallets (refreshed from blockchain)
- `api_usage` - API call usage logs
- `nft_scheduler_state` - Runtime scheduler state
- `nft_scheduler_api_calls` - Scheduler API call logs

## Export Configuration

### Via Web UI

1. Navigate to **Backup & Restore** from the waffle menu (📦 icon)
2. Review the "Current Data Stats" to see what you have
3. Select export options:
   - **Include API Keys**: Include your API keys (⚠️ store securely!)
   - **Include Security Settings**: Include SSL/cert configuration (usually not needed)
   - **Include Custom Tokens**: Include manually added tokens (recommended)
   - **Include NFT Collections**: Include tracked NFT collections (recommended)
4. Click **"Download Backup"**
5. Save the file securely (named `abct-backup-YYYY-MM-DD-HHMMSS.json`)

### Via API

```bash
# Export with all options
curl -X POST http://localhost:8000/api/backup/export \
  -H "Content-Type: application/json" \
  -d '{
    "include_api_keys": true,
    "include_security_settings": false,
    "include_custom_tokens": true,
    "include_nft_collections": true
  }' \
  -o abct-backup.json

# Export without API keys (safer for sharing)
curl -X POST http://localhost:8000/api/backup/export \
  -H "Content-Type: application/json" \
  -d '{
    "include_api_keys": false,
    "include_security_settings": false,
    "include_custom_tokens": true,
    "include_nft_collections": true
  }' \
  -o abct-backup-no-keys.json
```

## Import Configuration

### ⚠️ Important: Always Preview First!

Never import a backup without previewing it first. The preview shows:
- What data will be imported
- What will be overwritten
- Version compatibility
- Warnings about sensitive data

### Via Web UI

1. Navigate to **Backup & Restore** page
2. Click the upload area or drag-and-drop your backup JSON file
3. Select import mode:
   - **🔄 Merge Mode** (Recommended): Keeps existing data, adds/updates from backup
   - **🔥 Replace Mode** (Destructive): Deletes ALL data first, then imports backup
4. Configure import options:
   - **Skip API Keys**: Don't import API keys (if you want to keep current ones)
   - **Skip Security Settings**: Don't import SSL settings (recommended unless migrating servers)
5. Click **"Preview Import"** to validate the backup
6. Review the preview carefully:
   - Check backup version compatibility
   - Review warnings
   - Verify table counts
7. If everything looks good, click **"Import Configuration"**
8. Confirm the action (especially important for Replace mode!)

### Via API

#### Preview First
```bash
# Preview the import (dry-run)
curl -X POST http://localhost:8000/api/backup/preview \
  -H "Content-Type: application/json" \
  -d "{
    \"mode\": \"merge\",
    \"skip_api_keys\": false,
    \"skip_security_settings\": true,
    \"backup_data\": $(cat abct-backup.json | jq -c .)
  }" | jq .
```

#### Then Import
```bash
# Import in merge mode (safe)
curl -X POST http://localhost:8000/api/backup/import \
  -H "Content-Type: application/json" \
  -d "{
    \"mode\": \"merge\",
    \"skip_api_keys\": false,
    \"skip_security_settings\": true,
    \"backup_data\": $(cat abct-backup.json | jq -c .)
  }" | jq .

# Import in replace mode (destructive)
curl -X POST http://localhost:8000/api/backup/import \
  -H "Content-Type: application/json" \
  -d "{
    \"mode\": \"replace\",
    \"skip_api_keys\": false,
    \"skip_security_settings\": true,
    \"backup_data\": $(cat abct-backup.json | jq -c .)
  }" | jq .
```

## Import Modes

### 🔄 Merge Mode (Recommended)

**How it works:**
- Keeps all existing data
- Adds new records from backup
- Updates existing records if they conflict (by ID)
- Safe and reversible (just backup before merging)

**Use when:**
- Adding wallets from another ABCT instance
- Updating configuration while keeping existing data
- Recovering specific settings without losing current data
- Not sure if Replace mode is needed (merge is safer!)

**Example:**
- Current: 3 wallets, 2 API keys
- Backup: 5 wallets, 3 API keys
- After merge: 5 wallets (all unique), 3 API keys (updated)

### 🔥 Replace Mode (Destructive)

**How it works:**
- **Deletes ALL existing data first** (all tables cleared)
- Then imports everything from backup
- **CANNOT be undone** - data is permanently deleted
- Requires explicit confirmation

**Use when:**
- Restoring to a fresh ABCT installation
- Completely replacing current configuration
- You've made a backup of current state first
- You're absolutely sure you want to start fresh

**⚠️ Warning:**
- ALL wallets will be deleted
- ALL settings will be deleted
- ALL custom tokens will be deleted
- This is irreversible!

## Security Best Practices

### 🔒 API Keys in Backups

**If including API keys:**
1. ✅ Store backup files in encrypted storage
2. ✅ Never share backup files publicly
3. ✅ Use strong passwords for file encryption
4. ✅ Delete old backups when no longer needed
5. ✅ Treat backup files like passwords
6. ❌ Never commit backup files to git
7. ❌ Never upload to public cloud without encryption
8. ❌ Never share via email or messaging apps

**If excluding API keys:**
1. Safer for sharing configuration
2. Can post on GitHub or share with others
3. Recipient must add API keys manually after import
4. Good for open-source setups or documentation

### 📋 Backup File Format

The backup file is a JSON document with this structure:

```json
{
  "format_version": "1.0.0",
  "abct_version": "0.10.0",
  "export_date": "2026-01-26T12:00:00",
  "export_timestamp": 1706270400,
  "options": {
    "include_api_keys": true,
    "include_security_settings": false,
    "include_custom_tokens": true,
    "include_nft_collections": true
  },
  "data": {
    "wallets": [...],
    "api_settings": [...],
    "custom_tokens": [...],
    "token_metadata": [...],
    "nft_scheduler_collections": [...],
    "api_rate_limits": [...]
  },
  "warnings": [
    "This backup contains 3 API key(s)..."
  ]
}
```

### 🔐 Optional: Encrypt Your Backup

While ABCT doesn't provide built-in encryption, you can encrypt backups using standard tools:

#### Using GPG
```bash
# Encrypt backup
gpg --symmetric --cipher-algo AES256 abct-backup.json

# Decrypt backup
gpg --decrypt abct-backup.json.gpg > abct-backup.json
```

#### Using OpenSSL
```bash
# Encrypt backup
openssl enc -aes-256-cbc -salt -in abct-backup.json -out abct-backup.json.enc

# Decrypt backup
openssl enc -aes-256-cbc -d -in abct-backup.json.enc -out abct-backup.json
```

## Common Scenarios

### Scenario 1: Regular Backup Schedule

**Goal**: Weekly backups for disaster recovery

```bash
#!/bin/bash
# backup-abct.sh

DATE=$(date +%Y-%m-%d)
BACKUP_DIR="$HOME/abct-backups"
mkdir -p "$BACKUP_DIR"

curl -X POST http://localhost:8000/api/backup/export \
  -H "Content-Type: application/json" \
  -d '{"include_api_keys": true, "include_security_settings": false, "include_custom_tokens": true, "include_nft_collections": true}' \
  -o "$BACKUP_DIR/abct-backup-$DATE.json"

# Keep only last 4 backups
cd "$BACKUP_DIR"
ls -t abct-backup-*.json | tail -n +5 | xargs rm -f

echo "Backup saved to $BACKUP_DIR/abct-backup-$DATE.json"
```

Add to crontab for weekly execution:
```bash
# Run every Sunday at 2 AM
0 2 * * 0 /path/to/backup-abct.sh
```

### Scenario 2: Migrate to New Server

**Goal**: Move ABCT to a new machine

On old server:
```bash
# Export with all settings
curl -X POST http://localhost:8000/api/backup/export \
  -H "Content-Type: application/json" \
  -d '{"include_api_keys": true, "include_security_settings": true, "include_custom_tokens": true, "include_nft_collections": true}' \
  -o abct-full-backup.json

# Copy file to new server
scp abct-full-backup.json user@newserver:/tmp/
```

On new server:
```bash
# Install ABCT first, then import
curl -X POST http://localhost:8000/api/backup/import \
  -H "Content-Type: application/json" \
  -d "{\"mode\": \"replace\", \"skip_api_keys\": false, \"skip_security_settings\": false, \"backup_data\": $(cat /tmp/abct-full-backup.json | jq -c .)}"
```

### Scenario 3: Share Configuration (No Secrets)

**Goal**: Share wallet setup with a colleague (without API keys)

```bash
# Export without sensitive data
curl -X POST http://localhost:8000/api/backup/export \
  -H "Content-Type: application/json" \
  -d '{"include_api_keys": false, "include_security_settings": false, "include_custom_tokens": true, "include_nft_collections": true}' \
  -o abct-config-public.json

# Safe to share via email, GitHub, etc.
# Recipient imports and adds their own API keys
```

### Scenario 4: Test Configuration Changes

**Goal**: Try new settings, revert if needed

```bash
# 1. Backup current state
curl -X POST http://localhost:8000/api/backup/export \
  -H "Content-Type: application/json" \
  -d '{"include_api_keys": true, "include_security_settings": true, "include_custom_tokens": true, "include_nft_collections": true}' \
  -o abct-before-changes.json

# 2. Make changes in ABCT UI...

# 3. If something breaks, restore from backup
curl -X POST http://localhost:8000/api/backup/import \
  -H "Content-Type: application/json" \
  -d "{\"mode\": \"replace\", \"skip_api_keys\": false, \"skip_security_settings\": false, \"backup_data\": $(cat abct-before-changes.json | jq -c .)}"
```

## Troubleshooting

### "Invalid backup file" Error

**Cause**: Corrupted or improperly formatted JSON

**Solution**:
1. Verify the file is valid JSON: `cat backup.json | jq .`
2. Check file wasn't truncated during download
3. Re-download or re-export the backup

### "Version incompatible" Warning

**Cause**: Backup created with different ABCT version

**Solution**:
1. Check backup format version vs current ABCT version
2. Upgrade/downgrade ABCT to match backup version
3. For minor version differences, import may still work (check preview)

### Import Fails Midway

**Cause**: Database error or invalid data

**Solution**:
1. Check ABCT logs: `/api/logs`
2. Ensure database isn't corrupted: restart ABCT
3. Try import again (database rolled back)
4. If persistent, try merge mode instead of replace

### "Preview shows 0 records" Error

**Cause**: Backup file contains empty tables

**Solution**:
1. Check original ABCT instance had data before export
2. Verify export options included the data you wanted
3. Re-export with different options if needed

### Cannot Import API Keys

**Cause**: API keys may have invalid format

**Solution**:
1. Use "Skip API Keys" option on import
2. Add API keys manually via APIs page after import
3. Check backup file format matches expected structure

## API Reference

### GET /api/backup/info

Get information about current data status.

**Response:**
```json
{
  "backup_format_version": "1.0.0",
  "abct_version": "0.10.0",
  "tables": {
    "wallets": {
      "description": "All wallet addresses and labels",
      "sensitive": false,
      "required": true,
      "record_count": 5,
      "has_data": true
    },
    "api_settings": {
      "description": "API keys and configuration",
      "sensitive": true,
      "required": false,
      "record_count": 3,
      "has_data": true
    }
  }
}
```

### POST /api/backup/export

Export configuration to JSON backup file.

**Request:**
```json
{
  "include_api_keys": true,
  "include_security_settings": false,
  "include_custom_tokens": true,
  "include_nft_collections": true
}
```

**Response:** JSON file download

### POST /api/backup/preview

Preview import (dry-run validation).

**Request:**
```json
{
  "mode": "merge",
  "skip_api_keys": false,
  "skip_security_settings": true,
  "backup_data": "{...backup JSON content...}"
}
```

**Response:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": ["Will merge 5 wallet(s)"],
  "summary": {
    "backup_info": {
      "format_version": "1.0.0",
      "abct_version": "0.10.0",
      "export_date": "2026-01-26T12:00:00",
      "age_days": 0
    },
    "tables": {
      "wallets": {
        "count": 5,
        "action": "merge",
        "description": "All wallet addresses and labels"
      }
    }
  },
  "compatible": true
}
```

### POST /api/backup/import

Import configuration from backup file.

**Request:**
```json
{
  "mode": "merge",
  "skip_api_keys": false,
  "skip_security_settings": true,
  "backup_data": "{...backup JSON content...}"
}
```

**Response:**
```json
{
  "started_at": "2026-01-26T12:00:00",
  "mode": "merge",
  "tables_processed": {
    "wallets": {
      "status": "success",
      "imported": 5,
      "skipped": 0,
      "total": 5
    }
  },
  "warnings": [],
  "completed_at": "2026-01-26T12:00:05",
  "success": true
}
```

## Support

If you encounter issues with backup/restore:

1. Check the ABCT logs: Navigate to Logs page or `/api/logs`
2. Verify backup file integrity: `cat backup.json | jq .`
3. Try preview before import to catch errors early
4. Start with merge mode before trying replace mode
5. Keep backups in multiple locations for redundancy

For additional help, refer to the main ABCT documentation or file an issue on GitHub.
