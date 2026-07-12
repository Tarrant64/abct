"""
Tensor Protocol adapter - NFT marketplace position detection on Solana.

Tensor is a leading NFT marketplace and trading protocol on Solana. Users can:
- List NFTs for sale on the Tensor marketplace (tracked as LP positions)
- Place collection or individual bids that lock SOL (tracked as staking positions)
- Provide liquidity to Tensor AMM pools for NFT collections (tracked as LP positions)

This adapter detects active positions by querying Tensor's on-chain program accounts
via the Helius RPC. Two program IDs are checked:
- Marketplace (TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN): listings and bids
- AMM (TAMM6ub33ij1mbetoMyVBLeKY5iP41i4UPUJQGkhfsg): liquidity pool positions
"""

import logging
from typing import List
from services.defi_protocols.base_adapter import DetectionMethod, PositionType, ProtocolPosition
from services.defi_protocols.solana.base_solana_adapter import BaseSolanaAdapter, get_helius_rpc_url
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Tensor program IDs
TENSOR_MARKETPLACE_PROGRAM = "TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN"
TENSOR_AMM_PROGRAM = "TAMM6ub33ij1mbetoMyVBLeKY5iP41i4UPUJQGkhfsg"

# Account data sizes for Tensor on-chain accounts
# Listing account: stores NFT listing info (owner, price, mint, etc.)
TENSOR_LISTING_SIZE = 161
# Bid account: stores bid info (bidder, amount, collection, etc.)
TENSOR_BID_SIZE = 244
# AMM pool position: stores LP position in a Tensor AMM pool
TENSOR_AMM_POSITION_SIZE = 296


