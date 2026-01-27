# ABCT - A Better Crypto Tracker

A self-hosted cryptocurrency portfolio tracker that aggregates data from multiple blockchains, exchanges, and DeFi protocols.

![Version](https://img.shields.io/badge/version-0.8.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.109-teal.svg)
![Security](https://img.shields.io/badge/security-hardened-green.svg)

## Features

- **Multi-Blockchain Support**: Track wallets on Cardano, Bitcoin, and Ethereum
- **Exchange Integration**: Connect to Coinbase for centralized holdings
- **DeFi Monitoring**: View Cardano staking positions with APY and rewards
- **NFT Collection**: Browse your NFTs with floor price valuations
- **Portfolio History**: Interactive charts showing value over time
- **Privacy Mode**: Hide sensitive financial data with one click
- **Self-Hosted**: Your data stays on your machine

## Quick Start

```bash
# Clone the repository
git clone <repo-url> ABCT
cd ABCT

# Run the setup script
cd Deployment
chmod +x setup.sh
./setup.sh

# Configure your API keys
cd ..
nano .env  # Add your Blockfrost API key at minimum

# Start the server
./run.sh

# Open in browser
open http://127.0.0.1:8000
```

## Screenshots

The dashboard provides a comprehensive view of your crypto portfolio:

- **Portfolio Summary**: Total value across all blockchains
- **Value History Chart**: Track portfolio performance over 7 days, 4 weeks, or 3 months
- **Staking Positions**: View delegated ADA, earned rewards, and pool APY
- **Exchange Holdings**: See balances from connected exchanges
- **NFT Gallery**: Browse collections with floor price estimates

## Requirements

- Python 3.9 or higher
- 512MB RAM minimum
- API keys (see below)

## API Keys

| Service | Required | Purpose | Sign Up |
|---------|----------|---------|---------|
| Blockfrost | **Yes** | Cardano blockchain data | [blockfrost.io](https://blockfrost.io) |
| CExplorer | Recommended | Staking/rewards data | [cexplorer.io/api](https://cexplorer.io/api) |
| TapTools | Optional | NFT floor prices | [taptools.io](https://taptools.io/openapi/subscription) |
| Coinbase | Optional | Exchange integration | [portal.cdp.coinbase.com](https://portal.cdp.coinbase.com) |
| Etherscan | Optional | Ethereum support | [etherscan.io](https://etherscan.io/apis) |

## Project Structure

```
ABCT/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Application entry point
│   ├── config.py           # Configuration management
│   ├── database.py         # SQLite database layer
│   ├── routers/            # API endpoint handlers
│   │   ├── wallets.py      # Wallet CRUD operations
│   │   ├── portfolio.py    # Portfolio summary & history
│   │   ├── prices.py       # Cryptocurrency prices
│   │   ├── defi.py         # Staking positions
│   │   ├── exchanges.py    # Exchange balances
│   │   └── nfts.py         # NFT collection
│   ├── services/           # Business logic layer
│   │   ├── cardano.py      # Cardano blockchain service
│   │   ├── bitcoin.py      # Bitcoin blockchain service
│   │   ├── ethereum.py     # Ethereum blockchain service
│   │   ├── pricing.py      # Price aggregation
│   │   ├── defi.py         # DeFi/staking service
│   │   ├── coinbase.py     # Coinbase exchange service
│   │   ├── nft.py          # NFT service
│   │   └── snapshot.py     # Portfolio snapshot service
│   └── utils/              # Utility functions
├── frontend/               # HTML/CSS/JS frontend
│   ├── index.html          # Main dashboard
│   ├── css/styles.css      # Styling
│   └── js/app.js           # Client-side logic
├── data/                   # SQLite database (auto-created)
├── docs/                   # Documentation
│   ├── ARCHITECTURE.md     # System architecture diagram
│   └── ABCT_Technical_Documentation.docx
├── Deployment/             # Deployment scripts
│   ├── setup.sh           # Initial setup script
│   └── README.md          # Deployment guide
├── .env                    # API keys (you create this)
├── requirements.txt        # Python dependencies
├── run.sh                  # Start server
└── stop.sh                 # Stop server
```

## API Endpoints

### Wallets
- `GET /wallets` - List all tracked wallets
- `POST /wallets` - Add a new wallet
- `DELETE /wallets/{id}` - Remove a wallet
- `POST /wallets/{id}/refresh` - Refresh wallet data

### Portfolio
- `GET /portfolio/summary` - Get portfolio overview
- `GET /portfolio/history?range=7d|4w|3m` - Historical values
- `POST /portfolio/snapshot` - Create manual snapshot

### Prices
- `GET /prices` - Current cryptocurrency prices

### DeFi
- `GET /defi/staking` - Cardano staking positions

### Exchanges
- `GET /exchanges/balances` - Exchange holdings

### NFTs
- `GET /nfts` - NFT collection with values
- `GET /nfts/summary` - Collections grouped
- `GET /nfts/prices/status` - Price collection status
- `POST /nfts/prices/collect` - Trigger price collection

## Configuration

### Environment Variables (.env)

```bash
# Required
BLOCKFROST_API_KEY=your_key_here

# Recommended
CEXPLORER_API_KEY=your_key_here

# Optional
TAPTOOLS_API_KEY=your_key_here
ETHERSCAN_API_KEY=your_key_here
```

### Coinbase Integration

1. Get API credentials from https://portal.cdp.coinbase.com/access/api
2. Create `cdp_api_key.json` in project root:
```json
{
    "name": "your-api-key-name",
    "privateKey": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
}
```

## Development

```bash
# Activate virtual environment
source venv/bin/activate

# Run with auto-reload
cd backend
uvicorn main:app --reload

# Run tests (if available)
pytest
```

## Security

- **Local Only**: Server binds to 127.0.0.1 by default
- **Read-Only Access**: Cannot move funds, only view balances
- **No Telemetry**: No data sent to external analytics
- **Local Database**: All data stored in local SQLite file
- **HTTPS Support**: Optional SSL/TLS encryption (v0.8.0+)
- **Centralized Logging**: Secure audit trails with sensitive data redaction
- **Input Validation**: Protection against malformed inputs
- **CORS Hardening**: Restricted cross-origin access

For detailed security information, see [SECURITY.md](SECURITY.md)

## Troubleshooting

### Server won't start
```bash
# Check if port is in use
lsof -i :8000

# Kill existing process
./stop.sh
```

### Missing data
```bash
# Refresh all wallet data
# Click the refresh button in the UI, or:
curl -X POST http://127.0.0.1:8000/wallets/1/refresh
```

### Database reset
```bash
# Backup first!
cp data/portfolio.db data/portfolio.db.backup
rm data/portfolio.db
./run.sh  # Fresh database created
```

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Chart.js](https://www.chartjs.org/) - JavaScript charting library
- [Blockfrost](https://blockfrost.io/) - Cardano API
- [CoinGecko](https://www.coingecko.com/) - Cryptocurrency prices
