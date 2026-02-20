# Exchange Integration Guide

ABCT supports integration with multiple cryptocurrency exchanges to track your exchange balances alongside your self-custody wallets. This guide explains how to configure each supported exchange.

## Supported Exchanges

- **Coinbase** (via CDP API)
- **Binance** (Binance.com global)
- **Binance.US**
- **OKX**
- **Bitget**
- **Gate.io**
- **KuCoin**

## Security Best Practices

**⚠️ IMPORTANT SECURITY NOTES:**

1. **Use Read-Only API Keys**: Always create API keys with **read-only permissions** (view balances only). Never give withdrawal or trading permissions.
2. **IP Whitelisting**: When available, restrict API keys to your server's IP address.
3. **Environment Variables**: Store API keys in the `.env` file, which is excluded from version control.
4. **Never Commit Keys**: The `.env` file should never be committed to Git.

---

## Configuration Instructions

### 1. Coinbase

Coinbase uses the CDP (Coinbase Developer Platform) API with JWT authentication.

**Steps:**
1. Go to [https://coinbase.com/settings/api](https://coinbase.com/settings/api)
2. Create a new API key with **read-only** permissions
3. Download the JSON file (will be named like `cdp_api_key.json`)
4. Place the file in the ABCT project root directory
5. Restart the backend

**File Format:**
```json
{
  "name": "organizations/{org_id}/apiKeys/{key_id}",
  "privateKey": "-----BEGIN EC PRIVATE KEY-----\n..."
}
```

**Permissions Required:** Read-only access to accounts and transactions

---

### 2. Binance (Binance.com)

Binance global exchange API.

**Steps:**
1. Log into [Binance.com](https://www.binance.com)
2. Go to Account → API Management
3. Create a new API key
4. **Important:** Enable only "Read" permissions, disable "Spot & Margin Trading" and "Withdrawals"
5. Add to `.env` file:

```bash
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
```

**Permissions Required:** Read-only (Enable Reading checkbox only)

**Documentation:** [https://developers.binance.com/docs/binance-spot-api-docs](https://developers.binance.com/docs/binance-spot-api-docs)

---

### 3. Binance.US

Binance US exchange (separate from Binance.com).

**Steps:**
1. Log into [Binance.US](https://www.binance.us)
2. Go to Account → API Management
3. Create a new API key
4. Enable only "Read" permissions
5. Add to `.env` file:

```bash
BINANCE_US_API_KEY=your_api_key_here
BINANCE_US_API_SECRET=your_api_secret_here
```

**Permissions Required:** Read-only

**Documentation:** [https://docs.binance.us/#introduction](https://docs.binance.us/#introduction)

---

### 4. OKX

OKX exchange API (requires API key + secret + passphrase).

**Steps:**
1. Log into [OKX](https://www.okx.com)
2. Go to Profile → API
3. Create a new API key
4. Set permissions to **Read** only
5. Set a passphrase (you'll need to remember this)
6. Add to `.env` file:

```bash
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_API_PASSPHRASE=your_passphrase_here
```

**Permissions Required:** Read-only

**Documentation:** [https://www.okx.com/docs-v5/en/](https://www.okx.com/docs-v5/en/)

---

### 5. Bitget

Bitget exchange API (requires API key + secret + passphrase).

**Steps:**
1. Log into [Bitget](https://www.bitget.com)
2. Go to Account → API
3. Create a new API key
4. Set permissions to **Read** only
5. Set a passphrase
6. Add to `.env` file:

```bash
BITGET_API_KEY=your_api_key_here
BITGET_API_SECRET=your_api_secret_here
BITGET_API_PASSPHRASE=your_passphrase_here
```

**Permissions Required:** Read-only

**Documentation:** [https://www.bitget.com/api-doc/](https://www.bitget.com/api-doc/)

---

### 6. Gate.io

Gate.io exchange API.

**Steps:**
1. Log into [Gate.io](https://www.gate.io)
2. Go to Account → API → Create API Key
3. Set permissions to **Read** only
4. Add to `.env` file:

```bash
GATE_API_KEY=your_api_key_here
GATE_API_SECRET=your_api_secret_here
```

**Permissions Required:** Read-only (Spot account reading)

**Documentation:** [https://www.gate.io/docs/developers/apiv4/en/](https://www.gate.io/docs/developers/apiv4/en/)

---

### 7. KuCoin

KuCoin exchange API (requires API key + secret + passphrase).

**Steps:**
1. Log into [KuCoin](https://www.kucoin.com)
2. Go to Profile → API Management
3. Create a new API
4. Set permissions to **General** (read-only)
5. Set a passphrase
6. Add to `.env` file:

```bash
KUCOIN_API_KEY=your_api_key_here
KUCOIN_API_SECRET=your_api_secret_here
KUCOIN_API_PASSPHRASE=your_passphrase_here
```

**Permissions Required:** General (read-only)

**Documentation:** [https://www.kucoin.com/docs-new/intro](https://www.kucoin.com/docs-new/intro)

---

## Verifying Configuration

After adding API keys, you can verify they're configured correctly:

1. Restart the backend:
   ```bash
   cd backend
   python main.py
   ```

2. Check the `/exchanges/status` endpoint:
   ```bash
   curl http://localhost:8000/exchanges/status
   ```

3. View in the dashboard:
   - Log into ABCT
   - Navigate to "Exchange Wallets" section
   - Configured exchanges will appear automatically

---

## Troubleshooting

### "Exchange API not configured"
- Verify API keys are in the `.env` file
- Ensure there are no extra spaces or quotes around keys
- Restart the backend after adding keys

### "Authentication failed"
- Double-check API key and secret are correct
- For OKX/Bitget/KuCoin: verify the passphrase is correct
- Check if IP whitelisting is enabled on the exchange and add your server IP

### "No assets displayed"
- ABCT filters assets with USD value < $1.00
- Verify you have balances on the exchange
- Check if the exchange API is accessible from your location

### "Rate limit exceeded"
- ABCT caches exchange data for 5 minutes
- Multiple rapid refreshes may trigger rate limits
- Wait a few minutes before trying again

---

## API Rate Limits

Each exchange has different rate limits:

- **Coinbase**: 10 requests/second
- **Binance**: 1200 requests/minute (with weight system)
- **OKX**: 20 requests/2 seconds per endpoint
- **Bitget**: 10 requests/second
- **Gate.io**: 900 requests/minute
- **KuCoin**: 100 requests/10 seconds

ABCT implements caching to minimize API calls and stay within rate limits.

---

## Data Privacy

- All exchange API calls are made server-side from your ABCT instance
- API keys never leave your server
- No data is sent to third parties
- Exchange balances are cached locally for 5 minutes

---

## Support

For issues or questions:
- Check the troubleshooting section above
- Review exchange API documentation links
- Open an issue on GitHub: [https://github.com/yourusername/ABCT/issues](https://github.com/yourusername/ABCT/issues)
