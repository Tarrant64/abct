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
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
CHARLI3_API_KEY = os.getenv("CHARLI3_API_KEY", "")
ANKR_API_KEY = os.getenv("ANKR_API_KEY", "")

# LogoKit API Configuration
LOGOKIT_API_KEY = os.getenv('LOGOKIT_API_KEY', '')
LOGOKIT_BASE_URL = 'https://img.logokit.com'

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

# Exchange API Keys (from environment variables)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_US_API_KEY = os.getenv("BINANCE_US_API_KEY", "")
BINANCE_US_API_SECRET = os.getenv("BINANCE_US_API_SECRET", "")
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_API_SECRET = os.getenv("OKX_API_SECRET", "")
OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE", "")
BITGET_API_KEY = os.getenv("BITGET_API_KEY", "")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET", "")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE", "")
GATE_API_KEY = os.getenv("GATE_API_KEY", "")
GATE_API_SECRET = os.getenv("GATE_API_SECRET", "")
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET", "")
KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE", "")

# New Binance-style exchanges
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET", "")
HTX_API_KEY = os.getenv("HTX_API_KEY", "")
HTX_API_SECRET = os.getenv("HTX_API_SECRET", "")
BINGX_API_KEY = os.getenv("BINGX_API_KEY", "")
BINGX_API_SECRET = os.getenv("BINGX_API_SECRET", "")
POLONIEX_API_KEY = os.getenv("POLONIEX_API_KEY", "")
POLONIEX_API_SECRET = os.getenv("POLONIEX_API_SECRET", "")
LBANK_API_KEY = os.getenv("LBANK_API_KEY", "")
LBANK_API_SECRET = os.getenv("LBANK_API_SECRET", "")
BITMART_API_KEY = os.getenv("BITMART_API_KEY", "")
BITMART_API_SECRET = os.getenv("BITMART_API_SECRET", "")
WHITEBIT_API_KEY = os.getenv("WHITEBIT_API_KEY", "")
WHITEBIT_API_SECRET = os.getenv("WHITEBIT_API_SECRET", "")
COINEX_API_KEY = os.getenv("COINEX_API_KEY", "")
COINEX_API_SECRET = os.getenv("COINEX_API_SECRET", "")
BITVAVO_API_KEY = os.getenv("BITVAVO_API_KEY", "")
BITVAVO_API_SECRET = os.getenv("BITVAVO_API_SECRET", "")
BITRUE_API_KEY = os.getenv("BITRUE_API_KEY", "")
BITRUE_API_SECRET = os.getenv("BITRUE_API_SECRET", "")
XT_API_KEY = os.getenv("XT_API_KEY", "")
XT_API_SECRET = os.getenv("XT_API_SECRET", "")
DIGIFINEX_API_KEY = os.getenv("DIGIFINEX_API_KEY", "")
DIGIFINEX_API_SECRET = os.getenv("DIGIFINEX_API_SECRET", "")
COINW_API_KEY = os.getenv("COINW_API_KEY", "")
COINW_API_SECRET = os.getenv("COINW_API_SECRET", "")
PIONEX_API_KEY = os.getenv("PIONEX_API_KEY", "")
PIONEX_API_SECRET = os.getenv("PIONEX_API_SECRET", "")

