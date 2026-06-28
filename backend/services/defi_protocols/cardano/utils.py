"""
Shared utilities for Cardano DeFi protocol adapters.

Contains common helpers used across multiple Cardano adapters,
like address decoding, stake address lookup, and LP position valuation.
"""

import bech32
import logging
from typing import Optional, Dict, List, Tuple

from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL
from services.http_client import blockfrost_fetch

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


# ─── LP Valuation ────────────────────────────────────────────────────────────
# For LP valuation we use Blockfrost to get the
# LP token's on-chain metadata (total supply) and the pool's reserve data, then
# fall back to pricing services for token pricing.

# Map of DEX LP policy IDs for quick lookup
DEX_LP_POLICIES: Dict[str, str] = {
    "0be55d262b29f564998ff81efe21bdc0022621c12f15af08d0f2ddb1": "Minswap",
    "f5808c2c990d86da54bfc97d89cee6efa20cd8461616359478d96b4c": "Minswap V2",
    "e4214b7cce62ac6fbba385d164df48e157eae5863521b4b67ca71d86": "Minswap Farm",
    "0029cb7c88c7567b63d1a512c0ed626aa169688ec980730c0473b913": "SundaeSwap",
    "026a18d04a0c642759bb3d83b12e3344894e5c1c7b2aeb1a2113a570": "WingRiders",
    "7aca4c98b65906a5d8e3dfa174dcaa72d190e0eae5ee279df6b87c5a": "Splash",
    "af3d70acf4bd5b3abb319a7d75c89fb3e56eafcdd46b2e9b57a2999f": "MuesliSwap",
}


async def get_lp_token_info(unit: str) -> Optional[Dict]:
    """Fetch on-chain asset info for an LP token from Blockfrost.

    Returns total supply, policy ID, asset name, and on-chain metadata.

    Args:
        unit: Full Cardano asset unit (policy_id + hex asset name)

    Returns:
        Dict with total_supply, policy_id, asset_name_hex, metadata, or None
    """
    try:
        headers = {"project_id": BLOCKFROST_API_KEY}
        response = await blockfrost_fetch(
            f"/assets/{unit}",
            headers=headers,
            timeout=30.0,
        )
        if response.status_code != 200:
            logger.warning(f"Blockfrost asset info error for {unit[:30]}...: {response.status_code}")
            return None

        data = response.json()
        return {
            "unit": unit,
            "policy_id": data.get("policy_id", ""),
            "asset_name_hex": data.get("asset_name", ""),
            "total_supply": int(data.get("quantity", "0")),
            "metadata": data.get("onchain_metadata"),
            "fingerprint": data.get("fingerprint", ""),
        }
    except Exception as e:
        logger.error(f"get_lp_token_info error for {unit[:30]}...: {e}")
        return None


async def get_token_price_ada(unit: str) -> float:
    """Get token price in ADA via USD pricing service.

    Fetches token price in USD from the pricing service (Charli3 -> DefiLlama),
    then divides by the current ADA/USD price to get the price in ADA.

    Args:
        unit: Cardano asset unit (policy_id + hex asset name), or 'lovelace' for ADA

    Returns:
        Price in ADA (float), or 0.0 on failure
    """
    if unit == "lovelace":
        return 1.0  # 1 ADA = 1 ADA

    try:
        # Build a reverse lookup: unit -> symbol from CARDANO_TOKEN_POLICIES
        from services.pricing import CARDANO_TOKEN_POLICIES
        symbol_map = {}
        for sym, (policy_id, asset_name) in CARDANO_TOKEN_POLICIES.items():
            symbol_map[f"{policy_id}{asset_name}"] = sym

        symbol = symbol_map.get(unit)
        if not symbol:
            # Unit not in our known token policies; can't price it
            return 0.0

        # Get USD price from pricing service
        from services.pricing import pricing_service
        token_usd = await pricing_service.get_price(symbol)
        if token_usd <= 0:
            return 0.0

        # Get ADA/USD price
        ada_usd = await get_ada_usd_price()
        if ada_usd <= 0:
            return 0.0

        return token_usd / ada_usd
    except Exception as e:
        logger.debug(f"get_token_price_ada error for {unit[:30]}...: {e}")
        return 0.0


async def get_ada_usd_price() -> float:
    """Get current ADA/USD price from the pricing service.

    Uses CoinGecko -> CMC -> Coinbase -> CoinPaprika -> DefiLlama chain
    via the pricing service to fetch ADA/USD.

    Returns:
        ADA price in USD, or 0.0 on failure
    """
    try:
        from services.pricing import pricing_service
        return await pricing_service.get_price('ADA')
    except Exception as e:
        logger.debug(f"get_ada_usd_price error: {e}")
        return 0.0


