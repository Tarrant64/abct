"""
Cardano native-token metadata + logo resolver (multi-source fallback chain).

Why this exists
---------------
List payloads (wallet assets, all-holdings) used to embed whatever
`nmkr_service.get_token_logo_with_fallbacks` found: multi-hundred-KB
``data:image/png;base64`` URLs (registry logos), raw ``ipfs.io`` / ``ar://`` /
bare-CID image links (ipfs.io answers 403 to servers and phones alike) and
LogoKit URLs with an empty token (HTTP 401). None of those render in the
mobile app (https-only, 512 KB cap), so token rows showed a placeholder.

This module resolves each token ONCE, server-side, caches name / ticker /
decimals / logo, and serves a small normalised PNG through an authed endpoint
(`routers/token_logos.py`). Lists only carry a short relative path.

Source chain (first hit wins per field; see docs/TOKEN_METADATA_SOURCES.md)
---------------------------------------------------------------------------
1. Cardano Foundation Token Registry   tokens.cardano.org (CIP-26, off-chain, base64 logo)
2. Blockfrost asset metadata            registry `metadata` + `onchain_metadata`
                                        (CIP-25 / CIP-68, resolved by Blockfrost) - needs BLOCKFROST_API_KEY
3. Koios asset_info                     token_registry_metadata, CIP-25 minting metadata, CIP-68 datum (free, public)
4. token_metadata_cache                 CoinGecko-sourced image/name/coingecko_id, matched by ticker (last resort)

Caching: positive 7 days, "nothing found" 6 hours, "every source errored" 15 minutes.
Logo images are normalised (Pillow, <=128 px PNG) and stored as BLOBs for 30 days.

Security: logo bytes are only fetched over https from an allowlist of hosts
(IPFS gateways, Arweave, a few known CDNs), redirects are re-validated per hop,
the body is size-capped while streaming, the content type must be a raster
image and the bytes must decode with Pillow. Registry base64 is size-capped and
decoded the same way. Nothing token-supplied is fetched from an arbitrary host.
"""

import asyncio
import base64
import binascii
import hashlib
import io
import json
import logging
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiosqlite

from config import DATABASE_PATH
from services.http_client import get_client

logger = logging.getLogger(__name__)

# --- TTLs ---------------------------------------------------------------------
TTL_FOUND = 7 * 86400          # something useful was found
TTL_EMPTY = 6 * 3600           # every source answered, nothing found (negative)
TTL_ERROR = 15 * 60            # sources errored; retry soon
LOGO_TTL = 30 * 86400

# --- Limits -------------------------------------------------------------------
MAX_IMAGE_BYTES = 2 * 1024 * 1024      # raw download cap
MAX_B64_CHARS = 3 * 1024 * 1024        # registry base64 cap
LOGO_PX = 128
MAX_PIXELS = 24_000_000
MAX_REDIRECTS = 3
WARM_CONCURRENCY = 4

POLICY_RE = re.compile(r"^[0-9a-f]{56}$")
NAME_HEX_RE = re.compile(r"^(?:[0-9a-f]{2}){0,32}$")

REGISTRY_URL = "https://tokens.cardano.org/metadata"
KOIOS_URL = "https://api.koios.rest/api/v1/asset_info"

IPFS_GATEWAYS = [
    "https://gateway.pinata.cloud/ipfs/",
    "https://ipfs.blockfrost.dev/ipfs/",
    "https://ipfs.io/ipfs/",
]
ARWEAVE_GATEWAY = "https://arweave.net/"

# Exact hosts or suffixes (".host") that logo bytes may be fetched from.
ALLOWED_HOSTS = {
    "gateway.pinata.cloud", "ipfs.blockfrost.dev", "ipfs.io", "dweb.link", "w3s.link",
    "nftstorage.link", "arweave.net", "storage.cardanolands.com", "cdn.nmkr.io",
    "nmkr.io", "pbs.twimg.com", "raw.githubusercontent.com", "avatars.githubusercontent.com",
    "cryptologos.cc", "assets.coingecko.com", "coin-images.coingecko.com", "s2.coinmarketcap.com",
}
ALLOWED_SUFFIXES = (".ipfs.dweb.link", ".ipfs.w3s.link", ".ipfs.nftstorage.link", ".nmkr.io")

