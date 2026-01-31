# The Graph API Integration - Uniswap Subgraph

## Overview

The Graph API integration provides Ethereum-based token pricing data via Uniswap v2/v3 subgraphs. This enables native token-denominated pricing for Ethereum, Polygon, and Base chain assets.

## API Limits

- **Rate Limit**: 100,000 queries per 24 hours
- **Tracking**: Automatic via API tracking middleware
- **Status Endpoint**: `/api/status` (shows Graph API usage)

## Configuration

Add to `.env`:
```
GRAPH_API_KEY=your_graph_api_key_here
```

## Features

### 1. Token Price in Native Token (ETH/POL)

Get token prices denominated in the chain's native token:
- **Ethereum**: Prices in ETH
- **Polygon**: Prices in POL (via ETH equivalent)
- **Base**: Prices in ETH

### 2. Automatic Price Conversion

The system automatically:
1. Queries The Graph for ETH-denominated price
2. Converts to USD using current ETH price
3. Falls back to direct USD pricing if Graph data unavailable

### 3. Multi-Chain Support

Supported chains:
- Ethereum Mainnet (Uniswap V2/V3)
- Polygon (coming soon)
- Base (coming soon)

## Implementation

### Service: `services/graph.py`

```python
from services.graph import graph_service

# Get single token price in ETH
price_eth = await graph_service.get_token_price_eth(token_address)

# Get multiple token prices (batch query)
prices = await graph_service.get_multiple_token_prices([addr1, addr2, addr3])

# Get comprehensive token data
token_data = await graph_service.get_token_data(token_address)
```

### Integration in Wallet Assets

The `/wallets/id/{wallet_id}/assets` endpoint now returns:
- `price_native`: Price in native token (ETH/ADA/SOL/etc.)
- `total_native`: Total value in native token
- `price_usd`: Price in USD
- `total_value_usd`: Total USD value

### Frontend Display

Assets are displayed in a table with:
- Native Token Price column (e.g., "ETH Price", "ADA Price")
- Native Token Value column
- USD Value column
- Portfolio percentage

## Usage Examples

### Ethereum ERC-20 Token

For USDC on Ethereum (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`):

1. Graph API queries Uniswap for USDC/ETH price
2. Returns: `0.000234` ETH per USDC
3. Converts to USD: `0.000234 ETH × $3,500 = $0.819`
4. Displays in wallet assets with ETH-denominated price

### Fallback Behavior

If Graph API is unavailable or token not found:
1. Attempts direct USD price lookup via CoinGecko
2. Calculates native token equivalent
3. Displays "N/A" if no price data available

## Monitoring

### Check API Usage

```bash
curl http://localhost:8000/api/status
```

Response includes:
```json
{
  "graph": {
    "configured": true,
    "calls_today": 1234,
    "limit": 100000,
    "remaining": 98766
  }
}
```

### Database Tracking

API calls are tracked in the `api_usage` table:
- `api_name`: "graph"
- `period_start`: Daily period start
- `call_count`: Number of queries in period

## Best Practices

1. **Caching**: Token prices are cached for 5 minutes to reduce API calls
2. **Batch Queries**: Use `get_multiple_token_prices()` for multiple tokens
3. **Rate Limiting**: Monitor usage via status endpoint
4. **Fallbacks**: Always have USD pricing as fallback

## Troubleshooting

### No prices showing for Ethereum tokens

1. Check if token exists on Uniswap
2. Verify token address is correct (checksummed or lowercase)
3. Check Graph API key configuration
4. Review API usage limits

### API limit exceeded

1. Check current usage: `/api/status`
2. Wait for daily reset (midnight UTC)
3. Consider implementing additional caching

## Future Enhancements

- [ ] Polygon-specific subgraph integration
- [ ] Base-specific subgraph integration
- [ ] Sushiswap subgraph support
- [ ] Historical price queries
- [ ] Custom time ranges for price data
