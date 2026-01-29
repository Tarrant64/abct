#!/bin/bash
# Automatically move development docs to proper location

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Organizing documentation files..."

# Create directories if they don't exist
mkdir -p "$ROOT_DIR/docs/development/implementation"
mkdir -p "$ROOT_DIR/docs/development/testing"
mkdir -p "$ROOT_DIR/docs/development/planning"
mkdir -p "$ROOT_DIR/docs/guides"

# Move implementation files
for file in "$ROOT_DIR"/*_IMPLEMENTATION.md "$ROOT_DIR"/*_INTEGRATION_*.md "$ROOT_DIR"/INTEGRATION_*.md "$ROOT_DIR"/API_*.md "$ROOT_DIR"/MIDNIGHT_*.md; do
    [ -f "$file" ] && mv -n "$file" "$ROOT_DIR/docs/development/implementation/" && echo "Moved $(basename "$file") to implementation/"
done

# Move testing/fix reports
for file in "$ROOT_DIR"/*_REPORT*.md "$ROOT_DIR"/FIXES_*.md "$ROOT_DIR"/*_FIX_*.md "$ROOT_DIR"/*_INVESTIGATION_*.md "$ROOT_DIR"/POST_DEPLOYMENT*.md "$ROOT_DIR"/SECURITY_INCIDENT*.md "$ROOT_DIR"/SYNC_REPORT*.txt "$ROOT_DIR"/test_*.py "$ROOT_DIR"/test-*.json; do
    [ -f "$file" ] && mv -n "$file" "$ROOT_DIR/docs/development/testing/" && echo "Moved $(basename "$file") to testing/"
done

# Move planning files
for file in "$ROOT_DIR"/TODO.md "$ROOT_DIR"/STATUS.md "$ROOT_DIR"/PROJECT_PLAN.md "$ROOT_DIR"/*_SUMMARY.md "$ROOT_DIR"/SESSION_*.md "$ROOT_DIR"/RELEASE_NOTES_*.md "$ROOT_DIR"/GITHUB_RELEASE_*.md "$ROOT_DIR"/*_FEATURE_COMPLETE.md; do
    [ -f "$file" ] && mv -n "$file" "$ROOT_DIR/docs/development/planning/" && echo "Moved $(basename "$file") to planning/"
done

# Move guide files
for file in "$ROOT_DIR"/*_GUIDE.md; do
    [ -f "$file" ] && mv -n "$file" "$ROOT_DIR/docs/guides/" && echo "Moved $(basename "$file") to guides/"
done

echo "Documentation organized!"
echo ""
echo "Summary:"
echo "  - Implementation docs: docs/development/implementation/"
echo "  - Testing reports: docs/development/testing/"
echo "  - Planning/session notes: docs/development/planning/"
echo "  - User guides: docs/guides/"
