from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_all_wallets, get_wallet_by_address, save_wallet,
    save_balance, clear_wallet_balances, save_native_assets,
    get_wallet_assets, get_wallet_balance
)
from services.cardano import cardano_service, is_stake_address
from services.bitcoin import bitcoin_service
from services.ethereum import ethereum_service
from services.solana import solana_service
from services.polygon import polygon_service
from services.base import base_service
from services.logging_service import get_logging_service
from services.demo_wallet_service import demo_wallet_service
from utils.address import parse_wallets_file, detect_blockchain, is_bitcoin_xpub, get_xpub_type
from config import WALLETS_FILE, DATA_DIR
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session


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
    balance: Optional[str] = None
    balance_native: Optional[str] = None
    native_assets: Optional[list] = None

@router.get("")
async def list_wallets(username: str = Depends(verify_session)):
    """List all tracked wallets with their current balances and stake keys."""
    log_service = get_logging_service()

    # Check if demo user - return fake data
    if await is_demo_user(username):
        demo_wallets = await demo_wallet_service.get_all_wallets()
        return {
            "wallets": demo_wallets,
            "total": len(demo_wallets),
            "demo_mode": True
        }

    try:
        wallets = await get_all_wallets()
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

@router.get("/{address}")
async def get_wallet(address: str):
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
async def sync_wallets_from_file():
    """
    Sync wallets from the wallets.txt file.
    Stake addresses (stake1...) are automatically expanded to their associated payment addresses.
    """
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
                    await save_wallet(pay_addr, 'cardano', f"From stake: {address[:20]}...")
                    synced += 1
                    expanded_from_stake += 1
            else:
                # Save the stake address itself if no payment addresses found
                await save_wallet(address, wallet['blockchain'])
                synced += 1
        else:
            await save_wallet(address, wallet['blockchain'])
            synced += 1

    # Now refresh all wallet balances in parallel (with concurrency limit)
    all_wallets = await get_all_wallets()

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
async def refresh_all_balances():
    """Refresh balances for all tracked wallets in parallel."""
    wallets = await get_all_wallets()

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
        await clear_cache("portfolio_summary")
        # Trigger cache repopulation by calling portfolio summary
        try:
            from routers.portfolio import get_portfolio_summary
            await get_portfolio_summary(refresh=True)
        except Exception as e:
            import logging
            logging.warning(f"Could not repopulate portfolio cache: {e}")

    return {
        "message": f"Refreshed {success_count}/{len(wallets)} wallets",
        "refreshed": success_count,
        "results": list(results)
    }

@router.post("/{address}/refresh")
async def refresh_wallet_balance(address: str):
    """Refresh balance for a specific wallet."""
    wallet = await get_wallet_by_address(address)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    return await _refresh_wallet_balance(wallet)

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
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_ada'],
                    'unit': 'ADA',
                    'native_assets_count': len(info['native_assets']),
                    'source': info['source']
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
            if not ethereum_service.is_configured():
                return {
                    'address': address,
                    'success': False,
                    'error': 'Beaconcha.in API key not configured'
                }

            info = await ethereum_service.get_address_balance(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH')
                # Save ERC-20 tokens as native assets
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
                return {
                    'address': address,
                    'success': True,
                    'balance': info['balance_eth'],
                    'unit': 'ETH',
                    'token_count': info.get('token_count', 0),
                    'source': 'beaconcha.in'
                }

        elif blockchain == 'solana':
            if not solana_service.is_configured():
                return {
                    'address': address,
                    'success': False,
                    'error': 'Helius API key not configured'
                }

            info = await solana_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_sol']), 'SOL')
                # Save SPL tokens as native assets
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
                    'token_count': info.get('token_count', 0),
                    'source': 'helius'
                }

        elif blockchain == 'polygon':
            if not polygon_service.is_configured():
                return {
                    'address': address,
                    'success': False,
                    'error': 'Alchemy API key not configured for Polygon'
                }

            info = await polygon_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_matic']), 'MATIC')
                # Save ERC-20 tokens as native assets
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
                    'source': 'alchemy'
                }

        elif blockchain == 'base':
            if not base_service.is_configured():
                return {
                    'address': address,
                    'success': False,
                    'error': 'Alchemy API key not configured for Base'
                }

            info = await base_service.get_address_info(address)
            if info:
                await clear_wallet_balances(wallet_id)
                await save_balance(wallet_id, str(info['balance_eth']), 'ETH_BASE')
                # Save ERC-20 tokens as native assets
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
                    'source': 'alchemy'
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


