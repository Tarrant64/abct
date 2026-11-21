"""
Koios wallet reconciliation service (formerly ``services/taptools.py``).

This module is NOT TapTools. It is the Cardano account-level data source used
by wallet refresh and the portfolio reconciliation endpoints: it asks Koios
(https://koios.rest, free, no API key) for the stake account's spendable ADA,
rewards and native assets. Blockfrost (``cardano_service.get_account_utxo_ada``)
remains the ADA-only fallback in ``routers/wallets.py`` when this returns None.

Koios v1 endpoints used (all POST with a JSON body -- the GET forms 404):
- POST /account_info    {"_stake_addresses": [...]}  -> utxo / rewards_available / total_balance (lovelace strings)
- POST /account_assets  {"_stake_addresses": [...]}  -> one row per asset: policy_id, asset_name (hex),
                                                        fingerprint, decimals, quantity (raw string)
- POST /account_addresses {"_stake_addresses": [...]}-> payment addresses under the stake key
- POST /address_info    {"_addresses": [...]}        -> stake_address for an address (fallback only)

The stake address is derived locally from the bech32 address (no network call)
and only falls back to Koios /address_info (there is no /resolve_address
endpoint in Koios; calling it 404'd on every refresh).

``services/taptools.py`` remains as a thin import shim for the old name.
"""

