# ABCT Deployment Guide

## Quick Start

### Using Automated Script (Recommended)
```bash
./deploy.sh
```

The script will guide you through:
1. Checking git status and remote changes
2. Updating build version
3. Checking for unwanted files
4. README update prompts for significant changes
5. Proper push with security hook handling

### Manual Deployment
See full checklist in `.claude/claude.md` under "Deployment Process"

## Build Version Management

### When to Update
**ALWAYS** update after:
- CSS changes
- JavaScript changes
- HTML structure changes

### How to Update
```bash
# Generate new version
NEW_VER=$(date +%s)

# Update all HTML files
find frontend -name "*.html" -exec sed -i '' "s/v=[0-9]*/v=$NEW_VER/g" {} \;

# Verify
grep "v=" frontend/index.html

# Commit
git add frontend/*.html
git commit -m "chore: Update build version to $NEW_VER"
```

## Repository Cleanup

### Files That Should NEVER Be Committed
```
# Planning documents
DASHV2_STATUS.md
DEVELOPMENT_CHECKLIST.md
NFT_CARDANO_FIXES.md
*_TEST_RESULTS.md
*_IMPROVEMENTS.md
*_ENHANCEMENTS.md

# Credentials
cdp_api_key*.json
*_credentials.json

# Temp files
*.swp
*.tmp
.DS_Store
```

### Check Before Commit
```bash
# Check what's staged
git diff --cached --name-only

# Look for unwanted files
git diff --cached --name-only | grep -E "\.md$|\.json$"

# Unstage if needed
git reset HEAD <file>
```

## README Update Guidelines

### When to Update
**Required for**:
- New API integrations (Moralis, NMKR, etc.)
- New features (spam filter, metadata extractor, etc.)
- New services or major functionality
- Breaking changes
- Security updates

**Optional for**:
- Bug fixes
- Minor UI tweaks
- Build version bumps

### Update Template
Add to top of README.md:
```markdown
**Current Build**: v1.0.0 (BUILD 1770000515)
**Last Updated**: February 1, 2026

## Recent Changes

### February 2026
- **Feature Name**: Brief description
- **Another Feature**: Brief description
```

## Common Issues & Solutions

### Issue: Docker Container Shows Old Version
**Cause**: Code not pushed to remote repository
**Solution**:
```bash
git push --no-verify  # or run ./deploy.sh
```

### Issue: Browser Shows Old CSS
**Cause**: Build version not updated
**Solution**:
```bash
# Update version
NEW_VER=$(date +%s)
find frontend -name "*.html" -exec sed -i '' "s/v=[0-9]*/v=$NEW_VER/g" {} \;
git add frontend/*.html
git commit -m "chore: Update build version to $NEW_VER"
git push --no-verify
```

### Issue: Push Rejected - Fetch First
**Cause**: Remote has changes you don't have locally
**Solution**:
```bash
git stash              # Stash uncommitted changes
git pull --rebase      # Pull remote changes
git stash pop          # Restore your changes
git push --no-verify   # Push
```

### Issue: Security Hook Blocks Push
**Cause**: Pre-push security audit found issues
**Solution**:
```bash
# If frontend-only changes
git push --no-verify

# If backend changes, review audit output
# Fix critical issues before pushing
```

## Deployment Workflow

### Standard Deployment
```bash
# 1. Make changes and test
# ... edit files ...

# 2. Check status
git status

# 3. Run deployment script
./deploy.sh

# 4. Follow prompts for:
#    - Version update
#    - README update
#    - Push type selection

# 5. Run unRAID update on server
# ... on server ...

# 6. Verify in browser (hard refresh: Cmd+Shift+R)
```

### Emergency Hotfix
```bash
# 1. Make critical fix
# ... edit files ...

# 2. Quick commit
git add <files>
git commit -m "hotfix: Critical bug fix"

# 3. Pull and push immediately
git pull --rebase
git push --no-verify

# 4. Deploy
# ... run unRAID update ...
```

### Feature Branch Workflow
```bash
# 1. Create feature branch
git checkout -b feature/new-api

# 2. Make changes
# ... work on feature ...

# 3. Commit regularly
git add .
git commit -m "feat: Add new API integration"

# 4. Before merging to main
git checkout main
git pull
git checkout feature/new-api
git rebase main

# 5. Merge and deploy
git checkout main
git merge feature/new-api
./deploy.sh
```

## Pre-Deployment Checklist

### Every Deployment
- [ ] All changes tested locally
- [ ] Hard refresh in browser (Cmd+Shift+R)
- [ ] Git status reviewed
- [ ] Unwanted files not staged
- [ ] Build version updated (if CSS/JS changed)

### Significant Changes
- [ ] README updated with changes
- [ ] Build version noted in README
- [ ] API documentation updated (if applicable)
- [ ] Breaking changes documented

### Before Push
- [ ] Git pull completed (no conflicts)
- [ ] Commit history reviewed
- [ ] Push type determined (verify vs no-verify)

### After Deploy
- [ ] unRAID script completed successfully
- [ ] New build version visible in output
- [ ] Browser shows changes (hard refresh)
- [ ] All features tested
- [ ] Logs checked for errors

## Tools & Scripts

### deploy.sh
Automated deployment helper with:
- Git status checking
- Version management
- Cleanup verification
- README prompts
- Push handling

### Manual Commands
```bash
# Update build version
NEW_VER=$(date +%s)
find frontend -name "*.html" -exec sed -i '' "s/v=[0-9]*/v=$NEW_VER/g" {} \;

# Check for unwanted files
git status | grep -E "\.md$|cdp_api_key"

# Verify theme consistency
grep -r "data-theme=" frontend/

# Check version consistency
grep "v=" frontend/*.html | sort -u
```

## Getting Help

### Documentation
- **Full process**: `.claude/claude.md` > Deployment Process
- **Project context**: `.claude/claude.md` > Project Overview
- **Common errors**: `.claude/claude.md` > Common Errors & Solutions

### Quick Reference
- Current build version: `grep "v=" frontend/index.html | head -1`
- Git status: `git status -sb`
- Recent commits: `git log --oneline -10`
- Staged files: `git diff --cached --name-only`

---

**Remember**: When in doubt, use `./deploy.sh` for guided deployment!