@router.post("/discover")
async def discover_related_wallets(data: dict):
    """
    Discover all Cardano wallets related to a given address or stake key.

    If a stake address (stake1...) is provided, finds all payment addresses.
    If a payment address (addr1...) is provided, derives the stake key first.

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
        raise HTTPException(status_code=400, detail="Address must be a Cardano address (addr1...) or stake key (stake1...)")

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
async def add_multiple_wallets(data: dict):
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
            await save_wallet(addr, 'cardano', label)
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
async def discover_xpub_addresses(data: dict):
    """
    Discover all used addresses from a Bitcoin extended public key (xpub/ypub/zpub).

    Uses gap limit approach: scans until finding N consecutive unused addresses.

    Supports:
        - xpub: BIP44 Legacy addresses (1...)
        - ypub: BIP49 Nested SegWit addresses (3...)
        - zpub: BIP84 Native SegWit addresses (bc1...)
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
async def add_xpub_addresses(data: dict):
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
            await save_wallet(address, 'bitcoin', label)
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
async def xpub_status():
    """Check if xpub support is available."""
    return {
        'available': bitcoin_service.xpub_available(),
        'message': 'bip_utils installed' if bitcoin_service.xpub_available() else 'Install bip_utils for xpub support'
    }


@router.post("")
async def add_wallet(wallet: WalletCreate):
    """
    Add a new wallet to track.
    Stake addresses (stake1...) are automatically expanded to their associated payment addresses.
    Extended public keys (xpub/ypub/zpub) are expanded to their derived addresses.
    Also appends the wallet to wallets.txt for persistence across container rebuilds.
    """
    import traceback

    try:
        address = wallet.address.strip()
        blockchain = detect_blockchain(address)

        if not blockchain:
            raise HTTPException(
                status_code=400,
                detail="Could not detect blockchain. Supported: Cardano (addr1..., stake1...), Bitcoin (1.., 3.., bc1.., xpub.., ypub.., zpub..), Ethereum (0x...), Polygon (polygon:0x...), Base (base:0x...), Solana (base58)"
            )

        # Extract raw address if chain prefix was provided
        raw_address = address
        if ':' in address:
            parts = address.split(':', 1)
            chain_prefix = parts[0].lower()
            if chain_prefix in ('cardano', 'bitcoin', 'ethereum', 'eth', 'polygon', 'matic', 'base', 'solana', 'sol'):
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
                await save_wallet(pay_addr, 'cardano', label)
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
                await save_wallet(addr, 'bitcoin', label)
                append_to_wallets_file(f"bitcoin:{addr}", label)

                saved = await get_wallet_by_address(addr, 'bitcoin')
                if saved:
                    try:
                        await _refresh_wallet_balance(saved)
                    except Exception as e:
                        print(f"Warning: Failed to refresh balance for {addr[:15]}...: {e}")
                added_count += 1

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
        await save_wallet(address, blockchain, wallet.label)

        # Append to wallets.txt
        file_saved = append_to_wallets_file(address, wallet.label)

        # Immediately fetch balance (don't fail the request if this fails)
        saved_wallet = await get_wallet_by_address(address, blockchain)
        if saved_wallet:
            try:
                await _refresh_wallet_balance(saved_wallet)
            except Exception as e:
                print(f"Warning: Failed to refresh balance for {address}: {e}")

        return {
            "message": "Wallet added",
            "address": address,
            "blockchain": blockchain,
            "saved_to_file": file_saved
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding wallet: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to add wallet: {str(e)}")


@router.patch("/{address}")
async def update_wallet(address: str, update: WalletUpdate):
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
async def delete_wallet(address: str):
    """Delete a wallet and all its associated data, including from wallets.txt."""
    from database import delete_wallet as db_delete_wallet

    # Parse chain:address format if present
    blockchain = None
    raw_address = address
    if ':' in address:
        parts = address.split(':', 1)
        chain_prefix = parts[0].lower()
        if chain_prefix in ('cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana'):
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
async def update_wallet_label(wallet_id: int, data: dict):
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
async def get_stake_address_info(stake_address: str):
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
async def get_wallet_governance(address: str):
    """
    Get governance and staking info for a Cardano wallet.
    Includes staking pool, DRep delegation, and pending rewards.
    """
    if not address.startswith('addr1'):
        raise HTTPException(
            status_code=400,
            detail="Governance info only available for Cardano addresses"
        )

    gov_info = await cardano_service.get_wallet_governance_info(address)

    if not gov_info:
        raise HTTPException(
            status_code=404,
            detail="Could not fetch governance info"
        )

    return gov_info


@router.get("/ethereum/status")
async def get_ethereum_api_status():
    """Get Ethereum API (beaconcha.in) status and rate limit info."""
    return ethereum_service.get_rate_limit_status()


@router.post("/ethereum/clear-cache")
async def clear_ethereum_cache():
    """Clear Ethereum balance cache to force fresh fetches."""
    ethereum_service.clear_cache()
    return {"message": "Ethereum cache cleared"}


@router.get("/solana/status")
async def get_solana_api_status():
    """Get Solana API (Helius) status and cache info."""
    return solana_service.get_rate_limit_status()


@router.post("/solana/clear-cache")
async def clear_solana_cache():
    """Clear Solana balance cache to force fresh fetches."""
    solana_service.clear_cache()
    return {"message": "Solana cache cleared"}
