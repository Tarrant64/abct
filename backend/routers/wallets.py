from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_all_wallets, get_wallet_by_address, save_wallet,
    save_balance, clear_wallet_balances, save_native_assets,
    get_wallet_assets, get_wallet_balance,
    get_cache, set_cache,
    update_wallet_ada_handle
)
from config import CACHE_TTL_COLD
from services.cardano import cardano_service, is_stake_address, detect_ada_handle
from services.bitcoin import bitcoin_service
from services.ethereum import ethereum_service
from services.solana import solana_service
from services.polygon import polygon_service
from services.base import base_service
from services.algorand import algorand_service
from services.evm_chain import (
    bsc_service, arbitrum_service, avalanche_service,
    optimism_service, zksync_service, linea_service, scroll_service,
    fantom_service, cronos_service, gnosis_service, moonbeam_service, kaia_service
)
from services.cosmos_chain import (
    osmosis_service, celestia_service, injective_service,
    dydx_service, sei_service, akash_service
)
from services.ton_service import ton_service
from services.substrate_service import polkadot_service, kusama_service
from services.stellar_service import stellar_service
from services.kaspa_service import kaspa_service
from services.ergo_service import ergo_service
from services.iota_service import iota_service
from services.waves_service import waves_service
from services.mina_service import mina_service
from services.zilliqa_service import zilliqa_service
from services.tron import tron_service
from services.xrp import xrp_service
from services.hedera import hedera_service
from services.multiversx import multiversx_service
from services.sui import sui_service
from services.aptos import aptos_service
from services.filecoin import filecoin_service
from services.litecoin import litecoin_service
from services.dogecoin import dogecoin_service
from services.zcash import zcash_service
from services.monero import monero_service
from services.secret_network import secret_network_service
from services.tezos import tezos_service
from services.stacks import stacks_service
from services.vechain import vechain_service
from services.cosmos import cosmos_service
from services.near import near_service
from services.icp import icp_service
from services.logging_service import get_logging_service
from services.transaction_history import transaction_history_service
from services.demo_wallet_service import demo_wallet_service
from services.demo_defi_service import demo_defi_service
from services.pricing import pricing_service
from services.taptools import taptools_wallet_service
from services.graph import graph_service
from services.nmkr_service import nmkr_service
from services.logokit_service import logokit_service
from utils.address import parse_wallets_file, detect_blockchain, detect_blockchains, is_bitcoin_xpub, get_xpub_type
from config import WALLETS_FILE, DATA_DIR
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session
from database import get_username_by_user_id


