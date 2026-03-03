"""
Canonical data models for the V2 Ingestion Engine.

All pipeline stages communicate through these shared types.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime


class ChainId(str, Enum):
    CARDANO = "cardano"
    BITCOIN = "bitcoin"
    ETHEREUM = "ethereum"
    SOLANA = "solana"
    POLYGON = "polygon"
    BASE = "base"


class WorkDomain(str, Enum):
    INDEX = "index"
    HYDRATE = "hydrate"
    NORMALIZE = "normalize"
    ENRICH_PRICE = "enrich_price"
    ENRICH_METADATA = "enrich_metadata"


class WorkStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class BackfillStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    ASSET_MOVEMENT = "asset_movement"
    NFT_MOVEMENT = "nft_movement"
    POSITION_SNAPSHOT = "position_snapshot"


class AccountType(str, Enum):
    PRIMARY = "primary"
    DERIVED = "derived"
    TOKEN_ACCOUNT = "token_account"
    STAKE_KEY = "stake_key"


# --- Pipeline Data Models ---

class AccountSubject(BaseModel):
    """An expanded account discovered from a wallet (Stage A output)."""
    user_id: int
    wallet_id: int
    chain: ChainId
    account_id: str
    account_type: AccountType
    parent_account_id: Optional[str] = None


class TxIndexEntry(BaseModel):
    """A transaction identifier linked to an account (Stage B output)."""
    user_id: int
    chain: ChainId
    account_id: str
    tx_id: str
    block_height: Optional[int] = None
    block_time: Optional[int] = None


class TxRaw(BaseModel):
    """Cached full transaction data (Stage C output)."""
    chain: ChainId
    tx_id: str
    raw_data: Dict[str, Any]
    provider: str


class CanonicalEvent(BaseModel):
    """A normalized ledger event (Stage D output). Idempotent dedup key built from chain+tx_id+event_index+account_id+direction."""
    user_id: int
    chain: ChainId
    event_type: EventType
    tx_id: str
    event_index: int
    account_id: str
    direction: str  # 'in' or 'out'
    asset_id: str   # 'native', 'policyId.assetName', 'contract:tokenId'
    amount: str     # string for arbitrary precision
    counterparty: Optional[str] = None
    fee: Optional[str] = None
    block_height: Optional[int] = None
    block_time: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class PricePoint(BaseModel):
    """A historical price data point (Stage E output)."""
    asset_id: str
    date: str       # YYYY-MM-DD
    price_usd: float
    source: str


# --- Work Unit Models ---

class WorkUnit(BaseModel):
    """A portable work item for the scheduler."""
    id: Optional[int] = None
    backfill_id: int
    user_id: int
    chain: ChainId
    account_id: str
    domain: WorkDomain
    cursor_start: Optional[str] = None
    cursor_end: Optional[str] = None
    status: WorkStatus = WorkStatus.PENDING
    assigned_provider: Optional[str] = None
    attempt_count: int = 0
    max_attempts: int = 3
    error_message: Optional[str] = None


class BackfillPlan(BaseModel):
    """A top-level backfill job."""
    id: Optional[int] = None
    user_id: int
    chains: List[ChainId]
    domains: List[WorkDomain]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: BackfillStatus = BackfillStatus.PLANNING
    total_work_units: int = 0
    completed_work_units: int = 0
    failed_work_units: int = 0
    progress_pct: float = 0.0
    error_message: Optional[str] = None


# --- Provider Models ---

class ProviderCapability(BaseModel):
    """What a provider can do."""
    provider_name: str
    chain: ChainId
    domain: WorkDomain
    priority: int = 50  # higher = preferred


class ProviderHealth(BaseModel):
    """Health state for a provider+chain+domain combination."""
    provider_name: str
    chain: ChainId
    domain: WorkDomain
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    circuit_open_until: Optional[datetime] = None
    avg_latency_ms: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    quota_remaining: Optional[int] = None
    quota_resets_at: Optional[datetime] = None


# --- API Request/Response Models ---

class BackfillRequest(BaseModel):
    """Request to start a backfill."""
    chains: List[ChainId]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    wallet_ids: Optional[List[int]] = None
    force_full: bool = False  # Skip incremental detection — re-index from genesis
    domains: List[WorkDomain] = [
        WorkDomain.INDEX,
        WorkDomain.HYDRATE,
        WorkDomain.NORMALIZE,
        WorkDomain.ENRICH_PRICE,
    ]


class BackfillStatusResponse(BaseModel):
    """Status of a running backfill."""
    backfill_id: int
    status: BackfillStatus
    progress_pct: float
    stages: Dict[str, Dict[str, int]]  # {domain: {done: N, total: N}}
    error_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class GapInfo(BaseModel):
    """Missing data range for a wallet."""
    wallet_id: int
    chain: ChainId
    missing_ranges: List[Dict[str, str]]  # [{from: date, to: date}]


class SnapshotHolding(BaseModel):
    """A single holding in a portfolio snapshot."""
    chain: ChainId
    asset: str
    amount: str
    value_usd: Optional[float] = None


class PortfolioSnapshot(BaseModel):
    """Point-in-time portfolio state."""
    at_time: str
    total_value_usd: float
    holdings: List[SnapshotHolding]
