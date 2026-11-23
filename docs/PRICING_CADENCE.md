# Price refresh cadence

Goal: reliable prices on the CoinGecko free/demo plan with NO key, without
spamming the API. All CoinGecko traffic passes through one gate
(`backend/services/coingecko_gate.py`); spot-price cadence lives in
`backend/services/pricing.py`.

## How it works
- **Scheduled refresh**: one batched `/coins/markets` call for every tracked id
  (`ASSET_TO_COINGECKO`, ~70 ids, one page) every `PRICE_REFRESH_MINUTES`
  (default 30; 10 when a CoinGecko key is configured). First run is staggered
  30-120 s after start.
- **On demand** (app open, pull-to-refresh, web refresh): refreshes only if a
  symbol is older than 5 min AND the last refresh attempt is at least
  `PRICE_ON_DEMAND_MIN_AGE` old AND the hourly cap allows. Otherwise the cached
  snapshot is served. Concurrent callers coalesce on one in-flight refresh.
- **Fallbacks** (CMC, Coinbase, CoinPaprika, DefiLlama) run inside the same
  refresh slot, so they obey the same age, cap and coalescing.
- **429**: never retried in-request. `Retry-After` is honoured, then backoff
  2 -> 4 -> 8 -> 15 min (cap). During backoff no CoinGecko call is made and
  fallbacks fill in.
- **Gate limits**: `PRICE_CG_CALLS_PER_MIN` (default 8) and
  `PRICE_CG_DAILY_BUDGET` (default 300, about 9k/month); over-budget calls get a
  local 429 and use fallbacks/cache.
- **Charts/history**: market_chart/ohlc for 1 day are cached 30 min, longer
  ranges and `/history` 24 h, sparklines and top-N lists 1 h, coin metadata 24 h
  (gate cache, keyed by full URL, in-flight de-duplicated). Each refresh also
  stores a row per symbol in `price_snapshots` (35-day retention).
- **API key**: DB-stored API setting named `coingecko`. Demo keys go in
  `x-cg-demo-api-key` on api.coingecko.com, Pro keys (`CG-` + 32 chars or more)
  in `x-cg-pro-api-key` on pro-api.coingecko.com. Applied by the gate to every
  CoinGecko request.
- **Payload fields** (additive): `prices_as_of` (UTC ISO of the last refresh
  that produced prices) and `price_refresh_backing_off` on the mobile summary,
  all-holdings and web portfolio summary.
- **Logs**: every 15 min `coingecko 15m stats: calls=.. 429=.. blocked_*=..
  fallback_use=.. ondemand_served=.. ondemand_declined=.. scheduled=..`.
- **Price alerts** are evaluated against the latest snapshot, so they can lag
  up to the refresh interval until push notifications exist.

## Knobs
| Variable | Default | Meaning |
|---|---|---|
| `PRICE_REFRESH_MINUTES` | 30 (10 with key) | scheduled refresh interval |
| `PRICE_ON_DEMAND_MIN_AGE` | 300 | min seconds between refresh attempts |
| `PRICE_ON_DEMAND_MAX_PER_HOUR` | 12 | on-demand refresh cap |
| `PRICE_CG_CALLS_PER_MIN` | 8 | gate token ceiling |
| `PRICE_CG_DAILY_BUDGET` | 300 | gate daily soft budget |
