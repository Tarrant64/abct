"""
DeFi Protocol Tracking for Cardano

Identifies DeFi protocol tokens, LP positions, and staking receipts.
Tracks staked positions, pending rewards, and APY/APR via protocol APIs.
"""

import asyncio
import httpx
import bech32
import traceback
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client

# Protocol API endpoints
INDIGO_API_BASE = "https://analytics.indigoprotocol.io"
LIQWID_REWARDS_API = "https://api.sundae-rewards.sundaeswap.finance/api/v1/liqwid"
SURF_LENDING_API = "https://api.surflending.org"

# Strike Finance staking contract
STRIKE_STAKING_ADDRESS = "addr1z9yh4zcqs4gh78ysvh8nqp40fsnxg49nn3h6x25az9k8tms6409492020k6xml8uvwn34wrexagjh5fsk5xk96jyxk2qf3a7kj"
STRIKE_STAKING_NFT_POLICY = "497a8b0085517f1c9065cf3006af4c266454b39c6fa32a9d116c75ee"
STRIKE_TOKEN_POLICY = "f13ac4d66b3ee19a6aa0f2a22298737bd907cc95121662fc971b5275"
STRIKE_REWARDS_ADDRESS = "addr1z9yh4zcqs4gh78ysvh8nqp40fsnxg49nn3h6x25az9k8tms6409492020k6xml8uvwn34wrexagjh5fsk5xk96jyxk2qf3a7kj"

# Liqwid Finance staking contract
LIQWID_STAKING_ADDRESS = "addr1w8arvq7j9qlrmt0wpdvpp7h4jr4fmfk8l653p9t907v2nsss7w7r4"
LIQWID_LQ_TOKEN = "da8c30857834c6ae7203935b89278c532b3995245295456f993e1d244c51"

# Flow Lending - liquid staking (tokens stay in wallet)
FLOW_TOKEN_POLICY = "2d9db8a89f074aa045eab177f23a3395f62ced8b53499a9e4ad46c80"
FLOW_ASSET = "2d9db8a89f074aa045eab177f23a3395f62ced8b53499a9e4ad46c80464c4f57"

# Iagon staking contracts (addresses from DefiLlama adapter maintained by Iagon)
# NOTE: Old staking contract excluded — it's deprecated and shows ~7568 IAG that was refunded
# separately. Including it would double-count staked IAG.
IAGON_OLD_STAKING_ADDRESS = "addr1w9k25wa83tyfk5d26tgx4w99e5yhxd86hg33yl7x7ej7yusggvmu3"  # DEPRECATED
IAGON_OPERATOR_STAKING_ADDRESS = "addr1zxkrtm5fcf43ukp8w8kstt65kelawutmht4a0aezl06rp43y2c4s7gthspjk2c4557c9zltqcssl4qz7x5syzf7yknhqma7zxx"
IAGON_DELEGATED_STAKING_ADDRESS = "addr1z8awewqwaek2m7w6c5vyycldf5tykw87w820da273a4smgpy2c4s7gthspjk2c4557c9zltqcssl4qz7x5syzf7yknhq6uv6j0"
IAGON_BATCHER_ADDRESS = "addr1v8ckrqqrj4u34sxt45vdu8s8nqq3lm3lc8s7su5nyzaq9tcqy2n8j"  # Active batcher/aggregator
IAGON_ALL_STAKING_ADDRESSES = {
    IAGON_OPERATOR_STAKING_ADDRESS,
    IAGON_DELEGATED_STAKING_ADDRESS, IAGON_BATCHER_ADDRESS
}
# Staking-only addresses (excluding batcher and deprecated old contract)
# The batcher is transient; only actual staking contract outputs reflect current stake
IAGON_STAKING_CONTRACT_ADDRESSES = {
    IAGON_OPERATOR_STAKING_ADDRESS,
    IAGON_DELEGATED_STAKING_ADDRESS
}
IAGON_IAG_POLICY = "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114"
IAGON_IAG_ASSET = "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114494147"

# Global semaphore to limit concurrent Iagon scans (each scan makes many Blockfrost calls).
# Without this, 44+ wallets scanning simultaneously overwhelms Blockfrost rate limits.
_iagon_scan_semaphore = asyncio.Semaphore(3)

logger = logging.getLogger(__name__)

