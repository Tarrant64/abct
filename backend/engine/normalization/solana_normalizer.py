"""
Solana Event Normalizer

Converts Solana transaction data (from Helius or RPC) into canonical events.
Handles native SOL transfers and SPL token movements.
"""

import logging
from typing import List, Dict, Any

from engine.models import CanonicalEvent, ChainId, EventType
from engine.normalization.base import EventNormalizer

logger = logging.getLogger(__name__)


class SolanaNormalizer(EventNormalizer):
    chain = ChainId.SOLANA

    async def normalize(self, user_id: int, account_id: str,
                        raw_data: Dict[str, Any]) -> List[CanonicalEvent]:
        events = []
        event_idx = 0

        # Check if this is Helius enhanced format (has "type", "tokenTransfers", etc.)
        if "type" in raw_data and "tokenTransfers" in raw_data:
            return await self._normalize_helius(user_id, account_id, raw_data)

        # Standard RPC format
        tx_id = raw_data.get("signature", "")
        block_time = raw_data.get("block_time")
        slot = raw_data.get("slot")
        fee = str(raw_data.get("fee", 0))

        account_keys = raw_data.get("account_keys", [])
        # Find account index
        account_idx = None
        for i, key in enumerate(account_keys):
            key_str = key.get("pubkey", key) if isinstance(key, dict) else str(key)
            if key_str == account_id:
                account_idx = i
                break

        if account_idx is not None:
            pre_balances = raw_data.get("pre_balances", [])
            post_balances = raw_data.get("post_balances", [])

            if account_idx < len(pre_balances) and account_idx < len(post_balances):
                pre = pre_balances[account_idx]
                post = post_balances[account_idx]
                diff = post - pre

                if diff != 0:
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=ChainId.SOLANA,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="in" if diff > 0 else "out",
                        asset_id="native",
                        amount=str(abs(diff)),  # in lamports
                        fee=fee,
                        block_height=slot,
                        block_time=block_time,
                    ))
                    event_idx += 1

        # SPL token balance changes
        pre_tokens = raw_data.get("pre_token_balances", [])
        post_tokens = raw_data.get("post_token_balances", [])

        # Build lookup: {(owner, mint): amount}
        pre_map = {}
        for tb in pre_tokens:
            owner = tb.get("owner", "")
            mint = tb.get("mint", "")
            amount = int(tb.get("uiTokenAmount", {}).get("amount", "0"))
            pre_map[(owner, mint)] = amount

        post_map = {}
        for tb in post_tokens:
            owner = tb.get("owner", "")
            mint = tb.get("mint", "")
            amount = int(tb.get("uiTokenAmount", {}).get("amount", "0"))
            post_map[(owner, mint)] = amount

        all_keys = set(pre_map.keys()) | set(post_map.keys())
        for (owner, mint) in all_keys:
            if owner != account_id:
                continue
            pre_amt = pre_map.get((owner, mint), 0)
            post_amt = post_map.get((owner, mint), 0)
            diff = post_amt - pre_amt
            if diff != 0:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=ChainId.SOLANA,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="in" if diff > 0 else "out",
                    asset_id=mint,
                    amount=str(abs(diff)),
                    block_height=slot,
                    block_time=block_time,
                ))
                event_idx += 1

        return events

    async def _normalize_helius(self, user_id: int, account_id: str,
                                 raw_data: Dict[str, Any]) -> List[CanonicalEvent]:
        """Normalize Helius enhanced transaction format."""
        events = []
        event_idx = 0
        tx_id = raw_data.get("signature", "")
        block_time = raw_data.get("timestamp")
        slot = raw_data.get("slot")
        fee = str(raw_data.get("fee", 0))

        # Native SOL transfers
        for transfer in raw_data.get("nativeTransfers", []):
            from_addr = transfer.get("fromUserAccount", "")
            to_addr = transfer.get("toUserAccount", "")
            amount = transfer.get("amount", 0)

            if from_addr == account_id:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=ChainId.SOLANA,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="out",
                    asset_id="native",
                    amount=str(amount),
                    counterparty=to_addr,
                    fee=fee if event_idx == 0 else None,
                    block_height=slot,
                    block_time=block_time,
                ))
                event_idx += 1

            if to_addr == account_id:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=ChainId.SOLANA,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="in",
                    asset_id="native",
                    amount=str(amount),
                    counterparty=from_addr,
                    block_height=slot,
                    block_time=block_time,
                ))
                event_idx += 1

        # SPL token transfers
        for transfer in raw_data.get("tokenTransfers", []):
            from_addr = transfer.get("fromUserAccount", "")
            to_addr = transfer.get("toUserAccount", "")
            mint = transfer.get("mint", "")
            amount = transfer.get("tokenAmount", 0)

            if from_addr == account_id:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=ChainId.SOLANA,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="out",
                    asset_id=mint,
                    amount=str(amount),
                    counterparty=to_addr,
                    block_height=slot,
                    block_time=block_time,
                ))
                event_idx += 1

            if to_addr == account_id:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=ChainId.SOLANA,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="in",
                    asset_id=mint,
                    amount=str(amount),
                    counterparty=from_addr,
                    block_height=slot,
                    block_time=block_time,
                ))
                event_idx += 1

        return events
