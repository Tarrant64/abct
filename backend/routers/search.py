"""
Global Search Router

Provides a unified search endpoint that queries wallets, tokens,
DeFi/governance positions, staking, and exchange holdings.
Used by the frontend global search component in the header.
"""

from fastapi import APIRouter, Depends, Query
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_cache, get_all_wallets
from auth_utils import verify_session

import aiosqlite
from config import DATABASE_PATH

router = APIRouter(prefix="/search", tags=["search"])

# Exchange names to scan for cached portfolios
EXCHANGE_NAMES = ["coinbase", "binance", "binance_us", "okx", "kucoin", "bitget", "gate", "kraken"]


@router.get("")
async def global_search(
    q: str = Query(..., min_length=2, max_length=100),
    user_id: int = Depends(verify_session),
):
    """Search wallets, tokens, DeFi positions, staking, and exchange holdings"""
    query = q.strip().lower()

    # 1. Search wallets by label or address
    wallets = []
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, address, label, blockchain FROM wallets
                   WHERE user_id = ? AND (LOWER(label) LIKE ? OR LOWER(address) LIKE ?)
                   LIMIT 3""",
                (user_id, f"%{query}%", f"%{query}%"),
            )
            rows = await cursor.fetchall()
            wallets = [
                {
                    "id": row["id"],
                    "address": row["address"],
                    "label": row["label"],
                    "blockchain": row["blockchain"],
                }
                for row in rows
            ]
    except Exception:
        pass

    # 2. Search tokens from cached portfolio assets (wallet-held tokens)
    tokens = []
    try:
        cached = await get_cache("native_assets_all", user_id=user_id)
        if cached:
            assets = json.loads(cached) if isinstance(cached, str) else cached
            if isinstance(assets, dict):
                asset_list = assets.get("assets", assets.get("tokens", []))
                if isinstance(asset_list, dict):
                    asset_list = list(asset_list.values())
            elif isinstance(assets, list):
                asset_list = assets
            else:
                asset_list = []

            for asset in asset_list:
                if not isinstance(asset, dict):
                    continue
                ticker = (asset.get("ticker") or asset.get("symbol") or "").lower()
                name = (asset.get("asset_name") or asset.get("name") or "").lower()
                if query in ticker or query in name:
                    tokens.append(
                        {
                            "ticker": asset.get("ticker") or asset.get("symbol", ""),
                            "name": asset.get("asset_name") or asset.get("name", ""),
                            "blockchain": asset.get("blockchain", ""),
                            "total_value_usd": asset.get("value_usd") or asset.get("total_value_usd", 0),
                            "price_usd": asset.get("price_usd") or asset.get("price", 0),
                            "logo_url": asset.get("logo_url") or asset.get("logo", ""),
                        }
                    )
                    if len(tokens) >= 4:
                        break
    except Exception:
        pass

    # 3. Search DeFi / governance positions from cached defi_summary
    defi = []
    try:
        cached = await get_cache(f"defi_summary_{user_id}")
        if cached:
            data = json.loads(cached) if isinstance(cached, str) else cached
            positions = data.get("all_positions", [])
            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                token = (pos.get("token") or "").lower()
                asset_name = (pos.get("asset_name") or "").lower()
                protocol = (pos.get("protocol") or "").lower()
                type_label = (pos.get("type_label") or "").lower()
                if query in token or query in asset_name or query in protocol or query in type_label:
                    defi.append(
                        {
                            "token": pos.get("token", ""),
                            "name": pos.get("asset_name", ""),
                            "protocol": pos.get("protocol", ""),
                            "type": pos.get("type_label", ""),
                            "quantity": pos.get("quantity_formatted") or str(pos.get("quantity", "")),
                            "logo_url": pos.get("logo_url", ""),
                        }
                    )
                    if len(defi) >= 3:
                        break
    except Exception:
        pass

    # 4. Search staking positions from cached staking data per wallet
    staking = []
    try:
        user_wallets = await get_all_wallets(user_id=user_id)
        cardano_addrs = [w["address"] for w in user_wallets if w["blockchain"] == "cardano"]
        seen_tokens = set()
        for addr in cardano_addrs:
            if len(staking) >= 3:
                break
            cached = await get_cache(f"staking_positions_{addr}")
            if not cached:
                continue
            data = json.loads(cached) if isinstance(cached, str) else cached
            protocols = data.get("protocols", {})
            for proto_name, proto_data in protocols.items():
                if len(staking) >= 3:
                    break
                if not isinstance(proto_data, dict):
                    continue
                staked_list = proto_data.get("staked", [])
                for item in staked_list:
                    if not isinstance(item, dict):
                        continue
                    ticker = (item.get("ticker") or item.get("token") or "").lower()
                    name = (item.get("name") or proto_name or "").lower()
                    if query in ticker or query in name or query in proto_name.lower():
                        dedup_key = f"{proto_name}:{ticker}"
                        if dedup_key in seen_tokens:
                            continue
                        seen_tokens.add(dedup_key)
                        staking.append(
                            {
                                "token": item.get("ticker") or item.get("token", ""),
                                "name": item.get("name") or proto_name,
                                "protocol": proto_name,
                                "quantity": item.get("quantity_formatted") or str(item.get("quantity", "")),
                                "logo_url": item.get("logo_url", ""),
                            }
                        )
                        if len(staking) >= 3:
                            break
    except Exception:
        pass

    # 5. Search exchange holdings from cached exchange portfolios
    exchanges = []
    try:
        for ex_name in EXCHANGE_NAMES:
            if len(exchanges) >= 3:
                break
            cached = await get_cache(f"{ex_name}_portfolio", user_id=user_id)
            if not cached:
                continue
            data = json.loads(cached) if isinstance(cached, str) else cached
            ex_assets = data.get("assets", [])
            for asset in ex_assets:
                if not isinstance(asset, dict):
                    continue
                currency = (asset.get("currency") or "").lower()
                name = (asset.get("name") or currency).lower()
                if query in currency or query in name:
                    exchanges.append(
                        {
                            "currency": asset.get("currency", ""),
                            "name": asset.get("name") or asset.get("currency", ""),
                            "exchange": ex_name.replace("_", " ").title(),
                            "balance": asset.get("balance", 0),
                            "usd_value": asset.get("usd_value", 0),
                        }
                    )
                    if len(exchanges) >= 3:
                        break
    except Exception:
        pass

    return {
        "tokens": tokens,
        "wallets": wallets,
        "defi": defi,
        "staking": staking,
        "exchanges": exchanges,
    }