# Known DeFi Protocol Policy IDs and Token Information
DEFI_PROTOCOLS = {
    # === Indigo Protocol ===
    "533bb94a8850ee3ccbe483106489399112b74c905342cb1792a797a0": {
        "protocol": "Indigo",
        "token": "INDY",
        "type": "governance",
        "decimals": 6,
        "description": "Indigo governance token"
    },
    "f66d78b4a3cb3d37afa0ec36461e51ecbde00f26c8f0a68f94b69880": {
        "protocol": "Indigo",
        "token": "iAsset",
        "type": "synthetic",
        "decimals": 6,
        "description": "Indigo synthetic assets (iUSD, iBTC, iETH)"
    },

    # === Liqwid Finance ===
    "da8c30857834c6ae7203935b89278c532b3995245295456f993e1d24": {
        "protocol": "Liqwid",
        "token": "LQ",
        "type": "governance",
        "decimals": 6,
        "description": "Liqwid governance token"
    },
    "d195ca7b121c6a0689e84cf3d6d526f1813e53266661c55a91027bdd": {
        "protocol": "Liqwid",
        "token": "qToken",
        "type": "receipt",
        "decimals": 6,
        "description": "Liqwid supply receipt tokens"
    },

    # === Minswap ===
    "29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c6": {
        "protocol": "Minswap",
        "token": "MIN",
        "type": "governance",
        "decimals": 6,
        "description": "Minswap governance token"
    },
    "0be55d262b29f564998ff81efe21bdc0022621c12f15af08d0f2ddb1": {
        "protocol": "Minswap",
        "token": "LP",
        "type": "lp",
        "decimals": 0,
        "description": "Minswap liquidity pool tokens"
    },
    "e4214b7cce62ac6fbba385d164df48e157eae5863521b4b67ca71d86": {
        "protocol": "Minswap",
        "token": "Farm",
        "type": "staking_receipt",
        "decimals": 0,
        "description": "Minswap yield farming receipts"
    },

    # === SundaeSwap ===
    "9a9693a9a37912a5097918f97918d15240c92ab729a0b7c4aa144d77": {
        "protocol": "SundaeSwap",
        "token": "SUNDAE",
        "type": "governance",
        "decimals": 6,
        "description": "SundaeSwap governance token"
    },
    "0029cb7c88c7567b63d1a512c0ed626aa169688ec980730c0473b913": {
        "protocol": "SundaeSwap",
        "token": "LP",
        "type": "lp",
        "decimals": 0,
        "description": "SundaeSwap liquidity pool tokens"
    },

    # === Strike Finance ===
    "f13ac4d66b3ee19a6aa0f2a22298737bd907cc95121662fc971b5275": {
        "protocol": "Strike",
        "token": "STRIKE",
        "type": "governance",
        "decimals": 6,
        "description": "Strike Finance governance token"
    },

    # === WingRiders ===
    "c0ee29a85b13209423b10447d3c2e6a50641a15c57770e27cb9d5073": {
        "protocol": "WingRiders",
        "token": "WRT",
        "type": "governance",
        "decimals": 6,
        "description": "WingRiders governance token"
    },
    "026a18d04a0c642759bb3d83b12e3344894e5c1c7b2aeb1a2113a570": {
        "protocol": "WingRiders",
        "token": "LP",
        "type": "lp",
        "decimals": 0,
        "description": "WingRiders liquidity pool tokens"
    },

    # === DJED Stablecoin ===
    "8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61": {
        "protocol": "DJED",
        "token": "DJED",
        "type": "stablecoin",
        "decimals": 6,
        "description": "DJED algorithmic stablecoin"
    },
    "884892bcdc360bcef87d6b3f806e7f9cd5ac30d999d49970e7a903ae": {
        "protocol": "DJED",
        "token": "SHEN",
        "type": "reserve",
        "decimals": 6,
        "description": "SHEN reserve token"
    },

    # === Lenfi (formerly Aada) ===
    "8fef2d34078659493ce161a6c7fba4b56afefa8535296a5743f69587": {
        "protocol": "Lenfi",
        "token": "LENFI",
        "type": "governance",
        "decimals": 6,
        "description": "Lenfi governance token"
    },

    # === Optim Finance ===
    "e52964af4fffdb54504859875b1827b60ba679074996571f26b8ca14": {
        "protocol": "Optim",
        "token": "OADA",
        "type": "liquid_staking",
        "decimals": 6,
        "description": "Optim liquid staked ADA"
    },

    # === Spectrum Finance (DEFUNCT - protocol shut down Sept 2025, SPF airdrop refund completed) ===
    "6c8642400e8437f737eb86df0fc8a8437c760f48592b1ba8f5767e81": {
        "protocol": "Spectrum",
        "token": "SPF",
        "type": "reserve",
        "decimals": 6,
        "description": "Spectrum Finance token (protocol discontinued)"
    },

    # === Flow Lending ===
    "2d9db8a89f074aa045eab177f23a3395f62ced8b53499a9e4ad46c80": {
        "protocol": "Flow Lending",
        "token": "FLOW",
        "type": "liquid_staking",
        "decimals": 6,
        "description": "Flow Lending - tokens stay in wallet (liquid staking)"
    },

    # === VyFinance ===
    "804f5544c1962a40546827cab750a88404dc7108c0f588b72c2e2c91": {
        "protocol": "VyFinance",
        "token": "VYFI",
        "type": "governance",
        "decimals": 6,
        "description": "VyFinance governance token"
    },

    # === Stablecoins ===
    "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff935": {
        "protocol": "Wanchain",
        "token": "USDC",
        "type": "stablecoin",
        "decimals": 6,
        "description": "Bridged USDC"
    },
    "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff93555534454": {
        "protocol": "Wanchain",
        "token": "USDT",
        "type": "stablecoin",
        "decimals": 6,
        "description": "Bridged USDT"
    },
    "25c5de5f5b286073c593edfd77b48abc7a48e5a4f3d4cd9d428ff935444149": {
        "protocol": "Wanchain",
        "token": "DAI",
        "type": "stablecoin",
        "decimals": 6,
        "description": "Bridged DAI"
    },

    # === FluidTokens (CIP-68 token) ===
    "577f0b1342f8f8f4aed3388b80a8535812950c7a892495c0ecdf0f1e": {
        "protocol": "FluidTokens",
        "token": "FLDT",
        "type": "governance",
        "decimals": 6,
        "description": "FluidTokens governance token (FluidDAO)"
    },

    # === Iagon (DePIN - utility token, NOT governance) ===
    "5d16cc1a177b5d9ba9cfa9793b07e60f1fb70fea1f8aef064415d114": {
        "protocol": "Iagon",
        "token": "IAG",
        "type": "depin",
        "decimals": 6,
        "description": "Iagon DePIN utility token"
    },

    # === SingularityNET ===
    "f43a62fdc3965df486de8a0d32fe800963589c41b38946602a0dc535": {
        "protocol": "SingularityNET",
        "token": "AGIX",
        "type": "governance",
        "decimals": 8,
        "description": "SingularityNET AI token"
    },

    # === Xerberus ===
    "6d06570ddd778ec7c0cca09d381eca194e90c8cffa7582879735dbde": {
        "protocol": "Xerberus",
        "token": "XER",
        "type": "governance",
        "decimals": 6,
        "description": "Xerberus risk management token"
    },
}

# Token type categories for display
TOKEN_CATEGORIES = {
    "governance": "Governance Tokens",
    "lp": "Liquidity Pool Tokens",
    "staking_receipt": "Staking Receipts",
    "receipt": "Protocol Receipts",
    "synthetic": "Synthetic Assets",
    "stablecoin": "Stablecoins",
    "reserve": "Reserve Tokens",
    "liquid_staking": "Liquid Staking",
    "depin": "DePIN Tokens",
}


