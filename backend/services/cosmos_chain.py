"""
Generic Cosmos IBC Chain Service - Fetches wallet data for Cosmos SDK chains using LCD REST API.

Config-driven: each chain is an entry in COSMOS_IBC_CHAINS with its LCD URL, bech32 prefix,
native denom, and CoinGecko ID. All chains share the same CosmosIBCChainService class.

Uses persistent HTTP client pool via get_client().
"""

import logging
from typing import Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Chain configurations for Cosmos IBC chains
# (Cosmos Hub itself uses the dedicated cosmos.py service)
COSMOS_IBC_CHAINS: Dict[str, dict] = {
    'osmosis': {
        'name': 'Osmosis',
        'lcd_url': 'https://osmosis-rest.publicnode.com',
        'bech32_prefix': 'osmo',
        'native_denom': 'uosmo',
        'native_symbol': 'OSMO',
        'decimals': 6,
        'coingecko_id': 'osmosis',
    },
    'celestia': {
        'name': 'Celestia',
        'lcd_url': 'https://celestia-rest.publicnode.com',
        'bech32_prefix': 'celestia',
        'native_denom': 'utia',
        'native_symbol': 'TIA',
        'decimals': 6,
        'coingecko_id': 'celestia',
    },
    'injective': {
        'name': 'Injective',
        'lcd_url': 'https://injective-rest.publicnode.com',
        'bech32_prefix': 'inj',
        'native_denom': 'inj',
        'native_symbol': 'INJ',
        'decimals': 18,
        'coingecko_id': 'injective-protocol',
    },
    'dydx': {
        'name': 'dYdX',
        'lcd_url': 'https://dydx-rest.publicnode.com',
        'bech32_prefix': 'dydx',
        'native_denom': 'adydx',
        'native_symbol': 'DYDX',
        'decimals': 18,
        'coingecko_id': 'dydx-chain',
    },
    'sei': {
        'name': 'Sei',
        'lcd_url': 'https://sei-rest.publicnode.com',
        'bech32_prefix': 'sei',
        'native_denom': 'usei',
        'native_symbol': 'SEI',
        'decimals': 6,
        'coingecko_id': 'sei-network',
    },
    'akash': {
        'name': 'Akash',
        'lcd_url': 'https://akash-rest.publicnode.com',
        'bech32_prefix': 'akash',
        'native_denom': 'uakt',
        'native_symbol': 'AKT',
        'decimals': 6,
        'coingecko_id': 'akash-network',
    },
}


class CosmosIBCChainService:
    """Generic service for fetching Cosmos IBC chain wallet data via LCD REST API."""

    def __init__(self, chain_key: str):
        if chain_key not in COSMOS_IBC_CHAINS:
            raise ValueError(f"Unknown Cosmos IBC chain: {chain_key}")
        self.chain_key = chain_key
        self.config = COSMOS_IBC_CHAINS[chain_key]
        self.lcd_url = self.config['lcd_url']
        self.prefix = self.config['bech32_prefix']
        self.native_denom = self.config['native_denom']
        self.native_symbol = self.config['native_symbol']
        self.decimals = self.config['decimals']
        self.divisor = 10 ** self.decimals

    def _is_valid_address(self, address: str) -> bool:
        return (
            isinstance(address, str)
            and address.startswith(self.prefix + '1')
            and len(address) >= 39
        )

    async def _get_balances(self, address: str) -> Optional[list]:
        """Fetch bank balances via LCD: GET /cosmos/bank/v1beta1/balances/{address}"""
        try:
            client = get_client(f"cosmos_{self.chain_key}", timeout=30.0)
            response = await client.get(
                f"{self.lcd_url}/cosmos/bank/v1beta1/balances/{address}",
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.error(f"{self.config['name']} LCD error: {response.status_code}")
                return None
            return response.json().get("balances", [])
        except Exception as e:
            logger.error(f"{self.config['name']} LCD balances error: {e}")
            return None

    async def _get_delegations(self, address: str) -> Optional[list]:
        """Fetch staking delegations via LCD."""
        try:
            client = get_client(f"cosmos_{self.chain_key}", timeout=30.0)
            response = await client.get(
                f"{self.lcd_url}/cosmos/staking/v1beta1/delegations/{address}",
                timeout=30.0,
            )
            if response.status_code == 404:
                return []
            if response.status_code != 200:
                return None
            return response.json().get("delegation_responses", [])
        except Exception as e:
            logger.error(f"{self.config['name']} LCD delegations error: {e}")
            return None

    def _to_native(self, raw_amount: str) -> float:
        """Convert raw denom amount to native float."""
        try:
            return int(raw_amount) / self.divisor
        except (ValueError, TypeError):
            return 0.0

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get balance info for an address on this Cosmos IBC chain."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid {self.config['name']} address: {address}")
            return None

        try:
            import asyncio
            balances_result, delegations_result = await asyncio.gather(
                self._get_balances(address),
                self._get_delegations(address),
                return_exceptions=True,
            )

            if isinstance(balances_result, Exception):
                balances_result = None
            if isinstance(delegations_result, Exception):
                delegations_result = None

            if balances_result is None:
                return None

            # Parse native balance
            balance_native = 0.0
            tokens = []
            for bal in balances_result:
                denom = bal.get("denom", "")
                amount_raw = bal.get("amount", "0")
                if denom == self.native_denom:
                    balance_native = self._to_native(amount_raw)
                    tokens.append({
                        "denom": denom,
                        "symbol": self.native_symbol,
                        "amount_raw": amount_raw,
                        "amount": balance_native,
                        "decimals": self.decimals,
                    })
                else:
                    tokens.append({
                        "denom": denom,
                        "symbol": denom[:20],
                        "amount_raw": amount_raw,
                        "decimals": None,
                    })

            # Parse delegations
            delegated = 0.0
            if delegations_result:
                for deleg in delegations_result:
                    bal_info = deleg.get("balance", {})
                    if bal_info.get("denom") == self.native_denom:
                        delegated += self._to_native(bal_info.get("amount", "0"))

            balance_key = f"balance_{self.native_symbol.lower()}"
            return {
                "address": address,
                balance_key: balance_native,
                "delegated": delegated,
                "tokens": tokens,
                "blockchain": self.chain_key,
                "source": f"cosmos_lcd_{self.chain_key}",
            }
        except Exception as e:
            logger.error(f"{self.config['name']} get_address_info error: {e}")
            return None


# Singleton instances for each Cosmos IBC chain
osmosis_service = CosmosIBCChainService('osmosis')
celestia_service = CosmosIBCChainService('celestia')
injective_service = CosmosIBCChainService('injective')
dydx_service = CosmosIBCChainService('dydx')
sei_service = CosmosIBCChainService('sei')
akash_service = CosmosIBCChainService('akash')