def append_to_wallets_file(address: str, label: Optional[str] = None) -> bool:
    """
    Append a wallet address to wallets.txt, creating the file if it doesn't exist.

    Args:
        address: The wallet address to add
        label: Optional label (added as a comment on the same line)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Check if address already exists in file
        existing_addresses = set()
        if WALLETS_FILE.exists():
            with open(WALLETS_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Extract address (handle prefix format like "cardano:addr1...")
                        addr = line.split(':')[-1].split('#')[0].strip()
                        existing_addresses.add(addr)

        # Don't add duplicate
        if address in existing_addresses:
            return True

        # Append to file
        with open(WALLETS_FILE, 'a') as f:
            if label:
                f.write(f"{address}  # {label}\n")
            else:
                f.write(f"{address}\n")

        return True
    except Exception as e:
        # Use centralized logging instead of print
        import asyncio
        log_service = get_logging_service()
        asyncio.create_task(log_service.error(
            "wallets",
            f"Error appending to wallets.txt: {str(e)}",
            exc_info=e
        ))
        return False

router = APIRouter(prefix="/wallets", tags=["wallets"])

class WalletCreate(BaseModel):
    address: str
    label: Optional[str] = None

class WalletUpdate(BaseModel):
    label: str

class WalletResponse(BaseModel):
    id: int
    address: str
    blockchain: str
    label: Optional[str]
    ada_handle: Optional[str] = None
    balance: Optional[str] = None
    balance_native: Optional[str] = None
    native_assets: Optional[list] = None

@router.get("")
async def list_wallets(user_id: int = Depends(verify_session)):
    """List all tracked wallets with their current balances and stake keys."""
    # Demo mode: return fake wallet data
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        demo_wallets = await demo_wallet_service.get_all_wallets()
        result = []
        for w in demo_wallets:
            bc = w['blockchain']
            tokens = await demo_wallet_service.get_wallet_tokens(w['address'], bc)
            result.append({
                'id': w['id'],
                'address': w['address'],
                'blockchain': bc,
                'label': w.get('label'),
                'balance': w.get('balance'),
                'balance_unit': demo_wallet_service._get_native_unit(bc),
                'native_assets_count': len(tokens),
                'user_id': user_id,
                'created_at': w.get('created_at'),
            })
        return {"wallets": result, "total": len(result), "demo_mode": True}

    log_service = get_logging_service()

    try:
        wallets = await get_all_wallets(user_id=user_id)
    except Exception as e:
        await log_service.error("wallets", "Failed to retrieve wallets from database", exc_info=e)
        raise HTTPException(status_code=500, detail="Failed to retrieve wallets")

    result = []
    # Cache stake key lookups to avoid duplicate API calls
    stake_key_cache = {}

    for wallet in wallets:
        balance_info = await get_wallet_balance(wallet['id'])
        assets = await get_wallet_assets(wallet['id'])

        wallet_data = {
            **wallet,
            'balance': balance_info['amount'] if balance_info else None,
            'balance_unit': balance_info['unit'] if balance_info else None,
            'native_assets_count': len(assets)
        }

        # For Cardano wallets, derive the stake key
        if wallet['blockchain'] == 'cardano' and wallet['address'].startswith('addr1'):
            address = wallet['address']
            if address not in stake_key_cache:
                try:
                    stake_key = await cardano_service.get_stake_address(address)
                    stake_key_cache[address] = stake_key
                except Exception:
                    stake_key_cache[address] = None
            wallet_data['stake_key'] = stake_key_cache[address]

        result.append(wallet_data)

    return {"wallets": result, "total": len(result)}

@router.get("/id/{wallet_id}/assets")
async def get_wallet_assets_by_id(wallet_id: int, user_id: int = Depends(verify_session)):
    """Get native assets for a specific wallet by ID with pricing information."""
    # Demo mode: return fake token data for the requested wallet
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        demo_wallets = await demo_wallet_service.get_all_wallets()
        wallet = next((w for w in demo_wallets if w['id'] == wallet_id), None)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        tokens = await demo_wallet_service.get_wallet_tokens(wallet['address'], wallet['blockchain'])
        assets = []
        for t in tokens:
            assets.append({
                'id': 0,
                'asset_id': t.get('ticker', 'UNKNOWN'),
                'asset_name': t.get('name', 'Unknown'),
                'ticker': t.get('ticker', 'UNKNOWN'),
                'quantity': str(t.get('quantity', 0)),
                'decimals': t.get('decimals', 0),
                'actual_quantity': float(t.get('quantity', 0)),
                'price_usd': t.get('price_usd', 0),
                'total_value_usd': round(t.get('value_usd', 0), 2),
                'logo_url': t.get('logo', ''),
                'ignored': False,
            })
        assets.sort(key=lambda x: x['total_value_usd'], reverse=True)
        return {
            'wallet_id': wallet_id,
            'blockchain': wallet['blockchain'],
            'address': wallet['address'],
            'assets': assets,
            'total_assets': len(assets),
            'total_value_usd': round(sum(a['total_value_usd'] for a in assets), 2),
            'demo_mode': True,
        }

    import aiosqlite
    from config import DATABASE_PATH

    # First get the wallet to know its blockchain and address
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,))
        wallet_row = await cursor.fetchone()
        if not wallet_row:
            raise HTTPException(status_code=404, detail="Wallet not found")
        wallet = dict(wallet_row)

    # Get assets with ticker information from token_metadata and custom_tokens
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                na.*,
                COALESCE(ct.ticker, tm.ticker) as ticker,
                COALESCE(ct.token_name, tm.name) as token_name
            FROM native_assets na
            LEFT JOIN token_metadata tm ON na.asset_id = tm.asset_id
            LEFT JOIN custom_tokens ct ON
                ct.policy_id = na.policy_id
                AND ct.asset_name = na.asset_name
                AND ct.user_id = na.user_id
            WHERE na.wallet_id = ?
            ORDER BY na.asset_name
        """, (wallet_id,))
        rows = await cursor.fetchall()
        assets = [dict(row) for row in rows]

    # Get native coin prices for USD conversions
    ada_price_usd = await pricing_service.get_price('ADA')
    eth_price_usd = await pricing_service.get_price('ETH')
    sol_price_usd = await pricing_service.get_price('SOL')
    pol_price_usd = await pricing_service.get_price('MATIC')
    bnb_price_usd = await pricing_service.get_price('BNB')
    avax_price_usd = await pricing_service.get_price('AVAX')
    trx_price_usd = await pricing_service.get_price('TRX')
    xrp_price_usd = await pricing_service.get_price('XRP')
    hbar_price_usd = await pricing_service.get_price('HBAR')
    egld_price_usd = await pricing_service.get_price('EGLD')
    sui_price_usd = await pricing_service.get_price('SUI')
    apt_price_usd = await pricing_service.get_price('APT')
    fil_price_usd = await pricing_service.get_price('FIL')
    ltc_price_usd = await pricing_service.get_price('LTC')
    doge_price_usd = await pricing_service.get_price('DOGE')
    zec_price_usd = await pricing_service.get_price('ZEC')
    xtz_price_usd = await pricing_service.get_price('XTZ')
    stx_price_usd = await pricing_service.get_price('STX')
    vet_price_usd = await pricing_service.get_price('VET')
    atom_price_usd = await pricing_service.get_price('ATOM')
    near_price_usd = await pricing_service.get_price('NEAR')
    icp_price_usd = await pricing_service.get_price('ICP')
    ftm_price_usd = await pricing_service.get_price('FTM')
    cro_price_usd = await pricing_service.get_price('CRO')
    xdai_price_usd = await pricing_service.get_price('DAI')
    glmr_price_usd = await pricing_service.get_price('GLMR')
    # New chains
    osmo_price_usd = await pricing_service.get_price('OSMO')
    tia_price_usd = await pricing_service.get_price('TIA')
    inj_price_usd = await pricing_service.get_price('INJ')
    dydx_price_usd = await pricing_service.get_price('DYDX')
    sei_price_usd = await pricing_service.get_price('SEI')
    akt_price_usd = await pricing_service.get_price('AKT')
    ton_price_usd = await pricing_service.get_price('TON')
    dot_price_usd = await pricing_service.get_price('DOT')
    ksm_price_usd = await pricing_service.get_price('KSM')
    xlm_price_usd = await pricing_service.get_price('XLM')
    kas_price_usd = await pricing_service.get_price('KAS')
    klay_price_usd = await pricing_service.get_price('KLAY')
    erg_price_usd = await pricing_service.get_price('ERG')
    iota_price_usd = await pricing_service.get_price('IOTA')
    waves_price_usd = await pricing_service.get_price('WAVES')
    mina_price_usd = await pricing_service.get_price('MINA')
    zil_price_usd = await pricing_service.get_price('ZIL')
    xmr_price_usd = await pricing_service.get_price('XMR')
    scrt_price_usd = await pricing_service.get_price('SCRT')

    # For Cardano wallets, try to get TapTools data for ADA-denominated pricing
    taptools_positions = {}
    if wallet['blockchain'] == 'cardano' and taptools_wallet_service.is_configured():
        try:
            portfolio = await taptools_wallet_service.get_wallet_portfolio(wallet['address'])
            if portfolio and portfolio.get('positions'):
                # Index TapTools positions by unit (asset_id)
                for pos in portfolio['positions']:
                    unit = pos.get('unit', '')
                    if unit and unit != 'lovelace':  # Skip ADA
                        taptools_positions[unit] = pos
        except Exception as e:
            logger = get_logging_service()
            logger.log_debug(f"TapTools data unavailable for wallet {wallet_id}: {e}")

    # For Ethereum-based chains, try to get Graph/Uniswap data for native-token-denominated pricing
    graph_prices = {}
    if wallet['blockchain'] in ['ethereum', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche', 'optimism', 'zksync', 'linea', 'scroll', 'fantom', 'cronos', 'gnosis', 'moonbeam'] and graph_service.is_configured():
        try:
            # Get token addresses for Graph API lookup
            token_addresses = []
            for asset in assets:
                if asset.get('asset_id'):  # asset_id should be the contract address
                    token_addresses.append(asset['asset_id'])

            if token_addresses:
                # Get prices in ETH for all tokens
                graph_prices = await graph_service.get_multiple_token_prices(token_addresses)
        except Exception as e:
            logger = get_logging_service()
            logger.log_debug(f"Graph API data unavailable for wallet {wallet_id}: {e}")

    # Enrich assets with pricing information
    enriched_assets = []
    for asset in assets:
        # Convert raw quantity to actual quantity using decimals
        raw_qty = float(asset.get('quantity') or 0)
        decimals = int(asset.get('decimals') or 0)
        actual_qty = raw_qty / (10 ** decimals)

        asset_data = {
            **asset,
            'actual_quantity': actual_qty,
            'price_native': None,  # Price in native token (ADA/ETH/SOL/etc)
            'total_native': None,  # Total value in native token
            'price_usd': None,
            'total_value_usd': None,
            'logo_url': None
        }

        # Keep ADA-specific fields for backwards compatibility
        asset_data['price_ada'] = None
        asset_data['total_ada'] = None

        # For Cardano assets, try TapTools first (ADA-denominated)
        if wallet['blockchain'] == 'cardano' and asset.get('asset_id') in taptools_positions:
            pos = taptools_positions[asset['asset_id']]
            price_ada = float(pos.get('price', 0))
            total_ada = float(pos.get('adaValue', 0))

            asset_data['price_ada'] = price_ada
            asset_data['total_ada'] = total_ada
            asset_data['price_native'] = price_ada
            asset_data['total_native'] = total_ada

            # Calculate USD value
            if ada_price_usd and total_ada > 0:
                asset_data['total_value_usd'] = total_ada * ada_price_usd
                if actual_qty > 0:
                    asset_data['price_usd'] = (total_ada * ada_price_usd) / actual_qty

        # For Ethereum-based chains, try Graph API (ETH-denominated)
        elif wallet['blockchain'] in ['ethereum', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche', 'optimism', 'zksync', 'linea', 'scroll', 'fantom', 'cronos', 'gnosis', 'moonbeam'] and asset.get('asset_id') in graph_prices:
            price_eth = graph_prices[asset['asset_id']]
            total_eth = actual_qty * price_eth

            asset_data['price_native'] = price_eth
            asset_data['total_native'] = total_eth

            # Calculate USD value
            native_price_usd = eth_price_usd if wallet['blockchain'] in ['ethereum', 'base'] else pol_price_usd
            if native_price_usd and total_eth > 0:
                asset_data['total_value_usd'] = total_eth * native_price_usd
                if actual_qty > 0:
                    asset_data['price_usd'] = (total_eth * native_price_usd) / actual_qty

        # Fallback to direct USD pricing if available
        elif asset.get('ticker'):
            try:
                price_usd = await pricing_service.get_price(asset['ticker'].upper())
                if price_usd and price_usd > 0:
                    asset_data['price_usd'] = price_usd
                    asset_data['total_value_usd'] = actual_qty * price_usd

                    # Calculate native token equivalent
                    if wallet['blockchain'] == 'cardano' and ada_price_usd and ada_price_usd > 0:
                        asset_data['price_ada'] = price_usd / ada_price_usd
                        asset_data['total_ada'] = (actual_qty * price_usd) / ada_price_usd
                        asset_data['price_native'] = price_usd / ada_price_usd
                        asset_data['total_native'] = (actual_qty * price_usd) / ada_price_usd
                    elif wallet['blockchain'] in ['ethereum', 'base'] and eth_price_usd and eth_price_usd > 0:
                        asset_data['price_native'] = price_usd / eth_price_usd
                        asset_data['total_native'] = (actual_qty * price_usd) / eth_price_usd
                    elif wallet['blockchain'] == 'solana' and sol_price_usd and sol_price_usd > 0:
                        asset_data['price_native'] = price_usd / sol_price_usd
                        asset_data['total_native'] = (actual_qty * price_usd) / sol_price_usd
                    elif wallet['blockchain'] == 'polygon' and pol_price_usd and pol_price_usd > 0:
                        asset_data['price_native'] = price_usd / pol_price_usd
                        asset_data['total_native'] = (actual_qty * price_usd) / pol_price_usd
            except Exception:
                pass

        # Add logo URL with multiple fallback strategies
        logo_url = None
        if wallet['blockchain'] == 'cardano':
            # For Cardano native tokens, use comprehensive fallback chain
            policy_id = asset.get('policy_id')
            asset_id = asset.get('asset_id', '')

            # Extract hex asset name from asset_id (format: policy_id + asset_name_hex)
            asset_name_hex = asset_id[len(policy_id):] if policy_id and len(asset_id) > len(policy_id) else None

            if policy_id and asset_name_hex:
                ticker = asset_data.get('ticker')
                # Try NMKR → Cardano Token Registry → Blockfrost → LogoKit
                logo_url = await nmkr_service.get_token_logo_with_fallbacks(
                    policy_id,
                    asset_name_hex,
                    ticker=ticker,
                    user_id=user_id
                )

        # Non-Cardano fallback to LogoKit
        if not logo_url:
            ticker = asset_data.get('ticker')
            if ticker:
                logo_url = logokit_service.get_crypto_logo_url(ticker, size=64)
            else:
                # Use asset name as fallback
                asset_name = asset.get('asset_name', '')[:10]
                if asset_name:
                    logo_url = logokit_service.get_crypto_logo_url(asset_name, size=64)

        asset_data['logo_url'] = logo_url
        enriched_assets.append(asset_data)

    # Get wallet balance for native coin
    wallet_balance = await get_wallet_balance(wallet_id)
    native_balance = None

    if wallet_balance:
        balance_raw = float(wallet_balance.get('amount', 0))

        # Define native coin parameters by blockchain
        native_config = {
            'cardano': {'ticker': 'ADA', 'name': 'Cardano', 'decimals': 6, 'price_usd': ada_price_usd},
            'bitcoin': {'ticker': 'BTC', 'name': 'Bitcoin', 'decimals': 8, 'price_usd': await pricing_service.get_price('BTC')},
            'ethereum': {'ticker': 'ETH', 'name': 'Ethereum', 'decimals': 18, 'price_usd': eth_price_usd},
            'solana': {'ticker': 'SOL', 'name': 'Solana', 'decimals': 9, 'price_usd': sol_price_usd},
            'polygon': {'ticker': 'POL', 'name': 'Polygon', 'decimals': 18, 'price_usd': pol_price_usd},
            'base': {'ticker': 'ETH', 'name': 'Base (ETH)', 'decimals': 18, 'price_usd': eth_price_usd},
            'algorand': {'ticker': 'ALGO', 'name': 'Algorand', 'decimals': 6, 'price_usd': await pricing_service.get_price('ALGO')},
            'bsc': {'ticker': 'BNB', 'name': 'BNB Smart Chain', 'decimals': 18, 'price_usd': bnb_price_usd},
            'arbitrum': {'ticker': 'ETH', 'name': 'Arbitrum (ETH)', 'decimals': 18, 'price_usd': eth_price_usd},
            'avalanche': {'ticker': 'AVAX', 'name': 'Avalanche', 'decimals': 18, 'price_usd': avax_price_usd},
            'tron': {'ticker': 'TRX', 'name': 'Tron', 'decimals': 6, 'price_usd': trx_price_usd},
            'xrp': {'ticker': 'XRP', 'name': 'XRP Ledger', 'decimals': 6, 'price_usd': xrp_price_usd},
            'hedera': {'ticker': 'HBAR', 'name': 'Hedera', 'decimals': 8, 'price_usd': hbar_price_usd},
            'multiversx': {'ticker': 'EGLD', 'name': 'MultiversX', 'decimals': 18, 'price_usd': egld_price_usd},
            'sui': {'ticker': 'SUI', 'name': 'Sui', 'decimals': 9, 'price_usd': sui_price_usd},
            'aptos': {'ticker': 'APT', 'name': 'Aptos', 'decimals': 8, 'price_usd': apt_price_usd},
            'filecoin': {'ticker': 'FIL', 'name': 'Filecoin', 'decimals': 18, 'price_usd': fil_price_usd},
            'litecoin': {'ticker': 'LTC', 'name': 'Litecoin', 'decimals': 8, 'price_usd': ltc_price_usd},
            'dogecoin': {'ticker': 'DOGE', 'name': 'Dogecoin', 'decimals': 8, 'price_usd': doge_price_usd},
            'zcash': {'ticker': 'ZEC', 'name': 'Zcash', 'decimals': 8, 'price_usd': zec_price_usd},
            'tezos': {'ticker': 'XTZ', 'name': 'Tezos', 'decimals': 6, 'price_usd': xtz_price_usd},
            'stacks': {'ticker': 'STX', 'name': 'Stacks', 'decimals': 6, 'price_usd': stx_price_usd},
            'vechain': {'ticker': 'VET', 'name': 'VeChain', 'decimals': 18, 'price_usd': vet_price_usd},
            'cosmos': {'ticker': 'ATOM', 'name': 'Cosmos', 'decimals': 6, 'price_usd': atom_price_usd},
            'near': {'ticker': 'NEAR', 'name': 'NEAR Protocol', 'decimals': 24, 'price_usd': near_price_usd},
            'icp': {'ticker': 'ICP', 'name': 'Internet Computer', 'decimals': 8, 'price_usd': icp_price_usd},
            'optimism': {'ticker': 'ETH', 'name': 'Optimism (ETH)', 'decimals': 18, 'price_usd': eth_price_usd},
            'zksync': {'ticker': 'ETH', 'name': 'zkSync Era (ETH)', 'decimals': 18, 'price_usd': eth_price_usd},
            'linea': {'ticker': 'ETH', 'name': 'Linea (ETH)', 'decimals': 18, 'price_usd': eth_price_usd},
            'scroll': {'ticker': 'ETH', 'name': 'Scroll (ETH)', 'decimals': 18, 'price_usd': eth_price_usd},
            'fantom': {'ticker': 'FTM', 'name': 'Fantom', 'decimals': 18, 'price_usd': ftm_price_usd},
            'cronos': {'ticker': 'CRO', 'name': 'Cronos', 'decimals': 18, 'price_usd': cro_price_usd},
            'gnosis': {'ticker': 'xDAI', 'name': 'Gnosis Chain', 'decimals': 18, 'price_usd': xdai_price_usd},
            'moonbeam': {'ticker': 'GLMR', 'name': 'Moonbeam', 'decimals': 18, 'price_usd': glmr_price_usd},
            'kaia': {'ticker': 'KLAY', 'name': 'Kaia', 'decimals': 18, 'price_usd': klay_price_usd},
            'osmosis': {'ticker': 'OSMO', 'name': 'Osmosis', 'decimals': 6, 'price_usd': osmo_price_usd},
            'celestia': {'ticker': 'TIA', 'name': 'Celestia', 'decimals': 6, 'price_usd': tia_price_usd},
            'injective': {'ticker': 'INJ', 'name': 'Injective', 'decimals': 18, 'price_usd': inj_price_usd},
            'dydx': {'ticker': 'DYDX', 'name': 'dYdX', 'decimals': 18, 'price_usd': dydx_price_usd},
            'sei': {'ticker': 'SEI', 'name': 'Sei', 'decimals': 6, 'price_usd': sei_price_usd},
            'akash': {'ticker': 'AKT', 'name': 'Akash', 'decimals': 6, 'price_usd': akt_price_usd},
            'ton': {'ticker': 'TON', 'name': 'TON', 'decimals': 9, 'price_usd': ton_price_usd},
            'polkadot': {'ticker': 'DOT', 'name': 'Polkadot', 'decimals': 10, 'price_usd': dot_price_usd},
            'kusama': {'ticker': 'KSM', 'name': 'Kusama', 'decimals': 12, 'price_usd': ksm_price_usd},
            'stellar': {'ticker': 'XLM', 'name': 'Stellar', 'decimals': 7, 'price_usd': xlm_price_usd},
            'kaspa': {'ticker': 'KAS', 'name': 'Kaspa', 'decimals': 8, 'price_usd': kas_price_usd},
            'ergo': {'ticker': 'ERG', 'name': 'Ergo', 'decimals': 9, 'price_usd': erg_price_usd},
            'iota': {'ticker': 'IOTA', 'name': 'IOTA', 'decimals': 9, 'price_usd': iota_price_usd},
            'waves': {'ticker': 'WAVES', 'name': 'Waves', 'decimals': 8, 'price_usd': waves_price_usd},
            'mina': {'ticker': 'MINA', 'name': 'Mina Protocol', 'decimals': 9, 'price_usd': mina_price_usd},
            'zilliqa': {'ticker': 'ZIL', 'name': 'Zilliqa', 'decimals': 12, 'price_usd': zil_price_usd},
            'monero': {'ticker': 'XMR', 'name': 'Monero', 'decimals': 12, 'price_usd': xmr_price_usd},
            'secret_network': {'ticker': 'SCRT', 'name': 'Secret Network', 'decimals': 6, 'price_usd': scrt_price_usd},
        }

        if wallet['blockchain'] in native_config:
            config = native_config[wallet['blockchain']]
            balance_actual = balance_raw / (10 ** config['decimals'])

            native_balance = {
                'ticker': config['ticker'],
                'token_name': config['name'],
                'actual_quantity': balance_actual,
                'price_native': 1.0,  # Native coin priced in itself is always 1
                'total_native': balance_actual,
                'price_usd': config['price_usd'],
                'total_value_usd': balance_actual * config['price_usd'] if config['price_usd'] else 0,
                'is_native': True
            }

            # Keep ADA-specific fields for backwards compatibility
            if wallet['blockchain'] == 'cardano':
                native_balance['price_ada'] = 1.0
                native_balance['total_ada'] = balance_actual

    return {
        "assets": enriched_assets,
        "native_balance": native_balance,
        "blockchain": wallet['blockchain'],
        "native_coin_price_usd": native_balance['price_usd'] if native_balance else None
    }

@router.get("/detect")
async def detect_address(address: str, user_id: int = Depends(verify_session)):
    """Detect which blockchain(s) an address belongs to."""
    address = address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address is required")

    detected = detect_blockchains(address)
    raw = address.split(':', 1)[-1] if ':' in address else address

    return {
        'detected': detected,
        'ambiguous': len(detected) > 1,
        'is_xpub': is_bitcoin_xpub(raw),
        'is_stake': raw.startswith('stake1')
    }


@router.get("/{address}")
async def get_wallet(address: str, user_id: int = Depends(verify_session)):
    """Get details for a specific wallet."""
    wallet = await get_wallet_by_address(address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    balance_info = await get_wallet_balance(wallet['id'])
    assets = await get_wallet_assets(wallet['id'])

    return {
        **wallet,
        'balance': balance_info['amount'] if balance_info else None,
        'balance_unit': balance_info['unit'] if balance_info else None,
        'native_assets': assets
    }

@router.post("/sync")
async def sync_wallets_from_file(user_id: int = Depends(verify_session)):
    """
    Sync wallets from the wallets.txt file.
    Stake addresses (stake1) are automatically expanded to their associated payment addresses.
    """
    # Demo mode: block write operations
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"message": "Demo mode: Wallet sync disabled", "synced": 0, "demo_mode": True}

    wallets = parse_wallets_file(str(WALLETS_FILE))

    if not wallets:
        return {"message": "No wallets found in file", "synced": 0}

    synced = 0
    expanded_from_stake = 0
    stake_addresses_processed = []

    for wallet in wallets:
        address = wallet['address']

        # Check if this is a stake address
        if is_stake_address(address):
            stake_addresses_processed.append(address)
            # Get all payment addresses associated with this stake address
            payment_addresses = await cardano_service.get_addresses_from_stake(address)

            if payment_addresses:
                for pay_addr in payment_addresses:
                    await save_wallet(pay_addr, 'cardano', f"From stake: {address[:20]}...", user_id)
                    synced += 1
                    expanded_from_stake += 1
            else:
                # Save the stake address itself if no payment addresses found
                await save_wallet(address, wallet['blockchain'], None, user_id)
                synced += 1
        else:
            await save_wallet(address, wallet['blockchain'], None, user_id)
            synced += 1

    # Now refresh all wallet balances in parallel (with concurrency limit)
    all_wallets = await get_all_wallets(user_id=user_id)

    # Use semaphore to limit concurrent API calls (prevents rate limiting)
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent refreshes

    async def refresh_with_limit(wallet):
        async with semaphore:
            return await _refresh_wallet_balance(wallet)

    # Refresh all wallets in parallel
    results = await asyncio.gather(*[refresh_with_limit(w) for w in all_wallets])
    refreshed = sum(1 for r in results if r.get('success'))

    message = f"Synced {synced} wallets from file, refreshed {refreshed} balances"
    if expanded_from_stake > 0:
        message += f" ({expanded_from_stake} expanded from {len(stake_addresses_processed)} stake address(es))"

    return {
        "message": message,
        "synced": synced,
        "refreshed": refreshed,
        "stake_addresses_expanded": len(stake_addresses_processed),
        "payment_addresses_from_stake": expanded_from_stake
    }

@router.post("/refresh")
async def refresh_all_balances(user_id: int = Depends(verify_session)):
    """Refresh balances for all tracked wallets in parallel."""
    # Demo mode: return fake refresh result
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        demo_wallets = await demo_wallet_service.get_all_wallets()
        return {
            "message": f"Demo mode: Simulated refresh of {len(demo_wallets)} wallets",
            "refreshed": len(demo_wallets),
            "results": [{"address": w['address'], "success": True} for w in demo_wallets],
            "demo_mode": True,
        }

    wallets = await get_all_wallets(user_id=user_id)

    if not wallets:
        return {"message": "No wallets to refresh", "refreshed": 0}

    # Use semaphore to limit concurrent API calls (prevents rate limiting)
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent refreshes

    async def refresh_with_limit(wallet):
        async with semaphore:
            return await _refresh_wallet_balance(wallet)

    # Refresh all wallets in parallel
    results = await asyncio.gather(*[refresh_with_limit(w) for w in wallets])

    success_count = sum(1 for r in results if r.get('success'))

    # Invalidate and repopulate portfolio cache with fresh data
    if success_count > 0:
        from database import clear_cache
        await clear_cache("portfolio_summary", user_id=user_id)
        # Trigger cache repopulation by calling portfolio summary
        try:
            from routers.portfolio import get_portfolio_summary
            await get_portfolio_summary(user_id=user_id, refresh=True)
        except Exception as e:
            import logging
            logging.warning(f"Could not repopulate portfolio cache: {e}")

        # Start background logo pre-fetching (don't wait for completion)
        try:
            asyncio.create_task(nmkr_service.prefetch_logos_for_wallet_assets(user_id))
            import logging
            logging.info("Started background logo pre-fetching")
        except Exception as e:
            import logging
            logging.warning(f"Could not start logo pre-fetching: {e}")

    return {
        "message": f"Refreshed {success_count}/{len(wallets)} wallets",
        "refreshed": success_count,
        "results": list(results)
    }

@router.post("/{address}/refresh")
async def refresh_wallet_balance(address: str, user_id: int = Depends(verify_session)):
    """Refresh balance for a specific wallet."""
    wallet = await get_wallet_by_address(address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    return await _refresh_wallet_balance(wallet)


async def get_stored_balance(wallet_id: int, unit: str) -> Optional[str]:
    """Get stored balance for a wallet from the balances table, filtered by unit."""
    import aiosqlite as _aiosqlite
    from config import DATABASE_PATH as _DATABASE_PATH
    async with _aiosqlite.connect(str(_DATABASE_PATH)) as db:
        cursor = await db.execute(
            "SELECT amount FROM balances WHERE wallet_id = ? AND unit = ? ORDER BY updated_at DESC LIMIT 1",
            (wallet_id, unit)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def _refresh_wallet_balance(wallet: dict) -> dict:
    """Internal function to refresh a single wallet's balance."""
    address = wallet['address']
    blockchain = wallet['blockchain']
    wallet_id = wallet['id']

    try:
        if blockchain == 'cardano':
            info = await cardano_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, info['balance_ada'], 'ADA')
                await save_native_assets(wallet_id, info['native_assets'])

                # Detect ADA Handle from native assets
                ada_handle = detect_ada_handle(info['native_assets'])
                if ada_handle:
                    await update_wallet_ada_handle(wallet_id, ada_handle)

                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_ada'],
                    'unit': 'ADA',
                    'native_assets_count': len(info['native_assets']),
                    'source': info['source'],
                    'ada_handle': ada_handle
                }

        elif blockchain == 'bitcoin':
            info = await bitcoin_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, info['balance_btc'], 'BTC')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_btc'],
                    'unit': 'BTC',
                    'confirmed': info['confirmed_satoshis'],
                    'unconfirmed': info['unconfirmed_satoshis'],
                    'source': info['source']
                }

        elif blockchain == 'ethereum':
            # Service handles fallback to public RPC internally
            info = await ethereum_service.get_address_balance(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH')
                # Save ERC-20 tokens as native assets (empty if using public RPC fallback)
                erc20_assets = [
                    {
                        'asset_id': token['contract_address'],
                        'policy_id': token['contract_address'],
                        'asset_name': token['symbol'],
                        'quantity': str(int(token['balance'] * (10 ** token['decimals']))),
                        'decimals': token['decimals']
                    }
                    for token in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, erc20_assets)

                # Try ENS reverse resolution
                ens_name = None
                try:
                    from services.moralis import moralis_service
                    if await moralis_service.is_configured():
                        ens_name = await moralis_service.resolve_address_to_ens(address)
                except Exception as e:
                    logger.debug(f"ENS resolution failed for {address}: {e}")

                result = {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source', 'alchemy')
                }
                if ens_name:
                    result['ens_name'] = ens_name
                return result

        elif blockchain == 'solana':
            # Service handles fallback to public RPC internally
            info = await solana_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_sol']), 'SOL')
                # Save SPL tokens as native assets (empty if using public RPC fallback)
                spl_assets = [
                    {
                        'asset_id': token['mint'],
                        'policy_id': token['mint'],
                        'asset_name': token['symbol'],
                        'quantity': str(int(token['amount_raw'])),
                        'decimals': token['decimals']
                    }
                    for token in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, spl_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_sol'],
                    'unit': 'SOL',
                    'token_count': len(info.get('tokens', [])),
                    'source': info.get('source', 'helius')
                }
            else:
                logger.error(f"All sources failed to fetch balance for Solana {address}")
                return {
                    'address': address,
                    'success': False,
                    'error': 'Failed to fetch balance from all sources (Helius + public RPC)'
                }

        elif blockchain == 'polygon':
            # Service handles fallback to public RPC internally
            info = await polygon_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_matic']), 'MATIC')
                # Save ERC-20 tokens as native assets (empty if using public RPC fallback)
                polygon_assets = [
                    {
                        'asset_id': token['contract_address'],
                        'policy_id': token['contract_address'],
                        'asset_name': token['symbol'],
                        'quantity': str(int(token['balance_raw'])),
                        'decimals': token['decimals']
                    }
                    for token in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, polygon_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_matic'],
                    'unit': 'MATIC',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source', 'alchemy')
                }

        elif blockchain == 'base':
            # Service handles fallback to public RPC internally
            info = await base_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_BASE')
                # Save ERC-20 tokens as native assets (empty if using public RPC fallback)
                base_assets = [
                    {
                        'asset_id': token['contract_address'],
                        'policy_id': token['contract_address'],
                        'asset_name': token['symbol'],
                        'quantity': str(int(token['balance_raw'])),
                        'decimals': token['decimals']
                    }
                    for token in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, base_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source', 'alchemy')
                }

        elif blockchain == 'algorand':
            info = await algorand_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_algo']), 'ALGO')
                algorand_assets = [
                    {
                        'asset_id': str(asset['asset_id']),
                        'policy_id': str(asset['asset_id']),
                        'asset_name': asset.get('unit_name', '') or asset.get('name', ''),
                        'quantity': str(asset['amount']),
                        'decimals': asset['decimals']
                    }
                    for asset in info.get('assets', [])
                ]
                await save_native_assets(wallet_id, algorand_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_algo'],
                    'unit': 'ALGO',
                    'asset_count': len(info.get('assets', [])),
                    'source': info.get('source', 'pera')
                }

        elif blockchain == 'bsc':
            info = await bsc_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_bnb']), 'BNB')
                bsc_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, bsc_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_bnb'],
                    'unit': 'BNB',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'arbitrum':
            info = await arbitrum_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_ARB')
                arb_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, arb_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'avalanche':
            info = await avalanche_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_avax']), 'AVAX')
                avax_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, avax_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_avax'],
                    'unit': 'AVAX',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'optimism':
            info = await optimism_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_OP')
                op_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, op_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'zksync':
            info = await zksync_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_ZK')
                zk_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, zk_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'linea':
            info = await linea_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_LINEA')
                linea_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, linea_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'scroll':
            info = await scroll_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_SCROLL')
                scroll_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, scroll_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'fantom':
            info = await fantom_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_ftm']), 'FTM')
                ftm_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, ftm_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_ftm'],
                    'unit': 'FTM',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'cronos':
            info = await cronos_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_cro']), 'CRO')
                cro_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, cro_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_cro'],
                    'unit': 'CRO',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'gnosis':
            info = await gnosis_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_xdai']), 'xDAI')
                gnosis_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, gnosis_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_xdai'],
                    'unit': 'xDAI',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'moonbeam':
            info = await moonbeam_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_glmr']), 'GLMR')
                glmr_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, glmr_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_glmr'],
                    'unit': 'GLMR',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'tron':
            info = await tron_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_trx']), 'TRX')
                tron_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, tron_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_trx'],
                    'unit': 'TRX',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'xrp':
            info = await xrp_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_xrp']), 'XRP')
                xrp_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(float(t['balance_raw']))),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, xrp_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_xrp'],
                    'unit': 'XRP',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'hedera':
            info = await hedera_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_hbar']), 'HBAR')
                hedera_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, hedera_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_hbar'],
                    'unit': 'HBAR',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'multiversx':
            info = await multiversx_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_egld']), 'EGLD')
                mx_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, mx_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_egld'],
                    'unit': 'EGLD',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'sui':
            info = await sui_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_sui']), 'SUI')
                sui_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, sui_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_sui'],
                    'unit': 'SUI',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'aptos':
            info = await aptos_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_apt']), 'APT')
                apt_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, apt_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_apt'],
                    'unit': 'APT',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'filecoin':
            info = await filecoin_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_fil']), 'FIL')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_fil'],
                    'unit': 'FIL',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'litecoin':
            info = await litecoin_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_ltc']), 'LTC')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_ltc'],
                    'unit': 'LTC',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'dogecoin':
            info = await dogecoin_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_doge']), 'DOGE')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_doge'],
                    'unit': 'DOGE',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'zcash':
            info = await zcash_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_zec']), 'ZEC')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_zec'],
                    'unit': 'ZEC',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'tezos':
            info = await tezos_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_xtz']), 'XTZ')
                tezos_assets = [
                    {
                        'asset_id': t.get('contract', ''),
                        'policy_id': t.get('contract', ''),
                        'asset_name': t.get('symbol', '') or t.get('name', ''),
                        'quantity': str(int(t.get('balance_raw', '0'))),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, tezos_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_xtz'],
                    'unit': 'XTZ',
                    'token_count': len(tezos_assets),
                    'source': info.get('source')
                }

        elif blockchain == 'stacks':
            info = await stacks_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_stx']), 'STX')
                stx_assets = [
                    {
                        'asset_id': t.get('contract_id', t.get('token_id', '')),
                        'policy_id': t.get('contract_id', ''),
                        'asset_name': t.get('token_name', 'unknown'),
                        'quantity': str(int(t.get('balance', '0'))),
                        'decimals': t.get('decimals', 6)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, stx_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_stx'],
                    'unit': 'STX',
                    'token_count': len(stx_assets),
                    'source': info.get('source')
                }

        elif blockchain == 'vechain':
            info = await vechain_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_vet']), 'VET')
                vet_assets = []
                for t in info.get('tokens', []):
                    # VTHO token has no contract address, use symbol as ID
                    symbol = t.get('symbol', '')
                    raw_balance = float(t.get('balance', '0'))
                    decimals = t.get('decimals', 18)
                    vet_assets.append({
                        'asset_id': symbol,
                        'policy_id': symbol,
                        'asset_name': symbol,
                        'quantity': str(int(raw_balance * (10 ** decimals))),
                        'decimals': decimals
                    })
                await save_native_assets(wallet_id, vet_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_vet'],
                    'unit': 'VET',
                    'token_count': len(vet_assets),
                    'source': info.get('source')
                }

        elif blockchain == 'cosmos':
            info = await cosmos_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_atom']), 'ATOM')
                cosmos_assets = []
                for t in info.get('tokens', []):
                    denom = t.get('denom', '')
                    if denom == 'uatom':
                        continue  # Skip native ATOM, already saved as balance
                    cosmos_assets.append({
                        'asset_id': denom,
                        'policy_id': denom,
                        'asset_name': t.get('symbol', denom[:20]),
                        'quantity': str(int(t.get('amount_raw', '0'))),
                        'decimals': t.get('decimals') or 6
                    })
                await save_native_assets(wallet_id, cosmos_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_atom'],
                    'unit': 'ATOM',
                    'token_count': len(cosmos_assets),
                    'source': info.get('source')
                }

        elif blockchain == 'near':
            info = await near_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_near']), 'NEAR')
                near_assets = [
                    {
                        'asset_id': t.get('contract', ''),
                        'policy_id': t.get('contract', ''),
                        'asset_name': t.get('symbol', '') or t.get('name', ''),
                        'quantity': str(int(t.get('balance_raw', '0'))),
                        'decimals': t.get('decimals', 0)
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, near_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_near'],
                    'unit': 'NEAR',
                    'token_count': len(near_assets),
                    'source': info.get('source')
                }

        elif blockchain == 'icp':
            info = await icp_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_icp']), 'ICP')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_icp'],
                    'unit': 'ICP',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'kaia':
            info = await kaia_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_klay']), 'KLAY')
                kaia_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, kaia_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_klay'],
                    'unit': 'KLAY',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'osmosis':
            info = await osmosis_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_osmo']), 'OSMO')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_osmo'],
                    'unit': 'OSMO',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'celestia':
            info = await celestia_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_tia']), 'TIA')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_tia'],
                    'unit': 'TIA',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'injective':
            info = await injective_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_inj']), 'INJ')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_inj'],
                    'unit': 'INJ',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'dydx':
            info = await dydx_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_dydx']), 'DYDX')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_dydx'],
                    'unit': 'DYDX',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'sei':
            info = await sei_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_sei']), 'SEI')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_sei'],
                    'unit': 'SEI',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'akash':
            info = await akash_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_akt']), 'AKT')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_akt'],
                    'unit': 'AKT',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'ton':
            info = await ton_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_ton']), 'TON')
                ton_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, ton_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_ton'],
                    'unit': 'TON',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'polkadot':
            info = await polkadot_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_dot']), 'DOT')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_dot'],
                    'unit': 'DOT',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'kusama':
            info = await kusama_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_ksm']), 'KSM')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_ksm'],
                    'unit': 'KSM',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'stellar':
            info = await stellar_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_xlm']), 'XLM')
                stellar_assets = [
                    {
                        'asset_id': t['contract_address'],
                        'policy_id': t['contract_address'],
                        'asset_name': t['symbol'],
                        'quantity': str(int(t['balance_raw'])),
                        'decimals': t['decimals']
                    }
                    for t in info.get('tokens', [])
                ]
                await save_native_assets(wallet_id, stellar_assets)
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_xlm'],
                    'unit': 'XLM',
                    'token_count': info.get('token_count', 0),
                    'source': info.get('source')
                }

        elif blockchain == 'kaspa':
            info = await kaspa_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_kas']), 'KAS')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_kas'],
                    'unit': 'KAS',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'ergo':
            info = await ergo_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_erg']), 'ERG')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_erg'],
                    'unit': 'ERG',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'iota':
            info = await iota_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_iota']), 'IOTA')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_iota'],
                    'unit': 'IOTA',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'waves':
            info = await waves_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_waves']), 'WAVES')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_waves'],
                    'unit': 'WAVES',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'mina':
            info = await mina_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_mina']), 'MINA')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_mina'],
                    'unit': 'MINA',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'zilliqa':
            info = await zilliqa_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_zil']), 'ZIL')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_zil'],
                    'unit': 'ZIL',
                    'token_count': 0,
                    'source': info.get('source')
                }

        elif blockchain == 'monero':
            # Monero: fully private, manual balance only
            # The address is stored for reference only - we cannot query balances
            existing_balance = await get_stored_balance(wallet_id, 'XMR')
            manual_balance = float(existing_balance) if existing_balance else 0.0
            return {
                'address': address,
                'success': True,
                'balance': manual_balance,
                'unit': 'XMR',
                'token_count': 0,
                'source': 'manual',
                'manual': True,
                'privacy_note': 'Monero balances cannot be fetched publicly. Set balance manually.'
            }

        elif blockchain == 'secret_network':
            info = await secret_network_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_scrt']), 'SCRT')
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_scrt'],
                    'unit': 'SCRT',
                    'token_count': 0,
                    'source': info.get('source')
                }

        return {
            'address': address,
            'success': False,
            'error': 'Failed to fetch balance'
        }

    except Exception as e:
        return {
            'address': address,
            'success': False,
            'error': str(e)
        }