def _parse_pool_pair_from_hex(asset_name_hex: str) -> Tuple[str, str]:
    """Parse pool pair tokens from LP token asset name hex.

    Many Cardano DEXes encode pool information in the LP token name.
    This is a best-effort parser that returns readable pair names.

    Args:
        asset_name_hex: Hex-encoded asset name of the LP token

    Returns:
        Tuple of (token_a_label, token_b_label)
    """
    try:
        decoded = bytes.fromhex(asset_name_hex).decode("utf-8", errors="replace")
        # Common patterns: "ADA-MIN", "ADA/MIN", etc.
        for sep in ["-", "/", "_"]:
            if sep in decoded:
                parts = decoded.split(sep, 1)
                return (parts[0].strip(), parts[1].strip())
        return (decoded, "")
    except Exception:
        return ("Unknown", "Unknown")


async def resolve_lp_value(
    lp_unit: str,
    lp_quantity: int,
    dex_name: str,
) -> Optional[Dict]:
    """Resolve the USD value of LP tokens using Blockfrost pool data + pricing service.

    Strategy:
    1. Get LP token total supply from Blockfrost
    2. Find the pool UTXOs that hold the reserves for this LP token
    3. Calculate user's share of the pool reserves
    4. Price each reserve token via the pricing service (Charli3 -> DefiLlama for ADA-paired tokens)
    5. Sum to get total USD value

    This is the primary valuation method used by all 5 DEX adapters.

    Args:
        lp_unit: Full asset unit of the LP token (policy_id + hex_name)
        lp_quantity: Raw quantity of LP tokens held by user
        dex_name: Name of the DEX (for logging)

    Returns:
        Dict with valuation details, or None if valuation fails:
        {
            "value_usd": float,
            "value_ada": float,
            "pair_name": str,         # e.g. "ADA/MIN"
            "token_a": {"symbol": str, "amount": float, "value_usd": float},
            "token_b": {"symbol": str, "amount": float, "value_usd": float},
            "pool_share_pct": float,
            "total_lp_supply": int,
        }
    """
    try:
        # Step 1: Get LP token info (total supply)
        lp_info = await get_lp_token_info(lp_unit)
        if not lp_info or lp_info["total_supply"] <= 0:
            logger.debug(f"[{dex_name}] Could not get LP token supply for {lp_unit[:30]}...")
            return None

        total_supply = lp_info["total_supply"]
        policy_id = lp_unit[:56]
        asset_name_hex = lp_unit[56:]

        # Step 2: Find pool address holding this LP token's reserves
        # The pool address is typically a script address that holds the pool NFT
        # with the same policy as the LP token. Query Blockfrost for addresses
        # holding this specific asset.
        headers = {"project_id": BLOCKFROST_API_KEY}
        response = await blockfrost_fetch(
            f"/assets/{lp_unit}/addresses",
            headers=headers,
            params={"count": 5, "order": "desc"},
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.debug(f"[{dex_name}] Could not find pool addresses for LP {lp_unit[:30]}...")
            return None

        asset_addresses = response.json()
        if not asset_addresses:
            return None

        # The pool address is the one with the largest quantity of LP tokens
        # (the pool itself holds the "locked" LP tokens as pool liquidity marker)
        pool_address = None
        max_qty = 0
        for addr_info in asset_addresses:
            qty = int(addr_info.get("quantity", "0"))
            if qty > max_qty:
                max_qty = qty
                pool_address = addr_info.get("address")

        if not pool_address:
            logger.debug(f"[{dex_name}] No pool address found for LP {lp_unit[:30]}...")
            return None

        # Step 3: Get pool UTXOs to find reserve amounts
        response = await blockfrost_fetch(
            f"/addresses/{pool_address}/utxos",
            headers=headers,
            params={"count": 100},
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.debug(f"[{dex_name}] Could not get pool UTXOs for {pool_address[:30]}...")
            return None

        utxos = response.json()

        # Aggregate all assets at the pool address
        pool_lovelace = 0
        pool_assets: Dict[str, int] = {}  # unit -> quantity
        for utxo in utxos:
            for amount_entry in utxo.get("amount", []):
                u = amount_entry["unit"]
                q = int(amount_entry["quantity"])
                if u == "lovelace":
                    pool_lovelace += q
                else:
                    pool_assets[u] = pool_assets.get(u, 0) + q

        # Remove the LP token itself and any NFT identifiers from reserves
        pool_assets.pop(lp_unit, None)
        # Remove assets with quantity 1 (likely NFT pool identifiers)
        pool_assets = {u: q for u, q in pool_assets.items() if q > 1}

        # Step 4: Identify the two reserve tokens
        # For ADA-paired pools: one side is lovelace
        # For token-token pools: two non-ADA tokens
        reserve_a_unit = "lovelace"
        reserve_a_qty = pool_lovelace
        reserve_a_decimals = 6  # ADA has 6 decimals

        reserve_b_unit = None
        reserve_b_qty = 0
        reserve_b_decimals = 0

        if pool_assets:
            # Find the primary non-ADA token (highest quantity likely the reserve)
            # Sort by quantity descending
            sorted_assets = sorted(pool_assets.items(), key=lambda x: x[1], reverse=True)
            reserve_b_unit = sorted_assets[0][0]
            reserve_b_qty = sorted_assets[0][1]

            # Try to get decimals from Blockfrost
            b_info = await get_lp_token_info(reserve_b_unit)
            if b_info and b_info.get("metadata"):
                meta = b_info["metadata"]
                reserve_b_decimals = int(meta.get("decimals", 0))
            else:
                # Common default: 6 decimals for most Cardano tokens
                reserve_b_decimals = 6

        if not reserve_b_unit:
            logger.debug(f"[{dex_name}] Could not identify pool reserves for {lp_unit[:30]}...")
            return None

        # Step 5: Calculate user's share
        share_data = calculate_lp_share(
            lp_tokens_held=lp_quantity,
            total_lp_supply=total_supply,
            pool_reserve_a=reserve_a_qty / (10 ** reserve_a_decimals),
            pool_reserve_b=reserve_b_qty / (10 ** reserve_b_decimals),
        )

        # Step 6: Get token prices (ADA price + token B price in ADA)
        ada_usd = await get_ada_usd_price()

        # Token A is ADA
        token_a_price_usd = ada_usd

        # Token B: get price in ADA then convert to USD
        token_b_price_ada = await get_token_price_ada(reserve_b_unit)
        token_b_price_usd = token_b_price_ada * ada_usd

        # Step 7: Calculate USD values
        amount_a = share_data["amount_a"]
        amount_b = share_data["amount_b"]
        value_a_usd = amount_a * token_a_price_usd
        value_b_usd = amount_b * token_b_price_usd
        total_value_usd = value_a_usd + value_b_usd
        total_value_ada = amount_a + (amount_b * token_b_price_ada)

        # Parse pair name
        token_a_label, token_b_label = _parse_pool_pair_from_hex(asset_name_hex)
        if token_a_label in ("Unknown", "") and reserve_a_unit == "lovelace":
            token_a_label = "ADA"
        if token_b_label in ("Unknown", ""):
            # Try to get ticker from metadata
            if b_info and b_info.get("metadata"):
                token_b_label = b_info["metadata"].get("ticker", b_info["metadata"].get("name", "Token"))
            else:
                token_b_label = reserve_b_unit[56:70] if len(reserve_b_unit) > 56 else "Token"
                try:
                    token_b_label = bytes.fromhex(token_b_label).decode("utf-8", errors="replace")
                except Exception:
                    pass

        pair_name = f"{token_a_label}/{token_b_label}"

        logger.info(
            f"[{dex_name}] LP valued: {pair_name} = ${total_value_usd:.2f} "
            f"(share={share_data['share_pct']:.4f}%, {amount_a:.2f} {token_a_label} + {amount_b:.4f} {token_b_label})"
        )

        return {
            "value_usd": round(total_value_usd, 2),
            "value_ada": round(total_value_ada, 4),
            "pair_name": pair_name,
            "token_a": {
                "symbol": token_a_label,
                "amount": round(amount_a, 6),
                "value_usd": round(value_a_usd, 2),
                "unit": reserve_a_unit,
            },
            "token_b": {
                "symbol": token_b_label,
                "amount": round(amount_b, 6),
                "value_usd": round(value_b_usd, 2),
                "unit": reserve_b_unit,
            },
            "pool_share_pct": round(share_data["share_pct"], 6),
            "total_lp_supply": total_supply,
        }

    except Exception as e:
        logger.error(f"[{dex_name}] LP valuation error for {lp_unit[:30]}...: {e}")
        return None
