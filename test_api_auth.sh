#!/bin/bash
# Test API authentication and endpoints

echo "========================================="
echo "Testing ABCT API Endpoints"
echo "========================================="
echo ""

# Login to get token
echo "1. Logging in as admin..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"satoshi"}')

echo "Login response: $LOGIN_RESPONSE"
echo ""

# Extract token
TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo "ERROR: Failed to get token"
    exit 1
fi

echo "Token obtained: ${TOKEN:0:20}..."
echo ""

# Test GET /settings/apis
echo "2. Testing GET /settings/apis with Bearer token..."
GET_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  http://localhost:8000/settings/apis \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$GET_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$GET_RESPONSE" | sed '$d')

echo "HTTP Status: $HTTP_CODE"
echo "Response body (first 200 chars): ${BODY:0:200}..."
echo ""

# Test PATCH /settings/apis/{api_id}/enabled
echo "3. Testing PATCH /settings/apis/blockfrost/enabled..."
PATCH_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X PATCH http://localhost:8000/settings/apis/blockfrost/enabled \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}')

HTTP_CODE=$(echo "$PATCH_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$PATCH_RESPONSE" | sed '$d')

echo "HTTP Status: $HTTP_CODE"
echo "Response: $BODY"
echo ""

# Test PUT /settings/apis/{api_id} (save key)
echo "4. Testing PUT /settings/apis/coingecko..."
PUT_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X PUT http://localhost:8000/settings/apis/coingecko \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test_key_12345"}')

HTTP_CODE=$(echo "$PUT_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$PUT_RESPONSE" | sed '$d')

echo "HTTP Status: $HTTP_CODE"
echo "Response: $BODY"
echo ""

# Test DELETE /settings/apis/{api_id}
echo "5. Testing DELETE /settings/apis/coingecko..."
DELETE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X DELETE http://localhost:8000/settings/apis/coingecko \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$DELETE_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$DELETE_RESPONSE" | sed '$d')

echo "HTTP Status: $HTTP_CODE"
echo "Response: $BODY"
echo ""

echo "========================================="
echo "Test Complete"
echo "========================================="
