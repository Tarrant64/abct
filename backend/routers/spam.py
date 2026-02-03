"""
Spam Token Management Router

Endpoints for detecting and managing spam tokens using Moralis.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import aiosqlite
import logging
from datetime import datetime

from auth_utils import verify_session
from database import get_all_wallets, DATABASE_PATH
from services.moralis import moralis_service

router = APIRouter(prefix="/spam", tags=["spam"])
logger = logging.getLogger(__name__)


class HideTokenRequest(BaseModel):
    blockchain: str
    token_address: str
    token_symbol: Optional[str] = None
    token_name: Optional[str] = None
    reason: str = "spam"


class HideTokensRequest(BaseModel):
    tokens: List[HideTokenRequest]


@router.get("/scan")
async def scan_for_spam(user_id: int = Depends(verify_session)):
    """
    Scan all EVM and Solana wallets for spam tokens.
    Returns list of detected spam tokens for user confirmation.
    """
    if not await moralis_service.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Moralis API key not configured. Please add it in API Management."
        )

    try:
        # Get all user wallets
        wallets = await get_all_wallets(user_id=user_id)

        # Filter for EVM and Solana chains
        evm_chains_map = {
            "ethereum": "eth",
            "polygon": "polygon",
            "base": "base"
        }

        spam_tokens = []
        scanned_count = 0

        # Scan EVM wallets
        for wallet in wallets:
            if wallet['blockchain'] in evm_chains_map:
                chain_id = evm_chains_map[wallet['blockchain']]
                logger.info(f"Scanning {wallet['blockchain']} wallet {wallet['address'][:10]}...")

                spam = await moralis_service.scan_wallet_tokens(
                    wallet['address'],
                    chain_id
                )

                for token in spam:
                    token['wallet_address'] = wallet['address']
                    token['blockchain'] = wallet['blockchain']

                spam_tokens.extend(spam)
                scanned_count += 1

            elif wallet['blockchain'] == 'solana':
                logger.info(f"Scanning Solana wallet {wallet['address'][:10]}...")

                spam = await moralis_service.scan_solana_wallet(wallet['address'])

                for token in spam:
                    token['wallet_address'] = wallet['address']
                    token['blockchain'] = 'solana'

                spam_tokens.extend(spam)
                scanned_count += 1

        logger.info(f"Scan complete: {len(spam_tokens)} spam tokens found across {scanned_count} wallets")

        return {
            "spam_tokens": spam_tokens,
            "total_found": len(spam_tokens),
            "wallets_scanned": scanned_count
        }

    except Exception as e:
        logger.error(f"Error scanning for spam: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hide")
async def hide_tokens(request: HideTokensRequest, user_id: int = Depends(verify_session)):
    """
    Hide selected spam tokens from wallet display.
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            hidden_count = 0

            for token in request.tokens:
                await db.execute("""
                    INSERT OR REPLACE INTO hidden_tokens
                    (user_id, blockchain, token_address, token_symbol, token_name, reason, hidden_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    token.blockchain,
                    token.token_address,
                    token.token_symbol,
                    token.token_name,
                    token.reason,
                    datetime.now().isoformat()
                ))
                hidden_count += 1

            await db.commit()

            logger.info(f"Hidden {hidden_count} tokens for user {user_id}")

            return {
                "success": True,
                "hidden_count": hidden_count,
                "message": f"Successfully hidden {hidden_count} spam token(s)"
            }

    except Exception as e:
        logger.error(f"Error hiding tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hidden")
async def get_hidden_tokens(user_id: int = Depends(verify_session)):
    """
    Get list of hidden tokens for the current user.
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute("""
                SELECT blockchain, token_address, token_symbol, token_name, reason, hidden_at
                FROM hidden_tokens
                WHERE user_id = ?
                ORDER BY hidden_at DESC
            """, (user_id,))

            rows = await cursor.fetchall()

            hidden_tokens = []
            for row in rows:
                hidden_tokens.append({
                    "blockchain": row['blockchain'],
                    "token_address": row['token_address'],
                    "token_symbol": row['token_symbol'],
                    "token_name": row['token_name'],
                    "reason": row['reason'],
                    "hidden_at": row['hidden_at']
                })

            return {
                "hidden_tokens": hidden_tokens,
                "total_count": len(hidden_tokens)
            }

    except Exception as e:
        logger.error(f"Error getting hidden tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/unhide/{blockchain}/{token_address}")
async def unhide_token(blockchain: str, token_address: str, user_id: int = Depends(verify_session)):
    """
    Unhide a previously hidden token.
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("""
                DELETE FROM hidden_tokens
                WHERE user_id = ? AND blockchain = ? AND token_address = ?
            """, (user_id, blockchain, token_address))

            await db.commit()

            if cursor.rowcount > 0:
                logger.info(f"Unhidden token {token_address} on {blockchain} for user {user_id}")
                return {"success": True, "message": "Token unhidden successfully"}
            else:
                return {"success": False, "message": "Token not found in hidden list"}

    except Exception as e:
        logger.error(f"Error unhiding token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_spam_filter_status(user_id: int = Depends(verify_session)):
    """
    Get spam filter configuration status.
    """
    return {
        "configured": await moralis_service.is_configured(),
        "hidden_tokens_count": await get_hidden_tokens_count(user_id)
    }


async def get_hidden_tokens_count(user_id: int) -> int:
    """Helper to get count of hidden tokens for a user."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM hidden_tokens WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        return 0
