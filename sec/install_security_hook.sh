#!/bin/bash
#
# ABCT Security Hook Installer
# Installs pre-push security audit hook into git repository
#

set -e

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "ABCT Security Hook Installer"
echo "========================================"
echo ""
echo "Project root: $PROJECT_ROOT"
echo ""

# Check if git is initialized
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "Git repository not initialized."
    read -p "Would you like to initialize git now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$PROJECT_ROOT"
        git init
        echo "✓ Git repository initialized"
    else
        echo "Cancelled. Please initialize git manually and run this script again."
        exit 1
    fi
fi

# Create hooks directory if it doesn't exist
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
mkdir -p "$HOOKS_DIR"

# Install pre-push hook
HOOK_SOURCE="$SCRIPT_DIR/pre-push-hook.sh"
HOOK_DEST="$HOOKS_DIR/pre-push"

if [ ! -f "$HOOK_SOURCE" ]; then
    echo "Error: Hook source not found at $HOOK_SOURCE"
    exit 1
fi

# Check if hook already exists
if [ -f "$HOOK_DEST" ]; then
    echo "Warning: pre-push hook already exists at $HOOK_DEST"
    read -p "Would you like to overwrite it? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled. Existing hook preserved."
        exit 1
    fi
    # Backup existing hook
    backup="$HOOK_DEST.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$HOOK_DEST" "$backup"
    echo "✓ Existing hook backed up to $backup"
fi

# Copy hook and make executable
cp "$HOOK_SOURCE" "$HOOK_DEST"
chmod +x "$HOOK_DEST"

echo "✓ Pre-push hook installed successfully"
echo ""

# Make security scripts executable
chmod +x "$SCRIPT_DIR/security_audit.py"
chmod +x "$SCRIPT_DIR/security_agent.py"
echo "✓ Security scripts made executable"
echo ""

# Test the setup
echo "Testing security audit setup..."
if python3 "$SCRIPT_DIR/security_audit.py" --project-root "$PROJECT_ROOT" --format text > /dev/null 2>&1; then
    echo "✓ Security audit can run successfully"
else
    echo "⚠️  Warning: Security audit test failed"
    echo "   Please ensure Python 3 is installed and dependencies are available"
fi

echo ""
echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "The security audit will now run automatically before every git push."
echo ""
echo "How it works:"
echo "  • CRITICAL/HIGH issues: You'll be prompted to fix before push"
echo "  • MEDIUM/LOW issues: Warning only, push continues"
echo "  • No vulnerability details will be pushed to git"
echo ""
echo "Manual commands:"
echo "  • Run audit manually:"
echo "    python3 sec/security_agent.py --mode audit"
echo ""
echo "  • Disable hook temporarily:"
echo "    git push --no-verify"
echo ""
echo "  • Uninstall hook:"
echo "    rm .git/hooks/pre-push"
echo ""