# Batch 2-5 exchanges
PHEMEX_API_KEY = os.getenv("PHEMEX_API_KEY", "")
PHEMEX_API_SECRET = os.getenv("PHEMEX_API_SECRET", "")
WOOX_API_KEY = os.getenv("WOOX_API_KEY", "")
WOOX_API_SECRET = os.getenv("WOOX_API_SECRET", "")
ASCENDEX_API_KEY = os.getenv("ASCENDEX_API_KEY", "")
ASCENDEX_API_SECRET = os.getenv("ASCENDEX_API_SECRET", "")
DERIBIT_CLIENT_ID = os.getenv("DERIBIT_CLIENT_ID", "")
DERIBIT_CLIENT_SECRET = os.getenv("DERIBIT_CLIENT_SECRET", "")
BITFLYER_API_KEY = os.getenv("BITFLYER_API_KEY", "")
BITFLYER_API_SECRET = os.getenv("BITFLYER_API_SECRET", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_SECRET = os.getenv("GEMINI_API_SECRET", "")
BITFINEX_API_KEY = os.getenv("BITFINEX_API_KEY", "")
BITFINEX_API_SECRET = os.getenv("BITFINEX_API_SECRET", "")
BTSE_API_KEY = os.getenv("BTSE_API_KEY", "")
BTSE_API_SECRET = os.getenv("BTSE_API_SECRET", "")
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY", "")
KRAKEN_API_SECRET = os.getenv("KRAKEN_API_SECRET", "")
COINSPOT_API_KEY = os.getenv("COINSPOT_API_KEY", "")
COINSPOT_API_SECRET = os.getenv("COINSPOT_API_SECRET", "")
CRYPTOCOM_API_KEY = os.getenv("CRYPTOCOM_API_KEY", "")
CRYPTOCOM_API_SECRET = os.getenv("CRYPTOCOM_API_SECRET", "")
BITSTAMP_API_KEY = os.getenv("BITSTAMP_API_KEY", "")
BITSTAMP_API_SECRET = os.getenv("BITSTAMP_API_SECRET", "")
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")
BACKPACK_API_KEY = os.getenv("BACKPACK_API_KEY", "")
BACKPACK_API_SECRET = os.getenv("BACKPACK_API_SECRET", "")
SWYFTX_API_KEY = os.getenv("SWYFTX_API_KEY", "")
BITPANDA_API_KEY = os.getenv("BITPANDA_API_KEY", "")
ROBINHOOD_ACCESS_TOKEN = os.getenv("ROBINHOOD_ACCESS_TOKEN", "")
HITBTC_API_KEY = os.getenv("HITBTC_API_KEY", "")
HITBTC_API_SECRET = os.getenv("HITBTC_API_SECRET", "")
INDRES_API_KEY = os.getenv("INDRES_API_KEY", "")
INDRES_API_SECRET = os.getenv("INDRES_API_SECRET", "")
PROBIT_CLIENT_ID = os.getenv("PROBIT_CLIENT_ID", "")
PROBIT_CLIENT_SECRET = os.getenv("PROBIT_CLIENT_SECRET", "")

# API Endpoints
BLOCKFROST_BASE_URL = os.getenv("BLOCKFROST_BASE_URL", "https://cardano-mainnet.blockfrost.io/api/v0")
BLOCKFROST_EXTERNAL_URL = os.getenv("BLOCKFROST_EXTERNAL_URL", "https://cardano-mainnet.blockfrost.io/api/v0")
CEXPLORER_BASE_URL = "https://api.cexplorer.io/v1"
BLOCKSTREAM_BASE_URL = "https://blockstream.info/api"
MEMPOOL_BASE_URL = "https://mempool.space/api"  # Fallback for Bitcoin transactions
TAPTOOLS_BASE_URL = "https://openapi.taptools.io/api/v1"
BEACONCHAIN_BASE_URL = "https://beaconcha.in/api/v1"
ALCHEMY_ETH_URL = "https://eth-mainnet.g.alchemy.com"
ALCHEMY_BASE_URL = "https://eth-mainnet.g.alchemy.com/nft/v3"
ALCHEMY_POLYGON_URL = "https://polygon-mainnet.g.alchemy.com"
ALCHEMY_BASE_URL_CHAIN = "https://base-mainnet.g.alchemy.com"
ALCHEMY_BSC_URL = "https://bnb-mainnet.g.alchemy.com"
ALCHEMY_ARBITRUM_URL = "https://arb-mainnet.g.alchemy.com"
ALCHEMY_AVALANCHE_URL = "https://avax-mainnet.g.alchemy.com"
ALCHEMY_OPTIMISM_URL = "https://opt-mainnet.g.alchemy.com"
ALCHEMY_ZKSYNC_URL = "https://zksync-mainnet.g.alchemy.com"
ALCHEMY_LINEA_URL = "https://linea-mainnet.g.alchemy.com"
ALCHEMY_SCROLL_URL = "https://scroll-mainnet.g.alchemy.com"

# Public RPC URLs for non-Alchemy EVM chains
FANTOM_RPC_URL = "https://rpc.ftm.tools"
CRONOS_RPC_URL = "https://evm.cronos.org"
GNOSIS_RPC_URL = "https://rpc.gnosischain.com"
MOONBEAM_RPC_URL = "https://rpc.api.moonbeam.network"
HELIUS_BASE_URL = "https://api.helius.xyz/v0"
HELIUS_RPC_URL = "https://mainnet.helius-rpc.com"

# TronGrid API (free, no key required)
TRONGRID_BASE_URL = "https://api.trongrid.io"

# New chain APIs (all free, no key required)
XRPL_RPC_URL = "https://xrplcluster.com"
HEDERA_MIRROR_URL = "https://mainnet-public.mirrornode.hedera.com/api/v1"
MULTIVERSX_API_URL = "https://api.multiversx.com"
SUI_RPC_URL = "https://fullnode.mainnet.sui.io:443"
APTOS_API_URL = "https://fullnode.mainnet.aptoslabs.com/v1"
GLIF_RPC_URL = "https://api.node.glif.io/rpc/v1"

# Additional chain APIs (all free, no key required)
BLOCKCYPHER_LTC_URL = "https://api.blockcypher.com/v1/ltc/main"
BLOCKCYPHER_DOGE_URL = "https://api.blockcypher.com/v1/doge/main"
BLOCKCHAIR_ZEC_URL = "https://api.blockchair.com/zcash"
TZKT_BASE_URL = "https://api.tzkt.io/v1"
HIRO_BASE_URL = "https://api.mainnet.hiro.so"
VECHAIN_THOR_URL = "https://mainnet.veblocks.net"
COSMOS_LCD_URL = "https://cosmos-rest.publicnode.com"
NEAR_RPC_URL = "https://rpc.mainnet.near.org"
NEARBLOCKS_API_URL = "https://api.nearblocks.io/v1"
ICP_ROSETTA_URL = "https://rosetta-api.internetcomputer.org"

# New chain LCD/API URLs (all free, no key required)
OSMOSIS_LCD_URL = "https://osmosis-rest.publicnode.com"
CELESTIA_LCD_URL = "https://celestia-rest.publicnode.com"
INJECTIVE_LCD_URL = "https://injective-rest.publicnode.com"
DYDX_LCD_URL = "https://dydx-rest.publicnode.com"
SEI_LCD_URL = "https://sei-rest.publicnode.com"
AKASH_LCD_URL = "https://akash-rest.publicnode.com"
TON_CENTER_URL = "https://toncenter.com/api/v2"
SUBSCAN_POLKADOT_URL = "https://polkadot.api.subscan.io"
SUBSCAN_KUSAMA_URL = "https://kusama.api.subscan.io"
STELLAR_HORIZON_URL = "https://horizon.stellar.org"
KASPA_API_URL = "https://api.kaspa.org"
KAIA_RPC_URL = "https://public-en.node.kaia.io"
ERGO_EXPLORER_URL = "https://explorer.ergoplatform.com/api/v1"
IOTA_RPC_URL = "https://api.mainnet.iota.cafe"
WAVES_NODE_URL = "https://nodes.wavesnodes.com"
MINA_GRAPHQL_URL = "https://graphql.minaexplorer.com"
ZILLIQA_API_URL = "https://api.zilliqa.com"

# Etherscan V2 unified API (single endpoint, chain selected by chainid param)
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"
# Legacy aliases (deprecated — use ETHERSCAN_V2_URL + chainid instead)
ETHERSCAN_BASE_URL = ETHERSCAN_V2_URL
BASESCAN_BASE_URL = ETHERSCAN_V2_URL
POLYGONSCAN_BASE_URL = ETHERSCAN_V2_URL
BSCSCAN_BASE_URL = ETHERSCAN_V2_URL
ARBISCAN_BASE_URL = ETHERSCAN_V2_URL
SNOWSCAN_BASE_URL = ETHERSCAN_V2_URL

# CoinMarketCap API
CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1"

# Charli3 API (Cardano token pricing + OHLCV)
CHARLI3_BASE_URL = "https://api.charli3.io/api/v1"

# CoinPaprika API (free, no key required — 25k calls/month)
COINPAPRIKA_BASE_URL = "https://api.coinpaprika.com/v1"

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

# Cache TTL Tiers (in seconds)
CACHE_TTL_HOT = 300         # 5 minutes - prices, exchange balances, wallet balances
CACHE_TTL_WARM = 3600       # 1 hour - portfolio analytics, charts, asset breakdowns
CACHE_TTL_COLD = 86400      # 24 hours - NFT data, DeFi positions
CACHE_TTL_PERSISTENT = 604800  # 7 days - portfolio summary, native assets

# Legacy alias
BALANCE_CACHE_TTL = CACHE_TTL_HOT

# NFT Image Cache Settings
# DB Sync PostgreSQL (direct read-only access — OPTIONAL)
# When DBSYNC_PG_HOST is empty/unset, direct DB access is disabled entirely.
# All existing Blockfrost code paths remain fully functional.
DBSYNC_PG_HOST = os.getenv("DBSYNC_PG_HOST", "")
DBSYNC_PG_PORT = int(os.getenv("DBSYNC_PG_PORT", "5432"))
DBSYNC_PG_DATABASE = os.getenv("DBSYNC_PG_DATABASE", "cexplorer")
DBSYNC_PG_USER = os.getenv("DBSYNC_PG_USER", "abct_readonly")
DBSYNC_PG_PASSWORD = os.getenv("DBSYNC_PG_PASSWORD", "")
DBSYNC_PG_MIN_CONNECTIONS = int(os.getenv("DBSYNC_PG_MIN_POOL", "2"))
DBSYNC_PG_MAX_CONNECTIONS = int(os.getenv("DBSYNC_PG_MAX_POOL", "10"))
DBSYNC_PG_ENABLED = bool(DBSYNC_PG_HOST)

NFT_IMAGE_CACHE_ENABLED = os.getenv("NFT_IMAGE_CACHE_ENABLED", "false").lower() == "true"
NFT_IMAGE_MAX_SIZE_MB = int(os.getenv("NFT_IMAGE_MAX_SIZE_MB", "20"))
NFT_IMAGE_THUMBNAIL_SIZE = int(os.getenv("NFT_IMAGE_THUMBNAIL_SIZE", "150"))
NFT_IMAGE_MOBILE_SIZE = int(os.getenv("NFT_IMAGE_MOBILE_SIZE", "400"))

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
