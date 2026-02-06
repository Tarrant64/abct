"""
Custom Tokens Router - API endpoints for manual token tracking.

Allows users to manually add tokens to track that may not be in their wallets.
These appear in a "Custom Wallets" section in the UI.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    add_custom_token, get_all_custom_tokens, get_custom_token_by_id,
    get_custom_token_by_policy, update_custom_token, delete_custom_token
)
from services.pricing import pricing_service
from middleware.auth import verify_admin
from auth_utils import verify_session
from services.http_client import get_client

router = APIRouter(prefix="/custom-tokens", tags=["custom-tokens"])


class TokenAddRequest(BaseModel):
    """Request body for adding a custom token."""
    policy_id: str
    asset_name: Optional[str] = ""
    ticker: Optional[str] = None
    blockchain: str  # cardano, ethereum, bitcoin
    quantity: float
    decimals: Optional[int] = 0
    label: Optional[str] = None


class TokenUpdateRequest(BaseModel):
    """Request body for updating a custom token."""
    quantity: Optional[float] = None
    label: Optional[str] = None
    ticker: Optional[str] = None


@router.get("")
async def list_custom_tokens(user_id: int = Depends(verify_session)):
    """
    Get all custom tokens being tracked.
    Returns tokens with current price data if available.
    """
    tokens = await get_all_custom_tokens(user_id=user_id)

    # Get current prices
    all_prices = await pricing_service.get_all_tracked_prices()

    # Calculate USD values
    total_usd = 0.0
    tracked_total_usd = 0.0
    for token in tokens:
        # Try to get price by ticker
        ticker = (token.get('ticker') or '').upper()
        include_in_total = token.get('include_in_total', 1) == 1

        if ticker and ticker in all_prices:
            price = all_prices[ticker].get('usd', 0)
            token['current_price'] = price
            quantity = float(token.get('quantity', 0))
            token['value_usd'] = quantity * price
            total_usd += token['value_usd']
            if include_in_total:
                tracked_total_usd += token['value_usd']
        elif token.get('price_usd'):
            # Use stored price if no live price
            token['current_price'] = token['price_usd']
            quantity = float(token.get('quantity', 0))
            token['value_usd'] = quantity * token['price_usd']
            total_usd += token['value_usd']
            if include_in_total:
                tracked_total_usd += token['value_usd']
        else:
            token['current_price'] = None
            token['value_usd'] = None

    return {
        'tokens': tokens,
        'count': len(tokens),
        'total_value_usd': total_usd,
        'tracked_total_usd': tracked_total_usd
    }


@router.post("")
async def add_token(user_id: int = Depends(verify_session), request: TokenAddRequest = None):
    """
    Add a new custom token for manual tracking.

    Validates the blockchain and attempts to look up token info.
    """
    # Validate blockchain
    if request.blockchain not in ['cardano', 'ethereum', 'bitcoin']:
        raise HTTPException(
            status_code=400,
            detail="Only Cardano, Ethereum, and Bitcoin chains are supported"
        )

    # Validate policy_id format based on blockchain
    if request.blockchain == 'cardano':
        if len(request.policy_id) != 56:
            raise HTTPException(
                status_code=400,
                detail="Cardano policy ID must be 56 characters"
            )
    elif request.blockchain == 'ethereum':
        if not request.policy_id.startswith('0x') or len(request.policy_id) != 42:
            raise HTTPException(
                status_code=400,
                detail="Ethereum contract address must start with 0x and be 42 characters"
            )

    # Check if token already exists
    existing = await get_custom_token_by_policy(
        request.policy_id,
        request.asset_name or '',
        user_id=user_id
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Token already exists. Use PUT to update quantity."
        )

    # Try to look up token info (for Cardano tokens)
    token_info = None
    if request.blockchain == 'cardano' and not request.ticker:
        token_info = await lookup_cardano_token(request.policy_id, request.asset_name)

    # Prepare token data
    token_data = {
        'policy_id': request.policy_id,
        'asset_name': request.asset_name or '',
        'ticker': request.ticker or (token_info.get('ticker') if token_info else None),
        'blockchain': request.blockchain,
        'quantity': request.quantity,
        'decimals': request.decimals,
        'label': request.label,
        'token_name': token_info.get('name') if token_info else None,
        'price_usd': token_info.get('price_usd') if token_info else None
    }

    token_id = await add_custom_token(token_data, user_id=user_id)

    return {
        'message': 'Token added successfully',
        'token_id': token_id,
        'token_info': token_info
    }


@router.get("/lookup")
async def lookup_token(
    user_id: int = Depends(verify_session),
    policy_id: str = Query(..., description="Policy ID or contract address"),
    asset_name: str = Query("", description="Asset name (hex) for Cardano tokens"),
    blockchain: str = Query("cardano", description="Blockchain: cardano, ethereum, bitcoin")
):
    """
    Look up token information by policy ID / contract address.

    Returns token name, ticker, and current price if available.
    """
    if blockchain == 'cardano':
        info = await lookup_cardano_token(policy_id, asset_name)
        if info:
            return {'found': True, **info}
        return {'found': False, 'message': 'Token ID not recognized'}

    elif blockchain == 'ethereum':
        # For Ethereum, we'd need to query Etherscan or similar
        # For now, return not found
        return {'found': False, 'message': 'Ethereum token lookup not yet implemented'}

    elif blockchain == 'bitcoin':
        return {'found': False, 'message': 'Bitcoin does not have tokens with policy IDs'}

    return {'found': False, 'message': 'ID not recognized'}


async def lookup_cardano_token(policy_id: str, asset_name: str = "") -> dict:
    """
    Look up Cardano token information from various sources.
    """
    import httpx
    from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL

    if not BLOCKFROST_API_KEY:
        return None

    try:
        # Build asset ID
        asset_id = policy_id + asset_name if asset_name else policy_id

        client = get_client("blockfrost", timeout=30.0)

        # Try Blockfrost for token info
        response = await client.get(
            f"{BLOCKFROST_BASE_URL}/assets/{asset_id}",
            headers={"project_id": BLOCKFROST_API_KEY}
        )

        if response.status_code == 200:
            data = response.json()
            metadata = data.get('onchain_metadata', {})
            token_info = {
                'policy_id': data.get('policy_id'),
                'asset_name': data.get('asset_name'),
                'name': metadata.get('name') or data.get('asset_name'),
                'ticker': metadata.get('ticker'),
                'decimals': metadata.get('decimals', 0),
                'description': metadata.get('description'),
            }

            # Try to get price from our pricing service
            ticker = token_info.get('ticker')
            if ticker:
                try:
                    prices = await pricing_service.get_all_tracked_prices()
                    if ticker.upper() in prices:
                        token_info['price_usd'] = prices[ticker.upper()].get('usd', 0)
                except:
                    pass

            return token_info

        elif response.status_code == 404:
            return None

    except Exception as e:
        print(f"Error looking up Cardano token: {e}")

    return None


@router.get("/{token_id}")
async def get_token(token_id: int, user_id: int = Depends(verify_session)):
    """Get a specific custom token by ID."""
    token = await get_custom_token_by_id(token_id, user_id=user_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Get current price
    ticker = token.get('ticker', '').upper()
    if ticker:
        try:
            prices = await pricing_service.get_all_tracked_prices()
            if ticker in prices:
                token['current_price'] = prices[ticker].get('usd', 0)
                quantity = float(token.get('quantity', 0))
                token['value_usd'] = quantity * token['current_price']
        except:
            pass

    return token


@router.put("/{token_id}")
async def update_token(token_id: int, user_id: int = Depends(verify_session), request: TokenUpdateRequest = None):
    """Update a custom token's quantity or label."""
    token = await get_custom_token_by_id(token_id, user_id=user_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    updates = {}
    if request.quantity is not None:
        updates['quantity'] = str(request.quantity)
    if request.label is not None:
        updates['label'] = request.label
    if request.ticker is not None:
        updates['ticker'] = request.ticker

    if updates:
        await update_custom_token(token_id, updates, user_id=user_id)

    return {'message': 'Token updated successfully'}


@router.delete("/{token_id}")
async def remove_token(token_id: int, user_id: int = Depends(verify_session)):
    """Remove a custom token from tracking."""
    token = await get_custom_token_by_id(token_id, user_id=user_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    await delete_custom_token(token_id, user_id=user_id)

    return {'message': 'Token removed successfully'}


class TokenToggleRequest(BaseModel):
    """Request body for toggling token inclusion in portfolio total."""
    include_in_total: bool


@router.post("/{token_id}/toggle")
async def toggle_token_inclusion(token_id: int, user_id: int = Depends(verify_session), request: TokenToggleRequest = None):
    """Toggle whether a custom token is included in the portfolio total."""
    token = await get_custom_token_by_id(token_id, user_id=user_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    await update_custom_token(token_id, {'include_in_total': 1 if request.include_in_total else 0}, user_id=user_id)

    return {
        'message': 'Token inclusion updated',
        'include_in_total': request.include_in_total
    }
