"""
Browser-facing NFT image URLs (ABCT-NFT-DIAG2-2026-09-28).

NFT metadata usually points at IPFS, and ABCT used to hand the browser a
single ``https://ipfs.io/ipfs/<cid>`` URL. The public ipfs.io gateway now
answers hot-linked images with a Cloudflare challenge (HTTP 403/429), so every
Cardano (and the Algorand) NFT image failed to load and the NFT page's Gallery
Mode, which hides tiles whose image fails, showed only Ethereum NFTs.

``display_image_candidates()`` turns one metadata image URL into an ordered
list of URLs the browser may try: IPFS content is offered on every configured
gateway (``NFT_DISPLAY_IPFS_GATEWAYS``), anything else is passed through only
if it is ``https://`` or an inline ``data:image/`` URI. On-chain metadata is
attacker-controlled, so ``http://`` and other schemes are never handed out.
"""

import re
from typing import List, Optional
from urllib.parse import quote, unquote, urlsplit

try:
    from config import NFT_DISPLAY_IPFS_GATEWAYS
except Exception:  # pragma: no cover - config import problems must not break NFT lists
    NFT_DISPLAY_IPFS_GATEWAYS = ["https://ipfs.io/ipfs/"]

# CIDv0 (Qm + 44 base58 chars) or CIDv1 in base32 (bafy..., bafk..., bafb...)
_CID_RE = re.compile(r"^(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[a-z2-7]{20,})$")
# Characters left as-is in the path after the CID (file names inside a
# directory CID); everything else is percent-encoded.
_PATH_SAFE_CHARS = "/!$&'()*+,;=:@-._~"


def ipfs_path(url) -> Optional[str]:
    """Return ``<cid>[/path]`` if ``url`` refers to IPFS content, else None.

    Recognises ``ipfs://<cid>``, ``ipfs://ipfs/<cid>``, a bare CID, and any
    ``http(s)://<gateway>/ipfs/<cid>`` gateway URL.
    """
    if not isinstance(url, str):
        return None
    u = url.strip()
    if not u:
        return None
    lowered = u.lower()
    if lowered.startswith("ipfs://"):
        rest = u[7:]
        if rest.lower().startswith("ipfs/"):
            rest = rest[5:]
    elif lowered.startswith(("https://", "http://")):
        try:
            path = urlsplit(u).path
        except ValueError:
            return None
        if not path.startswith("/ipfs/"):
            return None
        rest = path[len("/ipfs/"):]
    else:
        rest = u
    rest = rest.lstrip("/")
    cid, _, sub = rest.partition("/")
    if not _CID_RE.match(cid):
        return None
    if sub:
        sub = sub.split("?", 1)[0].split("#", 1)[0]
        decoded = unquote(sub)
        if any(seg == ".." for seg in decoded.split("/")) or any(ord(ch) < 32 for ch in decoded):
            return None
        sub = quote(decoded, safe=_PATH_SAFE_CHARS)
    return cid + ("/" + sub if sub else "")


def _safe_passthrough(url) -> Optional[str]:
    if not isinstance(url, str) or not url.strip():
        return None
    u = url.strip()
    lowered = u.lower()
    if lowered.startswith("https://") or lowered.startswith("data:image/"):
        return u
    return None


def display_image_candidates(url, gateways: Optional[List[str]] = None) -> List[str]:
    """Ordered, de-duplicated list of browser-safe URLs for one NFT image."""
    gateways = NFT_DISPLAY_IPFS_GATEWAYS if gateways is None else gateways
    path = ipfs_path(url)
    candidates: List[str] = []
    if path:
        for g in gateways:
            if isinstance(g, str) and g.lower().startswith("https://"):
                candidates.append(g.rstrip("/") + "/" + path)
    else:
        safe = _safe_passthrough(url)
        if safe:
            candidates.append(safe)
    seen = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def attach_display_images(nft: dict, source_url) -> dict:
    """Set ``image_url`` (first candidate or None) and ``image_fallbacks`` on ``nft``."""
    candidates = display_image_candidates(source_url)
    nft["image_url"] = candidates[0] if candidates else None
    nft["image_fallbacks"] = candidates[1:]
    return nft
