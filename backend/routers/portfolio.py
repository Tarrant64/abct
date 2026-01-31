from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_all_wallets, get_wallet_balance, get_wallet_assets,
    get_cache, set_cache, clear_cache, get_latest_snapshot_date,
    get_all_token_metadata, toggle_token_tracking, get_tracked_tokens,
    save_token_metadata, update_native_asset_decimals
)
from services.cardano import cardano_service
from services.snapshot import snapshot_service
from services.pricing import pricing_service
from services.defi import DEFI_PROTOCOLS
from services.taptools import taptools_wallet_service
from services.logokit_service import logokit_service
from auth_utils import verify_session


class TokenTrackRequest(BaseModel):
    """Request to toggle token tracking."""
    asset_id: str
    track: bool
    ticker: str = None
    decimals: int = None

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Cache TTL in seconds (7 days for portfolio so it persists between sessions, only cleared on manual refresh)
PORTFOLIO_CACHE_TTL = 604800  # 7 days
STAKE_CACHE_TTL = 3600  # 1 hour for stake address lookups

async def calculate_wallet_native_assets_value(wallet_id: int, blockchain: str, user_id: int):
    """Calculate total USD value of non-ignored native assets for a wallet."""
    import aiosqlite
    from config import DATABASE_PATH
    from services.taptools import taptools_wallet_service

    # Get non-ignored assets
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                na.*,
                COALESCE(ct.ticker, tm.ticker) as ticker,
                w.address as wallet_address
            FROM native_assets na
            LEFT JOIN token_metadata tm ON na.asset_id = tm.asset_id
            LEFT JOIN custom_tokens ct ON
                ct.policy_id = na.policy_id
                AND ct.asset_name = na.asset_name
                AND ct.user_id = na.user_id
            LEFT JOIN wallets w ON na.wallet_id = w.id
            WHERE na.wallet_id = ? AND (na.ignored IS NULL OR na.ignored = 0)
        """, (wallet_id,))
        rows = await cursor.fetchall()
        assets = [dict(row) for row in rows]

    if not assets:
        return 0.0

    # Get ADA price for conversions
    ada_price_usd = await pricing_service.get_price('ADA')

    # For Cardano, try to get TapTools data
    taptools_positions = {}
    if blockchain == 'cardano' and taptools_wallet_service.is_configured() and assets:
        try:
            wallet_address = assets[0].get('wallet_address')
            if wallet_address:
                portfolio = await taptools_wallet_service.get_wallet_portfolio(wallet_address)
                if portfolio and portfolio.get('positions'):
                    for pos in portfolio['positions']:
                        unit = pos.get('unit', '')
                        if unit and unit != 'lovelace':
                            taptools_positions[unit] = pos
        except Exception:
            pass

    total_value_usd = 0.0

    for asset in assets:
        raw_qty = float(asset.get('quantity') or 0)
        decimals = int(asset.get('decimals') or 0)
        actual_qty = raw_qty / (10 ** decimals)

        if actual_qty == 0:
            continue

        # Try TapTools first for Cardano
        if blockchain == 'cardano' and asset.get('asset_id') in taptools_positions:
            pos = taptools_positions[asset['asset_id']]
            total_ada = float(pos.get('adaValue', 0))
            if total_ada > 0 and ada_price_usd:
                total_value_usd += total_ada * ada_price_usd
        # Fallback to direct USD pricing
        elif asset.get('ticker'):
            try:
                price_usd = await pricing_service.get_price(asset['ticker'].upper())
                if price_usd and price_usd > 0:
                    total_value_usd += actual_qty * price_usd
            except Exception:
                pass

    return total_value_usd


@router.get("/summary")
async def get_portfolio_summary(user_id: int = Depends(verify_session), refresh: bool = Query(False, description="Force refresh cache")):
    """Get a summary of the entire portfolio grouped by blockchain."""
    cache_key = f"portfolio_summary_{user_id}"

    # Check cache first (unless refresh requested)
    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            cached['from_cache'] = True
            return cached

    wallets = await get_all_wallets(user_id=user_id)

    summary = {
        'cardano': {
            'wallet_count': 0,
            'total_ada': 0.0,
            'native_assets_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': [],
            'stake_groups': []  # Wallets grouped by stake key
        },
        'bitcoin': {
            'wallet_count': 0,
            'total_btc': 0.0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'ethereum': {
            'wallet_count': 0,
            'total_eth': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'solana': {
            'wallet_count': 0,
            'total_sol': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'polygon': {
            'wallet_count': 0,
            'total_matic': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'base': {
            'wallet_count': 0,
            'total_eth': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        }
    }

    # Track stake address groupings for Cardano
    stake_groups = {}  # stake_address -> list of wallets

    for wallet in wallets:
        blockchain = wallet['blockchain']
        balance_info = await get_wallet_balance(wallet['id'])
        assets = await get_wallet_assets(wallet['id'])

        balance = float(balance_info['amount']) if balance_info else 0.0

        # Calculate native assets value for this wallet
        native_assets_value_usd = await calculate_wallet_native_assets_value(
            wallet['id'], blockchain, user_id
        )

        wallet_summary = {
            'id': wallet['id'],
            'address': wallet['address'],
            'address_short': f"{wallet['address'][:12]}...{wallet['address'][-8:]}",
            'label': wallet['label'],
            'balance': balance,
            'native_assets_value_usd': native_assets_value_usd,
            'updated_at': wallet.get('updated_at')
        }

        if blockchain == 'cardano':
            summary['cardano']['wallet_count'] += 1
            summary['cardano']['total_ada'] += balance
            summary['cardano']['native_assets_count'] += len(assets)
            summary['cardano']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['native_assets_count'] = len(assets)

            # Get stake address for grouping
            stake_address = await cardano_service.get_stake_address(wallet['address'])
            wallet_summary['stake_address'] = stake_address

            if stake_address:
                if stake_address not in stake_groups:
                    stake_groups[stake_address] = {
                        'stake_address': stake_address,
                        'stake_address_short': f"{stake_address[:12]}...{stake_address[-8:]}",
                        'wallets': [],
                        'total_ada': 0.0,
                        'total_assets': 0,
                        'native_assets_value_usd': 0.0
                    }
                stake_groups[stake_address]['wallets'].append(wallet_summary)
                stake_groups[stake_address]['total_ada'] += balance
                stake_groups[stake_address]['total_assets'] += len(assets)
                stake_groups[stake_address]['native_assets_value_usd'] += native_assets_value_usd
            else:
                # No stake key - treat as individual wallet
                stake_groups[f"no_stake_{wallet['address']}"] = {
                    'stake_address': None,
                    'stake_address_short': None,
                    'wallets': [wallet_summary],
                    'total_ada': balance,
                    'total_assets': len(assets),
                    'native_assets_value_usd': native_assets_value_usd
                }

            summary['cardano']['wallets'].append(wallet_summary)

        elif blockchain == 'bitcoin':
            summary['bitcoin']['wallet_count'] += 1
            summary['bitcoin']['total_btc'] += balance
            summary['bitcoin']['native_assets_value_usd'] += native_assets_value_usd
            summary['bitcoin']['wallets'].append(wallet_summary)

        elif blockchain == 'ethereum':
            summary['ethereum']['wallet_count'] += 1
            summary['ethereum']['total_eth'] += balance
            summary['ethereum']['token_count'] += len(assets)
            summary['ethereum']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['ethereum']['wallets'].append(wallet_summary)

        elif blockchain == 'solana':
            summary['solana']['wallet_count'] += 1
            summary['solana']['total_sol'] += balance
            summary['solana']['token_count'] += len(assets)
            summary['solana']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['solana']['wallets'].append(wallet_summary)

        elif blockchain == 'polygon':
            summary['polygon']['wallet_count'] += 1
            summary['polygon']['total_matic'] += balance
            summary['polygon']['token_count'] += len(assets)
            summary['polygon']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['polygon']['wallets'].append(wallet_summary)

        elif blockchain == 'base':
            summary['base']['wallet_count'] += 1
            summary['base']['total_eth'] += balance
            summary['base']['token_count'] += len(assets)
            summary['base']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['base']['wallets'].append(wallet_summary)

    # Convert stake groups dict to list and round totals
    summary['cardano']['stake_groups'] = [
        {**group, 'total_ada': round(group['total_ada'], 6)}
        for group in stake_groups.values()
    ]

    # Sort stake groups by total_ada descending
    summary['cardano']['stake_groups'].sort(key=lambda x: x['total_ada'], reverse=True)

    # Round totals for display
    summary['cardano']['total_ada'] = round(summary['cardano']['total_ada'], 6)
    summary['bitcoin']['total_btc'] = round(summary['bitcoin']['total_btc'], 8)
    summary['ethereum']['total_eth'] = round(summary['ethereum']['total_eth'], 8)
    summary['solana']['total_sol'] = round(summary['solana']['total_sol'], 9)
    summary['polygon']['total_matic'] = round(summary['polygon']['total_matic'], 6)
    summary['base']['total_eth'] = round(summary['base']['total_eth'], 8)

    # Cache the result with timestamp
    from datetime import datetime
    summary['from_cache'] = False
    summary['last_updated'] = datetime.now().isoformat()
    await set_cache(cache_key, summary, PORTFOLIO_CACHE_TTL, user_id=user_id)

    return summary

# Cache TTL for native assets (7 days - tokens don't change often, only cleared on manual refresh)
NATIVE_ASSETS_CACHE_TTL = 604800

@router.get("/assets")
async def get_all_native_assets(user_id: int = Depends(verify_session), refresh: bool = Query(False, description="Force refresh cache")):
    """
    Get all native assets across all wallets with prices.
    Returns aggregated quantities, proper decimal conversion, and USD values.
    Uses caching for faster loads - pass refresh=true to force update.
    """
    cache_key = f"native_assets_all"

    # Check cache first (unless refresh requested)
    if not refresh:
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            # Still need to recalculate prices since they change frequently
            return await _enrich_cached_assets_with_prices(cached)

    wallets = await get_all_wallets(user_id=user_id)

    all_assets = []
    for wallet in wallets:
        blockchain = wallet['blockchain']
        assets = await get_wallet_assets(wallet['id'])

        for asset in assets:
            asset['wallet_address'] = wallet['address']
            asset['wallet_label'] = wallet['label']
            asset['blockchain'] = blockchain

            # Normalize field names for non-Cardano tokens
            if blockchain == 'ethereum':
                # ERC-20 tokens use contract_address as asset_id
                if 'asset_id' not in asset or not asset['asset_id']:
                    asset['asset_id'] = asset.get('policy_id', '')
                asset['asset_name'] = asset.get('asset_name', 'ERC-20')
            elif blockchain == 'solana':
                # SPL tokens use mint as asset_id
                if 'asset_id' not in asset or not asset['asset_id']:
                    asset['asset_id'] = asset.get('policy_id', '')
                asset['asset_name'] = asset.get('asset_name', 'SPL')

            all_assets.append(asset)

    # Get token metadata for fallback decimals and tracking status
    all_metadata = await get_all_token_metadata()
    metadata_by_id = {m['asset_id']: m for m in all_metadata}

    # Get tracked token IDs
    tracked_tokens = await get_tracked_tokens()
    tracked_ids = {t['asset_id'] for t in tracked_tokens}

    # Get all prices for value calculation
    all_prices = await pricing_service.get_all_tracked_prices()

    # Group by asset_id and sum quantities
    asset_totals = {}
    for asset in all_assets:
        asset_id = asset['asset_id']
        if asset_id not in asset_totals:
            policy_id = asset['policy_id']

            # Get decimals from asset, or fallback to metadata cache, or DEFI_PROTOCOLS
            decimals = asset.get('decimals', 0)
            ticker = asset.get('ticker')

            # Try metadata cache
            if asset_id in metadata_by_id:
                meta = metadata_by_id[asset_id]
                if decimals == 0:
                    decimals = meta.get('decimals', 0)
                ticker = ticker or meta.get('ticker')

            # Try DEFI_PROTOCOLS by policy_id
            if policy_id in DEFI_PROTOCOLS:
                protocol_info = DEFI_PROTOCOLS[policy_id]
                if decimals == 0:
                    decimals = protocol_info.get('decimals', 0)
                ticker = ticker or protocol_info.get('token')

            # Check if this token is being tracked
            is_tracked = asset_id in tracked_ids

            # Generate LogoKit URL for this asset
            logo_symbol = ticker if ticker else asset['asset_name'][:10] if asset['asset_name'] else 'UNKNOWN'
            logo_url = logokit_service.get_crypto_logo_url(logo_symbol, size=64)

            asset_totals[asset_id] = {
                'asset_id': asset_id,
                'policy_id': policy_id,
                'asset_name': asset['asset_name'],
                'ticker': ticker,
                'decimals': decimals,
                'tracked': is_tracked,
                'blockchain': asset.get('blockchain', 'cardano'),
                'logo_url': logo_url,
                'total_quantity_raw': 0,
                'wallet_count': 0,
                'wallets': []
            }
        asset_totals[asset_id]['total_quantity_raw'] += float(asset['quantity'])
        asset_totals[asset_id]['wallet_count'] += 1
        asset_totals[asset_id]['wallets'].append({
            'address': asset['wallet_address'],
            'label': asset['wallet_label'],
            'quantity': asset['quantity'],
            'blockchain': asset.get('blockchain', 'cardano')
        })

    # Calculate human-readable quantities and USD values
    total_value_usd = 0.0
    tracked_value_usd = 0.0
    valuable_assets = []

    for asset_id, data in asset_totals.items():
        decimals = data.get('decimals') or 0  # Handle None
        raw_qty = data['total_quantity_raw']

        # Convert to human-readable quantity
        human_qty = raw_qty / (10 ** decimals) if decimals > 0 else raw_qty
        data['total_quantity'] = human_qty
        data['total_quantity_formatted'] = f"{human_qty:,.{min(decimals, 6)}f}"

        # Try to find price by ticker
        ticker = data.get('ticker') or data.get('asset_name', '').upper()
        price_info = all_prices.get(ticker.upper()) if ticker else None

        if price_info and price_info.get('usd'):
            price = price_info['usd']
            value_usd = human_qty * price
            data['price_usd'] = price
            data['value_usd'] = value_usd
            data['price_source'] = price_info.get('source')
            total_value_usd += value_usd
            valuable_assets.append(data)

            # Only include in tracked total if token is tracked
            # BUT exclude tokens already counted in DeFi totals (prevent double-counting)
            policy_id = data.get('policy_id', '')
            is_defi_token = policy_id in DEFI_PROTOCOLS
            data['is_defi_token'] = is_defi_token

            if data.get('tracked') and not is_defi_token:
                tracked_value_usd += value_usd
        else:
            data['price_usd'] = None
            data['value_usd'] = None

    # Sort valuable assets by USD value
    valuable_assets.sort(key=lambda x: x.get('value_usd', 0), reverse=True)

    result = {
        'assets': list(asset_totals.values()),
        'valuable_assets': valuable_assets,
        'total_unique_assets': len(asset_totals),
        'total_value_usd': total_value_usd,
        'tracked_value_usd': tracked_value_usd
    }

    # Cache the raw asset data (without prices, since those change frequently)
    cache_data = {
        'assets': list(asset_totals.values()),
        'total_unique_assets': len(asset_totals)
    }
    await set_cache(cache_key, cache_data, NATIVE_ASSETS_CACHE_TTL, user_id=user_id)

    return result


async def _enrich_cached_assets_with_prices(cached_data: dict) -> dict:
    """
    Take cached asset data and recalculate USD values with current prices.
    This allows us to cache the asset quantities but still show current prices.
    """
    assets = cached_data.get('assets', [])

    # Get tracked token IDs
    tracked_tokens = await get_tracked_tokens()
    tracked_ids = {t['asset_id'] for t in tracked_tokens}

    # Get all current prices
    all_prices = await pricing_service.get_all_tracked_prices()

    total_value_usd = 0.0
    tracked_value_usd = 0.0
    valuable_assets = []

    for asset in assets:
        # Update tracked status (might have changed)
        asset['tracked'] = asset['asset_id'] in tracked_ids

        # Recalculate USD value with current price
        ticker = asset.get('ticker') or asset.get('asset_name', '').upper()
        price_info = all_prices.get(ticker.upper()) if ticker else None

        if price_info and price_info.get('usd'):
            price = price_info['usd']
            human_qty = asset.get('total_quantity', 0)
            value_usd = human_qty * price
            asset['price_usd'] = price
            asset['value_usd'] = value_usd
            asset['price_source'] = price_info.get('source')
            total_value_usd += value_usd
            valuable_assets.append(asset)

            # Only include in tracked total if tracked AND not a DeFi token (prevent double-counting)
            policy_id = asset.get('policy_id', '')
            is_defi_token = policy_id in DEFI_PROTOCOLS
            asset['is_defi_token'] = is_defi_token

            if asset.get('tracked') and not is_defi_token:
                tracked_value_usd += value_usd
        else:
            asset['price_usd'] = None
            asset['value_usd'] = None

    # Sort valuable assets by USD value
    valuable_assets.sort(key=lambda x: x.get('value_usd', 0), reverse=True)

    return {
        'assets': assets,
        'valuable_assets': valuable_assets,
        'total_unique_assets': cached_data.get('total_unique_assets', len(assets)),
        'total_value_usd': total_value_usd,
        'tracked_value_usd': tracked_value_usd,
        'cached': True
    }


@router.get("/history")
async def get_portfolio_history(
    user_id: int = Depends(verify_session),
    range: str = Query("7d", description="Time range: 7d (7 days), 4w (4 weeks), 3m (3 months)")
):
    """
    Get portfolio value history for charting.

    Returns daily snapshots of total portfolio value.
    """
    # Map range to days
    days_map = {"7d": 7, "4w": 28, "3m": 90}
    days = days_map.get(range, 7)

    history = await snapshot_service.get_history(days, user_id=user_id)
    latest = await get_latest_snapshot_date(user_id=user_id)

    return {
        "range": range,
        "days": days,
        "data": history,
        "data_points": len(history),
        "latest_snapshot": latest
    }


@router.post("/snapshot")
async def create_portfolio_snapshot(user_id: int = Depends(verify_session), force: bool = Query(False, description="Force create even if exists")):
    """
    Manually create a portfolio snapshot.

    Useful for testing or creating snapshots outside the normal schedule.
    """
    result = await snapshot_service.create_snapshot(user_id=user_id, force=force)
    return result


@router.post("/history/generate")
async def generate_historical_data(user_id: int = Depends(verify_session), days: int = Query(30, description="Number of days of history to generate")):
    """
    Generate historical portfolio data for the past N days.

    Uses CoinGecko's free API to fetch historical prices, then calculates
    portfolio values based on current holdings × historical prices.

    Note: This assumes holdings have been constant. For accurate historical
    balances, transaction history reconstruction would be needed.
    """
    result = await snapshot_service.generate_historical_data(user_id=user_id, days=days)
    return result


@router.post("/history/backfill")
async def backfill_historical_components(user_id: int = Depends(verify_session)):
    """
    Backfill historical snapshots with current staking/defi/exchange/NFT values.

    Updates existing snapshots to include non-wallet components, making the
    chart more accurate. Assumes these component values have been relatively stable.
    """
    result = await snapshot_service.backfill_component_values(user_id=user_id)
    return result


@router.post("/tokens/track")
async def track_token(user_id: int = Depends(verify_session), request: TokenTrackRequest = None):
    """
    Toggle tracking for a native token.

    When tracked, the token will be included in portfolio totals
    and pricing will be fetched for it.
    """
    # Save tracking preference
    await toggle_token_tracking(request.asset_id, request.track, user_id=user_id)

    # If enabling tracking and ticker/decimals provided, save metadata
    if request.track and (request.ticker or request.decimals is not None):
        metadata = {'asset_id': request.asset_id}
        if request.ticker:
            metadata['ticker'] = request.ticker
        if request.decimals is not None:
            metadata['decimals'] = request.decimals
            # Also update the native_assets table
            await update_native_asset_decimals(request.asset_id, request.decimals)
        await save_token_metadata(metadata)

    return {
        'success': True,
        'asset_id': request.asset_id,
        'tracked': request.track
    }


@router.get("/tokens/tracked")
async def get_tracked_token_list(user_id: int = Depends(verify_session)):
    """Get all tokens that are being tracked for pricing."""
    tracked = await get_tracked_tokens(user_id=user_id)
    return {
        'tokens': tracked,
        'count': len(tracked)
    }


@router.post("/tokens/decimals")
async def update_token_decimals(user_id: int = Depends(verify_session), asset_id: str = Query(...), decimals: int = Query(...)):
    """
    Update decimals for a specific token.

    This updates both the metadata cache and all native_assets records.
    """
    # Update metadata
    await save_token_metadata({'asset_id': asset_id, 'decimals': decimals}, user_id=user_id)

    # Update native_assets table
    await update_native_asset_decimals(asset_id, decimals, user_id=user_id)

    return {
        'success': True,
        'asset_id': asset_id,
        'decimals': decimals
    }


@router.get("/verify/{address}")
async def verify_wallet_balance(address: str, user_id: int = Depends(verify_session)):
    """
    Verify wallet balance against TapTools data.

    TapTools returns the full stake key balance including DeFi positions,
    which may differ from our address-level tracking.
    """
    from database import get_wallet_by_address

    wallet = await get_wallet_by_address(address)
    if not wallet:
        return {'error': 'Wallet not found'}

    # Get our local balance
    balance_info = await get_wallet_balance(wallet['id'])
    local_ada = float(balance_info['amount']) if balance_info else 0

    # Get TapTools data
    taptools_portfolio = await taptools_wallet_service.get_wallet_portfolio(address)

    if not taptools_portfolio:
        return {
            'address': address,
            'local_ada': local_ada,
            'taptools_available': False,
            'message': 'TapTools API not configured or unavailable'
        }

    taptools_ada = taptools_portfolio['ada_balance']
    difference = taptools_ada - local_ada

    # Get DeFi positions
    defi_positions = await taptools_wallet_service.get_defi_positions(address)

    return {
        'address': address,
        'label': wallet.get('label'),
        'local_ada': local_ada,
        'taptools_ada': taptools_ada,
        'difference': difference,
        'difference_pct': (difference / local_ada * 100) if local_ada > 0 else 0,
        'taptools_tokens': taptools_portfolio['num_tokens'],
        'taptools_nfts': taptools_portfolio['num_nfts'],
        'defi_positions': defi_positions[:10] if defi_positions else [],  # Top 10
        'note': 'TapTools returns full stake key balance. Difference may be from DeFi or other addresses under same stake key.'
    }


@router.get("/stake/discover/{address}")
async def discover_stake_addresses(address: str, user_id: int = Depends(verify_session)):
    """
    Discover all addresses under the stake key for a given address.

    Compares on-chain addresses with locally tracked wallets to find
    missing addresses that should be added to tracking.
    """
    from database import get_wallet_by_address

    # Get stake address from payment address
    stake_address = await cardano_service.get_stake_address(address)
    if not stake_address:
        return {
            'address': address,
            'has_stake_key': False,
            'message': 'No stake key found for this address'
        }

    # Get all addresses under this stake key from blockchain
    all_addresses = await cardano_service.get_addresses_from_stake(stake_address)
    if not all_addresses:
        return {
            'address': address,
            'stake_address': stake_address,
            'on_chain_addresses': 0,
            'message': 'No addresses found on-chain for this stake key'
        }

    # Check which are tracked vs missing
    tracked = []
    missing = []
    total_tracked_ada = 0
    total_missing_ada = 0

    for addr in all_addresses:
        wallet = await get_wallet_by_address(addr)
        addr_info = await cardano_service.get_address_info(addr)
        ada_balance = float(addr_info.get('balance_ada', 0)) if addr_info else 0
        native_count = len(addr_info.get('native_assets', [])) if addr_info else 0

        addr_summary = {
            'address': addr,
            'address_short': f"{addr[:15]}...{addr[-8:]}",
            'ada_balance': round(ada_balance, 6),
            'native_assets_count': native_count
        }

        if wallet:
            addr_summary['label'] = wallet.get('label')
            addr_summary['wallet_id'] = wallet['id']
            tracked.append(addr_summary)
            total_tracked_ada += ada_balance
        else:
            missing.append(addr_summary)
            total_missing_ada += ada_balance

    # Get stake account info for total controlled
    account_info = await cardano_service.get_stake_account_info(stake_address)

    return {
        'address': address,
        'stake_address': stake_address,
        'stake_address_short': f"{stake_address[:15]}...{stake_address[-8:]}",
        'on_chain_addresses': len(all_addresses),
        'tracked_addresses': len(tracked),
        'missing_addresses': len(missing),
        'total_tracked_ada': round(total_tracked_ada, 6),
        'total_missing_ada': round(total_missing_ada, 6),
        'tracked': tracked,
        'missing': missing,
        'account_info': {
            'controlled_ada': account_info.get('controlled_ada') if account_info else None,
            'rewards_ada': account_info.get('withdrawable_ada') if account_info else None,
            'pool_id': account_info.get('pool_id') if account_info else None
        }
    }


@router.post("/stake/sync")
async def sync_stake_addresses(address: str, label_prefix: str = "Discovered", user_id: int = Depends(verify_session)):
    """
    Add all missing addresses from a stake key to tracking.

    Discovers addresses on-chain and adds any not already tracked.
    """
    from database import save_wallet, get_wallet_by_address

    # Get discovery info first
    discovery = await discover_stake_addresses(address)

    if not discovery.get('missing'):
        return {
            'address': address,
            'added': 0,
            'message': 'All addresses under this stake key are already tracked'
        }

    added = []
    for missing_addr in discovery['missing']:
        addr = missing_addr['address']
        label = f"{label_prefix}: {addr[-8:]}"

        await save_wallet(addr, 'cardano', label)

        # Refresh balance immediately
        wallet = await get_wallet_by_address(addr)
        if wallet:
            from routers.wallets import _refresh_wallet_balance
            await _refresh_wallet_balance(wallet)
            added.append({
                'address': addr,
                'label': label,
                'ada_balance': missing_addr['ada_balance']
            })

    return {
        'stake_address': discovery['stake_address'],
        'added': len(added),
        'total_ada_added': sum(a['ada_balance'] for a in added),
        'addresses': added
    }


@router.get("/defi/analysis/{address}")
async def analyze_defi_locked_ada(address: str, user_id: int = Depends(verify_session)):
    """
    Deep analysis of DeFi-locked ADA for a given address.

    Checks all known DeFi protocols for positions that may explain
    differences between local tracking and TapTools/on-chain totals.
    """
    from services.defi import defi_service

    # Get stake address to check full stake key
    stake_address = await cardano_service.get_stake_address(address)

    # Get basic wallet info
    addr_info = await cardano_service.get_address_info(address)
    local_ada = float(addr_info.get('balance_ada', 0)) if addr_info else 0

    # Get TapTools data for comparison
    taptools_data = await taptools_wallet_service.get_wallet_portfolio(address)

    # Get all DeFi positions
    defi_analysis = await defi_service.analyze_wallet_defi(address)

    # Get staking positions across protocols
    staking_positions = await defi_service.get_all_staking_positions(address)

    # Check for LP positions with significant ADA value
    lp_ada_value = 0
    lp_positions = []

    if defi_analysis:
        for pos in defi_analysis.get('defi_positions', []):
            if pos.get('type') == 'lp':
                # LP tokens represent locked value
                lp_positions.append({
                    'protocol': pos.get('protocol'),
                    'token': pos.get('asset_name'),
                    'quantity': pos.get('quantity'),
                    'note': 'LP tokens represent locked liquidity'
                })

    # Get Indigo CDP/collateral positions
    indigo_staking = await defi_service.get_indigo_staking(address)

    # Get Liqwid supply positions (qTokens represent supplied assets)
    liqwid_staking = await defi_service.get_liqwid_staking(address)

    # Build summary
    locked_positions = []

    if staking_positions.get('protocols'):
        for protocol, data in staking_positions['protocols'].items():
            for staked in data.get('staked', []):
                locked_positions.append({
                    'protocol': protocol,
                    'type': 'staking',
                    'token': staked['token'],
                    'amount': staked['amount'],
                    'note': f"Staked {staked['token']} in {protocol}"
                })

    if lp_positions:
        locked_positions.extend([{**p, 'type': 'liquidity_pool'} for p in lp_positions])

    # Calculate potential locked ADA
    taptools_ada = taptools_data['ada_balance'] if taptools_data else 0
    difference = taptools_ada - local_ada

    return {
        'address': address,
        'stake_address': stake_address,
        'local_ada_balance': local_ada,
        'taptools_ada_balance': taptools_ada,
        'difference_ada': round(difference, 6),
        'difference_pct': round((difference / local_ada * 100), 2) if local_ada > 0 else 0,
        'defi_summary': {
            'total_protocols': defi_analysis.get('total_protocols', 0) if defi_analysis else 0,
            'total_positions': defi_analysis.get('total_positions', 0) if defi_analysis else 0,
            'protocols_with_staking': len(staking_positions.get('protocols', {}))
        },
        'locked_positions': locked_positions,
        'lp_positions': lp_positions,
        'staking_protocols': list(staking_positions.get('protocols', {}).keys()),
        'taptools_positions': taptools_data.get('positions', [])[:20] if taptools_data else [],
        'analysis_notes': [
            'TapTools returns full stake key balance including DeFi-locked assets',
            'LP tokens represent locked liquidity that may contain ADA',
            'Staked tokens are locked in protocol contracts',
            'Check individual protocol apps for exact ADA value in positions'
        ]
    }


@router.get("/taptools/summary")
async def get_taptools_summary(user_id: int = Depends(verify_session)):
    """
    Get TapTools portfolio summary for all Cardano wallets.

    Groups wallets by stake key and shows aggregate local vs TapTools balances.
    TapTools returns stake key totals, so we aggregate our local balances similarly.
    """
    wallets = await get_all_wallets(user_id=user_id)
    cardano_wallets = [w for w in wallets if w['blockchain'] == 'cardano']

    if not taptools_wallet_service.is_configured():
        return {
            'configured': False,
            'message': 'TapTools API key not configured'
        }

    # Group wallets by stake key suffix (the staking credential portion)
    # In bech32 Cardano addresses, the stake key is encoded in the latter part
    # Addresses sharing stake key: c4uvfq4rzx55e747eqtqewnue7jcrjp3qagpaeee58cqs
    stake_key_groups = {}
    for wallet in cardano_wallets:
        address = wallet['address']
        # Look for common stake key pattern - take chars from position 55 onwards
        # but exclude the final checksum/suffix (last 8 chars vary)
        if len(address) > 100:  # Standard base address
            # The stake key is roughly the last 54 chars before final 8
            stake_suffix = address[55:-8]  # Start after payment part
        else:
            stake_suffix = address  # Use full address for non-standard

        if stake_suffix not in stake_key_groups:
            stake_key_groups[stake_suffix] = {
                'wallets': [],
                'local_ada': 0,
                'taptools_ada': None,
                'labels': []
            }

        stake_key_groups[stake_suffix]['wallets'].append(wallet)
        if wallet.get('label'):
            stake_key_groups[stake_suffix]['labels'].append(wallet['label'])

        # Sum local balance
        balance_info = await get_wallet_balance(wallet['id'])
        local_ada = float(balance_info['amount']) if balance_info else 0
        stake_key_groups[stake_suffix]['local_ada'] += local_ada

    # Query TapTools once per stake key
    results = []
    total_local_ada = 0
    total_taptools_ada = 0

    for stake_suffix, group in stake_key_groups.items():
        # Use first wallet address to query TapTools
        first_address = group['wallets'][0]['address']

        tt_data = await taptools_wallet_service.get_stake_key_balance(first_address)
        if tt_data:
            group['taptools_ada'] = tt_data['total_ada']
            group['tokens'] = tt_data['total_tokens']
            group['nfts'] = tt_data['total_nfts']
            total_taptools_ada += tt_data['total_ada']

        total_local_ada += group['local_ada']

        # Build display label
        labels = group['labels'][:3]
        label_str = ', '.join(labels) if labels else 'Unnamed'
        if len(group['wallets']) > 1:
            label_str += f" (+{len(group['wallets'])-1} more)"

        difference = (group['taptools_ada'] or 0) - group['local_ada']

        results.append({
            'stake_key': stake_suffix[:12] + '...' + stake_suffix[-8:] if len(stake_suffix) > 25 else stake_suffix,
            'addresses': len(group['wallets']),
            'labels': label_str,
            'local_ada': round(group['local_ada'], 2),
            'taptools_ada': round(group['taptools_ada'], 2) if group['taptools_ada'] else None,
            'difference': round(difference, 2),
            'tokens': group.get('tokens', 0),
            'nfts': group.get('nfts', 0)
        })

    # Sort by TapTools balance descending
    results.sort(key=lambda x: x['taptools_ada'] or 0, reverse=True)

    return {
        'configured': True,
        'unique_stake_keys': len(results),
        'total_addresses': len(cardano_wallets),
        'total_local_ada': round(total_local_ada, 2),
        'total_taptools_ada': round(total_taptools_ada, 2),
        'difference': round(total_taptools_ada - total_local_ada, 2),
        'difference_pct': round((total_taptools_ada - total_local_ada) / total_local_ada * 100, 1) if total_local_ada > 0 else 0,
        'stake_keys': results
    }


@router.get("/analytics")
async def get_portfolio_analytics(user_id: int = Depends(verify_session)):
    """
    Get portfolio analytics for coin allocation and category allocation charts.

    Returns:
        dict with coin_allocation and category_allocation data, cached for 1 hour
    """
    from datetime import datetime, timedelta

    # Check cache (1 hour TTL)
    cache_key = f"portfolio_analytics_{user_id}"
    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        return cached

    # Get all portfolio data
    summary = await get_portfolio_summary(user_id=user_id)
    assets_data = await get_all_native_assets(user_id=user_id)
    all_prices = await pricing_service.get_all_tracked_prices()

    # Token category mapping
    TOKEN_CATEGORIES = {
        # Layer 1
        'ADA': 'Layer 1 (L1)', 'BTC': 'Layer 1 (L1)', 'ETH': 'Layer 1 (L1)',
        'SOL': 'Layer 1 (L1)', 'POL': 'Layer 1 (L1)', 'MATIC': 'Layer 1 (L1)',

        # DeFi
        'INDY': 'Decentralized Finance (DeFi)', 'SUNDAE': 'Decentralized Finance (DeFi)',
        'MIN': 'Decentralized Finance (DeFi)', 'WMT': 'Decentralized Finance (DeFi)',
        'MILK': 'Decentralized Finance (DeFi)', 'LQ': 'Decentralized Finance (DeFi)',

        # Cardano Ecosystem
        'SNEK': 'Cardano Ecosystem', 'HOSKY': 'Cardano Ecosystem',
        'IAG': 'Cardano Ecosystem', 'NMKR': 'Cardano Ecosystem',
        'BOOK': 'Cardano Ecosystem', 'HUNTER': 'Cardano Ecosystem',

        # Infrastructure/Oracles
        'CHARLI': 'Infrastructure', 'ORCFAX': 'Infrastructure',

        # Stablecoins
        'USDC': 'Stablecoins', 'USDT': 'Stablecoins', 'DJED': 'Stablecoins',
        'iUSD': 'Stablecoins',

        # Meme
        'NIGHT': 'Meme', 'STRIKE': 'Meme',

        # Gaming/Metaverse
        'HUNT': 'Gaming', 'DUST': 'Gaming',
    }

    # Calculate coin allocation
    coin_allocations = []
    total_value = 0

    # Add native coins
    for blockchain in ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon']:
        chain_data = summary.get(blockchain, {})
        if blockchain == 'cardano':
            qty = chain_data.get('total_ada', 0)
            symbol = 'ADA'
        elif blockchain == 'bitcoin':
            qty = chain_data.get('total_btc', 0)
            symbol = 'BTC'
        elif blockchain == 'ethereum':
            qty = chain_data.get('total_eth', 0)
            symbol = 'ETH'
        elif blockchain == 'solana':
            qty = chain_data.get('total_sol', 0)
            symbol = 'SOL'
        elif blockchain == 'polygon':
            qty = chain_data.get('total_matic', 0)
            symbol = 'POL'
        else:
            continue

        price = all_prices.get(symbol, {}).get('usd', 0)
        value_usd = qty * price

        if value_usd > 0:
            coin_allocations.append({
                'symbol': symbol,
                'name': symbol,
                'quantity': qty,
                'value_usd': value_usd,
                'category': TOKEN_CATEGORIES.get(symbol, 'Other'),
                'logo_url': logokit_service.get_crypto_logo_url(symbol, size=64)
            })
            total_value += value_usd

    # Add tokens
    for asset in assets_data.get('assets', []):
        value_usd = asset.get('value_usd') or 0
        if value_usd > 0:
            symbol = asset.get('ticker') or asset.get('asset_name', '')[:10]
            coin_allocations.append({
                'symbol': symbol,
                'name': asset.get('asset_name', symbol),
                'quantity': asset.get('total_quantity', 0),
                'value_usd': value_usd,
                'category': TOKEN_CATEGORIES.get(symbol, 'Other'),
                'logo_url': logokit_service.get_crypto_logo_url(symbol, size=64)
            })
            total_value += value_usd

    # Calculate percentages for coin allocation
    for coin in coin_allocations:
        coin['percentage'] = (coin['value_usd'] / total_value * 100) if total_value > 0 else 0

    # Sort by value descending
    coin_allocations.sort(key=lambda x: x['value_usd'], reverse=True)

    # Calculate category allocation
    category_totals = {}
    for coin in coin_allocations:
        category = coin['category']
        if category not in category_totals:
            category_totals[category] = {
                'category': category,
                'value_usd': 0,
                'tokens': []
            }
        category_totals[category]['value_usd'] += coin['value_usd']
        category_totals[category]['tokens'].append({
            'symbol': coin['symbol'],
            'value_usd': coin['value_usd']
        })

    # Calculate category percentages
    category_allocations = list(category_totals.values())
    for category in category_allocations:
        category['percentage'] = (category['value_usd'] / total_value * 100) if total_value > 0 else 0
        category['token_count'] = len(category['tokens'])

    # Sort by value descending
    category_allocations.sort(key=lambda x: x['value_usd'], reverse=True)

    result = {
        'total_value_usd': total_value,
        'coin_allocation': coin_allocations,
        'category_allocation': category_allocations,
        'generated_at': datetime.now().isoformat()
    }

    # Cache for 1 hour (3600 seconds)
    await set_cache(cache_key, result, ttl_seconds=3600, user_id=user_id)

    return result


@router.get("/assets/{blockchain}")
async def get_blockchain_asset_breakdown(
    blockchain: str,
    user_id: int = Depends(verify_session)
):
    """Get asset breakdown for a specific blockchain for doughnut chart display."""
    try:
        # Validate blockchain
        valid_chains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base']
        if blockchain not in valid_chains:
            raise HTTPException(400, f"Invalid blockchain: {blockchain}")

        # Check cache first (5 minute TTL)
        cache_key = f"asset_breakdown_{blockchain}_{user_id}"
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return cached

        # Get portfolio summary for native coin balance (uses cache)
        summary = await get_portfolio_summary(user_id=user_id)
        chain_data = summary.get(blockchain, {})

        # Get all assets filtered by blockchain (uses cache)
        assets_data = await get_all_native_assets(user_id=user_id)
        chain_assets = [a for a in assets_data['assets'] if a['blockchain'] == blockchain]

        # Calculate native coin value
        native_symbols = {
            'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH',
            'solana': 'SOL', 'polygon': 'POL', 'base': 'ETH'
        }
        native_keys = {
            'cardano': 'total_ada', 'bitcoin': 'total_btc', 'ethereum': 'total_eth',
            'solana': 'total_sol', 'polygon': 'total_matic', 'base': 'total_eth'
        }

        native_symbol = native_symbols[blockchain]
        native_qty = chain_data.get(native_keys[blockchain], 0)

        # Get price from cache if possible
        all_prices = await pricing_service.get_all_tracked_prices()
        native_price = all_prices.get(native_symbol, {}).get('usd', 0)
        native_value = native_qty * native_price if native_price else 0

        # Get NFT value for this chain (placeholder for now)
        nft_value = 0
        nft_count = 0
        # TODO: Query NFT service for this blockchain

        # Calculate total value from tokens
        tokens_value = sum(a.get('value_usd', 0) or 0 for a in chain_assets)

        # Total value across all asset types
        total_value = native_value + tokens_value + nft_value

        # Calculate percentages
        native_pct = (native_value / total_value * 100) if total_value > 0 else 0
        nft_pct = (nft_value / total_value * 100) if total_value > 0 else 0

        # Build token list
        token_list = []
        for a in chain_assets:
            asset_value = a.get('value_usd', 0) or 0
            if asset_value > 0:  # Only include tokens with value
                token_symbol = a.get('ticker') or (a.get('asset_name', '')[:10] if a.get('asset_name') else 'Unknown')
                token_list.append({
                    'symbol': token_symbol,
                    'name': a.get('asset_name', 'Unknown'),
                    'quantity': a.get('total_quantity', 0),
                    'value_usd': asset_value,
                    'percentage': (asset_value / total_value * 100) if total_value > 0 else 0,
                    'logo_url': logokit_service.get_crypto_logo_url(token_symbol, size=64)
                })

        # Sort tokens by value descending
        token_list.sort(key=lambda x: x['value_usd'], reverse=True)

        # Build response
        result = {
            'blockchain': blockchain,
            'symbol': native_symbol,
            'logo_url': logokit_service.get_blockchain_logo_url(blockchain, size=128),
            'total_value_usd': total_value,
            'native_coin': {
                'symbol': native_symbol,
                'quantity': native_qty,
                'value_usd': native_value,
                'percentage': native_pct,
                'logo_url': logokit_service.get_crypto_logo_url(native_symbol, size=64)
            },
            'tokens': token_list,
            'nfts': {
                'count': nft_count,
                'value_usd': nft_value,
                'percentage': nft_pct
            }
        }

        # Cache for 5 minutes (300 seconds)
        await set_cache(cache_key, result, ttl_seconds=300, user_id=user_id)

        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[ERROR] Asset breakdown for {blockchain} (user {user_id}): {str(e)}")
        logger.error(traceback.format_exc())
        # Return more detailed error message
        error_detail = f"{type(e).__name__}: {str(e)}"
        raise HTTPException(500, detail=error_detail)


@router.get("/charts/blockchain/{blockchain}")
async def get_blockchain_price_chart(
    blockchain: str,
    timeframe: str = Query('1D', description="1H, 4H, 1D, 7D, 3M, 1Y"),
    user_id: int = Depends(verify_session)
):
    """
    Get historical price data for a blockchain's native coin.

    Timeframes:
        - 1H: 1 hour (5-minute intervals)
        - 4H: 4 hours (5-minute intervals)
        - 1D: 1 day (5-minute intervals) (default)
        - 7D: 7 days (hourly intervals)
        - 3M: 90 days (hourly intervals)
        - 1Y: 365 days (daily intervals)

    Returns data in TradingView lightweight-charts format:
        {
            'blockchain': 'cardano',
            'symbol': 'ADA',
            'timeframe': '1D',
            'data': [
                { 'time': '2024-01-01T12:00:00', 'value': 0.5 },
                { 'time': '2024-01-01T12:05:00', 'value': 0.52 }
            ],
            'current_price': 0.55,
            'change_24h': 2.34,
            'data_points': 288
        }
    """
    try:
        # Check cache first (1 hour TTL for historical data)
        # Cache key versioned to bust old ISO string format (v2 = Unix timestamps)
        cache_key = f"price_chart_v2_{blockchain}_{timeframe}_{user_id}"
        cached = await get_cache(cache_key, user_id=user_id)
        if cached:
            return cached

        # Map blockchain to symbol
        blockchain_symbols = {
            'cardano': 'ADA',
            'bitcoin': 'BTC',
            'ethereum': 'ETH',
            'solana': 'SOL',
            'polygon': 'MATIC',
            'base': 'ETH'  # Base uses ETH
        }

        symbol = blockchain_symbols.get(blockchain.lower())
        if not symbol:
            raise HTTPException(400, f"Unsupported blockchain: {blockchain}")

        # Map timeframe to days (CoinGecko API parameter)
        # 1H, 4H, 1D all use days=1 (5-minute intervals)
        # 7D uses days=7 (hourly intervals)
        # 3M uses days=90 (hourly intervals)
        # 1Y uses days=365 (daily intervals)
        timeframe_days = {
            '1H': 1,
            '4H': 1,
            '1D': 1,
            '7D': 7,
            '3M': 90,
            '1Y': 365
        }

        days = timeframe_days.get(timeframe.upper(), 1)

        # Fetch historical prices
        historical = await pricing_service.get_historical_prices([symbol], days=days)

        if symbol not in historical or not historical[symbol]:
            raise HTTPException(404, f"No historical data available for {symbol}")

        # Filter data based on timeframe (for sub-daily intervals)
        chart_data_raw = historical[symbol]

        if timeframe.upper() == '1H':
            # Last 1 hour: 12 data points (5-minute intervals)
            chart_data_raw = chart_data_raw[-12:] if len(chart_data_raw) >= 12 else chart_data_raw
        elif timeframe.upper() == '4H':
            # Last 4 hours: 48 data points (5-minute intervals)
            chart_data_raw = chart_data_raw[-48:] if len(chart_data_raw) >= 48 else chart_data_raw

        # Get current price and 24h change (use get_all_tracked_prices for metadata)
        all_prices = await pricing_service.get_all_tracked_prices()
        price_data = all_prices.get(symbol, {})

        # Transform data for lightweight-charts
        chart_data = [
            {
                'time': point['time'],  # Use 'time' field which has ISO format
                'value': point['price']
            }
            for point in chart_data_raw
        ]

        result = {
            'blockchain': blockchain,
            'symbol': symbol,
            'timeframe': timeframe.upper(),
            'data': chart_data,
            'current_price': price_data.get('usd', 0),
            'change_24h': price_data.get('usd_1h_change', 0),
            'data_points': len(chart_data)
        }

        # Cache for 1 hour (3600 seconds)
        await set_cache(cache_key, result, ttl_seconds=3600, user_id=user_id)

        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error fetching price chart for {blockchain}: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Error fetching price chart: {str(e)}")
