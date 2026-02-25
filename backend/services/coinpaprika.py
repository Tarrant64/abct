"""
CoinPaprika API Client Service

Free pricing data source (25,000 calls/month, no API key required).
Used as a fallback in the pricing chain:
    CoinGecko -> CoinMarketCap -> Coinbase -> DefiLlama -> CoinPaprika -> TapTools

API docs: https://api.coinpaprika.com
Base URL: https://api.coinpaprika.com/v1
"""

import asyncio
import logging
from typing import Dict, List, Optional

from services.http_client import get_client

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coinpaprika.com/v1"

# Static mapping from ticker symbol to CoinPaprika coin ID.
# CoinPaprika IDs follow the pattern "{ticker}-{name}" (lowercase, hyphenated).
SYMBOL_TO_COINPAPRIKA: Dict[str, str] = {
    # Major chains
    "ADA": "ada-cardano",
    "BTC": "btc-bitcoin",
    "ETH": "eth-ethereum",
    "SOL": "sol-solana",
    "ALGO": "algo-algorand",
    "MATIC": "matic-polygon",
    # Stablecoins
    "USDC": "usdc-usd-coin",
    "USDT": "usdt-tether",
    "DAI": "dai-dai",
    # Cardano DeFi tokens
    "INDY": "indy-indigo-protocol",
    "LQ": "lq-liqwid-finance",
    "MIN": "min-minswap",
    "SUNDAE": "sundae-sundaeswap",
    "WRT": "wrt-wingriders",
    "DJED": "djed-djed",
    "SHEN": "shen-shen",
    "LENFI": "lenfi-lenfi",
    "SNEK": "snek-snek",
    "AGIX": "agix-singularitynet",
    "STRIKE": "strike-strike-finance",
    "IAG": "iag-iagon",
    "FLDT": "fldt-fluidtokens",
    "XER": "xer-xerberus",
    "NIGHT": "night-midnight",
    "FLOW": "flow-flow-lending",
    # Chain native tokens
    "XRP": "xrp-xrp",
    "HBAR": "hbar-hedera-hashgraph",
    "EGLD": "egld-multiversx",
    "SUI": "sui-sui",
    "APT": "apt-aptos",
    "FIL": "fil-filecoin",
    "BNB": "bnb-binance-coin",
    "AVAX": "avax-avalanche",
    "TRX": "trx-tron",
    "LINK": "link-chainlink",
    "HNT": "hnt-helium",
    "LTC": "ltc-litecoin",
    "DOGE": "doge-dogecoin",
    "ZEC": "zec-zcash",
    "XMR": "xmr-monero",
    "SCRT": "scrt-secret",
    "DOT": "dot-polkadot",
    "KSM": "ksm-kusama",
    "NEAR": "near-near-protocol",
    "ICP": "icp-internet-computer",
    "TON": "ton-toncoin",
    "XTZ": "xtz-tezos",
    "XLM": "xlm-stellar",
    "VET": "vet-vechain",
    "VTHO": "vtho-vethor-token",
    "STX": "stx-stacks",
    "KAS": "kas-kaspa",
    "ERG": "erg-ergo",
    "KLAY": "klay-klaytn",
    "ARB": "arb-arbitrum",
    "MINA": "mina-mina-protocol",
    "ZIL": "zil-zilliqa",
    "WAVES": "waves-waves",
    "IOTA": "miota-iota",
    "MOBILE": "mobile-helium-mobile",
    # Cosmos ecosystem
    "ATOM": "atom-cosmos",
    "OSMO": "osmo-osmosis",
    "TIA": "tia-celestia",
    "INJ": "inj-injective-protocol",
    "SEI": "sei-sei-network",
    "AKT": "akt-akash-network",
    "DYDX": "dydx-dydx",
}


