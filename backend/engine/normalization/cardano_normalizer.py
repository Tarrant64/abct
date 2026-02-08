"""
Cardano Event Normalizer

Converts Blockfrost UTXO data into canonical AssetMovement events.
Each input/output that involves the account generates an event.
"""

import logging
from typing import List, Dict, Any

from engine.models import CanonicalEvent, ChainId, EventType
from engine.normalization.base import EventNormalizer

logger = logging.getLogger(__name__)


class CardanoNormalizer(EventNormalizer):
    chain = ChainId.CARDANO

    async def normalize(self, user_id: int, account_id: str,
                        raw_data: Dict[str, Any]) -> List[CanonicalEvent]:
        events = []
        tx_id = raw_data.get("tx_hash", "")
        block_height = raw_data.get("block_height")
        block_time = raw_data.get("block_time")
        fee = raw_data.get("fees", "0")
        event_idx = 0

        # Process inputs (outgoing from account)
        for inp in raw_data.get("inputs", []):
            inp_addr = inp.get("address", "")
            if inp_addr != account_id:
                continue

            # ADA (lovelace)
            for amount_entry in inp.get("amount", []):
                if amount_entry.get("unit") == "lovelace":
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=ChainId.CARDANO,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="out",
                        asset_id="native",
                        amount=amount_entry.get("quantity", "0"),
                        fee=fee,
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1
                else:
                    # Native asset
                    unit = amount_entry.get("unit", "")
                    policy_id = unit[:56] if len(unit) >= 56 else unit
                    asset_name = unit[56:] if len(unit) > 56 else ""
                    asset_id = f"{policy_id}.{asset_name}" if asset_name else policy_id

                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=ChainId.CARDANO,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="out",
                        asset_id=asset_id,
                        amount=amount_entry.get("quantity", "0"),
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1

        # Process outputs (incoming to account)
        for out in raw_data.get("outputs", []):
            out_addr = out.get("address", "")
            if out_addr != account_id:
                continue

            for amount_entry in out.get("amount", []):
                if amount_entry.get("unit") == "lovelace":
                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=ChainId.CARDANO,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="in",
                        asset_id="native",
                        amount=amount_entry.get("quantity", "0"),
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1
                else:
                    unit = amount_entry.get("unit", "")
                    policy_id = unit[:56] if len(unit) >= 56 else unit
                    asset_name = unit[56:] if len(unit) > 56 else ""
                    asset_id = f"{policy_id}.{asset_name}" if asset_name else policy_id

                    events.append(CanonicalEvent(
                        user_id=user_id,
                        chain=ChainId.CARDANO,
                        event_type=EventType.ASSET_MOVEMENT,
                        tx_id=tx_id,
                        event_index=event_idx,
                        account_id=account_id,
                        direction="in",
                        asset_id=asset_id,
                        amount=amount_entry.get("quantity", "0"),
                        block_height=block_height,
                        block_time=block_time,
                    ))
                    event_idx += 1

        return events
