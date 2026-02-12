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

from config import (BLOCKFROST_BASE_URL, BLOCKSTREAM_BASE_URL,
                    ETHERSCAN_BASE_URL, BASESCAN_BASE_URL, POLYGONSCAN_BASE_URL,
                    HELIUS_BASE_URL, HELIUS_RPC_URL)
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
    get_unpriced_date_ranges,
    update_balance_history_prices,
)
from services.api_key_manager import APIKeyManager
from services.cardano import cardano_service
from services.http_client import get_client
from services.logging_service import get_logging_service

logger = logging.getLogger(__name__)
log_service = get_logging_service()

# API key managers for chain collectors
_etherscan_keys = APIKeyManager("etherscan", "ETHERSCAN_API_KEY")
_helius_keys = APIKeyManager("helius", "HELIUS_API_KEY")

# Chains supported by the balance history collector
SUPPORTED_CHAINS = {'cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana', 'algorand'}

# Native symbols per chain
CHAIN_SYMBOL = {
    'cardano': 'ADA',
    'bitcoin': 'BTC',
    'ethereum': 'ETH',
    'solana': 'SOL',
    'polygon': 'MATIC',
    'base': 'ETH',
    'algorand': 'ALGO',
}

# Smallest-unit divisors
CHAIN_DIVISOR = {
    'cardano': 1_000_000,        # 1 ADA = 1,000,000 lovelace
    'bitcoin': 100_000_000,      # 1 BTC = 100,000,000 satoshi
    'ethereum': 10**18,          # 1 ETH = 10^18 wei
    'polygon': 10**18,           # 1 MATIC = 10^18 wei
    'base': 10**18,              # 1 ETH = 10^18 wei
    'solana': 1_000_000_000,     # 1 SOL = 1,000,000,000 lamports
    'algorand': 1_000_000,       # 1 ALGO = 1,000,000 microalgos
}

# EVM chain configuration (Etherscan-compatible APIs)
EVM_CHAIN_CONFIG = {
    'ethereum': {'base_url': ETHERSCAN_BASE_URL, 'explorer_name': 'Etherscan'},
    'polygon': {'base_url': POLYGONSCAN_BASE_URL, 'explorer_name': 'Polygonscan'},
    'base': {'base_url': BASESCAN_BASE_URL, 'explorer_name': 'Basescan'},
}

