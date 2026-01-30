# Docker Database Migration Guide

## Problem: "no such column: user_id" Error

If you're seeing this error when starting your Docker container:
```
sqlite3.OperationalError: no such column: user_id
ERROR: Application startup failed. Exiting.
```

This means your database was created with an older version of ABCT (before v0.12.0) and needs to be migrated to the multi-user schema.

## Solution: Run Database Migration

### Option 1: Run Migration Inside Docker Container (Recommended)

1. **Start the container** (it will fail, but that's okay):
   ```bash
   docker-compose up -d
   ```

2. **Copy the migration script into the container**:
   ```bash
   docker cp backend/migrate_to_multiuser.py abct:/app/backend/
   ```

3. **Run the migration**:
   ```bash
   docker exec -it abct python3 /app/backend/migrate_to_multiuser.py --db-path /app/data/portfolio.db
   ```

4. **Restart the container**:
   ```bash
   docker-compose restart
   ```

### Option 2: Migrate Database Locally Then Mount

If you're using a locally mounted database:

1. **Stop the container**:
   ```bash
   docker-compose down
   ```

2. **Run migration on your host machine**:
   ```bash
   cd /Users/chriscata/Documents/Claude-Projects/ABCT
   python3 backend/migrate_to_multiuser.py --db-path ./data/portfolio.db
   ```

3. **Start the container**:
   ```bash
   docker-compose up -d
   ```

### Option 3: Start Fresh (Loses Data)

If you don't have important data:

1. **Stop and remove container**:
   ```bash
   docker-compose down
   ```

2. **Delete the old database**:
   ```bash
   rm data/portfolio.db
   ```

3. **Start the container** (fresh database will be created):
   ```bash
   docker-compose up -d
   ```

## What the Migration Does

The migration script:
1. ✅ Creates a backup of your database
2. ✅ Creates users, sessions, and password_reset tables
3. ✅ Adds user_id column to all existing tables
4. ✅ Creates a default admin user (username: admin, password: admin)
5. ✅ Assigns all existing data to the default user

## After Migration

### Default Login Credentials
```
Username: admin
Password: admin
```

**⚠️ IMPORTANT**: Change the password immediately after first login!

### Verify Migration Worked

1. **Check container logs**:
   ```bash
   docker logs abct
   ```

   You should see:
   ```
   INFO: Application startup complete.
   INFO: Uvicorn running on http://0.0.0.0:8000
   ```

2. **Access the web interface**:
   - Navigate to http://localhost:8080 (or your configured port)
   - Login with admin/admin
   - Go to Settings → Change Password

## Troubleshooting

### "Module 'bcrypt' not found"

If the migration script fails with bcrypt error:

```bash
# Install bcrypt in the container
docker exec -it abct pip install bcrypt

# Try migration again
docker exec -it abct python3 /app/backend/migrate_to_multiuser.py --db-path /app/data/portfolio.db
```

### Container Still Won't Start

1. **Check if database is mounted correctly**:
   ```bash
   docker exec -it abct ls -la /app/data/
   ```

2. **Check database permissions**:
   ```bash
   docker exec -it abct chmod 664 /app/data/portfolio.db
   ```

3. **View detailed logs**:
   ```bash
   docker logs abct --tail 100
   ```

### Migration Creates Duplicate Data

If you run the migration multiple times, you might see duplicate users. To fix:

```bash
# Connect to database
docker exec -it abct sqlite3 /app/data/portfolio.db

# Check users
sqlite> SELECT * FROM users;

# Delete duplicate users (keep admin with id=1)
sqlite> DELETE FROM users WHERE id > 1;
sqlite> .quit
```

## Backup Recommendations

Before running migration:

1. **Manual backup**:
   ```bash
   cp data/portfolio.db data/portfolio_backup.db
   ```

2. **Export using ABCT backup feature** (if accessible):
   - Go to Settings → Backup & Restore
   - Export configuration
   - Save the JSON file

## Docker Compose Volume Configuration

Make sure your docker-compose.yml has the data directory mounted:

```yaml
volumes:
  - ./data:/app/data
```

This ensures your database persists across container restarts.

## Version Information

- **Required for**: Upgrading from ABCT < v0.12.0 to v0.12.0+
- **Migration script**: backend/migrate_to_multiuser.py
- **Database changes**: Adds multi-user support with user_id foreign keys

## Need Help?

1. Check the main logs: `docker logs abct`
2. Check migration backup: `ls -la data/portfolio_backup_*.db`
3. Report issue on GitHub with full error logs

---

Last Updated: 2026-01-30
ABCT Version: v0.12.0+
