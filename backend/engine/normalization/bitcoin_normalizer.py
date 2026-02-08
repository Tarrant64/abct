"""
Bitcoin Event Normalizer

Converts Blockstream vin/vout data into canonical AssetMovement events.
"""

import logging
from typing import List, Dict, Any

from engine.models import CanonicalEvent, ChainId, EventType
from engine.normalization.base import EventNormalizer

logger = logging.getLogger(__name__)


class BitcoinNormalizer(EventNormalizer):
    chain = ChainId.BITCOIN

    async def normalize(self, user_id: int, account_id: str,
                        raw_data: Dict[str, Any]) -> List[CanonicalEvent]:
        events = []
        tx_id = raw_data.get("txid", "")
        block_height = raw_data.get("block_height")
        block_time = raw_data.get("block_time")
        fee = str(raw_data.get("fee", 0))
        event_idx = 0

        # Process inputs (outgoing)
        for vin in raw_data.get("vin", []):
            prevout = vin.get("prevout", {})
            if not prevout:
                continue

            scriptpubkey_address = prevout.get("scriptpubkey_address", "")
            if scriptpubkey_address != account_id:
                continue

            value = prevout.get("value", 0)
            events.append(CanonicalEvent(
                user_id=user_id,
                chain=ChainId.BITCOIN,
                event_type=EventType.ASSET_MOVEMENT,
                tx_id=tx_id,
                event_index=event_idx,
                account_id=account_id,
                direction="out",
                asset_id="native",
                amount=str(value),  # in satoshis
                fee=fee,
                block_height=block_height,
                block_time=block_time,
            ))
            event_idx += 1

        # Process outputs (incoming)
        for vout_idx, vout in enumerate(raw_data.get("vout", [])):
            scriptpubkey_address = vout.get("scriptpubkey_address", "")
            if scriptpubkey_address != account_id:
                continue

            value = vout.get("value", 0)
            events.append(CanonicalEvent(
                user_id=user_id,
                chain=ChainId.BITCOIN,
                event_type=EventType.ASSET_MOVEMENT,
                tx_id=tx_id,
                event_index=event_idx,
                account_id=account_id,
                direction="in",
                asset_id="native",
                amount=str(value),  # in satoshis
                block_height=block_height,
                block_time=block_time,
            ))
            event_idx += 1

        return events
