#!/bin/bash
#
# ABCT Security Pre-Push Hook
# Runs automated security audit before allowing git push
#
# This hook will:
# - Run security audit on ABCT codebase
# - Block push if CRITICAL/HIGH issues found (with user prompt)
# - Warn about MEDIUM/LOW issues but allow push
# - Generate generic commit messages (no vulnerability details)
#

# Get the remote and URL being pushed to
remote="$1"
url="$2"

# Determine project root (parent of .git directory)
PROJECT_ROOT="$(git rev-parse --show-toplevel)"

# Path to security agent
SECURITY_AGENT="$PROJECT_ROOT/sec/security_agent.py"

# Check if security agent exists
if [ ! -f "$SECURITY_AGENT" ]; then
    echo "Warning: Security agent not found at $SECURITY_AGENT"
    echo "Skipping security check..."
    exit 0
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Warning: python3 not found. Skipping security check..."
    exit 0
fi

# Run security agent in pre-push mode
echo ""
echo "Running pre-push security audit..."
echo ""

python3 "$SECURITY_AGENT" \
    --project-root "$PROJECT_ROOT" \
    --mode pre-push \
    --remote "$remote" \
    --url "$url" \
    --save-report "$PROJECT_ROOT/sec/last_audit.json"

exit_code=$?

# Exit with the same code as security agent
# 0 = allow push
# 1 = block push
exit $exit_code