class TensorAdapter(BaseSolanaAdapter):
    """Tensor Protocol adapter for detecting NFT marketplace positions.

    Detects three types of positions:
    1. Active listings - NFTs listed for sale on Tensor marketplace
    2. Active bids - SOL locked in collection/individual bids
    3. AMM pool positions - Liquidity provided to Tensor AMM pools

    Uses on-chain program account scanning via Helius RPC (getProgramAccounts)
    with memcmp filters to find accounts owned by the target wallet.
    """

    PROTOCOL_NAME = "Tensor"
    SUPPORTED_CHAINS = ["solana"]
    DETECTION_METHOD = DetectionMethod.PROGRAM_ACCOUNT
    PROTOCOL_URL = "https://www.tensor.trade"

    async def detect_positions(self, address: str, chain: str = None) -> List[ProtocolPosition]:
        """Detect all Tensor positions for a given wallet address.

        Queries both the marketplace program (listings + bids) and the AMM program
        (pool positions) in sequence. Returns an empty list if no positions are found
        or if RPC calls fail.

        Args:
            address: Solana wallet address (base58)
            chain: Chain filter (only 'solana' supported)

        Returns:
            List of ProtocolPosition objects for detected Tensor positions
        """
        positions = []

        # Detect marketplace listings
        listings = await self._detect_listings(address)
        positions.extend(listings)

        # Detect active bids
        bids = await self._detect_bids(address)
        positions.extend(bids)

        # Detect AMM pool positions
        amm_positions = await self._detect_amm_positions(address)
        positions.extend(amm_positions)

        return positions

    async def _detect_listings(self, address: str) -> List[ProtocolPosition]:
        """Detect active NFT listings on the Tensor marketplace.

        Scans the marketplace program for listing accounts where the owner
        field (at offset 8) matches the target wallet address.
        """
        rpc_url = await get_helius_rpc_url()
        if not rpc_url:
            return []

        try:
            client = get_client("helius", timeout=30.0)
            response = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    TENSOR_MARKETPLACE_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": TENSOR_LISTING_SIZE},
                            # Owner/seller pubkey at offset 8
                            {"memcmp": {"offset": 8, "bytes": address}},
                        ]
                    }
                ]
            })

            if response.status_code != 200:
                logger.warning(f"Tensor listings RPC returned {response.status_code}")
                return []

            data = response.json()

            # Check for RPC-level errors
            if "error" in data:
                logger.warning(f"Tensor listings RPC error: {data['error']}")
                return []

            accounts = data.get('result', [])

            if not accounts:
                return []

            positions = []
            for i, account in enumerate(accounts):
                pubkey = account.get('pubkey', '')
                positions.append(ProtocolPosition(
                    protocol="Tensor",
                    chain="solana",
                    position_type=PositionType.LP_POSITION,
                    token_symbol="TENSOR-LIST",
                    token_name="Tensor NFT Listing",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": TENSOR_MARKETPLACE_PROGRAM,
                        "listing_account": pubkey,
                        "position_index": i,
                        "position_subtype": "listing",
                        "note": "Active NFT listing on Tensor marketplace",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Tensor listings for {address[:20]}...: {e}")
            return []

    async def _detect_bids(self, address: str) -> List[ProtocolPosition]:
        """Detect active bids (collection or individual) on Tensor.

        Scans the marketplace program for bid accounts where the bidder
        field (at offset 8) matches the target wallet address. Bids lock
        SOL until they are filled or cancelled.
        """
        rpc_url = await get_helius_rpc_url()
        if not rpc_url:
            return []

        try:
            client = get_client("helius", timeout=30.0)
            response = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    TENSOR_MARKETPLACE_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": TENSOR_BID_SIZE},
                            # Bidder pubkey at offset 8
                            {"memcmp": {"offset": 8, "bytes": address}},
                        ]
                    }
                ]
            })

            if response.status_code != 200:
                logger.warning(f"Tensor bids RPC returned {response.status_code}")
                return []

            data = response.json()

            if "error" in data:
                logger.warning(f"Tensor bids RPC error: {data['error']}")
                return []

            accounts = data.get('result', [])

            if not accounts:
                return []

            positions = []
            for i, account in enumerate(accounts):
                pubkey = account.get('pubkey', '')
                positions.append(ProtocolPosition(
                    protocol="Tensor",
                    chain="solana",
                    position_type=PositionType.STAKING,
                    token_symbol="TENSOR-BID",
                    token_name="Tensor Active Bid",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": TENSOR_MARKETPLACE_PROGRAM,
                        "bid_account": pubkey,
                        "position_index": i,
                        "position_subtype": "bid",
                        "note": "SOL locked in active bid on Tensor",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Tensor bids for {address[:20]}...: {e}")
            return []

    async def _detect_amm_positions(self, address: str) -> List[ProtocolPosition]:
        """Detect AMM pool liquidity positions on Tensor.

        Scans the Tensor AMM program for pool position accounts where the
        owner field (at offset 8) matches the target wallet address. These
        represent liquidity provided to NFT collection trading pools.
        """
        rpc_url = await get_helius_rpc_url()
        if not rpc_url:
            return []

        try:
            client = get_client("helius", timeout=30.0)
            response = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    TENSOR_AMM_PROGRAM,
                    {
                        "encoding": "base64",
                        "filters": [
                            {"dataSize": TENSOR_AMM_POSITION_SIZE},
                            # Pool owner/LP provider at offset 8
                            {"memcmp": {"offset": 8, "bytes": address}},
                        ]
                    }
                ]
            })

            if response.status_code != 200:
                logger.warning(f"Tensor AMM RPC returned {response.status_code}")
                return []

            data = response.json()

            if "error" in data:
                logger.warning(f"Tensor AMM RPC error: {data['error']}")
                return []

            accounts = data.get('result', [])

            if not accounts:
                return []

            positions = []
            for i, account in enumerate(accounts):
                pubkey = account.get('pubkey', '')
                positions.append(ProtocolPosition(
                    protocol="Tensor",
                    chain="solana",
                    position_type=PositionType.LP_POSITION,
                    token_symbol="TENSOR-AMM",
                    token_name="Tensor AMM Pool Position",
                    amount=1.0,
                    contract_address=pubkey,
                    extra={
                        "program_id": TENSOR_AMM_PROGRAM,
                        "pool_account": pubkey,
                        "position_index": i,
                        "position_subtype": "amm_pool",
                        "note": "Liquidity in Tensor AMM collection pool",
                        "source": "onchain",
                    },
                ))

            return positions

        except Exception as e:
            logger.error(f"Error detecting Tensor AMM positions for {address[:20]}...: {e}")
            return []


from services.defi_protocols.registry import protocol_registry
protocol_registry.register(TensorAdapter())
