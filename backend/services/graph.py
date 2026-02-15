"""
The Graph API Service - Uniswap Subgraph Integration

Provides token pricing data for Ethereum-based chains using The Graph's hosted service.
Queries Uniswap v2/v3 subgraphs for token prices in ETH and USD.

API Limits: 100,000 queries per 24 hours
Documentation: https://thegraph.com/docs/
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GRAPH_API_KEY
from middleware.api_tracker import get_tracked_client

logger = logging.getLogger(__name__)


class GraphService:
    """Service for The Graph API - Uniswap subgraph queries."""

    def __init__(self):
        # Uniswap V3 subgraph endpoint (mainnet)
        self.uniswap_v3_url = f"https://gateway.thegraph.com/api/{GRAPH_API_KEY}/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"

        # Uniswap V2 subgraph endpoint (mainnet)
        self.uniswap_v2_url = f"https://gateway.thegraph.com/api/{GRAPH_API_KEY}/subgraphs/id/A3Np3RQbaBA6oKJgiwDJeo5T3zrYfGHPWFYayMwtNDum"

        self._cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    def is_configured(self) -> bool:
        """Check if Graph API key is configured."""
        return bool(GRAPH_API_KEY)

    async def get_token_price_eth(self, token_address: str, use_v2: bool = False) -> Optional[float]:
        """
        Get token price in ETH from Uniswap.

        Args:
            token_address: Ethereum token contract address (checksummed or lowercase)
            use_v2: Use Uniswap V2 instead of V3 (default False)

        Returns:
            Price in ETH, or None if not found
        """
        if not self.is_configured():
            logger.debug("Graph API not configured")
            return None

        # Normalize address to lowercase
        token_address = token_address.lower()

        # Check cache
        cache_key = f"eth_price_{token_address}_{'v2' if use_v2 else 'v3'}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now() - cached['timestamp'] < self._cache_ttl:
                return cached['price']

        try:
            url = self.uniswap_v2_url if use_v2 else self.uniswap_v3_url

            # GraphQL query for token price
            if use_v2:
                # Uniswap V2 query
                query = """
                {
                  token(id: "%s") {
                    derivedETH
                    symbol
                    name
                  }
                }
                """ % token_address
            else:
                # Uniswap V3 query
                query = """
                {
                  token(id: "%s") {
                    derivedETH
                    symbol
                    name
                  }
                }
                """ % token_address

            async with get_tracked_client("graph", timeout=30) as client:
                response = await client.post(
                    url,
                    json={"query": query}
                )

                if response.status_code == 200:
                    data = response.json()

                    if 'errors' in data:
                        logger.warning(f"Graph API errors: {data['errors']}")
                        return None

                    token_data = data.get('data', {}).get('token')
                    if token_data and token_data.get('derivedETH'):
                        price_eth = float(token_data['derivedETH'])

                        # Cache result
                        self._cache[cache_key] = {
                            'price': price_eth,
                            'timestamp': datetime.now()
                        }

                        logger.info(f"Got {token_data.get('symbol', token_address)} price: {price_eth} ETH")
                        return price_eth
                else:
                    logger.warning(f"Graph API request failed: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching token price from Graph: {e}")
            return None

    async def get_token_data(self, token_address: str, use_v2: bool = False) -> Optional[Dict]:
        """
        Get comprehensive token data from Uniswap subgraph.

        Returns token info including:
        - derivedETH: Price in ETH
        - totalValueLockedUSD: TVL in USD
        - volume: Trading volume
        - symbol, name, decimals

        Args:
            token_address: Ethereum token contract address
            use_v2: Use Uniswap V2 instead of V3

        Returns:
            Dict with token data, or None if not found
        """
        if not self.is_configured():
            return None

        token_address = token_address.lower()

        try:
            url = self.uniswap_v2_url if use_v2 else self.uniswap_v3_url

            query = """
            {
              token(id: "%s") {
                symbol
                name
                decimals
                derivedETH
                totalValueLockedUSD
                volumeUSD
              }
            }
            """ % token_address

            async with get_tracked_client("graph", timeout=30) as client:
                response = await client.post(url, json={"query": query})

                if response.status_code == 200:
                    data = response.json()

                    if 'errors' in data:
                        logger.warning(f"Graph API errors: {data['errors']}")
                        return None

                    token_data = data.get('data', {}).get('token')
                    if token_data:
                        return {
                            'symbol': token_data.get('symbol'),
                            'name': token_data.get('name'),
                            'decimals': int(token_data.get('decimals', 18)),
                            'price_eth': float(token_data.get('derivedETH', 0)),
                            'tvl_usd': float(token_data.get('totalValueLockedUSD', 0)),
                            'volume_usd': float(token_data.get('volumeUSD', 0))
                        }

                return None

        except Exception as e:
            logger.error(f"Error fetching token data from Graph: {e}")
            return None

    async def get_multiple_token_prices(self, token_addresses: List[str], use_v2: bool = False) -> Dict[str, float]:
        """
        Get prices for multiple tokens in a single query.

        Args:
            token_addresses: List of token contract addresses
            use_v2: Use Uniswap V2 instead of V3

        Returns:
            Dict mapping token address to price in ETH
        """
        if not self.is_configured() or not token_addresses:
            return {}

        # Normalize addresses
        token_addresses = [addr.lower() for addr in token_addresses]

        try:
            url = self.uniswap_v2_url if use_v2 else self.uniswap_v3_url

            # Build query for multiple tokens
            token_queries = []
            for i, addr in enumerate(token_addresses[:100]):  # Limit to 100 tokens per query
                token_queries.append(f'token{i}: token(id: "{addr}") {{ id derivedETH symbol }}')

            query = "{" + " ".join(token_queries) + "}"

            async with get_tracked_client("graph", timeout=30) as client:
                response = await client.post(url, json={"query": query})

                if response.status_code == 200:
                    data = response.json()

                    if 'errors' in data:
                        logger.warning(f"Graph API errors: {data['errors']}")
                        return {}

                    result = {}
                    token_data = data.get('data', {})

                    for key, value in token_data.items():
                        if value and value.get('derivedETH'):
                            addr = value['id'].lower()
                            result[addr] = float(value['derivedETH'])

                    return result

                return {}

        except Exception as e:
            logger.error(f"Error fetching multiple token prices from Graph: {e}")
            return {}

    async def get_lp_positions(self, address: str) -> List[Dict]:
        """
        Get Uniswap V3 LP positions for an Ethereum address.

        Args:
            address: Ethereum address (0x...)

        Returns:
            List of LP position dicts with token pair, liquidity, and fee tier
        """
        if not self.is_configured():
            return []

        address = address.lower()

        # Check cache
        cache_key = f"lp_positions_{address}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now() - cached['timestamp'] < self._cache_ttl:
                return cached['data']

        try:
            query = """
            {
              positions(where: {owner: "%s", liquidity_gt: "0"}, first: 100) {
                id
                liquidity
                tickLower { tickIdx }
                tickUpper { tickIdx }
                token0 { id symbol name decimals }
                token1 { id symbol name decimals }
                pool {
                  feeTier
                  token0Price
                  token1Price
                  totalValueLockedUSD
                }
                depositedToken0
                depositedToken1
              }
            }
            """ % address

            async with get_tracked_client("graph", timeout=30) as client:
                response = await client.post(
                    self.uniswap_v3_url,
                    json={"query": query}
                )

                if response.status_code != 200:
                    logger.warning(f"Graph API LP positions request failed: {response.status_code}")
                    return []

                data = response.json()
                if 'errors' in data:
                    logger.warning(f"Graph API LP errors: {data['errors']}")
                    return []

                positions = data.get('data', {}).get('positions', [])
                result = []

                for pos in positions:
                    token0 = pos.get('token0', {})
                    token1 = pos.get('token1', {})
                    pool = pos.get('pool', {})

                    result.append({
                        'position_id': pos.get('id'),
                        'token0_symbol': token0.get('symbol', '?'),
                        'token0_name': token0.get('name', ''),
                        'token0_address': token0.get('id', ''),
                        'token1_symbol': token1.get('symbol', '?'),
                        'token1_name': token1.get('name', ''),
                        'token1_address': token1.get('id', ''),
                        'fee_tier': int(pool.get('feeTier', 0)),
                        'liquidity': pos.get('liquidity', '0'),
                        'deposited_token0': float(pos.get('depositedToken0', 0)),
                        'deposited_token1': float(pos.get('depositedToken1', 0)),
                        'pool_tvl_usd': float(pool.get('totalValueLockedUSD', 0)),
                        'protocol': 'Uniswap V3',
                        'chain': 'ethereum'
                    })

                # Cache result
                self._cache[cache_key] = {
                    'data': result,
                    'timestamp': datetime.now()
                }

                logger.info(f"Found {len(result)} Uniswap V3 LP positions for {address[:10]}")
                return result

        except Exception as e:
            logger.error(f"Error fetching LP positions from Graph: {e}")
            return []

    def clear_cache(self):
        """Clear the price cache."""
        self._cache.clear()


# Singleton instance
graph_service = GraphService()
