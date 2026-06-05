"""
Settings Router - API Key Management

Provides endpoints for managing API keys and their enabled status.
API keys are stored in the database and can override environment variables.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_all_api_settings, get_api_setting, save_api_setting, delete_api_setting,
    update_api_enabled_status, get_api_key, update_api_health,
    get_api_usage, get_all_api_usage, get_api_rate_limit, save_api_rate_limit,
    delete_api_rate_limit, get_all_api_rate_limits
)
from auth_utils import verify_session
from services.http_client import get_client

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)

# API Registry - defines all supported APIs with metadata
# Default rate limits are for free tiers; users can customize via the UI
API_REGISTRY = {
    # Cardano APIs
    "blockfrost": {
        "name": "Blockfrost",
        "category": "cardano",
        "description": "Primary Cardano blockchain API for wallet balances, transactions, and staking info",
        "required": True,
        "docs_url": "https://blockfrost.io/",
        "env_var": "BLOCKFROST_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 50,000 requests/day, 10 requests/sec, burst of 500 requests",
        "default_limit": 50000,  # 50k requests per day on free tier
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "10 req/sec, 500 burst",
        "rate_limit_type": "quota"
    },
    "taptools": {
        "name": "TapTools",
        "category": "cardano",
        "description": "Cardano NFT floor prices only (use nftcdn/nmkr for metadata)",
        "required": False,
        "docs_url": "https://www.taptools.io/",
        "env_var": "TAPTOOLS_API_KEY",
        "pricing": "paid",
        "pricing_note": "$9/mo plan: 100 requests/day",
        "default_limit": 100,  # $9/mo plan limit
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "~100 req/day on $9/mo plan",
        "rate_limit_type": "quota"
    },
    "nftcdn": {
        "name": "NFT CDN",
        "category": "cardano",
        "description": "Cardano NFT metadata and images (prioritized over TapTools)",
        "required": False,
        "docs_url": "https://nftcdn.io/doc",
        "env_var": "NFTCDN_API_KEY",
        "pricing": "paid",
        "pricing_note": "Paid service for NFT metadata and images",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Paid service, limits not documented",
        "rate_limit_type": "none"
    },
    "nmkr": {
        "name": "NMKR Studio",
        "category": "cardano",
        "description": "Cardano NFT metadata via NMKR Studio API (prioritized over TapTools)",
        "required": False,
        "docs_url": "https://studio-api.nmkr.io/swagger/index.html",
        "env_var": "NMKR_API_KEY",
        "pricing": "free",
        "pricing_note": "Free API access for NFT metadata",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Limits not documented",
        "rate_limit_type": "none"
    },
    "cexplorer": {
        "name": "CExplorer",
        "category": "cardano",
        "description": "Cardano staking and DeFi data",
        "required": False,
        "docs_url": "https://cexplorer.io/",
        "env_var": "CEXPLORER_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier available, limits not documented",
        "default_limit": None,  # Not documented
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Limits not documented",
        "rate_limit_type": "none"
    },
    "charli3": {
        "name": "Charli3",
        "category": "cardano",
        "description": "Cardano token pricing, OHLCV history, and DEX analytics",
        "required": False,
        "docs_url": "https://charli3.io/",
        "env_var": "CHARLI3_API_KEY",
        "pricing": "freemium",
        "pricing_note": "Freemium: generous free tier for token pricing",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Limits not documented",
        "rate_limit_type": "none"
    },
    "maestro": {
        "name": "Maestro",
        "category": "cardano",
        "description": "Alternative Cardano API for redundancy",
        "required": False,
        "docs_url": "https://www.gomaestro.org/",
        "env_var": "MAESTRO_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 500,000 credits/mo (credits vary per call)",
        "default_limit": None,  # Credits vary per call type
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "500K credits/mo (cost varies by endpoint)",
        "rate_limit_type": "none"
    },

    # EVM APIs (Ethereum, Polygon, Base)
    "alchemy": {
        "name": "Alchemy",
        "category": "evm",
        "description": "Ethereum, Polygon, and Base wallet data, NFTs, and token balances",
        "required": False,
        "docs_url": "https://www.alchemy.com/",
        "env_var": "ALCHEMY_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 30M compute units/mo (~1.8M simple requests)",
        "default_limit": 60000,  # ~30M CU / 30 days = 1M CU/day = ~60k simple requests/day (conservative)
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "500 CU/sec",
        "rate_limit_type": "quota"
    },
    "etherscan": {
        "name": "Etherscan",
        "category": "evm",
        "description": "Ethereum blockchain explorer API for transaction data",
        "required": False,
        "docs_url": "https://etherscan.io/apis",
        "env_var": "ETHERSCAN_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 5 calls/sec, 100,000 calls/day",
        "default_limit": 100000,  # 100k calls per day
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "5 req/sec",
        "rate_limit_type": "quota"
    },
    "blockscout": {
        "name": "Blockscout PRO",
        "category": "evm",
        "description": "Free Etherscan-compatible multichain EVM explorer API for transaction data",
        "required": False,
        "docs_url": "https://docs.blockscout.com/devs/migrate-from-etherscan",
        "env_var": "BLOCKSCOUT_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier available across supported Blockscout PRO chains",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "5 req/sec on free tier",
        "rate_limit_type": "none"
    },
    "beaconchain": {
        "name": "Beaconchain",
        "category": "evm",
        "description": "Ethereum staking and validator data",
        "required": False,
        "docs_url": "https://beaconcha.in/",
        "env_var": "BEACONCHAIN_API_KEY",
        "pricing": "freemium",
        "pricing_note": "Free tier limited; Premium from $5/mo",
        "default_limit": None,  # Not clearly documented
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Limits vary by plan",
        "rate_limit_type": "none"
    },

    # Solana APIs
    "helius": {
        "name": "Helius",
        "category": "solana",
        "description": "Solana wallet balances, tokens, and NFTs",
        "required": False,
        "docs_url": "https://helius.xyz/",
        "env_var": "HELIUS_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 1M credits/mo, 10 RPS rate limit",
        "default_limit": 33333,  # ~1M credits / 30 days = 33k credits/day
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "10 RPS (RPC), 2 RPS (DAS/Enhanced)",
        "rate_limit_type": "quota"
    },
    "moralis": {
        "name": "Moralis",
        "category": "services",
        "description": "Spam token detection for EVM and Solana chains (on-demand filtering)",
        "required": False,
        "docs_url": "https://docs.moralis.com/web3-data-api/evm/spam-detection",
        "env_var": "MORALIS_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 40,000 compute units/month",
        "default_limit": 1333,  # ~40k CU / 30 days = 1333 CU/day
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "1,000 CU/sec",
        "rate_limit_type": "quota"
    },

    # Pricing APIs
    "coingecko": {
        "name": "CoinGecko",
        "category": "pricing",
        "description": "Cryptocurrency price data (works without key, key increases limits)",
        "required": False,
        "docs_url": "https://www.coingecko.com/en/api",
        "pricing": "free",
        "pricing_note": "Demo API (free): 30 calls/min, 10,000 calls/month",
        "env_var": "COINGECKO_API_KEY",
        "default_limit": 333,  # 10k/month ≈ 333/day
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "30 calls/min",
        "rate_limit_type": "quota"
    },
    "coinmarketcap": {
        "name": "CoinMarketCap",
        "category": "pricing",
        "description": "Alternative cryptocurrency price data",
        "required": False,
        "docs_url": "https://coinmarketcap.com/api/",
        "env_var": "CMC_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 10,000 calls/mo",
        "default_limit": 333,  # ~10k/month = 333/day
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-minute throttle",
        "rate_limit_type": "quota"
    },

    # Data & Analytics APIs
    "thegraph": {
        "name": "The Graph",
        "category": "services",
        "description": "Decentralized protocol for indexing and querying blockchain data",
        "required": False,
        "docs_url": "https://thegraph.com/studio/apikeys/",
        "env_var": "GRAPH_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 100,000 queries/mo",
        "default_limit": 3333,  # ~100k/month = 3333/day
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Rate-limited on free subgraphs",
        "rate_limit_type": "quota"
    },

    # Service APIs
    "logokit": {
        "name": "LogoKit",
        "category": "services",
        "description": "Logo and icon service for crypto tokens and brands",
        "required": False,
        "docs_url": "https://logokit.com/",
        "env_var": "LOGOKIT_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier available",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Limits not documented",
        "rate_limit_type": "none"
    },
    "logostream": {
        "name": "Logostream",
        "category": "services",
        "description": "Crypto token and coin logo API with chain-specific lookups",
        "required": False,
        "docs_url": "https://logostream.dev/documentation",
        "env_var": "LOGOSTREAM_API_KEY",
        "pricing": "freemium",
        "pricing_note": "Free tier: 100 requests/month",
        "default_limit": 100,
        "default_period": 2592000,
        "period_label": "month",
        "rate_limit_note": "10 req/min",
        "rate_limit_type": "quota"
    },

    # Exchange APIs
    "coinbase": {
        "name": "Coinbase",
        "category": "exchanges",
        "description": "Track Coinbase exchange balances (requires CDP API key JSON file)",
        "required": False,
        "docs_url": "https://docs.cdp.coinbase.com/coinbase-app/docs/welcome",
        "env_var": "COINBASE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "requires_file_upload": True,
        "file_upload_hint": "Upload CDP API key JSON file (contains 'name' and 'privateKey' fields)",
        "rate_limit_note": "No documented read limits",
        "rate_limit_type": "rate"
    },
    "binance": {
        "name": "Binance.com",
        "category": "exchanges",
        "description": "Track Binance.com exchange balances",
        "required": False,
        "docs_url": "https://www.binance.com/en/my/settings/api-management",
        "env_var": "BINANCE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": 6000,
        "default_period": 60,
        "period_label": "minute",
        "rate_limit_note": "6,000 weight/min",
        "rate_limit_type": "rate",
        "requires_secret": True
    },
    "binance_us": {
        "name": "Binance.US",
        "category": "exchanges",
        "description": "Track Binance.US exchange balances",
        "required": False,
        "docs_url": "https://www.binance.us/en/usercenter/settings/api-management",
        "env_var": "BINANCE_US_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": 6000,
        "default_period": 60,
        "period_label": "minute",
        "rate_limit_note": "6,000 weight/min",
        "rate_limit_type": "rate",
        "requires_secret": True
    },
    "okx": {
        "name": "OKX",
        "category": "exchanges",
        "description": "Track OKX exchange balances",
        "required": False,
        "docs_url": "https://www.okx.com/account/my-api",
        "env_var": "OKX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "10-20 req/2sec per endpoint",
        "rate_limit_type": "rate"
    },
    "bitget": {
        "name": "Bitget",
        "category": "exchanges",
        "description": "Track Bitget exchange balances",
        "required": False,
        "docs_url": "https://www.bitget.com/en/account/newapi",
        "env_var": "BITGET_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "6,000 req/min",
        "rate_limit_type": "rate"
    },
    "gate": {
        "name": "Gate.io",
        "category": "exchanges",
        "description": "Track Gate.io exchange balances",
        "required": False,
        "docs_url": "https://www.gate.io/myaccount/apiv4keys",
        "env_var": "GATE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate"
    },
    "kucoin": {
        "name": "KuCoin",
        "category": "exchanges",
        "description": "Track KuCoin exchange balances",
        "required": False,
        "docs_url": "https://www.kucoin.com/account/api",
        "env_var": "KUCOIN_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Resource pool per 30sec",
        "rate_limit_type": "rate"
    },

    # New Binance-style exchanges
    "bybit": {
        "name": "Bybit",
        "category": "exchanges",
        "description": "Track Bybit exchange balances",
        "required": False,
        "docs_url": "https://www.bybit.com/app/user/api-management",
        "env_var": "BYBIT_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "120 req/sec",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "mexc": {
        "name": "MEXC",
        "category": "exchanges",
        "description": "Track MEXC exchange balances",
        "required": False,
        "docs_url": "https://www.mexc.com/user/openapi",
        "env_var": "MEXC_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "20 req/2sec per endpoint",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "htx": {
        "name": "HTX",
        "category": "exchanges",
        "description": "Track HTX (Huobi) exchange balances",
        "required": False,
        "docs_url": "https://www.htx.com/en-us/apikey/",
        "env_var": "HTX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "10 req/sec",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bingx": {
        "name": "BingX",
        "category": "exchanges",
        "description": "Track BingX exchange balances",
        "required": False,
        "docs_url": "https://bingx.com/en-us/account/api",
        "env_var": "BINGX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "poloniex": {
        "name": "Poloniex",
        "category": "exchanges",
        "description": "Track Poloniex exchange balances",
        "required": False,
        "docs_url": "https://poloniex.com/user/apiKeys",
        "env_var": "POLONIEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "200 req/sec",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "lbank": {
        "name": "LBank",
        "category": "exchanges",
        "description": "Track LBank exchange balances",
        "required": False,
        "docs_url": "https://www.lbank.com/en-US/openapi/",
        "env_var": "LBANK_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bitmart": {
        "name": "BitMart",
        "category": "exchanges",
        "description": "Track BitMart exchange balances",
        "required": False,
        "docs_url": "https://developer-pro.bitmart.com/en/spot/",
        "env_var": "BITMART_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "1200 req/min",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "whitebit": {
        "name": "WhiteBIT",
        "category": "exchanges",
        "description": "Track WhiteBIT exchange balances",
        "required": False,
        "docs_url": "https://whitebit.com/en/trade-setting/api/create",
        "env_var": "WHITEBIT_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "1200 req/min",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "coinex": {
        "name": "CoinEx",
        "category": "exchanges",
        "description": "Track CoinEx exchange balances",
        "required": False,
        "docs_url": "https://www.coinex.com/en/apiKeys",
        "env_var": "COINEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bitvavo": {
        "name": "Bitvavo",
        "category": "exchanges",
        "description": "Track Bitvavo exchange balances",
        "required": False,
        "docs_url": "https://account.bitvavo.com/user/api",
        "env_var": "BITVAVO_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "1000 req/min",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bitrue": {
        "name": "Bitrue",
        "category": "exchanges",
        "description": "Track Bitrue exchange balances",
        "required": False,
        "docs_url": "https://www.bitrue.com/user/api",
        "env_var": "BITRUE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "xt": {
        "name": "XT.com",
        "category": "exchanges",
        "description": "Track XT.com exchange balances",
        "required": False,
        "docs_url": "https://xt.com/en/api-management",
        "env_var": "XT_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "digifinex": {
        "name": "DigiFinex",
        "category": "exchanges",
        "description": "Track DigiFinex exchange balances",
        "required": False,
        "docs_url": "https://openapi.digifinex.com/",
        "env_var": "DIGIFINEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "coinw": {
        "name": "CoinW",
        "category": "exchanges",
        "description": "Track CoinW exchange balances",
        "required": False,
        "docs_url": "https://www.coinw.com/front/api",
        "env_var": "COINW_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "pionex": {
        "name": "Pionex",
        "category": "exchanges",
        "description": "Track Pionex exchange balances",
        "required": False,
        "docs_url": "https://www.pionex.com/en/apiKey",
        "env_var": "PIONEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },

    # Batch 2: OKX-style exchanges
    "phemex": {
        "name": "Phemex",
        "category": "exchanges",
        "description": "Track Phemex exchange balances",
        "required": False,
        "docs_url": "https://phemex.com/user-center/api-management",
        "env_var": "PHEMEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "woox": {
        "name": "WOO X",
        "category": "exchanges",
        "description": "Track WOO X exchange balances",
        "required": False,
        "docs_url": "https://woo.org/en/trade/api-management",
        "env_var": "WOOX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "ascendex": {
        "name": "AscendEX",
        "category": "exchanges",
        "description": "Track AscendEX exchange balances",
        "required": False,
        "docs_url": "https://ascendex.com/en/account/api-management",
        "env_var": "ASCENDEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "deribit": {
        "name": "Deribit",
        "category": "exchanges",
        "description": "Track Deribit exchange balances (crypto derivatives)",
        "required": False,
        "docs_url": "https://www.deribit.com/account/BTC/api",
        "env_var": "DERIBIT_CLIENT_ID",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bitflyer": {
        "name": "BitFlyer",
        "category": "exchanges",
        "description": "Track BitFlyer exchange balances",
        "required": False,
        "docs_url": "https://bitflyer.com/en-jp/developer",
        "env_var": "BITFLYER_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },

    # Batch 3: Gemini-style exchanges
    "gemini": {
        "name": "Gemini",
        "category": "exchanges",
        "description": "Track Gemini exchange balances",
        "required": False,
        "docs_url": "https://exchange.gemini.com/settings/api",
        "env_var": "GEMINI_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bitfinex": {
        "name": "Bitfinex",
        "category": "exchanges",
        "description": "Track Bitfinex exchange balances",
        "required": False,
        "docs_url": "https://setting.bitfinex.com/api",
        "env_var": "BITFINEX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "btse": {
        "name": "BTSE",
        "category": "exchanges",
        "description": "Track BTSE exchange balances",
        "required": False,
        "docs_url": "https://www.btse.com/en/api",
        "env_var": "BTSE_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },

    # Batch 4: HMAC-SHA512 exchanges
    "kraken": {
        "name": "Kraken",
        "category": "exchanges",
        "description": "Track Kraken exchange balances",
        "required": False,
        "docs_url": "https://www.kraken.com/u/security/api",
        "env_var": "KRAKEN_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "15 calls/min per tier",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "coinspot": {
        "name": "CoinSpot",
        "category": "exchanges",
        "description": "Track CoinSpot exchange balances (Australia)",
        "required": False,
        "docs_url": "https://www.coinspot.com.au/api",
        "env_var": "COINSPOT_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },

    # Batch 5: Special auth exchanges
    "cryptocom": {
        "name": "Crypto.com",
        "category": "exchanges",
        "description": "Track Crypto.com Exchange balances",
        "required": False,
        "docs_url": "https://exchange.crypto.com/",
        "env_var": "CRYPTOCOM_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "bitstamp": {
        "name": "Bitstamp",
        "category": "exchanges",
        "description": "Track Bitstamp exchange balances",
        "required": False,
        "docs_url": "https://www.bitstamp.net/account/security/api/",
        "env_var": "BITSTAMP_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "8,000 req/10min",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "upbit": {
        "name": "Upbit",
        "category": "exchanges",
        "description": "Track Upbit exchange balances (Korea)",
        "required": False,
        "docs_url": "https://upbit.com/service_center/open_api_guide",
        "env_var": "UPBIT_ACCESS_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "backpack": {
        "name": "Backpack",
        "category": "exchanges",
        "description": "Track Backpack Exchange balances",
        "required": False,
        "docs_url": "https://backpack.exchange/portfolio/api-keys",
        "env_var": "BACKPACK_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "swyftx": {
        "name": "Swyftx",
        "category": "exchanges",
        "description": "Track Swyftx exchange balances (Australia)",
        "required": False,
        "docs_url": "https://swyftx.com/au/trade/api-management/",
        "env_var": "SWYFTX_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key"],
        "requires_secret": False
    },
    "bitpanda": {
        "name": "Bitpanda",
        "category": "exchanges",
        "description": "Track Bitpanda Pro exchange balances",
        "required": False,
        "docs_url": "https://exchange.bitpanda.com/account/api",
        "env_var": "BITPANDA_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key"],
        "requires_secret": False
    },
    "robinhood": {
        "name": "Robinhood",
        "category": "exchanges",
        "description": "Track Robinhood balances via OAuth2 access token",
        "required": False,
        "docs_url": "https://robinhood.com/",
        "env_var": "ROBINHOOD_ACCESS_TOKEN",
        "pricing": "free",
        "pricing_note": "Uses OAuth2 access token from session",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Unofficial API, no documented limits",
        "rate_limit_type": "none",
        "fields": ["api_key"],
        "requires_secret": False
    },
    "hitbtc": {
        "name": "HitBTC",
        "category": "exchanges",
        "description": "Track HitBTC exchange balances",
        "required": False,
        "docs_url": "https://api.hitbtc.com/",
        "env_var": "HITBTC_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "independentreserve": {
        "name": "Independent Reserve",
        "category": "exchanges",
        "description": "Track Independent Reserve exchange balances (Australia/NZ)",
        "required": False,
        "docs_url": "https://www.independentreserve.com/en/api",
        "env_var": "INDRES_API_KEY",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },
    "probit": {
        "name": "ProBit",
        "category": "exchanges",
        "description": "Track ProBit exchange balances",
        "required": False,
        "docs_url": "https://www.probit.com/en-us/account-setting/api-management",
        "env_var": "PROBIT_CLIENT_ID",
        "pricing": "free",
        "pricing_note": "Read-only API access (no trading)",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Per-endpoint limits",
        "rate_limit_type": "rate",
        "fields": ["api_key", "api_secret"],
        "requires_secret": True
    },

    # TradFi / Market Data APIs
    "alphavantage": {
        "name": "Alpha Vantage",
        "category": "pricing",
        "description": "Traditional finance data (S&P 500, NASDAQ, Dow Jones, BTC ETF) for cross-asset analytics",
        "required": False,
        "docs_url": "https://www.alphavantage.co/support/#api-key",
        "env_var": "ALPHAVANTAGE_API_KEY",
        "pricing": "free",
        "pricing_note": "Free tier: 25 requests/day, 5 requests/minute",
        "default_limit": 25,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "5 req/min, 25 req/day",
        "rate_limit_type": "quota"
    },

    # Layer 1 APIs
    "ton_center": {
        "name": "TON Center",
        "category": "services",
        "description": "TON blockchain balances and Jetton token data. Optional key for higher rate limits",
        "required": False,
        "docs_url": "https://toncenter.com/api/v2",
        "env_var": "TON_CENTER_API_KEY",
        "pricing": "free",
        "pricing_note": "Free public API, optional key for higher limits",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "1 req/sec without key, 10 req/sec with key",
        "rate_limit_type": "rate"
    },
    "subscan": {
        "name": "Subscan",
        "category": "services",
        "description": "Polkadot DOT and Kusama KSM balances and token data. Optional key for higher rate limits",
        "required": False,
        "docs_url": "https://docs.subscan.io/",
        "env_var": "SUBSCAN_API_KEY",
        "pricing": "free",
        "pricing_note": "Free public API, optional key for higher limits",
        "default_limit": None,
        "default_period": 86400,
        "period_label": "day",
        "rate_limit_note": "Rate-limited on free tier",
        "rate_limit_type": "rate"
    },
}

# Category labels for grouping
CATEGORIES = {
    "cardano": {
        "name": "Cardano",
        "description": "APIs for Cardano blockchain data",
        "icon": "ADA"
    },
    "evm": {
        "name": "EVM Chains",
        "description": "APIs for Ethereum, Polygon, and Base",
        "icon": "ETH"
    },
    "solana": {
        "name": "Solana",
        "description": "APIs for Solana blockchain data",
        "icon": "SOL"
    },
    "pricing": {
        "name": "Pricing",
        "description": "Cryptocurrency price data providers",
        "icon": "$"
    },
    "services": {
        "name": "Services",
        "description": "Analytics, utilities, and supporting services for crypto tracking",
        "icon": "🛠️"
    },
    "exchanges": {
        "name": "Exchanges",
        "description": "Cryptocurrency exchange integrations",
        "icon": "🏦"
    }
}


class APIKeyUpdate(BaseModel):
    api_key: str
    api_secret: Optional[str] = None  # For exchange APIs
    api_passphrase: Optional[str] = None  # For some exchange APIs (OKX, Bitget, KuCoin)


class APIEnabledUpdate(BaseModel):
    enabled: bool


@router.get("/apis")
async def list_apis():
    """
    List all supported APIs with their current status.
    Returns APIs grouped by category with enabled/configured status.
    """
    # Get saved settings from database
    saved_settings = await get_all_api_settings()
    saved_map = {s['api_name']: s for s in saved_settings}

    # Build response with all APIs
    apis_by_category = {}

    for api_id, api_info in API_REGISTRY.items():
        category = api_info['category']
        if category not in apis_by_category:
            apis_by_category[category] = {
                **CATEGORIES.get(category, {"name": category, "description": "", "icon": ""}),
                "apis": []
            }

        # Check if enabled in database or has env var
        saved = saved_map.get(api_id)
        env_key = os.getenv(api_info['env_var'], "")

        # Determine status
        if saved:
            enabled = bool(saved.get('enabled'))
            has_key = bool(saved.get('api_key'))
            source = "database"
        elif env_key:
            enabled = True
            has_key = True
            source = "environment"
        else:
            enabled = False
            has_key = False
            source = None

        apis_by_category[category]["apis"].append({
            "id": api_id,
            "name": api_info['name'],
            "description": api_info['description'],
            "required": api_info['required'],
            "docs_url": api_info['docs_url'],
            "enabled": enabled,
            "configured": has_key,
            "source": source,
            "requires_secret": api_info.get('requires_secret', False),
            "requires_passphrase": api_info.get('requires_passphrase', False),
            "requires_file_upload": api_info.get('requires_file_upload', False),
            "file_upload_hint": api_info.get('file_upload_hint'),
            "placeholder": api_info.get('placeholder'),
            "secret_placeholder": api_info.get('secret_placeholder'),
            "pricing": api_info.get('pricing', 'unknown'),
            "last_test_status": saved.get('last_test_status') if saved else None,
            "last_test_message": saved.get('last_test_message') if saved else None,
            "last_tested_at": saved.get('last_tested_at') if saved else None,
        })

    return {
        "categories": apis_by_category,
        "total_apis": len(API_REGISTRY),
        "configured_count": sum(1 for c in apis_by_category.values() for a in c['apis'] if a['configured'])
    }


@router.get("/apis/{api_id}")
async def get_api_status(api_id: str):
    """Get status of a specific API."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    api_info = API_REGISTRY[api_id]
    saved = await get_api_setting(api_id)
    env_key = os.getenv(api_info['env_var'], "")

    if saved:
        enabled = bool(saved.get('enabled'))
        has_key = bool(saved.get('api_key'))
        # Mask the key for display
        key_preview = saved['api_key'][:4] + "..." + saved['api_key'][-4:] if saved.get('api_key') and len(saved['api_key']) > 8 else "****"
        source = "database"
    elif env_key:
        enabled = True
        has_key = True
        key_preview = env_key[:4] + "..." + env_key[-4:] if len(env_key) > 8 else "****"
        source = "environment"
    else:
        enabled = False
        has_key = False
        key_preview = None
        source = None

    return {
        "id": api_id,
        **api_info,
        "enabled": enabled,
        "configured": has_key,
        "key_preview": key_preview,
        "source": source,
        "last_test_status": saved.get('last_test_status') if saved else None,
        "last_test_message": saved.get('last_test_message') if saved else None,
        "last_tested_at": saved.get('last_tested_at') if saved else None,
    }


