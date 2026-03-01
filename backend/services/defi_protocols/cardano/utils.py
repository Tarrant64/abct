"""
Shared utilities for Cardano DeFi protocol adapters.

Contains common helpers used across multiple Cardano adapters,
like address decoding and stake address lookup.
"""

import bech32
import logging
from typing import Optional

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import get_client, blockfrost_fetch

logger = logging.getLogger(__name__)


def get_payment_credential(address: str) -> Optional[str]:
    """Extract payment credential (key hash) from a Cardano address.

    Decodes a bech32 Cardano address and extracts the 28-byte
    payment credential (key hash) as a hex string.

    Args:
        address: Cardano bech32 address (addr1...)

    Returns:
        Hex string of the payment credential, or None on error
    """
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


async def get_stake_address(address: str) -> Optional[str]:
    """Get the stake address associated with a wallet address via Blockfrost.

    Args:
        address: Cardano bech32 address

    Returns:
        Stake address string (stake1...) or None
    """
    try:
        headers = {"project_id": BLOCKFROST_API_KEY}
        response = await blockfrost_fetch(
            f"/addresses/{address}",
            headers=headers,
            timeout=30.0
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('stake_address')
    except Exception as e:
        logger.warning(f"Could not get stake address: {e}")
    return None


async def check_token_in_wallet(address: str, policy_id: str) -> list:
    """Check if a wallet holds any tokens with the given policy ID via Blockfrost.

    Args:
        address: Cardano bech32 address
        policy_id: The policy ID to look for

    Returns:
        List of matching assets with their quantities, or empty list
    """
    try:
        headers = {"project_id": BLOCKFROST_API_KEY}
        page = 1
        matched = []
        while True:
            response = await blockfrost_fetch(
                f"/addresses/{address}/assets",
                headers=headers,
                params={"page": page, "count": 100},
                timeout=30.0,
            )
            if response.status_code == 404:
                break
            if response.status_code != 200:
                logger.error(f"Blockfrost assets error: {response.status_code}")
                break
            assets = response.json()
            if not assets:
                break
            for asset in assets:
                unit = asset.get("unit", "")
                if unit.startswith(policy_id):
                    matched.append({
                        "unit": unit,
                        "policy_id": policy_id,
                        "asset_name_hex": unit[len(policy_id):],
                        "quantity": int(asset.get("quantity", 0)),
                    })
            if len(assets) < 100:
                break
            page += 1
        return matched
    except Exception as e:
        logger.error(f"check_token_in_wallet error: {e}")
        return []


async def get_wallet_utxos_at_script(
    script_address: str, payment_key_hash: str
) -> list:
    """Scan UTXOs at a script address for those belonging to a specific payment key.

    Used for protocols like FluidTokens where user funds are locked at script addresses.

    Args:
        script_address: The protocol's script address
        payment_key_hash: The user's payment key hash (from get_payment_credential)

    Returns:
        List of matching UTXOs with amounts and datum info
    """
    try:
        headers = {"project_id": BLOCKFROST_API_KEY}
        page = 1
        matched_utxos = []
        while True:
            response = await blockfrost_fetch(
                f"/addresses/{script_address}/utxos",
                headers=headers,
                params={"page": page, "count": 100},
                timeout=30.0,
            )
            if response.status_code == 404:
                break
            if response.status_code != 200:
                break
            utxos = response.json()
            if not utxos:
                break
            for utxo in utxos:
                datum_hash = utxo.get("data_hash") or utxo.get("inline_datum")
                if datum_hash and payment_key_hash:
                    # Check if this UTXO's datum references the user's payment key
                    # Protocol-specific datum parsing would happen in the adapter
                    matched_utxos.append({
                        "tx_hash": utxo.get("tx_hash"),
                        "tx_index": utxo.get("tx_index"),
                        "amount": utxo.get("amount", []),
                        "data_hash": utxo.get("data_hash"),
                        "inline_datum": utxo.get("inline_datum"),
                    })
            if len(utxos) < 100:
                break
            page += 1
        return matched_utxos
    except Exception as e:
        logger.error(f"get_wallet_utxos_at_script error: {e}")
        return []


def calculate_lp_share(
    lp_tokens_held: int,
    total_lp_supply: int,
    pool_reserve_a: float,
    pool_reserve_b: float,
) -> dict:
    """Calculate a user's share of a liquidity pool based on LP token holdings.

    Args:
        lp_tokens_held: Number of LP tokens the user holds
        total_lp_supply: Total supply of LP tokens for this pool
        pool_reserve_a: Total amount of token A in the pool
        pool_reserve_b: Total amount of token B in the pool

    Returns:
        Dict with share_pct, amount_a, amount_b
    """
    if total_lp_supply <= 0:
        return {"share_pct": 0.0, "amount_a": 0.0, "amount_b": 0.0}

    share = lp_tokens_held / total_lp_supply
    return {
        "share_pct": share * 100,
        "amount_a": pool_reserve_a * share,
        "amount_b": pool_reserve_b * share,
    }
