"""
Demo Transaction Service - Returns fake transaction history

Provides mock transaction data for demo accounts:
- 1 year (365 days) of fake transactions across all chains
- Mix of sent and received transactions
- Realistic amounts and timestamps
- All transaction types (native, token, contract, NFT)
- No real blockchain API calls

Total Transactions: ~1500 across all chains
- Cardano: ~500 transactions
- Ethereum: ~200 transactions
- Bitcoin: ~100 transactions
- Solana: ~300 transactions
- Polygon: ~150 transactions
- Base: ~100 transactions
- Algorand: ~150 transactions
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import random
import json


class DemoTransactionService:
    """Service for returning fake transaction history in demo mode."""

    def __init__(self):
        """Initialize demo transaction service with fake transaction history."""
        self.transactions = []
        self._generate_transaction_history()

    def _generate_transaction_history(self):
        """Generate 1 year of realistic transaction history."""
        now = datetime.utcnow()

        # Cardano transactions (~500 over 365 days)
        self._generate_cardano_transactions(now, 500)

        # Ethereum transactions (~200)
        self._generate_ethereum_transactions(now, 200)

        # Bitcoin transactions (~100)
        self._generate_bitcoin_transactions(now, 100)

        # Solana transactions (~300)
        self._generate_solana_transactions(now, 300)

        # Polygon transactions (~150)
        self._generate_polygon_transactions(now, 150)

        # Base transactions (~100)
        self._generate_base_transactions(now, 100)

        # Algorand transactions (~150)
        self._generate_algorand_transactions(now, 150)

        # Sort all transactions by timestamp (most recent first)
        self.transactions.sort(key=lambda x: x['tx_time'], reverse=True)

    def _random_timestamp(self, base_time: datetime, max_days_ago: int) -> datetime:
        """Generate random timestamp within the last N days."""
        days_ago = random.randint(0, max_days_ago)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)

        return base_time - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

    def _generate_cardano_transactions(self, now: datetime, count: int):
        """Generate Cardano transaction history."""
        cardano_tokens = [
            ('ADA', 'Cardano', 1.0),
            ('MIN', 'Minswap', 0.045),
            ('SNEK', 'Snek', 0.0012),
            ('WMT', 'World Mobile Token', 0.15),
            ('HOSKY', 'Hosky Token', 0.00001),
            ('INDY', 'Indigo', 0.85),
            ('SUNDAE', 'SundaeSwap', 0.025),
            ('COPI', 'Cornucopias', 0.12),
            ('AGIX', 'SingularityNET', 0.45),
            ('NMKR', 'NMKR', 0.32)
        ]

        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])  # More receives
            token = random.choice(cardano_tokens)

            if token[0] == 'ADA':
                amount = random.uniform(10, 5000)
            else:
                amount = random.uniform(100, 50000)

            tx_hash = f"cardano_tx_{i:06d}{'a' * 58}"

            self.transactions.append({
                'blockchain': 'cardano',
                'tx_hash': tx_hash[:64],
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 6)),
                'token_symbol': token[0],
                'token_name': token[1],
                'from_address': 'addr1qx2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9wejf9wejf9we' if direction == 'sent' else f'addr1qx{random.randint(1000000, 9999999)}',
                'to_address': f'addr1qy{random.randint(1000000, 9999999)}' if direction == 'sent' else 'addr1qx2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9wejf9wejf9we',
                'fee': str(round(random.uniform(0.15, 0.25), 6)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'block_height': random.randint(8000000, 9000000),
                    'slot': random.randint(80000000, 90000000),
                    'size': random.randint(300, 800)
                })
            })

    def _generate_ethereum_transactions(self, now: datetime, count: int):
        """Generate Ethereum transaction history."""
        ethereum_tokens = [
            ('ETH', 'Ethereum', 3500),
            ('USDT', 'Tether USD', 1.0),
            ('USDC', 'USD Coin', 1.0),
            ('DAI', 'Dai Stablecoin', 1.0),
            ('LINK', 'Chainlink', 18),
            ('UNI', 'Uniswap', 8),
            ('AAVE', 'Aave', 120),
            ('MKR', 'Maker', 2000),
            ('COMP', 'Compound', 85),
            ('CRV', 'Curve DAO Token', 0.8),
            ('SUSHI', 'SushiSwap', 1.2)
        ]

        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])
            token = random.choice(ethereum_tokens)

            if token[0] == 'ETH':
                amount = random.uniform(0.01, 2.5)
            elif token[0] in ['USDT', 'USDC', 'DAI']:
                amount = random.uniform(50, 10000)
            else:
                amount = random.uniform(1, 500)

            tx_hash = f"0x{''.join(random.choices('0123456789abcdef', k=64))}"

            self.transactions.append({
                'blockchain': 'ethereum',
                'tx_hash': tx_hash,
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 6)),
                'token_symbol': token[0],
                'token_name': token[1],
                'from_address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb8' if direction == 'sent' else f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                'to_address': f"0x{''.join(random.choices('0123456789abcdef', k=40))}" if direction == 'sent' else '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb8',
                'fee': str(round(random.uniform(0.001, 0.05), 6)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'block_number': random.randint(18000000, 19000000),
                    'gas_used': random.randint(21000, 150000),
                    'gas_price': random.randint(20000000000, 100000000000)
                })
            })

    def _generate_bitcoin_transactions(self, now: datetime, count: int):
        """Generate Bitcoin transaction history."""
        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])
            amount = random.uniform(0.0001, 0.05)

            tx_hash = ''.join(random.choices('0123456789abcdef', k=64))

            self.transactions.append({
                'blockchain': 'bitcoin',
                'tx_hash': tx_hash,
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 8)),
                'token_symbol': 'BTC',
                'token_name': 'Bitcoin',
                'from_address': 'bc1qxy2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9we' if direction == 'sent' else f"bc1q{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=30))}",
                'to_address': f"bc1q{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=30))}" if direction == 'sent' else 'bc1qxy2kd3efdwy98fwejfkw9fj2kjdl3kjf9wejf9we',
                'fee': str(round(random.uniform(0.00001, 0.0001), 8)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'block_height': random.randint(800000, 850000),
                    'confirmations': random.randint(6, 1000),
                    'size': random.randint(200, 500),
                    'weight': random.randint(800, 2000)
                })
            })

    def _generate_solana_transactions(self, now: datetime, count: int):
        """Generate Solana transaction history."""
        solana_tokens = [
            ('SOL', 'Solana', 180),
            ('BONK', 'Bonk', 0.00001),
            ('WIF', 'dogwifhat', 2.5),
            ('PYTH', 'Pyth Network', 0.45),
            ('JUP', 'Jupiter', 1.2),
            ('RAY', 'Raydium', 3.5),
            ('ORCA', 'Orca', 4.2),
            ('SRM', 'Serum', 0.8),
            ('FIDA', 'Bonfida', 0.35),
            ('MNGO', 'Mango Markets', 0.05)
        ]

        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])
            token = random.choice(solana_tokens)

            if token[0] == 'SOL':
                amount = random.uniform(0.1, 50)
            elif token[0] == 'BONK':
                amount = random.uniform(1000000, 100000000)
            else:
                amount = random.uniform(10, 5000)

            tx_hash = ''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=88))

            self.transactions.append({
                'blockchain': 'solana',
                'tx_hash': tx_hash,
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 6)),
                'token_symbol': token[0],
                'token_name': token[1],
                'from_address': 'DemoSo1anaWa11etAddress123456789ABC' if direction == 'sent' else f"{''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=44))}",
                'to_address': f"{''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=44))}" if direction == 'sent' else 'DemoSo1anaWa11etAddress123456789ABC',
                'fee': str(round(random.uniform(0.000001, 0.00001), 6)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'slot': random.randint(200000000, 250000000),
                    'type': random.choice(['TRANSFER', 'TOKEN_TRANSFER', 'SWAP']),
                    'source': 'HELIUS'
                })
            })

    def _generate_polygon_transactions(self, now: datetime, count: int):
        """Generate Polygon transaction history."""
        polygon_tokens = [
            ('MATIC', 'Polygon', 0.90),
            ('USDC', 'USD Coin', 1.0),
            ('USDT', 'Tether USD', 1.0),
            ('QUICK', 'QuickSwap', 0.08),
            ('GHST', 'Aavegotchi', 1.5),
            ('MATICX', 'Stader MaticX', 1.1),
            ('DQUICK', 'Dragon Quick', 0.15)
        ]

        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])
            token = random.choice(polygon_tokens)

            if token[0] == 'MATIC':
                amount = random.uniform(1, 500)
            elif token[0] in ['USDC', 'USDT']:
                amount = random.uniform(10, 5000)
            else:
                amount = random.uniform(1, 1000)

            tx_hash = f"0x{''.join(random.choices('0123456789abcdef', k=64))}"

            self.transactions.append({
                'blockchain': 'polygon',
                'tx_hash': tx_hash,
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 6)),
                'token_symbol': token[0],
                'token_name': token[1],
                'from_address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb9' if direction == 'sent' else f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                'to_address': f"0x{''.join(random.choices('0123456789abcdef', k=40))}" if direction == 'sent' else '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb9',
                'fee': str(round(random.uniform(0.001, 0.01), 6)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'block_number': random.randint(50000000, 55000000),
                    'gas_used': random.randint(21000, 100000),
                    'gas_price': random.randint(30000000000, 100000000000)
                })
            })

    def _generate_base_transactions(self, now: datetime, count: int):
        """Generate Base transaction history."""
        base_tokens = [
            ('ETH', 'Ethereum on Base', 3500),
            ('USDC', 'USD Coin', 1.0),
            ('DAI', 'Dai Stablecoin', 1.0),
            ('cbETH', 'Coinbase Wrapped Staked ETH', 3800)
        ]

        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])
            token = random.choice(base_tokens)

            if token[0] in ['ETH', 'cbETH']:
                amount = random.uniform(0.01, 1.5)
            else:
                amount = random.uniform(10, 3000)

            tx_hash = f"0x{''.join(random.choices('0123456789abcdef', k=64))}"

            self.transactions.append({
                'blockchain': 'base',
                'tx_hash': tx_hash,
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 6)),
                'token_symbol': token[0],
                'token_name': token[1],
                'from_address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEc0' if direction == 'sent' else f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                'to_address': f"0x{''.join(random.choices('0123456789abcdef', k=40))}" if direction == 'sent' else '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEc0',
                'fee': str(round(random.uniform(0.0001, 0.001), 6)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'block_number': random.randint(8000000, 9000000),
                    'gas_used': random.randint(21000, 80000),
                    'gas_price': random.randint(1000000, 5000000000)
                })
            })

    def _generate_algorand_transactions(self, now: datetime, count: int):
        """Generate Algorand transaction history."""
        algorand_assets = [
            ('ALGO', 'Algorand', 1.0),
            ('USDC', 'USD Coin (Algorand)', 1.0),
            ('PLANETS', 'Planets', 0.005),
            ('OPUL', 'Opulous', 0.08),
            ('GOBTC', 'AlgoFi Wrapped BTC', 98000),
            ('GOETH', 'AlgoFi Wrapped ETH', 3500)
        ]

        for i in range(count):
            direction = random.choice(['sent', 'received', 'received'])
            asset = random.choice(algorand_assets)

            if asset[0] == 'ALGO':
                amount = random.uniform(1, 1000)
            elif asset[0] == 'USDC':
                amount = random.uniform(10, 5000)
            elif asset[0] in ['GOBTC', 'GOETH']:
                amount = random.uniform(0.001, 0.1)
            else:
                amount = random.uniform(100, 50000)

            tx_hash = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', k=52))

            self.transactions.append({
                'blockchain': 'algorand',
                'tx_hash': tx_hash,
                'tx_time': self._random_timestamp(now, 365),
                'direction': direction,
                'amount': str(round(amount, 6)),
                'token_symbol': asset[0],
                'token_name': asset[1],
                'from_address': 'SWOUICD7LO3MWVKLHFKADCXLF5HZPUQQFW5OIJAFZJBG4HDQH53RTTJPFE' if direction == 'sent' else ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', k=58)),
                'to_address': ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', k=58)) if direction == 'sent' else 'SWOUICD7LO3MWVKLHFKADCXLF5HZPUQQFW5OIJAFZJBG4HDQH53RTTJPFE',
                'fee': str(round(random.uniform(0.001, 0.002), 6)),
                'status': 'confirmed',
                'metadata': json.dumps({
                    'round': random.randint(30000000, 35000000),
                    'asset_id': random.randint(10000, 999999) if asset[0] != 'ALGO' else 0
                })
            })

    async def get_transactions(
        self,
        user_id: int,
        days: int = 7,
        blockchain: str = None,
        direction: str = None,
        search: str = None
    ) -> List[Dict]:
        """
        Get demo transactions with filtering.

        Args:
            user_id: User ID (ignored in demo mode)
            days: Number of days to look back
            blockchain: Filter by blockchain
            direction: Filter by direction (sent/received)
            search: Text search in tx hash, addresses, token

        Returns:
            List of filtered demo transactions
        """
        # Filter by time
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        filtered = [tx for tx in self.transactions if tx['tx_time'] >= cutoff_time]

        # Filter by blockchain
        if blockchain:
            filtered = [tx for tx in filtered if tx['blockchain'] == blockchain]

        # Filter by direction
        if direction:
            filtered = [tx for tx in filtered if tx['direction'] == direction]

        # Search filter
        if search:
            search_lower = search.lower()
            filtered = [
                tx for tx in filtered
                if (
                    search_lower in tx['tx_hash'].lower() or
                    search_lower in tx['from_address'].lower() or
                    search_lower in tx['to_address'].lower() or
                    search_lower in tx['token_symbol'].lower() or
                    search_lower in tx['token_name'].lower()
                )
            ]

        # Convert datetime to ISO string for JSON serialization
        result = []
        for tx in filtered:
            tx_copy = tx.copy()
            tx_copy['tx_time'] = tx['tx_time'].isoformat()
            result.append(tx_copy)

        return result

    async def get_transaction_stats(self, user_id: int, days: int = 30) -> Dict:
        """
        Get transaction statistics for demo account.

        Args:
            user_id: User ID (ignored in demo mode)
            days: Number of days to analyze

        Returns:
            Transaction statistics
        """
        transactions = await self.get_transactions(user_id, days)

        total = len(transactions)
        by_blockchain = {}
        by_direction = {'sent': 0, 'received': 0}

        for tx in transactions:
            chain = tx.get('blockchain', 'unknown')
            by_blockchain[chain] = by_blockchain.get(chain, 0) + 1

            direction = tx.get('direction', 'unknown')
            if direction in by_direction:
                by_direction[direction] += 1

        return {
            'total_transactions': total,
            'by_blockchain': by_blockchain,
            'by_direction': by_direction,
            'days': days
        }

    async def get_transaction_analytics(self, user_id: int, days: int = 30) -> Dict:
        """
        Get transaction analytics grouped by blockchain and time buckets.

        Args:
            user_id: User ID (ignored in demo mode)
            days: Time period in days

        Returns:
            Transaction counts by blockchain over time buckets
        """
        transactions = await self.get_transactions(user_id, days)

        if not transactions:
            return {
                'period': f"{days} days" if days < 99999 else "all time",
                'buckets': [],
                'chains': {}
            }

        # Determine bucket size based on time period
        if days <= 30:
            bucket_format = '%Y-%m-%d'  # Daily buckets
            bucket_label = 'day'
        elif days <= 365:
            bucket_format = '%Y-W%U'  # Weekly buckets
            bucket_label = 'week'
        else:
            bucket_format = '%Y-%m'  # Monthly buckets
            bucket_label = 'month'

        # Group transactions by blockchain and time bucket
        from collections import defaultdict
        chain_buckets = defaultdict(lambda: defaultdict(int))
        all_buckets = set()

        for tx in transactions:
            chain = tx.get('blockchain', 'unknown')
            tx_time_str = tx.get('tx_time')

            if not tx_time_str:
                continue

            # Parse timestamp
            tx_dt = datetime.fromisoformat(tx_time_str.replace('Z', '+00:00'))

            # Create bucket key
            bucket_key = tx_dt.strftime(bucket_format)
            all_buckets.add(bucket_key)
            chain_buckets[chain][bucket_key] += 1

        # Sort buckets chronologically
        sorted_buckets = sorted(list(all_buckets))

        # Build response with aligned data for each chain
        chains_data = {}
        for chain in chain_buckets.keys():
            chain_counts = []
            for bucket in sorted_buckets:
                chain_counts.append(chain_buckets[chain].get(bucket, 0))
            chains_data[chain] = chain_counts

        # Format bucket labels for display
        display_buckets = []
        for bucket in sorted_buckets:
            if bucket_label == 'day':
                display_buckets.append(bucket)
            elif bucket_label == 'week':
                # Convert week format to readable
                year, week = bucket.split('-W')
                display_buckets.append(f"{year}-W{week}")
            else:
                # Month format
                display_buckets.append(bucket)

        return {
            'period': f"{days} days" if days < 99999 else "all time",
            'bucket_type': bucket_label,
            'buckets': display_buckets,
            'chains': chains_data
        }


# Global instance
demo_transaction_service = DemoTransactionService()
