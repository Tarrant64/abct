"""
Base Protocol Adapter - Abstract base class for all DeFi protocol integrations.

Each protocol adapter detects positions by one of these methods:
- token_balance: Check if wallet holds protocol receipt tokens (stETH, rETH, etc.)
- contract_call: Query smart contract state (Aave getUserAccountData, etc.)
- utxo_scan: Scan UTXOs for protocol-specific assets (Cardano DeFi)
- nft_position: Check for NFT-based LP positions (Uniswap v3)
- program_account: Parse Solana program accounts (Marinade, Orca, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class DetectionMethod(str, Enum):
    TOKEN_BALANCE = "token_balance"
    CONTRACT_CALL = "contract_call"
    UTXO_SCAN = "utxo_scan"
    NFT_POSITION = "nft_position"
    PROGRAM_ACCOUNT = "program_account"


class PositionType(str, Enum):
    LENDING_SUPPLY = "lending_supply"
    LENDING_BORROW = "lending_borrow"
    LIQUID_STAKING = "liquid_staking"
    LP_POSITION = "lp_position"
    CONCENTRATED_LP = "concentrated_lp"
    STAKING = "staking"
    YIELD_VAULT = "yield_vault"
    GOVERNANCE = "governance"
    RESTAKING = "restaking"
    PERPETUALS = "perpetuals"
    DEPIN = "depin"


@dataclass
class ProtocolPosition:
    """Standardized DeFi position across all protocols and chains."""
    protocol: str
    chain: str
    position_type: PositionType
    token_symbol: str
    token_name: str = ""
    amount: float = 0.0
    value_usd: float = 0.0
    # Optional fields
    underlying_tokens: list = field(default_factory=list)  # For LP: [{symbol, amount}]
    apy: Optional[float] = None
    pending_rewards: Optional[float] = None
    reward_token: Optional[str] = None
    contract_address: Optional[str] = None
    token_id: Optional[str] = None  # For NFT positions
    logo_url: Optional[str] = None
    extra: dict = field(default_factory=dict)  # Protocol-specific metadata

    def to_dict(self) -> dict:
        result = {
            'protocol': self.protocol,
            'chain': self.chain,
            'position_type': self.position_type.value,
            'token_symbol': self.token_symbol,
            'token_name': self.token_name,
            'amount': self.amount,
            'value_usd': self.value_usd,
        }
        if self.underlying_tokens:
            result['underlying_tokens'] = self.underlying_tokens
        if self.apy is not None:
            result['apy'] = self.apy
        if self.pending_rewards is not None:
            result['pending_rewards'] = self.pending_rewards
            result['reward_token'] = self.reward_token
        if self.contract_address:
            result['contract_address'] = self.contract_address
        if self.token_id:
            result['token_id'] = self.token_id
        if self.logo_url:
            result['logo_url'] = self.logo_url
        if self.extra:
            result['extra'] = self.extra
        return result


class ProtocolAdapter(ABC):
    """Abstract base class for all DeFi protocol adapters.

    Subclasses must define class attributes:
    - PROTOCOL_NAME: str - e.g., 'Aave v3'
    - SUPPORTED_CHAINS: list[str] - e.g., ['ethereum', 'polygon', 'arbitrum']
    - DETECTION_METHOD: DetectionMethod
    - PROTOCOL_URL: str - main protocol URL
    - LOGO_URL: str - protocol logo URL (optional)
    """

    PROTOCOL_NAME: str = ""
    SUPPORTED_CHAINS: List[str] = []
    DETECTION_METHOD: DetectionMethod = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL: str = ""
    LOGO_URL: str = ""

    @abstractmethod
    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect all positions for a given address on this protocol.

        Args:
            address: Wallet address to scan
            chain: Specific chain to scan (None = all supported chains)

        Returns:
            List of detected positions (empty if none found)
        """
        ...

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending/claimable rewards. Optional - not all protocols have this.

        Returns:
            Dict with reward info or None if not applicable/implemented
        """
        return None

    def supports_chain(self, chain: str) -> bool:
        """Check if this adapter supports a given chain."""
        return chain in self.SUPPORTED_CHAINS

    def info(self) -> dict:
        """Return protocol metadata."""
        return {
            'name': self.PROTOCOL_NAME,
            'chains': self.SUPPORTED_CHAINS,
            'detection_method': self.DETECTION_METHOD.value,
            'url': self.PROTOCOL_URL,
            'logo_url': self.LOGO_URL,
        }
