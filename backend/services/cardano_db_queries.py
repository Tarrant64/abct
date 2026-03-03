"""
SQL query registry for DB Sync access.

All DB Sync SQL is centralized here. When DB Sync schema changes,
only this file needs updating. Service code calls named functions.

Schema version tested against: db-sync 13.7.0.1
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DBSYNC_SCHEMA_VERSION = "13.7.0.1"


# ---------------------------------------------------------------------------
# Tier 1: Highest-impact queries (transaction UTXOs, address txs, balances)
# ---------------------------------------------------------------------------

async def get_tx_details(tx_hash_hex: str) -> Optional[dict]:
    """Get transaction metadata (replaces /txs/{hash})."""
    from services.cardano_db import query_one
    tx_hash = bytes.fromhex(tx_hash_hex)
    row = await query_one("""
        SELECT
            encode(tx.hash, 'hex') AS tx_hash,
            b.block_no AS block_height,
            EXTRACT(EPOCH FROM b.time)::bigint AS block_time,
            tx.fee::text AS fees
        FROM tx
        JOIN block b ON b.id = tx.block_id
        WHERE tx.hash = $1
    """, tx_hash)
    return dict(row) if row else None


async def get_tx_utxos(tx_hash_hex: str) -> dict:
    """Get inputs and outputs for a transaction (replaces /txs/{hash}/utxos)."""
    from services.cardano_db import query
    tx_hash = bytes.fromhex(tx_hash_hex)

    inputs = await query("""
        SELECT
            encode(src_tx.hash, 'hex') AS tx_hash,
            txo.index::int AS output_index,
            txo.address,
            txo.value::text AS lovelace
        FROM tx_in txi
        JOIN tx_out txo ON txo.tx_id = txi.tx_out_id
                       AND txo.index = txi.tx_out_index
        JOIN tx src_tx ON src_tx.id = txi.tx_out_id
        JOIN tx consuming ON consuming.id = txi.tx_in_id
        WHERE consuming.hash = $1
    """, tx_hash)

    outputs = await query("""
        SELECT
            txo.index::int AS output_index,
            txo.address,
            txo.value::text AS lovelace,
            encode(txo.data_hash, 'hex') AS data_hash
        FROM tx_out txo
        JOIN tx ON tx.id = txo.tx_id
        WHERE tx.hash = $1
        ORDER BY txo.index
    """, tx_hash)

    # Multi-asset amounts for inputs
    input_assets = await query("""
        SELECT
            encode(src_tx.hash, 'hex') AS tx_hash,
            txo.index::int AS output_index,
            encode(ma.policy, 'hex') AS policy_id,
            encode(ma.name, 'hex') AS asset_name_hex,
            mto.quantity::text AS quantity
        FROM tx_in txi
        JOIN tx_out txo ON txo.tx_id = txi.tx_out_id
                       AND txo.index = txi.tx_out_index
        JOIN tx src_tx ON src_tx.id = txi.tx_out_id
        JOIN tx consuming ON consuming.id = txi.tx_in_id
        JOIN ma_tx_out mto ON mto.tx_out_id = txo.id
        JOIN multi_asset ma ON ma.id = mto.ident
        WHERE consuming.hash = $1
    """, tx_hash)

    # Multi-asset amounts for outputs
    output_assets = await query("""
        SELECT
            txo.index::int AS output_index,
            encode(ma.policy, 'hex') AS policy_id,
            encode(ma.name, 'hex') AS asset_name_hex,
            mto.quantity::text AS quantity
        FROM tx_out txo
        JOIN tx ON tx.id = txo.tx_id
        JOIN ma_tx_out mto ON mto.tx_out_id = txo.id
        JOIN multi_asset ma ON ma.id = mto.ident
        WHERE tx.hash = $1
    """, tx_hash)

    # Build Blockfrost-compatible response format
    def _build_amount(lovelace, assets_list):
        amounts = [{"unit": "lovelace", "quantity": lovelace}]
        for a in assets_list:
            amounts.append({
                "unit": a["policy_id"] + a["asset_name_hex"],
                "quantity": a["quantity"],
            })
        return amounts

    # Group input assets by (tx_hash, output_index)
    inp_asset_map = {}
    for a in input_assets:
        key = (a["tx_hash"], a["output_index"])
        inp_asset_map.setdefault(key, []).append(a)

    # Group output assets by output_index
    out_asset_map = {}
    for a in output_assets:
        out_asset_map.setdefault(a["output_index"], []).append(a)

    formatted_inputs = []
    for inp in inputs:
        key = (inp["tx_hash"], inp["output_index"])
        formatted_inputs.append({
            "address": inp["address"],
            "amount": _build_amount(inp["lovelace"], inp_asset_map.get(key, [])),
            "tx_hash": inp["tx_hash"],
            "output_index": inp["output_index"],
        })

    formatted_outputs = []
    for out in outputs:
        formatted_outputs.append({
            "address": out["address"],
            "amount": _build_amount(out["lovelace"], out_asset_map.get(out["output_index"], [])),
            "output_index": out["output_index"],
            "data_hash": out["data_hash"],
        })

    return {"inputs": formatted_inputs, "outputs": formatted_outputs}


async def batch_tx_utxos(tx_hashes_hex: list) -> dict:
    """Batch fetch UTXOs for multiple transactions at once.

    The killer optimization — replaces N sequential
    blockfrost_fetch("/txs/{hash}/utxos") calls with a few SQL queries.
    """
    if not tx_hashes_hex:
        return {}

    from services.cardano_db import query
    tx_hashes = [bytes.fromhex(h) for h in tx_hashes_hex]

    inputs = await query("""
        SELECT
            encode(consuming.hash, 'hex') AS consuming_tx,
            encode(src_tx.hash, 'hex') AS source_tx,
            txo.index::int AS output_index,
            txo.address,
            txo.value::text AS lovelace
        FROM tx_in txi
        JOIN tx_out txo ON txo.tx_id = txi.tx_out_id
                       AND txo.index = txi.tx_out_index
        JOIN tx src_tx ON src_tx.id = txi.tx_out_id
        JOIN tx consuming ON consuming.id = txi.tx_in_id
        WHERE consuming.hash = ANY($1::bytea[])
    """, tx_hashes)

    outputs = await query("""
        SELECT
            encode(tx.hash, 'hex') AS tx_hash,
            txo.index::int AS output_index,
            txo.address,
            txo.value::text AS lovelace,
            encode(txo.data_hash, 'hex') AS data_hash
        FROM tx_out txo
        JOIN tx ON tx.id = txo.tx_id
        WHERE tx.hash = ANY($1::bytea[])
        ORDER BY tx.hash, txo.index
    """, tx_hashes)

    # Multi-asset for inputs
    input_assets = await query("""
        SELECT
            encode(consuming.hash, 'hex') AS consuming_tx,
            encode(src_tx.hash, 'hex') AS source_tx,
            txo.index::int AS output_index,
            encode(ma.policy, 'hex') AS policy_id,
            encode(ma.name, 'hex') AS asset_name_hex,
            mto.quantity::text AS quantity
        FROM tx_in txi
        JOIN tx_out txo ON txo.tx_id = txi.tx_out_id
                       AND txo.index = txi.tx_out_index
        JOIN tx src_tx ON src_tx.id = txi.tx_out_id
        JOIN tx consuming ON consuming.id = txi.tx_in_id
        JOIN ma_tx_out mto ON mto.tx_out_id = txo.id
        JOIN multi_asset ma ON ma.id = mto.ident
        WHERE consuming.hash = ANY($1::bytea[])
    """, tx_hashes)

    # Multi-asset for outputs
    output_assets = await query("""
        SELECT
            encode(tx.hash, 'hex') AS tx_hash,
            txo.index::int AS output_index,
            encode(ma.policy, 'hex') AS policy_id,
            encode(ma.name, 'hex') AS asset_name_hex,
            mto.quantity::text AS quantity
        FROM tx_out txo
        JOIN tx ON tx.id = txo.tx_id
        JOIN ma_tx_out mto ON mto.tx_out_id = txo.id
        JOIN multi_asset ma ON ma.id = mto.ident
        WHERE tx.hash = ANY($1::bytea[])
    """, tx_hashes)

    # Group assets
    inp_asset_map = {}
    for a in input_assets:
        key = (a["consuming_tx"], a["source_tx"], a["output_index"])
        inp_asset_map.setdefault(key, []).append(a)

    out_asset_map = {}
    for a in output_assets:
        key = (a["tx_hash"], a["output_index"])
        out_asset_map.setdefault(key, []).append(a)

    def _build_amount(lovelace, assets):
        amounts = [{"unit": "lovelace", "quantity": lovelace}]
        for a in assets:
            amounts.append({
                "unit": a["policy_id"] + a["asset_name_hex"],
                "quantity": a["quantity"],
            })
        return amounts

    # Build result keyed by tx hash
    result = {h: {"inputs": [], "outputs": []} for h in tx_hashes_hex}
    for inp in inputs:
        key = (inp["consuming_tx"], inp["source_tx"], inp["output_index"])
        result[inp["consuming_tx"]]["inputs"].append({
            "address": inp["address"],
            "amount": _build_amount(inp["lovelace"], inp_asset_map.get(key, [])),
            "tx_hash": inp["source_tx"],
            "output_index": inp["output_index"],
        })
    for out in outputs:
        key = (out["tx_hash"], out["output_index"])
        result[out["tx_hash"]]["outputs"].append({
            "address": out["address"],
            "amount": _build_amount(out["lovelace"], out_asset_map.get(key, [])),
            "output_index": out["output_index"],
            "data_hash": out["data_hash"],
        })

    return result


async def get_address_transactions(address: str, from_block: int = 0) -> list:
    """Get all transactions involving an address (replaces /addresses/{addr}/transactions)."""
    from services.cardano_db import query
    rows = await query("""
        SELECT DISTINCT
            encode(tx.hash, 'hex') AS tx_hash,
            b.block_no AS block_height,
            EXTRACT(EPOCH FROM b.time)::bigint AS block_time
        FROM tx
        JOIN block b ON b.id = tx.block_id
        WHERE b.block_no >= $2
          AND tx.id IN (
            SELECT tx_id FROM tx_out WHERE address = $1
            UNION
            SELECT tx_in_id FROM tx_in
            JOIN tx_out ON tx_out.tx_id = tx_in.tx_out_id
                       AND tx_out.index = tx_in.tx_out_index
            WHERE tx_out.address = $1
        )
        ORDER BY b.block_no ASC
    """, address, from_block)
    return [dict(r) for r in rows]


async def get_stake_transactions(stake_address: str, from_block: int = 0) -> list:
    """Get all transactions for a stake address (replaces /accounts/{addr}/transactions)."""
    from services.cardano_db import query
    rows = await query("""
        SELECT DISTINCT
            encode(tx.hash, 'hex') AS tx_hash,
            b.block_no AS block_height,
            EXTRACT(EPOCH FROM b.time)::bigint AS block_time
        FROM tx
        JOIN block b ON b.id = tx.block_id
        WHERE b.block_no >= $2
          AND tx.id IN (
            SELECT txo.tx_id FROM tx_out txo
            JOIN stake_address sa ON sa.id = txo.stake_address_id
            WHERE sa.view = $1
            UNION
            SELECT txi.tx_in_id FROM tx_in txi
            JOIN tx_out txo ON txo.tx_id = txi.tx_out_id
                           AND txo.index = txi.tx_out_index
            JOIN stake_address sa ON sa.id = txo.stake_address_id
            WHERE sa.view = $1
        )
        ORDER BY b.block_no ASC
    """, stake_address, from_block)
    return [dict(r) for r in rows]


async def get_utxos_at_address(address: str) -> list:
    """Get all unspent UTXOs at an address with multi-asset amounts
    (replaces /addresses/{addr}/utxos)."""
    from services.cardano_db import query

    # Base UTXOs
    rows = await query("""
        SELECT
            encode(tx.hash, 'hex') AS tx_hash,
            txo.index::int AS tx_index,
            txo.value::text AS lovelace,
            encode(txo.data_hash, 'hex') AS data_hash,
            txo.inline_datum_id
        FROM tx_out txo
        JOIN tx ON tx.id = txo.tx_id
        LEFT JOIN tx_in txi ON txi.tx_out_id = txo.tx_id
                            AND txi.tx_out_index = txo.index
        WHERE txo.address = $1
          AND txi.id IS NULL
    """, address)

    if not rows:
        return []

    # Multi-asset amounts for these UTXOs
    assets = await query("""
        SELECT
            encode(tx.hash, 'hex') AS tx_hash,
            txo.index::int AS tx_index,
            encode(ma.policy, 'hex') AS policy_id,
            encode(ma.name, 'hex') AS asset_name_hex,
            mto.quantity::text AS quantity
        FROM ma_tx_out mto
        JOIN multi_asset ma ON ma.id = mto.ident
        JOIN tx_out txo ON txo.id = mto.tx_out_id
        JOIN tx ON tx.id = txo.tx_id
        LEFT JOIN tx_in txi ON txi.tx_out_id = txo.tx_id
                            AND txi.tx_out_index = txo.index
        WHERE txo.address = $1
          AND txi.id IS NULL
    """, address)

    # Group assets by (tx_hash, tx_index)
    asset_map = {}
    for a in assets:
        key = (a["tx_hash"], a["tx_index"])
        asset_map.setdefault(key, []).append(a)

    # Build Blockfrost-compatible response
    result = []
    for r in rows:
        key = (r["tx_hash"], r["tx_index"])
        utxo_assets = asset_map.get(key, [])
        amount = [{"unit": "lovelace", "quantity": r["lovelace"]}]
        for a in utxo_assets:
            amount.append({
                "unit": a["policy_id"] + a["asset_name_hex"],
                "quantity": a["quantity"],
            })
        result.append({
            "tx_hash": r["tx_hash"],
            "tx_index": r["tx_index"],
            "output_index": r["tx_index"],
            "amount": amount,
            "data_hash": r["data_hash"],
            "inline_datum": r["inline_datum_id"] is not None,
        })

    return result


async def get_address_balance(address: str) -> dict:
    """Get ADA balance + native assets for an address (replaces /addresses/{addr})."""
    from services.cardano_db import query_one, query

    row = await query_one("""
        SELECT
            COALESCE(SUM(txo.value), 0)::text AS balance_lovelace
        FROM tx_out txo
        LEFT JOIN tx_in txi ON txi.tx_out_id = txo.tx_id
                            AND txi.tx_out_index = txo.index
        WHERE txo.address = $1
          AND txi.id IS NULL
    """, address)

    balance = int(row["balance_lovelace"]) if row else 0

    # Native assets
    assets = await query("""
        SELECT
            encode(ma.policy, 'hex') AS policy_id,
            encode(ma.name, 'hex') AS asset_name_hex,
            SUM(mto.quantity)::text AS quantity
        FROM ma_tx_out mto
        JOIN multi_asset ma ON ma.id = mto.ident
        JOIN tx_out txo ON txo.id = mto.tx_out_id
        LEFT JOIN tx_in txi ON txi.tx_out_id = txo.tx_id
                            AND txi.tx_out_index = txo.index
        WHERE txo.address = $1
          AND txi.id IS NULL
        GROUP BY ma.policy, ma.name
    """, address)

    # Build Blockfrost-compatible amount array
    amount = [{"unit": "lovelace", "quantity": str(balance)}]
    for a in assets:
        amount.append({
            "unit": a["policy_id"] + a["asset_name_hex"],
            "quantity": a["quantity"],
        })

    return {
        "address": address,
        "amount": amount,
        "stake_address": None,  # Would need separate lookup
        "type": "shelley",
    }


# ---------------------------------------------------------------------------
# Tier 2: Stake account, expansion, metadata
# ---------------------------------------------------------------------------

async def get_stake_addresses(stake_address: str) -> list:
    """Get all payment addresses for a stake key
    (replaces /accounts/{addr}/addresses)."""
    from services.cardano_db import query
    rows = await query("""
        SELECT DISTINCT txo.address
        FROM tx_out txo
        JOIN stake_address sa ON sa.id = txo.stake_address_id
        WHERE sa.view = $1
    """, stake_address)
    return [{"address": r["address"]} for r in rows]


async def get_address_stake_key(address: str) -> Optional[str]:
    """Look up the stake address for a payment address
    (replaces /addresses/{addr} for stake key lookup)."""
    from services.cardano_db import query_one
    row = await query_one("""
        SELECT sa.view AS stake_address
        FROM tx_out txo
        JOIN stake_address sa ON sa.id = txo.stake_address_id
        WHERE txo.address = $1
        LIMIT 1
    """, address)
    return row["stake_address"] if row else None


# ---------------------------------------------------------------------------
# Health / diagnostics
# ---------------------------------------------------------------------------

async def check_schema_version() -> Optional[str]:
    """Check DB Sync schema version for compatibility."""
    from services.cardano_db import query_one
    try:
        row = await query_one("""
            SELECT stage_one, stage_two, stage_three
            FROM schema_version
            ORDER BY id DESC LIMIT 1
        """)
        if row:
            version = f"{row['stage_one']}.{row['stage_two']}.{row['stage_three']}"
            if row['stage_one'] != 13:
                logger.warning(
                    f"DB Sync major version {row['stage_one']} differs from "
                    f"tested version 13. SQL queries may need updating."
                )
            return version
    except Exception as e:
        logger.warning(f"Could not check DB Sync schema version: {e}")
    return None
