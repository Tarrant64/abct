"""
Pydantic Validation Models for ABCT Routers

Centralized validation models to ensure all API inputs are properly validated.

Security Benefits:
- Type validation prevents injection attacks
- String length limits prevent DoS
- Pattern validation prevents malicious inputs
- Required fields enforce data completeness
"""

from pydantic import BaseModel, validator, Field, constr
from typing import Optional, List
import re


# ============ Wallet Models ============

class WalletAddressRequest(BaseModel):
    """Validation for wallet discovery and operations."""
    address: constr(min_length=1, max_length=512) = Field(
        ...,
        description="Wallet address or stake key"
    )

    @validator('address')
    def validate_address(cls, v):
        # Remove whitespace
        v = v.strip()
        if not v:
            raise ValueError("Address cannot be empty")
        # Prevent null bytes and control characters
        if '\x00' in v or any(ord(c) < 32 for c in v):
            raise ValueError("Address contains invalid characters")
        return v


class WalletLabelRequest(BaseModel):
    """Validation for wallet label updates."""
    label: Optional[constr(max_length=256)] = Field(
        None,
        description="Wallet label/nickname"
    )

    @validator('label')
    def validate_label(cls, v):
        if v is None:
            return v
        # Strip whitespace
        v = v.strip()
        # Prevent null bytes
        if '\x00' in v:
            raise ValueError("Label contains invalid characters")
        return v if v else None


class MultipleWalletsRequest(BaseModel):
    """Validation for adding multiple wallets."""
    addresses: List[constr(min_length=1, max_length=512)] = Field(
        ...,
        description="List of wallet addresses",
        max_items=100  # Prevent excessive batch operations
    )
    label: Optional[constr(max_length=256)] = None

    @validator('addresses')
    def validate_addresses(cls, v):
        if not v:
            raise ValueError("At least one address is required")
        # Validate each address
        cleaned = []
        for addr in v:
            addr = addr.strip()
            if not addr:
                continue
            if '\x00' in addr or any(ord(c) < 32 for c in addr):
                raise ValueError(f"Address '{addr[:50]}...' contains invalid characters")
            cleaned.append(addr)
        if not cleaned:
            raise ValueError("No valid addresses provided")
        return cleaned


class XPubDiscoveryRequest(BaseModel):
    """Validation for xpub/ypub/zpub discovery."""
    xpub: constr(min_length=1, max_length=256) = Field(
        ...,
        description="Extended public key (xpub/ypub/zpub)"
    )
    gap_limit: int = Field(default=20, ge=1, le=100)
    max_addresses: int = Field(default=100, ge=1, le=1000)

    @validator('xpub')
    def validate_xpub(cls, v):
        v = v.strip()
        # Must start with xpub, ypub, or zpub
        if not v.startswith(('xpub', 'ypub', 'zpub')):
            raise ValueError("Invalid extended public key format")
        if '\x00' in v:
            raise ValueError("Invalid characters in xpub")
        return v


class XPubAddRequest(BaseModel):
    """Validation for adding xpub addresses."""
    xpub: Optional[constr(min_length=1, max_length=256)] = None
    addresses: Optional[List[constr(min_length=1, max_length=256)]] = Field(
        None,
        max_items=1000
    )
    add_all: bool = False
    label: Optional[constr(max_length=256)] = "xpub"
    gap_limit: int = Field(default=20, ge=1, le=100)

    @validator('xpub')
    def validate_xpub(cls, v):
        if v is None:
            return v
        v = v.strip()
        if v and not v.startswith(('xpub', 'ypub', 'zpub')):
            raise ValueError("Invalid extended public key format")
        return v


# ============ Portfolio Models ============

class TokenTrackRequest(BaseModel):
    """Validation for token tracking toggle."""
    asset_id: constr(min_length=1, max_length=256) = Field(
        ...,
        description="Asset ID to track"
    )
    track: bool = Field(..., description="Enable or disable tracking")
    ticker: Optional[constr(min_length=1, max_length=32)] = None
    decimals: Optional[int] = Field(None, ge=0, le=18)

    @validator('asset_id')
    def validate_asset_id(cls, v):
        v = v.strip()
        if '\x00' in v:
            raise ValueError("Asset ID contains invalid characters")
        return v

    @validator('ticker')
    def validate_ticker(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        # Allow only alphanumeric and common symbols
        if not re.match(r'^[A-Z0-9_.-]+$', v):
            raise ValueError("Ticker contains invalid characters")
        return v


class StakeSyncRequest(BaseModel):
    """Validation for stake address sync."""
    address: constr(min_length=1, max_length=512) = Field(
        ...,
        description="Cardano address to sync"
    )
    label_prefix: constr(min_length=1, max_length=128) = "Discovered"

    @validator('address')
    def validate_address(cls, v):
        v = v.strip()
        if '\x00' in v:
            raise ValueError("Address contains invalid characters")
        return v


# ============ Settings Models ============

class APIKeyUpdate(BaseModel):
    """Validation for API key updates."""
    api_key: constr(min_length=1, max_length=512) = Field(
        ...,
        description="API key to configure"
    )

    @validator('api_key')
    def validate_api_key(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("API key cannot be empty")
        # Check for control characters (but allow some special chars in keys)
        if any(ord(c) < 32 or c == '\x00' for c in v):
            raise ValueError("API key contains invalid characters")
        return v


class RateLimitUpdate(BaseModel):
    """Validation for rate limit updates."""
    requests_limit: int = Field(..., gt=0, le=1000000)
    period_seconds: int = Field(default=86400, gt=0, le=2592000)  # Max 30 days


# ============ Query Parameter Validation ============

def validate_refresh_param(refresh: bool = False) -> bool:
    """Validate refresh query parameter."""
    return refresh


def validate_range_param(range: str = "7d") -> str:
    """Validate range query parameter."""
    valid_ranges = {"7d", "4w", "3m", "1y"}
    if range not in valid_ranges:
        raise ValueError(f"Invalid range. Must be one of: {', '.join(valid_ranges)}")
    return range


def validate_days_param(days: int = 30) -> int:
    """Validate days query parameter."""
    if days < 1 or days > 365:
        raise ValueError("Days must be between 1 and 365")
    return days