async def resolve_coinpaprika_id(symbol: str) -> Optional[str]:
    """
    Resolve a ticker symbol to a CoinPaprika coin ID.

    Checks the static SYMBOL_TO_COINPAPRIKA map first.
    Falls back to the /search API if the symbol is not in the map.

    Returns:
        The CoinPaprika coin ID string, or None if not found.
    """
    upper = symbol.upper()
    if upper in SYMBOL_TO_COINPAPRIKA:
        return SYMBOL_TO_COINPAPRIKA[upper]

    # Fallback: search the API
    try:
        client = get_client("coinpaprika", timeout=15.0)
        response = await client.get(
            f"{BASE_URL}/search",
            params={"q": symbol, "c": "currencies", "limit": 5},
        )
        if response.status_code == 200:
            data = response.json()
            currencies = data.get("currencies", [])
            # Find an exact symbol match (case-insensitive)
            for coin in currencies:
                if coin.get("symbol", "").upper() == upper:
                    return coin.get("id")
            # If no exact match, return the first result
            if currencies:
                return currencies[0].get("id")
    except Exception as e:
        logger.warning("CoinPaprika search fallback failed for %s: %s", symbol, e)

    return None


class CoinPaprikaService:
    """Client for the CoinPaprika free API."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(5)

    def _get_client(self):
        return get_client("coinpaprika", timeout=15.0)

    # ------------------------------------------------------------------
    # 1. Batch price fetching
    # ------------------------------------------------------------------
    async def get_prices_batch(self, symbols: List[str]) -> Dict[str, dict]:
        """
        Fetch current price data for multiple symbols in parallel.

        Uses asyncio.gather with a semaphore to limit concurrency to 5
        simultaneous requests.

        Returns:
            Dict mapping each successfully resolved symbol to a price dict:
            {symbol: {usd, usd_1h_change, usd_24h_change, market_cap,
                      volume_24h, source: 'CoinPaprika'}}
        """
        results: Dict[str, dict] = {}

        async def _fetch_one(symbol: str) -> None:
            coin_id = await resolve_coinpaprika_id(symbol)
            if not coin_id:
                logger.warning("CoinPaprika: no ID for symbol %s", symbol)
                return

            async with self._semaphore:
                try:
                    client = self._get_client()
                    response = await client.get(f"{BASE_URL}/tickers/{coin_id}")
                    if response.status_code != 200:
                        logger.warning(
                            "CoinPaprika ticker %s returned %d",
                            coin_id,
                            response.status_code,
                        )
                        return

                    data = response.json()
                    quotes = data.get("quotes", {}).get("USD", {})
                    results[symbol.upper()] = {
                        "usd": quotes.get("price"),
                        "usd_1h_change": quotes.get("percent_change_1h"),
                        "usd_24h_change": quotes.get("percent_change_24h"),
                        "market_cap": quotes.get("market_cap"),
                        "volume_24h": quotes.get("volume_24h"),
                        "source": "CoinPaprika",
                    }
                except Exception as e:
                    logger.warning(
                        "CoinPaprika price fetch failed for %s: %s", symbol, e
                    )

        await asyncio.gather(*[_fetch_one(s) for s in symbols])
        return results

    # ------------------------------------------------------------------
    # 2. Global market data
    # ------------------------------------------------------------------
    async def get_global_market(self) -> dict:
        """
        Fetch global cryptocurrency market statistics.

        Returns:
            Dict with total_market_cap_usd, market_cap_change_24h,
            btc_dominance, total_volume_usd, active_cryptocurrencies,
            and source.  Empty dict on failure.
        """
        try:
            client = self._get_client()
            response = await client.get(f"{BASE_URL}/global")
            if response.status_code != 200:
                logger.warning(
                    "CoinPaprika /global returned %d", response.status_code
                )
                return {}

            data = response.json()
            return {
                "total_market_cap_usd": data.get("market_cap_usd"),
                "market_cap_change_24h": data.get("market_cap_change_24h"),
                "btc_dominance": data.get("bitcoin_dominance_percentage"),
                "total_volume_usd": data.get("volume_24h_usd"),
                "active_cryptocurrencies": data.get(
                    "cryptocurrencies_number"
                ),
                "source": "CoinPaprika",
            }
        except Exception as e:
            logger.warning("CoinPaprika global market fetch failed: %s", e)
            return {}

    # ------------------------------------------------------------------
    # 3. Trending coins (top gainers with meaningful market cap)
    # ------------------------------------------------------------------
    async def get_trending(self) -> List[dict]:
        """
        Return top 10 coins with the largest positive 24h price change
        and a market cap above $50M.

        CoinPaprika has no dedicated trending endpoint, so this fetches
        the top 250 tickers by rank and sorts locally.

        Returns:
            List of dicts: [{name, symbol, market_cap_rank, price_usd,
            change_24h, thumb: None, source: 'CoinPaprika'}]
        """
        try:
            client = self._get_client()
            response = await client.get(
                f"{BASE_URL}/tickers", params={"limit": 250}
            )
            if response.status_code != 200:
                logger.warning(
                    "CoinPaprika /tickers returned %d", response.status_code
                )
                return []

            tickers = response.json()

            # Filter: must have positive 24h change and market cap > $50M
            candidates = []
            for t in tickers:
                quotes = t.get("quotes", {}).get("USD", {})
                change_24h = quotes.get("percent_change_24h")
                market_cap = quotes.get("market_cap")
                if (
                    change_24h is not None
                    and market_cap is not None
                    and change_24h > 0
                    and market_cap > 50_000_000
                ):
                    candidates.append(
                        {
                            "name": t.get("name"),
                            "symbol": t.get("symbol"),
                            "market_cap_rank": t.get("rank"),
                            "price_usd": quotes.get("price"),
                            "change_24h": change_24h,
                            "thumb": None,
                            "source": "CoinPaprika",
                        }
                    )

            # Sort by 24h change descending, take top 10
            candidates.sort(key=lambda c: c["change_24h"], reverse=True)
            return candidates[:10]

        except Exception as e:
            logger.warning("CoinPaprika trending fetch failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # 4. Token search
    # ------------------------------------------------------------------
    async def search_token(self, query: str) -> List[dict]:
        """
        Search for coins/tokens by name or symbol.

        Endpoint: GET /search?q={query}&c=currencies&limit=10

        Returns:
            List of dicts: [{id, name, symbol, rank}]
        """
        try:
            client = self._get_client()
            response = await client.get(
                f"{BASE_URL}/search",
                params={"q": query, "c": "currencies", "limit": 10},
            )
            if response.status_code != 200:
                logger.warning(
                    "CoinPaprika /search returned %d", response.status_code
                )
                return []

            data = response.json()
            results = []
            for coin in data.get("currencies", []):
                results.append(
                    {
                        "id": coin.get("id"),
                        "name": coin.get("name"),
                        "symbol": coin.get("symbol"),
                        "rank": coin.get("rank"),
                    }
                )
            return results

        except Exception as e:
            logger.warning("CoinPaprika search failed for '%s': %s", query, e)
            return []

    # ------------------------------------------------------------------
    # 5. Full coin details / metadata
    # ------------------------------------------------------------------
    async def get_coin_details(self, coin_id: str) -> dict:
        """
        Fetch full metadata for a coin.

        Endpoint: GET /coins/{coin_id}

        Returns:
            Dict with name, symbol, rank, description, logo, type, tags,
            team, links, etc.  Empty dict on failure.
        """
        try:
            client = self._get_client()
            response = await client.get(f"{BASE_URL}/coins/{coin_id}")
            if response.status_code != 200:
                logger.warning(
                    "CoinPaprika /coins/%s returned %d",
                    coin_id,
                    response.status_code,
                )
                return {}

            return response.json()

        except Exception as e:
            logger.warning(
                "CoinPaprika coin details failed for %s: %s", coin_id, e
            )
            return {}

    # ------------------------------------------------------------------
    # 6. Coin market / ticker data
    # ------------------------------------------------------------------
    async def get_coin_market_data(self, coin_id: str) -> dict:
        """
        Fetch all market data for a coin including supply, ATH, ATL, etc.

        Endpoint: GET /tickers/{coin_id}

        Returns:
            The full ticker response dict.  Empty dict on failure.
        """
        try:
            client = self._get_client()
            response = await client.get(f"{BASE_URL}/tickers/{coin_id}")
            if response.status_code != 200:
                logger.warning(
                    "CoinPaprika /tickers/%s returned %d",
                    coin_id,
                    response.status_code,
                )
                return {}

            return response.json()

        except Exception as e:
            logger.warning(
                "CoinPaprika market data failed for %s: %s", coin_id, e
            )
            return {}


# Singleton instance
coinpaprika_service = CoinPaprikaService()
