"""
ABCT Configuration Module

This module centralizes all configuration settings for the ABCT application.
It loads API keys from environment variables (.env file) and defines constants
for API endpoints, file paths, and cache settings.

Environment Variables Required:
    - BLOCKFROST_API_KEY: Cardano blockchain API (required for Cardano wallets)
    - CEXPLORER_API_KEY: Cardano staking/DeFi data (optional)

    - ETHERSCAN_API_KEY: Ethereum blockchain data fallback (optional)
    - BLOCKSCOUT_API_KEY: Free Etherscan-compatible EVM transaction data (optional)

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
BEACONCHAIN_API_KEY = os.getenv("BEACONCHAIN_API_KEY", "")
MAESTRO_API_KEY = os.getenv("MAESTRO_API_KEY", "")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
BLOCKSCOUT_API_KEY = os.getenv("BLOCKSCOUT_API_KEY", "")
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
GRAPH_API_KEY = os.getenv("GRAPH_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
CHARLI3_API_KEY = os.getenv("CHARLI3_API_KEY", "")
# Deprecated — TapTools sunset. Retained for NFT service compatibility until NFT pricing is migrated.
TAPTOOLS_API_KEY = os.getenv("TAPTOOLS_API_KEY", "")
ANKR_API_KEY = os.getenv("ANKR_API_KEY", "")

# LogoKit API Configuration
LOGOKIT_API_KEY = os.getenv('LOGOKIT_API_KEY', '')
LOGOKIT_BASE_URL = 'https://img.logokit.com'

# Coinbase CDP API Key (loaded from JSON file)
# Security (Finding #1): CDP key files moved to EXCLUDE/credentials/ to keep
# private keys outside the project tree proper. EXCLUDE/ is gitignored.
CDP_API_KEY_FILE = Path(__file__).parent.parent / "EXCLUDE" / "credentials" / "cdp_api_key.json"
# Legacy fallback: check project root for backwards compatibility during migration
_CDP_API_KEY_FILE_LEGACY = Path(__file__).parent.parent / "cdp_api_key.json"
COINBASE_API_KEY_NAME = ""
COINBASE_API_PRIVATE_KEY = ""

_cdp_file_to_load = CDP_API_KEY_FILE if CDP_API_KEY_FILE.exists() else (
    _CDP_API_KEY_FILE_LEGACY if _CDP_API_KEY_FILE_LEGACY.exists() else None
)
if _cdp_file_to_load:
    try:
        with open(_cdp_file_to_load) as f:
            cdp_key = json.load(f)
            COINBASE_API_KEY_NAME = cdp_key.get("name", "")
            COINBASE_API_PRIVATE_KEY = cdp_key.get("privateKey", "")
        if _cdp_file_to_load == _CDP_API_KEY_FILE_LEGACY:
            print("Warning: CDP key found in project root (legacy location). "
                  "Move to EXCLUDE/credentials/cdp_api_key.json for security.")
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
FANTOM_RPC_URL = "https://rpcapi.fantom.network"
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
VECHAIN_THOR_URL = "https://mainnet.vechain.org"
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
MINA_GRAPHQL_URL = "https://mina-mainnet-graphql.aurowallet.com/graphql"
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

# CORS Configuration (Finding #6 — restrict cross-origin requests)
# Comma-separated list of allowed origins from .env; defaults to localhost only.
_allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins_raw.split(",") if origin.strip()]

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
    "https://dweb.link/ipfs/",
    "https://gateway.pinata.cloud/ipfs/",
]

# NFT Background Scheduler Configuration
NFT_SCHEDULER_ENABLED = os.getenv("NFT_SCHEDULER_ENABLED", "false").lower() == "true"
NFT_UPDATE_INTERVAL_MINUTES = int(os.getenv("NFT_UPDATE_INTERVAL_MINUTES", "15"))
NFT_CALLS_PER_UPDATE = int(os.getenv("NFT_CALLS_PER_UPDATE", "1"))
NFT_MAX_DAILY_CALLS = int(os.getenv("NFT_MAX_DAILY_CALLS", "95"))  # Leave buffer under 100

# Wallet Balance Background Sync Configuration (ABCT-BGSYNC-20260919)
# Kill switch defaults to OFF: this is a new job that runs continuously against
# live provider infrastructure once enabled -- ship it dark, let the user turn
# it on after confirming behavior in logs. Requires a container restart to
# change (read once at process start, same as NFT_SCHEDULER_ENABLED above).
WALLET_BGSYNC_ENABLED = os.getenv("WALLET_BGSYNC_ENABLED", "false").lower() == "true"
# One wallet_id-modulo bucket ticks per minute; a wallet's bucket is
# (wallet_id % WALLET_BGSYNC_BUCKET_COUNT), so each wallet is due once per
# WALLET_BGSYNC_BUCKET_COUNT minutes (60 = hourly, per the accepted design).
WALLET_BGSYNC_BUCKET_COUNT = int(os.getenv("WALLET_BGSYNC_BUCKET_COUNT", "60"))
# Skip a wallet whose balances row was updated more recently than this --
# avoids redundant work when a user just refreshed it themselves.
WALLET_BGSYNC_SKIP_RECENT_MINUTES = int(os.getenv("WALLET_BGSYNC_SKIP_RECENT_MINUTES", "5"))
# Wallets within one cycle's bucket are refreshed strictly one at a time with
# at least this many seconds between them -- a hard ceiling on how often this
# scheduler *starts* a new wallet's refresh, independent of provider latency
# or bucket size. See the rate-math in the task report.
WALLET_BGSYNC_DISPATCH_DELAY_SECONDS = float(os.getenv("WALLET_BGSYNC_DISPATCH_DELAY_SECONDS", "0.5"))
# Cross-process advisory lock TTL: long enough to cover a real cycle, short
# enough that a crashed holder self-heals quickly (a few missed buckets, not
# a long outage).
WALLET_BGSYNC_LOCK_TTL_MINUTES = int(os.getenv("WALLET_BGSYNC_LOCK_TTL_MINUTES", "3"))

# Balance Anomaly Guard (ABCT-BALANCE-GUARD-20260919)
# Root cause: the 2026-09-19 "vault" incident wasn't a write bug -- a wallet
# lost 78% of its stored ADA in a single legitimate refresh because 3 of its
# 11 real payment addresses were never registered with ABCT, so a correct
# fetch of only the 9 known addresses looked, from the DB's point of view,
# like a huge and completely silent drop. Nothing compared the new value to
# the old one. This guard does not fix that root cause (see
# ABCT-STAKE-REDISCOVERY-20260919) -- it makes ANY future large jump, from
# whatever cause, visible instead of silent. It never blocks or rolls back a
# write: a user legitimately moving funds out produces the exact same signal
# as a bug, and refusing that write would corrupt real data.
#
# Percentage-based, not absolute: save_balance() operates on raw per-chain
# unit amounts (ADA, BTC, DOGE, ...) with no price context available at that
# layer, so a fixed absolute threshold would be meaningless across chains
# (0.01 BTC vs 10,000 DOGE). A relative threshold catches the same class of
# incident (a large fraction of a wallet's value disappearing or appearing
# in one write) regardless of unit or chain. 50% default: rare for organic
# activity (even a large partial withdrawal is usually a smaller fraction of
# a HODL wallet's total), comfortably below the 78% drop that triggered this.
BALANCE_ANOMALY_PCT_THRESHOLD = float(os.getenv("BALANCE_ANOMALY_PCT_THRESHOLD", "0.5"))

# Cardano Stake-Key Address Rediscovery (ABCT-STAKE-REDISCOVERY-20260919)
# Root cause fix for the same incident as the guard above: ABCT tracks a
# fixed list of manually-registered payment addresses, but a Cardano
# hardware wallet's "account" is really a stake key with an open-ended,
# growing set of derived payment addresses. The existing discovery flow
# (routers/wallets.py's /discover + /add-multiple) only ever runs once, at
# add-time, on explicit user action -- any address the hardware wallet
# derives afterward is permanently invisible to ABCT with no code path that
# would ever notice it. This re-runs that same, already-correct discovery
# logic periodically per stake key the user has already registered.
#
# Kill switch defaults to OFF, matching WALLET_BGSYNC_ENABLED's precedent --
# ship dark, let the user opt in after confirming behavior in logs.
STAKE_REDISCOVERY_ENABLED = os.getenv("STAKE_REDISCOVERY_ENABLED", "false").lower() == "true"
# Daily, not hourly: a hardware wallet deriving a new receive address is a
# low-frequency event tied to user activity (initiated withdrawals/deposits
# on the device), not something that changes minute to minute like a
# balance. A day of lag before ABCT notices a newly-used address is an
# acceptable trade for a ~10x lower interval than the balance sync and a
# correspondingly lighter footprint against Blockfrost.
STAKE_REDISCOVERY_INTERVAL_HOURS = int(os.getenv("STAKE_REDISCOVERY_INTERVAL_HOURS", "24"))
# Same hard-rate-ceiling approach as WALLET_BGSYNC_DISPATCH_DELAY_SECONDS:
# items (wallets being stake-resolved, then distinct stake keys being
# queried for new addresses) are processed strictly one at a time with at
# least this many seconds between them, independent of provider latency.
# Longer than the balance sync's 0.5s because this job runs once a day, not
# once an hour, so there is no reason to hurry, and each "item" here can
# itself fan out into more than one call (stake resolution, then address
# listing, then a balance check per newly found address).
STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS = float(os.getenv("STAKE_REDISCOVERY_DISPATCH_DELAY_SECONDS", "1.0"))
# Cross-process advisory lock TTL -- longer than the balance sync's because
# a full daily pass over every registered Cardano wallet, at >=1s/item, can
# legitimately take a while for a user with many wallets.
STAKE_REDISCOVERY_LOCK_TTL_MINUTES = int(os.getenv("STAKE_REDISCOVERY_LOCK_TTL_MINUTES", "120"))

# Portfolio Quantity Cache TTL Stopgap (ABCT-SUMMARY-PERF-20260919)
# ABCT-BACKEND-QTYCACHE-20260918 tied the summary-level and per-wallet
# quantity caches to WALLET_DATA_CACHE_TTL (5 minutes, at the time equal to
# CACHE_TTL_HOT) to fix a 7-day staleness bug. Side effect discovered in
# production: for a user with many Cardano wallets, the full per-wallet
# recompute this cache guards costs ~20s (an unthrottled burst of Koios
# calls -- see ABCT-CARDANO-ACCOUNT-LEVEL-20260919 for the real fix, and
# ABCT-SUMMARY-PERF-20260919 for the throttle). At a 5-minute TTL that
# recompute now runs roughly every 5 minutes instead of roughly weekly --
# whoever's request lands on the cold window eats the full 20s, which on
# mobile exceeds the client's HTTP timeout and looks like a hard failure.
#
# This constant is now independent of CACHE_TTL_HOT (which also governs
# unrelated things -- prices, exchange balances -- that should not be
# affected by this change). 20 minutes: a 4x reduction in how often the
# expensive recompute can fire, immediate and proportional relief while the
# account-level redesign and the Koios throttle land; quantities stale for
# up to 20 minutes is a real but minor regression against the account-level
# fix's target of "as fresh as the sync makes it," and utterly minor next to
# the 7-day staleness this was fixed from. Intended to be temporary -- once
# ABCT-CARDANO-ACCOUNT-LEVEL-20260919 collapses the per-wallet fan-out to
# ~1 call per stake key, this can likely drop back toward 5 minutes.
PORTFOLIO_QUANTITY_CACHE_TTL_SECONDS = int(os.getenv("PORTFOLIO_QUANTITY_CACHE_TTL_SECONDS", "1200"))
