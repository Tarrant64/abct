"""
Display-name helpers for NFTs (pure functions, no network or DB access).

Cardano NFT dicts carry no ``name`` of their own. The best source is the
CIP-25 on-chain metadata ``name`` (captured when the image URL is resolved);
otherwise the asset name (hex on-chain) decoded as UTF-8 is a usable label.
On-chain metadata is attacker-controlled, so every value is coerced to a
bounded, control-character-free string before it is shown anywhere.
"""
import re
from typing import Any, Optional

MAX_NAME_LEN = 200

# Values that older code (or upstream APIs) used as "no name" markers.
_PLACEHOLDERS = frozenset({'unknown', 'unknown collection', 'none', 'null', 'undefined'})

_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f-\x9f]')
# Legacy CIP-68 label prefix: 4 bytes = 0x000NNNN0 (e.g. 000de140 = label 222)
_CIP68_PREFIX_RE = re.compile(r'^000[0-9a-f]{4}0', re.IGNORECASE)


def clean_display_text(value: Any) -> Optional[str]:
    """Coerce a metadata value (str, or list of str chunks) to clean text or None."""
    if isinstance(value, list):
        if not all(isinstance(p, str) for p in value):
            return None
        value = ''.join(value)
    if not isinstance(value, str):
        return None
    text = _CONTROL_RE.sub('', value).strip()
    if not text or text.lower() in _PLACEHOLDERS:
        return None
    return text[:MAX_NAME_LEN]


def name_from_metadata(metadata: Any) -> Optional[str]:
    """CIP-25 ``name`` (falling back to ``title``/``displayName``) from a metadata dict."""
    if not isinstance(metadata, dict):
        return None
    for key in ('name', 'title', 'displayName'):
        text = clean_display_text(metadata.get(key))
        if text:
            return text
    return None


def decode_asset_name(asset_name_hex: Any) -> Optional[str]:
    """Decode a hex asset name as printable UTF-8, or None if it is not text."""
    if not isinstance(asset_name_hex, str) or not asset_name_hex:
        return None
    hex_str = asset_name_hex.strip()
    if len(hex_str) % 2 or not re.fullmatch(r'[0-9a-fA-F]+', hex_str):
        return None
    if _CIP68_PREFIX_RE.match(hex_str):
        hex_str = hex_str[8:]  # drop the 4-byte CIP-67 label
        if not hex_str:
            return None
    try:
        text = bytes.fromhex(hex_str).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return None
    if not text.strip() or not text.isprintable():
        return None
    return text.strip()[:MAX_NAME_LEN]


def resolve_cardano_name(nft: dict) -> Optional[str]:
    """Best display name for a Cardano NFT dict, or None.

    Order: stored/on-chain metadata name, decoded asset name from hex,
    the raw ``asset_name`` field (if it is clean text), else None.
    """
    if not isinstance(nft, dict):
        return None
    name = clean_display_text(nft.get('name'))
    if name:
        return name
    hex_name = nft.get('asset_name_hex')
    if not hex_name:
        asset_id = nft.get('asset_id') or ''
        hex_name = asset_id[56:] if len(asset_id) > 56 else ''
    name = decode_asset_name(hex_name)
    if name:
        return name
    raw = nft.get('asset_name')
    if isinstance(raw, str) and raw.isprintable():
        return clean_display_text(raw)
    return None


def clean_name(value: Any) -> Optional[str]:
    """Name for non-Cardano chains: the service-provided name or None (never 'Unknown')."""
    return clean_display_text(value)


def clean_collection(nft: dict) -> Optional[str]:
    """Collection name from an NFT dict (dict or str form) or None (never 'Unknown Collection')."""
    coll = nft.get('collection') if isinstance(nft, dict) else None
    if isinstance(coll, dict):
        coll = coll.get('name')
    return clean_display_text(coll)
