from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_all_wallets, get_wallet_balance, get_wallet_assets,
    get_cache, set_cache, clear_cache,
    get_all_token_metadata, toggle_token_tracking, get_tracked_tokens,
    save_token_metadata, update_native_asset_decimals
)
from services.cardano import cardano_service
from services.pricing import pricing_service
from services.defi import DEFI_PROTOCOLS
from services.taptools import taptools_wallet_service
from services.logokit_service import logokit_service
from services.nmkr_service import nmkr_service
from services.demo_wallet_service import demo_wallet_service
from auth_utils import verify_session
from database import get_username_by_user_id
from middleware.demo_mode import is_demo_user


class TokenTrackRequest(BaseModel):
    """Request to toggle token tracking."""
    asset_id: str
    track: bool
    ticker: str = None
    decimals: int = None

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)

# Cache TTL in seconds (7 days for portfolio so it persists between sessions, only cleared on manual refresh)
from config import CACHE_TTL_PERSISTENT, CACHE_TTL_WARM, CACHE_TTL_HOT
PORTFOLIO_CACHE_TTL = CACHE_TTL_PERSISTENT  # 7 days
STAKE_CACHE_TTL = CACHE_TTL_WARM  # 1 hour for stake address lookups

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
    if blockchain == 'cardano' and await taptools_wallet_service.is_configured() and assets:
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
    # Demo mode: return fake portfolio data
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await _get_demo_portfolio_summary()

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
        },
        'algorand': {
            'wallet_count': 0,
            'total_algo': 0.0,
            'asset_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'bsc': {
            'wallet_count': 0,
            'total_bnb': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'arbitrum': {
            'wallet_count': 0,
            'total_eth': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'avalanche': {
            'wallet_count': 0,
            'total_avax': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'tron': {
            'wallet_count': 0,
            'total_trx': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'xrp': {
            'wallet_count': 0,
            'total_xrp': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'hedera': {
            'wallet_count': 0,
            'total_hbar': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'multiversx': {
            'wallet_count': 0,
            'total_egld': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'sui': {
            'wallet_count': 0,
            'total_sui': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'aptos': {
            'wallet_count': 0,
            'total_apt': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'filecoin': {
            'wallet_count': 0,
            'total_fil': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'litecoin': {
            'wallet_count': 0,
            'total_ltc': 0.0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'dogecoin': {
            'wallet_count': 0,
            'total_doge': 0.0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'zcash': {
            'wallet_count': 0,
            'total_zec': 0.0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'tezos': {
            'wallet_count': 0,
            'total_xtz': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'stacks': {
            'wallet_count': 0,
            'total_stx': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'vechain': {
            'wallet_count': 0,
            'total_vet': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'cosmos': {
            'wallet_count': 0,
            'total_atom': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'near': {
            'wallet_count': 0,
            'total_near': 0.0,
            'token_count': 0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        },
        'icp': {
            'wallet_count': 0,
            'total_icp': 0.0,
            'native_assets_value_usd': 0.0,
            'wallets': []
        }
    }

    # Track stake address groupings for Cardano
    stake_groups = {}  # stake_address -> list of wallets

    # Fetch all wallet data in parallel (balances, assets, native values, stake addresses)
    async def fetch_wallet_data(wallet):
        """Fetch balance, assets, native value, and stake address for a single wallet."""
        blockchain = wallet['blockchain']
        wallet_id = wallet['id']

        # Build parallel tasks for this wallet
        tasks = [
            get_wallet_balance(wallet_id),
            get_wallet_assets(wallet_id),
            calculate_wallet_native_assets_value(wallet_id, blockchain, user_id),
        ]
        # For Cardano wallets, also fetch stake address in parallel
        if blockchain == 'cardano':
            tasks.append(cardano_service.get_stake_address(wallet['address']))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        balance_info = results[0] if not isinstance(results[0], Exception) else None
        assets = results[1] if not isinstance(results[1], Exception) else []
        native_assets_value_usd = results[2] if not isinstance(results[2], Exception) else 0.0
        stake_address = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else None

        return {
            'wallet': wallet,
            'blockchain': blockchain,
            'balance_info': balance_info,
            'assets': assets,
            'native_assets_value_usd': native_assets_value_usd,
            'stake_address': stake_address,
        }

    # Fetch all wallet data concurrently
    wallet_data_list = await asyncio.gather(
        *[fetch_wallet_data(w) for w in wallets],
        return_exceptions=True
    )

    # Aggregate results sequentially (fast in-memory operations)
    for wallet_data in wallet_data_list:
        if isinstance(wallet_data, Exception):
            continue  # Skip wallets that failed entirely

        wallet = wallet_data['wallet']
        blockchain = wallet_data['blockchain']
        balance_info = wallet_data['balance_info']
        assets = wallet_data['assets']
        native_assets_value_usd = wallet_data['native_assets_value_usd']
        stake_address = wallet_data['stake_address']

        balance = float(balance_info['amount']) if balance_info else 0.0

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

        elif blockchain == 'algorand':
            summary['algorand']['wallet_count'] += 1
            summary['algorand']['total_algo'] += balance
            summary['algorand']['asset_count'] += len(assets)
            summary['algorand']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['asset_count'] = len(assets)
            summary['algorand']['wallets'].append(wallet_summary)

        elif blockchain == 'bsc':
            balance_bnb = float(balance_info.get('amount', 0)) if balance_info else 0.0
            summary['bsc']['wallet_count'] += 1
            summary['bsc']['total_bnb'] += balance_bnb
            summary['bsc']['token_count'] += len(assets)
            summary['bsc']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['bsc']['wallets'].append(wallet_summary)

        elif blockchain == 'arbitrum':
            balance_eth = float(balance_info.get('amount', 0)) if balance_info else 0.0
            summary['arbitrum']['wallet_count'] += 1
            summary['arbitrum']['total_eth'] += balance_eth
            summary['arbitrum']['token_count'] += len(assets)
            summary['arbitrum']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['arbitrum']['wallets'].append(wallet_summary)

        elif blockchain == 'avalanche':
            balance_avax = float(balance_info.get('amount', 0)) if balance_info else 0.0
            summary['avalanche']['wallet_count'] += 1
            summary['avalanche']['total_avax'] += balance_avax
            summary['avalanche']['token_count'] += len(assets)
            summary['avalanche']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['avalanche']['wallets'].append(wallet_summary)

        elif blockchain == 'tron':
            balance_trx = float(balance_info.get('amount', 0)) if balance_info else 0.0
            summary['tron']['wallet_count'] += 1
            summary['tron']['total_trx'] += balance_trx
            summary['tron']['token_count'] += len(assets)
            summary['tron']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['tron']['wallets'].append(wallet_summary)

        elif blockchain == 'xrp':
            summary['xrp']['wallet_count'] += 1
            summary['xrp']['total_xrp'] += balance
            summary['xrp']['token_count'] += len(assets)
            summary['xrp']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['xrp']['wallets'].append(wallet_summary)

        elif blockchain == 'hedera':
            summary['hedera']['wallet_count'] += 1
            summary['hedera']['total_hbar'] += balance
            summary['hedera']['token_count'] += len(assets)
            summary['hedera']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['hedera']['wallets'].append(wallet_summary)

        elif blockchain == 'multiversx':
            summary['multiversx']['wallet_count'] += 1
            summary['multiversx']['total_egld'] += balance
            summary['multiversx']['token_count'] += len(assets)
            summary['multiversx']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['multiversx']['wallets'].append(wallet_summary)

        elif blockchain == 'sui':
            summary['sui']['wallet_count'] += 1
            summary['sui']['total_sui'] += balance
            summary['sui']['token_count'] += len(assets)
            summary['sui']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['sui']['wallets'].append(wallet_summary)

        elif blockchain == 'aptos':
            summary['aptos']['wallet_count'] += 1
            summary['aptos']['total_apt'] += balance
            summary['aptos']['token_count'] += len(assets)
            summary['aptos']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['aptos']['wallets'].append(wallet_summary)

        elif blockchain == 'filecoin':
            summary['filecoin']['wallet_count'] += 1
            summary['filecoin']['total_fil'] += balance
            summary['filecoin']['native_assets_value_usd'] += native_assets_value_usd
            summary['filecoin']['wallets'].append(wallet_summary)

        elif blockchain == 'litecoin':
            summary['litecoin']['wallet_count'] += 1
            summary['litecoin']['total_ltc'] += balance
            summary['litecoin']['native_assets_value_usd'] += native_assets_value_usd
            summary['litecoin']['wallets'].append(wallet_summary)

        elif blockchain == 'dogecoin':
            summary['dogecoin']['wallet_count'] += 1
            summary['dogecoin']['total_doge'] += balance
            summary['dogecoin']['native_assets_value_usd'] += native_assets_value_usd
            summary['dogecoin']['wallets'].append(wallet_summary)

        elif blockchain == 'zcash':
            summary['zcash']['wallet_count'] += 1
            summary['zcash']['total_zec'] += balance
            summary['zcash']['native_assets_value_usd'] += native_assets_value_usd
            summary['zcash']['wallets'].append(wallet_summary)

        elif blockchain == 'tezos':
            summary['tezos']['wallet_count'] += 1
            summary['tezos']['total_xtz'] += balance
            summary['tezos']['token_count'] += len(assets)
            summary['tezos']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['tezos']['wallets'].append(wallet_summary)

        elif blockchain == 'stacks':
            summary['stacks']['wallet_count'] += 1
            summary['stacks']['total_stx'] += balance
            summary['stacks']['token_count'] += len(assets)
            summary['stacks']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['stacks']['wallets'].append(wallet_summary)

        elif blockchain == 'vechain':
            summary['vechain']['wallet_count'] += 1
            summary['vechain']['total_vet'] += balance
            summary['vechain']['token_count'] += len(assets)
            summary['vechain']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['vechain']['wallets'].append(wallet_summary)

        elif blockchain == 'cosmos':
            summary['cosmos']['wallet_count'] += 1
            summary['cosmos']['total_atom'] += balance
            summary['cosmos']['token_count'] += len(assets)
            summary['cosmos']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['cosmos']['wallets'].append(wallet_summary)

        elif blockchain == 'near':
            summary['near']['wallet_count'] += 1
            summary['near']['total_near'] += balance
            summary['near']['token_count'] += len(assets)
            summary['near']['native_assets_value_usd'] += native_assets_value_usd
            wallet_summary['token_count'] = len(assets)
            summary['near']['wallets'].append(wallet_summary)

        elif blockchain == 'icp':
            summary['icp']['wallet_count'] += 1
            summary['icp']['total_icp'] += balance
            summary['icp']['native_assets_value_usd'] += native_assets_value_usd
            summary['icp']['wallets'].append(wallet_summary)

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
    summary['algorand']['total_algo'] = round(summary['algorand']['total_algo'], 6)
    summary['bsc']['total_bnb'] = round(summary['bsc']['total_bnb'], 8)
    summary['arbitrum']['total_eth'] = round(summary['arbitrum']['total_eth'], 8)
    summary['avalanche']['total_avax'] = round(summary['avalanche']['total_avax'], 8)
    summary['tron']['total_trx'] = round(summary['tron']['total_trx'], 6)
    summary['xrp']['total_xrp'] = round(summary['xrp']['total_xrp'], 6)
    summary['hedera']['total_hbar'] = round(summary['hedera']['total_hbar'], 8)
    summary['multiversx']['total_egld'] = round(summary['multiversx']['total_egld'], 8)
    summary['sui']['total_sui'] = round(summary['sui']['total_sui'], 9)
    summary['aptos']['total_apt'] = round(summary['aptos']['total_apt'], 8)
    summary['filecoin']['total_fil'] = round(summary['filecoin']['total_fil'], 8)
    summary['litecoin']['total_ltc'] = round(summary['litecoin']['total_ltc'], 8)
    summary['dogecoin']['total_doge'] = round(summary['dogecoin']['total_doge'], 8)
    summary['zcash']['total_zec'] = round(summary['zcash']['total_zec'], 8)
    summary['tezos']['total_xtz'] = round(summary['tezos']['total_xtz'], 6)
    summary['stacks']['total_stx'] = round(summary['stacks']['total_stx'], 6)
    summary['vechain']['total_vet'] = round(summary['vechain']['total_vet'], 8)
    summary['cosmos']['total_atom'] = round(summary['cosmos']['total_atom'], 6)
    summary['near']['total_near'] = round(summary['near']['total_near'], 8)
    summary['icp']['total_icp'] = round(summary['icp']['total_icp'], 8)

    # Cache the result with timestamp
    from datetime import datetime
    summary['from_cache'] = False
    summary['last_updated'] = datetime.now().isoformat()
    await set_cache(cache_key, summary, PORTFOLIO_CACHE_TTL, user_id=user_id)

    return summary

# Cache TTL for native assets (7 days - tokens don't change often, only cleared on manual refresh)
NATIVE_ASSETS_CACHE_TTL = CACHE_TTL_PERSISTENT  # 7 days

@router.get("/assets")
async def get_all_native_assets(user_id: int = Depends(verify_session), refresh: bool = Query(False, description="Force refresh cache")):
    """
    Get all native assets across all wallets with prices.
    Returns aggregated quantities, proper decimal conversion, and USD values.
    Uses caching for faster loads - pass refresh=true to force update.
    """
    # Demo mode: return fake token data
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await _get_demo_native_assets()

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

            # Generate logo URL with multiple fallback strategies
            logo_url = None
            blockchain = asset.get('blockchain', 'cardano')

            # For Cardano native assets with policy_id, use comprehensive fallback chain
            if blockchain == 'cardano' and policy_id and asset_id:
                # Extract hex asset name from asset_id (format: policy_id + asset_name_hex)
                asset_name_hex = asset_id[len(policy_id):] if len(asset_id) > len(policy_id) else None

                if asset_name_hex:
                    # Try NMKR → Cardano Token Registry → Blockfrost → LogoKit
                    logo_url = await nmkr_service.get_token_logo_with_fallbacks(
                        policy_id,
                        asset_name_hex,
                        ticker=ticker,
                        user_id=user_id
                    )

            # Non-Cardano fallback to LogoKit
            if not logo_url:
                logo_symbol = ticker if ticker else asset['asset_name'][:10] if asset['asset_name'] else 'UNKNOWN'
                logo_url = logokit_service.get_crypto_logo_url(logo_symbol, size=64)

            asset_totals[asset_id] = {
                'asset_id': asset_id,
                'policy_id': policy_id,
                'asset_name': asset['asset_name'],
                'ticker': ticker,
                'decimals': decimals,
                'tracked': is_tracked,
                'blockchain': blockchain,
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
    range: str = Query("7d", description="Time range: 1d (1 day hourly), 7d (7 days), 4w (4 weeks), 3m (3 months)")
):
    """
    Get portfolio value history for charting (V2 — reads from wallet_daily_balances).

    Returns daily data points with breakdown by component.
    """
    from datetime import datetime, timedelta
    from database import get_unified_daily_totals

    # Demo mode: return pre-generated fake history directly
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await _get_demo_portfolio_history(range)

    # Map range to days
    days_map = {"1d": 1, "7d": 7, "4w": 28, "3m": 90}
    days = days_map.get(range, 7)
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    rows = await get_unified_daily_totals(user_id, start_date=start_date)

    history = []
    for row in rows:
        on_chain = row.get('on_chain_value', 0) or 0
        exchange = row.get('exchange_value', 0) or 0
        staking = row.get('staking_value', 0) or 0
        defi = row.get('defi_value', 0) or 0
        nfts = row.get('nft_value', 0) or 0
        total = row.get('total_value', 0) or 0

        history.append({
            "date": row['date'],
            "value": round(total, 2),
            "breakdown": {
                "wallets": round(on_chain, 2),
                "exchange": round(exchange, 2),
                "staking": round(staking, 2),
                "defi": round(defi, 2),
                "nfts": round(nfts, 2),
                "tracked_tokens": 0,
            }
        })

    latest = rows[-1]['date'] if rows else None

    return {
        "range": range,
        "days": days,
        "data": history,
        "data_points": len(history),
        "latest_snapshot": latest
    }


@router.get("/totals")
async def get_portfolio_totals(user_id: int = Depends(verify_session)):
    """
    Get portfolio value breakdown from wallet_daily_balances (V2).

    Returns component totals (staking, defi, exchange, NFTs) from the latest
    date in wallet_daily_balances without making any external API calls.
    """
    from database import get_unified_daily_totals

    rows = await get_unified_daily_totals(user_id)
    if not rows:
        return {
            "staking_usd": 0, "defi_usd": 0, "exchange_usd": 0,
            "nft_usd": 0, "tracked_tokens_usd": 0, "snapshot_time": None
        }

    latest = rows[-1]  # Most recent date
    return {
        "staking_usd": float(latest.get('staking_value', 0) or 0),
        "defi_usd": float(latest.get('defi_value', 0) or 0),
        "exchange_usd": float(latest.get('exchange_value', 0) or 0),
        "nft_usd": float(latest.get('nft_value', 0) or 0),
        "tracked_tokens_usd": 0,
        "snapshot_time": latest.get('date')
    }


@router.get("/chart/unified")
async def get_unified_chart(
    user_id: int = Depends(verify_session),
    range: str = Query("1w", description="Time range: 24h, 1w, 1m, 3m, 6m, 1y, all"),
    by_chain: bool = Query(False, description="Return per-chain breakdown"),
):
    """
    Unified portfolio chart from wallet_daily_balances (V2 per-wallet architecture).

    Reads exclusively from wallet_daily_balances. Run the migration script
    or POST /portfolio/history/rebuild to populate historical data.
    """
    # Demo mode: return pre-generated fake history
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await _get_demo_unified_chart(range)

    range_to_days = {
        '24h': 1, '1w': 7, '1m': 30, '3m': 90,
        '6m': 180, '1y': 365, 'all': 3650,
    }
    days = range_to_days.get(range, 7)

    # Check cache first
    chain_suffix = '_by_chain' if by_chain else ''
    cache_key = f"unified_chart_{user_id}_{range}{chain_suffix}"
    cached = await get_cache(cache_key, user_id=user_id)
    if cached:
        cached['from_cache'] = True
        return cached

    from datetime import datetime, timedelta
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    if by_chain:
        from database import get_unified_daily_totals_by_chain
        chain_rows = await get_unified_daily_totals_by_chain(user_id, start_date=start_date)

        if not chain_rows:
            return {
                "data": [],
                "chain_list": [],
                "coverage": {"oldest_date": None, "newest_date": None, "total_days": 0}
            }

        # Pivot rows into per-date objects with chain breakdown
        from collections import OrderedDict
        date_map = OrderedDict()
        chain_totals = {}
        for row in chain_rows:
            d = row['date']
            chain = row['chain'] or 'unknown'
            val = row['value_usd'] or 0
            if d not in date_map:
                date_map[d] = {"date": d, "total_value": 0, "chains": {}}
            date_map[d]["chains"][chain] = round(date_map[d]["chains"].get(chain, 0) + val, 2)
            date_map[d]["total_value"] = round(date_map[d]["total_value"] + val, 2)
            chain_totals[chain] = chain_totals.get(chain, 0) + val

        data = list(date_map.values())
        # Sort chains by total value descending
        chain_list = sorted(chain_totals.keys(), key=lambda c: chain_totals[c], reverse=True)

        logger.info(f"Unified chart by_chain: {len(data)} points, {len(chain_list)} chains")
        result = {"data": data, "chain_list": chain_list, "coverage": _compute_chart_coverage(data)}
        await set_cache(cache_key, result, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
        return result

    from database import get_unified_daily_totals
    wdb_rows = await get_unified_daily_totals(user_id, start_date=start_date)

    if not wdb_rows:
        return {
            "data": [],
            "coverage": {"oldest_date": None, "newest_date": None, "total_days": 0}
        }

    data = []
    for row in wdb_rows:
        on_chain = row.get('on_chain_value', 0) or 0
        exchange = row.get('exchange_value', 0) or 0
        staking = row.get('staking_value', 0) or 0
        defi = row.get('defi_value', 0) or 0
        nfts = row.get('nft_value', 0) or 0
        total = row.get('total_value', 0) or 0
        off_chain = exchange + staking + defi + nfts

        data.append({
            "date": row['date'],
            "total_value": round(total, 2),
            "on_chain_value": round(on_chain, 2),
            "off_chain_value": round(off_chain, 2),
            "breakdown": {
                "chains": {},
                "components": {
                    "wallets": round(on_chain, 2),
                    "exchange": round(exchange, 2),
                    "staking": round(staking, 2),
                    "defi": round(defi, 2),
                    "nfts": round(nfts, 2),
                    "tracked_tokens": 0,
                }
            }
        })

    logger.info(f"Unified chart: {len(data)} points from wallet_daily_balances")
    result = {"data": data, "coverage": _compute_chart_coverage(data)}
    await set_cache(cache_key, result, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)
    return result


@router.post("/history/rebuild")
async def rebuild_wallet_history(
    user_id: int = Depends(verify_session),
    nuclear: bool = Query(False, description="Nuclear reset: also clear wallet_sources and re-seed"),
    full_reindex: bool = Query(False, description="Clear engine data (engine_events, engine_tx_raw) for full re-index"),
):
    """
    Clear wallet_daily_balances and rebuild from V2 engine events.

    With nuclear=true: also clears wallet_sources and re-seeds them.
    With full_reindex=true: also clears engine_events and engine_tx_raw for a complete re-index.
    """
    import aiosqlite
    from config import DATABASE_PATH
    from database import seed_wallet_sources
    from engine.materializer import materializer

    cleared = []

    # Invalidate cached chart data for all ranges
    for r in ('24h', '1w', '1m', '3m', '6m', '1y', 'all'):
        await clear_cache(f"unified_chart_{user_id}_{r}", user_id=user_id)
        await clear_cache(f"unified_chart_{user_id}_{r}_by_chain", user_id=user_id)

    # Clear existing balance data for this user
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM wallet_daily_balances WHERE user_id = ?", (user_id,))
        await db.commit()
    cleared.append('wallet_daily_balances')
    logger.info(f"Cleared wallet_daily_balances for user {user_id}")

    if nuclear:
        # Clear wallet_sources and re-seed
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM wallet_sources WHERE user_id = ?", (user_id,))
            await db.commit()
        cleared.append('wallet_sources')
        logger.info(f"Nuclear: cleared wallet_sources for user {user_id}")

    if full_reindex:
        # Clear engine data for full re-index
        try:
            from engine import db as engine_db
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("DELETE FROM engine_events WHERE user_id = ?", (user_id,))
                await db.execute("DELETE FROM engine_tx_index WHERE user_id = ?", (user_id,))
                await db.execute("DELETE FROM engine_account_subjects WHERE user_id = ?", (user_id,))
                await db.commit()
            cleared.extend(['engine_events', 'engine_tx_index', 'engine_account_subjects'])
            logger.info(f"Nuclear: cleared engine data for user {user_id}")
        except Exception as e:
            logger.warning(f"Nuclear: engine data clear failed: {e}")

    # Re-seed sources
    await seed_wallet_sources(user_id)

    # Pre-check: how many engine_events exist?
    engine_event_count = 0
    try:
        from engine import db as engine_db
        engine_event_count = await engine_db.get_event_count(user_id)
        logger.info(f"Rebuild: user {user_id} has {engine_event_count} engine_events")
    except Exception as e:
        logger.warning(f"Rebuild: engine event count check failed: {e}")

    # Materialize on-chain data
    onchain_error = None
    try:
        if engine_event_count > 0:
            # V2 engine has events — materialize from engine_events
            logger.info(f"Rebuild: materializing on-chain from {engine_event_count} engine_events")
            await materializer.materialize_onchain(user_id)
        else:
            # No engine_events — fall back to V1 balance_history table
            logger.info(f"Rebuild: no engine_events, migrating on-chain from V1 balance_history")
            await materializer.materialize_onchain_from_v1_balance_history(user_id)
    except Exception as e:
        onchain_error = str(e)
        logger.error(f"Rebuild: on-chain materialization failed: {e}", exc_info=True)

    # Materialize off-chain from V1 snapshots (legacy data)
    offchain_error = None
    try:
        await materializer.materialize_offchain_from_v1(user_id)
    except Exception as e:
        offchain_error = str(e)
        logger.error(f"Rebuild: off-chain materialization failed: {e}", exc_info=True)

    # Gap-fill
    try:
        await materializer.backfill_offchain_gaps(user_id)
    except Exception as e:
        logger.error(f"Rebuild: gap-fill failed: {e}")

    # Anchor today's values from live data (on-chain + off-chain)
    try:
        from services.offchain_collector import offchain_collector
        await offchain_collector.collect_for_user(user_id)
        logger.info(f"Rebuild: anchored today's live values for user {user_id}")
    except Exception as e:
        logger.warning(f"Rebuild: today's live collection failed: {e}")

    # Count results
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT ws.source_type, COUNT(*) as rows, ROUND(SUM(wdb.value_usd), 2) as total_usd
            FROM wallet_daily_balances wdb
            JOIN wallet_sources ws ON wdb.source_id = ws.id
            WHERE wdb.user_id = ?
            GROUP BY ws.source_type
        """, (user_id,))
        breakdown = {row['source_type']: {'rows': row['rows'], 'total_usd': row['total_usd']}
                     for row in await cursor.fetchall()}

        cursor = await db.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM wallet_daily_balances WHERE user_id = ?",
            (user_id,)
        )
        stats = await cursor.fetchone()

    # Set migration flag
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO migrations (migration_key) VALUES ('v1_to_wallet_daily_balances')"
        )
        await db.commit()

    logger.info(f"Rebuild complete for user {user_id}: {stats[0]} rows, {stats[1]} to {stats[2]}, cleared={cleared}")
    return {
        "status": "rebuilt",
        "nuclear": nuclear,
        "full_reindex": full_reindex,
        "cleared_tables": cleared,
        "engine_events": engine_event_count,
        "total_rows": stats[0],
        "date_range": {"earliest": stats[1], "latest": stats[2]},
        "breakdown": breakdown,
        "errors": {
            "onchain": onchain_error,
            "offchain": offchain_error,
        }
    }


@router.get("/v2/health")
async def get_v2_health(user_id: int = Depends(verify_session)):
    """
    V2 data health check. Returns counts and date ranges for all V2 data tables.
    """
    import aiosqlite
    from config import DATABASE_PATH

    health = {}

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # wallet_sources
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM wallet_sources WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        health['wallet_sources_count'] = row['cnt']

        # wallet_daily_balances
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt, MIN(date) as oldest, MAX(date) as newest FROM wallet_daily_balances WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        health['wallet_daily_balances_count'] = row['cnt']
        health['oldest_date'] = row['oldest']
        health['newest_date'] = row['newest']

    # Engine tables
    try:
        from engine import db as engine_db
        health['engine_events_count'] = await engine_db.get_event_count(user_id)

        subjects = await engine_db.get_account_subjects(user_id)
        health['engine_account_subjects'] = len(subjects)

        # Price history count
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM engine_price_history")
            row = await cursor.fetchone()
            health['engine_price_history_count'] = row[0]
    except Exception as e:
        health['engine_error'] = str(e)

    # Missing dates detection
    if health.get('oldest_date') and health.get('newest_date'):
        from datetime import datetime, timedelta
        oldest = datetime.strptime(health['oldest_date'], '%Y-%m-%d')
        newest = datetime.strptime(health['newest_date'], '%Y-%m-%d')
        expected_days = (newest - oldest).days + 1

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT date) FROM wallet_daily_balances WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            actual_days = row[0]

        health['expected_days'] = expected_days
        health['actual_days'] = actual_days
        health['missing_days'] = expected_days - actual_days

    return health


@router.get("/chart/wallet/{source_id}")
async def get_wallet_chart(
    source_id: int,
    user_id: int = Depends(verify_session),
    range: str = Query("1w", description="Time range: 24h, 1w, 1m, 3m, 6m, 1y, all"),
):
    """Per-wallet balance history drill-down from wallet_daily_balances."""
    from database import get_wallet_source_by_id, get_wallet_source_daily_balances
    from datetime import datetime, timedelta
    import json as json_mod

    source = await get_wallet_source_by_id(source_id)
    if not source or source['user_id'] != user_id:
        raise HTTPException(status_code=404, detail="Wallet source not found")

    range_to_days = {
        '24h': 1, '1w': 7, '1m': 30, '3m': 90,
        '6m': 180, '1y': 365, 'all': 3650,
    }
    days = range_to_days.get(range, 7)
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    rows = await get_wallet_source_daily_balances(source_id, start_date=start_date)

    data = []
    for row in rows:
        meta = {}
        if row.get('metadata'):
            try:
                meta = json_mod.loads(row['metadata'])
            except (ValueError, TypeError):
                pass
        data.append({
            "date": row['date'],
            "value_usd": round(row['value_usd'], 2),
            "metadata": meta,
        })

    return {
        "source": {
            "id": source['id'],
            "source_type": source['source_type'],
            "source_key": source['source_key'],
            "chain": source.get('chain'),
            "label": source.get('label'),
        },
        "data": data,
        "coverage": _compute_chart_coverage([{"date": d["date"]} for d in data]) if data else {
            "oldest_date": None, "newest_date": None, "total_days": 0
        },
    }


@router.get("/wallet-sources")
async def get_wallet_sources_list(
    user_id: int = Depends(verify_session),
):
    """List all wallet sources for the current user."""
    from database import get_wallet_sources
    sources = await get_wallet_sources(user_id)
    return {"sources": sources}


def _compute_chart_coverage(data: list) -> dict:
    """Compute coverage stats from unified chart data."""
    if not data:
        return {"oldest_date": None, "newest_date": None, "total_days": 0}
    dates = [p['date'] for p in data]
    return {"oldest_date": min(dates), "newest_date": max(dates), "total_days": len(dates)}


async def _get_demo_unified_chart(range_str: str) -> dict:
    """Return pre-generated demo data in unified chart format."""
    from services.demo_data_generator import generate_portfolio_history

    range_to_days = {
        '24h': 1, '1w': 7, '1m': 30, '3m': 90,
        '6m': 180, '1y': 365, 'all': 3650,
    }
    days = range_to_days.get(range_str, 7)
    all_history = generate_portfolio_history(max(days, 90))
    filtered = all_history[-days:] if days < len(all_history) else all_history

    data = []
    for s in filtered:
        total = s.get('total_value_usd', 0)
        wallets = s.get('self_custody_value_usd', 0)
        exchange = s.get('exchange_value_usd', 0)
        defi = s.get('defi_value_usd', 0)
        nfts = s.get('nft_value_usd', 0)
        off_chain = exchange + defi + nfts
        data.append({
            "date": s['snapshot_date'],
            "total_value": round(total, 2),
            "on_chain_value": round(wallets, 2),
            "off_chain_value": round(off_chain, 2),
            "breakdown": {
                "chains": s.get('blockchain_breakdown', {}),
                "components": {
                    "wallets": round(wallets, 2),
                    "exchange": round(exchange, 2),
                    "staking": 0,
                    "defi": round(defi, 2),
                    "nfts": round(nfts, 2),
                    "tracked_tokens": 0,
                }
            }
        })

    return {"data": data, "coverage": _compute_chart_coverage(data)}


@router.post("/snapshot")
async def create_portfolio_snapshot(user_id: int = Depends(verify_session), force: bool = Query(False, description="Force create even if exists")):
    """DEPRECATED: V1 snapshot creation. Use off-chain collector (automatic) or POST /portfolio/history/rebuild."""
    return {
        "status": "deprecated",
        "message": "V1 snapshots are deprecated. Off-chain data is collected automatically every 2 hours. Use POST /portfolio/history/rebuild to rebuild historical data."
    }


@router.post("/history/generate")
async def generate_historical_data(user_id: int = Depends(verify_session), days: int = Query(30, description="Number of days of history to generate")):
    """DEPRECATED: V1 history generation. Use POST /portfolio/history/rebuild instead."""
    return {"status": "deprecated", "message": "V1 history generation removed. Use POST /portfolio/history/rebuild to rebuild from V2 engine data."}


@router.get("/history/generate/status")
async def get_generation_status(user_id: int = Depends(verify_session)):
    """DEPRECATED: V1 generation status. Always returns idle."""
    return {"status": "idle", "progress": 0, "step": "V1 generation removed. Use POST /portfolio/history/rebuild."}


@router.post("/history/backfill")
async def backfill_historical_components(user_id: int = Depends(verify_session)):
    """DEPRECATED: V1 component backfill. Use POST /portfolio/history/rebuild instead."""
    return {"status": "deprecated", "message": "V1 component backfill removed. Use POST /portfolio/history/rebuild to rebuild from V2 engine data."}


@router.post("/history/reset")
async def reset_and_regenerate_history(
    user_id: int = Depends(verify_session),
    days: int = Query(90, description="Number of days of history to regenerate")
):
    """DEPRECATED: V1 reset and regenerate. Use POST /portfolio/history/rebuild instead."""
    return {"status": "deprecated", "message": "V1 reset removed. Use POST /portfolio/history/rebuild to rebuild from V2 engine data."}


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

    if not await taptools_wallet_service.is_configured():
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
    # Demo mode: return fake analytics from demo wallet service
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await _get_demo_portfolio_analytics()

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
        'BNB': 'Layer 1 (L1)', 'AVAX': 'Layer 1 (L1)', 'TRX': 'Layer 1 (L1)',
        'XRP': 'Layer 1 (L1)', 'HBAR': 'Layer 1 (L1)', 'EGLD': 'Layer 1 (L1)',
        'SUI': 'Layer 1 (L1)', 'APT': 'Layer 1 (L1)', 'FIL': 'Layer 1 (L1)',
        'LINK': 'Infrastructure',

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

    # Chain symbol to blockchain name mapping
    chain_symbol_map = {'ADA': 'cardano', 'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'POL': 'polygon', 'ALGO': 'algorand', 'BNB': 'bsc', 'AVAX': 'avalanche', 'TRX': 'tron', 'XRP': 'xrp', 'HBAR': 'hedera', 'EGLD': 'multiversx', 'SUI': 'sui', 'APT': 'aptos', 'FIL': 'filecoin', 'LTC': 'litecoin', 'DOGE': 'dogecoin', 'ZEC': 'zcash', 'XTZ': 'tezos', 'STX': 'stacks', 'VET': 'vechain', 'ATOM': 'cosmos', 'NEAR': 'near', 'ICP': 'icp'}

    # Add native coins
    for blockchain in ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base', 'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron', 'xrp', 'hedera', 'multiversx', 'sui', 'aptos', 'filecoin', 'litecoin', 'dogecoin', 'zcash', 'tezos', 'stacks', 'vechain', 'cosmos', 'near', 'icp']:
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
        elif blockchain == 'base':
            qty = chain_data.get('total_eth', 0)
            symbol = 'ETH'
        elif blockchain == 'algorand':
            qty = chain_data.get('total_algo', 0)
            symbol = 'ALGO'
        elif blockchain == 'bsc':
            qty = chain_data.get('total_bnb', 0)
            symbol = 'BNB'
        elif blockchain == 'arbitrum':
            qty = chain_data.get('total_eth', 0)
            symbol = 'ETH'
        elif blockchain == 'avalanche':
            qty = chain_data.get('total_avax', 0)
            symbol = 'AVAX'
        elif blockchain == 'tron':
            qty = chain_data.get('total_trx', 0)
            symbol = 'TRX'
        elif blockchain == 'xrp':
            qty = chain_data.get('total_xrp', 0)
            symbol = 'XRP'
        elif blockchain == 'hedera':
            qty = chain_data.get('total_hbar', 0)
            symbol = 'HBAR'
        elif blockchain == 'multiversx':
            qty = chain_data.get('total_egld', 0)
            symbol = 'EGLD'
        elif blockchain == 'sui':
            qty = chain_data.get('total_sui', 0)
            symbol = 'SUI'
        elif blockchain == 'aptos':
            qty = chain_data.get('total_apt', 0)
            symbol = 'APT'
        elif blockchain == 'filecoin':
            qty = chain_data.get('total_fil', 0)
            symbol = 'FIL'
        elif blockchain == 'litecoin':
            qty = chain_data.get('total_ltc', 0)
            symbol = 'LTC'
        elif blockchain == 'dogecoin':
            qty = chain_data.get('total_doge', 0)
            symbol = 'DOGE'
        elif blockchain == 'zcash':
            qty = chain_data.get('total_zec', 0)
            symbol = 'ZEC'
        elif blockchain == 'tezos':
            qty = chain_data.get('total_xtz', 0)
            symbol = 'XTZ'
        elif blockchain == 'stacks':
            qty = chain_data.get('total_stx', 0)
            symbol = 'STX'
        elif blockchain == 'vechain':
            qty = chain_data.get('total_vet', 0)
            symbol = 'VET'
        elif blockchain == 'cosmos':
            qty = chain_data.get('total_atom', 0)
            symbol = 'ATOM'
        elif blockchain == 'near':
            qty = chain_data.get('total_near', 0)
            symbol = 'NEAR'
        elif blockchain == 'icp':
            qty = chain_data.get('total_icp', 0)
            symbol = 'ICP'
        else:
            continue

        price_data = all_prices.get(symbol, {})
        price = price_data.get('usd', 0)
        value_usd = qty * price

        if value_usd > 0:
            coin_allocations.append({
                'symbol': symbol,
                'name': symbol,
                'quantity': qty,
                'value_usd': value_usd,
                'blockchain': blockchain,
                'category': TOKEN_CATEGORIES.get(symbol, 'Other'),
                'logo_url': logokit_service.get_crypto_logo_url(symbol, size=64),
                'price_change_24h': price_data.get('usd_24h_change', 0),
            })
            total_value += value_usd

    # Add tokens
    for asset in assets_data.get('assets', []):
        value_usd = asset.get('value_usd') or 0
        if value_usd > 0:
            symbol = asset.get('ticker') or asset.get('asset_name', '')[:10]
            blockchain = asset.get('blockchain', 'cardano')
            price_data = all_prices.get(symbol, {})
            coin_allocations.append({
                'symbol': symbol,
                'name': asset.get('asset_name', symbol),
                'quantity': asset.get('total_quantity', 0),
                'value_usd': value_usd,
                'blockchain': blockchain,
                'category': TOKEN_CATEGORIES.get(symbol, 'Other'),
                'logo_url': logokit_service.get_crypto_logo_url(symbol, size=64),
                'price_change_24h': price_data.get('usd_24h_change', 0),
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
    await set_cache(cache_key, result, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)

    return result


@router.get("/assets/{blockchain}")
async def get_blockchain_asset_breakdown(
    blockchain: str,
    user_id: int = Depends(verify_session)
):
    """Get asset breakdown for a specific blockchain for doughnut chart display."""
    # Demo mode: return fake breakdown from demo wallet service
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await _get_demo_blockchain_breakdown(blockchain)

    try:
        # Validate blockchain
        valid_chains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche', 'tron', 'xrp', 'hedera', 'multiversx', 'sui', 'aptos', 'filecoin', 'litecoin', 'dogecoin', 'zcash', 'tezos', 'stacks', 'vechain', 'cosmos', 'near', 'icp']
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
            'solana': 'SOL', 'polygon': 'POL', 'base': 'ETH',
            'bsc': 'BNB', 'arbitrum': 'ETH', 'avalanche': 'AVAX', 'tron': 'TRX',
            'xrp': 'XRP', 'hedera': 'HBAR', 'multiversx': 'EGLD',
            'sui': 'SUI', 'aptos': 'APT', 'filecoin': 'FIL',
            'litecoin': 'LTC', 'dogecoin': 'DOGE', 'zcash': 'ZEC',
            'tezos': 'XTZ', 'stacks': 'STX', 'vechain': 'VET',
            'cosmos': 'ATOM', 'near': 'NEAR', 'icp': 'ICP'
        }
        native_keys = {
            'cardano': 'total_ada', 'bitcoin': 'total_btc', 'ethereum': 'total_eth',
            'solana': 'total_sol', 'polygon': 'total_matic', 'base': 'total_eth',
            'bsc': 'total_bnb', 'arbitrum': 'total_eth', 'avalanche': 'total_avax', 'tron': 'total_trx',
            'xrp': 'total_xrp', 'hedera': 'total_hbar', 'multiversx': 'total_egld',
            'sui': 'total_sui', 'aptos': 'total_apt', 'filecoin': 'total_fil',
            'litecoin': 'total_ltc', 'dogecoin': 'total_doge', 'zcash': 'total_zec',
            'tezos': 'total_xtz', 'stacks': 'total_stx', 'vechain': 'total_vet',
            'cosmos': 'total_atom', 'near': 'total_near', 'icp': 'total_icp'
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
                    'logo_url': a.get('logo_url')  # Use cached logo URL from asset data
                })

        # Sort tokens by value descending
        token_list.sort(key=lambda x: x['value_usd'], reverse=True)

        # Get supply data from price cache
        native_price_data = all_prices.get(native_symbol, {})
        supply_data = {}
        if native_price_data.get('circulating_supply'):
            supply_data['circulating_supply'] = native_price_data['circulating_supply']
        if native_price_data.get('total_supply'):
            supply_data['total_supply'] = native_price_data['total_supply']
        if native_price_data.get('max_supply'):
            supply_data['max_supply'] = native_price_data['max_supply']

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
            },
            'supply': supply_data
        }

        # Cache for 1 hour (asset breakdowns don't change frequently)
        await set_cache(cache_key, result, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)

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
            'base': 'ETH',  # Base uses ETH
            'bsc': 'BNB',
            'arbitrum': 'ETH',  # Arbitrum uses ETH
            'avalanche': 'AVAX',
            'tron': 'TRX',
            'xrp': 'XRP',
            'hedera': 'HBAR',
            'multiversx': 'EGLD',
            'sui': 'SUI',
            'aptos': 'APT',
            'filecoin': 'FIL',
            'litecoin': 'LTC',
            'dogecoin': 'DOGE',
            'zcash': 'ZEC',
            'tezos': 'XTZ',
            'stacks': 'STX',
            'vechain': 'VET',
            'cosmos': 'ATOM',
            'near': 'NEAR',
            'icp': 'ICP'
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
        await set_cache(cache_key, result, ttl_seconds=CACHE_TTL_WARM, user_id=user_id)

        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error fetching price chart for {blockchain}: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Error fetching price chart: {str(e)}")


# ── Demo mode helper functions ──────────────────────────────────────────────

async def _get_demo_portfolio_history(range_str: str) -> dict:
    """Return pre-generated demo portfolio history for charting."""
    from services.demo_data_generator import generate_portfolio_history

    days_map = {"1d": 1, "7d": 7, "4w": 28, "3m": 90}
    days = days_map.get(range_str, 7)

    # Generate 90 days and slice to requested range
    all_history = generate_portfolio_history(90)
    filtered = all_history[-days:] if days < len(all_history) else all_history

    data = []
    for s in filtered:
        data.append({
            'date': s['snapshot_date'],
            'value': s['total_value_usd'],
            'breakdown': {
                'wallets': s.get('self_custody_value_usd', 0),
                'staking': 0,
                'defi': s.get('defi_value_usd', 0),
                'exchange': s.get('exchange_value_usd', 0),
                'nfts': s.get('nft_value_usd', 0),
                'tracked_tokens': 0
            }
        })

    return {
        "range": range_str,
        "days": days,
        "data": data,
        "data_points": len(data),
        "latest_snapshot": filtered[-1]['snapshot_date'] if filtered else None,
        "demo_mode": True
    }


async def _get_demo_portfolio_summary() -> dict:
    """Build a portfolio summary from demo_wallet_service data."""
    from datetime import datetime

    total_info = await demo_wallet_service.get_total_balance_usd()
    wallets = await demo_wallet_service.get_all_wallets()

    # Group wallets by blockchain
    summary = {}
    symbol_map = {
        'cardano': ('ADA', 'total_ada'),
        'bitcoin': ('BTC', 'total_btc'),
        'ethereum': ('ETH', 'total_eth'),
        'solana': ('SOL', 'total_sol'),
        'polygon': ('POL', 'total_matic'),
        'base': ('ETH', 'total_eth'),
        'algorand': ('ALGO', 'total_algo'),
        'bsc': ('BNB', 'total_bnb'),
        'arbitrum': ('ETH', 'total_eth'),
        'avalanche': ('AVAX', 'total_avax'),
        'tron': ('TRX', 'total_trx'),
        'xrp': ('XRP', 'total_xrp'),
        'hedera': ('HBAR', 'total_hbar'),
        'multiversx': ('EGLD', 'total_egld'),
        'sui': ('SUI', 'total_sui'),
        'aptos': ('APT', 'total_apt'),
        'filecoin': ('FIL', 'total_fil'),
        'litecoin': ('LTC', 'total_ltc'),
        'dogecoin': ('DOGE', 'total_doge'),
        'zcash': ('ZEC', 'total_zec'),
        'tezos': ('XTZ', 'total_xtz'),
        'stacks': ('STX', 'total_stx'),
        'vechain': ('VET', 'total_vet'),
        'cosmos': ('ATOM', 'total_atom'),
        'near': ('NEAR', 'total_near'),
        'icp': ('ICP', 'total_icp'),
    }

    for wallet in wallets:
        bc = wallet['blockchain']
        if bc not in summary:
            symbol, amount_key = symbol_map.get(bc, ('UNKNOWN', 'total_unknown'))
            summary[bc] = {
                'wallet_count': 0,
                amount_key: 0.0,
                'native_assets_count': 0,
                'native_assets_value_usd': 0.0,
                'wallets': [],
            }
        chain = summary[bc]
        chain['wallet_count'] += 1
        _, amount_key = symbol_map.get(bc, ('UNKNOWN', 'total_unknown'))
        chain[amount_key] = chain.get(amount_key, 0) + float(wallet.get('balance', 0))

        # Add token value
        tokens = await demo_wallet_service.get_wallet_tokens(wallet['address'], bc)
        token_value = sum(t.get('value_usd', 0) for t in tokens)
        chain['native_assets_count'] += len(tokens)
        chain['native_assets_value_usd'] += token_value

        chain['wallets'].append({
            'id': wallet['id'],
            'address': wallet['address'],
            'label': wallet.get('label'),
            'blockchain': bc,
            'balance': wallet.get('balance'),
            'balance_usd': wallet.get('balance_usd', 0),
        })

    summary['from_cache'] = False
    summary['last_updated'] = datetime.utcnow().isoformat()
    summary['demo_mode'] = True
    return summary


async def _get_demo_native_assets() -> dict:
    """Build native assets list from demo_wallet_service data."""
    from datetime import datetime

    all_assets = []
    total_value = 0.0

    for blockchain, tokens in demo_wallet_service.demo_tokens.items():
        for token in tokens:
            value = token.get('value_usd', 0)
            total_value += value
            all_assets.append({
                'asset_id': token.get('ticker', 'UNKNOWN'),
                'asset_name': token.get('name', 'Unknown'),
                'ticker': token.get('ticker', 'UNKNOWN'),
                'blockchain': blockchain,
                'quantity': token.get('quantity', 0),
                'decimals': token.get('decimals', 0),
                'actual_quantity': float(token.get('quantity', 0)),
                'price_usd': token.get('price_usd', 0),
                'total_value_usd': round(value, 2),
                'logo_url': token.get('logo', ''),
                'ignored': False,
                'tracked': True,
            })

    # Sort by value descending
    all_assets.sort(key=lambda x: x['total_value_usd'], reverse=True)

    return {
        'assets': all_assets,
        'total_unique_assets': len(all_assets),
        'total_value_usd': round(total_value, 2),
        'tracked_value_usd': round(total_value, 2),
        'demo_mode': True,
    }


async def _get_demo_portfolio_analytics() -> dict:
    """Build portfolio analytics from demo_wallet_service data."""
    from datetime import datetime

    total_info = await demo_wallet_service.get_total_balance_usd()
    total_usd = total_info['total_usd']

    # Build coin allocation from wallet balances + tokens
    coin_allocation = []

    # Add native coins
    native_symbols = {
        'cardano': ('ADA', 'Layer 1 (L1)'),
        'bitcoin': ('BTC', 'Layer 1 (L1)'),
        'ethereum': ('ETH', 'Layer 1 (L1)'),
        'solana': ('SOL', 'Layer 1 (L1)'),
        'polygon': ('POL', 'Layer 2 (L2)'),
        'base': ('ETH', 'Layer 2 (L2)'),
        'algorand': ('ALGO', 'Layer 1 (L1)'),
        'bsc': ('BNB', 'Layer 1 (L1)'),
        'arbitrum': ('ETH', 'Layer 2 (L2)'),
        'avalanche': ('AVAX', 'Layer 1 (L1)'),
        'tron': ('TRX', 'Layer 1 (L1)'),
        'xrp': ('XRP', 'Layer 1 (L1)'),
        'hedera': ('HBAR', 'Layer 1 (L1)'),
        'multiversx': ('EGLD', 'Layer 1 (L1)'),
        'sui': ('SUI', 'Layer 1 (L1)'),
        'aptos': ('APT', 'Layer 1 (L1)'),
        'filecoin': ('FIL', 'Layer 1 (L1)'),
        'litecoin': ('LTC', 'Layer 1 (L1)'),
        'dogecoin': ('DOGE', 'Layer 1 (L1)'),
        'zcash': ('ZEC', 'Layer 1 (L1)'),
        'tezos': ('XTZ', 'Layer 1 (L1)'),
        'stacks': ('STX', 'Layer 1 (L1)'),
        'vechain': ('VET', 'Layer 1 (L1)'),
        'cosmos': ('ATOM', 'Layer 1 (L1)'),
        'near': ('NEAR', 'Layer 1 (L1)'),
        'icp': ('ICP', 'Layer 1 (L1)'),
    }

    for bc, wallets in demo_wallet_service.demo_wallets.items():
        symbol, category = native_symbols.get(bc, ('UNKNOWN', 'Other'))
        for w in wallets:
            value = w.get('balance_usd', 0)
            coin_allocation.append({
                'symbol': symbol,
                'name': bc.title(),
                'quantity': float(w.get('balance', 0)),
                'value_usd': round(value, 2),
                'percentage': round((value / total_usd * 100) if total_usd > 0 else 0, 1),
                'category': category,
                'logo_url': f'https://logostream.dev/api/logo?symbol={symbol}',
            })

    # Add tokens
    for bc, tokens in demo_wallet_service.demo_tokens.items():
        for t in tokens:
            value = t.get('value_usd', 0)
            if value > 0:
                coin_allocation.append({
                    'symbol': t.get('ticker', 'UNKNOWN'),
                    'name': t.get('name', 'Unknown'),
                    'quantity': float(t.get('quantity', 0)),
                    'value_usd': round(value, 2),
                    'percentage': round((value / total_usd * 100) if total_usd > 0 else 0, 1),
                    'category': 'DeFi Token',
                    'logo_url': t.get('logo', ''),
                })

    coin_allocation.sort(key=lambda x: x['value_usd'], reverse=True)

    # Build category allocation
    categories = {}
    for coin in coin_allocation:
        cat = coin['category']
        if cat not in categories:
            categories[cat] = {'category': cat, 'value_usd': 0, 'token_count': 0, 'tokens': []}
        categories[cat]['value_usd'] += coin['value_usd']
        categories[cat]['token_count'] += 1
        categories[cat]['tokens'].append(coin['symbol'])

    category_allocation = list(categories.values())
    for cat in category_allocation:
        cat['value_usd'] = round(cat['value_usd'], 2)
        cat['percentage'] = round((cat['value_usd'] / total_usd * 100) if total_usd > 0 else 0, 1)
    category_allocation.sort(key=lambda x: x['value_usd'], reverse=True)

    return {
        'total_value_usd': round(total_usd, 2),
        'coin_allocation': coin_allocation,
        'category_allocation': category_allocation,
        'generated_at': datetime.utcnow().isoformat(),
        'demo_mode': True,
    }


async def _get_demo_blockchain_breakdown(blockchain: str) -> dict:
    """Build asset breakdown for a specific blockchain from demo data."""
    valid_chains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base', 'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron', 'xrp', 'hedera', 'multiversx', 'sui', 'aptos', 'filecoin', 'litecoin', 'dogecoin', 'zcash', 'tezos', 'stacks', 'vechain', 'cosmos', 'near', 'icp']
    if blockchain not in valid_chains:
        raise HTTPException(400, f"Invalid blockchain: {blockchain}")

    symbol_map = {
        'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH',
        'solana': 'SOL', 'polygon': 'POL', 'base': 'ETH', 'algorand': 'ALGO',
        'bsc': 'BNB', 'arbitrum': 'ETH', 'avalanche': 'AVAX', 'tron': 'TRX',
        'xrp': 'XRP', 'hedera': 'HBAR', 'multiversx': 'EGLD',
        'sui': 'SUI', 'aptos': 'APT', 'filecoin': 'FIL',
        'litecoin': 'LTC', 'dogecoin': 'DOGE', 'zcash': 'ZEC',
        'tezos': 'XTZ', 'stacks': 'STX', 'vechain': 'VET',
        'cosmos': 'ATOM', 'near': 'NEAR', 'icp': 'ICP',
    }
    symbol = symbol_map.get(blockchain, 'UNKNOWN')

    # Get native coin value
    wallets = demo_wallet_service.demo_wallets.get(blockchain, [])
    native_value = sum(w.get('balance_usd', 0) for w in wallets)
    native_qty = sum(float(w.get('balance', 0)) for w in wallets)

    # Get tokens
    tokens_raw = demo_wallet_service.demo_tokens.get(blockchain, [])
    token_total = sum(t.get('value_usd', 0) for t in tokens_raw)
    total_value = native_value + token_total

    tokens = []
    for t in tokens_raw:
        v = t.get('value_usd', 0)
        tokens.append({
            'symbol': t.get('ticker', 'UNKNOWN'),
            'name': t.get('name', 'Unknown'),
            'quantity': float(t.get('quantity', 0)),
            'value_usd': round(v, 2),
            'percentage': round((v / total_value * 100) if total_value > 0 else 0, 1),
            'logo_url': t.get('logo', ''),
        })
    tokens.sort(key=lambda x: x['value_usd'], reverse=True)

    return {
        'blockchain': blockchain,
        'symbol': symbol,
        'logo_url': f'https://logostream.dev/api/logo?symbol={symbol}',
        'total_value_usd': round(total_value, 2),
        'native_coin': {
            'symbol': symbol,
            'quantity': round(native_qty, 8),
            'value_usd': round(native_value, 2),
            'percentage': round((native_value / total_value * 100) if total_value > 0 else 0, 1),
            'logo_url': f'https://logostream.dev/api/logo?symbol={symbol}',
        },
        'tokens': tokens,
        'nfts': {'count': 0, 'value_usd': 0, 'percentage': 0},
        'demo_mode': True,
    }