import asyncio
import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KOIOS_API_BASE = "https://api.koios.rest/api/v1"
LOVELACE = 1_000_000
ASSET_PAGE_SIZE = 1000
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

    async def _koios_post(self, path: str, body: dict, params: Optional[dict] = None) -> Optional[list]:
        """Execute a Koios API POST request (Koios v1 account/address endpoints are POST-only)."""
        client = self._get_client()
        url = f"{self.api_base}{path}"
        try:
            response = await client.post(url, json=body, params=params)
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
                'ada_balance': float,        # UTXO-held ADA -- spendable balance (== 'utxo_ada')
                'utxo_ada': float,           # Same value, explicit name
                'rewards_available_ada': float,  # Unclaimed staking rewards -- NOT in ada_balance
                'total_balance_ada': float,  # utxo_ada + rewards_available_ada
                'ada_value': float,          # ADA balance (value not available from Koios)
                'liquid_value': float,       # Same as ada_balance (Koios has no DeFi split)
                'num_tokens': int,           # Count of native asset types (excl. ADA)
                'num_nfts': int,             # Assets with quantity == 1
                'positions': [...],          # Native asset positions
                'nft_positions': [...],      # NFT positions (quantity == 1)
                'source': 'Koios'
            }

        ABCT-CARDANO-ACCOUNT-LEVEL-20260919: 'ada_balance' now reports
        Koios's 'utxo' field (spendable ADA held in UTXOs at this stake
        key), matching what hardware wallets display, rather than folding
        in unclaimed rewards -- see 'rewards_available_ada' for those
        separately. Previously this read a field literally named 'amount',
        which does not exist in Koios's account_info response (confirmed
        against the real schema fields: utxo, rewards_available,
        total_balance) -- ada_balance was effectively always 0 before this
        fix, silently.
        """
        # Derive stake key from address
        stake_address = await self._address_to_stake(address)
        if not stake_address:
            logger.debug("Could not derive stake key for a wallet address")
            return None

        cache_key = f"portfolio_{address}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            # account_info and account_assets are independent of each other
            # (both take only stake_address) -- gather them concurrently
            # rather than sequentially, a free latency win once resolve
            # (above) has the stake key.
            info, assets = await asyncio.gather(
                self._koios_post("/account_info", {"_stake_addresses": [stake_address]}),
                self._fetch_account_assets(stake_address),
            )

            if not info or not isinstance(info, list) or not info:
                return None
            account = info[0]
            # Koios returns lovelace as strings.
            utxo_ada = int(account.get('utxo', 0) or 0) / LOVELACE
            rewards_available_ada = int(account.get('rewards_available', 0) or 0) / LOVELACE
            total_balance_ada = (
                int(account['total_balance']) / LOVELACE
                if account.get('total_balance') is not None
                else utxo_ada + rewards_available_ada
            )
            ada_balance = utxo_ada

            positions = []
            nft_positions = []
            num_tokens = 0
            num_nfts = 0

            if assets and isinstance(assets, list):
                for a in assets:
                    policy_id = a.get('policy_id', '') or ''
                    asset_name = a.get('asset_name', '') or ''
                    unit = a.get('unit') or (policy_id + asset_name)
                    if unit == 'lovelace' or not unit:
                        continue
                    quantity_raw = int(a.get('quantity', 0) or 0)
                    decimals = int(a.get('decimals') or 0)
                    quantity = quantity_raw / (10 ** decimals) if decimals > 0 else float(quantity_raw)

                    pos = {
                        'unit': unit,
                        'ticker': a.get('ticker', ''),
                        'asset_name': asset_name,
                        'policy_id': policy_id,
                        'balance': quantity,
                        'raw_quantity': quantity_raw,
                        'decimals': decimals,
                        'ada_value': 0,  # Koios does not provide pricing
                        'price': 0,
                        'label': a.get('label', ''),
                    }

                    # NFT heuristic: a single indivisible unit
                    is_nft = (quantity_raw == 1 and decimals == 0)

                    positions.append(pos)
                    if is_nft:
                        nft_positions.append(pos)
                        num_nfts += 1
                    else:
                        num_tokens += 1

            result = {
                'ada_balance': ada_balance,
                'utxo_ada': utxo_ada,
                'rewards_available_ada': rewards_available_ada,
                'total_balance_ada': total_balance_ada,
                'ada_value': ada_balance,  # Koios has no pricing
                'liquid_value': ada_balance,  # no DeFi split on-chain
                'num_tokens': num_tokens,
                'num_nfts': num_nfts,
                'positions': positions,
                'nft_positions': nft_positions,
                'source': 'Koios',
                'stake_address': stake_address,
            }

            await self._cache_set(cache_key, result)
            return result

        except Exception as e:
            logger.error("Error fetching Koios portfolio: %s", type(e).__name__)
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
            rows = await self._koios_post("/account_addresses", {"_stake_addresses": [stake_address]})
            if not rows or not isinstance(rows, list):
                return []

            # Koios returns [{"stake_address": ..., "addresses": ["addr1...", ...]}]
            result = []
            for row in rows:
                for addr in (row.get('addresses') or []):
                    result.append({'address': addr, 'balance': None})

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

    async def _fetch_account_assets(self, stake_address: str) -> Optional[list]:
        """Fetch every native-asset row for a stake account (paged, 1000 rows/page)."""
        rows: list = []
        offset = 0
        while True:
            page = await self._koios_post(
                "/account_assets",
                {"_stake_addresses": [stake_address]},
                params={"limit": ASSET_PAGE_SIZE, "offset": offset},
            )
            if page is None:
                return None if offset == 0 else rows
            if not isinstance(page, list):
                return rows
            rows.extend(page)
            if len(page) < ASSET_PAGE_SIZE:
                return rows
            offset += ASSET_PAGE_SIZE

    async def _address_to_stake(self, address: str) -> Optional[str]:
        """Derive the stake address for a payment address.

        1. Local bech32 derivation (base addresses encode the stake credential;
           no network call).
        2. Koios POST /address_info (real endpoint; there is no /resolve_address).
        """
        try:
            from services.cardano import _derive_stake_key_local
            local = _derive_stake_key_local(address)
            if local:
                return local
        except Exception as e:
            logger.debug(f"Local stake derivation failed: {e}")

        info = await self._koios_post("/address_info", {"_addresses": [address]})
        if info and isinstance(info, list):
            return info[0].get('stake_address')
        return None


# Singleton instance -- routers import this exact name
taptools_wallet_service = WalletReconciliationService()
koios_reconcile_service = taptools_wallet_service
