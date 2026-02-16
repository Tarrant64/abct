"""
Analytics Router - Advanced on-chain metrics, market benchmarks, TradFi comparisons

Endpoints:
    GET /analytics/chain-metrics              - All 9 chains: TVL, fees, revenue, DEX volume
    GET /analytics/chain-metrics/{chain}       - Single chain detailed metrics
    GET /analytics/chain-fees-history/{chain}  - Daily fee history for chart
    GET /analytics/market-summary              - Crypto market cap, BTC dominance, total TVL, DEX volume
    GET /analytics/relative-strength           - Normalized % change for major assets
    GET /analytics/gas-prices                  - Current gas prices (Etherscan oracle)
    GET /analytics/chain-breakdown/{blockchain} - TVL, stablecoins, DEX volume per chain (proxy)
    GET /analytics/cardano-dex                 - Cardano DEX analytics (Charli3)
    GET /analytics/tradfi/summary              - TradFi index data (requires Alpha Vantage)
    GET /analytics/tradfi/history/{symbol}     - TradFi daily close prices
    GET /analytics/tradfi/correlation          - BTC vs S&P 500 correlation
"""

import logging
import os
import sys
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth_utils import verify_session
from services.chain_analytics import chain_analytics_service, SUPPORTED_CHAINS

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.get("/chain-metrics")
async def get_chain_metrics(user_id: int = Depends(verify_session)):
    """Get TVL, fees, revenue, and DEX volume for all supported chains"""
    try:
        data = await chain_analytics_service.get_chain_overview()
        return {"success": True, "chains": data.get("chains", {}), "timestamp": data.get("timestamp")}
    except Exception as e:
        logger.error(f"Error fetching chain metrics: {e}")
        return {"success": False, "error": str(e), "chains": {}}


@router.get("/chain-metrics/{chain}")
async def get_chain_metric(chain: str, user_id: int = Depends(verify_session)):
    """Get detailed metrics for a single chain"""
    if chain not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}. Supported: {SUPPORTED_CHAINS}")

    try:
        data = await chain_analytics_service.get_chain_overview()
        chain_data = data.get("chains", {}).get(chain, {})
        return {"success": True, "chain": chain, "metrics": chain_data}
    except Exception as e:
        logger.error(f"Error fetching metrics for {chain}: {e}")
        return {"success": False, "error": str(e)}


@router.get("/chain-fees-history/{chain}")
async def get_chain_fees_history(
    chain: str,
    days: int = Query(default=30, ge=7, le=365),
    user_id: int = Depends(verify_session)
):
    """Get daily fee history for a specific chain (for charting)"""
    if chain not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    try:
        history = await chain_analytics_service.get_chain_fees_history(chain, days)
        return {"success": True, "chain": chain, "days": days, "history": history}
    except Exception as e:
        logger.error(f"Error fetching fee history for {chain}: {e}")
        return {"success": False, "error": str(e), "history": []}


