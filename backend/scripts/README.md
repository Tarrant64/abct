# ABCT Scripts

This directory contains utility scripts for managing the ABCT application.

## create_demo_account.py

Creates a demo user account with realistic fake portfolio data totaling approximately $1M.

### Features

- **Demo User Account**
  - Username: `demo`
  - Password: `demo`
  - No password change prompt on login (password_changed = 1)
  - Marked as demo account (is_demo = 1)

- **Multi-Chain Wallet Portfolio (~$465k)**
  - **Cardano** (3 wallets, ~$95k): Main wallet with 50,000 ADA + native tokens, staking wallet with 30,000 ADA, secondary wallet with 20,000 ADA
  - **Bitcoin** (2 wallets, ~$198k): Main wallet with 2.1 BTC, cold storage with 1.5 BTC
  - **Ethereum** (2 wallets, ~$120k): Main wallet with 22 ETH + ERC20 tokens, DeFi wallet with 18 ETH
  - **Solana** (2 wallets, ~$196k): Main wallet with 800 SOL + SPL tokens, NFT wallet with 600 SOL
  - **Polygon** (1 wallet, ~$30k): Main wallet with 40,000 POL
  - **Base** (1 wallet, ~$24k): Main wallet with 8 ETH

- **NFT Collections (~$135k)**
  - 15 Clay Nation NFTs (~$50k)
  - 8 The Ape Society NFTs (~$38k)
  - 12 Bored Ape Yacht Club NFTs (~$28k)
  - 20 Solana Monkey Business NFTs (~$19k)
  - Includes floor price data

- **Historical Portfolio Data**
  - 90 days of daily snapshots
  - Growth trend from ~$748k to ~$880k (17.6% growth)
  - Realistic daily volatility (±3%)
  - Includes DeFi, staking, and exchange values

### Usage

```bash
cd backend
python3 scripts/create_demo_account.py
```

### Requirements

- Python 3.7+
- bcrypt
- aiosqlite
- Initialized ABCT database (portfolio.db)

### What It Creates

1. **User Account**
   - Adds `is_demo` column to users table (if not exists)
   - Creates demo user with hashed password
   - Sets password_changed = 1 (no prompt on login)

2. **Wallets & Balances**
   - 11 wallets across 6 different blockchains
   - Native balances for each wallet
   - Native assets (tokens) for select wallets

3. **NFT Data**
   - 55 NFTs across 4 major collections
   - Floor price data from NFT marketplaces
   - Realistic collection metadata

4. **Portfolio History**
   - 90 daily portfolio snapshots
   - Tracks total value, crypto amounts, and prices
   - Includes DeFi, staking, exchange, and NFT values
   - Realistic growth trend with daily volatility

### Notes

- If demo user already exists, it will be deleted and recreated
- All data is fake and for demonstration purposes only
- The script uses realistic but approximate cryptocurrency prices
- Portfolio values may vary slightly due to random volatility generation

### Output

The script provides detailed output showing:
- Demo user creation status
- Each wallet created with its balance and value
- Each NFT collection with count and floor prices
- Historical data generation summary
- Final portfolio summary with login credentials
