"""
Helium Hotspot Reward Tracking

Queries Helium reward oracles directly for pending HNT/MOBILE rewards.
No API key required — oracles are public HTTP endpoints.
"""

import asyncio
import logging
from typing import Dict, Optional

from services.http_client import get_client

logger = logging.getLogger(__name__)

ORACLE_URLS = {
    'HNT': 'https://hnt-rewards.oracle.helium.io',
    'MOBILE': 'https://mobile-rewards.oracle.helium.io',
}

TOKEN_DECIMALS = {
    'HNT': 8,
    'MOBILE': 6,
}


async def _query_oracle(token: str, wallet_address: str) -> Optional[Dict]:
    """Query a single Helium reward oracle for pending rewards."""
    base_url = ORACLE_URLS.get(token)
    if not base_url:
        return None

    client = get_client("helium_oracle", timeout=15.0)
    try:
        resp = await client.get(
            f"{base_url}/rewards",
            params={"owner": wallet_address}
        )
        if resp.status_code == 200:
            data = resp.json()
            decimals = TOKEN_DECIMALS[token]
            lifetime_raw = int(data.get('lifetime', '0'))
            pending_raw = int(data.get('pending', '0'))
            return {
                'lifetime': lifetime_raw / (10 ** decimals),
                'pending': pending_raw / (10 ** decimals),
            }
        elif resp.status_code == 404:
            logger.debug(f"Helium {token} oracle: no rewards for {wallet_address[:20]}...")
            return None
        else:
            logger.warning(f"Helium {token} oracle returned {resp.status_code} for {wallet_address[:20]}...")
            return None
    except Exception as e:
        logger.error(f"Helium {token} oracle error for {wallet_address[:20]}...: {e}")
        return None


async def get_pending_rewards(wallet_address: str) -> Dict[str, Dict]:
    """
    Query HNT and MOBILE oracles in parallel for pending rewards.

    Returns: { 'HNT': {'lifetime': float, 'pending': float}, 'MOBILE': {...} }
    Only includes tokens with data.
    """
    results = await asyncio.gather(
        _query_oracle('HNT', wallet_address),
        _query_oracle('MOBILE', wallet_address),
        return_exceptions=True
    )

    rewards = {}
    for token, result in zip(['HNT', 'MOBILE'], results):
        if isinstance(result, Exception):
            logger.error(f"Helium {token} oracle exception: {result}")
            continue
        if result:
            rewards[token] = result

    return rewards


async def get_helium_staking(wallet_address: str) -> Optional[Dict]:
    """
    Get Helium staking position for a Solana wallet.

    Returns protocol-compatible dict for DeFi staking rendering,
    or None if no Helium rewards found.
    """
    rewards = await get_pending_rewards(wallet_address)

    if not rewards:
        return None

    # Build staked positions list from rewards data
    staked = []
    total_pending_hnt = 0

    # HNT rewards (primary after HIP-138)
    hnt_data = rewards.get('HNT')
    if hnt_data and (hnt_data['pending'] > 0 or hnt_data['lifetime'] > 0):
        total_pending_hnt = hnt_data['pending']
        staked.append({
            'token': 'HNT',
            'amount': hnt_data['lifetime'],
            'positions': 0,  # We don't know hotspot count from oracle
            'logo_url': 'https://img.logokit.com/crypto/HNT?token=LOGOKIT_KEY_REMOVED&size=32',
        })

    # MOBILE rewards (legacy, may still have balances)
    mobile_data = rewards.get('MOBILE')
    if mobile_data and (mobile_data['pending'] > 0 or mobile_data['lifetime'] > 0):
        staked.append({
            'token': 'MOBILE',
            'amount': mobile_data['lifetime'],
            'positions': 0,
            'logo_url': 'https://img.logokit.com/crypto/MOBILE?token=LOGOKIT_KEY_REMOVED&size=32',
        })

    if not staked:
        return None

    return {
        'protocols': {
            'Helium': {
                'staked': staked,
                'pending_rewards': total_pending_hnt,
                'reward_token': 'HNT',
                'rewards_url': 'https://app.helium.com',
                'blockchain': 'solana',
                'total_positions': len(staked),
            }
        }
    }
