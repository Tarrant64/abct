"""
ABCT Configuration Module

This module centralizes all configuration settings for the ABCT application.
It loads API keys from environment variables (.env file) and defines constants
for API endpoints, file paths, and cache settings.

Environment Variables Required:
    - BLOCKFROST_API_KEY: Cardano blockchain API (required for Cardano wallets)
    - CEXPLORER_API_KEY: Cardano staking/DeFi data (optional)
    - TAPTOOLS_API_KEY: NFT floor prices (optional)
    - ETHERSCAN_API_KEY: Ethereum blockchain data (optional)

Coinbase Integration:
    - Requires cdp_api_key.json file in project root with 'name' and 'privateKey'
    - Obtain from https://coinbase.com/settings/api

Usage:
    from config import BLOCKFROST_API_KEY, DATABASE_PATH
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
load_dotenv(Path(__file__).parent.parent / ".env")

# API Keys
BLOCKFROST_API_KEY = os.getenv("BLOCKFROST_API_KEY", "")
CEXPLORER_API_KEY = os.getenv("CEXPLORER_API_KEY", "")
TAPTOOLS_API_KEY = os.getenv("TAPTOOLS_API_KEY", "")
BEACONCHAIN_API_KEY = os.getenv("BEACONCHAIN_API_KEY", "")
MAESTRO_API_KEY = os.getenv("MAESTRO_API_KEY", "")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
CMC_API_KEY = os.getenv("CMC_API_KEY", "")

# Coinbase CDP API Key (loaded from JSON file)
CDP_API_KEY_FILE = Path(__file__).parent.parent / "cdp_api_key.json"
COINBASE_API_KEY_NAME = ""
COINBASE_API_PRIVATE_KEY = ""

if CDP_API_KEY_FILE.exists():
    try:
        with open(CDP_API_KEY_FILE) as f:
            cdp_key = json.load(f)
            COINBASE_API_KEY_NAME = cdp_key.get("name", "")
            COINBASE_API_PRIVATE_KEY = cdp_key.get("privateKey", "")
    except Exception as e:
        print(f"Warning: Failed to load CDP API key: {e}")

# API Endpoints
BLOCKFROST_BASE_URL = "https://cardano-mainnet.blockfrost.io/api/v0"
CEXPLORER_BASE_URL = "https://api.cexplorer.io/v1"
BLOCKSTREAM_BASE_URL = "https://blockstream.info/api"
TAPTOOLS_BASE_URL = "https://openapi.taptools.io/api/v1"
BEACONCHAIN_BASE_URL = "https://beaconcha.in/api/v1"
ALCHEMY_BASE_URL = "https://eth-mainnet.g.alchemy.com/nft/v3"
ALCHEMY_POLYGON_URL = "https://polygon-mainnet.g.alchemy.com"
ALCHEMY_BASE_URL_CHAIN = "https://base-mainnet.g.alchemy.com"
HELIUS_BASE_URL = "https://api.helius.xyz/v0"
HELIUS_RPC_URL = "https://mainnet.helius-rpc.com"

# Etherscan API endpoints (same format works for Basescan, Polygonscan, etc.)
ETHERSCAN_BASE_URL = "https://api.etherscan.io/api"
BASESCAN_BASE_URL = "https://api.basescan.org/api"
POLYGONSCAN_BASE_URL = "https://api.polygonscan.com/api"

# CoinMarketCap API
CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1"

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
WALLETS_FILE = DATA_DIR / "wallets.txt"
DATABASE_PATH = DATA_DIR / "portfolio.db"
NFT_IMAGE_DB_PATH = DATA_DIR / "nft_images.db"

# SSL/HTTPS Configuration
CERTS_DIR = DATA_DIR / "certs"
DEFAULT_CERT_PATH = CERTS_DIR / "server.crt"
DEFAULT_KEY_PATH = CERTS_DIR / "server.key"

# Cache settings (in seconds)
BALANCE_CACHE_TTL = 300  # 5 minutes

# NFT Image Cache Settings
NFT_IMAGE_CACHE_ENABLED = os.getenv("NFT_IMAGE_CACHE_ENABLED", "false").lower() == "true"
NFT_IMAGE_MAX_SIZE_MB = int(os.getenv("NFT_IMAGE_MAX_SIZE_MB", "5"))
NFT_IMAGE_THUMBNAIL_SIZE = int(os.getenv("NFT_IMAGE_THUMBNAIL_SIZE", "150"))

# IPFS Gateways (fallback order)
IPFS_GATEWAYS = [
    "https://ipfs.io/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
]

# NFT Background Scheduler Configuration
NFT_SCHEDULER_ENABLED = os.getenv("NFT_SCHEDULER_ENABLED", "false").lower() == "true"
NFT_UPDATE_INTERVAL_MINUTES = int(os.getenv("NFT_UPDATE_INTERVAL_MINUTES", "15"))
NFT_CALLS_PER_UPDATE = int(os.getenv("NFT_CALLS_PER_UPDATE", "1"))
NFT_MAX_DAILY_CALLS = int(os.getenv("NFT_MAX_DAILY_CALLS", "95"))  # Leave buffer under 100
