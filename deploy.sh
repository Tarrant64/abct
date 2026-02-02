#!/bin/bash
# ABCT Deployment Helper Script
# Ensures proper deployment process is followed

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  ABCT Deployment Helper${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Check for uncommitted changes
echo -e "${YELLOW}[1/8] Checking git status...${NC}"
if [[ -n $(git status -s) ]]; then
    echo -e "${YELLOW}⚠️  Uncommitted changes found:${NC}"
    git status -s
    echo ""
else
    echo -e "${GREEN}✓ No uncommitted changes${NC}"
fi

# Step 2: Check if remote is ahead
echo -e "${YELLOW}[2/8] Checking remote status...${NC}"
git fetch origin
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})
BASE=$(git merge-base @ @{u})

if [ $LOCAL = $REMOTE ]; then
    echo -e "${GREEN}✓ Up to date with remote${NC}"
elif [ $LOCAL = $BASE ]; then
    echo -e "${RED}✗ Remote is ahead - need to pull first${NC}"
    echo -e "${YELLOW}Would you like to pull now? (y/n)${NC}"
    read -r PULL_NOW
    if [[ "$PULL_NOW" == "y" ]]; then
        # Check for unstaged changes
        if [[ -n $(git diff --name-only) ]]; then
            echo -e "${YELLOW}⚠️  Stashing unstaged changes...${NC}"
            git stash
            STASHED=true
        fi
        echo -e "${YELLOW}Pulling with rebase...${NC}"
        git pull --rebase
        if [[ "$STASHED" == "true" ]]; then
            echo -e "${YELLOW}Restoring stashed changes...${NC}"
            git stash pop
        fi
    else
        echo -e "${RED}Cannot proceed without pulling. Exiting.${NC}"
        exit 1
    fi
elif [ $REMOTE = $BASE ]; then
    echo -e "${GREEN}✓ Local is ahead of remote (ready to push)${NC}"
else
    echo -e "${RED}✗ Branches have diverged${NC}"
    exit 1
fi

# Step 3: Update build version (if needed)
echo ""
echo -e "${YELLOW}[3/8] Build version management${NC}"
CURRENT_VER=$(grep -o "styles.css?v=[0-9]*" frontend/index.html | head -1 | grep -o "[0-9]*")
echo "Current build version: $CURRENT_VER"
echo -e "${YELLOW}Update build version? (y/n)${NC}"
read -r UPDATE_VER

if [[ "$UPDATE_VER" == "y" ]]; then
    NEW_VER=$(date +%s)
    echo -e "${YELLOW}Updating to version: $NEW_VER${NC}"

    # Update all HTML files
    find frontend -name "*.html" -type f -exec sed -i '' "s/v=[0-9]*/v=$NEW_VER/g" {} \;

    echo -e "${GREEN}✓ Updated all HTML files to v=$NEW_VER${NC}"

    # Stage and commit version update
    git add frontend/*.html
    git commit -m "chore: Update build version to $NEW_VER

Update cache-busting version parameter across all HTML files.

Previous version: $CURRENT_VER
New version: $NEW_VER"

    echo -e "${GREEN}✓ Version update committed${NC}"
fi

# Step 4: Check for unwanted files
echo ""
echo -e "${YELLOW}[4/8] Checking for unwanted files in staging...${NC}"
UNWANTED_PATTERNS=("*.md" "DASHV2_STATUS.md" "DEVELOPMENT_CHECKLIST.md" "*.swp" "*.tmp" ".DS_Store" "cdp_api_key*.json")

FOUND_UNWANTED=false
for pattern in "${UNWANTED_PATTERNS[@]}"; do
    if git diff --cached --name-only | grep -q "$pattern"; then
        echo -e "${RED}⚠️  Found staged file matching pattern: $pattern${NC}"
        git diff --cached --name-only | grep "$pattern"
        FOUND_UNWANTED=true
    fi
done

if [ "$FOUND_UNWANTED" = true ]; then
    echo -e "${YELLOW}Unstage these files? (y/n)${NC}"
    read -r UNSTAGE
    if [[ "$UNSTAGE" == "y" ]]; then
        for pattern in "${UNWANTED_PATTERNS[@]}"; do
            git diff --cached --name-only | grep "$pattern" | xargs git reset HEAD 2>/dev/null || true
        done
        echo -e "${GREEN}✓ Unwanted files unstaged${NC}"
    fi
else
    echo -e "${GREEN}✓ No unwanted files in staging${NC}"
fi

# Step 5: Review commits
echo ""
echo -e "${YELLOW}[5/8] Recent commits:${NC}"
git log --oneline -5

# Step 6: Check if README needs updating
echo ""
echo -e "${YELLOW}[6/8] README update check${NC}"
echo -e "${YELLOW}Does this push include significant changes (new APIs/features/services)? (y/n)${NC}"
read -r SIGNIFICANT

if [[ "$SIGNIFICANT" == "y" ]]; then
    echo -e "${YELLOW}⚠️  Please update README.md with:${NC}"
    echo "  - Build version tag"
    echo "  - Recent changes section at top"
    echo "  - New features/APIs/services documentation"
    echo ""
    echo -e "${YELLOW}Press Enter when README is updated...${NC}"
    read -r

    if git diff --name-only | grep -q "README.md"; then
        echo -e "${GREEN}✓ README.md has been modified${NC}"
    else
        echo -e "${RED}⚠️  README.md not modified. Continue anyway? (y/n)${NC}"
        read -r CONTINUE
        if [[ "$CONTINUE" != "y" ]]; then
            exit 1
        fi
    fi
fi

# Step 7: Push decision
echo ""
echo -e "${YELLOW}[7/8] Ready to push${NC}"
echo -e "${YELLOW}Push type:${NC}"
echo "  1) Frontend-only changes (skip security hook with --no-verify)"
echo "  2) Backend changes included (run security hook)"
echo "  3) Cancel"
read -r PUSH_TYPE

case $PUSH_TYPE in
    1)
        echo -e "${YELLOW}Pushing with --no-verify...${NC}"
        if git push --no-verify; then
            echo -e "${GREEN}✓ Push successful${NC}"
        else
            echo -e "${RED}✗ Push failed${NC}"
            exit 1
        fi
        ;;
    2)
        echo -e "${YELLOW}Pushing with security hook...${NC}"
        if git push; then
            echo -e "${GREEN}✓ Push successful${NC}"
        else
            echo -e "${RED}✗ Push failed (security hook may have blocked)${NC}"
            exit 1
        fi
        ;;
    3)
        echo -e "${YELLOW}Deployment cancelled${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

# Step 8: Completion
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Run unRAID update script on server"
echo "  2. Verify changes in browser (hard refresh)"
echo "  3. Test all affected features"
echo ""