@router.put("/apis/{api_id}")
async def enable_api(api_id: str, data: APIKeyUpdate, user_id: int = Depends(verify_session)):
    """Enable an API and save its key. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    api_key = data.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    # Get optional secret and passphrase (for exchange APIs)
    api_secret = data.api_secret.strip() if data.api_secret else None
    api_passphrase = data.api_passphrase.strip() if data.api_passphrase else None

    await save_api_setting(api_id, api_key, enabled=True, user_id=user_id,
                          api_secret=api_secret, api_passphrase=api_passphrase)

    # Test the API key after saving
    from services.api_health import run_api_test
    test_result = await run_api_test(api_id, api_key, api_secret, api_passphrase)
    await update_api_health(api_id, user_id, test_result)

    api_name = API_REGISTRY[api_id]['name']

    if test_result.get("tested") and not test_result.get("success"):
        # Test failed — auto-disable the API
        await update_api_enabled_status(api_id, False, user_id=user_id)
        return {
            "message": f"{api_name} API saved but test FAILED — auto-disabled. {test_result.get('message', '')}",
            "api_id": api_id,
            "enabled": False,
            "test_result": test_result
        }

    if test_result.get("tested"):
        msg = f"{api_name} API enabled and verified"
    else:
        msg = f"{api_name} API enabled (no test available)"

    return {
        "message": msg,
        "api_id": api_id,
        "enabled": True,
        "test_result": test_result
    }


@router.patch("/apis/{api_id}/enabled")
async def toggle_api_enabled(api_id: str, data: APIEnabledUpdate, user_id: int = Depends(verify_session)):
    """Toggle API enabled/disabled status without changing the key. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    success = await update_api_enabled_status(api_id, data.enabled, user_id=user_id)

    if not success:
        raise HTTPException(status_code=400, detail="API key not configured. Please save an API key first.")

    return {
        "message": f"{API_REGISTRY[api_id]['name']} API {'enabled' if data.enabled else 'disabled'}",
        "api_id": api_id,
        "enabled": data.enabled
    }


