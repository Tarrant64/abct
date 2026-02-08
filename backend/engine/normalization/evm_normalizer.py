"""
EVM Event Normalizer

Converts EVM transaction data + receipt logs into canonical events.
Handles native ETH transfers, ERC-20 transfers, and ERC-721 transfers.
"""

import logging
from typing import List, Dict, Any

from engine.models import CanonicalEvent, ChainId, EventType
from engine.normalization.base import EventNormalizer

logger = logging.getLogger(__name__)

# ERC-20 Transfer event topic
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _hex_to_int(hex_str: str) -> int:
    """Convert hex string to int, handling empty/None."""
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


def _topic_to_address(topic: str) -> str:
    """Extract address from a 32-byte padded log topic."""
    if not topic or len(topic) < 42:
        return ""
    return "0x" + topic[-40:].lower()


class EvmNormalizer(EventNormalizer):
    def __init__(self, chain: ChainId):
        self.chain = chain

    async def normalize(self, user_id: int, account_id: str,
                        raw_data: Dict[str, Any]) -> List[CanonicalEvent]:
        events = []
        tx_id = raw_data.get("hash", "")
        block_height = raw_data.get("block_number")
        block_time = raw_data.get("block_time")
        event_idx = 0

        account_lower = account_id.lower()
        tx_from = (raw_data.get("from", "") or "").lower()
        tx_to = (raw_data.get("to", "") or "").lower()

        # Gas fee (in wei)
        gas_used = _hex_to_int(raw_data.get("gas_used", "0x0"))
        gas_price = _hex_to_int(raw_data.get("gas_price", "0x0"))
        fee_wei = str(gas_used * gas_price)

        # Native value transfer
        value = _hex_to_int(raw_data.get("value", "0x0"))
        if value > 0:
            if tx_from == account_lower:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=self.chain,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="out",
                    asset_id="native",
                    amount=str(value),
                    counterparty=tx_to,
                    fee=fee_wei,
                    block_height=block_height,
                    block_time=block_time,
                ))
                event_idx += 1

            if tx_to == account_lower:
                events.append(CanonicalEvent(
                    user_id=user_id,
                    chain=self.chain,
                    event_type=EventType.ASSET_MOVEMENT,
                    tx_id=tx_id,
                    event_index=event_idx,
                    account_id=account_id,
                    direction="in",
                    asset_id="native",
                    amount=str(value),
                    counterparty=tx_from,
                    block_height=block_height,
                    block_time=block_time,
                ))
                event_idx += 1

        # If sender is our account but no native value, still record fee
        if tx_from == account_lower and value == 0 and gas_used > 0:
            events.append(CanonicalEvent(
                user_id=user_id,
                chain=self.chain,
                event_type=EventType.ASSET_MOVEMENT,
                tx_id=tx_id,
                event_index=event_idx,
                account_id=account_id,
                direction="out",
                asset_id="native",
                amount="0",
                fee=fee_wei,
                block_height=block_height,
                block_time=block_time,
                metadata={"type": "fee_only"},
            ))
            event_idx += 1

        # Process logs for ERC-20 and ERC-721 transfers
        for log in raw_data.get("logs", []):
            topics = log.get("topics", [])
            if not topics or topics[0] != ERC20_TRANSFER_TOPIC:
                continue
            if len(topics) < 3:
                continue

            from_addr = _topic_to_address(topics[1])
            to_addr = _topic_to_address(topics[2])
            contract = (log.get("address", "") or "").lower()

            # Determine if ERC-20 (data has value) or ERC-721 (topics[3] has tokenId)
            if len(topics) == 4:
                # ERC-721 transfer
                token_id = _hex_to_int(topics[3])
                nft_asset_id = f"{contract}:{token_id}"

                if from_addr == account_lower:
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=self.chain,
                        event_type=EventType.NFT_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="out",
                        asset_id=nft_asset_id,
                        amount="1",
                        counterparty=to_addr,
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1

                if to_addr == account_lower:
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=self.chain,
                        event_type=EventType.NFT_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="in",
                        asset_id=nft_asset_id,
                        amount="1",
                        counterparty=from_addr,
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1
            else:
                # ERC-20 transfer
                data = log.get("data", "0x0")
                amount = _hex_to_int(data)
                token_asset_id = contract

                if from_addr == account_lower:
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=self.chain,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="out",
                        asset_id=token_asset_id,
                        amount=str(amount),
                        counterparty=to_addr,
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1

                if to_addr == account_lower:
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=self.chain,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="in",
                        asset_id=token_asset_id,
                        amount=str(amount),
                        counterparty=from_addr,
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1

        return events
