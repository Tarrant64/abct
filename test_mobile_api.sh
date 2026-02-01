#!/bin/bash

# ABCT Mobile API Test Script
# Tests all mobile endpoints to ensure they're working correctly

BASE_URL="http://localhost:8000"

echo "========================================="
echo "ABCT Mobile API Test Suite"
echo "========================================="
echo ""

# Test 1: Health/Status (no auth required)
echo "Test 1: GET /api/mobile/status"
curl -s "$BASE_URL/api/mobile/status" | python3 -m json.tool
echo ""
echo "========================================="
echo ""

# For authenticated endpoints, you'll need a token
echo "To test authenticated endpoints, first login:"
echo ""
echo "curl -X POST $BASE_URL/auth/login \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"username\":\"admin\",\"password\":\"YOUR_PASSWORD\"}'"
echo ""
echo "Then set the token:"
echo "export TOKEN='your_token_here'"
echo ""
echo "And run the following tests:"
echo ""

echo "# Test 2: Portfolio Summary"
echo "curl -s \"$BASE_URL/api/mobile/portfolio/summary\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 3: Wallets List"
echo "curl -s \"$BASE_URL/api/mobile/wallets\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 4: Exchanges Summary"
echo "curl -s \"$BASE_URL/api/mobile/exchanges/summary\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 5: DeFi Staking"
echo "curl -s \"$BASE_URL/api/mobile/defi/staking\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 6: NFT Summary"
echo "curl -s \"$BASE_URL/api/mobile/nfts/summary\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 7: Portfolio History (7 days)"
echo "curl -s \"$BASE_URL/api/mobile/chart/portfolio-history?range=7d\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 8: BTC Price Chart (7 days)"
echo "curl -s \"$BASE_URL/api/mobile/chart/price/BTC?range=7d\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 9: ETH Price Chart (24 hours)"
echo "curl -s \"$BASE_URL/api/mobile/chart/price/ETH?range=24h\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "# Test 10: ADA Price Chart (30 days)"
echo "curl -s \"$BASE_URL/api/mobile/chart/price/ADA?range=30d\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
echo ""

echo "========================================="
echo "Test script ready!"
echo "========================================="