@router.delete("/apis/{api_id}")
async def disable_api(api_id: str, user_id: int = Depends(verify_session)):
    """Disable an API and clear its saved key. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    await delete_api_setting(api_id, user_id=user_id)

    return {
        "message": f"{API_REGISTRY[api_id]['name']} API disabled",
        "api_id": api_id,
        "enabled": False
    }


@router.post("/apis/{api_id}/upload")
async def upload_api_file(api_id: str, file: UploadFile = File(...), user_id: int = Depends(verify_session)):
    """
    Upload a configuration file for APIs that require file-based credentials (e.g., Coinbase CDP).
    The file contents will be stored as a JSON string in the api_settings table.
    Requires authentication.
    """
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    api_info = API_REGISTRY[api_id]
    if not api_info.get('requires_file_upload'):
        raise HTTPException(status_code=400, detail=f"{api_info['name']} does not accept file uploads")

    # Validate file type (JSON only for now)
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only JSON files are accepted")

    # Read and parse JSON file
    try:
        contents = await file.read()
        credentials = json.loads(contents.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Validate structure for Coinbase CDP (must have 'name' and 'privateKey')
    if api_id == 'coinbase':
        if 'name' not in credentials or 'privateKey' not in credentials:
            raise HTTPException(
                status_code=400,
                detail="Invalid CDP API key file. Must contain 'name' and 'privateKey' fields"
            )

    # Store as JSON string in database
    api_key_json = json.dumps(credentials)
    await save_api_setting(api_id, api_key_json, enabled=True, user_id=user_id)

    # Test the API after saving
    from services.api_health import run_api_test
    test_result = await run_api_test(api_id, api_key_json)
    await update_api_health(api_id, user_id, test_result)

    if test_result.get("tested") and not test_result.get("success"):
        await update_api_enabled_status(api_id, False, user_id=user_id)
        return {
            "message": f"{api_info['name']} credentials uploaded but test FAILED — auto-disabled. {test_result.get('message', '')}",
            "api_id": api_id,
            "enabled": False,
            "test_result": test_result
        }

    return {
        "message": f"{api_info['name']} credentials uploaded and verified",
        "api_id": api_id,
        "enabled": True,
        "test_result": test_result
    }


@router.get("/apis/{api_id}/test")
async def test_api(api_id: str):
    """Test if an API key is valid by making a simple request."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    # Get the effective API key (database or env)
    api_key = await get_effective_api_key(api_id)
    if not api_key:
        return {
            "api_id": api_id,
            "success": False,
            "tested": True,
            "message": "No API key configured"
        }

    from services.api_health import run_api_test
    test_result = await run_api_test(api_id)

    # Store health result in DB (best-effort, need user_id)
    try:
        from database import get_current_user_id
        user_id = get_current_user_id()
        if user_id:
            await update_api_health(api_id, user_id, test_result)
    except Exception:
        pass

    return {"api_id": api_id, **test_result}


