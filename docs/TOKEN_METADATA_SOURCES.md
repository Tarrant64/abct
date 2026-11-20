# Cardano native-token metadata and logo sources

Implemented in `backend/services/cardano_token_meta.py`, served by `backend/routers/token_logos.py`.

## Chain (first hit wins per field)

| # | Source | Gives | Notes |
|---|---|---|---|
| 1 | Cardano Foundation Token Registry (`tokens.cardano.org/metadata/{policy}{namehex}`, CIP-26) | name, ticker, decimals, base64 logo | free, no key; HTTP 204 = not registered |
| 2 | Blockfrost `/assets/{id}` (registry block + CIP-25 / CIP-68 on-chain metadata) | name, ticker, decimals, logo or image (IPFS / Arweave / https) | needs `BLOCKFROST_API_KEY` (skipped when unset) |
| 3 | Koios `asset_info` (token_registry_metadata, CIP-25 minting metadata, CIP-68 datum) | same | free public tier, rate limited |
| 4 | `token_metadata_cache` (CoinGecko, by ticker) | `coingecko_id`, name, image | last resort for the image, also supplies `coingecko_id` |

Skipped: TapTools (key is configured but it has no logo/metadata endpoint worth a call), DexScreener (no reliable Cardano image), NMKR proxy (key not configured). LogoKit and Logostream are NOT part of this chain; see "LogoKit and Logostream" below.

## Caching

- Metadata rows: table `cardano_token_meta`. Found 7 days, nothing found ("empty") 6 hours, all sources errored 15 minutes.
- Logos: table `cardano_token_logo`, normalised PNG (<= 128 px, a few KB), 30 days.
- List endpoints read the cache only (never block on the network). Unknown tokens are queued for background resolution (4 at a time, de-duplicated).

## Serving

- `GET /api/mobile/token-logo/{policy_id}/{asset_name_hex}`: PNG, `ETag`, `Cache-Control: private, max-age=86400`, 404 when no logo, `verify_session`.
- `GET /api/mobile/token-meta/{policy_id}/{asset_name_hex}`: name, ticker, decimals, coingecko_id, sources, `verify_session`.
- Lists (`/wallets/id/{id}/assets`, `/portfolio/all-holdings` assets, `/api/mobile/wallets/{id}` tokens) carry `logo_url` as the relative path above (never a `data:` URL), plus `policy_id`, `asset_name_hex` (TapTools links), `coingecko_id`, `meta_ticker`, `meta_name`, `meta_decimals`.

## Safety

Images are fetched over https only from an allowlist of hosts (IPFS gateways, Arweave, a few CDNs), no userinfo or custom ports, redirects re-validated per hop, body capped at 2 MB while streaming, content type must be `image/*` (not SVG), and the bytes must decode in Pillow (pixel cap). Registry base64 is size-capped and decoded the same way.

## LogoKit and Logostream (web only, majors only)

Both services have keys in Settings > API keys (DB-backed; env `LOGOKIT_API_KEY` / `LOGOSTREAM_API_KEY` are fallbacks). They are deliberately **not** in the stored chain above:

- **Terms.** LogoKit (terms 2.2-2.4) requires hotlinking; scraping/caching/serving from your own server is Enterprise-only. Logostream (terms 2.3/2.4) allows only end-user (browser) caching and treats any backend/proxy/CDN storage as "shared caching" (Enterprise-only); bulk enumeration of identifier-to-logo mappings is prohibited. The free Community plans also require attribution, and Logostream counts every request against 20K/month.
- **Symbol-only lookup.** Neither has policy-id/contract lookup, so Cardano native tokens cannot be matched and obscure tickers would collide with the wrong logo.

How they are used instead:
- Backend never fetches, stores, proxies or emits their URLs (no `/api/mobile/*` payload contains one; `/images/token/{symbol}` 404s rather than redirecting).
- `GET /api/config/public` (session required) returns `logokit_token`, `logostream_key` and the `logo_majors` allowlist (`services/logokit_service.py: MAJOR_SYMBOLS`); all empty when no key is set.
- `frontend/js/logos.js` builds `img.logokit.com/crypto/{SYM}?token=...` for majors in the browser; if that image errors it tries `api.logostream.dev/cryptos/{SYM}?key=...` (so Logostream traffic is minimal), then a local letter placeholder.
- Web footers carry the required attribution. README credit retained.

Keys: add or change them in the web UI under Settings > API keys (stored in the DB, survives deploys because the deploy script keeps the data volume); no container env change is needed.
