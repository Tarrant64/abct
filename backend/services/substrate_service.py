"""
Substrate Chain Service - Fetches wallet data for Polkadot/Kusama using Subscan REST API.

Config-driven: Polkadot and Kusama share this class with different configs.
Uses Subscan public API (no key required, but key available for higher rate limits).
"""

import logging
from typing import Dict, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

SUBSTRATE_CHAINS: Dict[str, dict] = {
    'polkadot': {
        'name': 'Polkadot',
        'subscan_url': 'https://polkadot.api.subscan.io',
        'native_symbol': 'DOT',
        'decimals': 10,
        'coingecko_id': 'polkadot',
        'address_prefix': '1',  # SS58 prefix 0 → starts with 1
    },
    'kusama': {
        'name': 'Kusama',
        'subscan_url': 'https://kusama.api.subscan.io',
        'native_symbol': 'KSM',
        'decimals': 12,
        'coingecko_id': 'kusama',
        'address_prefix': None,  # Various prefixes
    },
}


class SubstrateChainService(APIKeyManager):
    """Service for fetching Polkadot/Kusama wallet data via Subscan REST API."""

    def __init__(self, chain_key: str):
        super().__init__(api_name='subscan', env_var='SUBSCAN_API_KEY')
        if chain_key not in SUBSTRATE_CHAINS:
            raise ValueError(f"Unknown Substrate chain: {chain_key}")
        self.chain_key = chain_key
        self.config = SUBSTRATE_CHAINS[chain_key]
        self.subscan_url = self.config['subscan_url']
        self.native_symbol = self.config['native_symbol']
        self.decimals = self.config['decimals']
        self.divisor = 10 ** self.decimals

    def _is_valid_address(self, address: str) -> bool:
        """Basic Substrate address validation (SS58 format)."""
        if not isinstance(address, str):
            return False
        # SS58 addresses are 47-48 chars, alphanumeric (no 0, O, I, l)
        if len(address) < 46 or len(address) > 48:
            return False
        return True

    async def _get_headers(self) -> dict:
        """Get request headers with optional API key."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        key = await self.get_api_key()
        if key:
            headers["X-API-Key"] = key
        return headers

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get balance and token info for a Substrate address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid {self.config['name']} address: {address}")
            return None

        try:
            client = get_client(f"subscan_{self.chain_key}", timeout=30.0)
            headers = await self._get_headers()

            # Fetch account tokens (includes native + other tokens)
            response = await client.post(
                f"{self.subscan_url}/api/v2/scan/account/tokens",
                json={"address": address},
                headers=headers,
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Subscan {self.config['name']} error: {response.status_code}")
                return None

            data = response.json()
            if data.get("code") != 0:
                logger.error(f"Subscan error: {data.get('message', 'unknown')}")
                return None

            result_data = data.get("data", {})

            # Parse native balance
            native_list = result_data.get("native", [])
            balance_native = 0.0
            if native_list:
                for native in native_list:
                    balance_raw = native.get("balance", "0")
                    try:
                        balance_native = int(balance_raw) / self.divisor
                    except (ValueError, TypeError):
                        balance_native = 0.0

            # Parse other tokens
            tokens = []
            for token_list_key in ["ERC20", "ERC721", "native"]:
                for token in result_data.get(token_list_key, []):
                    symbol = token.get("symbol", "")
                    if symbol == self.native_symbol:
                        continue  # Skip native, already captured
                    balance_raw = token.get("balance", "0")
                    decimals = int(token.get("decimals", self.decimals))
                    if int(balance_raw) > 0:
                        tokens.append({
                            "contract_address": token.get("unique_id", ""),
                            "symbol": symbol,
                            "name": token.get("name", symbol),
                            "decimals": decimals,
                            "balance_raw": balance_raw,
                        })

            balance_key = f"balance_{self.native_symbol.lower()}"
            return {
                "address": address,
                balance_key: balance_native,
                "tokens": tokens,
                "token_count": len(tokens),
                "blockchain": self.chain_key,
                "source": f"subscan_{self.chain_key}",
            }

        except Exception as e:
            logger.error(f"{self.config['name']} get_address_info error: {e}")
            return None


# Singleton instances
polkadot_service = SubstrateChainService('polkadot')
kusama_service = SubstrateChainService('kusama')