async def get_effective_api_key(api_id: str) -> str:
    """
    Get the effective API key for an API.
    Checks database first, falls back to environment variable.
    """
    if api_id not in API_REGISTRY:
        return ""

    # Check database first
    db_key = await get_api_key(api_id)
    if db_key:
        return db_key

    # Fall back to environment variable
    env_var = API_REGISTRY[api_id]['env_var']
    return os.getenv(env_var, "")


# ============ API Utilization Tracking ============

class RateLimitUpdate(BaseModel):
    requests_limit: int
    period_seconds: Optional[int] = 86400


@router.get("/api-utilization")
async def get_api_utilization():
    """
    Get API utilization data for all configured APIs.
    Returns usage counts, limits, and utilization percentages.
    Fetches live usage from APIs that support it (CoinGecko, CMC, Blockfrost).
    """
    import asyncio
    from datetime import datetime, timedelta
    from services.api_usage_live import get_live_usage

    # Get current usage for all APIs
    usage_data = await get_all_api_usage()
    usage_map = {u['api_name']: u for u in usage_data}

    # Get custom rate limits
    custom_limits = await get_all_api_rate_limits()
    limits_map = {l['api_name']: l for l in custom_limits}

    # Get saved API settings to know which are configured
    saved_settings = await get_all_api_settings()
    saved_map = {s['api_name']: s for s in saved_settings}

    # Fetch live usage data in parallel for supported APIs
    live_api_ids = ["coingecko", "coinmarketcap", "blockfrost"]
    live_results = await asyncio.gather(
        *[get_live_usage(api_id) for api_id in live_api_ids],
        return_exceptions=True
    )
    live_map = {}
    for api_id, result in zip(live_api_ids, live_results):
        if isinstance(result, dict):
            live_map[api_id] = result

    utilization = []

    for api_id, api_info in API_REGISTRY.items():
        # Check if configured (has key in db or env)
        saved = saved_map.get(api_id)
        env_key = os.getenv(api_info['env_var'], "")
        is_configured = bool((saved and saved.get('api_key')) or env_key)

        # Get usage data
        usage = usage_map.get(api_id, {})
        call_count = usage.get('call_count', 0)
        last_called = usage.get('last_called')

        # Check for live usage data
        live_data = live_map.get(api_id)
        usage_source = "live" if live_data else "local"

        # Get rate limit (custom or default)
        custom_limit = limits_map.get(api_id)
        if custom_limit:
            requests_limit = custom_limit['requests_limit']
            period_seconds = custom_limit['period_seconds']
        elif live_data:
            # Use live data for limits when available
            requests_limit = live_data.get('requests_limit')
            period_seconds = api_info.get('default_period', 86400)
            call_count = live_data.get('call_count', call_count)
        else:
            requests_limit = api_info.get('default_limit')  # May be None
            period_seconds = api_info.get('default_period', 86400)

        # Calculate utilization percentage (None if limit unknown)
        if requests_limit is not None and requests_limit > 0:
            utilization_pct = min(100, round((call_count / requests_limit) * 100, 1))
        else:
            utilization_pct = None  # Unknown limit

        # Calculate time until reset
        now = datetime.now()
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(seconds=period_seconds)
        seconds_until_reset = max(0, (period_end - now).total_seconds())

        # Format reset time
        hours_until_reset = int(seconds_until_reset // 3600)
        minutes_until_reset = int((seconds_until_reset % 3600) // 60)
        if hours_until_reset > 0:
            reset_text = f"{hours_until_reset}h {minutes_until_reset}m"
        else:
            reset_text = f"{minutes_until_reset}m"

        # Use live period_label if available (e.g., "month" instead of "day")
        period_label = live_data.get('period_label') if live_data else api_info.get('period_label', 'day')

        utilization.append({
            "api_id": api_id,
            "name": api_info['name'],
            "category": api_info['category'],
            "configured": is_configured,
            "call_count": call_count,
            "requests_limit": requests_limit,
            "utilization_pct": utilization_pct,
            "period_label": period_label,
            "reset_in": reset_text,
            "seconds_until_reset": int(seconds_until_reset),
            "has_custom_limit": custom_limit is not None,
            "pricing": api_info.get('pricing', 'free'),
            "last_called": last_called,
            "rate_limit_type": api_info.get('rate_limit_type', 'none'),
            "rate_limit_note": api_info.get('rate_limit_note', ''),
            "usage_source": usage_source
        })

    # Sort by utilization (highest first, None last), then by name
    utilization.sort(key=lambda x: (-(x['utilization_pct'] or -1), x['name']))

    return {
        "utilization": utilization,
        "summary": {
            "total_apis": len(API_REGISTRY),
            "configured_count": sum(1 for u in utilization if u['configured']),
            "high_utilization_count": sum(1 for u in utilization if u['utilization_pct'] is not None and u['utilization_pct'] >= 80),
            "total_calls_today": sum(u['call_count'] for u in utilization)
        }
    }


@router.get("/api-utilization/{api_id}")
async def get_single_api_utilization(api_id: str):
    """Get utilization data for a specific API."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    from datetime import datetime, timedelta

    api_info = API_REGISTRY[api_id]

    # Get usage
    usage = await get_api_usage(api_id)
    call_count = usage.get('call_count', 0)

    # Get rate limit
    custom_limit = await get_api_rate_limit(api_id)
    if custom_limit:
        requests_limit = custom_limit['requests_limit']
        period_seconds = custom_limit['period_seconds']
    else:
        requests_limit = api_info.get('default_limit')  # May be None
        period_seconds = api_info.get('default_period', 86400)

    # Calculate utilization (None if limit unknown)
    if requests_limit is not None and requests_limit > 0:
        utilization_pct = min(100, round((call_count / requests_limit) * 100, 1))
    else:
        utilization_pct = None

    # Calculate reset time
    now = datetime.now()
    period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(seconds=period_seconds)
    seconds_until_reset = max(0, (period_end - now).total_seconds())

    hours_until_reset = int(seconds_until_reset // 3600)
    minutes_until_reset = int((seconds_until_reset % 3600) // 60)
    reset_text = f"{hours_until_reset}h {minutes_until_reset}m" if hours_until_reset > 0 else f"{minutes_until_reset}m"

    return {
        "api_id": api_id,
        "name": api_info['name'],
        "call_count": call_count,
        "requests_limit": requests_limit,
        "utilization_pct": utilization_pct,
        "period_label": api_info.get('period_label', 'day'),
        "reset_in": reset_text,
        "seconds_until_reset": int(seconds_until_reset),
        "has_custom_limit": custom_limit is not None,
        "default_limit": api_info.get('default_limit'),
        "last_called": usage.get('last_called'),
        "rate_limit_type": api_info.get('rate_limit_type', 'none'),
        "rate_limit_note": api_info.get('rate_limit_note', '')
    }


@router.put("/api-utilization/{api_id}/limit")
async def update_api_rate_limit(api_id: str, data: RateLimitUpdate, user_id: int = Depends(verify_session)):
    """Update custom rate limit for an API. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    if data.requests_limit <= 0:
        raise HTTPException(status_code=400, detail="Rate limit must be positive")

    await save_api_rate_limit(api_id, data.requests_limit, data.period_seconds)

    return {
        "message": f"Rate limit updated for {API_REGISTRY[api_id]['name']}",
        "api_id": api_id,
        "requests_limit": data.requests_limit,
        "period_seconds": data.period_seconds
    }


@router.delete("/api-utilization/{api_id}/limit")
async def reset_api_rate_limit(api_id: str, user_id: int = Depends(verify_session)):
    """Reset rate limit to default for an API. Requires authentication."""
    if api_id not in API_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown API: {api_id}")

    await delete_api_rate_limit(api_id)

    return {
        "message": f"Rate limit reset to default for {API_REGISTRY[api_id]['name']}",
        "api_id": api_id,
        "default_limit": API_REGISTRY[api_id].get('default_limit', 1000)
    }


@router.post("/apis/reload")
async def reload_all_api_keys(user_id: int = Depends(verify_session)):
    """
    Clear all API key caches, forcing services to reload keys from database.

    This is useful after updating API keys via the web interface to ensure
    they are recognized immediately without waiting for the 60-second cache TTL.
    """
    import importlib
    import sys

    # List of service modules to reload
    service_modules = [
        'services.taptools',
        'services.cardano',
        'services.polygon',
        'services.base',
        'services.nft_price_client',
        'services.solana',
        'services.ethereum',
        'services.etherscan',
        'services.coinbase',
        'services.charli3',
    ]

    reloaded_count = 0

    for module_name in service_modules:
        try:
            if module_name in sys.modules:
                module = sys.modules[module_name]

                # Find service instances and clear their caches
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    # Check if it's a service instance with clear_cache method
                    if hasattr(attr, 'clear_cache') and callable(attr.clear_cache):
                        attr.clear_cache()
                        reloaded_count += 1
                        logger.info(f"Cleared cache for {module_name}.{attr_name}")

        except Exception as e:
            logger.warning(f"Could not reload {module_name}: {e}")

    return {
        "message": f"API key caches cleared for {reloaded_count} service(s)",
        "detail": "All services will reload keys from database on next API call",
        "services_reloaded": reloaded_count
    }


# ============================================================================
# STARTUP TASK THROTTLING & RATE LIMIT MANAGEMENT
# ============================================================================

@router.get("/startup-tasks")
async def get_startup_tasks_status(user_id: int = Depends(verify_session)):
    """
    Get status of all startup tasks and their cooldowns.

    Shows when tasks last ran and if they're currently in cooldown period.
    Useful for debugging why certain tasks might be skipped on startup.
    """
    from services.rate_limit_tracker import rate_limit_tracker

    tasks = await rate_limit_tracker.get_all_task_status()
    rate_limits = await rate_limit_tracker.get_all_rate_limit_status()

    return {
        "tasks": tasks,
        "rate_limits": rate_limits,
        "summary": {
            "total_tasks": len(tasks),
            "tasks_in_cooldown": sum(1 for t in tasks if t.get('is_in_cooldown')),
            "services_rate_limited": sum(1 for r in rate_limits if r.get('is_rate_limited'))
        }
    }


@router.post("/startup-tasks/{service}/{task}/force")
async def force_run_task(
    service: str,
    task: str,
    user_id: int = Depends(verify_session)
):
    """
    Force a startup task to run immediately, bypassing cooldown.

    This is useful for manual refresh operations. The task will still be tracked
    and subject to cooldown for the next automatic run.

    IMPORTANT: This only resets the cooldown timer. The actual task execution
    must be triggered separately (e.g., via the respective API endpoint).

    Args:
        service: Service name (taptools, portfolio, etc.)
        task: Task name (nft_floor_prices, snapshot, etc.)
    """
    from services.rate_limit_tracker import rate_limit_tracker

    # Check if service is rate limited
    if await rate_limit_tracker.is_rate_limited(service):
        raise HTTPException(
            status_code=429,
            detail=f"Service '{service}' is currently rate limited. Clear the rate limit first."
        )

    # Mark the task as manually run (resets cooldown)
    await rate_limit_tracker.mark_task_run(task, service, run_type='manual')

    logger.info(f"Manual task trigger: {service}/{task} (user_id={user_id})")

    return {
        "message": f"Task cooldown reset for {service}/{task}",
        "service": service,
        "task": task,
        "run_type": "manual",
        "note": "Cooldown timer reset. Trigger the actual task via its respective API endpoint."
    }


@router.post("/rate-limits/{service}/clear")
async def clear_service_rate_limit(
    service: str,
    user_id: int = Depends(verify_session)
):
    """
    Manually clear rate limit status for a service.

    Use this to recover from rate limiting if you've verified the limit period
    has passed or if you want to attempt API calls again.

    Args:
        service: Service name (taptools, alchemy, etc.)
    """
    from services.rate_limit_tracker import rate_limit_tracker

    await rate_limit_tracker.clear_rate_limit(service)

    logger.info(f"Rate limit manually cleared for service '{service}' (user_id={user_id})")

    return {
        "message": f"Rate limit cleared for service '{service}'",
        "service": service,
        "note": "Service can now be used for API calls. Use with caution to avoid hitting limits again."
    }


@router.post("/rate-limits/{service}/mark")
async def mark_service_rate_limited(
    service: str,
    recovery_minutes: int = 60,
    user_id: int = Depends(verify_session)
):
    """
    Manually mark a service as rate limited.

    Use this if you've hit a rate limit manually and want to prevent
    automatic tasks from attempting to use the service.

    Args:
        service: Service name
        recovery_minutes: How long to block the service (default: 60 minutes)
    """
    from services.rate_limit_tracker import rate_limit_tracker

    await rate_limit_tracker.mark_rate_limited(service, recovery_minutes)

    logger.info(f"Service '{service}' manually marked as rate limited for {recovery_minutes} minutes (user_id={user_id})")

    return {
        "message": f"Service '{service}' marked as rate limited",
        "service": service,
        "recovery_minutes": recovery_minutes,
        "blocked_until": (datetime.now() + timedelta(minutes=recovery_minutes)).isoformat()
    }
