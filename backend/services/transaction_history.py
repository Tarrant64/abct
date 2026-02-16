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
from services.http_client import get_client

logger = logging.getLogger(__name__)


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
                user_id, chain=blockchain, min_time=min_time, limit=5000
            )
            if not events:
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

            logger.info(f"V2 engine: converted {len(transactions)} events to transaction format")
            return transactions
        except Exception as e:
            logger.debug(f"V2 engine events query failed: {e}")
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

    async def fetch_transactions(
        self,
        user_id: int,
        days: int = 7,
        blockchain: str = None,
        wallet_ids: List[int] = None
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

        Returns:
            Dict with counts of transactions fetched per blockchain
        """
        # Try V2 engine indexing to populate engine_events
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

            chains = set()
            for w in selected:
                c = w.get('blockchain', '').lower()
                try:
                    chains.add(ChainId(c))
                except ValueError:
                    pass

            if chains:
                request = BackfillRequest(
                    chains=list(chains),
                    wallet_ids=wallet_ids,
                    domains=[WorkDomain.INDEX, WorkDomain.HYDRATE, WorkDomain.NORMALIZE],
                )
                backfill_id = await backfill_orchestrator.plan_backfill(user_id, request)
                await backfill_orchestrator.run_backfill(backfill_id)
                logger.info(f"V2 engine indexing triggered for transaction fetch: backfill={backfill_id}")
        except Exception as e:
            logger.debug(f"V2 engine indexing for transactions skipped: {e}")

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
                # Check existing transaction bounds for smart fetching
                bounds = await self.get_transaction_bounds(user_id, wallet_id, chain)
                if bounds:
                    newest = bounds['newest']
                    oldest = bounds['oldest']
                    logger.info(f"Existing transactions: newest={newest}, oldest={oldest}")
                    logger.info("Fetching only new transactions since last fetch")

                transactions = await self._fetch_blockchain_transactions(
                    chain, address, days
                )

                if transactions:
                    # Filter out transactions we already have (if bounds exist)
                    if bounds:
                        # Convert newest to comparable format
                        newest_dt = datetime.fromisoformat(bounds['newest']) if isinstance(bounds['newest'], str) else bounds['newest']

                        original_count = len(transactions)
                        # Keep only transactions newer than what we have
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
                logger.error(f"Error fetching {chain} transactions: {e}")
                continue

        return counts

    async def _fetch_blockchain_transactions(
        self,
        blockchain: str,
        address: str,
        days: int
    ) -> List[dict]:
        """
        Fetch transactions from blockchain-specific service.

        Args:
            blockchain: Blockchain name
            address: Wallet address
            days: Number of days of history

        Returns:
            List of raw transactions from blockchain API
        """
        limit = min(100, days * 20)  # Estimate ~20 txs per day max

        try:
            if blockchain == 'cardano':
                return await self._fetch_cardano_transactions(address, limit)
            elif blockchain == 'ethereum':
                return await self._fetch_ethereum_transactions(address, limit)
            elif blockchain == 'bitcoin':
                return await self._fetch_bitcoin_transactions(address, limit)
            elif blockchain == 'solana':
                return await self._fetch_solana_transactions(address, limit)
            elif blockchain == 'polygon':
                return await self._fetch_polygon_transactions(address, limit)
            elif blockchain == 'base':
                return await self._fetch_base_transactions(address, limit)
            else:
                logger.warning(f"Unsupported blockchain: {blockchain}")
                return []
        except Exception as e:
            logger.error(f"Error fetching {blockchain} transactions: {e}")
            return []

    async def _fetch_cardano_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Cardano transactions via Blockfrost."""
        import httpx
        from config import BLOCKFROST_BASE_URL

        try:
            # Get Blockfrost API key
            blockfrost_key = await cardano_service._get_blockfrost_key()
            if not blockfrost_key:
                logger.warning("Blockfrost API key not configured")
                return []

            headers = {"project_id": blockfrost_key}

            client = get_client("blockfrost", timeout=30.0)

            # Get address transactions
            response = await client.get(
                f"{BLOCKFROST_BASE_URL}/addresses/{address}/transactions",
                headers=headers,
                params={"count": limit, "order": "desc"}
            )

            if response.status_code == 404:
                # Address has no transactions
                return []

            if response.status_code != 200:
                logger.error(f"Blockfrost transactions error: {response.status_code}")
                return []

            tx_hashes = response.json()

            # Fetch details for each transaction
            detailed_txs = []
            for tx_info in tx_hashes[:limit]:
                tx_hash = tx_info.get('tx_hash')
                if not tx_hash:
                    continue

                # Get transaction details
                tx_response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/txs/{tx_hash}",
                    headers=headers
                )

                if tx_response.status_code == 200:
                    tx_detail = tx_response.json()

                    # Get UTXOs for the transaction
                    utxo_response = await client.get(
                        f"{BLOCKFROST_BASE_URL}/txs/{tx_hash}/utxos",
                        headers=headers
                    )

                    if utxo_response.status_code == 200:
                        utxos = utxo_response.json()
                        tx_detail['utxos'] = utxos

                    detailed_txs.append(tx_detail)

            logger.info(f"Fetched {len(detailed_txs)} Cardano transactions")
            return detailed_txs

        except Exception as e:
            logger.error(f"Error fetching Cardano transactions: {e}")
            return []

    async def _fetch_ethereum_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Ethereum transactions via Etherscan."""
        txs = await etherscan_service.get_transactions('ethereum', address, limit)
        token_txs = await etherscan_service.get_token_transfers('ethereum', address, limit)
        return txs + token_txs

    async def _fetch_bitcoin_transactions(self, address: str, limit: int) -> List[dict]:
        """
        Fetch Bitcoin transactions from Blockstream API with Mempool.space fallback.

        Uses smart fetching to avoid re-fetching existing transactions.
        """
        import httpx
        from config import MEMPOOL_BASE_URL

        # Try Blockstream first
        try:
            client = get_client("blockfrost", timeout=30.0)
            # Get transaction list
            response = await client.get(
                f"{bitcoin_service.base_url}/address/{address}/txs"
            )

            if response.status_code != 200:
                logger.warning(f"Blockstream API error: {response.status_code}, trying Mempool.space fallback")
                # Try Mempool.space fallback
                return await self._fetch_bitcoin_transactions_mempool(address, limit)

            txs = response.json()[:limit]

            # Fetch full details for each transaction to get inputs/outputs
            detailed_txs = []
            for tx in txs:
                tx_response = await client.get(
                    f"{bitcoin_service.base_url}/tx/{tx['txid']}"
                )
                if tx_response.status_code == 200:
                    detailed_txs.append(tx_response.json())

            logger.info(f"Fetched {len(detailed_txs)} Bitcoin transactions from Blockstream")
            return detailed_txs

        except Exception as e:
            logger.error(f"Blockstream error: {e}, trying Mempool.space fallback")
            return await self._fetch_bitcoin_transactions_mempool(address, limit)

    async def _fetch_bitcoin_transactions_mempool(self, address: str, limit: int) -> List[dict]:
        """Fetch Bitcoin transactions from Mempool.space API (fallback)."""
        import httpx
        from config import MEMPOOL_BASE_URL

        try:
            client = get_client("blockfrost", timeout=30.0)
            # Mempool.space has the same API format as Blockstream
            response = await client.get(
                f"{MEMPOOL_BASE_URL}/address/{address}/txs"
            )

            if response.status_code != 200:
                logger.error(f"Mempool.space API error: {response.status_code}")
                return []

            txs = response.json()[:limit]

            # Fetch full details
            detailed_txs = []
            for tx in txs:
                tx_response = await client.get(
                    f"{MEMPOOL_BASE_URL}/tx/{tx['txid']}"
                )
                if tx_response.status_code == 200:
                    detailed_txs.append(tx_response.json())

            logger.info(f"Fetched {len(detailed_txs)} Bitcoin transactions from Mempool.space (fallback)")
            return detailed_txs

        except Exception as e:
            logger.error(f"Mempool.space error: {e}")
            return []

    async def _fetch_solana_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Solana transactions using Helius API."""
        import httpx
        from config import HELIUS_BASE_URL

        try:
            # Get Helius API key
            helius_key = await solana_service.get_api_key()
            if not helius_key:
                logger.warning("Helius API key not configured")
                return []

            client = get_client("blockfrost", timeout=30.0)

            # Get transaction signatures for the address
            # Using Helius enhanced transactions endpoint
            response = await client.get(
                f"{HELIUS_BASE_URL}/addresses/{address}/transactions",
                params={
                    "api-key": helius_key,
                    "limit": limit
                }
            )

            if response.status_code != 200:
                logger.error(f"Helius transactions error: {response.status_code}")
                return []

            transactions = response.json()
            logger.info(f"Fetched {len(transactions)} Solana transactions")
            return transactions

        except Exception as e:
            logger.error(f"Error fetching Solana transactions: {e}")
            return []

    async def _fetch_polygon_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Polygon transactions via Polygonscan."""
        txs = await etherscan_service.get_transactions('polygon', address, limit)
        token_txs = await etherscan_service.get_token_transfers('polygon', address, limit)
        return txs + token_txs

    async def _fetch_base_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Base transactions via Basescan."""
        txs = await etherscan_service.get_transactions('base', address, limit)
        token_txs = await etherscan_service.get_token_transfers('base', address, limit)
        return txs + token_txs

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
            if blockchain in ['ethereum', 'polygon', 'base']:
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
        if not token_symbol:
            if blockchain == 'ethereum':
                token_symbol = 'ETH'
                token_name = 'Ethereum'
            elif blockchain == 'polygon':
                token_symbol = 'MATIC'
                token_name = 'Polygon'
            elif blockchain == 'base':
                token_symbol = 'ETH'
                token_name = 'Base ETH'

        # Extract amount
        amount = tx.get('value', 0)
        if isinstance(amount, str):
            try:
                amount = float(amount)
            except:
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
                                except:
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

        query += " ORDER BY th.tx_time DESC LIMIT 1000"

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
        return v1_results[:1000]


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