async def _trigger_tx_history(user_id: int, wallet_id: int, blockchain: str):
    """Fire-and-forget transaction history fetch for a newly added wallet."""
    try:
        await transaction_history_service.fetch_transactions(
            user_id, days=30, blockchain=blockchain, wallet_ids=[wallet_id]
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Auto tx-history fetch failed for wallet {wallet_id}: {e}")


async def _trigger_balance_history(user_id: int, wallet_id: int, blockchain: str):
    """Fire-and-forget balance history collection for a newly added wallet."""
    try:
        from engine.orchestrator import backfill_orchestrator
        from engine.models import BackfillRequest, ChainId, WorkDomain
        from engine import db as engine_db

        try:
            chain = ChainId(blockchain)
        except ValueError:
            return  # Chain not supported by V2 engine

        request = BackfillRequest(
            chains=[chain],
            wallet_ids=[wallet_id],
            domains=[WorkDomain.INDEX, WorkDomain.HYDRATE, WorkDomain.NORMALIZE, WorkDomain.ENRICH_PRICE],
        )
        backfill_id = await backfill_orchestrator.plan_backfill(user_id, request)
        run_id = await engine_db.create_scheduler_run(user_id, backfill_id, 'auto_wallet_add')
        backfill_orchestrator.set_run_id(backfill_id, run_id)
        await backfill_orchestrator.run_backfill(backfill_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Auto balance-history for wallet {wallet_id}: {e}")


@router.post("/discover")
async def discover_related_wallets(data: dict, user_id: int = Depends(verify_session)):
    """
    Discover all Cardano wallets related to a given address or stake key.

    If a stake address (stake1) is provided, finds all payment addresses.
    If a payment address (addr1) is provided, derives the stake key first.

    Returns list of addresses with balances and whether they're already tracked.
    """
    address = data.get('address', '').strip()

    if not address:
        raise HTTPException(status_code=400, detail="Address is required")

    # Determine if it's a stake address or payment address
    stake_address = None

    if address.startswith('stake1'):
        stake_address = address
    elif address.startswith('addr1'):
        # Derive stake address from payment address
        stake_address = await cardano_service.get_stake_address(address)
        if not stake_address:
            # Address might not have a stake component (enterprise address)
            return {
                'stake_address': None,
                'input_address': address,
                'is_enterprise': True,
                'addresses': [{
                    'address': address,
                    'balance_ada': 0,
                    'has_utxos': False,
                    'already_tracked': await get_wallet_by_address(address, 'cardano') is not None
                }],
                'total_addresses': 1,
                'total_with_utxos': 0,
                'already_tracked_count': 1 if await get_wallet_by_address(address, 'cardano') else 0
            }
    else:
        raise HTTPException(status_code=400, detail="Address must be a Cardano address (addr1) or stake key (stake1)")

    # Get all addresses under this stake key
    payment_addresses = await cardano_service.get_addresses_from_stake(stake_address)

    if not payment_addresses:
        return {
            'stake_address': stake_address,
            'input_address': address,
            'addresses': [],
            'total_addresses': 0,
            'total_with_utxos': 0,
            'already_tracked_count': 0,
            'message': 'No payment addresses found for this stake key'
        }

    # Get balance info for each address and check if already tracked
    addresses_info = []
    total_with_utxos = 0
    already_tracked = 0

    for addr in payment_addresses:
        # Check if already tracked
        is_tracked = await get_wallet_by_address(addr, 'cardano') is not None
        if is_tracked:
            already_tracked += 1

        # Get balance info
        addr_info = await cardano_service.get_address_info(addr)
        balance_ada = 0
        has_utxos = False

        if addr_info:
            balance_ada = float(addr_info.get('balance_ada', 0))
            has_utxos = balance_ada > 0 or len(addr_info.get('native_assets', [])) > 0
            if has_utxos:
                total_with_utxos += 1

        addresses_info.append({
            'address': addr,
            'address_short': f"{addr[:15]}...{addr[-8:]}",
            'balance_ada': balance_ada,
            'has_utxos': has_utxos,
            'already_tracked': is_tracked
        })

    # Sort: addresses with UTXOs first, then by balance
    addresses_info.sort(key=lambda x: (-x['has_utxos'], -x['balance_ada']))

    return {
        'stake_address': stake_address,
        'input_address': address,
        'addresses': addresses_info,
        'total_addresses': len(addresses_info),
        'total_with_utxos': total_with_utxos,
        'already_tracked_count': already_tracked,
        'new_addresses_count': len(addresses_info) - already_tracked
    }


@router.post("/add-multiple")
async def add_multiple_wallets(data: dict, user_id: int = Depends(verify_session)):
    """
    Add multiple Cardano wallets at once.
    Used after discover to add selected addresses.
    """
    addresses = data.get('addresses', [])
    label = data.get('label')

    if not addresses:
        raise HTTPException(status_code=400, detail="No addresses provided")

    added = 0
    skipped = 0

    for addr in addresses:
        # Check if already exists
        existing = await get_wallet_by_address(addr, 'cardano')
        if existing:
            skipped += 1
            continue

        try:
            await save_wallet(addr, 'cardano', label, user_id)
            append_to_wallets_file(f"cardano:{addr}", label)
            added += 1

            # Refresh balance in background (don't wait)
            saved = await get_wallet_by_address(addr, 'cardano')
            if saved:
                try:
                    await _refresh_wallet_balance(saved)
                except Exception as e:
                    print(f"Warning: Failed to refresh {addr[:20]}...: {e}")
        except Exception as e:
            print(f"Error adding {addr[:20]}...: {e}")
            skipped += 1

    return {
        'message': f'Added {added} wallets' + (f', {skipped} skipped' if skipped else ''),
        'added': added,
        'skipped': skipped
    }


@router.post("/xpub/discover")
async def discover_xpub_addresses(data: dict, user_id: int = Depends(verify_session)):
    """
    Discover all used addresses from a Bitcoin extended public key (xpub/ypub/zpub).

    Uses gap limit approach: scans until finding N consecutive unused addresses.

    Supports:
        - xpub: BIP44 Legacy addresses (1)
        - ypub: BIP49 Nested SegWit addresses (3)
        - zpub: BIP84 Native SegWit addresses (bc1)
    """
    xpub = data.get('xpub', '').strip()
    gap_limit = data.get('gap_limit', 20)
    max_addresses = data.get('max_addresses', 100)

    if not xpub:
        raise HTTPException(status_code=400, detail="xpub is required")

    if not is_bitcoin_xpub(xpub):
        raise HTTPException(
            status_code=400,
            detail="Invalid extended public key. Must start with xpub, ypub, or zpub"
        )

    if not bitcoin_service.xpub_available():
        raise HTTPException(
            status_code=503,
            detail="xpub support not available. Install bip_utils package."
        )

    # Discover addresses
    result = await bitcoin_service.discover_xpub_addresses(
        xpub,
        gap_limit=gap_limit,
        max_addresses=max_addresses
    )

    if 'error' in result:
        raise HTTPException(status_code=400, detail=result.get('message', result['error']))

    # Check which addresses are already tracked
    for addr in result.get('addresses', []):
        existing = await get_wallet_by_address(addr['address'], 'bitcoin')
        addr['already_tracked'] = existing is not None

    already_tracked = sum(1 for a in result.get('addresses', []) if a.get('already_tracked'))
    result['already_tracked_count'] = already_tracked
    result['new_addresses_count'] = result['total_addresses'] - already_tracked

    return result


@router.post("/xpub/add")
async def add_xpub_addresses(data: dict, user_id: int = Depends(verify_session)):
    """
    Add discovered Bitcoin addresses from an xpub.

    Can add all discovered addresses or a selected subset.
    """
    xpub = data.get('xpub', '').strip()
    addresses = data.get('addresses', [])  # List of addresses to add
    add_all = data.get('add_all', False)
    label_prefix = data.get('label', 'xpub')
    gap_limit = data.get('gap_limit', 20)

    if not xpub and not addresses:
        raise HTTPException(status_code=400, detail="xpub or addresses required")

    # If add_all, discover and add all addresses
    if add_all and xpub:
        if not bitcoin_service.xpub_available():
            raise HTTPException(
                status_code=503,
                detail="xpub support not available. Install bip_utils package."
            )

        discovery = await bitcoin_service.discover_xpub_addresses(xpub, gap_limit=gap_limit)
        if 'error' in discovery:
            raise HTTPException(status_code=400, detail=discovery.get('message', discovery['error']))

        addresses = [a['address'] for a in discovery.get('addresses', [])]

    if not addresses:
        return {
            'message': 'No addresses to add',
            'added': 0,
            'skipped': 0
        }

    added = 0
    skipped = 0
    xpub_short = f"{xpub[:8]}...{xpub[-4:]}" if xpub else "manual"

    for addr in addresses:
        # Handle both string addresses and dict format
        address = addr if isinstance(addr, str) else addr.get('address', '')
        if not address:
            continue

        # Check if already tracked
        existing = await get_wallet_by_address(address, 'bitcoin')
        if existing:
            skipped += 1
            continue

        try:
            # Create label with xpub reference
            label = f"{label_prefix} ({xpub_short})"
            await save_wallet(address, 'bitcoin', label, user_id)
            append_to_wallets_file(f"bitcoin:{address}", label)
            added += 1

            # Refresh balance
            saved = await get_wallet_by_address(address, 'bitcoin')
            if saved:
                try:
                    await _refresh_wallet_balance(saved)
                except Exception as e:
                    print(f"Warning: Failed to refresh {address[:15]}...: {e}")

        except Exception as e:
            print(f"Error adding {address[:15]}...: {e}")
            skipped += 1

    return {
        'message': f'Added {added} Bitcoin addresses from xpub' + (f', {skipped} skipped' if skipped else ''),
        'xpub': xpub[:20] + '...' if xpub else None,
        'added': added,
        'skipped': skipped
    }


@router.get("/xpub/status")
async def xpub_status(user_id: int = Depends(verify_session)):
    """Check if xpub support is available."""
    return {
        'available': bitcoin_service.xpub_available(),
        'message': 'bip_utils installed' if bitcoin_service.xpub_available() else 'Install bip_utils for xpub support'
    }


@router.post("")
async def add_wallet(wallet: WalletCreate, user_id: int = Depends(verify_session)):
    """
    Add a new wallet to track.
    Stake addresses (stake1) are automatically expanded to their associated payment addresses.
    Extended public keys (xpub/ypub/zpub) are expanded to their derived addresses.
    Also appends the wallet to wallets.txt for persistence across container rebuilds.
    """
    # Demo mode: block wallet creation
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await demo_wallet_service.add_wallet(wallet.address, "demo", wallet.label)

    import traceback

    try:
        address = wallet.address.strip()

        # ADA Handle resolution: if input starts with '$', resolve to Cardano address
        resolved_ada_handle = None
        if address.startswith('$'):
            resolved_address = await cardano_service.resolve_ada_handle(address)
            if not resolved_address:
                raise HTTPException(
                    status_code=404,
                    detail=f"ADA Handle '{address}' not found. Make sure the handle exists and is currently held."
                )
            resolved_ada_handle = address  # Store the original handle (e.g., '$chriscata')
            address = resolved_address  # Use the resolved Cardano address

        blockchain = detect_blockchain(address)

        if not blockchain:
            raise HTTPException(
                status_code=400,
                detail="Could not detect blockchain. Supported: Cardano (addr1, stake1, $handle), Bitcoin (1, 3, bc1, xpub/ypub/zpub), Ethereum (0x 42-char), Polygon (polygon:0x), Base (base:0x), Solana (base58), BNB Chain (bsc:0x), Arbitrum (arb:0x), Avalanche (avax:0x), Tron (T...), XRP (r...), Hedera (0.0.N), MultiversX (erd1...), Sui (0x 66-char), Aptos (aptos:0x), Filecoin (f1/f3...), Litecoin (L/M/ltc1), Dogecoin (D...), Zcash (t1/t3), Tezos (tz1/KT1), Stacks (SP...), VeChain (vet:0x), Cosmos (cosmos1...), NEAR (*.near), ICP (icp:...), TON (EQ/UQ...), Polkadot (polkadot:...), Kusama (kusama:...), Stellar (G...), Kaspa (kaspa:...), Osmosis (osmo1...), Celestia (celestia1...), Injective (inj1...), dYdX (dydx1...), Sei (sei1...), Akash (akash1...), Kaia (kaia:0x), Ergo (9...), IOTA (iota:0x), Waves (3P...), Mina (B62...), Zilliqa (zil1/0x), Monero (monero:4.../8...), Secret Network (secret1...)"
            )

        # Extract raw address if chain prefix was provided
        raw_address = address
        if ':' in address:
            parts = address.split(':', 1)
            chain_prefix = parts[0].lower()
            if chain_prefix in ('cardano', 'bitcoin', 'ethereum', 'eth', 'polygon', 'matic', 'base', 'solana', 'sol', 'algorand', 'algo', 'bsc', 'bnb', 'arb', 'arbitrum', 'avax', 'avalanche', 'tron', 'trx', 'xrp', 'ripple', 'hedera', 'hbar', 'multiversx', 'egld', 'elrond', 'sui', 'aptos', 'apt', 'filecoin', 'fil', 'litecoin', 'ltc', 'dogecoin', 'doge', 'zcash', 'zec', 'tezos', 'xtz', 'stacks', 'stx', 'vechain', 'vet', 'cosmos', 'atom', 'near', 'icp', 'ton', 'polkadot', 'dot', 'kusama', 'ksm', 'stellar', 'xlm', 'kaspa', 'kas', 'osmosis', 'osmo', 'celestia', 'tia', 'injective', 'inj', 'dydx', 'sei', 'akash', 'akt', 'kaia', 'klay', 'ergo', 'erg', 'iota', 'waves', 'mina', 'zilliqa', 'zil', 'monero', 'xmr', 'secret_network', 'secret', 'scrt'):
                raw_address = parts[1]
        address = raw_address

        # Handle stake addresses specially
        if is_stake_address(address):
            payment_addresses = await cardano_service.get_addresses_from_stake(address)

            if not payment_addresses:
                raise HTTPException(
                    status_code=404,
                    detail="No payment addresses found for this stake address. It may be inactive."
                )

            added_count = 0
            for pay_addr in payment_addresses:
                label = wallet.label or f"From stake: {address[:20]}..."
                await save_wallet(pay_addr, 'cardano', label, user_id)
                # Append each payment address to wallets.txt
                append_to_wallets_file(pay_addr, label)
                saved = await get_wallet_by_address(pay_addr)
                if saved:
                    try:
                        await _refresh_wallet_balance(saved)
                    except Exception as e:
                        print(f"Warning: Failed to refresh balance for {pay_addr}: {e}")
                added_count += 1

            # Also save the original stake address to wallets.txt for reference
            append_to_wallets_file(address, wallet.label)

            # Fire-and-forget tx history fetch for all newly added Cardano addresses
            asyncio.create_task(transaction_history_service.fetch_transactions(user_id, days=30, blockchain='cardano'))

            return {
                "message": f"Stake address expanded to {added_count} payment address(es)",
                "stake_address": address,
                "blockchain": blockchain,
                "payment_addresses_added": added_count,
                "saved_to_file": True
            }

        # Handle Bitcoin extended public keys (xpub/ypub/zpub)
        if is_bitcoin_xpub(address):
            if not bitcoin_service.xpub_available():
                raise HTTPException(
                    status_code=503,
                    detail="xpub support not available. Install bip_utils package."
                )

            # Discover all addresses with balance
            discovery = await bitcoin_service.discover_xpub_addresses(address, gap_limit=20)

            if 'error' in discovery:
                raise HTTPException(
                    status_code=400,
                    detail=discovery.get('message', discovery['error'])
                )

            discovered_addresses = discovery.get('addresses', [])
            if not discovered_addresses:
                raise HTTPException(
                    status_code=404,
                    detail="No addresses with balance found for this xpub. It may be unused."
                )

            added_count = 0
            xpub_short = f"{address[:8]}...{address[-4:]}"

            for addr_info in discovered_addresses:
                addr = addr_info['address']
                # Check if already exists
                existing = await get_wallet_by_address(addr, 'bitcoin')
                if existing:
                    continue

                label = wallet.label or f"xpub ({xpub_short})"
                await save_wallet(addr, 'bitcoin', label, user_id)
                append_to_wallets_file(f"bitcoin:{addr}", label)

                saved = await get_wallet_by_address(addr, 'bitcoin')
                if saved:
                    try:
                        await _refresh_wallet_balance(saved)
                    except Exception as e:
                        print(f"Warning: Failed to refresh balance for {addr[:15]}...: {e}")
                added_count += 1

            # Fire-and-forget tx history fetch for all newly added Bitcoin addresses
            asyncio.create_task(transaction_history_service.fetch_transactions(user_id, days=30, blockchain='bitcoin'))

            return {
                "message": f"xpub expanded to {added_count} Bitcoin address(es)",
                "xpub": xpub_short,
                "xpub_type": discovery.get('address_type'),
                "blockchain": "bitcoin",
                "addresses_added": added_count,
                "total_balance_btc": discovery.get('total_balance_btc'),
                "saved_to_file": True
            }

        # Regular address handling
        await save_wallet(address, blockchain, wallet.label, user_id)

        # If this was an ADA Handle resolution, store the handle on the wallet
        if resolved_ada_handle:
            saved_for_handle = await get_wallet_by_address(address, blockchain)
            if saved_for_handle:
                await update_wallet_ada_handle(saved_for_handle['id'], resolved_ada_handle)

        # Append to wallets.txt
        file_saved = append_to_wallets_file(address, wallet.label)

        # Immediately fetch balance (don't fail the request if this fails)
        saved_wallet = await get_wallet_by_address(address, blockchain)
        if saved_wallet:
            try:
                await _refresh_wallet_balance(saved_wallet)
            except Exception as e:
                print(f"Warning: Failed to refresh balance for {address}: {e}")
            # Fire-and-forget tx history + balance history for the newly added wallet
            asyncio.create_task(_trigger_tx_history(user_id, saved_wallet['id'], blockchain))
            asyncio.create_task(_trigger_balance_history(user_id, saved_wallet['id'], blockchain))

        response_data = {
            "message": "Wallet added",
            "address": address,
            "blockchain": blockchain,
            "saved_to_file": file_saved
        }
        if resolved_ada_handle:
            response_data["ada_handle"] = resolved_ada_handle
            response_data["message"] = f"Wallet added via ADA Handle {resolved_ada_handle}"
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding wallet: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to add wallet: {str(e)}")


@router.delete("/stake-group/{stake_address}")
async def delete_stake_group(stake_address: str, user_id: int = Depends(verify_session)):
    """Delete all wallets belonging to a Cardano stake key group."""
    from database import delete_wallet as db_delete_wallet

    # Demo mode: block deletion
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"message": "Demo mode: Not deleted", "deleted": 0, "demo_mode": True}

    if not is_stake_address(stake_address):
        raise HTTPException(status_code=400, detail="Invalid stake address")

    # Get all Cardano wallets for this user
    all_wallets = await get_all_wallets(user_id=user_id)
    cardano_wallets = [w for w in all_wallets if w['blockchain'] == 'cardano']

    # Resolve stake keys and find matches
    wallets_to_delete = []
    for wallet in cardano_wallets:
        if wallet['address'].startswith('addr1'):
            try:
                wallet_stake = await cardano_service.get_stake_address(wallet['address'])
                if wallet_stake == stake_address:
                    wallets_to_delete.append(wallet)
            except Exception:
                continue

    if not wallets_to_delete:
        raise HTTPException(status_code=404, detail="No wallets found for this stake key")

    deleted = 0
    for wallet in wallets_to_delete:
        await db_delete_wallet(wallet['id'])
        remove_from_wallets_file(wallet['address'])
        deleted += 1

    return {"message": f"Deleted {deleted} wallet(s)", "deleted": deleted, "stake_address": stake_address}


@router.put("/stake-group/{stake_address}/label")
async def update_stake_group_label(stake_address: str, data: dict, user_id: int = Depends(verify_session)):
    """Update the label for all wallets in a Cardano stake key group."""
    import aiosqlite
    from config import DATABASE_PATH

    # Demo mode: block updates
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"message": "Demo mode: Not updated", "demo_mode": True}

    label = data.get('label', '').strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label is required")

    if not is_stake_address(stake_address):
        raise HTTPException(status_code=400, detail="Invalid stake address")

    # Get all Cardano wallets for this user
    all_wallets = await get_all_wallets(user_id=user_id)
    cardano_wallets = [w for w in all_wallets if w['blockchain'] == 'cardano']

    # Resolve stake keys and find matches
    wallet_ids = []
    for wallet in cardano_wallets:
        if wallet['address'].startswith('addr1'):
            try:
                wallet_stake = await cardano_service.get_stake_address(wallet['address'])
                if wallet_stake == stake_address:
                    wallet_ids.append(wallet['id'])
            except Exception:
                continue

    if not wallet_ids:
        raise HTTPException(status_code=404, detail="No wallets found for this stake key")

    # Update label on all matching wallets
    async with aiosqlite.connect(DATABASE_PATH) as db:
        placeholders = ','.join('?' * len(wallet_ids))
        await db.execute(
            f"UPDATE wallets SET label = ? WHERE id IN ({placeholders})",
            [label] + wallet_ids
        )
        await db.commit()

    return {"message": "Label updated", "updated": len(wallet_ids), "label": label}


