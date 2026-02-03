"""
Transaction History Service - Fetch and normalize transactions from all blockchains
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

logger = logging.getLogger(__name__)


class TransactionHistoryService:
    """Fetch and normalize transactions from all blockchains."""

    def __init__(self):
        self.supported_blockchains = ['cardano', 'ethereum', 'bitcoin', 'solana', 'polygon', 'base']

    async def fetch_transactions(
        self,
        user_id: int,
        days: int = 7,
        blockchain: str = None
    ) -> Dict[str, int]:
        """
        Fetch transactions from all wallets for a user.

        Args:
            user_id: User ID to fetch transactions for
            days: Number of days of transaction history
            blockchain: Filter by specific blockchain (None for all)

        Returns:
            Dict with counts of transactions fetched per blockchain
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        # Get all wallets for user
        wallets = await get_all_wallets(user_id)

        if not wallets:
            logger.info(f"No wallets found for user {user_id}")
            return {}

        # Filter by blockchain if specified
        if blockchain:
            wallets = [w for w in wallets if w['blockchain'] == blockchain]

        counts = {}

        for wallet in wallets:
            wallet_id = wallet['id']
            chain = wallet['blockchain']
            address = wallet['address']

            logger.info(f"Fetching transactions for {chain} wallet {address[:12]}...")

            try:
                transactions = await self._fetch_blockchain_transactions(
                    chain, address, days
                )

                if transactions:
                    # Normalize and save
                    normalized = []
                    for tx in transactions:
                        normalized_tx = await self.normalize_transaction(
                            chain, tx, address
                        )
                        if normalized_tx:
                            normalized.append(normalized_tx)

                    await self.save_transactions(user_id, wallet_id, normalized)
                    counts[chain] = counts.get(chain, 0) + len(normalized)
                    logger.info(f"Saved {len(normalized)} transactions for {chain}")

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
        # Blockfrost doesn't have a direct transaction history endpoint
        # We'll need to use address/transactions endpoint
        # For now, return empty list - can be implemented when Blockfrost adds support
        logger.info("Cardano transaction history not yet implemented")
        return []

    async def _fetch_ethereum_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Ethereum transactions via Etherscan."""
        txs = await etherscan_service.get_transactions('ethereum', address, limit)
        token_txs = await etherscan_service.get_token_transfers('ethereum', address, limit)
        return txs + token_txs

    async def _fetch_bitcoin_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Bitcoin transactions from Blockstream API."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get transaction list
                response = await client.get(
                    f"{bitcoin_service.base_url}/address/{address}/txs"
                )

                if response.status_code != 200:
                    logger.error(f"Blockstream API error: {response.status_code}")
                    return []

                txs = response.json()[:limit]

                # Fetch full details for each transaction to get inputs/outputs
                detailed_txs = []
                for tx in txs:
                    tx_response = await client.get(
                        f"{bitcoin_service.base_url}/tx/{tx['txid']}"
                    )
                    if tx_response.status_code == 200:
                        detailed_txs.append(tx_response.json())

                return detailed_txs

        except Exception as e:
            logger.error(f"Error fetching Bitcoin transactions: {e}")
            return []

    async def _fetch_solana_transactions(self, address: str, limit: int) -> List[dict]:
        """Fetch Solana transactions."""
        # Solana service would need transaction history method
        logger.info("Solana transaction history not yet implemented")
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
        """Normalize Cardano transaction."""
        # Placeholder - implement when Cardano tx API is available
        return {
            'blockchain': 'cardano',
            'tx_hash': tx.get('hash', ''),
            'tx_time': datetime.utcnow(),
            'direction': 'received',
            'amount': '0',
            'token_symbol': 'ADA',
            'token_name': 'Cardano',
            'from_address': '',
            'to_address': wallet_address,
            'fee': '0',
            'status': 'confirmed',
            'metadata': '{}'
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
        """Normalize Solana transaction."""
        # Placeholder - implement when Solana tx API is available
        return {
            'blockchain': 'solana',
            'tx_hash': tx.get('signature', ''),
            'tx_time': datetime.utcnow(),
            'direction': 'received',
            'amount': '0',
            'token_symbol': 'SOL',
            'token_name': 'Solana',
            'from_address': '',
            'to_address': wallet_address,
            'fee': '0',
            'status': 'confirmed',
            'metadata': '{}'
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
                        INSERT OR REPLACE INTO transaction_history
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

            return [dict(row) for row in rows]


# Singleton
transaction_history_service = TransactionHistoryService()
