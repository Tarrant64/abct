# ABCT Mobile API - Quick Reference

## Base URL
```
http://localhost:8000/api/mobile
```

## Authentication
All endpoints (except `/status`) require a Bearer token:
```bash
Authorization: Bearer YOUR_TOKEN_HERE
```

Get token via:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'
```

---

## Endpoints

### 📊 Portfolio

#### Get Portfolio Summary
```http
GET /api/mobile/portfolio/summary?refresh=false
```

**Response:** Consolidated view of all assets (wallets, exchanges, NFTs, staking)

**Example:**
```bash
curl "http://localhost:8000/api/mobile/portfolio/summary" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 💰 Wallets

#### List All Wallets
```http
GET /api/mobile/wallets?blockchain={chain}&include_balances=true
```

**Query Parameters:**
- `blockchain` (optional): Filter by chain (cardano, bitcoin, ethereum, etc.)
- `include_balances` (optional): Include balances (default: true)

**Example:**
```bash
curl "http://localhost:8000/api/mobile/wallets?blockchain=cardano" \
  -H "Authorization: Bearer $TOKEN"
```

#### Get Wallet Detail
```http
GET /api/mobile/wallets/{wallet_id}
```

**Example:**
```bash
curl "http://localhost:8000/api/mobile/wallets/1" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 🏦 Exchanges

#### Get Exchanges Summary
```http
GET /api/mobile/exchanges/summary?refresh=false
```

**Example:**
```bash
curl "http://localhost:8000/api/mobile/exchanges/summary" \
  -H "Authorization: Bearer $TOKEN"
```

#### Get Exchange Detail
```http
GET /api/mobile/exchanges/{exchange_name}?refresh=false
```

**Supported exchanges:**
- `coinbase`
- `binance`
- `binance_us`
- `okx`
- `bitget`
- `gate`
- `kucoin`

**Example:**
```bash
curl "http://localhost:8000/api/mobile/exchanges/coinbase" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 🔒 DeFi & Staking

#### Get Staking Positions
```http
GET /api/mobile/defi/staking
```

**Response:** Cardano staking + DeFi protocol positions

**Example:**
```bash
curl "http://localhost:8000/api/mobile/defi/staking" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 🖼️ NFTs

#### Get NFT Summary
```http
GET /api/mobile/nfts/summary?blockchain={chain}
```

**Query Parameters:**
- `blockchain` (optional): Filter by blockchain

**Example:**
```bash
curl "http://localhost:8000/api/mobile/nfts/summary" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 📈 Charts

#### Get Portfolio History
```http
GET /api/mobile/chart/portfolio-history?range={range}&interval={interval}
```

**Query Parameters:**
- `range` (required): 7d, 4w, 3m, 1y, all
- `interval` (optional): hourly, daily (auto-selected if not specified)

**Example:**
```bash
curl "http://localhost:8000/api/mobile/chart/portfolio-history?range=7d" \
  -H "Authorization: Bearer $TOKEN"
```

#### Get Price Chart (OHLCV)
```http
GET /api/mobile/chart/price/{symbol}?range={range}&interval={interval}
```

**Path Parameters:**
- `symbol`: Cryptocurrency symbol (BTC, ETH, ADA, SOL, etc.)

**Query Parameters:**
- `range` (required): 1h, 24h, 7d, 30d, 90d, 1y, all
- `interval` (optional): 1m, 5m, 15m, 1h, 4h, 1d

**Data Sources (with automatic fallback):**
1. CoinGecko (primary)
2. Binance (fallback #1)
3. Coinbase (fallback #2)

**Examples:**
```bash
# Bitcoin - 7 days
curl "http://localhost:8000/api/mobile/chart/price/BTC?range=7d" \
  -H "Authorization: Bearer $TOKEN"

# Ethereum - 24 hours
curl "http://localhost:8000/api/mobile/chart/price/ETH?range=24h" \
  -H "Authorization: Bearer $TOKEN"

# Cardano - 30 days
curl "http://localhost:8000/api/mobile/chart/price/ADA?range=30d" \
  -H "Authorization: Bearer $TOKEN"
```

---

### ✅ System Status

#### Get API Status
```http
GET /api/mobile/status
```

**No authentication required**

**Example:**
```bash
curl "http://localhost:8000/api/mobile/status"
```

---

## Common Response Fields

All responses include:
```json
{
  "last_updated": "2026-01-31T20:30:00Z",
  "from_cache": false
}
```

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Not authenticated. Please login."
}
```

### 404 Not Found
```json
{
  "detail": "Wallet with ID 999 not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error",
  "message": "An unexpected error occurred. Please try again later.",
  "timestamp": "2026-01-31T20:30:00Z"
}
```

---

## Supported Cryptocurrencies for Charts

- BTC (Bitcoin)
- ETH (Ethereum)
- ADA (Cardano)
- SOL (Solana)
- MATIC/POL (Polygon)
- DOGE (Dogecoin)
- XRP (Ripple)
- DOT (Polkadot)
- USDC (USD Coin)
- USDT (Tether)

Plus many more - check CoinGecko support for full list.

---

## Testing

Run the test script:
```bash
./test_mobile_api.sh
```

Or test manually with the examples above.

---

## Rate Limits

Default limits:
- 60 requests per minute per user
- Check response headers for current limits

---

## Tips

1. **Cache Management**: Use `refresh=true` to force fresh data
2. **Performance**: Keep cache enabled for frequently accessed endpoints
3. **Pagination**: Not implemented yet - all data returned at once
4. **Errors**: Check HTTP status codes and error messages
5. **Timestamps**: All times in UTC with 'Z' suffix

---

## Next Steps

1. Start the ABCT backend: `./run.sh`
2. Login to get a token
3. Test endpoints using examples above
4. Build your mobile app!

---

For full API documentation, visit: http://localhost:8000/docs