@router.patch("/{address}")
async def update_wallet(address: str, update: WalletUpdate, user_id: int = Depends(verify_session)):
    """Update wallet label."""
    from database import update_wallet_label

    wallet = await get_wallet_by_address(address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    await update_wallet_label(address, update.label)
    return {"message": "Wallet updated", "address": address, "label": update.label}


def remove_from_wallets_file(address: str) -> bool:
    """
    Remove a wallet address from wallets.txt.

    Args:
        address: The wallet address to remove

    Returns:
        True if successful, False otherwise
    """
    try:
        if not WALLETS_FILE.exists():
            return True

        # Read all lines
        with open(WALLETS_FILE, 'r') as f:
            lines = f.readlines()

        # Filter out the address
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                new_lines.append(line)
                continue

            # Extract address from line (handle prefix and comments)
            addr = stripped.split(':')[-1].split('#')[0].strip()
            if addr != address:
                new_lines.append(line)

        # Write back
        with open(WALLETS_FILE, 'w') as f:
            f.writelines(new_lines)

        return True
    except Exception as e:
        print(f"Error removing from wallets.txt: {e}")
        return False


@router.delete("/{address:path}")
async def delete_wallet(address: str, user_id: int = Depends(verify_session)):
    """Delete a wallet and all its associated data, including from wallets.txt."""
    # Demo mode: block deletion
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return {"message": "Demo mode: Wallet not actually deleted", "address": address, "demo_mode": True}

    from database import delete_wallet as db_delete_wallet

    # Parse chain:address format if present
    blockchain = None
    raw_address = address
    if ':' in address:
        parts = address.split(':', 1)
        chain_prefix = parts[0].lower()
        if chain_prefix in ('cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana', 'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron', 'xrp', 'hedera', 'multiversx', 'sui', 'aptos', 'filecoin', 'litecoin', 'dogecoin', 'zcash', 'tezos', 'stacks', 'vechain', 'cosmos', 'near', 'icp', 'ton', 'polkadot', 'kusama', 'stellar', 'kaspa', 'osmosis', 'celestia', 'injective', 'dydx', 'sei', 'akash', 'kaia', 'ergo', 'iota', 'waves', 'mina', 'zilliqa'):
            blockchain = chain_prefix
            raw_address = parts[1]

    # Try to find wallet with raw address first
    wallet = await get_wallet_by_address(raw_address, blockchain)

    # If not found, try with full prefixed address (for backwards compatibility)
    if not wallet and blockchain:
        wallet = await get_wallet_by_address(address, blockchain)

    # If still not found and no blockchain specified, try raw address without blockchain filter
    if not wallet:
        wallet = await get_wallet_by_address(raw_address)

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    await db_delete_wallet(wallet['id'])

    # Also remove from wallets.txt (try both formats)
    file_removed = remove_from_wallets_file(address) or remove_from_wallets_file(raw_address)

    return {"message": "Wallet deleted", "address": address, "removed_from_file": file_removed}


@router.put("/{wallet_id}/label")
async def update_wallet_label(wallet_id: int, data: dict, user_id: int = Depends(verify_session)):
    """Update the label for a wallet."""
    import aiosqlite
    from database import DATABASE_PATH

    label = data.get('label')

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE wallets SET label = ? WHERE id = ?",
            (label, wallet_id)
        )
        await db.commit()

    return {"message": "Label updated", "wallet_id": wallet_id, "label": label}


