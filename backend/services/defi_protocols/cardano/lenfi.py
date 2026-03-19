"""
Lenfi (ex-Aada) Lending Adapter for Cardano.
Detects lending supply positions via receipt token in wallet, and
borrow positions via Lenfi loan NFTs.

Lenfi (formerly Aada Finance) is a lending protocol on Cardano (~$255K TVL).
When users supply assets, they receive receipt tokens whose policy ID identifies
them as Lenfi lenders. The token name encodes position details.

When users borrow, they receive a loan NFT that represents their active loan.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import check_token_in_wallet

logger = logging.getLogger(__name__)

# Lenfi receipt token policy ID (supply positions)
RECEIPT_TOKEN_POLICY_ID = "d4b1e603f382e42f63d6b4c61b1bfe756f2a3d2d1d0e3c3c33fabe42"

# Lenfi loan NFT policy ID (borrow positions)
# When users take a loan, they receive an NFT with this policy
LOAN_NFT_POLICY_ID = "a43a5e14b0f9245c0f5fe3f2fce7a732e4e0628c5efc5e1f89c16683"


class LenfiAdapter(ProtocolAdapter):
    """Adapter for Lenfi (ex-Aada) lending supply and borrow positions on Cardano."""

    PROTOCOL_NAME = "Lenfi"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://lenfi.io"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Lenfi lending positions via receipt token and loan NFT balance.

        Queries Blockfrost for:
        1. Assets with the Lenfi receipt token policy ID (supply positions)
        2. Assets with the Lenfi loan NFT policy ID (borrow positions)

        Each matching token represents an active lending or borrowing position.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for each position held
        """
        if chain and chain != "cardano":
            return []

        positions = []

        # Detect supply positions (receipt tokens)
        try:
            supply_positions = await self._detect_supply_positions(address)
            positions.extend(supply_positions)
        except Exception as e:
            logger.error(f"[Lenfi] Supply detection error: {e}")

        # Detect borrow positions (loan NFTs)
        try:
            borrow_positions = await self._detect_borrow_positions(address)
            positions.extend(borrow_positions)
        except Exception as e:
            logger.error(f"[Lenfi] Borrow detection error: {e}")

        if positions:
            logger.info(
                f"[Lenfi] Found {len(positions)} position(s) "
                f"({sum(1 for p in positions if p.position_type == PositionType.LENDING_SUPPLY)} supply, "
                f"{sum(1 for p in positions if p.position_type == PositionType.LENDING_BORROW)} borrow) "
                f"for {address[:20]}..."
            )

        return positions

    async def _detect_supply_positions(self, address: str) -> List[ProtocolPosition]:
        """Detect supply positions via Lenfi receipt tokens."""
        matched = await check_token_in_wallet(address, RECEIPT_TOKEN_POLICY_ID)
        if not matched:
            return []

        positions = []
        for token in matched:
            qty = token["quantity"]
            asset_hex = token.get("asset_name_hex", "")
            try:
                position_label = bytes.fromhex(asset_hex).decode("utf-8", errors="replace").strip("\x00")
            except Exception:
                position_label = "Receipt"

            # Parse underlying token from position label if possible
            underlying = self._parse_underlying_from_label(position_label)

            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.LENDING_SUPPLY,
                token_symbol=position_label or "LENFI-RECEIPT",
                token_name="Lenfi Lending Supply",
                amount=float(qty),
                value_usd=0.0,
                extra={
                    "receipt_token": token.get("unit", ""),
                    "underlying_token": underlying,
                },
            ))

        return positions

    async def _detect_borrow_positions(self, address: str) -> List[ProtocolPosition]:
        """Detect borrow positions via Lenfi loan NFTs.

        When a user borrows from Lenfi, they receive a loan NFT that
        represents their active loan position. The NFT asset name
        encodes loan details.
        """
        matched = await check_token_in_wallet(address, LOAN_NFT_POLICY_ID)
        if not matched:
            return []

        positions = []
        for token in matched:
            qty = token["quantity"]
            asset_hex = token.get("asset_name_hex", "")
            try:
                loan_label = bytes.fromhex(asset_hex).decode("utf-8", errors="replace").strip("\x00")
            except Exception:
                loan_label = "Loan"

            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.LENDING_BORROW,
                token_symbol=loan_label or "LENFI-LOAN",
                token_name="Lenfi Active Loan",
                amount=float(qty),
                value_usd=0.0,
                extra={
                    "loan_nft": token.get("unit", ""),
                },
            ))

        return positions

    def _parse_underlying_from_label(self, label: str) -> str:
        """Try to extract underlying token symbol from receipt token label."""
        if not label:
            return "unknown"

        # Common patterns: "ADA Pool", "ADA-pool-receipt", etc.
        label_upper = label.upper()
        known_tokens = ["ADA", "USDC", "USDT", "DJED", "MIN", "SNEK", "LENFI"]
        for tok in known_tokens:
            if tok in label_upper:
                return tok
        return label.split("-")[0] if "-" in label else label.split(" ")[0] if " " in label else label
