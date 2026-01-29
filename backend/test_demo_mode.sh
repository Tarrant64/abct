#!/bin/bash

# Demo Mode Testing Script
# Tests that demo mode is working correctly

set -e  # Exit on error

echo "=========================================="
echo "ABCT Demo Mode Testing Script"
echo "=========================================="
echo ""

# Configuration
API_URL="${API_URL:-http://localhost:8000/api}"
DEMO_USER="demo"
DEMO_PASS="demo"

echo "Testing against: $API_URL"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Demo user login
echo "Test 1: Demo User Login"
echo "------------------------"
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$DEMO_USER\", \"password\": \"$DEMO_PASS\"}")

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.token')

if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
    echo -e "${GREEN}✓ Demo user login successful${NC}"
    echo "  Token: ${TOKEN:0:20}..."
else
    echo -e "${RED}✗ Demo user login failed${NC}"
    echo "  Response: $LOGIN_RESPONSE"
    exit 1
fi
echo ""

# Test 2: Check demo status
echo "Test 2: Demo Status Endpoint"
echo "-----------------------------"
DEMO_STATUS=$(curl -s "$API_URL/auth/demo-status" \
  -H "Authorization: Bearer $TOKEN")

IS_DEMO=$(echo "$DEMO_STATUS" | jq -r '.is_demo')

if [ "$IS_DEMO" = "true" ]; then
    echo -e "${GREEN}✓ Demo status correctly identified${NC}"
    echo "  Response: $DEMO_STATUS" | jq '.'
else
    echo -e "${RED}✗ Demo status check failed${NC}"
    echo "  Expected is_demo=true, got: $IS_DEMO"
    exit 1
fi
echo ""

# Test 3: Demo wallets endpoint
echo "Test 3: Demo Wallets Endpoint"
echo "------------------------------"
WALLETS_RESPONSE=$(curl -s "$API_URL/wallets" \
  -H "Authorization: Bearer $TOKEN")

DEMO_MODE=$(echo "$WALLETS_RESPONSE" | jq -r '.demo_mode')
WALLET_COUNT=$(echo "$WALLETS_RESPONSE" | jq -r '.total')

if [ "$DEMO_MODE" = "true" ] && [ "$WALLET_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Demo wallets endpoint working${NC}"
    echo "  Demo mode: $DEMO_MODE"
    echo "  Wallet count: $WALLET_COUNT"
    echo ""
    echo "  Sample wallet:"
    echo "$WALLETS_RESPONSE" | jq '.wallets[0]'
else
    echo -e "${RED}✗ Demo wallets endpoint failed${NC}"
    echo "  Demo mode: $DEMO_MODE (expected: true)"
    echo "  Wallet count: $WALLET_COUNT (expected: > 0)"
    exit 1
fi
echo ""

# Test 4: Verify no real API calls (check logs if available)
echo "Test 4: API Call Verification"
echo "------------------------------"
echo -e "${YELLOW}⚠ Manual check: Review logs to ensure no real API calls were made${NC}"
echo "  Look for: Blockfrost, TapTools, CoinGecko, etc."
echo "  Expected: Zero external API calls for demo user"
echo ""

# Test 5: Auth status endpoint
echo "Test 5: Auth Status Endpoint"
echo "-----------------------------"
AUTH_STATUS=$(curl -s "$API_URL/auth/status")

HAS_DEMO_INFO=$(echo "$AUTH_STATUS" | jq 'has("demo_account")')

if [ "$HAS_DEMO_INFO" = "true" ]; then
    echo -e "${GREEN}✓ Auth status includes demo account info${NC}"
    echo "  Demo account info:"
    echo "$AUTH_STATUS" | jq '.demo_account'
else
    echo -e "${RED}✗ Auth status missing demo account info${NC}"
    exit 1
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}✓ All core tests passed!${NC}"
echo ""
echo "Demo Mode Status: WORKING"
echo "Demo User: $DEMO_USER"
echo "Demo Password: $DEMO_PASS"
echo ""
echo "Next Steps:"
echo "  1. Update remaining routers (NFTs, Prices, DeFi, Portfolio)"
echo "  2. Add frontend demo mode banner"
echo "  3. Test all endpoints with demo user"
echo ""
echo "Documentation:"
echo "  - DEMO_MODE_GUIDE.md"
echo "  - DEMO_MODE_IMPLEMENTATION_EXAMPLES.md"
echo "  - DEMO_MODE_TODO.md"
echo ""
echo "=========================================="
