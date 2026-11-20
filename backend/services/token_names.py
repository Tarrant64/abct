"""Display names for tokens that CoinGecko/metadata_cache may not know.

Shared by routers/mobile.py and routers/portfolio.py so every payload names a
token the same way. Resolution order for a holding's display name:
metadata_cache (registry/CoinGecko name) -> this table -> the ticker. The raw
`native_assets.asset_name` is NOT a name source: it is a wallet-side label
(hex-decoded asset name, or the 'ERC-20'/'SPL' placeholders) and made rows show
junk like "ERC-20".
"""

# Display names for tokens not in metadata_cache (CoinGecko top 250)
TOKEN_NAMES = {
    'INDY': 'Indigo',
    'LQ': 'Liqwid Finance',
    'STRIKE': 'Strike',
    'MIN': 'Minswap',
    'SUNDAE': 'SundaeSwap',
    'LENFI': 'Lenfi',
    'SNEK': 'Snek',
    'WMT': 'World Mobile',
    'MILK': 'MuesliSwap',
    'HUNT': 'Hunt',
    'HOSKY': 'Hosky',
    'NMKR': 'NMKR',
}


def resolve_token_display_name(symbol: str, metadata: dict = None, fallback: str = None) -> str:
    """Name for a token row: metadata name, then the static table, then the ticker."""
    sym = (symbol or '').strip()
    meta_name = (metadata or {}).get('name') if isinstance(metadata, dict) else None
    if meta_name and str(meta_name).strip():
        return str(meta_name).strip()
    known = TOKEN_NAMES.get(sym.upper())
    if known:
        return known
    return sym or (fallback or '')