@router.get("/stake/{stake_address}")
async def get_stake_address_info(stake_address: str, user_id: int = Depends(verify_session)):
    """
    Get comprehensive information for a Cardano stake address.
    Returns account info, all associated payment addresses, and aggregated totals.
    """
    if not is_stake_address(stake_address):
        raise HTTPException(
            status_code=400,
            detail="Invalid stake address. Must start with 'stake1'"
        )

    totals = await cardano_service.get_stake_address_totals(stake_address)

    if not totals:
        raise HTTPException(
            status_code=404,
            detail="Stake address not found or API error"
        )

    return totals


@router.get("/{address}/governance")
async def get_wallet_governance(address: str, refresh: bool = False, user_id: int = Depends(verify_session)):
    """
    Get governance and staking info for a Cardano wallet.
    Includes staking pool, DRep delegation, and pending rewards.
    """
    # Demo user intercept
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return demo_defi_service.get_governance_info(address)

    if not address.startswith('addr1'):
        raise HTTPException(
            status_code=400,
            detail="Governance info only available for Cardano addresses"
        )

    cache_key = f"governance_{address}"

    if not refresh:
        cached = await get_cache(cache_key)
        if cached:
            cached['from_cache'] = True
            return cached

    gov_info = await cardano_service.get_wallet_governance_info(address)

    if not gov_info:
        raise HTTPException(
            status_code=404,
            detail="Could not fetch governance info"
        )

    gov_info['from_cache'] = False
    await set_cache(cache_key, gov_info, CACHE_TTL_COLD)

    return gov_info