class DeFiService:
    """Service for tracking Cardano DeFi positions."""

    def __init__(self):
        self.headers = {"project_id": BLOCKFROST_API_KEY}

    async def analyze_wallet_defi(self, address: str) -> Optional[Dict]:
        """
        Analyze a wallet's DeFi positions.

        Returns categorized DeFi holdings including:
        - Protocol tokens (governance, LP, receipts)
        - Stablecoins
        - Summary by protocol
        """
        try:
            client = get_client("blockfrost", timeout=30.0)
            # Get all UTXOs
            logger.info(f"[DeFi] Fetching UTXOs for {address[:20]}... API key present: {bool(self.headers.get('project_id'))}")
            response = await client.get(
                f"{BLOCKFROST_BASE_URL}/addresses/{address}/utxos",
                headers=self.headers,
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"[DeFi] Failed to get UTXOs for {address[:20]}...: HTTP {response.status_code} - {response.text[:200]}")
                return None

            utxos = response.json()
            logger.info(f"[DeFi] Got {len(utxos)} UTXOs for {address[:20]}...")

            # Analyze assets
            defi_positions = {}
            protocol_summary = {}

            for utxo in utxos:
                for amount in utxo.get('amount', []):
                    unit = amount['unit']
                    quantity = int(amount['quantity'])

                    if unit == 'lovelace':
                        continue

                    policy_id = unit[:56]
                    asset_name_hex = unit[56:]

                    # Decode asset name
                    try:
                        asset_name = bytes.fromhex(asset_name_hex).decode('utf-8') if asset_name_hex else ""
                    except Exception:
                        asset_name = asset_name_hex

                    # Check if it's a known DeFi token
                    if policy_id in DEFI_PROTOCOLS:
                        info = DEFI_PROTOCOLS[policy_id]
                        protocol = info['protocol']
                        token = info['token']
                        token_type = info['type']
                        decimals = info['decimals']

                        # Create unique key
                        key = f"{protocol}:{token}"
                        if asset_name and token in ['LP', 'qToken', 'iAsset']:
                            key = f"{protocol}:{token}:{asset_name}"

                        if key not in defi_positions:
                            defi_positions[key] = {
                                'protocol': protocol,
                                'token': token,
                                'asset_name': asset_name or token,
                                'type': token_type,
                                'type_label': TOKEN_CATEGORIES.get(token_type, token_type),
                                'quantity_raw': 0,
                                'decimals': decimals,
                                'description': info['description'],
                                'policy_id': policy_id
                            }

                        defi_positions[key]['quantity_raw'] += quantity

                        # Update protocol summary
                        if protocol not in protocol_summary:
                            protocol_summary[protocol] = {
                                'protocol': protocol,
                                'tokens': [],
                                'has_governance': False,
                                'has_lp': False,
                                'has_staking': False
                            }

                        if token_type == 'governance':
                            protocol_summary[protocol]['has_governance'] = True
                        elif token_type == 'lp':
                            protocol_summary[protocol]['has_lp'] = True
                        elif token_type in ['staking_receipt', 'receipt']:
                            protocol_summary[protocol]['has_staking'] = True

            # Calculate formatted quantities
            for key, pos in defi_positions.items():
                pos['quantity'] = pos['quantity_raw'] / (10 ** pos['decimals'])
                pos['quantity_formatted'] = f"{pos['quantity']:,.6f}".rstrip('0').rstrip('.')

                # Add to protocol summary
                protocol = pos['protocol']
                if protocol in protocol_summary:
                    protocol_summary[protocol]['tokens'].append({
                        'token': pos['asset_name'],
                        'type': pos['type_label'],
                        'quantity': pos['quantity_formatted']
                    })

            # Fetch logo URLs for governance tokens
            gov_tokens = [pos['token'] for pos in defi_positions.values() if pos['type'] == 'governance']
            if gov_tokens:
                logo_coros = {t: self._get_token_logo_url(t) for t in set(gov_tokens)}
                logo_results = await asyncio.gather(*logo_coros.values(), return_exceptions=True)
                logo_map = {}
                for t, result in zip(logo_coros.keys(), logo_results):
                    if isinstance(result, str):
                        logo_map[t] = result
                for pos in defi_positions.values():
                    if pos['type'] == 'governance' and pos['token'] in logo_map:
                        pos['logo_url'] = logo_map[pos['token']]

            # Categorize by type
            by_category = {}
            for key, pos in defi_positions.items():
                cat = pos['type_label']
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(pos)

            logger.info(f"[DeFi] Found {len(defi_positions)} DeFi positions in {address[:20]}... Categories: {list(by_category.keys())}")

            return {
                'address': address,
                'defi_positions': list(defi_positions.values()),
                'by_category': by_category,
                'protocol_summary': list(protocol_summary.values()),
                'total_protocols': len(protocol_summary),
                'total_positions': len(defi_positions)
            }

        except Exception as e:
            logger.error(f"[DeFi] Error analyzing DeFi for {address[:20]}...: {e}\n{traceback.format_exc()}")
            return None

    async def get_protocol_info(self, protocol_name: str) -> Dict:
        """Get information about a specific DeFi protocol."""
        protocol_tokens = []

        for policy_id, info in DEFI_PROTOCOLS.items():
            if info['protocol'].lower() == protocol_name.lower():
                protocol_tokens.append({
                    'token': info['token'],
                    'type': info['type'],
                    'decimals': info['decimals'],
                    'description': info['description'],
                    'policy_id': policy_id
                })

        return {
            'protocol': protocol_name,
            'tokens': protocol_tokens
        }

    def get_supported_protocols(self) -> List[str]:
        """Get list of supported DeFi protocols."""
        protocols = set()
        for info in DEFI_PROTOCOLS.values():
            protocols.add(info['protocol'])
        return sorted(list(protocols))

    async def get_indigo_staking(self, address: str) -> Optional[Dict]:
        """
        Get Indigo Protocol staking positions for an address.
        Uses Indigo Analytics API to find staked INDY.
        """
        try:
            # Extract payment credential from address
            payment_cred = self._get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)

            # Fetch all staking positions from Indigo
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/staking/positions"
            )

            if response.status_code != 200:
                logger.error(f"Indigo API error: {response.status_code}")
                return None

            positions = response.json()

            # Find positions matching this payment credential
            user_positions = []
            total_staked = 0

            for pos in positions:
                if pos.get('owner') == payment_cred:
                    staked = pos.get('stakedIndy', 0)
                    total_staked += staked
                    user_positions.append({
                        'staked_indy_raw': staked,
                        'staked_indy': staked / 1_000_000,
                        'snapshot_ada': pos.get('snapshotAda', 0) / 1_000_000,
                        'slot': pos.get('slot'),
                        'output_hash': pos.get('outputHash')
                    })

            if not user_positions:
                return None

            return {
                'protocol': 'Indigo',
                'address': address,
                'positions': user_positions,
                'total_staked_indy': total_staked / 1_000_000,
                'position_count': len(user_positions)
            }

        except Exception as e:
            logger.error(f"Error getting Indigo staking: {e}")
            return None

    def _get_payment_credential(self, address: str) -> Optional[str]:
        """Extract payment credential (key hash) from a Cardano address."""
        try:
            hrp, data = bech32.bech32_decode(address)
            if data is None:
                return None

            decoded = bech32.convertbits(data, 5, 8, False)
            if decoded is None or len(decoded) < 29:
                return None

            # First byte is header, next 28 bytes are payment credential
            return bytes(decoded[1:29]).hex()

        except Exception as e:
            logger.error(f"Error decoding address: {e}")
            return None

    async def get_liqwid_staking(self, address: str) -> Optional[Dict]:
        """
        Get Liqwid Finance staking positions for an address.
        Queries the Liqwid staking contract for UTxOs with matching user PKH in datum.
        Uses parallel page fetching to handle large contract state (2700+ UTxOs).
        """
        try:
            # Extract payment credential from address
            payment_cred = self._get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)
            sem = asyncio.Semaphore(5)  # Limit concurrent Blockfrost requests

            async def fetch_page(pg):
                async with sem:
                    try:
                        resp = await client.get(
                            f"{BLOCKFROST_BASE_URL}/addresses/{LIQWID_STAKING_ADDRESS}/utxos",
                            headers=self.headers,
                            params={"count": 100, "page": pg}
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        elif resp.status_code == 404:
                            return []  # No more pages
                        else:
                            logger.warning(f"[Liqwid] Page {pg} returned HTTP {resp.status_code}")
                            return None  # Error — eligible for retry
                    except Exception as e:
                        logger.warning(f"[Liqwid] Page {pg} fetch failed: {e}")
                        return None

            # Phase 1: Fetch first page to confirm contract has UTxOs
            first_page = await fetch_page(1)
            if not first_page:
                return None

            # Phase 2: Fetch remaining pages in parallel (contract has ~2700+ UTxOs = ~28 pages)
            remaining = await asyncio.gather(
                *[fetch_page(pg) for pg in range(2, 31)],
                return_exceptions=True
            )

            all_utxos = list(first_page)
            failed_pages = []
            for i, result in enumerate(remaining):
                pg = i + 2
                if isinstance(result, Exception):
                    logger.warning(f"[Liqwid] Page {pg} raised exception: {result}")
                    failed_pages.append(pg)
                elif result is None:
                    failed_pages.append(pg)
                else:
                    all_utxos.extend(result)

            # Retry failed pages sequentially (rate-limit safe)
            if failed_pages:
                logger.info(f"[Liqwid] Retrying {len(failed_pages)} failed pages sequentially...")
                for pg in failed_pages:
                    try:
                        result = await fetch_page(pg)
                        if result:
                            all_utxos.extend(result)
                    except Exception as e:
                        logger.warning(f"[Liqwid] Retry page {pg} failed: {e}")

            logger.info(f"[Liqwid] Scanned {len(all_utxos)} UTxOs for PKH {payment_cred[:16]}...")

            # Search for UTxOs with user's PKH in the inline datum
            positions = []
            total_staked = 0

            for utxo in all_utxos:
                inline_datum = utxo.get('inline_datum') or ''

                # Check if user's PKH is in the datum
                if inline_datum and payment_cred in inline_datum:
                    lq_amount = 0
                    for asset in utxo.get('amount', []):
                        if asset.get('unit') == LIQWID_LQ_TOKEN:
                            lq_amount = int(asset.get('quantity', 0))

                    if lq_amount > 0:
                        total_staked += lq_amount
                        positions.append({
                            'tx_hash': utxo.get('tx_hash'),
                            'output_index': utxo.get('output_index'),
                            'staked_lq_raw': lq_amount,
                            'staked_lq': lq_amount / 1_000_000
                        })

            if not positions:
                logger.info(f"[Liqwid] No positions found in {len(all_utxos)} UTxOs for {address[:20]}...")
                return None

            logger.info(f"[Liqwid] Found {len(positions)} positions, {total_staked/1_000_000:.2f} LQ for {address[:20]}...")
            return {
                'protocol': 'Liqwid',
                'address': address,
                'positions': positions,
                'total_staked_lq': total_staked / 1_000_000,
                'position_count': len(positions)
            }

        except Exception as e:
            logger.error(f"Error getting Liqwid staking: {e}")
            return None

    async def get_strike_staking(self, address: str) -> Optional[Dict]:
        """
        Get Strike Finance staking positions for an address.
        Queries the Strike staking contract for UTxOs with matching user NFT.
        Uses parallel page fetching to handle large contract state (1000+ UTxOs).
        """
        try:
            # Extract payment credential from address
            payment_cred = self._get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)
            sem = asyncio.Semaphore(5)

            async def fetch_page(pg):
                async with sem:
                    try:
                        resp = await client.get(
                            f"{BLOCKFROST_BASE_URL}/addresses/{STRIKE_STAKING_ADDRESS}/utxos",
                            headers=self.headers,
                            params={"count": 100, "page": pg}
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        elif resp.status_code == 404:
                            return []
                        else:
                            logger.warning(f"[Strike] Page {pg} returned HTTP {resp.status_code}")
                            return None
                    except Exception as e:
                        logger.warning(f"[Strike] Page {pg} fetch failed: {e}")
                        return None

            # Fetch first page, then remaining in parallel
            first_page = await fetch_page(1)
            if not first_page:
                return None

            remaining = await asyncio.gather(
                *[fetch_page(pg) for pg in range(2, 16)],
                return_exceptions=True
            )

            all_utxos = list(first_page)
            failed_pages = []
            for i, result in enumerate(remaining):
                pg = i + 2
                if isinstance(result, Exception):
                    logger.warning(f"[Strike] Page {pg} raised exception: {result}")
                    failed_pages.append(pg)
                elif result is None:
                    failed_pages.append(pg)
                else:
                    all_utxos.extend(result)

            if failed_pages:
                logger.info(f"[Strike] Retrying {len(failed_pages)} failed pages sequentially...")
                for pg in failed_pages:
                    try:
                        result = await fetch_page(pg)
                        if result:
                            all_utxos.extend(result)
                    except Exception as e:
                        logger.warning(f"[Strike] Retry page {pg} failed: {e}")

            logger.info(f"[Strike] Scanned {len(all_utxos)} UTxOs for PKH {payment_cred[:16]}...")

            # Search for UTxOs with user's staking NFT
            total_staked = 0
            positions = []

            for utxo in all_utxos:
                has_user_nft = False
                strike_amount = 0

                for asset in utxo.get('amount', []):
                    unit = asset.get('unit', '')
                    qty = int(asset.get('quantity', 0))

                    # Check if this UTxO has an NFT with user's PKH
                    if unit.startswith(STRIKE_STAKING_NFT_POLICY):
                        asset_name = unit[len(STRIKE_STAKING_NFT_POLICY):]
                        if asset_name == payment_cred:
                            has_user_nft = True

                    # Check for STRIKE tokens
                    if unit.startswith(STRIKE_TOKEN_POLICY):
                        strike_amount = qty

                if has_user_nft and strike_amount > 0:
                    total_staked += strike_amount
                    positions.append({
                        'tx_hash': utxo.get('tx_hash'),
                        'output_index': utxo.get('output_index'),
                        'staked_strike_raw': strike_amount,
                        'staked_strike': strike_amount / 1_000_000
                    })

            if not positions:
                return None

            return {
                'protocol': 'Strike',
                'address': address,
                'positions': positions,
                'total_staked_strike': total_staked / 1_000_000,
                'position_count': len(positions)
            }

        except Exception as e:
            logger.error(f"Error getting Strike staking: {e}")
            return None

    async def get_iagon_staking(self, address: str) -> Optional[Dict]:
        """
        Get Iagon staking position for an address.

        Checks all 3 Iagon staking contracts (old, operator, delegated).
        Uses incremental scanning — caches last-scanned block height and
        accumulated deposit/withdrawal totals so subsequent calls only
        scan new transactions.

        Uses a global semaphore (_iagon_scan_semaphore) to limit concurrent
        scans — each scan makes many Blockfrost API calls and running 44+
        in parallel overwhelms rate limits.
        """
        from database import get_cache, set_cache

        async with _iagon_scan_semaphore:
            return await self._get_iagon_staking_inner(address)

    async def _get_iagon_staking_inner(self, address: str) -> Optional[Dict]:
        """Inner implementation of Iagon staking scan (called under semaphore)."""
        from database import get_cache, set_cache

        try:
            client = get_client("blockfrost", timeout=15.0)

            # Load incremental scan state from persistent cache (7-day TTL)
            # Version marker: bump when calculation logic changes to invalidate stale data
            SCAN_STATE_VERSION = 5  # v5: exclude deprecated old staking contract (refunded separately)
            scan_key = f"iagon_scan_state_{address}"
            scan_state = await get_cache(scan_key)

            # Track flows through STAKING CONTRACTS ONLY (not batcher).
            # Key insight from on-chain analysis:
            #   - Principal deposits/withdrawals go through staking contract addresses
            #   - Reward claims go through the batcher ONLY
            # By ignoring batcher-only flows, we get accurate staked = deposits - withdrawals.
            staking_deposits = 0
            staking_withdrawals = 0
            total_rewards = 0  # informational: batcher-only outflows (reward claims)
            from_block = None

            if scan_state and scan_state.get('version') == SCAN_STATE_VERSION:
                staking_deposits = scan_state.get('staking_deposits', 0)
                staking_withdrawals = scan_state.get('staking_withdrawals', 0)
                total_rewards = scan_state.get('total_rewards', 0)
                from_block = scan_state.get('last_block_height')
                logger.info(f"[Iagon] Resuming scan for {address[:20]}... from block {from_block}, "
                           f"staked={(staking_deposits - staking_withdrawals)/1_000_000:.2f} IAG")
            elif scan_state:
                logger.info(f"[Iagon] Discarding stale v{scan_state.get('version', 1)} scan state for {address[:20]}... (need v{SCAN_STATE_VERSION})")

            # Fetch transactions (incremental if we have scan state)
            all_txs = []
            page = 1

            while True:
                params = {"count": 100, "page": page, "order": "asc"}
                if from_block:
                    # Start from next block to avoid re-processing already-counted txs
                    params["from"] = str(from_block + 1)

                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/addresses/{address}/transactions",
                    headers=self.headers,
                    params=params
                )

                if response.status_code != 200:
                    break

                txs = response.json()
                if not txs:
                    break

                all_txs.extend(txs)
                if len(txs) < 100:
                    break  # Last page
                page += 1

            logger.info(f"[Iagon] Scanned {len(all_txs)} {'new ' if from_block else ''}transactions "
                       f"across {page} pages for {address[:20]}...")

            # If incremental and no new txs, return cached result
            if from_block and not all_txs:
                net_staked = staking_deposits - staking_withdrawals
                if net_staked <= 0:
                    return None
                return {
                    'protocol': 'Iagon',
                    'address': address,
                    'total_staked_iag': net_staked / 1_000_000,
                    'total_deposited': staking_deposits / 1_000_000,
                    'total_withdrawn': staking_withdrawals / 1_000_000,
                    'total_rewards_claimed': total_rewards / 1_000_000,
                    'position_count': 1,
                    'contract': 'multiple'
                }

            if not all_txs and not scan_state:
                return None

            # Fetch UTxOs in parallel batches (5 concurrent to respect Blockfrost limits)
            sem = asyncio.Semaphore(5)

            async def fetch_tx_utxos(tx_hash):
                async with sem:
                    try:
                        resp = await client.get(
                            f"{BLOCKFROST_BASE_URL}/txs/{tx_hash}/utxos",
                            headers=self.headers
                        )
                        if resp.status_code == 200:
                            return resp.json()
                        else:
                            logger.warning(f"[Iagon] UTxO fetch for tx {tx_hash[:16]} returned HTTP {resp.status_code}")
                            return None
                    except Exception as e:
                        logger.warning(f"[Iagon] UTxO fetch for tx {tx_hash[:16]} failed: {e}")
                        return None

            if all_txs:
                utxo_results = await asyncio.gather(
                    *[fetch_tx_utxos(tx['tx_hash']) for tx in all_txs],
                    return_exceptions=True
                )

                # Track last block for incremental scan
                last_block = from_block or 0

                for i, tx_data in enumerate(utxo_results):
                    if isinstance(tx_data, Exception) or tx_data is None:
                        continue

                    tx_block = all_txs[i].get('block_height', 0)
                    if tx_block > last_block:
                        last_block = tx_block

                    # Calculate IAG flows separately for staking contracts vs batcher
                    staking_receives = 0  # IAG received by staking contracts
                    staking_sends = 0     # IAG sent from staking contracts
                    batcher_receives = 0  # IAG received by batcher
                    batcher_sends = 0     # IAG sent from batcher
                    user_receives_iag = 0

                    for inp in tx_data.get('inputs', []):
                        for amt in inp.get('amount', []):
                            if amt['unit'] == IAGON_IAG_ASSET:
                                qty = int(amt['quantity'])
                                if inp['address'] in IAGON_STAKING_CONTRACT_ADDRESSES:
                                    staking_sends += qty
                                elif inp['address'] == IAGON_BATCHER_ADDRESS:
                                    batcher_sends += qty

                    for out in tx_data.get('outputs', []):
                        for amt in out.get('amount', []):
                            if amt['unit'] == IAGON_IAG_ASSET:
                                qty = int(amt['quantity'])
                                if out['address'] == address:
                                    user_receives_iag += qty
                                elif out['address'] in IAGON_STAKING_CONTRACT_ADDRESSES:
                                    staking_receives += qty
                                elif out['address'] == IAGON_BATCHER_ADDRESS:
                                    batcher_receives += qty

                    # Track staking contract flows (principal deposits/withdrawals)
                    net_to_staking = staking_receives - staking_sends
                    if net_to_staking > 0:
                        staking_deposits += net_to_staking
                    elif net_to_staking < 0:
                        staking_withdrawals += abs(net_to_staking)

                    # Track batcher-only flows as reward claims (informational)
                    if staking_sends == 0 and staking_receives == 0:
                        net_batcher = batcher_receives - batcher_sends
                        if net_batcher < 0 and user_receives_iag > 0:
                            total_rewards += user_receives_iag

                # Save scan state persistently (7-day TTL)
                await set_cache(scan_key, {
                    'version': SCAN_STATE_VERSION,
                    'staking_deposits': staking_deposits,
                    'staking_withdrawals': staking_withdrawals,
                    'total_rewards': total_rewards,
                    'last_block_height': last_block
                }, ttl_seconds=604800)

            net_staked = staking_deposits - staking_withdrawals

            logger.info(f"[Iagon] {address[:20]}... staked={net_staked/1_000_000:.2f} IAG "
                         f"(deposits={staking_deposits/1_000_000:.2f}, withdrawals={staking_withdrawals/1_000_000:.2f}, "
                         f"rewards_claimed={total_rewards/1_000_000:.2f})")

            if net_staked <= 0:
                return None

            return {
                'protocol': 'Iagon',
                'address': address,
                'total_staked_iag': net_staked / 1_000_000,
                'total_deposited': staking_deposits / 1_000_000,
                'total_withdrawn': staking_withdrawals / 1_000_000,
                'total_rewards_claimed': total_rewards / 1_000_000,
                'position_count': 1,
                'contract': 'multiple'
            }

        except Exception as e:
            logger.error(f"Error getting Iagon staking: {e}")
            return None

    async def get_indigo_pending_rewards(self, address: str) -> Optional[Dict]:
        """
        Get pending INDY and ADA rewards from Indigo Protocol.
        Uses Indigo Analytics API to fetch pending rewards.
        Indigo stakers earn both INDY and ADA rewards.

        The snapshotAda field represents the ADA snapshot used for rewards calculation.
        The lockedAmount represents locked INDY that may include accumulated rewards.
        """
        try:
            payment_cred = self._get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)

            # Fetch staking positions which include rewards data
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/staking/positions"
            )

            if response.status_code != 200:
                logger.warning(f"Indigo staking API returned {response.status_code}")
                return None

            positions_data = response.json()

            # Find user's positions and rewards
            total_staked = 0
            total_locked = 0
            snapshot_ada = 0

            for pos in positions_data:
                if pos.get('owner') == payment_cred:
                    staked = pos.get('stakedIndy', 0) / 1_000_000

                    # lockedAmount can be a dict or int
                    locked_raw = pos.get('lockedAmount', 0)
                    if isinstance(locked_raw, dict):
                        # Sum values if it's a dict of token amounts
                        locked = sum(v for v in locked_raw.values() if isinstance(v, (int, float))) / 1_000_000
                    else:
                        locked = locked_raw / 1_000_000

                    ada_snapshot = pos.get('snapshotAda', 0) / 1_000_000

                    total_staked += staked
                    total_locked += locked
                    snapshot_ada += ada_snapshot

                    logger.info(f"Indigo position: staked={staked:.2f}, locked={locked:.2f}, snapshotAda={ada_snapshot:.2f}")

            # snapshotAda is the ADA backing/collateral value, not pending rewards
            # Actual pending rewards require epoch-based calculation not available via this API
            # For now, we show the staked amount and link to the app for actual rewards
            pending_indy = max(0, total_locked - total_staked) if total_locked > 0 else 0

            return {
                'protocol': 'Indigo',
                'pending_indy': pending_indy,
                'pending_ada': 0,  # ADA rewards need to be checked in app
                'total_staked': total_staked,
                'ada_backing': snapshot_ada,  # ADA collateral backing the position
                'reward_tokens': ['INDY', 'ADA'],
                'rewards_url': 'https://app.indigoprotocol.io/earn'
            }

        except Exception as e:
            logger.error(f"Error fetching Indigo rewards: {e}")
            return None

    async def _get_indigo_apy(self, client: httpx.AsyncClient) -> Optional[float]:
        """Fetch current Indigo staking APY."""
        try:
            response = await client.get(f"{INDIGO_API_BASE}/api/v1/protocol/stats")
            if response.status_code == 200:
                stats = response.json()
                return stats.get('stakingApy', stats.get('apy'))
        except Exception as e:
            logger.warning(f"Could not fetch Indigo APY: {e}")
        return None

    async def get_strike_pending_rewards(self, address: str, staking_data=None) -> Optional[Dict]:
        """
        Get pending STRIKE rewards.
        Calculated from staking duration and reward rate.

        Args:
            staking_data: Optional pre-fetched staking data to avoid re-scanning contracts.
        """
        try:
            payment_cred = self._get_payment_credential(address)
            if not payment_cred:
                return None

            # Reuse Phase 1 staking data if provided, otherwise fetch
            staking = staking_data or await self.get_strike_staking(address)
            if not staking or staking['total_staked_strike'] == 0:
                return None

            client = get_client("blockfrost", timeout=15.0)

            # Query Strike rewards contract for pending rewards
            # Strike uses epoch-based rewards distribution
            pending_strike = 0
            accumulated_rewards = 0

            # Check for pending rewards in the staking UTxOs datum
            response = await client.get(
                f"{BLOCKFROST_BASE_URL}/addresses/{STRIKE_STAKING_ADDRESS}/utxos",
                headers=self.headers,
                params={"count": 100}
            )

            if response.status_code == 200:
                utxos = response.json()
                for utxo in utxos:
                    # Check if this UTxO belongs to user
                    has_user_nft = False
                    for asset in utxo.get('amount', []):
                        unit = asset.get('unit', '')
                        if unit.startswith(STRIKE_STAKING_NFT_POLICY):
                            asset_name = unit[len(STRIKE_STAKING_NFT_POLICY):]
                            if asset_name == payment_cred:
                                has_user_nft = True
                                break

                    if has_user_nft:
                        # Check for STRIKE tokens in the UTxO (accumulated rewards)
                        for asset in utxo.get('amount', []):
                            unit = asset.get('unit', '')
                            if unit.startswith(STRIKE_TOKEN_POLICY) and unit != f"{STRIKE_TOKEN_POLICY}":
                                # This might be accumulated rewards in the staking UTxO
                                qty = int(asset.get('quantity', 0))
                                if qty > 0:
                                    accumulated_rewards += qty / 1_000_000

            return {
                'protocol': 'Strike',
                'pending_rewards': pending_strike,
                'accumulated_rewards': accumulated_rewards,
                'reward_token': 'STRIKE',
                'staked_amount': staking['total_staked_strike'],
                'rewards_url': 'https://app.strikefinance.org/perpetuals/ada'
            }

        except Exception as e:
            logger.error(f"Error fetching Strike rewards: {e}")
            return None

    async def get_liqwid_pending_rewards(self, address: str, staking_data=None) -> Optional[Dict]:
        """
        Get pending LQ rewards from Liqwid Finance via SundaeSwap rewards portal.

        Args:
            staking_data: Optional pre-fetched staking data to avoid re-scanning contracts.
        """
        try:
            # Get stake address from wallet address
            stake_address = await self._get_stake_address(address)

            client = get_client("blockfrost", timeout=15.0)

            pending_lq = 0
            claimed_lq = 0
            total_earned = 0

            if stake_address:
                try:
                    # Liqwid rewards API requires POST with stake address
                    response = await client.post(
                        f"{LIQWID_REWARDS_API}/rewards",
                        json={"stakeAddress": stake_address},
                        headers={"Content-Type": "application/json"}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        rewards_data = data.get('rewards', {})
                        # Parse rewards data - structure: {epochNumber: {pending: X, claimed: Y}}
                        for epoch, epoch_data in rewards_data.items():
                            if isinstance(epoch_data, dict):
                                pending_lq += epoch_data.get('pending', 0) / 1_000_000
                                claimed_lq += epoch_data.get('claimed', 0) / 1_000_000
                        total_earned = pending_lq + claimed_lq
                        logger.info(f"Liqwid rewards for {stake_address[:20]}...: pending={pending_lq}, claimed={claimed_lq}")
                except Exception as e:
                    logger.warning(f"Could not fetch from Liqwid rewards API: {e}")

            # Reuse Phase 1 staking data if provided, otherwise fetch
            staking = staking_data if staking_data is not None else await self.get_liqwid_staking(address)
            staked_amount = staking['total_staked_lq'] if staking else 0

            return {
                'protocol': 'Liqwid',
                'pending_rewards': pending_lq,
                'claimed_rewards': claimed_lq,
                'total_earned': total_earned,
                'reward_token': 'LQ',
                'staked_amount': staked_amount,
                'rewards_url': 'https://liqwid-rewards.sundaeswap.finance/'
            }

        except Exception as e:
            logger.error(f"Error fetching Liqwid rewards: {e}")
            return None

        return None

    async def _get_stake_address(self, address: str) -> Optional[str]:
        """Get the stake address associated with a wallet address."""
        try:
            client = get_client("blockfrost", timeout=30.0)
            response = await client.get(
                f"{BLOCKFROST_BASE_URL}/addresses/{address}",
                headers=self.headers
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('stake_address')
        except Exception as e:
            logger.warning(f"Could not get stake address: {e}")
        return None

    async def get_surf_lending_positions(self, address: str) -> Optional[Dict]:
        """
        Get Surf Lending (formerly Flow Lending) staking positions.
        """
        try:
            payment_cred = self._get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)

            # Try Surf Lending API
            try:
                response = await client.get(
                    f"{SURF_LENDING_API}/api/v1/positions/{address}"
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        'protocol': 'Surf Lending',
                        'positions': data.get('positions', []),
                        'total_supplied': data.get('total_supplied', 0),
                        'total_borrowed': data.get('total_borrowed', 0),
                        'pending_rewards': data.get('pending_rewards', 0),
                        'apy': data.get('supply_apy')
                    }
            except Exception as e:
                logger.warning(f"Surf Lending API not available: {e}")

            # Fallback: Query on-chain data
            from services.defi_protocols.cardano.surf import SURF_STAKING_ADDRESS
            if not SURF_STAKING_ADDRESS:
                logger.warning("[Surf] No staking address configured for on-chain fallback — skipping")
                return None

            response = await client.get(
                f"{BLOCKFROST_BASE_URL}/addresses/{SURF_STAKING_ADDRESS}/utxos",
                headers=self.headers,
                params={"count": 100}
            )

            if response.status_code != 200:
                return None

            utxos = response.json()
            positions = []
            total_supplied = 0

            for utxo in utxos:
                inline_datum = utxo.get('inline_datum') or ''
                if payment_cred in inline_datum:
                    # Found user's position
                    ada_amount = 0
                    for asset in utxo.get('amount', []):
                        if asset.get('unit') == 'lovelace':
                            ada_amount = int(asset.get('quantity', 0)) / 1_000_000

                    if ada_amount > 0:
                        total_supplied += ada_amount
                        positions.append({
                            'tx_hash': utxo.get('tx_hash'),
                            'supplied_ada': ada_amount
                        })

            if positions:
                return {
                    'protocol': 'Surf Lending',
                    'address': address,
                    'positions': positions,
                    'total_supplied_ada': total_supplied,
                    'position_count': len(positions)
                }

        except Exception as e:
            logger.error(f"Error getting Surf Lending positions: {e}")
            return None

        return None

    async def get_all_pending_rewards(self, address: str) -> Dict:
        """
        Get all pending rewards across all supported protocols.
        Uses parallel fetching for all protocols simultaneously.
        """
        import asyncio

        rewards = {
            'address': address,
            'protocols': {},
            'total_pending_usd': 0  # Will be calculated with prices
        }

        # Fetch rewards from all protocols in parallel
        indigo_rewards, strike_rewards, liqwid_rewards = await asyncio.gather(
            self.get_indigo_pending_rewards(address),
            self.get_strike_pending_rewards(address),
            self.get_liqwid_pending_rewards(address),
            return_exceptions=True
        )

        if not isinstance(indigo_rewards, Exception) and indigo_rewards and indigo_rewards.get('pending_rewards', 0) > 0:
            rewards['protocols']['Indigo'] = indigo_rewards
        if not isinstance(strike_rewards, Exception) and strike_rewards:
            rewards['protocols']['Strike'] = strike_rewards
        if not isinstance(liqwid_rewards, Exception) and liqwid_rewards:
            rewards['protocols']['Liqwid'] = liqwid_rewards

        return rewards

    async def _get_token_logo_url(self, token_symbol: str) -> Optional[str]:
        """Get logo URL for a token using multiple fallback strategies.

        Tries in order:
        1. Database cache (ticker, policy_id, case-insensitive)
        2. Logostream API (dedicated logo service)
        3. NMKR fallback chain (Token Registry -> Blockfrost -> LogoKit)
        """
        policy_id_for_symbol = None
        asset_id_for_symbol = None

        try:
            import aiosqlite
            from config import DATABASE_PATH

            async with aiosqlite.connect(DATABASE_PATH) as db:
                # Strategy 1: Exact ticker match for cached logo
                async with db.execute("SELECT logo_url FROM token_metadata WHERE ticker = ? AND logo_url IS NOT NULL", (token_symbol,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        return row[0]

                # Strategy 2: Look up by policy_id from DEFI_PROTOCOLS
                for pid, info in DEFI_PROTOCOLS.items():
                    if info.get('token') == token_symbol:
                        policy_id_for_symbol = pid
                        # First check for logo_url
                        async with db.execute("SELECT logo_url FROM token_metadata WHERE policy_id = ? AND logo_url IS NOT NULL LIMIT 1", (pid,)) as cursor:
                            row = await cursor.fetchone()
                            if row and row[0]:
                                return row[0]
                        # Even without logo, grab the asset_id for NMKR fallback
                        async with db.execute("SELECT asset_id FROM token_metadata WHERE policy_id = ? LIMIT 1", (pid,)) as cursor:
                            row = await cursor.fetchone()
                            if row and row[0]:
                                asset_id_for_symbol = row[0]
                        break

                # Strategy 3: Case-insensitive ticker match
                async with db.execute("SELECT logo_url FROM token_metadata WHERE LOWER(ticker) = LOWER(?) AND logo_url IS NOT NULL LIMIT 1", (token_symbol,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        return row[0]
        except Exception as e:
            logger.error(f"Error in DB logo lookup for {token_symbol}: {e}")

        # Strategy 4: Try Logostream API (dedicated logo service)
        try:
            from services.logostream import logostream_service
            if await logostream_service.is_configured():
                logo_url = await logostream_service.get_token_logo(token_symbol, chain='cardano')
                if logo_url:
                    logger.info(f"[DeFi Logo] Got logo for {token_symbol} via Logostream")
                    return logo_url
        except Exception as e:
            logger.debug(f"Logostream lookup failed for {token_symbol}: {e}")

        # Strategy 5: Use NMKR fallback chain (Token Registry -> Blockfrost -> LogoKit)
        if policy_id_for_symbol:
            try:
                from services.nmkr_service import nmkr_service

                # Derive hex name from actual asset_id in DB, or encode ticker
                if asset_id_for_symbol and len(asset_id_for_symbol) > len(policy_id_for_symbol):
                    token_name_hex = asset_id_for_symbol[len(policy_id_for_symbol):]
                else:
                    token_name_hex = token_symbol.encode('utf-8').hex()

                logger.info(f"[DeFi Logo] NMKR fallback for {token_symbol}: policy={policy_id_for_symbol[:16]}..., hex={token_name_hex}")
                logo_url = await nmkr_service.get_token_logo_with_fallbacks(
                    policy_id_for_symbol,
                    token_name_hex,
                    ticker=token_symbol
                )
                if logo_url:
                    logger.info(f"[DeFi Logo] Got logo for {token_symbol} via NMKR fallback")
                    return logo_url
            except Exception as e:
                logger.error(f"NMKR fallback failed for {token_symbol}: {e}")

        return None

    async def get_all_staking_positions(self, address: str, previous_result: Dict = None) -> Dict:
        """
        Get all protocol staking positions for an address.
        Aggregates data from supported protocol APIs including pending rewards.
        Uses parallel fetching with per-protocol timeouts to avoid 504s.
        If previous_result is provided, timed-out protocols are filled from it.
        """
        import asyncio

        staking = {
            'address': address,
            'protocols': {},
            'total_positions': 0,
            'total_pending_rewards': {}
        }

        # Track which protocols timed out vs returned no data
        timed_out = set()

        # Per-protocol timeout wrapper (15s per protocol, 45s overall)
        async def with_timeout(coro, name, timeout=15):
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"[Staking] {name} timed out after {timeout}s for {address[:20]}...")
                timed_out.add(name)
                return None

        # Phase 1: Fetch all protocol staking positions in parallel (15s each)
        indigo, strike, liqwid, iagon, surf = await asyncio.gather(
            with_timeout(self.get_indigo_staking(address), "Indigo"),
            with_timeout(self.get_strike_staking(address), "Strike", timeout=20),
            with_timeout(self.get_liqwid_staking(address), "Liqwid", timeout=25),
            with_timeout(self.get_iagon_staking(address), "Iagon", timeout=60),
            with_timeout(self.get_surf_lending_positions(address), "Surf"),
            return_exceptions=True
        )

        # Treat exceptions as None
        if isinstance(indigo, Exception):
            logger.error(f"Indigo staking error for {address[:20]}: {indigo}")
            indigo = None
        if isinstance(strike, Exception):
            logger.error(f"Strike staking error for {address[:20]}: {strike}")
            strike = None
        if isinstance(liqwid, Exception):
            logger.error(f"Liqwid staking error for {address[:20]}: {liqwid}")
            liqwid = None
        if isinstance(iagon, Exception):
            logger.error(f"Iagon staking error for {address[:20]}: {iagon}")
            timed_out.add('Iagon')
            iagon = None
        if isinstance(surf, Exception):
            logger.error(f"Surf staking error for {address[:20]}: {surf}")
            surf = None

        # Fill timed-out protocols from previous cache result
        if previous_result and previous_result.get('protocols'):
            prev = previous_result['protocols']
            protocol_map = {'Indigo': indigo, 'Strike': strike, 'Liqwid': liqwid, 'Iagon': iagon, 'Surf Lending': surf}
            for name, val in protocol_map.items():
                if val is None and name in prev:
                    logger.info(f"[Staking] {name} timed out — using previous cached data (stale)")
                    prev[name]['stale'] = True
                    staking['protocols'][name] = prev[name]
                    staking['total_positions'] += prev[name].get('total_positions', 0)

        # Phase 2: Fetch rewards and logos in parallel for protocols that returned data
        reward_tasks = {}
        logo_tasks = {}
        if indigo:
            reward_tasks['indigo'] = self.get_indigo_pending_rewards(address)
            logo_tasks['INDY'] = self._get_token_logo_url('INDY')
        if strike:
            reward_tasks['strike'] = self.get_strike_pending_rewards(address, staking_data=strike)
            logo_tasks['STRIKE'] = self._get_token_logo_url('STRIKE')
        if liqwid:
            reward_tasks['liqwid'] = self.get_liqwid_pending_rewards(address, staking_data=liqwid)
            logo_tasks['LQ'] = self._get_token_logo_url('LQ')
        if iagon:
            logo_tasks['IAG'] = self._get_token_logo_url('IAG')
        if surf:
            logo_tasks['ADA'] = self._get_token_logo_url('ADA')

        # Execute all rewards and logos in one parallel batch (10s timeout)
        all_keys = list(reward_tasks.keys()) + list(logo_tasks.keys())
        all_coros = [with_timeout(c, k, timeout=10) for k, c in zip(all_keys, list(reward_tasks.values()) + list(logo_tasks.values()))]
        all_results = await asyncio.gather(*all_coros, return_exceptions=True) if all_coros else []

        # Unpack results
        rewards = {}
        logos = {}
        for i, key in enumerate(all_keys):
            val = all_results[i]
            if isinstance(val, Exception):
                logger.error(f"Error fetching {key}: {val}")
                val = None
            if key in reward_tasks:
                rewards[key] = val
            else:
                logos[key] = val

        # Assemble Indigo
        if indigo:
            indigo_rewards = rewards.get('indigo')
            staking['protocols']['Indigo'] = {
                'staked': [{
                    'token': 'INDY',
                    'amount': indigo['total_staked_indy'],
                    'amount_formatted': f"{indigo['total_staked_indy']:,.6f}",
                    'positions': indigo['position_count'],
                    'logo_url': logos.get('INDY')
                }],
                'pending_indy': indigo_rewards.get('pending_indy', 0) if indigo_rewards else 0,
                'pending_ada': indigo_rewards.get('pending_ada', 0) if indigo_rewards else 0,
                'reward_tokens': ['INDY', 'ADA'],
                'rewards_url': 'https://app.indigoprotocol.io/earn',
                'total_positions': indigo['position_count']
            }
            staking['total_positions'] += indigo['position_count']
            if indigo_rewards:
                if indigo_rewards.get('pending_indy', 0) > 0:
                    staking['total_pending_rewards']['INDY'] = staking['total_pending_rewards'].get('INDY', 0) + indigo_rewards['pending_indy']
                if indigo_rewards.get('pending_ada', 0) > 0:
                    staking['total_pending_rewards']['ADA'] = staking['total_pending_rewards'].get('ADA', 0) + indigo_rewards['pending_ada']

        # Assemble Strike
        if strike:
            strike_rewards = rewards.get('strike')
            staking['protocols']['Strike'] = {
                'staked': [{
                    'token': 'STRIKE',
                    'amount': strike['total_staked_strike'],
                    'amount_formatted': f"{strike['total_staked_strike']:,.6f}",
                    'positions': strike['position_count'],
                    'logo_url': logos.get('STRIKE')
                }],
                'pending_rewards': strike_rewards.get('pending_rewards', 0) if strike_rewards else 0,
                'accumulated_rewards': strike_rewards.get('accumulated_rewards', 0) if strike_rewards else 0,
                'reward_token': 'STRIKE',
                'rewards_url': 'https://app.strikefinance.org/perpetuals/ada',
                'total_positions': strike['position_count']
            }
            staking['total_positions'] += strike['position_count']
            if strike_rewards and strike_rewards.get('pending_rewards', 0) > 0:
                staking['total_pending_rewards']['STRIKE'] = staking['total_pending_rewards'].get('STRIKE', 0) + strike_rewards['pending_rewards']

        # Assemble Liqwid
        if liqwid:
            liqwid_rewards = rewards.get('liqwid')
            staking['protocols']['Liqwid'] = {
                'staked': [{
                    'token': 'LQ',
                    'amount': liqwid['total_staked_lq'],
                    'amount_formatted': f"{liqwid['total_staked_lq']:,.6f}",
                    'positions': liqwid['position_count'],
                    'logo_url': logos.get('LQ')
                }],
                'pending_rewards': liqwid_rewards.get('pending_rewards', 0) if liqwid_rewards else 0,
                'reward_token': 'LQ',
                'claimed_rewards': liqwid_rewards.get('claimed_rewards', 0) if liqwid_rewards else 0,
                'total_earned': liqwid_rewards.get('total_earned', 0) if liqwid_rewards else 0,
                'rewards_url': 'https://liqwid-rewards.sundaeswap.finance/',
                'total_positions': liqwid['position_count']
            }
            staking['total_positions'] += liqwid['position_count']
            if liqwid_rewards and liqwid_rewards.get('pending_rewards', 0) > 0:
                staking['total_pending_rewards']['LQ'] = staking['total_pending_rewards'].get('LQ', 0) + liqwid_rewards['pending_rewards']

        # Assemble Iagon
        if iagon:
            staking['protocols']['Iagon'] = {
                'staked': [{
                    'token': 'IAG',
                    'amount': iagon['total_staked_iag'],
                    'amount_formatted': f"{iagon['total_staked_iag']:,.6f}",
                    'positions': iagon['position_count'],
                    'logo_url': logos.get('IAG')
                }],
                'total_deposited': iagon['total_deposited'],
                'total_withdrawn': iagon['total_withdrawn'],
                'reward_token': 'IAG',
                'rewards_url': 'https://iagon.com/staking',
                'total_positions': iagon['position_count'],
                'category': 'depin',
                'note': 'Old staking contract - position calculated from transaction history'
            }
            staking['total_positions'] += iagon['position_count']

        # Always include Iagon in response so the DePIN card is always visible
        if 'Iagon' not in staking['protocols']:
            if 'Iagon' in timed_out:
                staking['protocols']['Iagon'] = {
                    'staked': [],
                    'category': 'depin',
                    'status': 'timeout',
                    'reward_token': 'IAG',
                    'rewards_url': 'https://iagon.com/staking',
                    'blockchain': 'cardano',
                    'total_positions': 0,
                }
            else:
                # Scan completed but found no staked IAG — still show the card
                staking['protocols']['Iagon'] = {
                    'staked': [],
                    'category': 'depin',
                    'status': 'no_staking',
                    'reward_token': 'IAG',
                    'rewards_url': 'https://iagon.com/staking',
                    'blockchain': 'cardano',
                    'total_positions': 0,
                }

        # Assemble Surf Lending
        if surf:
            staking['protocols']['Surf Lending'] = {
                'staked': [{
                    'token': 'ADA',
                    'amount': surf.get('total_supplied_ada', 0),
                    'amount_formatted': f"{surf.get('total_supplied_ada', 0):,.6f}",
                    'positions': surf.get('position_count', 0),
                    'logo_url': logos.get('ADA')
                }],
                'pending_rewards': surf.get('pending_rewards', 0),
                'reward_token': 'SURF',
                'apy': surf.get('apy'),
                'total_positions': surf.get('position_count', 0)
            }
            staking['total_positions'] += surf.get('position_count', 0)

        return staking


# ===== Chainlink Staking (Ethereum) =====

# Chainlink Staking v0.2 contracts on Ethereum mainnet
CHAINLINK_COMMUNITY_STAKING = "0xBc10f2E862ED4502144c7d632a3459F49DFCDB5e"
CHAINLINK_NODE_OP_STAKING = "0xa1D76a7cA72128541E9FCAcafbDa3a92ef94FCD5"

# Minimal ABI for reading staked balance - getStake(address) returns (uint256)
CHAINLINK_STAKING_GET_STAKE_SIG = "0x7a766460"  # getStake(address)
CHAINLINK_STAKING_GET_REWARD_SIG = "0xc00007b0"  # getReward(address)


async def get_chainlink_staking(eth_address: str) -> Optional[Dict]:
    """
    Get Chainlink staking positions for an Ethereum address.
    Reads Chainlink Staking v0.2 community pool contract via Alchemy/public RPC.

    Returns staked LINK amount and pending rewards.
    """
    from config import ALCHEMY_API_KEY, ALCHEMY_ETH_URL

    if not ALCHEMY_API_KEY:
        return None

    try:
        client = get_client("alchemy_eth", timeout=30.0)
        rpc_url = f"{ALCHEMY_ETH_URL}/v2/{ALCHEMY_API_KEY}"

        # Pad address to 32 bytes for eth_call data parameter
        addr_padded = eth_address.lower().replace('0x', '').zfill(64)

        # Try community staking pool first, then node operator pool
        total_staked = 0
        total_rewards = 0
        pool_found = None

        for pool_name, pool_address in [
            ("Community", CHAINLINK_COMMUNITY_STAKING),
            ("Node Operator", CHAINLINK_NODE_OP_STAKING)
        ]:
            # Read staked amount: getStake(address)
            stake_data = CHAINLINK_STAKING_GET_STAKE_SIG + addr_padded
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": pool_address, "data": stake_data}, "latest"]
            }
            resp = await client.post(rpc_url, json=payload)
            if resp.status_code == 200:
                result = resp.json().get("result", "0x0")
                staked_raw = int(result, 16) if result != "0x" else 0
                staked_link = staked_raw / 10**18
                if staked_link > 0:
                    total_staked += staked_link
                    pool_found = pool_name

                    # Read pending rewards: getReward(address)
                    reward_data = CHAINLINK_STAKING_GET_REWARD_SIG + addr_padded
                    payload_r = {
                        "jsonrpc": "2.0", "id": 2, "method": "eth_call",
                        "params": [{"to": pool_address, "data": reward_data}, "latest"]
                    }
                    resp_r = await client.post(rpc_url, json=payload_r)
                    if resp_r.status_code == 200:
                        result_r = resp_r.json().get("result", "0x0")
                        reward_raw = int(result_r, 16) if result_r != "0x" else 0
                        total_rewards += reward_raw / 10**18

        if total_staked > 0:
            return {
                'protocol': 'Chainlink Staking',
                'pool': pool_found,
                'staked_link': total_staked,
                'pending_rewards_link': total_rewards,
                'token': 'LINK',
                'source': 'alchemy'
            }

        return None

    except Exception as e:
        logging.getLogger(__name__).error(f"Chainlink staking error for {eth_address[:20]}: {e}")
        return None


# Singleton instance
defi_service = DeFiService()
