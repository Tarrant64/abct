"""
Balance History Service (V2 On-Chain History)

Collects real historical wallet balances by replaying blockchain transactions,
pairs them with historical prices from CoinGecko, and stores daily balance
snapshots in the balance_history table.

MVP scope: Cardano + Bitcoin collectors.
EVM chains (Ethereum/Polygon/Base), Solana, and Coinbase are follow-up work.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import BLOCKFROST_BASE_URL, BLOCKSTREAM_BASE_URL
from database import (
    get_all_wallets,
    get_balance_history_latest_date,
    save_balance_history_batch,
    get_balance_history_aggregated,
    get_balance_history_range,
    get_balance_history_coverage,
    create_balance_history_job,
    update_balance_history_job,
    get_latest_balance_history_job,
)
from services.cardano import cardano_service
from services.http_client import get_client, fetch_with_retry
from services.logging_service import get_logging_service
from services.pricing import pricing_service, COINGECKO_BASE_URL, ASSET_TO_COINGECKO

logger = logging.getLogger(__name__)
log_service = get_logging_service()

# Chains supported by the balance history collector
SUPPORTED_CHAINS = {'cardano', 'bitcoin'}

# Native symbols per chain
CHAIN_SYMBOL = {
    'cardano': 'ADA',
    'bitcoin': 'BTC',
    'ethereum': 'ETH',
    'solana': 'SOL',
    'polygon': 'MATIC',
    'base': 'ETH',
}

# Lovelace / satoshi divisors
CHAIN_DIVISOR = {
    'cardano': 1_000_000,      # 1 ADA = 1,000,000 lovelace
    'bitcoin': 100_000_000,    # 1 BTC = 100,000,000 satoshi
}


class BalanceHistoryService:
    """Orchestrates on-chain balance history collection."""

    def __init__(self):
        self._running_tasks: Dict[int, asyncio.Task] = {}  # user_id -> Task
        self._cancel_flags: Dict[int, bool] = {}
        self._scheduler_tasks: Dict[int, asyncio.Task] = {}  # user_id -> scheduler Task

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect_history(
        self,
        user_id: int,
        blockchain: str = None,
        max_days_back: int = 730,
        force: bool = False,
    ) -> int:
        """Start background collection for a user's wallets.

        Args:
            user_id: User ID
            blockchain: Optional chain filter (e.g. 'cardano')
            max_days_back: Maximum days to look back (default 2 years)
            force: If True, ignore existing data and re-collect from scratch

        Returns:
            Job ID
        """
        # Check if already running for this user
        if user_id in self._running_tasks and not self._running_tasks[user_id].done():
            job = await get_latest_balance_history_job(user_id)
            if job:
                return job['id']
            return -1

        job_id = await create_balance_history_job(user_id, blockchain=blockchain)
        self._cancel_flags[user_id] = False

        task = asyncio.create_task(
            self._run_collection(user_id, job_id, blockchain, max_days_back, force)
        )
        self._running_tasks[user_id] = task
        return job_id

    async def cancel_collection(self, user_id: int):
        """Cancel a running collection task."""
        self._cancel_flags[user_id] = True
        task = self._running_tasks.get(user_id)
        if task and not task.done():
            await update_balance_history_job(
                (await get_latest_balance_history_job(user_id) or {}).get('id', 0),
                status='cancelled', step='Cancelled by user'
            )

    async def get_aggregated_history(self, user_id: int, days: int = None,
                                     start_date: str = None, end_date: str = None):
        """Get aggregated balance history for chart rendering."""
        data = await get_balance_history_aggregated(user_id, start_date, end_date, days)
        coverage = await get_balance_history_range(user_id)
        return {'data': data, 'coverage': coverage}

    # ------------------------------------------------------------------
    # Internal: Collection orchestrator
    # ------------------------------------------------------------------

    async def _run_collection(self, user_id: int, job_id: int,
                              blockchain: str, max_days_back: int, force: bool = False):
        """Main collection loop — runs as a background task."""
        try:
            wallets = await get_all_wallets(user_id)
            # Filter to supported chains
            target_wallets = [
                w for w in wallets
                if w['blockchain'] in SUPPORTED_CHAINS
                and (blockchain is None or w['blockchain'] == blockchain)
            ]

            if not target_wallets:
                await log_service.info("balance_history", f"No supported wallets found for user {user_id}")
                await update_balance_history_job(
                    job_id, status='completed', progress=100,
                    step='No supported wallets found'
                )
                return

            total = len(target_wallets)
            await log_service.info("balance_history", f"Balance history: Starting collection for user {user_id}, {total} wallets")
            await update_balance_history_job(
                job_id, total_items=total, step=f'Collecting history for {total} wallet(s)'
            )

            for idx, wallet in enumerate(target_wallets):
                if self._cancel_flags.get(user_id):
                    break

                chain = wallet['blockchain']
                label = wallet.get('label') or wallet.get('address', '')[:12]
                pct = int((idx / total) * 100)

                await log_service.info("balance_history", f"Balance history: Collecting {chain} wallet {label} ({idx+1}/{total})")
                await update_balance_history_job(
                    job_id, progress=pct, processed_items=idx,
                    step=f'Processing {chain} wallet: {label}'
                )

                try:
                    await self._collect_wallet(user_id, wallet, max_days_back, job_id, force)
                except Exception as e:
                    logger.error(f"Error collecting {chain} wallet {wallet['id']}: {e}")
                    await log_service.error("balance_history", f"Error collecting {chain} wallet {label}: {e}")
                    # Continue with other wallets

            status = 'cancelled' if self._cancel_flags.get(user_id) else 'completed'
            await log_service.info("balance_history", f"Balance history: Collection {status} for user {user_id}, {total} wallets processed")
            await update_balance_history_job(
                job_id, status=status, progress=100,
                processed_items=total, step='Collection complete'
            )

        except Exception as e:
            import traceback
            logger.error(f"Balance history collection failed for user {user_id}: {e}")
            await log_service.error("balance_history", f"Balance history collection failed for user {user_id}: {e}\n{traceback.format_exc()}")
            await update_balance_history_job(
                job_id, status='error', error_message=str(e)[:500],
                step='Collection failed'
            )
        finally:
            self._running_tasks.pop(user_id, None)
            self._cancel_flags.pop(user_id, None)

    async def _collect_wallet(self, user_id: int, wallet: dict,
                              max_days_back: int, job_id: int, force: bool = False):
        """Collect balance history for a single wallet."""
        chain = wallet['blockchain']
        wallet_id = wallet['id']
        address = wallet['address']

        # Check existing coverage for incremental updates (skip if force)
        latest_date = None if force else await get_balance_history_latest_date(user_id, wallet_id)
        cutoff = (datetime.utcnow() - timedelta(days=max_days_back)).strftime('%Y-%m-%d')

        if chain == 'cardano':
            daily_balances = await self._collect_cardano(address, latest_date, cutoff)
        elif chain == 'bitcoin':
            daily_balances = await self._collect_bitcoin(address, latest_date, cutoff)
        else:
            logger.info(f"Chain {chain} not yet supported for balance history")
            return

        if not daily_balances:
            logger.info(f"No new balance data for {chain} wallet {wallet_id}")
            await log_service.info("balance_history", f"No new balance data for {chain} wallet {wallet_id}")
            return

        # Fetch historical prices for the date range
        symbol = CHAIN_SYMBOL[chain]
        dates = sorted(daily_balances.keys())
        await log_service.info("balance_history", f"Fetching historical prices for {symbol}, {len(dates)} dates ({dates[0]} to {dates[-1]})")
        prices = await self._fetch_historical_prices(symbol, dates[0], dates[-1])

        # Build data points
        points = []
        for date_str, native_amount in sorted(daily_balances.items()):
            price = prices.get(date_str, 0)
            native_value = native_amount * price
            points.append({
                'wallet_id': wallet_id,
                'blockchain': chain,
                'balance_date': date_str,
                'native_amount': native_amount,
                'native_symbol': symbol,
                'native_price_usd': price,
                'native_value_usd': native_value,
                'token_value_usd': 0,  # MVP: native only
                'total_value_usd': native_value,
                'data_source': 'chain',
                'metadata': '{}',
            })

        # Save in batches of 100
        for i in range(0, len(points), 100):
            if self._cancel_flags.get(user_id):
                break
            batch = points[i:i + 100]
            await save_balance_history_batch(batch, user_id)

        logger.info(f"Saved {len(points)} balance history points for {chain} wallet {wallet_id}")
        await log_service.info("balance_history", f"Balance history: Saved {len(points)} data points for {chain} wallet {wallet_id}")

    # ------------------------------------------------------------------
    # Chain Collectors
    # ------------------------------------------------------------------

    async def _collect_cardano(self, address: str, latest_date: str,
                               cutoff: str) -> Dict[str, float]:
        """Collect Cardano balance history by anchoring to current on-chain balance.

        Strategy: Fetch current balance from Blockfrost, then replay only recent
        transactions to reconstruct historical daily balances. This avoids needing
        UTxO lookups for old transactions before the cutoff date.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to ADA balance on that date.
        """
        blockfrost_key = await cardano_service._get_blockfrost_key()
        if not blockfrost_key:
            logger.warning("Blockfrost API key not configured, skipping Cardano history")
            await log_service.warning("balance_history", "Blockfrost API key not configured, skipping Cardano history")
            return {}

        headers = {"project_id": blockfrost_key}
        client = get_client("blockfrost", timeout=30.0)

        # Step 1: Get current on-chain balance (anchor point)
        try:
            addr_response = await client.get(
                f"{BLOCKFROST_BASE_URL}/addresses/{address}",
                headers=headers
            )
            if addr_response.status_code == 404:
                await log_service.info("balance_history", f"Cardano address not found: {address[:20]}...")
                return {}
            if addr_response.status_code != 200:
                logger.error(f"Blockfrost address lookup error: {addr_response.status_code}")
                await log_service.error("balance_history", f"Blockfrost address lookup error for {address[:20]}...: {addr_response.status_code}")
                return {}

            addr_data = addr_response.json()
            current_lovelace = 0
            for amount in addr_data.get('amount', []):
                if amount.get('unit') == 'lovelace':
                    current_lovelace = int(amount.get('quantity', 0))
                    break

            current_ada = current_lovelace / CHAIN_DIVISOR['cardano']
            await log_service.info("balance_history", f"Current balance for {address[:20]}...: {current_ada:.2f} ADA")
        except Exception as e:
            logger.error(f"Error fetching Cardano address balance: {e}")
            await log_service.error("balance_history", f"Error fetching Cardano address balance: {e}")
            return {}

        # Step 2: Fetch all transactions (paginated, oldest first)
        all_txs = []
        page = 1
        while True:
            if self._cancel_flags.get(hash(address) % 1000):
                break
            try:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/addresses/{address}/transactions",
                    headers=headers,
                    params={"count": 100, "page": page, "order": "asc"}
                )
                if response.status_code == 404:
                    break
                if response.status_code == 429:
                    await asyncio.sleep(10)
                    continue
                if response.status_code != 200:
                    logger.error(f"Blockfrost tx list error: {response.status_code}")
                    break

                batch = response.json()
                if not batch:
                    break
                all_txs.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
                await asyncio.sleep(0.3)  # Rate limit: ~250 req/min
            except Exception as e:
                logger.error(f"Error fetching Cardano txs page {page}: {e}")
                break

        today = datetime.utcnow().strftime('%Y-%m-%d')

        if not all_txs:
            # No transactions but wallet may have balance (e.g. from staking rewards)
            if current_lovelace > 0:
                await log_service.info("balance_history", f"No txs for {address[:20]}... but has {current_ada:.2f} ADA, recording today's balance")
                return {today: current_ada}
            return {}

        logger.info(f"Fetched {len(all_txs)} Cardano transactions for {address}")
        await log_service.info("balance_history", f"Blockfrost: Fetched {len(all_txs)} Cardano transactions for {address[:20]}...")

        # Step 3: Determine effective start date for UTxO processing
        effective_start = latest_date if latest_date else cutoff

        # Step 4: Filter to only transactions within the date range
        # Only these need expensive UTxO lookups
        recent_txs = []
        for tx_info in all_txs:
            block_time = tx_info.get('block_time', 0)
            tx_date = datetime.utcfromtimestamp(block_time).strftime('%Y-%m-%d')
            tx_info['_date'] = tx_date
            if tx_date >= effective_start:
                recent_txs.append(tx_info)

        await log_service.info("balance_history",
            f"Processing {len(recent_txs)} of {len(all_txs)} txs for {address[:20]}... (from {effective_start})")

        # Step 5: Fetch UTxOs for recent transactions and calculate net changes
        net_change_lovelace = 0
        tx_changes = []  # list of (date, change_lovelace)

        for tx_info in recent_txs:
            tx_hash = tx_info.get('tx_hash')
            tx_date = tx_info['_date']

            try:
                utxo_response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/txs/{tx_hash}/utxos",
                    headers=headers
                )
                if utxo_response.status_code == 429:
                    await asyncio.sleep(10)
                    utxo_response = await client.get(
                        f"{BLOCKFROST_BASE_URL}/txs/{tx_hash}/utxos",
                        headers=headers
                    )
                if utxo_response.status_code != 200:
                    await asyncio.sleep(0.3)
                    continue

                utxos = utxo_response.json()

                input_lovelace = 0
                output_lovelace = 0

                for inp in utxos.get('inputs', []):
                    if inp.get('address') == address:
                        for amount in inp.get('amount', []):
                            if amount.get('unit') == 'lovelace':
                                input_lovelace += int(amount.get('quantity', 0))

                for out in utxos.get('outputs', []):
                    if out.get('address') == address:
                        for amount in out.get('amount', []):
                            if amount.get('unit') == 'lovelace':
                                output_lovelace += int(amount.get('quantity', 0))

                change = output_lovelace - input_lovelace
                net_change_lovelace += change
                tx_changes.append((tx_date, change))

                await asyncio.sleep(0.3)  # Rate limit
            except Exception as e:
                logger.error(f"Error processing Cardano tx {tx_hash}: {e}")
                continue

        # Step 6: Calculate starting balance using current balance as anchor
        # current_balance = starting_balance + net_change_from_recent_txs
        # Therefore: starting_balance = current_balance - net_change
        starting_balance_lovelace = current_lovelace - net_change_lovelace
        starting_ada = starting_balance_lovelace / CHAIN_DIVISOR['cardano']

        await log_service.info("balance_history",
            f"Balance for {address[:20]}...: current={current_ada:.2f} ADA, "
            f"net_change={net_change_lovelace / CHAIN_DIVISOR['cardano']:.2f} ADA, "
            f"starting={starting_ada:.2f} ADA ({len(tx_changes)} txs)")

        # Step 7: Replay transactions forward from starting balance
        running_balance_lovelace = starting_balance_lovelace
        daily_balances = {}

        for tx_date, change in tx_changes:
            running_balance_lovelace += change
            # Only save dates after latest_date (for incremental)
            if not latest_date or tx_date > latest_date:
                daily_balances[tx_date] = running_balance_lovelace / CHAIN_DIVISOR['cardano']

        # Ensure today's balance is recorded using the known current on-chain balance
        if not latest_date or today > (latest_date or ''):
            daily_balances[today] = current_ada

        # Fill in gaps: for dates between transactions, carry forward previous balance
        if daily_balances:
            daily_balances = self._fill_daily_gaps(daily_balances)

        return daily_balances

    async def _collect_bitcoin(self, address: str, latest_date: str,
                               cutoff: str) -> Dict[str, float]:
        """Collect Bitcoin balance history by replaying transactions.

        Uses Blockstream API to fetch all transactions, replays them
        chronologically to build a running BTC balance.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to BTC balance on that date.
        """
        client = get_client("blockstream", timeout=30.0)

        # Fetch all transactions (paginated via last_seen_txid)
        all_txs = []
        last_seen_txid = None
        while True:
            try:
                url = f"{BLOCKSTREAM_BASE_URL}/address/{address}/txs"
                if last_seen_txid:
                    url += f"/chain/{last_seen_txid}"

                response = await client.get(url)
                if response.status_code != 200:
                    logger.error(f"Blockstream tx list error: {response.status_code}")
                    break

                batch = response.json()
                if not batch:
                    break
                all_txs.extend(batch)
                if len(batch) < 25:  # Blockstream returns 25 per page
                    break
                last_seen_txid = batch[-1]['txid']
                await asyncio.sleep(1.0)  # Polite delay (no API key)
            except Exception as e:
                logger.error(f"Error fetching Bitcoin txs: {e}")
                break

        if not all_txs:
            await log_service.info("balance_history", f"No Bitcoin transactions found for {address[:12]}...")
            return {}

        # Sort by block time ascending (oldest first)
        # Unconfirmed txs have no 'status.block_time' — skip them
        confirmed_txs = [
            tx for tx in all_txs
            if tx.get('status', {}).get('confirmed', False)
        ]
        confirmed_txs.sort(key=lambda tx: tx['status'].get('block_time', 0))

        logger.info(f"Fetched {len(confirmed_txs)} confirmed Bitcoin transactions for {address}")
        await log_service.info("balance_history", f"Blockstream: Fetched {len(confirmed_txs)} confirmed Bitcoin txs for {address[:12]}...")

        # Build running balance by replaying ALL transactions (including pre-cutoff)
        # to ensure correct starting balance for the date range
        running_balance_sats = 0
        daily_balances = {}

        for tx in confirmed_txs:
            block_time = tx['status'].get('block_time', 0)
            tx_date = datetime.utcfromtimestamp(block_time).strftime('%Y-%m-%d')

            # Calculate balance change for ALL transactions (no extra API calls needed)
            input_sats = 0
            output_sats = 0

            for vin in tx.get('vin', []):
                prev = vin.get('prevout', {})
                if prev.get('scriptpubkey_address') == address:
                    input_sats += prev.get('value', 0)

            for vout in tx.get('vout', []):
                if vout.get('scriptpubkey_address') == address:
                    output_sats += vout.get('value', 0)

            running_balance_sats += (output_sats - input_sats)

            # Only record daily balance for dates within range
            if tx_date >= cutoff and (not latest_date or tx_date > latest_date):
                daily_balances[tx_date] = running_balance_sats / CHAIN_DIVISOR['bitcoin']

        # Record today's balance as the final running balance
        today = datetime.utcnow().strftime('%Y-%m-%d')
        if running_balance_sats > 0 and (not latest_date or today > (latest_date or '')):
            daily_balances[today] = running_balance_sats / CHAIN_DIVISOR['bitcoin']

        final_btc = running_balance_sats / CHAIN_DIVISOR['bitcoin']
        await log_service.info("balance_history",
            f"Bitcoin balance for {address[:12]}...: {final_btc:.8f} BTC, {len(daily_balances)} daily entries")

        # Fill in gaps
        if daily_balances:
            daily_balances = self._fill_daily_gaps(daily_balances)

        return daily_balances

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fill_daily_gaps(self, daily_balances: Dict[str, float]) -> Dict[str, float]:
        """Fill in missing dates by carrying forward the previous day's balance."""
        if not daily_balances:
            return daily_balances

        dates = sorted(daily_balances.keys())
        start = datetime.strptime(dates[0], '%Y-%m-%d')
        end = datetime.strptime(dates[-1], '%Y-%m-%d')
        today = datetime.utcnow()
        if end < today:
            end = today

        filled = {}
        current = start
        last_balance = 0
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            if date_str in daily_balances:
                last_balance = daily_balances[date_str]
            filled[date_str] = last_balance
            current += timedelta(days=1)

        return filled

    async def _fetch_historical_prices(self, symbol: str,
                                       start_date: str, end_date: str) -> Dict[str, float]:
        """Fetch daily historical prices from CoinGecko for a date range.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to USD price.
        """
        cg_id = ASSET_TO_COINGECKO.get(symbol)
        if not cg_id:
            return {}

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        # Add 1 day buffer to end
        end_dt = min(end_dt + timedelta(days=1), datetime.utcnow())

        from_ts = int(start_dt.timestamp())
        to_ts = int(end_dt.timestamp())

        prices = {}
        try:
            client = get_client("coingecko_historical", timeout=60.0)
            response = await fetch_with_retry(
                client, "GET",
                f"{COINGECKO_BASE_URL}/coins/{cg_id}/market_chart/range",
                params={
                    'vs_currency': 'usd',
                    'from': from_ts,
                    'to': to_ts,
                }
            )

            if response.status_code == 200:
                data = response.json()
                for timestamp_ms, price in data.get('prices', []):
                    dt = datetime.utcfromtimestamp(timestamp_ms / 1000)
                    date_str = dt.strftime('%Y-%m-%d')
                    # Keep the last price for each day (end-of-day)
                    prices[date_str] = price

                logger.info(f"Fetched {len(prices)} historical prices for {symbol}")
                await log_service.info("balance_history", f"CoinGecko: Fetched {len(prices)} historical prices for {symbol}")
            elif response.status_code == 429:
                logger.warning("CoinGecko rate limited during historical price fetch")
                await log_service.warning("balance_history", f"CoinGecko rate limited (429) during historical price fetch for {symbol}")
                await asyncio.sleep(60)
            else:
                logger.warning(f"CoinGecko historical range error: {response.status_code}")
                await log_service.warning("balance_history", f"CoinGecko historical range error: {response.status_code} for {symbol}")
        except Exception as e:
            logger.error(f"Error fetching historical prices for {symbol}: {e}")
            await log_service.error("balance_history", f"Error fetching historical prices for {symbol}: {e}")

        return prices

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    async def start_scheduler(self, user_id: int, interval_hours: int):
        """Start (or restart) the periodic collection scheduler for a user."""
        # Stop existing scheduler first
        await self.stop_scheduler(user_id)

        async def _scheduler_loop():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)
                    logger.info(f"Scheduler: Starting auto-collection for user {user_id}")
                    await log_service.info("balance_history", f"Scheduler: Starting auto-collection for user {user_id} (every {interval_hours}h)")
                    await self.collect_history(user_id=user_id)
                except asyncio.CancelledError:
                    logger.info(f"Scheduler cancelled for user {user_id}")
                    break
                except Exception as e:
                    logger.error(f"Scheduler error for user {user_id}: {e}")
                    await log_service.error("balance_history", f"Scheduler error for user {user_id}: {e}")
                    # Wait 1 hour before retrying on error
                    await asyncio.sleep(3600)

        task = asyncio.create_task(_scheduler_loop())
        self._scheduler_tasks[user_id] = task
        logger.info(f"Balance history scheduler started for user {user_id}, interval={interval_hours}h")

    async def stop_scheduler(self, user_id: int):
        """Stop the periodic collection scheduler for a user."""
        task = self._scheduler_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"Balance history scheduler stopped for user {user_id}")


# Singleton
balance_history_service = BalanceHistoryService()
