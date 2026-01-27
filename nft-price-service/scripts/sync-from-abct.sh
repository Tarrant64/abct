#!/bin/bash
# Sync Cardano NFT collections from ABCT to the Cardano NFT Price Service
#
# Usage:
#   ./sync-from-abct.sh [ABCT_URL] [NFT_SERVICE_URL]
#
# Example:
#   ./sync-from-abct.sh http://localhost:8000 http://your-server:8080

ABCT_URL="${1:-http://localhost:8081}"
NFT_SERVICE_URL="${2:-http://localhost:8082}"

echo "Syncing Cardano NFT collections from ABCT to Cardano NFT Price Service..."
echo "  ABCT: $ABCT_URL"
echo "  NFT Service: $NFT_SERVICE_URL"
echo ""

# Get all NFTs from ABCT
echo "Fetching NFTs from ABCT..."
NFTS=$(curl -s "$ABCT_URL/nfts")

if [ -z "$NFTS" ] || [ "$NFTS" = "null" ]; then
    echo "Error: Could not fetch NFTs from ABCT"
    exit 1
fi

# Extract unique policy IDs and build batch request
COLLECTIONS=$(echo "$NFTS" | python3 -c "
import sys, json

data = json.load(sys.stdin)
nfts = data.get('nfts', [])

# Group by policy_id and calculate priority based on floor value
collections = {}
for nft in nfts:
    policy_id = nft.get('policy_id')
    if policy_id:
        if policy_id not in collections:
            collections[policy_id] = {
                'policy_id': policy_id,
                'name': nft.get('collection_name', ''),
                'priority': 0,
                'count': 0
            }
        collections[policy_id]['count'] += 1
        # Higher priority for collections with floor prices
        if nft.get('floor_price'):
            collections[policy_id]['priority'] += 1

# Output as JSON array
result = list(collections.values())
print(json.dumps(result))
")

COLLECTION_COUNT=$(echo "$COLLECTIONS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "Found $COLLECTION_COUNT unique collections"

# Register collections with Cardano NFT Price Service
echo "Registering collections with Cardano NFT Price Service..."
RESPONSE=$(curl -s -X POST "$NFT_SERVICE_URL/collections/register-batch" \
    -H "Content-Type: application/json" \
    -d "$COLLECTIONS")

echo "$RESPONSE" | python3 -m json.tool

echo ""
echo "Sync complete!"
echo "The Cardano NFT Price Service will now gradually collect floor prices for these collections."
echo "Check status: curl $NFT_SERVICE_URL/status"
