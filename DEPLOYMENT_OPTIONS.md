# ABCT Docker Deployment Options

Three deployment scripts for different use cases:

## 1. Regular Update (update-unraid.sh) ⚡
**Use when**: Making incremental changes, want to preserve database and settings

```bash
./abct-docker/update-unraid.sh 192.168.50.225 8081
```

**What it does**:
- Syncs local files to unRAID
- Preserves database (mounted volume)
- Saves and restores API keys
- Rebuilds container with new code
- Runs database migrations

**Preserves**:
- ✅ Database (wallets, settings, users)
- ✅ API keys
- ✅ User preferences

---

## 2. Clean Deploy (clean-deploy-unraid.sh) 🧹
**Use when**: Testing from scratch, resetting everything

```bash
./abct-docker/clean-deploy-unraid.sh 192.168.50.225 8081
```

**What it does**:
- Syncs local files to unRAID
- **Deletes database** (fresh start!)
- Backs up old database to timestamped folder
- Option to preserve API keys or start fresh
- Rebuilds container
- Initializes empty database

**Interactive prompts**:
1. Preserve API keys? (yes/no)
2. Confirm clean deployment (type 'yes')

**Result**: Brand new instance, like first-time install

---

## 3. Deploy from Git (deploy-from-git.sh) 🚀
**Use when**: Want to pull directly from GitHub, ensure code matches repository

```bash
./abct-docker/deploy-from-git.sh 192.168.50.225 8081 [branch]
```

**What it does**:
- **Clones from GitHub** (not local files!)
- Removes old code directory on unRAID
- Pulls specified branch (default: main)
- Preserves database
- Saves and restores API keys
- Rebuilds container

**Advantages**:
- ✅ Guarantees code matches GitHub
- ✅ No need to push from local first
- ✅ Can deploy specific branches for testing
- ✅ Clean slate for code, keeps data

**Example with branch**:
```bash
./abct-docker/deploy-from-git.sh 192.168.50.225 8081 feature/new-dashboard
```

---

## Comparison Table

| Feature | update-unraid | clean-deploy | deploy-from-git |
|---------|---------------|--------------|-----------------|
| **Source** | Local files | Local files | GitHub |
| **Database** | Preserved | **Deleted** | Preserved |
| **API Keys** | Preserved | Optional | Preserved |
| **Use Case** | Regular updates | Fresh start | Pull from repo |
| **Speed** | Fast (rsync) | Medium | Slower (git clone) |
| **Safety** | Safe | Destructive | Safe |

---

## Recommended Workflows

### Development Testing (recommended for you)
```bash
# 1. Make code changes locally
# 2. Test on localhost first
# 3. Commit and push to GitHub
git add .
git commit -m "fix: SOL value calculation"
git push

# 4. Deploy from Git to unRAID
./abct-docker/deploy-from-git.sh 192.168.50.225 8081
```

**Why this is best**:
- Ensures unRAID runs exact same code as GitHub
- Local changes can't accidentally differ from deployed code
- Can roll back by deploying older commits/branches
- No sync issues between local and deployed

### Quick Iteration (current method)
```bash
# 1. Make changes locally
# 2. Sync and deploy immediately
./abct-docker/update-unraid.sh 192.168.50.225 8081
```

**Pros**: Fast iteration
**Cons**: Local and deployed code can drift from GitHub

### Fresh Testing Environment
```bash
# Clean deploy with API keys preserved
./abct-docker/clean-deploy-unraid.sh 192.168.50.225 8081
# Choose: Preserve API keys
```

**Result**: Empty database, no wallets, ready to test from scratch

---

## After Deployment

### Check Status
```bash
ssh root@192.168.50.225 "docker logs abct-dashboard --tail 50"
```

### Verify Version
```bash
curl -s http://192.168.50.225:8081/ | grep BUILD
```

### Health Check
```bash
curl http://192.168.50.225:8081/health
```

### Access Container
```bash
ssh root@192.168.50.225 "docker exec -it abct-dashboard bash"
```

### View Database
```bash
ssh root@192.168.50.225 "docker exec abct-dashboard sqlite3 /app/data/portfolio.db 'SELECT * FROM users;'"
```

---

## Database Location

**On unRAID Host**:
- Current: `/mnt/user/appdata/abct-dashboard/portfolio.db`
- Backups: `/mnt/user/appdata/abct-dashboard_backup_YYYYMMDD_HHMMSS/`

**Inside Container**:
- Path: `/app/data/portfolio.db`
- Mounted from host (persists across rebuilds)

---

## Resetting Database Without Rebuild

If you just want to clear the database without rebuilding:

```bash
ssh root@192.168.50.225

# Stop container
docker stop abct-dashboard

# Delete database
rm /mnt/user/appdata/abct-dashboard/portfolio.db

# Start container (will auto-create new DB)
docker start abct-dashboard
```

---

## Git-Based Workflow (Recommended Going Forward)

### Setup
1. Always commit and push changes to GitHub first
2. Use `deploy-from-git.sh` for unRAID deployments
3. Keep local and unRAID in sync with repository

### Benefits
- ✅ Single source of truth (GitHub)
- ✅ Easy rollbacks (deploy older commits)
- ✅ Branch testing (test features before merging)
- ✅ No "oops, forgot to push" issues
- ✅ Deployment history matches git history

### Example Flow
```bash
# Local development
vim frontend/js/app.js
git add .
git commit -m "fix: SOL value calculation"
git push

# Deploy to unRAID
./abct-docker/deploy-from-git.sh 192.168.50.225 8081

# Test on http://192.168.50.225:8081

# If issues, rollback to previous commit
git log --oneline  # Find previous commit hash
./abct-docker/deploy-from-git.sh 192.168.50.225 8081 <commit-hash>
```

---

## Current Status

**Your fixes deployed**:
- ✅ Copy button HTTP fallback
- ✅ SOL value calculation (includes tokens)
- ✅ Build version: 1770248608

**To deploy to unRAID**:
```bash
./abct-docker/deploy-from-git.sh 192.168.50.225 8081
```

This will pull the latest code from GitHub main branch with all your fixes.

---

## Notes

- All scripts use SSH connection multiplexing (only 1 password prompt)
- API keys are always saved before container stops
- Database migrations run automatically after deployment
- Health checks ensure service is running before completing
- Old images are cleaned up to prevent orphans
