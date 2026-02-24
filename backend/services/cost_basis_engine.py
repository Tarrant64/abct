"""
Cost Basis Engine - FIFO/LIFO/Average cost basis tracking and P&L computation.

Ingests exchange transactions and wallet balance history to build cost basis lots.
Computes unrealized and realized P&L per asset and portfolio-wide.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# Transaction types that create new lots (acquisitions)
ACQUISITION_TYPES = {'buy', 'receive', 'deposit', 'staking_reward', 'interest', 'airdrop', 'fork'}
# Transaction types that dispose of lots
DISPOSAL_TYPES = {'sell', 'send', 'withdrawal'}


class CostBasisEngine:
    """P&L analytics engine with FIFO/LIFO/Average cost basis methods."""

    async def ingest_exchange_transactions(self, user_id: int, exchange: str = None) -> dict:
        """Import transactions from exchange_transactions table into cost_basis_lots.

        For buy/deposit/receive: creates new lot with cost = native_amount / quantity
        For sell/withdrawal/send: calls dispose_lots() to match against existing lots

        Args:
            user_id: User ID
            exchange: Optional filter by exchange name

        Returns:
            dict with counts: {lots_created, disposals_processed, errors}
        """
        lots_created = 0
        disposals_processed = 0
        errors = 0

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # Get already-processed tx_ids to avoid duplicates
            cursor = await db.execute(
                "SELECT tx_id FROM cost_basis_lots WHERE user_id = ? AND tx_id IS NOT NULL",
                (user_id,)
            )
            processed_tx_ids = {row[0] for row in await cursor.fetchall()}

            # Also check realized_gains for disposal tx references in metadata
            # (disposals don't have tx_id in cost_basis_lots, tracked via lot_id)

            # Fetch exchange transactions ordered by time
            query = """
                SELECT id, exchange, tx_id, tx_type, tx_time, amount, token_symbol,
                       native_amount, native_currency, fee, fee_currency
                FROM exchange_transactions
                WHERE user_id = ? AND status = 'completed'
            """
            params: list = [user_id]
            if exchange:
                query += " AND exchange = ?"
                params.append(exchange)
            query += " ORDER BY tx_time ASC"

            cursor = await db.execute(query, params)
            transactions = await cursor.fetchall()

        # Process each transaction outside the main connection
        for tx in transactions:
            tx_id = tx['tx_id']
            tx_type = (tx['tx_type'] or '').lower()
            token_symbol = tx['token_symbol']

            if not token_symbol:
                continue

            try:
                amount = float(tx['amount'] or 0)
                native_amount = float(tx['native_amount'] or 0)
            except (ValueError, TypeError):
                errors += 1
                continue

            if amount <= 0:
                continue

            token_symbol = token_symbol.upper()

            if tx_type in ACQUISITION_TYPES:
                # Skip if already processed
                if tx_id in processed_tx_ids:
                    continue

                cost_per_unit = native_amount / amount if amount > 0 else 0
                acquisition_type = tx_type
                source = tx['exchange'] or 'unknown'

                try:
                    await self._insert_lot(
                        user_id, token_symbol, amount, cost_per_unit,
                        tx['tx_time'], acquisition_type, source, tx_id
                    )
                    lots_created += 1
                    processed_tx_ids.add(tx_id)
                except Exception as e:
                    logger.warning(f"Failed to create lot for tx {tx_id}: {e}")
                    errors += 1

            elif tx_type in DISPOSAL_TYPES:
                # Check if this disposal was already processed by looking for
                # realized_gains entries with matching parameters
                already_disposed = await self._is_disposal_processed(
                    user_id, token_symbol, tx['tx_time'], amount
                )
                if already_disposed:
                    continue

                proceeds = native_amount if native_amount > 0 else 0

                try:
                    result = await self.dispose_lots(
                        user_id, token_symbol, amount, proceeds,
                        method="fifo", disposal_type=tx_type,
                        disposal_date=tx['tx_time']
                    )
                    disposals_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to dispose lots for tx {tx_id}: {e}")
                    errors += 1

        return {
            "lots_created": lots_created,
            "disposals_processed": disposals_processed,
            "errors": errors,
            "total_transactions": len(transactions) if 'transactions' in dir() else 0
        }

    async def ingest_wallet_transactions(self, user_id: int, blockchain: str = None) -> dict:
        """Import on-chain wallet transactions into cost_basis_lots.

        Reads from transaction_history table, enriches with historical prices
        via price_enricher, then creates lots (received) or disposals (sent).

        Args:
            user_id: User ID
            blockchain: Optional filter by blockchain name

        Returns:
            dict with counts: {lots_created, disposals_processed, skipped_no_price, errors, total_transactions}
        """
        from engine.enrichment.price_enricher import price_enricher

        lots_created = 0
        disposals_processed = 0
        skipped_no_price = 0
        errors = 0

        # Blockchain -> native symbol mapping
        chain_symbol_map = {
            'cardano': 'ADA', 'bitcoin': 'BTC', 'ethereum': 'ETH',
            'solana': 'SOL', 'polygon': 'MATIC', 'base': 'ETH',
            'algorand': 'ALGO',
        }

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # Get already-processed tx_ids to avoid duplicates
            cursor = await db.execute(
                "SELECT tx_id FROM cost_basis_lots WHERE user_id = ? AND tx_id IS NOT NULL",
                (user_id,)
            )
            processed_tx_ids = {row[0] for row in await cursor.fetchall()}

            # Fetch wallet transactions
            query = """
                SELECT id, wallet_id, blockchain, tx_hash, tx_time, direction,
                       amount, token_symbol, fee, status
                FROM transaction_history
                WHERE user_id = ? AND status = 'confirmed'
                  AND direction IN ('sent', 'received')
                  AND amount IS NOT NULL AND token_symbol IS NOT NULL
            """
            params: list = [user_id]
            if blockchain:
                query += " AND blockchain = ?"
                params.append(blockchain)
            query += " ORDER BY tx_time ASC"

            cursor = await db.execute(query, params)
            transactions = await cursor.fetchall()

        if not transactions:
            return {
                "lots_created": 0, "disposals_processed": 0,
                "skipped_no_price": 0, "errors": 0, "total_transactions": 0
            }

        # Batch price enrichment: collect all unique (symbol, date) pairs
        symbol_dates: Dict[str, set] = {}
        for tx in transactions:
            tx_hash = tx['tx_hash']
            direction = tx['direction']

            # Skip already-processed acquisitions
            if direction == 'received' and tx_hash in processed_tx_ids:
                continue
            # Skip already-processed disposals
            if direction == 'sent':
                try:
                    amt = float(tx['amount'])
                except (ValueError, TypeError):
                    continue
                already = await self._is_disposal_processed(
                    user_id, tx['token_symbol'].upper(), tx['tx_time'], amt
                )
                if already:
                    continue

            symbol = tx['token_symbol'].upper()
            chain = tx['blockchain']

            # Map to native symbol if the token_symbol matches the chain native
            native = chain_symbol_map.get(chain)
            if native and symbol == native:
                lookup_symbol = native
            else:
                lookup_symbol = symbol

            tx_date = str(tx['tx_time'] or '')[:10]
            if not tx_date or len(tx_date) < 10:
                continue

            symbol_dates.setdefault(lookup_symbol, set()).add(tx_date)

        # Fetch prices in batches
        native_symbols = set(chain_symbol_map.values())
        price_cache: Dict[str, Dict[str, float]] = {}

        for symbol, dates in symbol_dates.items():
            date_list = sorted(dates)
            if symbol in native_symbols:
                prices = await price_enricher.fetch_historical_prices_batch(symbol, date_list)
            else:
                # Non-native token: per-date fetch via DefiLlama
                prices = {}
                for date in date_list:
                    # Try using the symbol as a coingecko lookup
                    price = await price_enricher.fetch_historical_price(symbol, "ethereum", date)
                    if price:
                        prices[date] = price
            price_cache[symbol] = prices

        logger.info(f"Wallet tx price enrichment: {sum(len(v) for v in price_cache.values())} prices for {len(price_cache)} symbols")

        # Process each transaction
        for tx in transactions:
            tx_hash = tx['tx_hash']
            direction = tx['direction']
            chain = tx['blockchain']
            raw_symbol = tx['token_symbol'].upper()

            native = chain_symbol_map.get(chain)
            lookup_symbol = native if (native and raw_symbol == native) else raw_symbol

            try:
                amount = float(tx['amount'] or 0)
            except (ValueError, TypeError):
                errors += 1
                continue

            if amount <= 0:
                continue

            tx_date = str(tx['tx_time'] or '')[:10]
            if not tx_date or len(tx_date) < 10:
                errors += 1
                continue

            price = price_cache.get(lookup_symbol, {}).get(tx_date)
            if not price:
                skipped_no_price += 1
                continue

            if direction == 'received':
                if tx_hash in processed_tx_ids:
                    continue

                cost_per_unit = price
                try:
                    await self._insert_lot(
                        user_id, raw_symbol, amount, cost_per_unit,
                        tx['tx_time'], 'receive', chain, tx_hash
                    )
                    lots_created += 1
                    processed_tx_ids.add(tx_hash)
                except Exception as e:
                    logger.warning(f"Failed to create wallet lot for tx {tx_hash}: {e}")
                    errors += 1

            elif direction == 'sent':
                already_disposed = await self._is_disposal_processed(
                    user_id, raw_symbol, tx['tx_time'], amount
                )
                if already_disposed:
                    continue

                proceeds = amount * price
                try:
                    await self.dispose_lots(
                        user_id, raw_symbol, amount, proceeds,
                        method="fifo", disposal_type='send',
                        disposal_date=tx['tx_time']
                    )
                    disposals_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to dispose wallet lots for tx {tx_hash}: {e}")
                    errors += 1

        return {
            "lots_created": lots_created,
            "disposals_processed": disposals_processed,
            "skipped_no_price": skipped_no_price,
            "errors": errors,
            "total_transactions": len(transactions)
        }

    async def _insert_lot(
        self, user_id: int, token_symbol: str, quantity: float,
        cost_per_unit: float, acquisition_date: str,
        acquisition_type: str = "buy", source: str = "exchange",
        tx_id: str = None
    ) -> int:
        """Insert a new cost basis lot. Returns lot ID."""
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            cursor = await db.execute(
                """INSERT INTO cost_basis_lots
                   (user_id, token_symbol, acquisition_date, acquisition_type,
                    acquisition_source, quantity, cost_per_unit_usd,
                    remaining_quantity, tx_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, token_symbol, acquisition_date, acquisition_type,
                 source, quantity, cost_per_unit, quantity, tx_id)
            )
            await db.commit()
            return cursor.lastrowid

    async def _is_disposal_processed(
        self, user_id: int, token_symbol: str,
        disposal_date: str, quantity: float
    ) -> bool:
        """Check if a disposal has already been recorded."""
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM realized_gains
                   WHERE user_id = ? AND token_symbol = ?
                   AND disposal_date = ? AND ABS(quantity - ?) < 0.000001""",
                (user_id, token_symbol, disposal_date, quantity)
            )
            row = await cursor.fetchone()
            return row[0] > 0

    async def record_manual_lot(
        self, user_id: int, token_symbol: str,
        quantity: float, cost_per_unit: float,
        acquisition_date: str = None, source: str = "manual"
    ) -> int:
        """Record a manual cost basis lot.

        Returns: lot ID
        """
        if acquisition_date is None:
            acquisition_date = datetime.utcnow().isoformat()

        return await self._insert_lot(
            user_id, token_symbol, quantity, cost_per_unit,
            acquisition_date, "buy", source
        )

    async def dispose_lots(
        self, user_id: int, token_symbol: str,
        quantity: float, proceeds_usd: float,
        method: str = "fifo", disposal_type: str = "sell",
        disposal_date: str = None
    ) -> dict:
        """Dispose of lots using specified method (FIFO/LIFO/Average).

        FIFO: Dispose oldest lots first (ORDER BY acquisition_date ASC)
        LIFO: Dispose newest lots first (ORDER BY acquisition_date DESC)
        Average: Use weighted average cost across all lots

        Creates entries in realized_gains table.
        Updates remaining_quantity in cost_basis_lots.

        Returns: {quantity_disposed, total_cost_basis, total_proceeds, gain_loss}
        """
        if disposal_date is None:
            disposal_date = datetime.utcnow().isoformat()

        method = method.lower()
        if method not in ('fifo', 'lifo', 'average'):
            method = 'fifo'

        remaining_to_dispose = quantity
        total_cost_basis = 0.0
        proceeds_per_unit = proceeds_usd / quantity if quantity > 0 else 0

        if method == 'average':
            return await self._dispose_average(
                user_id, token_symbol, quantity, proceeds_usd,
                disposal_type, disposal_date
            )

        # FIFO or LIFO
        order = "ASC" if method == "fifo" else "DESC"

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                f"""SELECT id, remaining_quantity, cost_per_unit_usd, acquisition_date
                    FROM cost_basis_lots
                    WHERE user_id = ? AND token_symbol = ? AND remaining_quantity > 0
                    ORDER BY acquisition_date {order}""",
                (user_id, token_symbol)
            )
            lots = await cursor.fetchall()

            for lot in lots:
                if remaining_to_dispose <= 0:
                    break

                lot_id = lot['id']
                lot_remaining = lot['remaining_quantity']
                cost_per_unit = lot['cost_per_unit_usd']
                acq_date = lot['acquisition_date']

                # How much to take from this lot
                dispose_from_lot = min(remaining_to_dispose, lot_remaining)
                lot_cost_basis = dispose_from_lot * cost_per_unit
                lot_proceeds = dispose_from_lot * proceeds_per_unit
                gain_loss = lot_proceeds - lot_cost_basis

                # Determine holding period
                holding_period = self._compute_holding_period(acq_date, disposal_date)

                # Update lot remaining quantity
                new_remaining = lot_remaining - dispose_from_lot
                await db.execute(
                    "UPDATE cost_basis_lots SET remaining_quantity = ? WHERE id = ?",
                    (new_remaining, lot_id)
                )

                # Record realized gain
                await db.execute(
                    """INSERT INTO realized_gains
                       (user_id, token_symbol, disposal_date, disposal_type,
                        quantity, proceeds_usd, cost_basis_usd, gain_loss_usd,
                        holding_period, lot_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, token_symbol, disposal_date, disposal_type,
                     dispose_from_lot, lot_proceeds, lot_cost_basis, gain_loss,
                     holding_period, lot_id)
                )

                total_cost_basis += lot_cost_basis
                remaining_to_dispose -= dispose_from_lot

            await db.commit()

        total_gain_loss = proceeds_usd - total_cost_basis
        quantity_disposed = quantity - remaining_to_dispose

        if remaining_to_dispose > 0:
            logger.warning(
                f"Insufficient lots for {token_symbol}: wanted {quantity}, "
                f"disposed {quantity_disposed}, {remaining_to_dispose} unmatched"
            )

        return {
            "quantity_disposed": quantity_disposed,
            "total_cost_basis": round(total_cost_basis, 2),
            "total_proceeds": round(proceeds_usd, 2),
            "gain_loss": round(total_gain_loss, 2),
            "unmatched_quantity": round(remaining_to_dispose, 8)
        }

    async def _dispose_average(
        self, user_id: int, token_symbol: str,
        quantity: float, proceeds_usd: float,
        disposal_type: str, disposal_date: str
    ) -> dict:
        """Dispose using weighted average cost method."""
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # Calculate weighted average cost
            cursor = await db.execute(
                """SELECT SUM(remaining_quantity) as total_qty,
                          SUM(remaining_quantity * cost_per_unit_usd) as total_cost
                   FROM cost_basis_lots
                   WHERE user_id = ? AND token_symbol = ? AND remaining_quantity > 0""",
                (user_id, token_symbol)
            )
            row = await cursor.fetchone()
            total_qty = row['total_qty'] or 0
            total_cost = row['total_cost'] or 0

            if total_qty <= 0:
                return {
                    "quantity_disposed": 0,
                    "total_cost_basis": 0,
                    "total_proceeds": round(proceeds_usd, 2),
                    "gain_loss": round(proceeds_usd, 2),
                    "unmatched_quantity": round(quantity, 8)
                }

            avg_cost = total_cost / total_qty
            actual_dispose = min(quantity, total_qty)
            cost_basis = actual_dispose * avg_cost
            gain_loss = proceeds_usd - cost_basis

            # Get earliest acquisition date for holding period
            cursor = await db.execute(
                """SELECT MIN(acquisition_date) as earliest
                   FROM cost_basis_lots
                   WHERE user_id = ? AND token_symbol = ? AND remaining_quantity > 0""",
                (user_id, token_symbol)
            )
            earliest = (await cursor.fetchone())['earliest']
            holding_period = self._compute_holding_period(earliest, disposal_date)

            # Proportionally reduce all lots
            remaining_to_dispose = actual_dispose
            cursor = await db.execute(
                """SELECT id, remaining_quantity FROM cost_basis_lots
                   WHERE user_id = ? AND token_symbol = ? AND remaining_quantity > 0
                   ORDER BY acquisition_date ASC""",
                (user_id, token_symbol)
            )
            lots = await cursor.fetchall()

            first_lot_id = lots[0]['id'] if lots else None

            for lot in lots:
                if remaining_to_dispose <= 0:
                    break
                proportion = lot['remaining_quantity'] / total_qty
                reduce_by = min(actual_dispose * proportion, lot['remaining_quantity'])
                reduce_by = min(reduce_by, remaining_to_dispose)
                new_remaining = lot['remaining_quantity'] - reduce_by
                await db.execute(
                    "UPDATE cost_basis_lots SET remaining_quantity = ? WHERE id = ?",
                    (new_remaining, lot['id'])
                )
                remaining_to_dispose -= reduce_by

            # Record as single realized gain entry
            await db.execute(
                """INSERT INTO realized_gains
                   (user_id, token_symbol, disposal_date, disposal_type,
                    quantity, proceeds_usd, cost_basis_usd, gain_loss_usd,
                    holding_period, lot_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, token_symbol, disposal_date, disposal_type,
                 actual_dispose, proceeds_usd, cost_basis, gain_loss,
                 holding_period, first_lot_id)
            )

            await db.commit()

        unmatched = quantity - actual_dispose
        return {
            "quantity_disposed": round(actual_dispose, 8),
            "total_cost_basis": round(cost_basis, 2),
            "total_proceeds": round(proceeds_usd, 2),
            "gain_loss": round(gain_loss, 2),
            "unmatched_quantity": round(unmatched, 8)
        }

    def _compute_holding_period(self, acq_date: str, disposal_date: str) -> str:
        """Compute holding period: 'short-term' (<1 year) or 'long-term' (>=1 year)."""
        try:
            # Handle various date formats
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    acq = datetime.strptime(str(acq_date)[:19], fmt[:len(str(acq_date)[:19])])
                    break
                except ValueError:
                    continue
            else:
                acq = datetime.strptime(str(acq_date)[:10], '%Y-%m-%d')

            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    disp = datetime.strptime(str(disposal_date)[:19], fmt[:len(str(disposal_date)[:19])])
                    break
                except ValueError:
                    continue
            else:
                disp = datetime.strptime(str(disposal_date)[:10], '%Y-%m-%d')

            diff = disp - acq
            return "long-term" if diff.days >= 365 else "short-term"
        except Exception:
            return "unknown"

    async def compute_unrealized_pnl(
        self, user_id: int, token_symbol: str = None
    ) -> List[dict]:
        """Compute unrealized P&L for open positions.

        For each token with remaining lots:
        - Sum remaining_quantity * cost_per_unit_usd = total_cost_basis
        - Get current_price from pricing_service
        - current_value = remaining_quantity * current_price
        - unrealized = current_value - total_cost_basis

        Returns list of per-token P&L dicts
        """
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            query = """
                SELECT token_symbol,
                       SUM(remaining_quantity) as total_qty,
                       SUM(remaining_quantity * cost_per_unit_usd) as total_cost
                FROM cost_basis_lots
                WHERE user_id = ? AND remaining_quantity > 0
            """
            params: list = [user_id]
            if token_symbol:
                query += " AND token_symbol = ?"
                params.append(token_symbol.upper())
            query += " GROUP BY token_symbol HAVING total_qty > 0"

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        if not rows:
            return []

        # Get current prices for all tokens
        symbols = [r['token_symbol'] for r in rows]
        from services.pricing import pricing_service
        prices = await pricing_service.get_prices(symbols)

        results = []
        for row in rows:
            symbol = row['token_symbol']
            total_qty = row['total_qty']
            total_cost = row['total_cost'] or 0
            current_price = prices.get(symbol, 0)
            current_value = total_qty * current_price
            unrealized = current_value - total_cost
            pct = (unrealized / total_cost * 100) if total_cost > 0 else 0

            results.append({
                "token_symbol": symbol,
                "total_quantity": round(total_qty, 8),
                "avg_cost_basis": round(total_cost / total_qty, 6) if total_qty > 0 else 0,
                "total_invested": round(total_cost, 2),
                "current_price": round(current_price, 6),
                "current_value": round(current_value, 2),
                "unrealized_gain": round(unrealized, 2),
                "unrealized_pct": round(pct, 2)
            })

        # Sort by absolute unrealized gain descending
        results.sort(key=lambda x: abs(x['unrealized_gain']), reverse=True)
        return results

    async def compute_realized_pnl(
        self, user_id: int, token_symbol: str = None,
        start_date: str = None, end_date: str = None
    ) -> List[dict]:
        """Get realized P&L from realized_gains table.

        Args:
            user_id: User ID
            token_symbol: Optional filter by token
            start_date: Optional ISO date string (inclusive lower bound on disposal_date)
            end_date: Optional ISO date string (inclusive upper bound on disposal_date)

        Returns list of realized gain/loss entries.
        """
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            query = """
                SELECT id, token_symbol, disposal_date, disposal_type,
                       quantity, proceeds_usd, cost_basis_usd, gain_loss_usd,
                       holding_period, lot_id, created_at
                FROM realized_gains
                WHERE user_id = ?
            """
            params: list = [user_id]
            if token_symbol:
                query += " AND token_symbol = ?"
                params.append(token_symbol.upper())
            if start_date:
                query += " AND disposal_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND disposal_date <= ?"
                params.append(end_date)
            query += " ORDER BY disposal_date DESC"

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_monthly_realized(self, user_id: int, months: int = 12) -> List[dict]:
        """Aggregate realized gains by month.

        Args:
            user_id: User ID
            months: Number of months to look back (default 12)

        Returns:
            List of dicts: [{month: "2026-02", realized: 1234.56, count: 5}, ...]
        """
        cutoff = (datetime.utcnow() - timedelta(days=months * 31)).strftime('%Y-%m-%d')

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """SELECT strftime('%Y-%m', disposal_date) as month,
                          COALESCE(SUM(gain_loss_usd), 0) as realized,
                          COUNT(*) as count
                   FROM realized_gains
                   WHERE user_id = ? AND disposal_date >= ?
                   GROUP BY month
                   ORDER BY month ASC""",
                (user_id, cutoff)
            )
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_portfolio_performance(self, user_id: int) -> dict:
        """Get overall portfolio performance.

        Returns:
            {
                total_invested: sum of all lot costs,
                current_value: sum of current values,
                total_unrealized: current - invested,
                total_realized: sum of realized gains,
                total_pnl: unrealized + realized,
                pnl_percent: total_pnl / total_invested * 100,
                top_gainers: [...],
                top_losers: [...],
                assets_count: int,
            }
        """
        # Get unrealized P&L per token
        unrealized_items = await self.compute_unrealized_pnl(user_id)

        total_invested = sum(item['total_invested'] for item in unrealized_items)
        current_value = sum(item['current_value'] for item in unrealized_items)
        total_unrealized = current_value - total_invested

        # Get total realized
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            cursor = await db.execute(
                "SELECT COALESCE(SUM(gain_loss_usd), 0) FROM realized_gains WHERE user_id = ?",
                (user_id,)
            )
            total_realized = (await cursor.fetchone())[0]

        total_pnl = total_unrealized + total_realized
        pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        # Top gainers and losers (from unrealized)
        gainers = sorted(
            [i for i in unrealized_items if i['unrealized_gain'] > 0],
            key=lambda x: x['unrealized_gain'], reverse=True
        )[:5]
        losers = sorted(
            [i for i in unrealized_items if i['unrealized_gain'] < 0],
            key=lambda x: x['unrealized_gain']
        )[:5]

        return {
            "total_invested": round(total_invested, 2),
            "current_value": round(current_value, 2),
            "total_unrealized": round(total_unrealized, 2),
            "total_realized": round(total_realized, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
            "top_gainers": gainers,
            "top_losers": losers,
            "assets_count": len(unrealized_items)
        }

    async def get_asset_detail(self, user_id: int, token_symbol: str) -> dict:
        """Get detailed P&L for a specific asset.

        Returns:
            {
                token_symbol, total_quantity, avg_cost_basis, total_invested,
                current_price, current_value, unrealized_gain, unrealized_pct,
                realized_gain, open_lots, realized_history
            }
        """
        token_symbol = token_symbol.upper()

        # Get unrealized for this specific token
        unrealized = await self.compute_unrealized_pnl(user_id, token_symbol)
        unrealized_data = unrealized[0] if unrealized else {
            "token_symbol": token_symbol,
            "total_quantity": 0,
            "avg_cost_basis": 0,
            "total_invested": 0,
            "current_price": 0,
            "current_value": 0,
            "unrealized_gain": 0,
            "unrealized_pct": 0
        }

        # Get realized gains for this token
        realized = await self.compute_realized_pnl(user_id, token_symbol)
        total_realized = sum(r['gain_loss_usd'] for r in realized)

        # Get open lots
        open_lots = await self.get_open_lots(user_id, token_symbol)

        return {
            **unrealized_data,
            "realized_gain": round(total_realized, 2),
            "open_lots": open_lots,
            "realized_history": realized[:50]  # Last 50 disposals
        }

    async def refresh_pnl_summary(self, user_id: int) -> None:
        """Recompute and update asset_pnl_summary table (materialized view)."""
        unrealized_items = await self.compute_unrealized_pnl(user_id)

        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            # Get realized gains per token
            cursor = await db.execute(
                """SELECT token_symbol, COALESCE(SUM(gain_loss_usd), 0) as realized
                   FROM realized_gains WHERE user_id = ?
                   GROUP BY token_symbol""",
                (user_id,)
            )
            realized_map = {row['token_symbol']: row['realized'] for row in await cursor.fetchall()}

            # Upsert each token's summary
            for item in unrealized_items:
                symbol = item['token_symbol']
                realized = realized_map.get(symbol, 0)

                await db.execute(
                    """INSERT INTO asset_pnl_summary
                       (user_id, token_symbol, total_invested_usd, current_value_usd,
                        unrealized_gain_usd, realized_gain_usd, avg_cost_basis_usd,
                        total_quantity, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id, token_symbol) DO UPDATE SET
                        total_invested_usd = excluded.total_invested_usd,
                        current_value_usd = excluded.current_value_usd,
                        unrealized_gain_usd = excluded.unrealized_gain_usd,
                        realized_gain_usd = excluded.realized_gain_usd,
                        avg_cost_basis_usd = excluded.avg_cost_basis_usd,
                        total_quantity = excluded.total_quantity,
                        last_updated = CURRENT_TIMESTAMP""",
                    (user_id, symbol, item['total_invested'], item['current_value'],
                     item['unrealized_gain'], realized, item['avg_cost_basis'],
                     item['total_quantity'])
                )

            # Remove tokens that no longer have open positions
            active_symbols = {item['token_symbol'] for item in unrealized_items}
            cursor = await db.execute(
                "SELECT token_symbol FROM asset_pnl_summary WHERE user_id = ?",
                (user_id,)
            )
            all_summary_symbols = {row['token_symbol'] for row in await cursor.fetchall()}
            stale_symbols = all_summary_symbols - active_symbols

            for symbol in stale_symbols:
                # Keep if there are realized gains, just zero out unrealized
                realized = realized_map.get(symbol, 0)
                if realized != 0:
                    await db.execute(
                        """UPDATE asset_pnl_summary
                           SET total_invested_usd = 0, current_value_usd = 0,
                               unrealized_gain_usd = 0, total_quantity = 0,
                               last_updated = CURRENT_TIMESTAMP
                           WHERE user_id = ? AND token_symbol = ?""",
                        (user_id, symbol)
                    )
                else:
                    await db.execute(
                        "DELETE FROM asset_pnl_summary WHERE user_id = ? AND token_symbol = ?",
                        (user_id, symbol)
                    )

            await db.commit()

        logger.info(f"Refreshed P&L summary for user {user_id}: {len(unrealized_items)} active assets")

    async def get_open_lots(self, user_id: int, token_symbol: str) -> List[dict]:
        """Get all open (remaining > 0) cost basis lots for a token."""
        async with aiosqlite.connect(str(DATABASE_PATH)) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """SELECT id, acquisition_date, acquisition_type, acquisition_source,
                          quantity, cost_per_unit_usd, remaining_quantity, tx_id, created_at
                   FROM cost_basis_lots
                   WHERE user_id = ? AND token_symbol = ? AND remaining_quantity > 0
                   ORDER BY acquisition_date ASC""",
                (user_id, token_symbol.upper())
            )
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]


# Singleton instance
cost_basis_engine = CostBasisEngine()
