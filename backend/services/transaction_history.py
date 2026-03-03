"""
Transaction History Service - Fetch and normalize transactions from all blockchains

Supported Blockchains:
- Cardano: Blockfrost API for transaction history with UTXO parsing
- Ethereum: Etherscan API for transactions and token transfers
- Bitcoin: Blockstream API with Mempool.space fallback
- Solana: Helius API for enhanced transaction data
- Polygon: Polygonscan API (EVM-compatible)
- Base: Basescan API (EVM-compatible)

Note: Exchange transaction support (Coinbase, Binance, etc.) is handled separately
through the exchanges router as they use different APIs and data models.
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import aiosqlite

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH
from database import get_all_wallets
from services.cardano import cardano_service
from services.ethereum import ethereum_service
from services.etherscan import etherscan_service
from services.bitcoin import bitcoin_service
from services.solana import solana_service
from services.polygon import polygon_service
from services.base import base_service
from services.coinbase import coinbase_service
from services.http_client import get_client, blockfrost_fetch

logger = logging.getLogger(__name__)


async def _syslog(level: str, msg: str, exc: Exception = None, **extra):
    """Write to the system logs page (LoggingService) at the given level."""
    try:
        from services.logging_service import get_logging_service
        svc = get_logging_service()
        if level == "error":
            await svc.error("transactions", msg, exc_info=exc, **extra)
        elif level == "warning":
            await svc.warning("transactions", msg, exc_info=exc, **extra)
        elif level == "info":
            await svc.info("transactions", msg, **extra)
        else:
            await svc.debug("transactions", msg, **extra)
    except Exception:
        pass  # Never let logging break the flow


class TransactionHistoryService:
    """Fetch and normalize transactions from all blockchains."""

    # V2 engine chain → native token symbol/name mapping
    _CHAIN_NATIVE = {
        'cardano': ('ADA', 'Cardano'),
        'bitcoin': ('BTC', 'Bitcoin'),
        'ethereum': ('ETH', 'Ethereum'),
        'solana': ('SOL', 'Solana'),
        'polygon': ('MATIC', 'Polygon'),
        'base': ('ETH', 'Ethereum'),
        'algorand': ('ALGO', 'Algorand'),
        'bnb': ('BNB', 'BNB Chain'),
        'tron': ('TRX', 'Tron'),
        'avalanche': ('AVAX', 'Avalanche'),
        'arbitrum': ('ETH', 'Ethereum'),
    }

    def __init__(self):
        self.supported_blockchains = ['cardano', 'ethereum', 'bitcoin', 'solana', 'polygon', 'base']

    def _is_transaction_newer(self, tx: dict, newest_dt: datetime, blockchain: str) -> bool:
        """
        Check if a transaction is newer than the newest one in database.

        Args:
            tx: Raw transaction from blockchain API
            newest_dt: Newest transaction datetime from database
            blockchain: Blockchain name

        Returns:
            True if transaction is newer than newest_dt
        """
        try:
            if blockchain in ['ethereum', 'polygon', 'base']:
                # EVM chains use 'timeStamp' field
                timestamp = int(tx.get('timeStamp', tx.get('timestamp', 0)))
                tx_time = datetime.fromtimestamp(timestamp) if timestamp > 0 else datetime.utcnow()
            elif blockchain == 'bitcoin':
                # Bitcoin uses status.block_time
                status = tx.get('status', {})
                block_time = status.get('block_time', 0)
                tx_time = datetime.fromtimestamp(block_time) if block_time > 0 else datetime.utcnow()
            elif blockchain == 'cardano':
                # Cardano uses block_time
                block_time = tx.get('block_time', 0)
                tx_time = datetime.fromtimestamp(block_time) if block_time > 0 else datetime.utcnow()
            elif blockchain == 'solana':
                # Solana uses timestamp
                timestamp = tx.get('timestamp', 0)
                tx_time = datetime.fromtimestamp(timestamp) if timestamp > 0 else datetime.utcnow()
            else:
                # Unknown format, keep the transaction to be safe
                return True

            return tx_time > newest_dt

        except Exception as e:
            logger.error(f"Error comparing transaction time: {e}")
            return True  # Keep transaction if we can't determine age

    async def _get_v2_events_as_transactions(
        self, user_id: int, days: int = 7, blockchain: str = None
    ) -> List[dict]:
        """Query V2 engine events and convert to transaction_history format."""
        try:
            from engine import db as engine_db

            min_time = int((datetime.utcnow() - timedelta(days=days)).timestamp())
            events = await engine_db.get_events(
                user_id, chain=blockchain, min_time=min_time, limit=25000
            )
            if not events:
                chain_label = blockchain or "all chains"
                await _syslog("info", f"V2 events query: 0 events for {chain_label} (days={days})")
                return []

            # Group events by tx_id, take the primary event per tx
            seen_tx = {}
            for evt in events:
                tx_id = evt.get('tx_id', '')
                if tx_id not in seen_tx:
                    seen_tx[tx_id] = evt

            transactions = []
            for tx_id, evt in seen_tx.items():
                chain = evt.get('chain', '')
                asset_id = evt.get('asset_id', '')
                if asset_id == 'native':
                    symbol, name = self._CHAIN_NATIVE.get(chain, (asset_id, ''))
                else:
                    symbol, name = asset_id, ''

                direction = evt.get('direction', '')
                mapped_dir = 'sent' if direction == 'out' else 'received' if direction == 'in' else direction

                from_addr = evt.get('account_id', '') if direction == 'out' else (evt.get('counterparty') or '')
                to_addr = (evt.get('counterparty') or '') if direction == 'out' else evt.get('account_id', '')

                block_time = evt.get('block_time', 0)
                tx_time = datetime.utcfromtimestamp(block_time).isoformat() if block_time else None

                transactions.append({
                    'user_id': user_id,
                    'wallet_id': None,
                    'blockchain': chain,
                    'tx_hash': tx_id,
                    'tx_time': tx_time,
                    'tx_time_formatted': tx_time,
                    'direction': mapped_dir,
                    'amount': str(evt.get('amount', '0')),
                    'token_symbol': symbol,
                    'token_name': name,
                    'from_address': from_addr,
                    'to_address': to_addr,
                    'fee': str(evt.get('fee', '0')) if evt.get('fee') else '0',
                    'status': 'confirmed',
                    'metadata': json.dumps(evt.get('metadata', {})) if isinstance(evt.get('metadata'), dict) else (evt.get('metadata') or ''),
                    'fetched_at': evt.get('created_at', ''),
                    'wallet_address': evt.get('account_id', ''),
                    'wallet_name': None,
                })

            await _syslog("info", f"V2 events: converted {len(transactions)} events "
                          f"({len(events)} raw) to transaction format")
            return transactions
        except Exception as e:
            await _syslog("error", f"V2 events query failed: {e}", exc=e)
            return []

    async def get_transaction_bounds(self, user_id: int, wallet_id: int, blockchain: str) -> Optional[dict]:
        """
        Get the newest and oldest transaction timestamps for a wallet.

        Returns:
            Dict with 'newest' and 'oldest' datetime, or None if no transactions exist
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("""
                SELECT
                    MAX(tx_time) as newest,
                    MIN(tx_time) as oldest
                FROM transaction_history
                WHERE user_id = ? AND wallet_id = ? AND blockchain = ?
            """, (user_id, wallet_id, blockchain))

            row = await cursor.fetchone()
            if row and row[0]:  # If newest exists
                return {
                    'newest': row[0],
                    'oldest': row[1]
                }
            return None

    async def _get_highest_block(self, user_id: int, wallet_id: int, blockchain: str) -> Optional[int]:
        """Get the highest block number from existing transactions for incremental EVM fetching."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("""
                SELECT MAX(json_extract(metadata, '$.block_number'))
                FROM transaction_history
                WHERE user_id = ? AND wallet_id = ? AND blockchain = ?
                AND metadata IS NOT NULL AND metadata != ''
            """, (user_id, wallet_id, blockchain))
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    return int(row[0])
                except (ValueError, TypeError):
                    return None
            return None

    async def fetch_transactions(
        self,
        user_id: int,
        days: int = 7,
        blockchain: str = None,
        wallet_ids: List[int] = None,
        force_full: bool = False
    ) -> Dict[str, int]:
        """
        Fetch transactions from all wallets for a user.

        Tries V2 engine indexing first (populates engine_events), then
        falls back to V1 chain-specific fetchers (populates transaction_history).

        Args:
            user_id: User ID to fetch transactions for
            days: Number of days of transaction history
            blockchain: Filter by specific blockchain (None for all)
            wallet_ids: Optional list of wallet IDs to fetch for (None for all)
            force_full: If True, skip incremental logic and fetch full history

        Returns:
            Dict with counts of transactions fetched per blockchain
        """
        # Try V2 engine indexing to populate engine_events
        chain_label = blockchain or "all chains"
        await _syslog("info", f"Transaction fetch started: {chain_label}, days={days}")
        try:
            from engine.orchestrator import backfill_orchestrator
            from engine.models import BackfillRequest, ChainId, WorkDomain
            from engine import db as engine_db

            all_wallets = await get_all_wallets(user_id)
            selected = all_wallets
            if blockchain:
                selected = [w for w in selected if w['blockchain'] == blockchain]
            if wallet_ids:
                selected = [w for w in selected if w['id'] in wallet_ids]

            if not selected:
                await _syslog("warning", f"No wallets found for {chain_label}")

            chains = set()
            for w in selected:
                c = w.get('blockchain', '').lower()
                try:
                    chains.add(ChainId(c))
                except ValueError:
                    pass

            if chains:
                await _syslog("info", f"V2 engine: starting backfill for {[c.value for c in chains]} "
                              f"({len(selected)} wallets)")
                request = BackfillRequest(
                    chains=list(chains),
                    wallet_ids=wallet_ids,
                    domains=[WorkDomain.INDEX, WorkDomain.HYDRATE, WorkDomain.NORMALIZE],
                )
                backfill_id = await backfill_orchestrator.plan_backfill(user_id, request)
                await backfill_orchestrator.run_backfill(backfill_id)

                # Report V2 results
                event_count = await engine_db.get_event_count(user_id, blockchain)
                await _syslog("info", f"V2 engine: backfill {backfill_id} complete, "
                              f"{event_count} engine_events for {chain_label}")
            else:
                await _syslog("warning", f"V2 engine: no valid chains resolved from wallets")
        except Exception as e:
            await _syslog("error", f"V2 engine failed for {chain_label}: {e}", exc=e)
            logger.error(f"V2 engine indexing for transactions failed: {e}")

        start_time = datetime.utcnow() - timedelta(days=days)

        # V1 chain-specific fetchers (still runs to populate transaction_history table)
        wallets = await get_all_wallets(user_id)

        if not wallets:
            logger.info(f"No wallets found for user {user_id}")
            return {}

        # Filter by blockchain if specified
        if blockchain:
            wallets = [w for w in wallets if w['blockchain'] == blockchain]

        # Filter by wallet IDs if specified
        if wallet_ids:
            wallets = [w for w in wallets if w['id'] in wallet_ids]

        counts = {}

        for wallet in wallets:
            wallet_id = wallet['id']
            chain = wallet['blockchain']
            address = wallet['address']

            logger.info(f"Fetching transactions for {chain} wallet {address[:12]}...")

            try:
                # For EVM chains: use block-based incremental fetching
                startblock = 0
                evm_chains = {'ethereum', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche'}
                if chain in evm_chains and not force_full:
                    highest_block = await self._get_highest_block(user_id, wallet_id, chain)
                    if highest_block:
                        startblock = highest_block + 1
                        logger.info(f"Incremental EVM fetch from block {startblock}")

                # Check existing transaction bounds for smart fetching (non-EVM)
                bounds = await self.get_transaction_bounds(user_id, wallet_id, chain)
                if bounds:
                    newest = bounds['newest']
                    oldest = bounds['oldest']
                    logger.info(f"Existing transactions: newest={newest}, oldest={oldest}")

                transactions = await self._fetch_blockchain_transactions(
                    chain, address, days, startblock=startblock,
                    force_full=force_full
                )

                if transactions:
                    # For non-EVM chains, filter by date (EVM uses startblock instead)
                    # Skip this filter during force_full to allow backfilling old data
                    if bounds and chain not in evm_chains and not force_full:
                        newest_dt = datetime.fromisoformat(bounds['newest']) if isinstance(bounds['newest'], str) else bounds['newest']

                        original_count = len(transactions)
                        transactions = [tx for tx in transactions if self._is_transaction_newer(tx, newest_dt, chain)]
                        logger.info(f"Filtered {original_count - len(transactions)} duplicate transactions")

                    # Normalize and save
                    normalized = []
                    for tx in transactions:
                        normalized_tx = await self.normalize_transaction(
                            chain, tx, address
                        )
                        if normalized_tx:
                            normalized.append(normalized_tx)

                    if normalized:
                        await self.save_transactions(user_id, wallet_id, normalized)
                        counts[chain] = counts.get(chain, 0) + len(normalized)
                        logger.info(f"Saved {len(normalized)} new transactions for {chain}")
                    else:
                        logger.info(f"No new transactions found for {chain} wallet")

            except Exception as e:
                await _syslog("error", f"V1 fetch failed for {chain}: {e}", exc=e)
                logger.error(f"Error fetching {chain} transactions: {e}")
                continue

        await _syslog("info", f"Transaction fetch complete: {counts or 'no new txs'}")
        return counts

    async def _fetch_blockchain_transactions(
        self,
        blockchain: str,
        address: str,
        days: int,
        startblock: int = 0,
        force_full: bool = False
    ) -> List[dict]:
        """
        Fetch transactions from blockchain-specific service.

        Args:
            blockchain: Blockchain name
            address: Wallet address
            days: Number of days of history
            startblock: Block number to start from (EVM chains only, 0 for full history)
            force_full: If True, fetch all available history (higher limits)

        Returns:
            List of raw transactions from blockchain API
        """
        evm_chains = {'ethereum', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche'}
        if blockchain in evm_chains:
            limit = 10000
        else:
            # For full backfill, use a generous limit; otherwise use the old formula
            if force_full:
                limit = 5000
            else:
                limit = min(500, days * 20)

        try:
            if blockchain == 'cardano':
                return await self._fetch_cardano_transactions(address, limit)
            elif blockchain in evm_chains:
                return await self._fetch_evm_transactions(blockchain, address, limit, startblock)
            elif blockchain == 'bitcoin':
                return await self._fetch_bitcoin_transactions(address, limit)
            elif blockchain == 'solana':
                return await self._fetch_solana_transactions(address, limit)
            else:
                await _syslog("warning", f"V1: unsupported blockchain '{blockchain}'")
                return []
        except Exception as e:
            await _syslog("error", f"V1 API call failed for {blockchain}: {e}", exc=e)
            return []

    async def _fetch_cardano_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Cardano transactions via Blockfrost with full pagination.

        Paginates through all transaction hashes (100 per page, max 50 pages),
        then fetches details and UTXOs for each transaction.
        Includes rate-limit delays between API calls.
        """
        MAX_PAGES = 50  # Safety cap: 50 pages x 100 = up to 5000 tx hashes

        try:
            # Get Blockfrost API key
            blockfrost_key = await cardano_service._get_blockfrost_key()
            if not blockfrost_key:
                logger.warning("Blockfrost API key not configured")
                return []

            headers = {"project_id": blockfrost_key}

            # --- Paginate through all transaction hashes (ascending for full history) ---
            all_tx_hashes = []
            page = 1

            while page <= MAX_PAGES and len(all_tx_hashes) < limit:
                response = await blockfrost_fetch(
                    f"/addresses/{address}/transactions",
                    headers=headers,
                    params={"count": 100, "page": page, "order": "asc"},
                    timeout=30.0
                )

                if response.status_code == 404:
                    break  # Address has no transactions
                if response.status_code != 200:
                    logger.error(f"Blockfrost transactions page {page} error: {response.status_code}")
                    break

                page_data = response.json()
                if not page_data:
                    break

                all_tx_hashes.extend(page_data)

                # If fewer than 100 results, we've reached the end
                if len(page_data) < 100:
                    break

                page += 1
                # Rate-limit delay between pages (Blockfrost: 10 req/s free tier)
                await asyncio.sleep(0.15)

            if not all_tx_hashes:
                return []

            # Trim to limit
            all_tx_hashes = all_tx_hashes[:limit]
            await _syslog("info", f"Cardano: fetched {len(all_tx_hashes)} tx hashes "
                          f"in {page} page(s) for {address[:20]}...")

            # --- Fetch details and UTXOs for each transaction ---
            detailed_txs = []
            for i, tx_info in enumerate(all_tx_hashes):
                tx_hash = tx_info.get('tx_hash')
                if not tx_hash:
                    continue

                try:
                    # Get transaction details
                    tx_response = await blockfrost_fetch(
                        f"/txs/{tx_hash}",
                        headers=headers,
                        timeout=30.0
                    )

                    if tx_response.status_code == 200:
                        tx_detail = tx_response.json()

                        # Get UTXOs for the transaction
                        utxo_response = await blockfrost_fetch(
                            f"/txs/{tx_hash}/utxos",
                            headers=headers,
                            timeout=30.0
                        )

                        if utxo_response.status_code == 200:
                            utxos = utxo_response.json()
                            tx_detail['utxos'] = utxos

                        detailed_txs.append(tx_detail)

                    # Rate-limit delay every 5 detail fetches
                    if (i + 1) % 5 == 0:
                        await asyncio.sleep(0.2)

                except Exception as e:
                    logger.warning(f"Error fetching Cardano tx details {tx_hash[:16]}...: {e}")
                    continue

            logger.info(f"Fetched {len(detailed_txs)} Cardano transactions (from {len(all_tx_hashes)} hashes)")
            return detailed_txs

        except Exception as e:
            logger.error(f"Error fetching Cardano transactions: {e}")
            return []

    async def _fetch_evm_transactions(self, chain: str, address: str, limit: int,
                                       startblock: int = 0) -> List[dict]:
        """Fetch EVM transactions via Etherscan-compatible API with full pagination."""
        txs = await etherscan_service.get_transactions(chain, address, limit, startblock=startblock)
        token_txs = await etherscan_service.get_token_transfers(chain, address, limit, startblock=startblock)
        return txs + token_txs

    async def _fetch_ethereum_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Ethereum transactions via Etherscan (legacy wrapper)."""
        return await self._fetch_evm_transactions('ethereum', address, limit)

    async def _fetch_bitcoin_transactions_from_api(
        self, address: str, limit: int, base_url: str, source_name: str
    ) -> List[dict]:
        """Fetch Bitcoin transactions from Blockstream/Mempool API with pagination.

        Both APIs return 25 transactions per page and support pagination via
        the last_seen_txid parameter: /address/{addr}/txs/chain/{last_txid}

        Args:
            address: Bitcoin wallet address
            limit: Maximum total transactions to fetch
            base_url: API base URL (Blockstream or Mempool.space)
            source_name: Human-readable name for logging

        Returns:
            List of detailed transaction dicts
        """
        MAX_PAGES = 80  # Safety cap: 80 pages x 25 = up to 2000 txs

        try:
            client = get_client("blockfrost", timeout=30.0)
            all_txs = []
            last_txid = None
            page = 0

            while page < MAX_PAGES and len(all_txs) < limit:
                if last_txid:
                    url = f"{base_url}/address/{address}/txs/chain/{last_txid}"
                else:
                    url = f"{base_url}/address/{address}/txs"

                response = await client.get(url)

                if response.status_code != 200:
                    if page == 0:
                        logger.warning(f"{source_name} API error: {response.status_code}")
                        return []  # Return empty so caller can try fallback
                    break  # Partial results are fine

                page_txs = response.json()
                if not page_txs:
                    break

                all_txs.extend(page_txs)

                # If fewer than 25, we've reached the end
                if len(page_txs) < 25:
                    break

                # The last txid is used for the next page cursor
                last_txid = page_txs[-1].get('txid')
                if not last_txid:
                    break

                page += 1
                await asyncio.sleep(0.2)  # Rate-limit delay

            # Trim to limit
            all_txs = all_txs[:limit]

            if not all_txs:
                return []

            await _syslog("info", f"Bitcoin: fetched {len(all_txs)} tx summaries "
                          f"from {source_name} in {page + 1} page(s)")

            # The list endpoint already returns full transaction data including
            # inputs/outputs, so we don't need separate detail fetches.
            # The txs endpoint returns the same format as /tx/{txid}.
            logger.info(f"Fetched {len(all_txs)} Bitcoin transactions from {source_name}")
            return all_txs

        except Exception as e:
            logger.error(f"{source_name} error: {e}")
            return []

    async def _fetch_bitcoin_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Bitcoin transactions from Blockstream API with Mempool.space fallback.

        Uses paginated fetching to retrieve full history.
        """
        # Try Blockstream first
        txs = await self._fetch_bitcoin_transactions_from_api(
            address, limit, bitcoin_service.base_url, "Blockstream"
        )
        if txs:
            return txs

        # Fallback to Mempool.space
        from config import MEMPOOL_BASE_URL
        logger.info("Blockstream returned no results, trying Mempool.space fallback")
        return await self._fetch_bitcoin_transactions_from_api(
            address, limit, MEMPOOL_BASE_URL, "Mempool.space"
        )

    async def _fetch_bitcoin_transactions_mempool(self, address: str, limit: int) -> List[dict]:
        """Fetch Bitcoin transactions from Mempool.space API (fallback). Legacy wrapper."""
        from config import MEMPOOL_BASE_URL
        return await self._fetch_bitcoin_transactions_from_api(
            address, limit, MEMPOOL_BASE_URL, "Mempool.space"
        )

    async def _fetch_solana_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Solana transactions using Helius API with pagination.

        Helius enhanced transactions endpoint supports pagination via the
        'before' parameter (pass the last signature to get the next page).
        Each page returns up to 100 transactions.
        """
        from config import HELIUS_BASE_URL
        MAX_PAGES = 50  # Safety cap: 50 pages x 100 = up to 5000 txs
        PAGE_SIZE = 100

        try:
            # Get Helius API key
            helius_key = await solana_service.get_api_key()
            if not helius_key:
                logger.warning("Helius API key not configured")
                return []

            client = get_client("blockfrost", timeout=30.0)
            all_transactions = []
            before_sig = None
            page = 0

            while page < MAX_PAGES and len(all_transactions) < limit:
                params = {
                    "api-key": helius_key,
                    "limit": min(PAGE_SIZE, limit - len(all_transactions))
                }
                if before_sig:
                    params["before"] = before_sig

                response = await client.get(
                    f"{HELIUS_BASE_URL}/addresses/{address}/transactions",
                    params=params
                )

                if response.status_code != 200:
                    if page == 0:
                        logger.error(f"Helius transactions error: {response.status_code}")
                        return []
                    break  # Partial results are fine

                page_txs = response.json()
                if not page_txs:
                    break

                all_transactions.extend(page_txs)

                # If fewer than PAGE_SIZE, we've reached the end
                if len(page_txs) < PAGE_SIZE:
                    break

                # Get the last signature for pagination cursor
                last_tx = page_txs[-1]
                before_sig = last_tx.get('signature')
                if not before_sig:
                    break

                page += 1
                await asyncio.sleep(0.15)  # Rate-limit delay

            all_transactions = all_transactions[:limit]
            logger.info(f"Fetched {len(all_transactions)} Solana transactions "
                        f"in {page + 1} page(s)")
            return all_transactions

        except Exception as e:
            logger.error(f"Error fetching Solana transactions: {e}")
            return []

    async def _fetch_polygon_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Polygon transactions via Polygonscan (legacy wrapper)."""
        return await self._fetch_evm_transactions('polygon', address, limit)

    async def _fetch_base_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Base transactions via Basescan (legacy wrapper)."""
        return await self._fetch_evm_transactions('base', address, limit)

    async def normalize_transaction(
        self,
        blockchain: str,
        raw_tx: dict,
        wallet_address: str
    ) -> Optional[dict]:
        """
        Normalize transaction from chain-specific format to common format.

        Args:
            blockchain: Blockchain name
            raw_tx: Raw transaction from blockchain API
            wallet_address: User's wallet address

        Returns:
            Normalized transaction dict or None if invalid
        """
        try:
            if blockchain in ['ethereum', 'polygon', 'base', 'bsc', 'arbitrum', 'avalanche']:
                return await self._normalize_evm_transaction(raw_tx, wallet_address, blockchain)
            elif blockchain == 'cardano':
                return await self._normalize_cardano_transaction(raw_tx, wallet_address)
            elif blockchain == 'bitcoin':
                return await self._normalize_bitcoin_transaction(raw_tx, wallet_address)
            elif blockchain == 'solana':
                return await self._normalize_solana_transaction(raw_tx, wallet_address)
            else:
                return None
        except Exception as e:
            logger.error(f"Error normalizing {blockchain} transaction: {e}")
            return None

    async def _normalize_evm_transaction(
        self,
        tx: dict,
        wallet_address: str,
        blockchain: str
    ) -> dict:
        """Normalize EVM-based transaction (Ethereum, Polygon, Base)."""
        from_addr = tx.get('from', '').lower()
        to_addr = tx.get('to', '').lower()
        wallet_lower = wallet_address.lower()

        # Determine direction
        direction = 'sent' if from_addr == wallet_lower else 'received'

        # Extract token info
        token_symbol = tx.get('tokenSymbol', tx.get('token_symbol', None))
        token_name = tx.get('tokenName', tx.get('token_name', None))

        # If no token info, it's native currency
        native_defaults = {
            'ethereum': ('ETH', 'Ethereum'),
            'polygon': ('MATIC', 'Polygon'),
            'base': ('ETH', 'Base ETH'),
            'bsc': ('BNB', 'BNB'),
            'arbitrum': ('ETH', 'Arbitrum ETH'),
            'avalanche': ('AVAX', 'Avalanche'),
        }
        if not token_symbol:
            token_symbol, token_name = native_defaults.get(blockchain, ('ETH', blockchain.title()))

        # Extract amount
        amount = tx.get('value', 0)
        if isinstance(amount, str):
            try:
                amount = float(amount)
            except Exception:
                amount = 0

        # Calculate fee
        gas_used = int(tx.get('gas_used', tx.get('gasUsed', 0)))
        gas_price = int(tx.get('gas_price', tx.get('gasPrice', 0)))
        fee_wei = gas_used * gas_price
        fee = fee_wei / 10**18 if fee_wei > 0 else 0

        # Get timestamp
        timestamp = tx.get('timestamp', tx.get('timeStamp', 0))
        if isinstance(timestamp, str):
            timestamp = int(timestamp)
        tx_time = datetime.fromtimestamp(timestamp) if timestamp > 0 else datetime.utcnow()

        # Status
        is_error = tx.get('is_error', tx.get('isError', '0'))
        status = 'failed' if (is_error == '1' or is_error is True) else 'confirmed'

        return {
            'blockchain': blockchain,
            'tx_hash': tx.get('hash', ''),
            'tx_time': tx_time,
            'direction': direction,
            'amount': str(amount),
            'token_symbol': token_symbol,
            'token_name': token_name,
            'from_address': from_addr,
            'to_address': to_addr,
            'fee': str(fee),
            'status': status,
            'metadata': json.dumps({
                'block_number': tx.get('block_number', tx.get('blockNumber', 0)),
                'gas_used': gas_used,
                'gas_price': gas_price
            })
        }

    async def _normalize_cardano_transaction(self, tx: dict, wallet_address: str) -> dict:
        """Normalize Cardano transaction from Blockfrost format."""
        # Get transaction timestamp
        block_time = tx.get('block_time', 0)
        tx_time = datetime.fromtimestamp(block_time) if block_time > 0 else datetime.utcnow()

        # Parse UTXOs to determine direction and amount
        utxos = tx.get('utxos', {})
        inputs = utxos.get('inputs', [])
        outputs = utxos.get('outputs', [])

        # Check if wallet is in inputs (sending)
        is_sender = False
        for input_utxo in inputs:
            if input_utxo.get('address') == wallet_address:
                is_sender = True
                break

        # Calculate amounts
        amount_lovelace = 0
        token_symbol = 'ADA'
        token_name = 'Cardano'
        from_addresses = []
        to_addresses = []

        if is_sender:
            # Sent transaction - sum outputs not going back to wallet
            direction = 'sent'
            for output in outputs:
                output_addr = output.get('address', '')
                if output_addr != wallet_address:
                    # Find ADA amount
                    for amount_item in output.get('amount', []):
                        if amount_item.get('unit') == 'lovelace':
                            amount_lovelace += int(amount_item.get('quantity', 0))
                    if output_addr and output_addr not in to_addresses:
                        to_addresses.append(output_addr)

            # Get sender addresses from inputs
            for input_utxo in inputs:
                addr = input_utxo.get('address', '')
                if addr and addr not in from_addresses:
                    from_addresses.append(addr)
        else:
            # Received transaction - sum outputs to wallet
            direction = 'received'
            for output in outputs:
                if output.get('address') == wallet_address:
                    for amount_item in output.get('amount', []):
                        if amount_item.get('unit') == 'lovelace':
                            amount_lovelace += int(amount_item.get('quantity', 0))
                        else:
                            # Native token - use first non-ADA token found
                            if token_symbol == 'ADA':
                                asset_id = amount_item.get('unit', '')
                                asset_name_hex = asset_id[56:] if len(asset_id) > 56 else ''
                                try:
                                    token_name = bytes.fromhex(asset_name_hex).decode('utf-8')
                                    token_symbol = token_name[:10]  # Truncate if too long
                                except Exception:
                                    token_symbol = 'TOKEN'

            # Get sender addresses
            for input_utxo in inputs:
                addr = input_utxo.get('address', '')
                if addr and addr not in from_addresses:
                    from_addresses.append(addr)

            to_addresses = [wallet_address]

        # Convert lovelace to ADA
        amount_ada = amount_lovelace / 1_000_000

        # Get fee
        fee_lovelace = int(tx.get('fees', 0))
        fee_ada = fee_lovelace / 1_000_000

        return {
            'blockchain': 'cardano',
            'tx_hash': tx.get('hash', ''),
            'tx_time': tx_time,
            'direction': direction,
            'amount': str(amount_ada),
            'token_symbol': token_symbol,
            'token_name': token_name,
            'from_address': from_addresses[0] if from_addresses else '',
            'to_address': to_addresses[0] if to_addresses else wallet_address,
            'fee': str(fee_ada),
            'status': 'confirmed',
            'metadata': json.dumps({
                'block_height': tx.get('block_height', 0),
                'slot': tx.get('slot', 0),
                'size': tx.get('size', 0)
            })
        }

    async def _normalize_bitcoin_transaction(self, tx: dict, wallet_address: str) -> dict:
        """Normalize Bitcoin transaction from Blockstream format."""
        # Get transaction timestamp
        status = tx.get('status', {})
        block_time = status.get('block_time', 0)
        tx_time = datetime.fromtimestamp(block_time) if block_time > 0 else datetime.utcnow()

        # Determine direction and calculate amount
        vin = tx.get('vin', [])
        vout = tx.get('vout', [])

        # Check if wallet address is in inputs (sending)
        is_sender = False
        for input_tx in vin:
            prevout = input_tx.get('prevout', {})
            if prevout.get('scriptpubkey_address') == wallet_address:
                is_sender = True
                break

        # Calculate amounts
        if is_sender:
            # Sent transaction - calculate amount sent to others
            direction = 'sent'
            amount_satoshis = 0
            to_addresses = []

            for output in vout:
                output_addr = output.get('scriptpubkey_address', '')
                output_value = output.get('value', 0)

                # Don't count change back to self
                if output_addr != wallet_address:
                    amount_satoshis += output_value
                    if output_addr and output_addr not in to_addresses:
                        to_addresses.append(output_addr)

            to_address = to_addresses[0] if to_addresses else ''
        else:
            # Received transaction - calculate amount received
            direction = 'received'
            amount_satoshis = 0
            from_addresses = []

            for output in vout:
                if output.get('scriptpubkey_address') == wallet_address:
                    amount_satoshis += output.get('value', 0)

            # Get sender addresses from inputs
            for input_tx in vin:
                prevout = input_tx.get('prevout', {})
                addr = prevout.get('scriptpubkey_address', '')
                if addr and addr not in from_addresses:
                    from_addresses.append(addr)

            to_address = wallet_address

        # Convert satoshis to BTC
        amount_btc = amount_satoshis / 100_000_000

        # Get fee
        fee_satoshis = tx.get('fee', 0)
        fee_btc = fee_satoshis / 100_000_000

        # Determine status
        is_confirmed = status.get('confirmed', False)
        tx_status = 'confirmed' if is_confirmed else 'pending'

        return {
            'blockchain': 'bitcoin',
            'tx_hash': tx.get('txid', ''),
            'tx_time': tx_time,
            'direction': direction,
            'amount': str(amount_btc),
            'token_symbol': 'BTC',
            'token_name': 'Bitcoin',
            'from_address': from_addresses[0] if 'from_addresses' in locals() and from_addresses else '',
            'to_address': to_address,
            'fee': str(fee_btc),
            'status': tx_status,
            'metadata': json.dumps({
                'block_height': status.get('block_height', 0),
                'confirmations': tx.get('confirmations', 0),
                'size': tx.get('size', 0),
                'weight': tx.get('weight', 0)
            })
        }

    async def _normalize_solana_transaction(self, tx: dict, wallet_address: str) -> dict:
        """Normalize Solana transaction from Helius format."""
        # Get transaction timestamp
        timestamp = tx.get('timestamp', 0)
        tx_time = datetime.fromtimestamp(timestamp) if timestamp > 0 else datetime.utcnow()

        # Get native transfers
        native_transfers = tx.get('nativeTransfers', [])
        token_transfers = tx.get('tokenTransfers', [])

        # Determine direction and amount
        direction = 'received'
        amount = 0
        token_symbol = 'SOL'
        token_name = 'Solana'
        from_address = ''
        to_address = wallet_address

        # Check native SOL transfers
        for transfer in native_transfers:
            from_addr = transfer.get('fromUserAccount', '')
            to_addr = transfer.get('toUserAccount', '')
            transfer_amount = transfer.get('amount', 0)

            if from_addr == wallet_address:
                # Sending SOL
                direction = 'sent'
                amount += transfer_amount
                to_address = to_addr
                from_address = from_addr
            elif to_addr == wallet_address:
                # Receiving SOL
                direction = 'received'
                amount += transfer_amount
                from_address = from_addr
                to_address = to_addr

        # Check SPL token transfers if no native transfers
        if amount == 0 and token_transfers:
            for transfer in token_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                transfer_amount = transfer.get('tokenAmount', 0)
                mint = transfer.get('mint', '')

                if from_addr == wallet_address or to_addr == wallet_address:
                    # Get token info
                    token_symbol = transfer.get('tokenSymbol', 'TOKEN')
                    token_name = transfer.get('tokenName', token_symbol)

                    if from_addr == wallet_address:
                        direction = 'sent'
                        amount = transfer_amount
                        to_address = to_addr
                        from_address = from_addr
                    else:
                        direction = 'received'
                        amount = transfer_amount
                        from_address = from_addr
                        to_address = to_addr
                    break

        # Convert lamports to SOL for native transfers
        if token_symbol == 'SOL':
            amount = amount / 1_000_000_000

        # Get fee
        fee_lamports = tx.get('fee', 0)
        fee_sol = fee_lamports / 1_000_000_000

        # Get status
        err = tx.get('transactionError')
        status = 'failed' if err else 'confirmed'

        return {
            'blockchain': 'solana',
            'tx_hash': tx.get('signature', ''),
            'tx_time': tx_time,
            'direction': direction,
            'amount': str(amount),
            'token_symbol': token_symbol,
            'token_name': token_name,
            'from_address': from_address,
            'to_address': to_address,
            'fee': str(fee_sol),
            'status': status,
            'metadata': json.dumps({
                'slot': tx.get('slot', 0),
                'type': tx.get('type', 'UNKNOWN'),
                'source': tx.get('source', 'HELIUS')
            })
        }

    async def save_transactions(
        self,
        user_id: int,
        wallet_id: int,
        transactions: List[dict]
    ):
        """
        Save transactions to database.

        Args:
            user_id: User ID
            wallet_id: Wallet ID
            transactions: List of normalized transactions
        """
        if not transactions:
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            for tx in transactions:
                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO transaction_history
                        (user_id, wallet_id, blockchain, tx_hash, tx_time, direction,
                         amount, token_symbol, token_name, from_address, to_address,
                         fee, status, metadata, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        wallet_id,
                        tx['blockchain'],
                        tx['tx_hash'],
                        tx['tx_time'],
                        tx['direction'],
                        tx['amount'],
                        tx['token_symbol'],
                        tx['token_name'],
                        tx['from_address'],
                        tx['to_address'],
                        tx['fee'],
                        tx['status'],
                        tx['metadata'],
                        datetime.utcnow()
                    ))
                except Exception as e:
                    logger.error(f"Error saving transaction {tx.get('tx_hash')}: {e}")
                    continue

            await db.commit()
            logger.info(f"Saved {len(transactions)} transactions to database")

    async def get_transactions(
        self,
        user_id: int,
        days: int = 7,
        blockchain: str = None,
        direction: str = None,
        search: str = None
    ) -> List[dict]:
        """
        Get transactions from database with filtering.

        Args:
            user_id: User ID
            days: Number of days to look back
            blockchain: Filter by blockchain
            direction: Filter by direction (sent/received)
            search: Text search in tx hash, addresses, token

        Returns:
            List of transactions
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        query = """
            SELECT
                th.*,
                w.address as wallet_address,
                w.label as wallet_name
            FROM transaction_history th
            LEFT JOIN wallets w ON th.wallet_id = w.id
            WHERE th.user_id = ? AND th.tx_time >= ?
        """
        params = [user_id, start_time]

        if blockchain:
            query += " AND th.blockchain = ?"
            params.append(blockchain)

        if direction:
            query += " AND th.direction = ?"
            params.append(direction)

        if search:
            query += """ AND (
                th.tx_hash LIKE ? OR
                th.from_address LIKE ? OR
                th.to_address LIKE ? OR
                th.token_symbol LIKE ? OR
                th.token_name LIKE ?
            )"""
            search_pattern = f"%{search}%"
            params.extend([search_pattern] * 5)

        query += " ORDER BY th.tx_time DESC LIMIT 10000"

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            v1_results = [dict(row) for row in rows]

        # Merge V2 engine events (deduplicated by tx_hash, V2 fills gaps)
        v2_results = await self._get_v2_events_as_transactions(user_id, days, blockchain)
        if not v2_results:
            return v1_results

        # Build set of V1 tx hashes for dedup
        v1_hashes = {tx.get('tx_hash') for tx in v1_results if tx.get('tx_hash')}

        # Add V2 events not already in V1, applying same filters
        for tx in v2_results:
            if tx['tx_hash'] in v1_hashes:
                continue
            if direction and tx.get('direction') != direction:
                continue
            if search:
                search_lower = search.lower()
                if not any(
                    search_lower in (tx.get(f) or '').lower()
                    for f in ('tx_hash', 'from_address', 'to_address', 'token_symbol', 'token_name')
                ):
                    continue
            v1_results.append(tx)

        # Re-sort merged results by tx_time descending
        v1_results.sort(key=lambda x: x.get('tx_time') or '', reverse=True)
        return v1_results[:10000]


    # ------------------------------------------------------------------
    # Exchange (CEX) transaction persistence
    # ------------------------------------------------------------------

    async def save_exchange_transactions(
        self,
        user_id: int,
        exchange: str,
        transactions: List[dict],
    ) -> int:
        """
        Persist exchange transactions to the exchange_transactions table.

        Uses INSERT OR IGNORE so duplicates (same user_id+exchange+tx_id) are skipped.

        Returns:
            Number of newly inserted rows
        """
        if not transactions:
            return 0

        inserted = 0
        async with aiosqlite.connect(DATABASE_PATH) as db:
            for tx in transactions:
                try:
                    cursor = await db.execute("""
                        INSERT OR IGNORE INTO exchange_transactions
                        (user_id, exchange, tx_id, tx_type, status, tx_time,
                         amount, token_symbol, native_amount, native_currency,
                         fee, fee_currency, from_address, to_address,
                         network_hash, metadata, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        exchange,
                        tx.get("tx_id", ""),
                        tx.get("tx_type", "unknown"),
                        tx.get("status", "completed"),
                        tx.get("tx_time", ""),
                        tx.get("amount", ""),
                        tx.get("token_symbol", ""),
                        tx.get("native_amount", ""),
                        tx.get("native_currency", "USD"),
                        tx.get("fee", ""),
                        tx.get("fee_currency", ""),
                        tx.get("from_address", ""),
                        tx.get("to_address", ""),
                        tx.get("network_hash", ""),
                        tx.get("metadata", ""),
                        datetime.utcnow().isoformat(),
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                except Exception as e:
                    logger.error(f"Error saving exchange tx {tx.get('tx_id')}: {e}")
                    continue

            await db.commit()

        logger.info(f"Saved {inserted} new exchange transactions ({exchange}) to database")
        return inserted

    async def get_exchange_transactions(
        self,
        user_id: int,
        days: int = 90,
        exchange: str = None,
        tx_type: str = None,
        search: str = None,
        limit: int = 2000,
    ) -> List[dict]:
        """
        Query stored exchange transactions with filtering.

        Args:
            user_id: User ID
            days: Number of days to look back (0 = all time)
            exchange: Filter by exchange name
            tx_type: Filter by transaction type (buy, sell, send, etc.)
            search: Text search in tx_id, token_symbol, addresses
            limit: Max results

        Returns:
            List of exchange transaction dicts
        """
        query = """
            SELECT * FROM exchange_transactions
            WHERE user_id = ?
        """
        params: list = [user_id]

        if days > 0:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            query += " AND tx_time >= ?"
            params.append(cutoff)

        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)

        if tx_type:
            query += " AND tx_type = ?"
            params.append(tx_type)

        if search:
            query += """ AND (
                tx_id LIKE ? OR
                token_symbol LIKE ? OR
                from_address LIKE ? OR
                to_address LIKE ? OR
                network_hash LIKE ?
            )"""
            pattern = f"%{search}%"
            params.extend([pattern] * 5)

        query += " ORDER BY tx_time DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_exchange_transaction_count(
        self,
        user_id: int,
        exchange: str = None,
    ) -> int:
        """Quick count of stored exchange transactions."""
        query = "SELECT COUNT(*) FROM exchange_transactions WHERE user_id = ?"
        params: list = [user_id]

        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            return row[0] if row else 0


# Singleton
transaction_history_service = TransactionHistoryService()