@router.get("/ethereum/status")
async def get_ethereum_api_status(user_id: int = Depends(verify_session)):
    """Get Ethereum API (beaconcha.in) status and rate limit info."""
    return ethereum_service.get_rate_limit_status()


@router.post("/ethereum/clear-cache")
async def clear_ethereum_cache(user_id: int = Depends(verify_session)):
    """Clear Ethereum balance cache to force fresh fetches."""
    ethereum_service.clear_cache()
    return {"message": "Ethereum cache cleared"}


@router.post("/assets/{asset_id}/toggle-ignore")
async def toggle_asset_ignore(asset_id: int, user_id: int = Depends(verify_session)):
    """Toggle the ignore flag for a native asset."""
    import aiosqlite
    from config import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Verify asset belongs to user
        cursor = await db.execute(
            "SELECT id, ignored FROM native_assets WHERE id = ? AND user_id = ?",
            (asset_id, user_id)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Asset not found")

        current_ignored = row[1] or 0
        new_ignored = 1 if current_ignored == 0 else 0

        # Toggle the ignore flag
        await db.execute(
            "UPDATE native_assets SET ignored = ?, updated_at = ? WHERE id = ?",
            (new_ignored, datetime.now(), asset_id)
        )
        await db.commit()

        return {
            "asset_id": asset_id,
            "ignored": new_ignored == 1,
            "message": "Asset ignored" if new_ignored == 1 else "Asset included"
        }


@router.get("/solana/status")
async def get_solana_api_status(user_id: int = Depends(verify_session)):
    """Get Solana API (Helius) status and cache info."""
    return await solana_service.get_rate_limit_status()


@router.post("/solana/clear-cache")
async def clear_solana_cache(user_id: int = Depends(verify_session)):
    """Clear Solana balance cache to force fresh fetches."""
    solana_service.clear_cache()
    return {"message": "Solana cache cleared"}