# Pera Wallet API (no key required)
PERA_BASE_URL = "https://mainnet.api.perawallet.app"


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
        max_days_back: int = 3650,
        force: bool = False,
        wallet_ids: List[int] = None,
    ) -> int:
        """Start background collection for a user's wallets.

        Args:
            user_id: User ID
            blockchain: Optional chain filter (e.g. 'cardano')
            max_days_back: Maximum days to look back (default ~10 years = all history)
            force: If True, ignore existing data and re-collect from scratch
            wallet_ids: Optional list of wallet IDs to collect for (None for all)

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
            self._run_collection(user_id, job_id, blockchain, max_days_back, force, wallet_ids)
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
                              blockchain: str, max_days_back: int, force: bool = False,
                              wallet_ids: List[int] = None):
        """Main collection loop — runs as a background task."""
        try:
            wallets = await get_all_wallets(user_id)
            # Filter to supported chains
            target_wallets = [
                w for w in wallets
                if w['blockchain'] in SUPPORTED_CHAINS
                and (blockchain is None or w['blockchain'] == blockchain)
            ]

            # Filter by wallet IDs if specified
            if wallet_ids:
                target_wallets = [w for w in target_wallets if w['id'] in wallet_ids]

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
        elif chain in ('ethereum', 'polygon', 'base'):
            daily_balances = await self._collect_evm(chain, address, latest_date, cutoff)
        elif chain == 'solana':
            daily_balances = await self._collect_solana(address, latest_date, cutoff)
        elif chain == 'algorand':
            daily_balances = await self._collect_algorand(address, latest_date, cutoff)
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
    # EVM Collector (Ethereum, Polygon, Base)
    # ------------------------------------------------------------------

    async def _collect_evm(self, chain: str, address: str, latest_date: str,
                           cutoff: str) -> Dict[str, float]:
        """Collect EVM chain balance history using Etherscan-compatible APIs.

        Handles Ethereum, Polygon, and Base using the same API format.
        Strategy: anchor to current on-chain balance, replay normal + internal
        transactions to reconstruct historical daily balances.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to native balance on that date.
        """
        api_key = await _etherscan_keys.get_api_key()
        if not api_key:
            logger.warning(f"Etherscan API key not configured, skipping {chain} history")
            await log_service.warning("balance_history",
                f"Etherscan API key not configured, skipping {chain} history")
            return {}

        config = EVM_CHAIN_CONFIG[chain]
        base_url = config['base_url']
        explorer = config['explorer_name']
        divisor = CHAIN_DIVISOR[chain]
        client = get_client("etherscan", timeout=30.0)

        # Step 1: Get current on-chain balance
        try:
            resp = await client.get(base_url, params={
                'module': 'account', 'action': 'balance',
                'address': address, 'tag': 'latest', 'apikey': api_key,
            })
            if resp.status_code != 200:
                logger.error(f"{explorer} balance error: {resp.status_code}")
                return {}
            data = resp.json()
            if data.get('status') != '1' and data.get('message') != 'OK':
                # status=0 with result="0" is valid (zero balance)
                if data.get('result') != '0':
                    logger.error(f"{explorer} balance error: {data.get('message')}")
                    return {}
            current_wei = int(data.get('result', 0))
            current_native = current_wei / divisor
            await log_service.info("balance_history",
                f"Current {chain} balance for {address[:12]}...: {current_native:.6f} {CHAIN_SYMBOL[chain]}")
        except Exception as e:
            logger.error(f"Error fetching {chain} balance: {e}")
            return {}

        # Step 2: Fetch normal transactions (paginated)
        normal_txs = await self._fetch_etherscan_txlist(
            client, base_url, api_key, address, 'txlist', explorer)

        # Step 3: Fetch internal transactions
        internal_txs = await self._fetch_etherscan_txlist(
            client, base_url, api_key, address, 'txlistinternal', explorer)

        # Step 4: Merge and sort by timestamp
        all_events = []
        for tx in normal_txs:
            ts = int(tx.get('timeStamp', 0))
            tx_date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d') if ts else None
            if not tx_date:
                continue
            value = int(tx.get('value', 0))
            gas_used = int(tx.get('gasUsed', 0))
            gas_price = int(tx.get('gasPrice', 0))
            gas_cost = gas_used * gas_price
            is_sender = tx.get('from', '').lower() == address.lower()
            is_receiver = tx.get('to', '').lower() == address.lower()
            change = 0
            if is_sender:
                change -= (value + gas_cost)
            if is_receiver:
                change += value
            if change != 0:
                all_events.append((ts, tx_date, change))

        for tx in internal_txs:
            ts = int(tx.get('timeStamp', 0))
            tx_date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d') if ts else None
            if not tx_date:
                continue
            value = int(tx.get('value', 0))
            is_sender = tx.get('from', '').lower() == address.lower()
            is_receiver = tx.get('to', '').lower() == address.lower()
            # Internal txs: no gas cost (outer tx already paid)
            change = 0
            if is_sender:
                change -= value
            if is_receiver:
                change += value
            if change != 0:
                all_events.append((ts, tx_date, change))

        today = datetime.utcnow().strftime('%Y-%m-%d')

        if not all_events:
            if current_wei > 0:
                await log_service.info("balance_history",
                    f"No txs for {chain} {address[:12]}... but has balance, recording today")
                return {today: current_native}
            return {}

        all_events.sort(key=lambda e: e[0])
        await log_service.info("balance_history",
            f"{explorer}: Fetched {len(normal_txs)} normal + {len(internal_txs)} internal txs for {address[:12]}...")

        # Step 5: Filter to recent, compute net change, anchor + replay
        effective_start = latest_date if latest_date else cutoff
        net_change_wei = 0
        tx_changes = []  # (date, change_wei)

        for _ts, tx_date, change_wei in all_events:
            if tx_date >= effective_start:
                net_change_wei += change_wei
                tx_changes.append((tx_date, change_wei))

        starting_wei = current_wei - net_change_wei
        starting_native = starting_wei / divisor

        await log_service.info("balance_history",
            f"{chain} {address[:12]}...: current={current_native:.6f}, "
            f"net_change={net_change_wei / divisor:.6f}, "
            f"starting={starting_native:.6f} ({len(tx_changes)} recent txs)")

        # Replay forward
        running_wei = starting_wei
        daily_balances = {}
        for tx_date, change_wei in tx_changes:
            running_wei += change_wei
            if not latest_date or tx_date > latest_date:
                daily_balances[tx_date] = running_wei / divisor

        if not latest_date or today > (latest_date or ''):
            daily_balances[today] = current_native

        if daily_balances:
            daily_balances = self._fill_daily_gaps(daily_balances)

        return daily_balances

    async def _fetch_etherscan_txlist(self, client, base_url: str, api_key: str,
                                      address: str, action: str,
                                      explorer: str) -> List[dict]:
        """Paginated fetch of Etherscan txlist or txlistinternal."""
        all_txs = []
        page = 1
        while True:
            try:
                resp = await client.get(base_url, params={
                    'module': 'account', 'action': action,
                    'address': address, 'startblock': 0, 'endblock': 99999999,
                    'page': page, 'offset': 1000, 'sort': 'asc',
                    'apikey': api_key,
                })
                if resp.status_code != 200:
                    logger.error(f"{explorer} {action} page {page} error: {resp.status_code}")
                    break

                data = resp.json()
                result = data.get('result', [])
                if not isinstance(result, list):
                    # API returns error string when no results
                    break
                if not result:
                    break

                all_txs.extend(result)
                if len(result) < 1000:
                    break
                page += 1
                await asyncio.sleep(0.25)  # Rate limit: 5 calls/sec free tier
            except Exception as e:
                logger.error(f"Error fetching {explorer} {action} page {page}: {e}")
                break

        return all_txs

    # ------------------------------------------------------------------
    # Solana Collector
    # ------------------------------------------------------------------

    async def _collect_solana(self, address: str, latest_date: str,
                              cutoff: str) -> Dict[str, float]:
        """Collect Solana balance history using Helius enhanced transactions.

        Strategy: anchor to current SOL balance from RPC, replay nativeTransfers
        from Helius enhanced transaction history.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to SOL balance on that date.
        """
        api_key = await _helius_keys.get_api_key()
        if not api_key:
            logger.warning("Helius API key not configured, skipping Solana history")
            await log_service.warning("balance_history",
                "Helius API key not configured, skipping Solana history")
            return {}

        divisor = CHAIN_DIVISOR['solana']
        client = get_client("helius", timeout=30.0)

        # Step 1: Get current balance via Helius RPC
        try:
            rpc_resp = await client.post(
                f"{HELIUS_RPC_URL}/?api-key={api_key}",
                json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getBalance",
                    "params": [address],
                },
            )
            if rpc_resp.status_code != 200:
                logger.error(f"Helius RPC getBalance error: {rpc_resp.status_code}")
                return {}
            rpc_data = rpc_resp.json()
            current_lamports = rpc_data.get('result', {}).get('value', 0)
            current_sol = current_lamports / divisor
            await log_service.info("balance_history",
                f"Current Solana balance for {address[:12]}...: {current_sol:.6f} SOL")
        except Exception as e:
            logger.error(f"Error fetching Solana balance: {e}")
            return {}

        # Step 2: Fetch enhanced transactions (paginated with 'before' cursor)
        all_events = []  # (timestamp, date_str, change_lamports)
        before_sig = None
        page_count = 0

        while True:
            try:
                url = f"{HELIUS_BASE_URL}/addresses/{address}/transactions?api-key={api_key}"
                params = {"limit": 100}
                if before_sig:
                    params["before"] = before_sig

                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.error(f"Helius enhanced txs error: {resp.status_code}")
                    break

                txs = resp.json()
                if not txs:
                    break

                for tx in txs:
                    ts = tx.get('timestamp', 0)
                    if not ts:
                        continue
                    tx_date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')

                    # Sum native transfers involving this address
                    change = 0
                    for nt in tx.get('nativeTransfers', []):
                        if nt.get('toUserAccount') == address:
                            change += nt.get('amount', 0)
                        if nt.get('fromUserAccount') == address:
                            change -= nt.get('amount', 0)

                    # Subtract fee if this address is the fee payer
                    if tx.get('feePayer') == address:
                        change -= tx.get('fee', 0)

                    if change != 0:
                        all_events.append((ts, tx_date, change))

                # Check if oldest tx is before our cutoff
                oldest_date = datetime.utcfromtimestamp(txs[-1].get('timestamp', 0)).strftime('%Y-%m-%d')
                if oldest_date < cutoff:
                    break

                before_sig = txs[-1].get('signature')
                if not before_sig or len(txs) < 100:
                    break

                page_count += 1
                await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                logger.error(f"Error fetching Solana txs page {page_count}: {e}")
                break

        today = datetime.utcnow().strftime('%Y-%m-%d')

        if not all_events:
            if current_lamports > 0:
                await log_service.info("balance_history",
                    f"No txs for Solana {address[:12]}... but has balance, recording today")
                return {today: current_sol}
            return {}

        # Sort oldest first
        all_events.sort(key=lambda e: e[0])
        await log_service.info("balance_history",
            f"Helius: Fetched {len(all_events)} Solana tx events for {address[:12]}...")

        # Step 3: Filter to recent, anchor + replay
        effective_start = latest_date if latest_date else cutoff
        net_change = 0
        tx_changes = []

        for _ts, tx_date, change in all_events:
            if tx_date >= effective_start:
                net_change += change
                tx_changes.append((tx_date, change))

        starting_lamports = current_lamports - net_change
        starting_sol = starting_lamports / divisor

        await log_service.info("balance_history",
            f"Solana {address[:12]}...: current={current_sol:.6f}, "
            f"net_change={net_change / divisor:.6f}, "
            f"starting={starting_sol:.6f} ({len(tx_changes)} recent txs)")

        running_lamports = starting_lamports
        daily_balances = {}
        for tx_date, change in tx_changes:
            running_lamports += change
            if not latest_date or tx_date > latest_date:
                daily_balances[tx_date] = running_lamports / divisor

        if not latest_date or today > (latest_date or ''):
            daily_balances[today] = current_sol

        if daily_balances:
            daily_balances = self._fill_daily_gaps(daily_balances)

        return daily_balances

    # ------------------------------------------------------------------
    # Algorand Collector
    # ------------------------------------------------------------------

    async def _collect_algorand(self, address: str, latest_date: str,
                                cutoff: str) -> Dict[str, float]:
        """Collect Algorand balance history using Pera Wallet API.

        Strategy: anchor to current ALGO balance, replay transactions
        (pay, axfer, acfg, afrz, keyreg, appl) to reconstruct history.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to ALGO balance on that date.
        """
        divisor = CHAIN_DIVISOR['algorand']
        client = get_client("pera", timeout=30.0)

        # Step 1: Get current balance from Pera API
        try:
            resp = await client.get(f"{PERA_BASE_URL}/v1/accounts/{address}")
            if resp.status_code == 404:
                await log_service.info("balance_history",
                    f"Algorand address not found: {address[:12]}...")
                return {}
            if resp.status_code != 200:
                logger.error(f"Pera account error: {resp.status_code}")
                return {}
            data = resp.json()
            current_microalgos = data.get('amount', 0)
            current_algo = current_microalgos / divisor
            await log_service.info("balance_history",
                f"Current Algorand balance for {address[:12]}...: {current_algo:.6f} ALGO")
        except Exception as e:
            logger.error(f"Error fetching Algorand balance: {e}")
            return {}

        # Step 2: Fetch transactions (paginated with 'next' token)
        all_events = []  # (timestamp, date_str, change_microalgos)
        next_token = None
        page_count = 0

        while True:
            try:
                url = f"{PERA_BASE_URL}/v1/accounts/{address}/transactions"
                params = {"limit": 100}
                if next_token:
                    params["next"] = next_token

                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.error(f"Pera txs error: {resp.status_code}")
                    break

                data = resp.json()
                txs = data.get('transactions', [])
                if not txs:
                    break

                for tx in txs:
                    # Round-time is Unix timestamp
                    ts = tx.get('round-time', 0)
                    if not ts:
                        continue
                    tx_date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
                    tx_type = tx.get('tx-type', '')
                    sender = tx.get('sender', '')
                    fee = tx.get('fee', 0)
                    is_sender = sender == address

                    change = 0

                    if tx_type == 'pay':
                        pay = tx.get('payment-transaction', {})
                        amount = pay.get('amount', 0)
                        receiver = pay.get('receiver', '')
                        if is_sender:
                            change -= (amount + fee)
                        if receiver == address:
                            change += amount
                        # Close-remainder-to: remaining balance sent to this address
                        close_to = pay.get('close-remainder-to', '')
                        close_amount = tx.get('closing-amount', 0)
                        if close_to == address and not is_sender:
                            change += close_amount
                        elif is_sender and close_to:
                            change -= close_amount

                    elif tx_type in ('axfer', 'acfg', 'afrz', 'keyreg'):
                        # These only cost the fee for the native balance
                        if is_sender:
                            change -= fee

                    elif tx_type == 'appl':
                        # Application call: fee + check inner transactions
                        if is_sender:
                            change -= fee
                        # Inner transactions may contain payment transfers
                        for inner in tx.get('inner-txns', []):
                            if inner.get('tx-type') == 'pay':
                                inner_pay = inner.get('payment-transaction', {})
                                inner_amount = inner_pay.get('amount', 0)
                                inner_sender = inner.get('sender', '')
                                inner_receiver = inner_pay.get('receiver', '')
                                if inner_sender == address:
                                    change -= inner_amount
                                if inner_receiver == address:
                                    change += inner_amount

                    else:
                        # Unknown type — just account for fee if sender
                        if is_sender:
                            change -= fee

                    if change != 0:
                        all_events.append((ts, tx_date, change))

                # Check if oldest tx is before cutoff
                oldest_ts = txs[-1].get('round-time', 0)
                if oldest_ts:
                    oldest_date = datetime.utcfromtimestamp(oldest_ts).strftime('%Y-%m-%d')
                    if oldest_date < cutoff:
                        break

                next_token = data.get('next-token')
                if not next_token or len(txs) < 100:
                    break

                page_count += 1
                await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                logger.error(f"Error fetching Algorand txs page {page_count}: {e}")
                break

        today = datetime.utcnow().strftime('%Y-%m-%d')

        if not all_events:
            if current_microalgos > 0:
                await log_service.info("balance_history",
                    f"No txs for Algorand {address[:12]}... but has balance, recording today")
                return {today: current_algo}
            return {}

        # Sort oldest first
        all_events.sort(key=lambda e: e[0])
        await log_service.info("balance_history",
            f"Pera: Fetched {len(all_events)} Algorand tx events for {address[:12]}...")

        # Step 3: Filter to recent, anchor + replay
        effective_start = latest_date if latest_date else cutoff
        net_change = 0
        tx_changes = []

        for _ts, tx_date, change in all_events:
            if tx_date >= effective_start:
                net_change += change
                tx_changes.append((tx_date, change))

        starting_microalgos = current_microalgos - net_change
        starting_algo = starting_microalgos / divisor

        await log_service.info("balance_history",
            f"Algorand {address[:12]}...: current={current_algo:.6f}, "
            f"net_change={net_change / divisor:.6f}, "
            f"starting={starting_algo:.6f} ({len(tx_changes)} recent txs)")

        running_microalgos = starting_microalgos
        daily_balances = {}
        for tx_date, change in tx_changes:
            running_microalgos += change
            if not latest_date or tx_date > latest_date:
                daily_balances[tx_date] = running_microalgos / divisor

        if not latest_date or today > (latest_date or ''):
            daily_balances[today] = current_algo

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
        """Fetch daily historical prices via the V2 engine's PriceEnricher.

        Delegates to the engine which uses a multi-source strategy:
          1. engine_price_history cache (instant, no API calls)
          2. CoinGecko /market_chart?days=365 bulk (free tier, 1 API call)
          3. DefiLlama per-date for older dates (rate-limited)
        Results are cached in engine_price_history for future reuse.

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to USD price.
        """
        from engine.enrichment.price_enricher import price_enricher

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = min(datetime.strptime(end_date, '%Y-%m-%d'), datetime.utcnow())
        dates = []
        current = start_dt
        while current <= end_dt:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        await log_service.info("balance_history",
            f"Fetching {len(dates)} {symbol} prices ({start_date} to {end_date})")

        result = await price_enricher.fetch_historical_prices_batch(symbol, dates)

        coverage_pct = (len(result) / len(dates) * 100) if dates else 0
        logger.info(f"Historical prices for {symbol}: {len(result)}/{len(dates)} dates ({coverage_pct:.0f}% coverage)")

        if not result:
            logger.warning(f"Zero prices fetched for {symbol} ({start_date} to {end_date})")
            await log_service.warning("balance_history",
                f"Zero prices fetched for {symbol}. Check API connectivity.")
        else:
            await log_service.info("balance_history",
                f"Got {len(result)}/{len(dates)} {symbol} prices ({coverage_pct:.0f}% coverage)")

        return result

    # ------------------------------------------------------------------
    # Price backfill
    # ------------------------------------------------------------------

    async def backfill_prices(self, user_id: int) -> dict:
        """Re-fetch prices for all balance_history records with native_price_usd = 0.

        Uses CoinGecko market_chart/range for bulk price fetching.

        Returns:
            Dict with status and count of updated records.
        """
        unpriced = await get_unpriced_date_ranges(user_id)
        if not unpriced:
            logger.info(f"No unpriced records found for user {user_id}")
            return {'status': 'nothing_to_backfill', 'updated': 0}

        total_updated = 0
        for group in unpriced:
            symbol = group['symbol']
            count = group['count']
            logger.info(f"Backfilling {count} {symbol} records ({group['min_date']} to {group['max_date']})")
            await log_service.info("balance_history", f"Backfilling {count} {symbol} records ({group['min_date']} to {group['max_date']})")

            prices = await self._fetch_historical_prices(symbol, group['min_date'], group['max_date'])

            if prices:
                updated = await update_balance_history_prices(user_id, symbol, prices)
                total_updated += updated
                logger.info(f"Backfilled {updated}/{count} {symbol} prices")
                await log_service.info("balance_history", f"Backfilled {updated}/{count} {symbol} prices")
            else:
                logger.warning(f"No prices fetched for {symbol}, skipping backfill")
                await log_service.warning("balance_history", f"No prices fetched for {symbol} during backfill")

        return {'status': 'completed', 'updated': total_updated}

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

                    # Try V2 engine backfill first, fall back to V1
                    try:
                        from engine.orchestrator import backfill_orchestrator
                        from engine.models import BackfillRequest, ChainId, WorkDomain
                        from engine import db as engine_db

                        request = BackfillRequest(
                            chains=list(ChainId),
                            domains=[WorkDomain.INDEX, WorkDomain.HYDRATE, WorkDomain.NORMALIZE, WorkDomain.ENRICH_PRICE],
                        )
                        backfill_id = await backfill_orchestrator.plan_backfill(user_id, request)
                        run_id = await engine_db.create_scheduler_run(user_id, backfill_id, 'scheduled')
                        backfill_orchestrator.set_run_id(backfill_id, run_id)
                        await backfill_orchestrator.run_backfill(backfill_id)
                        logger.info(f"Scheduler: V2 engine backfill started for user {user_id}: {backfill_id}")
                    except Exception as engine_err:
                        logger.warning(f"Scheduler: V2 engine failed ({engine_err}), using V1 collector")
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