@router.get("/market-summary")
async def get_market_summary(user_id: int = Depends(verify_session)):
    """Get combined crypto market summary: market cap, BTC dominance, total TVL, total DEX volume"""
    try:
        from services.http_client import get_client
        from config import CMC_API_KEY, CMC_BASE_URL
        import asyncio

        async def fetch_global():
            """Fetch global market data - try CMC first, fall back to CoinGecko."""
            # Try CMC first (saves CoinGecko rate limit)
            try:
                if CMC_API_KEY:
                    client = get_client("coinmarketcap", timeout=10.0)
                    resp = await client.get(
                        f"{CMC_BASE_URL}/global-metrics/quotes/latest",
                        headers={'X-CMC_PRO_API_KEY': CMC_API_KEY, 'Accept': 'application/json'}
                    )
                    if resp.status_code == 200:
                        cmc_data = resp.json().get("data", {})
                        quote = cmc_data.get("quote", {}).get("USD", {})
                        logger.info("Market summary global data from CMC")
                        return {
                            "total_market_cap": {"usd": quote.get("total_market_cap", 0)},
                            "market_cap_change_percentage_24h_usd": quote.get("total_market_cap_yesterday_percentage_change", 0),
                            "market_cap_percentage": {"btc": cmc_data.get("btc_dominance", 0)},
                        }
            except Exception as e:
                logger.debug(f"CMC global failed, trying CoinGecko: {e}")

            # CoinGecko fallback
            try:
                from database import get_api_key as _get_api_key
                cg_key = await _get_api_key("coingecko")
                cg_headers = {"x-cg-demo-api-key": cg_key} if cg_key else {}
                client = get_client("coingecko", timeout=10.0)
                resp = await client.get("https://api.coingecko.com/api/v3/global", headers=cg_headers)
                if resp.status_code == 200:
                    return resp.json().get("data", {})
                logger.warning(f"CoinGecko /global returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"CoinGecko global also failed: {e}")
            return {}

        async def fetch_tvl():
            return await chain_analytics_service.get_total_tvl()

        async def fetch_dex_volume():
            return await chain_analytics_service.get_total_dex_volume()

        global_data, total_tvl, dex_volume = await asyncio.gather(
            fetch_global(), fetch_tvl(), fetch_dex_volume()
        )

        return {
            "success": True,
            "total_market_cap_usd": global_data.get("total_market_cap", {}).get("usd", 0),
            "market_cap_change_24h": global_data.get("market_cap_change_percentage_24h_usd", 0),
            "btc_dominance": global_data.get("market_cap_percentage", {}).get("btc", 0),
            "total_defi_tvl": total_tvl,
            "total_dex_volume_24h": dex_volume,
        }
    except Exception as e:
        logger.error(f"Error fetching market summary: {e}")
        return {"success": False, "error": str(e)}


@router.get("/relative-strength")
async def get_relative_strength(
    days: int = Query(default=30, ge=7, le=90),
    user_id: int = Depends(verify_session)
):
    """Get normalized % change for major crypto assets over time"""
    from database import get_cache, set_cache
    from config import CACHE_TTL_WARM

    cache_key = f"relative_strength_{days}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    try:
        from services.pricing import pricing_service

        symbols = ['BTC', 'ETH', 'SOL', 'ADA', 'MATIC']
        historical = await pricing_service.get_historical_prices(symbols, days)

        # Normalize each asset to % change from day 0
        # Remap MATIC -> POL for frontend consistency
        result = {}
        for symbol, prices in historical.items():
            symbol = 'POL' if symbol == 'MATIC' else symbol
            if not prices:
                continue
            base_price = prices[0].get('price', 0)
            if base_price <= 0:
                continue

            result[symbol] = [
                {
                    'date': p.get('date', ''),
                    'time': p.get('time', ''),
                    'change_pct': ((p.get('price', 0) - base_price) / base_price) * 100
                }
                for p in prices
            ]

        response = {"success": True, "days": days, "assets": result}
        if result:
            await set_cache(cache_key, response, CACHE_TTL_WARM)
        return response
    except Exception as e:
        logger.error(f"Error fetching relative strength: {e}")
        return {"success": False, "error": str(e), "assets": {}}


# ---- Crypto Market Data (Stablecoins, Chains TVL, RWA) ----

@router.get("/market/stablecoins")
async def get_stablecoin_market(user_id: int = Depends(verify_session)):
    """Get top stablecoins by market cap from DefiLlama"""
    try:
        data = await chain_analytics_service.get_stablecoin_market()
        return {"success": True, **data}
    except Exception as e:
        logger.error(f"Error fetching stablecoin market: {e}")
        return {"success": False, "error": str(e), "total_stablecoin_mcap": 0, "stablecoins": []}


@router.get("/market/chains-tvl")
async def get_all_chains_tvl(
    limit: int = Query(default=25, ge=5, le=100),
    user_id: int = Depends(verify_session)
):
    """Get top chains by TVL from DefiLlama (all chains)"""
    try:
        data = await chain_analytics_service.get_all_chains_tvl(limit)
        return {"success": True, **data}
    except Exception as e:
        logger.error(f"Error fetching chains TVL: {e}")
        return {"success": False, "error": str(e), "total_tvl": 0, "chains": []}


@router.get("/market/rwa")
async def get_rwa_protocols(
    limit: int = Query(default=15, ge=5, le=50),
    user_id: int = Depends(verify_session)
):
    """Get RWA (Real World Asset) protocols from DefiLlama"""
    try:
        data = await chain_analytics_service.get_rwa_protocols(limit)
        return {"success": True, **data}
    except Exception as e:
        logger.error(f"Error fetching RWA protocols: {e}")
        return {"success": False, "error": str(e), "total_rwa_tvl": 0, "protocols": []}


# ---- Gas / Chain Breakdown / DEX Analytics ----

@router.get("/gas-prices")
async def get_gas_prices(
    chain: str = Query(default="ethereum"),
    user_id: int = Depends(verify_session)
):
    """Get current gas prices from Etherscan oracle"""
    try:
        from services.etherscan import etherscan_service
        if not await etherscan_service.is_configured():
            return {"success": False, "configured": False, "message": "Etherscan API key not configured"}

        data = await etherscan_service.get_gas_price(chain)
        if not data:
            return {"success": False, "error": "Failed to fetch gas prices"}

        return {"success": True, **data}
    except Exception as e:
        logger.error(f"Error fetching gas prices: {e}")
        return {"success": False, "error": str(e)}


@router.get("/chain-breakdown/{blockchain}")
async def get_chain_breakdown(
    blockchain: str,
    user_id: int = Depends(verify_session)
):
    """Get TVL, stablecoin supply, and DEX volume for a single chain (proxies DefiLlama)"""
    import asyncio
    from services.http_client import get_client
    from database import get_cache, set_cache
    from config import CACHE_TTL_WARM

    cache_key = f"analytics:chain_breakdown:{blockchain}"
    cached = await get_cache(cache_key)
    if cached:
        return {"success": True, **cached}

    # Map our chain names to DefiLlama slugs
    slug_map = {
        'ethereum': 'Ethereum', 'solana': 'Solana', 'cardano': 'Cardano',
        'bitcoin': 'Bitcoin', 'polygon': 'Polygon', 'base': 'Base',
        'arbitrum': 'Arbitrum', 'avalanche': 'Avalanche', 'bsc': 'BSC',
    }
    slug = slug_map.get(blockchain.lower())
    if not slug:
        return {"success": False, "error": f"Unsupported chain: {blockchain}"}

    client = get_client("defillama_analytics", timeout=15.0)

    async def fetch_tvl():
        try:
            resp = await client.get(f"https://api.llama.fi/v2/chains")
            if resp.status_code == 200:
                for item in resp.json():
                    name = item.get('name', '')
                    if name == 'Binance':
                        name = 'BSC'
                    if name == slug:
                        return {'tvl': item.get('tvl', 0), 'tvl_change_1d': item.get('change_1d', 0)}
        except Exception as e:
            logger.warning(f"DefiLlama chain TVL failed: {e}")
        return {'tvl': 0, 'tvl_change_1d': 0}

    async def fetch_stablecoin_supply():
        try:
            resp = await client.get("https://stablecoins.llama.fi/stablecoins?includePrices=true")
            if resp.status_code == 200:
                total = 0
                for coin in resp.json().get('peggedAssets', []):
                    chain_circ = coin.get('chainCirculating', {}).get(slug, {})
                    for peg_type in chain_circ.values():
                        if isinstance(peg_type, dict):
                            total += peg_type.get('peggedUSD', 0)
                return total
        except Exception as e:
            logger.warning(f"DefiLlama stablecoin supply failed: {e}")
        return 0

    async def fetch_dex_volume():
        try:
            resp = await client.get(f"https://api.llama.fi/overview/dexs/{slug}")
            if resp.status_code == 200:
                return resp.json().get('total24h', 0) or 0
        except Exception as e:
            logger.warning(f"DefiLlama DEX volume failed: {e}")
        return 0

    try:
        tvl_data, stablecoin_supply, dex_volume = await asyncio.gather(
            fetch_tvl(), fetch_stablecoin_supply(), fetch_dex_volume()
        )

        result = {
            'chain': blockchain,
            'tvl': tvl_data['tvl'],
            'tvl_change_1d': tvl_data['tvl_change_1d'],
            'stablecoin_supply': stablecoin_supply,
            'dex_volume_24h': dex_volume,
        }
        await set_cache(cache_key, result, CACHE_TTL_WARM)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Error fetching chain breakdown for {blockchain}: {e}")
        return {"success": False, "error": str(e)}


@router.get("/cardano-dex")
async def get_cardano_dex_analytics(user_id: int = Depends(verify_session)):
    """Get Cardano DEX breakdown (Minswap, SundaeSwap, etc.) from Charli3"""
    try:
        from services.charli3 import charli3_service
        if not await charli3_service.is_configured():
            return {"success": False, "configured": False, "message": "Charli3 API key not configured"}

        groups = await charli3_service.get_groups()
        if not groups:
            return {"success": False, "error": "Failed to fetch DEX groups"}

        return {"success": True, "dexes": groups}
    except Exception as e:
        logger.error(f"Error fetching Cardano DEX analytics: {e}")
        return {"success": False, "error": str(e)}


# ---- TradFi Endpoints (Phase 3) ----

@router.get("/tradfi/summary")
async def get_tradfi_summary(user_id: int = Depends(verify_session)):
    """Get TradFi index data (S&P 500, NASDAQ, Dow, BTC ETF). Requires Alpha Vantage API key."""
    try:
        from services.tradfi_data import tradfi_service
        if not await tradfi_service.is_configured():
            return {"success": False, "configured": False, "message": "Alpha Vantage API key not configured"}

        data = await tradfi_service.get_all_indices()
        return {"success": True, "configured": True, "indices": data}
    except ImportError:
        return {"success": False, "configured": False, "message": "TradFi service not available"}
    except Exception as e:
        logger.error(f"Error fetching TradFi summary: {e}")
        return {"success": False, "error": str(e)}


@router.get("/tradfi/history/{symbol}")
async def get_tradfi_history(
    symbol: str,
    days: int = Query(default=30, ge=7, le=365),
    user_id: int = Depends(verify_session)
):
    """Get daily close prices for a TradFi symbol"""
    try:
        from services.tradfi_data import tradfi_service
        if not await tradfi_service.is_configured():
            return {"success": False, "configured": False, "message": "Alpha Vantage API key not configured"}

        data = await tradfi_service.get_daily_data(symbol.upper())
        if not data:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        # Trim to requested days
        history = data.get('history', [])[-days:]
        return {"success": True, "symbol": symbol.upper(), "history": history}
    except ImportError:
        return {"success": False, "configured": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching TradFi history for {symbol}: {e}")
        return {"success": False, "error": str(e)}


@router.get("/tradfi/correlation")
async def get_tradfi_correlation(
    days: int = Query(default=30, ge=7, le=365),
    user_id: int = Depends(verify_session)
):
    """Get BTC vs S&P 500 correlation coefficient"""
    try:
        from services.tradfi_data import tradfi_service
        if not await tradfi_service.is_configured():
            return {"success": False, "configured": False, "message": "Alpha Vantage API key not configured"}

        correlation = await tradfi_service.get_btc_spy_correlation(days)
        return {"success": True, "days": days, "correlation": correlation}
    except ImportError:
        return {"success": False, "configured": False}
    except Exception as e:
        logger.error(f"Error computing correlation: {e}")
        return {"success": False, "error": str(e)}
