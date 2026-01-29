# Password Reset Guide

## Forgot Your Password?

This guide explains how to reset your ABCT admin password if you've forgotten it or need to change it for security reasons.

## Prerequisites

- Access to the server/machine running ABCT (SSH, terminal, or Docker access)
- Python 3.8+ with bcrypt library installed

## Reset Methods

### Local Development

If you're running ABCT locally on your machine:

1. **Stop the ABCT server** (if running):
   ```bash
   # Press Ctrl+C in the terminal running ABCT
   # Or run:
   ./stop.sh
   ```

2. **Navigate to the ABCT directory**:
   ```bash
   cd /path/to/ABCT
   ```

3. **Run the password reset script**:
   ```bash
   python scripts/password_reset.py
   ```

4. **Follow the prompts**:
   - Enter the username to reset (default: `admin`)
   - Enter your new password
   - Confirm your new password

5. **Restart the ABCT server**:
   ```bash
   ./run.sh
   ```

6. **Login with your new password** at http://127.0.0.1:8000/login.html

### Docker Deployment

If you're running ABCT in a Docker container:

1. **Access your Docker container**:
   ```bash
   docker exec -it abct-dashboard bash
   ```

2. **Run the password reset script**:
   ```bash
   python scripts/password_reset.py
   ```

3. **Follow the prompts**:
   - Enter the username to reset (default: `admin`)
   - Enter your new password
   - Confirm your new password

4. **Exit the container**:
   ```bash
   exit
   ```

5. **No restart needed** - changes take effect immediately

6. **Login with your new password** at your ABCT URL

### Using Environment Variable (Alternative)

You can also set the admin password via environment variable:

1. **Edit your `.env` file**:
   ```bash
   nano .env
   ```

2. **Add or update the password variable**:
   ```
   ABCT_ADMIN_PASSWORD=your_new_secure_password
   ```

3. **Restart ABCT** for changes to take effect

**Note**: If a password exists in the database, it takes precedence over the environment variable. Use the password reset script for database passwords.

## Password Requirements

### Minimum Requirements
- **Minimum length**: 8 characters
- **Must contain**: At least one letter

### Recommended Best Practices
- Mix of uppercase and lowercase letters
- Include numbers
- Include special characters (!@#$%^&*)
- Avoid common passwords or dictionary words
- Don't reuse passwords from other accounts
- Use a password manager

### Example Strong Passwords
- `Crypto!Tracker2026`
- `B3tt3r-P@ssw0rd!`
- `Satoshi#Bitcoin$42`

## Security Notes

### Password Storage
- Passwords are stored **hashed** using bcrypt
- The original password cannot be recovered
- Bcrypt includes salt to prevent rainbow table attacks
- Hash computation is deliberately slow to prevent brute-force

### Default Password
- Default username: `admin`
- Default password: `satoshi`
- **IMPORTANT**: Change the default password immediately after first login
- The default password is documented and publicly known

### Access Control
- The password reset script requires **local or SSH access** to the server
- This prevents unauthorized remote password resets
- If someone has local access, they already have full system control
- Consider this when evaluating your security model

## Troubleshooting

### "Database not found" Error

**Problem**: The script cannot find `data/portfolio.db`

**Solution**:
1. Make sure ABCT has been run at least once to create the database
2. Check that you're in the correct directory
3. Verify the database path in the error message

### "User not found" Error

**Problem**: The specified username doesn't exist in the database

**Solution**:
1. Use the default username: `admin`
2. If you created a custom user, make sure you spell it correctly
3. Run ABCT at least once to create the default admin user

### "bcrypt not installed" Error

**Problem**: The bcrypt library is not installed

**Solution**:
```bash
pip install bcrypt
# Or if using virtual environment:
source venv/bin/activate
pip install bcrypt
```

### Database Locked Error

**Problem**: The database is locked (ABCT is still running)

**Solution**:
1. Stop the ABCT server first
2. Wait a few seconds for the database to release
3. Try the reset script again

## Emergency Recovery

If you cannot access the password reset script or it's not working:

### Option 1: Delete the Database
```bash
# CAUTION: This will delete ALL data including wallets and history
cd /path/to/ABCT
rm data/portfolio.db
# Restart ABCT - it will recreate the database with default credentials
```

### Option 2: Manual SQL Update
```bash
# Generate a bcrypt hash for your new password
python -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"

# Update the database directly
sqlite3 data/portfolio.db
sqlite> UPDATE users SET password_hash = 'paste_hash_here' WHERE username = 'admin';
sqlite> .quit
```

### Option 3: Environment Variable Override
```bash
# Temporarily bypass database password
export ABCT_ADMIN_PASSWORD=temporary_password
# Start ABCT and login with this password
# Then use the web interface to change password permanently
```

## Support

If you're still having trouble resetting your password:

1. Check the ABCT logs for error messages
2. Verify file permissions on the database
3. Ensure Python and all dependencies are properly installed
4. Review the Security documentation (SECURITY.md)
5. Open an issue on GitHub with details (don't include passwords!)

## Related Documentation

- [README.md](README.md) - Main documentation with default credentials
- [SECURITY.md](SECURITY.md) - Security best practices
- [ENV_BACKUP_GUIDE.md](ENV_BACKUP_GUIDE.md) - Environment configuration

---

**Build**: v1769649627
**Last Updated**: 2026-01-28
