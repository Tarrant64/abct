"""
Wallet Reconciliation Service — Koios on-chain data provider.

Replaces the deprecated TapTools API for portfolio reconciliation.
Uses Koios (https://koios.rest) to provide independent on-chain
ground-truth for Cardano wallet balances, native assets, and
stake-key coverage.

Koios is free, no API key required, and returns:
- account_info: stake address ADA balance, rewards, withdrawals
- account_assets: all native assets held under a stake key
- account_addresses: all addresses for a stake key

The public interface mirrors the old TapToolsWalletService so that
the portfolio router endpoints continue to work without changes.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KOIOS_API_BASE = "https://api.koios.rest/api/v1"
logger = logging.getLogger(__name__)


class WalletReconciliationService:
    """On-chain wallet reconciliation service backed by Koios API."""

    def __init__(self):
        self.api_base = KOIOS_API_BASE
        self._cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return or create a persistent Koios HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _cache_get(self, key: str) -> Optional[dict]:
        """Check in-memory cache; return data if still fresh."""
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() - entry['timestamp'] < self._cache_ttl:
                return entry['data']
        return None

    async def _cache_set(self, key: str, data: dict):
        """Store data in in-memory cache."""
        self._cache[key] = {
            'data': data,
            'timestamp': datetime.now(),
        }

    async def _koios_get(self, path: str, params: dict) -> Optional[dict]:
        """Execute a Koios API GET request with retry."""
        client = self._get_client()
        url = f"{self.api_base}{path}"
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Koios {path} returned {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Koios {path} error: {e}")
            return None

    # ------------------------------------------------------------------
    # Public API — these signatures match the old TapToolsWalletService
    # ------------------------------------------------------------------

    async def get_wallet_portfolio(self, address: str) -> Optional[Dict]:
        """
        Get wallet portfolio positions from Koios on-chain data.

        Derives the stake key from the given address, then fetches
        account_info (ADA balance) and account_assets (native tokens).

        Returns dict compatible with the old TapTools response shape:
            {
                'ada_balance': float,        # Total ADA in lovelace / 1e6
                'ada_value': float,          # ADA balance (value not available from Koios)
                'liquid_value': float,       # Same as ada_balance (Koios has no DeFi split)
                'num_tokens': int,           # Count of native asset types (excl. ADA)
                'num_nfts': int,             # Assets with quantity == 1
                'positions': [...],          # Native asset positions
                'nft_positions': [...],      # NFT positions (quantity == 1)
                'source': 'Koios'
            }
        """
        # Derive stake key from address
        stake_address = await self._address_to_stake(address)
        if not stake_address:
            logger.debug(f"Could not derive stake key from {address}")
            return None

        cache_key = f"portfolio_{address}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            # 1. ADA balance
            info = await self._koios_get("/account_info", {"_stake_address": stake_address})
            if not info or not isinstance(info, list) or not info:
                return None
            account = info[0]
            ada_lovelace = int(account.get('amount', 0))
            ada_balance = ada_lovelace / 1_000_000.0

            # 2. Native assets
            assets = await self._koios_get("/account_assets", {"_stake_address": stake_address})
            positions = []
            nft_positions = []
            num_tokens = 0
            num_nfts = 0

            if assets and isinstance(assets, list):
                for a in assets:
                    unit = a.get('unit', '')
                    if unit == 'lovelace':
                        continue  # handled by account_info
                    quantity_raw = int(a.get('quantity', 0))
                    quantity = quantity_raw / (10 ** int(a.get('count', 0) or 0)) if a.get('count') else quantity_raw / 1.0
                    # Use raw decimal count from Koios or derive from quantity
                    # Koios returns raw quantity in smallest unit if count > 0
                    if a.get('count') and a['count'] > 0:
                        quantity = quantity_raw / (10 ** a['count'])

                    ticker = a.get('ticker', '')
                    asset_name = a.get('asset_name', '')
                    policy_id = a.get('policy_id', '')
                    label = a.get('label', '')

                    pos = {
                        'unit': unit,
                        'ticker': ticker,
                        'asset_name': asset_name,
                        'policy_id': policy_id,
                        'balance': quantity,
                        'raw_quantity': quantity_raw,
                        'decimals': a.get('count', 0),
                        'ada_value': 0,  # Koios does not provide pricing
                        'price': 0,
                        'label': label,
                    }

                    # Distinguish NFTs (quantity == 1 and no decimals > 0)
                    is_nft = (quantity_raw == 1 and (a.get('count', 0) == 0 or quantity == 1))

                    positions.append(pos)
                    if is_nft:
                        nft_positions.append(pos)
                        num_nfts += 1
                    else:
                        num_tokens += 1

            result = {
                'ada_balance': ada_balance,
                'ada_value': ada_balance,  # Koios has no pricing
                'liquid_value': ada_balance,  # no DeFi split on-chain
                'num_tokens': num_tokens,
                'num_nfts': num_nfts,
                'positions': positions,
                'nft_positions': nft_positions,
                'source': 'Koios',
            }

            await self._cache_set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching Koios portfolio for {address}: {e}")
            return None

    async def get_stake_key_balance(self, address: str) -> Optional[Dict]:
        """
        Get balance summary for a stake key via Koios.

        Returns dict compatible with the old TapTools shape:
            {
                'total_ada': float,
                'liquid_ada': float,
                'ada_value_usd': None,
                'total_tokens': int,
                'total_nfts': int,
                'source': 'Koios'
            }
        """
        portfolio = await self.get_wallet_portfolio(address)
        if not portfolio:
            return None

        return {
            'total_ada': portfolio['ada_balance'],
            'liquid_ada': portfolio.get('liquid_value', portfolio['ada_balance']),
            'ada_value_usd': None,  # Koios does not provide pricing
            'total_tokens': portfolio['num_tokens'],
            'total_nfts': portfolio['num_nfts'],
            'source': 'Koios',
        }

    async def get_defi_positions(self, address: str) -> Optional[List[Dict]]:
        """
        Return DeFi positions.

        Koios provides raw on-chain data without protocol-level
        interpretation, so this returns an empty list.
        """
        return []

    async def compare_with_local(self, address: str, local_ada_balance: float) -> Dict:
        """
        Compare local balance with on-chain data from Koios.

        Returns:
            {
                'status': 'match'|'minor_discrepancy'|'significant_discrepancy'|'unavailable',
                'local_ada': float,
                'taptools_ada': float,   # renamed from source; now Koios ADA
                'difference': float,
                'pct_difference': float,
                'note': str
            }
        """
        tk_data = await self.get_stake_key_balance(address)
        if not tk_data:
            return {
                'status': 'unavailable',
                'message': 'On-chain wallet data not available',
            }

        on_chain_ada = tk_data['total_ada']
        difference = on_chain_ada - local_ada_balance
        pct_diff = (difference / local_ada_balance * 100) if local_ada_balance > 0 else 0

        if abs(pct_diff) < 1:
            status = 'match'
        elif abs(pct_diff) < 10:
            status = 'minor_discrepancy'
        else:
            status = 'significant_discrepancy'

        return {
            'status': status,
            'local_ada': local_ada_balance,
            'taptools_ada': on_chain_ada,  # field name kept for API compat
            'difference': difference,
            'pct_difference': pct_diff,
            'note': 'On-chain wallet service returns total stake key balance from Koios',
        }

    async def is_configured(self, user_id: int = 1) -> bool:
        """
        Koios is a free, public API — always considered 'configured'.

        Kept for API compatibility with the old TapToolsWalletService.
        """
        return True

    async def get_all_addresses_for_stake(self, address: str) -> Optional[List[Dict]]:
        """
        Get all on-chain addresses for the stake key underlying the given address.

        Returns a list of dicts with 'address' and 'balance' keys.
        """
        stake_address = await self._address_to_stake(address)
        if not stake_address:
            return None

        # Use cache-keyed address for consistency
        cache_key = f"addresses_{address}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            addresses = await self._koios_get("/account_addresses", {"_stake_address": stake_address})
            if not addresses or not isinstance(addresses, list):
                return []

            result = []
            for a in addresses:
                result.append({
                    'address': a.get('address', ''),
                    'balance': a.get('balance', 0) / 1_000_000.0,
                })

            await self._cache_set(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Error fetching Koios addresses for {address}: {e}")
            return None

    async def get_stake_key_addresses_count(self, address: str) -> int:
        """
        Convenience: return the number of on-chain addresses for the stake key.
        """
        addrs = await self.get_all_addresses_for_stake(address)
        return len(addrs) if addrs else 0

    def clear_cache(self):
        """Clear the portfolio cache."""
        self._cache.clear()

    async def close(self):
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _address_to_stake(self, address: str) -> Optional[str]:
        """Derive stake address from any Cardano address using Koios resolve_address."""
        # Use Koios resolve_address for reliable derivation
        resolved = await self._koios_get("/resolve_address", {"_query": address})
        if resolved and isinstance(resolved, list) and resolved:
            # resolve_address returns [{ "stake_address": "stake1...", ... }]
            return resolved[0].get('stake_address')
        return None


# Singleton instance — router imports this exact name
taptools_wallet_service = WalletReconciliationService()