_table_ready = False
_inflight: Dict[str, "asyncio.Future"] = {}
_warm_sem: Optional[asyncio.Semaphore] = None
_warming: set = set()


# --- helpers ------------------------------------------------------------------

def split_asset_id(asset_id: str, policy_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """(policy, name_hex) from an `asset_id` (policy+namehex) or None,None if it is not a Cardano asset id."""
    a = (asset_id or "").strip().lower()
    p = (policy_id or a[:56]).strip().lower()
    if not POLICY_RE.match(p) or not a.startswith(p):
        return None, None
    n = a[len(p):]
    return (p, n) if NAME_HEX_RE.match(n) else (None, None)


def valid_ids(policy_id: str, name_hex: str) -> bool:
    return bool(POLICY_RE.match(policy_id or "")) and bool(NAME_HEX_RE.match(name_hex or ""))


def logo_path(policy_id: str, name_hex: str) -> str:
    return f"/api/mobile/token-logo/{policy_id}/{name_hex}"


def _decode_hex_name(name_hex: str) -> Optional[str]:
    try:
        s = bytes.fromhex(name_hex).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return s if s and all(c.isprintable() for c in s) else None


def host_allowed(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return False
    if u.port not in (None, 443):
        return False
    h = u.hostname.lower()
    return h in ALLOWED_HOSTS or h.endswith(ALLOWED_SUFFIXES)


def candidate_urls(ref: str) -> List[str]:
    """Turn a metadata image reference into fetchable https URLs (gateways tried in order)."""
    ref = (ref or "").strip()
    if not ref or len(ref) > 2048:
        return []
    if ref.startswith("ipfs://"):
        path = ref[len("ipfs://"):].lstrip("/")
        if path.lower().startswith("ipfs/"):
            path = path[5:]
        return [g + path for g in IPFS_GATEWAYS] if path else []
    if ref.startswith("ar://"):
        tx = ref[len("ar://"):].lstrip("/")
        return [ARWEAVE_GATEWAY + tx] if re.match(r"^[A-Za-z0-9_\-]{20,64}$", tx) else []
    if re.match(r"^(Qm[1-9A-HJ-NP-Za-km-z]{44}|b[a-z2-7]{50,})(/[\w.\-]+)*$", ref):
        return [g + ref for g in IPFS_GATEWAYS]
    if ref.startswith("https://"):
        return [ref] if host_allowed(ref) else []
    return []


def normalise_image(data: bytes) -> Optional[bytes]:
    """Decode with Pillow and re-encode as a small PNG (<=128 px). None if it is not a decodable raster image."""
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        im = Image.open(io.BytesIO(data))
        if im.width * im.height > MAX_PIXELS:
            return None
        im.seek(0)
        im = im.convert("RGBA")
        im.thumbnail((LOGO_PX, LOGO_PX))
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _b64_to_png(b64: str) -> Optional[bytes]:
    if not b64 or len(b64) > MAX_B64_CHARS:
        return None
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None
    if len(raw) > MAX_IMAGE_BYTES:
        return None
    return normalise_image(raw)


def _val(entry) -> Optional[str]:
    """Registry properties are {"value": ..., "signatures": [...]}; Blockfrost/Koios give plain values."""
    if isinstance(entry, dict):
        entry = entry.get("value")
    if entry is None:
        return None
    s = str(entry).strip()
    return s or None


def _join_image(v) -> Optional[str]:
    """CIP-25 images may be a string or a list of string chunks."""
    if isinstance(v, list):
        v = "".join(x for x in v if isinstance(x, str))
    return v.strip() if isinstance(v, str) and v.strip() else None


# --- DB -----------------------------------------------------------------------

async def _ensure_tables(db) -> None:
    global _table_ready
    if _table_ready:
        return
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cardano_token_meta (
            asset_id TEXT PRIMARY KEY,
            policy_id TEXT NOT NULL,
            name_hex TEXT NOT NULL,
            name TEXT,
            ticker TEXT,
            decimals INTEGER,
            coingecko_id TEXT,
            logo_ref TEXT,
            has_logo INTEGER DEFAULT 0,
            sources TEXT,
            status TEXT,
            checked_at REAL,
            expires_at REAL
        )""")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cardano_token_logo (
            asset_id TEXT PRIMARY KEY,
            png BLOB,
            etag TEXT,
            source TEXT,
            expires_at REAL
        )""")
    await db.commit()
    _table_ready = True


def _reset_for_tests() -> None:
    global _table_ready
    _table_ready = False
    _inflight.clear()
    _warming.clear()


async def get_cached_meta_bulk(asset_ids: List[str]) -> Dict[str, dict]:
    """Cache-only lookup (no network). Expired rows are returned too, flagged `expired`, so lists never block."""
    out: Dict[str, dict] = {}
    ids = [a for a in dict.fromkeys(asset_ids) if a]
    if not ids:
        return out
    now = time.time()
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            await _ensure_tables(db)
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                q = ",".join("?" * len(chunk))
                cur = await db.execute(f"SELECT * FROM cardano_token_meta WHERE asset_id IN ({q})", chunk)
                for r in await cur.fetchall():
                    d = dict(r)
                    d["expired"] = (d.get("expires_at") or 0) < now
                    out[d["asset_id"]] = d
    except Exception as e:
        logger.debug("token meta cache read failed: %s", e)
    return out


async def _save_meta(asset_id: str, policy: str, name_hex: str, meta: dict, status: str, ttl: int) -> None:
    now = time.time()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_tables(db)
        await db.execute("""
            INSERT INTO cardano_token_meta
                (asset_id, policy_id, name_hex, name, ticker, decimals, coingecko_id, logo_ref, has_logo, sources, status, checked_at, expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_id) DO UPDATE SET
                name=excluded.name, ticker=excluded.ticker, decimals=excluded.decimals, coingecko_id=excluded.coingecko_id,
                logo_ref=excluded.logo_ref, has_logo=excluded.has_logo, sources=excluded.sources, status=excluded.status,
                checked_at=excluded.checked_at, expires_at=excluded.expires_at
        """, (asset_id, policy, name_hex, meta.get("name"), meta.get("ticker"), meta.get("decimals"),
              meta.get("coingecko_id"), meta.get("logo_ref"), 1 if meta.get("has_logo") else 0,
              json.dumps(meta.get("sources") or []), status, now, now + ttl))
        await db.commit()


async def _save_logo(asset_id: str, png: bytes, source: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await _ensure_tables(db)
        await db.execute("""
            INSERT INTO cardano_token_logo (asset_id, png, etag, source, expires_at) VALUES (?,?,?,?,?)
            ON CONFLICT(asset_id) DO UPDATE SET png=excluded.png, etag=excluded.etag, source=excluded.source, expires_at=excluded.expires_at
        """, (asset_id, png, hashlib.sha256(png).hexdigest()[:32], source, time.time() + LOGO_TTL))
        await db.commit()


async def get_logo_blob(asset_id: str) -> Optional[Tuple[bytes, str]]:
    """(png, etag) for a fresh stored logo, else None."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await _ensure_tables(db)
            cur = await db.execute("SELECT png, etag, expires_at FROM cardano_token_logo WHERE asset_id=?", (asset_id,))
            row = await cur.fetchone()
    except Exception:
        return None
    if row and row[0] and (row[2] or 0) > time.time():
        return bytes(row[0]), row[1]
    return None


# --- sources (each returns a partial dict or None; all network lives here, so tests patch these) ---

async def fetch_registry(policy: str, name_hex: str) -> Optional[dict]:
    """Source 1: Cardano Foundation Token Registry (CIP-26). 204 = not registered."""
    client = get_client("cardano_token_registry", timeout=10)
    resp = await client.get(f"{REGISTRY_URL}/{policy}{name_hex}")
    if resp.status_code == 204:
        return {}
    if resp.status_code != 200:
        raise RuntimeError(f"registry status {resp.status_code}")
    d = resp.json()
    dec = _val(d.get("decimals"))
    return {
        "name": _val(d.get("name")), "ticker": _val(d.get("ticker")),
        "decimals": int(dec) if dec and dec.isdigit() else None,
        "logo_b64": _val(d.get("logo")),
    }


async def fetch_blockfrost(policy: str, name_hex: str) -> Optional[dict]:
    """Source 2: Blockfrost /assets/{id}: registry block and CIP-25 / CIP-68 on-chain metadata."""
    from services.cardano import cardano_service
    if not getattr(cardano_service, "blockfrost_api", None):
        return None  # not configured: skipped, not an error
    m = await cardano_service.get_asset_metadata(policy + name_hex)
    if m is None:
        return {}
    reg = m.get("registry_metadata") or {}
    on = m.get("onchain_metadata") or {}
    dec = reg.get("decimals", on.get("decimals"))
    return {
        "name": _val(reg.get("name")) or _val(on.get("name")),
        "ticker": _val(reg.get("ticker")) or _val(on.get("ticker")),
        "decimals": int(dec) if str(dec).isdigit() else None,
        "logo_b64": _val(reg.get("logo")),
        "image_ref": _join_image(on.get("logo")) or _join_image(on.get("image")),
    }


async def fetch_koios(policy: str, name_hex: str) -> Optional[dict]:
    """Source 3: Koios asset_info (registry block, CIP-25 mint metadata, CIP-68 datum). Public, rate limited."""
    client = get_client("koios_token_meta", timeout=15)
    resp = await client.post(KOIOS_URL, json={"_asset_list": [[policy, name_hex]]},
                             headers={"accept": "application/json"})
    if resp.status_code != 200:
        raise RuntimeError(f"koios status {resp.status_code}")
    rows = resp.json()
    if not rows:
        return {}
    r = rows[0]
    reg = r.get("token_registry_metadata") or {}
    c68 = r.get("cip68_metadata") or {}
    c68d = (c68.get("222") or c68.get("333") or c68.get("444") or {}) if isinstance(c68, dict) else {}
    c68f = c68d.get("fields") if isinstance(c68d, dict) else None
    mint = r.get("minting_tx_metadata") or {}
    c25 = {}
    try:
        c25 = ((mint.get("721") or {}).get(policy) or {}).get(_decode_hex_name(name_hex) or "", {}) or {}
    except AttributeError:
        c25 = {}
    on = c25 if isinstance(c25, dict) else {}
    if isinstance(c68f, dict):
        on = {**on, **{k: v for k, v in c68f.items() if k not in on}}
    dec = reg.get("decimals", on.get("decimals"))
    return {
        "name": _val(reg.get("name")) or _val(on.get("name")),
        "ticker": _val(reg.get("ticker")) or _val(on.get("ticker")),
        "decimals": int(dec) if str(dec).isdigit() else None,
        "logo_b64": _val(reg.get("logo")),
        "image_ref": _join_image(on.get("logo")) or _join_image(on.get("image")),
    }


async def fetch_cached_market(ticker: str) -> Optional[dict]:
    """Source 4: CoinGecko-derived token_metadata_cache row (image/name/coingecko_id) matched by ticker."""
    from services.token_metadata_cache import metadata_cache
    m = await metadata_cache.get_metadata(ticker)
    if not m:
        return {}
    return {"name": m.get("name"), "coingecko_id": m.get("coingecko_id"), "image_ref": m.get("image_url")}


async def fetch_image_bytes(url: str) -> Optional[bytes]:
    """Safe image download: https + allowlisted host per hop, no auto-redirects, size-capped stream, image/* only."""
    client = get_client("token_logo_fetch", timeout=15)
    cur = url
    for _ in range(MAX_REDIRECTS + 1):
        if not host_allowed(cur):
            return None
        async with client.stream("GET", cur, headers={"Accept": "image/*", "User-Agent": "abct-token-logo/1"},
                                 follow_redirects=False) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    return None
                from urllib.parse import urljoin
                cur = urljoin(cur, loc)
                continue
            if resp.status_code != 200:
                return None
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if not ctype.startswith("image/") or "svg" in ctype:
                return None
            try:
                if int(resp.headers.get("content-length") or 0) > MAX_IMAGE_BYTES:
                    return None
            except ValueError:
                pass
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_IMAGE_BYTES:
                    return None
            return bytes(buf)
    return None


# --- orchestration ------------------------------------------------------------

def _merge(into: dict, part: Optional[dict], source: str) -> None:
    if not part:
        return
    used = False
    for k in ("name", "ticker", "decimals", "coingecko_id", "logo_b64", "image_ref"):
        if part.get(k) not in (None, "") and into.get(k) in (None, ""):
            into[k] = part[k]
            used = True
    if used:
        into.setdefault("sources", []).append(source)


async def _resolve_logo_bytes(meta: dict) -> Tuple[Optional[bytes], Optional[str]]:
    """Registry base64 first (curated), then the on-chain / market image reference through safe gateways."""
    if meta.get("logo_b64"):
        png = _b64_to_png(meta["logo_b64"])
        if png:
            return png, "registry"
    for url in candidate_urls(meta.get("image_ref") or ""):
        try:
            raw = await fetch_image_bytes(url)
        except Exception as e:
            logger.debug("logo fetch failed for %s: %s", urlparse(url).hostname, e)
            continue
        if raw:
            png = normalise_image(raw)
            if png:
                return png, "onchain" if "coingecko" not in url and "coinmarketcap" not in url else "market"
    return None, None


async def resolve(policy: str, name_hex: str, force: bool = False) -> dict:
    """Run the full chain for one token, store and return the meta row. Concurrent callers share one run."""
    asset_id = policy + name_hex
    if not force:
        row = (await get_cached_meta_bulk([asset_id])).get(asset_id)
        if row and not row["expired"]:
            return row
    fut = _inflight.get(asset_id)
    if fut is not None:
        return await asyncio.shield(fut)
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _inflight[asset_id] = fut
    try:
        res = await _resolve_uncached(policy, name_hex)
        fut.set_result(res)
        return res
    except BaseException as e:  # noqa: BLE001 - propagate to waiters
        if not fut.done():
            fut.set_exception(e)
            fut.exception()  # mark retrieved
        raise
    finally:
        _inflight.pop(asset_id, None)


async def _resolve_uncached(policy: str, name_hex: str) -> dict:
    asset_id = policy + name_hex
    meta: dict = {"sources": []}
    errors = 0
    answered = 0
    for label, fn in (("registry", fetch_registry), ("blockfrost", fetch_blockfrost), ("koios", fetch_koios)):
        have_all = meta.get("name") and meta.get("ticker") and meta.get("decimals") is not None and (meta.get("logo_b64") or meta.get("image_ref"))
        if have_all:
            break
        try:
            part = await fn(policy, name_hex)
        except Exception as e:
            errors += 1
            logger.debug("token meta source %s failed: %s", label, e)
            continue
        if part is not None:
            answered += 1
        _merge(meta, part, label)
    if meta.get("ticker") and (not meta.get("coingecko_id") or not (meta.get("logo_b64") or meta.get("image_ref"))):
        try:
            part = await fetch_cached_market(meta["ticker"])
            _merge(meta, part, "market-cache")
        except Exception as e:
            logger.debug("market cache lookup failed: %s", e)
    if not meta.get("name"):
        decoded = _decode_hex_name(name_hex)
        if decoded and not name_hex.startswith(("000", "001", "002")):  # skip CIP-67 label prefixes
            meta["name"] = decoded

    png, src = await _resolve_logo_bytes(meta)
    if png is None and meta.get("logo_b64") and meta.get("image_ref"):
        pass  # already tried both inside _resolve_logo_bytes
    meta["has_logo"] = png is not None
    meta["logo_ref"] = (meta.get("image_ref") or ("registry" if png and src == "registry" else None))
    if png is not None:
        await _save_logo(asset_id, png, src or "unknown")

    found_any = bool(meta.get("has_logo") or meta.get("ticker") or meta.get("decimals") is not None or (meta.get("sources")))
    if errors and answered == 0 and not found_any:
        status, ttl = "error", TTL_ERROR
    elif found_any and (meta["has_logo"] or meta.get("ticker")):
        status, ttl = "found", TTL_FOUND
    elif errors and not meta["has_logo"]:
        status, ttl = "error", TTL_ERROR
    else:
        status, ttl = "empty", TTL_EMPTY
    meta["logo_ref"] = meta.get("logo_ref")
    await _save_meta(asset_id, policy, name_hex, meta, status, ttl)
    row = (await get_cached_meta_bulk([asset_id])).get(asset_id) or {}
    return row


# --- list enrichment (cache-only on the request path) ---------------------------

def _sem() -> asyncio.Semaphore:
    global _warm_sem
    if _warm_sem is None:
        _warm_sem = asyncio.Semaphore(WARM_CONCURRENCY)
    return _warm_sem


async def _warm_one(policy: str, name_hex: str) -> None:
    aid = policy + name_hex
    try:
        async with _sem():
            await resolve(policy, name_hex)
    except Exception as e:
        logger.debug("token warm failed: %s", e)
    finally:
        _warming.discard(aid)


def schedule_warm(pairs: List[Tuple[str, str]]) -> int:
    """Fire-and-forget resolution of unknown/expired tokens; bounded concurrency, deduplicated."""
    n = 0
    for policy, name_hex in pairs:
        aid = policy + name_hex
        if aid in _warming:
            continue
        _warming.add(aid)
        try:
            asyncio.get_running_loop().create_task(_warm_one(policy, name_hex))
            n += 1
        except RuntimeError:
            _warming.discard(aid)
    return n


def _bad(s) -> bool:
    return s is None or str(s).strip() in ("", "None", "none", "null", "Unknown", "UNKNOWN")


async def enrich_assets(assets: List[dict], schedule: bool = True, fill_ticker: bool = True) -> List[dict]:
    """
    Add `policy_id`, `asset_name_hex`, `logo_url` (relative server path), `coingecko_id`, `meta_decimals`, `meta_status`
    to Cardano native-asset dicts IN PLACE, filling a blank/"None" `ticker` / `token_name` from the cache.
    Cache-only: unknown tokens get the logo path optimistically (the endpoint resolves on demand) and are queued for warming.
    """
    parsed = []
    for a in assets:
        p, n = split_asset_id(a.get("asset_id", ""), a.get("policy_id"))
        parsed.append((a, p, n))
    rows = await get_cached_meta_bulk([p + n for _, p, n in parsed if p])
    to_warm: List[Tuple[str, str]] = []
    for a, p, n in parsed:
        if not p:
            continue
        aid = p + n
        r = rows.get(aid)
        a["policy_id"] = p
        a["asset_name_hex"] = n
        if r:
            if fill_ticker and _bad(a.get("ticker")) and r.get("ticker"):
                a["ticker"] = r["ticker"]
            if _bad(a.get("token_name")) and r.get("name"):
                a["token_name"] = r["name"]
            a["meta_ticker"] = r.get("ticker")
            a["meta_name"] = r.get("name")
            a["meta_decimals"] = r.get("decimals")
            a["coingecko_id"] = r.get("coingecko_id")
            a["meta_status"] = r.get("status")
        if r and r.get("has_logo"):
            a["logo_url"] = logo_path(p, n)
        elif r and not r.get("expired") and r.get("status") in ("empty", "found"):
            a["logo_url"] = None          # definitively no logo (negative cache)
        else:
            a["logo_url"] = logo_path(p, n)   # unknown yet: the endpoint resolves it
        if not r or r.get("expired"):
            to_warm.append((p, n))
    if schedule and to_warm:
        schedule_warm(to_warm)
    return assets
