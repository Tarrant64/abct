"""
Off-Chain Collector Service

Periodically collects off-chain balances (exchanges, staking, DeFi, NFTs)
and writes them to wallet_daily_balances. Replaces the V1 monolithic snapshot
for off-chain data collection.

Runs every 2 hours (same cadence as old V1 snapshot).
Reuses existing service methods from snapshot.py.
"""

import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CT_TIMEZONE = ZoneInfo("America/Chicago")
COLLECTION_INTERVAL_HOURS = 2


class OffchainCollector:
    """Collects off-chain balances and writes per-source daily rows."""

    def __init__(self):
        self._task: asyncio.Task = None
        self._pricing_service = None
        self._nft_service = None

    async def _get_pricing_service(self):
        if self._pricing_service is None:
            from services.pricing import pricing_service
            self._pricing_service = pricing_service
        return self._pricing_service

    async def _get_nft_service(self):
        if self._nft_service is None:
            from services.nft import nft_service
            self._nft_service = nft_service
        return self._nft_service

    async def _get_fresh_exchange_value(self, exchange_name: str, prices: dict, user_id: int) -> float:
        """Get exchange value, fetching live data if cache is expired."""
        from database import get_cache

        # Try cache first (populated by recent user activity or prior refresh)
        cache_key = f"{exchange_name}_portfolio"
        cached = await get_cache(cache_key, user_id=user_id)

        if cached and 'total_usd' in cached:
            return float(cached['total_usd'])

        if cached and 'assets' in cached:
            total = 0.0
            for asset in cached['assets']:
                currency = asset.get('currency', '').upper()
                balance = float(asset.get('balance', 0))
                if balance > 0:
                    p = prices.get(currency, {})
                    price = p.get('usd', 0) if isinstance(p, dict) else 0
                    total += balance * price
            return total

        # Cache miss — fetch live from the exchange API
        try:
            from routers.exchanges import process_exchange_portfolio
            import importlib

            service_map = {
                'binance': ('services.binance', 'binance_service'),
                'binance_us': ('services.binance_us', 'binance_us_service'),
                'okx': ('services.okx', 'okx_service'),
                'bitget': ('services.bitget', 'bitget_service'),
                'gate': ('services.gate', 'gate_service'),
                'kucoin': ('services.kucoin', 'kucoin_service'),
            }

            if exchange_name == 'coinbase':
                # Coinbase uses a different service method (get_portfolio_balances)
                from services.coinbase import coinbase_service
                if not await coinbase_service.is_configured(user_id=user_id):
                    return 0.0
                portfolio = await coinbase_service.get_portfolio_balances(user_id=user_id)
                return float(portfolio.get('total_usd', 0))

            entry = service_map.get(exchange_name)
            if not entry:
                logger.debug(f"Offchain collector: no service for {exchange_name}")
                return 0.0

            module = importlib.import_module(entry[0])
            service = getattr(module, entry[1])
            result = await process_exchange_portfolio(service, exchange_name, user_id, refresh=True)
            return float(result.get('total_usd', 0))
        except Exception as e:
            logger.warning(f"Offchain collector: live fetch for {exchange_name} failed: {e}")
            return 0.0

    async def collect_for_user(self, user_id: int):
        """Collect all off-chain balances for a user and write to wallet_daily_balances."""
        from database import (
            get_wallet_sources, upsert_wallet_daily_balance,
            get_all_wallets,
        )
        from services.offchain_helpers import (
            get_staking_value, get_defi_value, get_nft_value,
        )

        today = datetime.now(CT_TIMEZONE).strftime('%Y-%m-%d')
        pricing = await self._get_pricing_service()
        prices = await pricing.get_all_tracked_prices()
        ada_price = prices.get('ADA', {}).get('usd', 0)

        # --- Exchanges ---
        exchange_sources = await get_wallet_sources(user_id, source_type='exchange')
        for source in exchange_sources:
            try:
                exchange_name = source['source_key']
                value_usd = await self._get_fresh_exchange_value(
                    exchange_name, prices, user_id
                )

                await upsert_wallet_daily_balance(
                    user_id=user_id,
                    source_id=source['id'],
                    date=today,
                    value_usd=round(value_usd, 2),
                    metadata=json.dumps({'source': 'live', 'exchange': exchange_name}),
                )
                logger.debug(f"Offchain collector: {exchange_name} = ${value_usd:,.2f}")
            except Exception as e:
                logger.warning(f"Offchain collector: exchange {source['source_key']} failed: {e}")

        # --- Staking ---
        staking_sources = await get_wallet_sources(user_id, source_type='staking')
        if staking_sources:
            staking_total = await get_staking_value(prices, user_id=user_id)
            if staking_total > 0 and staking_sources:
                per_source = staking_total / len(staking_sources)
                for source in staking_sources:
                    try:
                        await upsert_wallet_daily_balance(
                            user_id=user_id,
                            source_id=source['id'],
                            date=today,
                            value_usd=round(per_source, 2),
                            metadata=json.dumps({'source': 'live'}),
                        )
                    except Exception as e:
                        logger.warning(f"Offchain collector: staking {source['source_key']} failed: {e}")
                logger.debug(f"Offchain collector: staking total = ${staking_total:,.2f}")

        # --- DeFi ---
        defi_sources = await get_wallet_sources(user_id, source_type='defi')
        if defi_sources:
            defi_total = await get_defi_value(prices, user_id=user_id)
            if defi_total > 0 and defi_sources:
                per_source = defi_total / len(defi_sources)
                for source in defi_sources:
                    try:
                        await upsert_wallet_daily_balance(
                            user_id=user_id,
                            source_id=source['id'],
                            date=today,
                            value_usd=round(per_source, 2),
                            metadata=json.dumps({'source': 'live'}),
                        )
                    except Exception as e:
                        logger.warning(f"Offchain collector: defi {source['source_key']} failed: {e}")
                logger.debug(f"Offchain collector: DeFi total = ${defi_total:,.2f}")

        # --- NFTs ---
        nft_sources = await get_wallet_sources(user_id, source_type='nft')
        if nft_sources:
            nft_total = await get_nft_value(ada_price, user_id=user_id)
            if nft_total > 0:
                try:
                    await upsert_wallet_daily_balance(
                        user_id=user_id,
                        source_id=nft_sources[0]['id'],
                        date=today,
                        value_usd=round(nft_total, 2),
                        metadata=json.dumps({'source': 'live'}),
                    )
                except Exception as e:
                    logger.warning(f"Offchain collector: NFT failed: {e}")
                logger.debug(f"Offchain collector: NFT total = ${nft_total:,.2f}")

        # --- On-Chain (today's live wallet values) ---
        # NOTE: V1 balance_history stored native-coin-only (token_value_usd = 0).
        # To maintain consistency with historical data, we only include native
        # balance × price here. Token values can be added once historical data
        # is backfilled with token values too.
        onchain_sources = await get_wallet_sources(user_id, source_type='on_chain')
        if onchain_sources:
            from database import get_wallet_balance

            chain_symbols = {
                'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH',
                'solana': 'SOL', 'polygon': 'MATIC', 'base': 'ETH',
                'algorand': 'ALGO', 'bsc': 'BNB', 'arbitrum': 'ETH',
                'avalanche': 'AVAX', 'tron': 'TRX',
            }
            onchain_total = 0.0
            for source in onchain_sources:
                wallet_id = source.get('wallet_id')
                if not wallet_id:
                    continue
                try:
                    chain = source.get('chain', '')
                    balance_info = await get_wallet_balance(wallet_id)
                    balance = float(balance_info['amount']) if balance_info else 0.0

                    symbol = chain_symbols.get(chain)
                    native_value_usd = 0.0
                    if balance > 0 and symbol:
                        price = prices.get(symbol, {})
                        native_price = price.get('usd', 0) if isinstance(price, dict) else 0
                        native_value_usd = balance * native_price

                    await upsert_wallet_daily_balance(
                        user_id=user_id,
                        source_id=source['id'],
                        date=today,
                        value_usd=round(native_value_usd, 2),
                        metadata=json.dumps({'source': 'live', 'chain': chain}),
                    )
                    onchain_total += native_value_usd
                except Exception as e:
                    logger.warning(f"Offchain collector: on-chain wallet {source.get('label', source['source_key'][:20])} failed: {e}")
            if onchain_total > 0:
                logger.debug(f"Offchain collector: on-chain total = ${onchain_total:,.2f}")

        # --- Tracked Tokens ---
        tracked_sources = await get_wallet_sources(user_id, source_type='tracked_tokens')
        if tracked_sources:
            try:
                from database import get_tracked_tokens, get_wallet_assets
                from services.defi import DEFI_PROTOCOLS

                tracked_tokens = await get_tracked_tokens()
                tracked_ids = {t['asset_id'] for t in tracked_tokens}

                if tracked_ids:
                    wallets = await get_all_wallets(user_id=user_id)
                    wallet_assets = await asyncio.gather(
                        *[get_wallet_assets(w['id']) for w in wallets]
                    )
                    asset_totals = {}
                    for wallet, assets in zip(wallets, wallet_assets):
                        for asset in assets:
                            aid = asset.get('asset_id', '')
                            if aid not in tracked_ids:
                                continue
                            if aid not in asset_totals:
                                asset_totals[aid] = {
                                    'quantity_raw': 0,
                                    'decimals': int(asset.get('decimals') or 0),
                                    'ticker': asset.get('ticker'),
                                    'policy_id': asset.get('policy_id', ''),
                                }
                            asset_totals[aid]['quantity_raw'] += float(asset.get('quantity') or 0)

                    tracked_total = 0.0
                    for aid, data in asset_totals.items():
                        decimals = data['decimals']
                        human_qty = data['quantity_raw'] / (10 ** decimals) if decimals > 0 else data['quantity_raw']
                        ticker = (data.get('ticker') or '').upper()
                        if not ticker:
                            continue
                        # Skip DeFi protocol tokens (already counted in DeFi total)
                        if data.get('policy_id', '') in DEFI_PROTOCOLS:
                            continue
                        price_info = prices.get(ticker, {})
                        price = price_info.get('usd', 0) if isinstance(price_info, dict) else 0
                        if price > 0:
                            tracked_total += human_qty * price

                    if tracked_total > 0:
                        await upsert_wallet_daily_balance(
                            user_id=user_id,
                            source_id=tracked_sources[0]['id'],
                            date=today,
                            value_usd=round(tracked_total, 2),
                            metadata=json.dumps({'source': 'live'}),
                        )
                        logger.debug(f"Offchain collector: tracked tokens = ${tracked_total:,.2f}")
            except Exception as e:
                logger.warning(f"Offchain collector: tracked tokens failed: {e}")

        # --- Custom Tokens ---
        custom_sources = await get_wallet_sources(user_id, source_type='custom_tokens')
        if custom_sources:
            try:
                from database import get_all_custom_tokens

                custom_tokens = await get_all_custom_tokens(user_id=user_id)
                custom_total = 0.0
                for token in custom_tokens:
                    if token.get('include_in_total', 1) != 1:
                        continue
                    ticker = (token.get('ticker') or '').upper()
                    quantity = float(token.get('quantity', 0))
                    if ticker and ticker in prices:
                        price = prices[ticker].get('usd', 0) if isinstance(prices[ticker], dict) else 0
                        custom_total += quantity * price
                    elif token.get('price_usd'):
                        custom_total += quantity * float(token['price_usd'])

                if custom_total > 0:
                    await upsert_wallet_daily_balance(
                        user_id=user_id,
                        source_id=custom_sources[0]['id'],
                        date=today,
                        value_usd=round(custom_total, 2),
                        metadata=json.dumps({'source': 'live'}),
                    )
                    logger.debug(f"Offchain collector: custom tokens = ${custom_total:,.2f}")
            except Exception as e:
                logger.warning(f"Offchain collector: custom tokens failed: {e}")

        # --- Write full position snapshot to portfolio_positions ---
        try:
            from database import upsert_portfolio_positions_batch
            pp_rows = []

            # Exchange positions from cached data
            for exch in ['coinbase', 'binance', 'binance_us', 'okx', 'bitget', 'gate', 'kucoin']:
                from database import get_cache as _gc
                exc_cache = await _gc(f"{exch}_portfolio", user_id=user_id)
                if exc_cache and exc_cache.get('assets'):
                    for asset in exc_cache['assets']:
                        currency = (asset.get('currency') or '').upper()
                        balance = float(asset.get('balance', 0))
                        if currency and balance > 0:
                            pp_rows.append({
                                'user_id': user_id, 'symbol': currency, 'quantity': balance,
                                'source_type': 'exchange', 'source_detail': exch,
                                'chain': '', 'last_price_usd': float(asset.get('price', 0)),
                            })

            # On-chain positions
            for source in (onchain_sources or []):
                wallet_id = source.get('wallet_id')
                if not wallet_id:
                    continue
                chain = source.get('chain', '')
                balance_info = await get_wallet_balance(wallet_id)
                balance = float(balance_info['amount']) if balance_info else 0.0
                symbol = {
                    'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH',
                    'solana': 'SOL', 'polygon': 'POL', 'base': 'ETH_BASE',
                    'algorand': 'ALGO', 'bsc': 'BNB', 'arbitrum': 'ETH_ARB',
                    'avalanche': 'AVAX', 'tron': 'TRX',
                }.get(chain)
                if balance > 0 and symbol:
                    _ps = {'ETH_BASE': 'ETH', 'ETH_ARB': 'ETH', 'POL': 'MATIC'}.get(symbol, symbol)
                    p = prices.get(_ps, {})
                    price = p.get('usd', 0) if isinstance(p, dict) else 0
                    pp_rows.append({
                        'user_id': user_id, 'symbol': symbol, 'quantity': balance,
                        'source_type': 'chain', 'source_detail': chain,
                        'chain': chain, 'last_price_usd': price,
                    })

            # Staking positions from cached staking data — shared valuation
            # over every position kind (this writer historically includes
            # pending rewards and keeps the protocol name's original case in
            # source_detail; both preserved)
            try:
                from database import get_all_wallets as _gaw
                from services.defi import staking_portfolio_rows
                wallets = await _gaw(user_id=user_id)
                cardano_addrs = [w['address'] for w in wallets if w['blockchain'] == 'cardano']
                for addr in cardano_addrs:
                    stk_cache = await _gc(f"staking_positions_{addr}", user_id=user_id)
                    if not stk_cache:
                        stk_cache = await _gc(f"staking_positions_{addr}")
                    if not stk_cache or not isinstance(stk_cache, dict) or not stk_cache.get('protocols'):
                        continue
                    pp_rows.extend(staking_portfolio_rows(
                        user_id, stk_cache['protocols'], prices,
                        include_rewards=True, detail_lower=False,
                    ))
            except Exception as e:
                logger.debug(f"Offchain collector: staking portfolio positions failed: {e}")

            # DeFi positions from cached DeFi summary
            try:
                defi_cache = await _gc(f"defi_summary_{user_id}", user_id=user_id)
                if not defi_cache:
                    defi_cache = await _gc("defi_summary", user_id=user_id)
                if defi_cache and defi_cache.get('all_positions'):
                    for pos in defi_cache['all_positions']:
                        token = (pos.get('token') or '').upper()
                        quantity = float(pos.get('quantity', 0))
                        if token and quantity > 0:
                            price_data = prices.get(token, {})
                            price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                            protocol = pos.get('protocol', 'defi')
                            pp_rows.append({
                                'user_id': user_id, 'symbol': token, 'quantity': quantity,
                                'source_type': 'defi', 'source_detail': protocol,
                                'chain': 'cardano', 'last_price_usd': price,
                            })
            except Exception as e:
                logger.debug(f"Offchain collector: defi portfolio positions failed: {e}")

            # Tracked native tokens
            try:
                from database import get_tracked_tokens, get_wallet_assets, get_all_wallets as _gaw2
                from services.defi import DEFI_PROTOCOLS
                tracked_tokens = await get_tracked_tokens()
                tracked_ids = {t['asset_id'] for t in tracked_tokens}
                if tracked_ids:
                    wallets_all = await _gaw2(user_id=user_id)
                    for w in wallets_all:
                        if w['blockchain'] != 'cardano':
                            continue
                        assets = await get_wallet_assets(w['id'])
                        for asset in assets:
                            aid = asset.get('asset_id', '')
                            if aid not in tracked_ids:
                                continue
                            ticker = (asset.get('ticker') or '').upper()
                            if not ticker:
                                continue
                            policy_id = asset.get('policy_id', '')
                            if policy_id in DEFI_PROTOCOLS:
                                continue
                            raw_qty = float(asset.get('quantity') or 0)
                            decimals = int(asset.get('decimals') or 0)
                            human_qty = raw_qty / (10 ** decimals) if decimals > 0 else raw_qty
                            if human_qty <= 0:
                                continue
                            price_data = prices.get(ticker, {})
                            price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                            if price > 0:
                                pp_rows.append({
                                    'user_id': user_id, 'symbol': ticker, 'quantity': human_qty,
                                    'source_type': 'tracked_token', 'source_detail': aid,
                                    'chain': 'cardano', 'last_price_usd': price,
                                })
            except Exception as e:
                logger.debug(f"Offchain collector: tracked tokens portfolio positions failed: {e}")

            # Custom tokens
            try:
                from database import get_all_custom_tokens
                custom_tokens = await get_all_custom_tokens(user_id=user_id)
                for token in custom_tokens:
                    if token.get('include_in_total', 1) != 1:
                        continue
                    ticker = (token.get('ticker') or '').upper()
                    quantity = float(token.get('quantity', 0))
                    if not ticker or quantity <= 0:
                        continue
                    price_data = prices.get(ticker, {})
                    price = price_data.get('usd', 0) if isinstance(price_data, dict) else 0
                    if price <= 0 and token.get('price_usd'):
                        price = float(token['price_usd'])
                    if price > 0:
                        pp_rows.append({
                            'user_id': user_id, 'symbol': ticker, 'quantity': quantity,
                            'source_type': 'custom_token', 'source_detail': str(token.get('id', '')),
                            'chain': '', 'last_price_usd': price,
                        })
            except Exception as e:
                logger.debug(f"Offchain collector: custom tokens portfolio positions failed: {e}")

            if pp_rows:
                await upsert_portfolio_positions_batch(pp_rows)
                logger.debug(f"Offchain collector: wrote {len(pp_rows)} portfolio positions for user {user_id}")
        except Exception as e:
            logger.debug(f"Offchain collector: portfolio positions write failed: {e}")

        logger.info(f"Offchain collector: Completed collection for user {user_id}")

    async def collect_all_users(self):
        """Collect off-chain balances for all non-demo users."""
        from database import get_all_users, seed_wallet_sources

        users = await get_all_users()
        non_demo = [u for u in users if not u.get('is_demo', False)]

        for user in non_demo:
            user_id = user['id']
            try:
                # Ensure sources are seeded
                await seed_wallet_sources(user_id)
                await self.collect_for_user(user_id)
            except Exception as e:
                logger.error(f"Offchain collector: Failed for user {user_id}: {e}")

    async def start_periodic(self):
        """Start the periodic collection loop (replaces V1 periodic_snapshot_task for off-chain)."""
        self._task = asyncio.current_task() or asyncio.ensure_future(self._run_loop())

    async def _run_loop(self):
        """Background loop: collect off-chain every COLLECTION_INTERVAL_HOURS."""
        from services.logging_service import get_logging_service
        log_service = get_logging_service()

        while True:
            try:
                await asyncio.sleep(COLLECTION_INTERVAL_HOURS * 3600)
                logger.info("Offchain collector: Starting periodic collection...")
                await log_service.info("offchain_collector", "Starting periodic off-chain collection")
                await self.collect_all_users()
                logger.info("Offchain collector: Periodic collection complete")
                await log_service.info("offchain_collector", "Periodic off-chain collection complete")
            except Exception as e:
                logger.error(f"Offchain collector: Periodic collection error: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error


# Singleton
offchain_collector = OffchainCollector()
