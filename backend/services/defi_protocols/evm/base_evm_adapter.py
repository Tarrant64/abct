"""
Base EVM Adapter - Shared helpers for EVM-chain DeFi protocol adapters.

Provides eth_call helpers, ABI encoding/decoding, and Alchemy RPC access.
"""

import logging
from typing import Optional, List
from services.defi_protocols.base_adapter import ProtocolAdapter
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Alchemy base URLs by chain
ALCHEMY_CHAIN_URLS = {
    'ethereum': 'https://eth-mainnet.g.alchemy.com',
    'polygon': 'https://polygon-mainnet.g.alchemy.com',
    'base': 'https://base-mainnet.g.alchemy.com',
    'arbitrum': 'https://arb-mainnet.g.alchemy.com',
    'avalanche': 'https://avax-mainnet.g.alchemy.com',
    'bsc': 'https://bnb-mainnet.g.alchemy.com',
    'optimism': 'https://opt-mainnet.g.alchemy.com',
    'zksync': 'https://zksync-mainnet.g.alchemy.com',
    'linea': 'https://linea-mainnet.g.alchemy.com',
    'scroll': 'https://scroll-mainnet.g.alchemy.com',
}

# Public RPCs for chains without Alchemy support
PUBLIC_RPC_URLS = {
    'fantom': 'https://rpcapi.fantom.network',
    'cronos': 'https://evm.cronos.org',
    'gnosis': 'https://rpc.gnosischain.com',
    'moonbeam': 'https://rpc.api.moonbeam.network',
}

# API key manager for Alchemy (shared)
_alchemy_key_manager = APIKeyManager(api_name='alchemy', env_var='ALCHEMY_API_KEY')


async def get_rpc_url(chain: str) -> Optional[str]:
    """Get the RPC URL for a chain (Alchemy or public)."""
    if chain in ALCHEMY_CHAIN_URLS:
        api_key = await _alchemy_key_manager.get_api_key()
        if api_key:
            return f"{ALCHEMY_CHAIN_URLS[chain]}/v2/{api_key}"
    if chain in PUBLIC_RPC_URLS:
        return PUBLIC_RPC_URLS[chain]
    return None


async def eth_call(chain: str, to: str, data: str) -> Optional[str]:
    """Execute eth_call on a chain.

    Args:
        chain: Chain name (ethereum, polygon, etc.)
        to: Contract address
        data: ABI-encoded call data (hex string with 0x prefix)

    Returns:
        Hex-encoded return data, or None on error
    """
    rpc_url = await get_rpc_url(chain)
    if not rpc_url:
        logger.warning(f"No RPC URL available for chain: {chain}")
        return None

    try:
        client = get_client("alchemy", timeout=15.0)
        response = await client.post(rpc_url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"]
        })

        if response.status_code != 200:
            logger.error(f"eth_call failed on {chain}: HTTP {response.status_code}")
            return None

        result = response.json()
        if 'error' in result:
            logger.debug(f"eth_call error on {chain}: {result['error']}")
            return None

        return result.get('result')

    except Exception as e:
        logger.error(f"eth_call error on {chain} to {to}: {e}")
        return None


async def get_erc20_balance(chain: str, token_address: str, wallet_address: str) -> Optional[int]:
    """Get ERC-20 token balance (raw, no decimals).

    Calls balanceOf(address) on the token contract.
    """
    # balanceOf(address) selector = 0x70a08231
    padded_address = wallet_address.lower().replace('0x', '').zfill(64)
    data = f"0x70a08231{padded_address}"

    result = await eth_call(chain, token_address, data)
    if result and result != '0x':
        try:
            return int(result, 16)
        except ValueError:
            return None
    return None


def encode_address(address: str) -> str:
    """ABI-encode an address to 32 bytes."""
    return address.lower().replace('0x', '').zfill(64)


def decode_uint256(hex_data: str, offset: int = 0) -> int:
    """Decode a uint256 from hex data at given 32-byte offset."""
    start = 2 + (offset * 64)  # Skip '0x' prefix
    end = start + 64
    if len(hex_data) < end:
        return 0
    return int(hex_data[start:end], 16)


class BaseEVMAdapter(ProtocolAdapter):
    """Base class for EVM DeFi protocol adapters with shared helpers."""

    async def _eth_call(self, chain: str, to: str, data: str) -> Optional[str]:
        return await eth_call(chain, to, data)

    async def _get_erc20_balance(self, chain: str, token: str, wallet: str) -> Optional[int]:
        return await get_erc20_balance(chain, token, wallet)

    def _decode_uint256(self, hex_data: str, offset: int = 0) -> int:
        return decode_uint256(hex_data, offset)

    def _encode_address(self, address: str) -> str:
        return encode_address(address)
