#!/usr/bin/env python3
"""
Staking read-latency repro / pre-flight gate (P3-FIX3).

Deploy-6 failed live with reads blocking behind in-flight rescans
(504 / 57.6s / 12.7s, draining in scan order) while the offline suite was
green. This script stands up the REAL server (uvicorn, real routes, real
sqlite DB, real pacing/semaphores) with all EXTERNAL network faked, then
drives it over real HTTP:

  1. seeds a cloned DB with cardano wallets + warm staking cache rows
  2. starts a full refresh (mobile hard pull)
  3. TIMES concurrent no-refresh reads (mobile endpoint + per-address
     route) while the paced rescan runs
  4. fires a second refresh mid-flight and after completion, counting
     rescheduled scans

Exit code 0 = PASS (reads stay under READ_BUDGET_S throughout; the
post-completion refresh reschedules nothing). Non-zero = reproduction of
the deploy-6 failure. Run it as a pre-flight before staking deploys:

    ./venv/bin/python scripts/staking_read_latency_repro.py \
        --source-db data/portfolio.db

Mode --serve is internal (the spawned server process).
"""

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

PORT = int(os.environ.get("REPRO_PORT", "8177"))
DB_PATH_FOR_DRIVER = None
READ_BUDGET_S = 2.0
SCAN_SLEEP_S = 0.05  # per fake Blockfrost request — paced by the REAL bucket

PRICES = {
    "ADA": {"usd": 0.60}, "INDY": {"usd": 0.10},
    "LQ": {"usd": 0.19}, "IAG": {"usd": 0.02}, "STRIKE": {"usd": 0.02},
}

WARM_PROTOCOLS = {
    "Indigo": {"staked": [{"token": "INDY", "amount": 8670.38}],
               "total_positions": 1},
    "Liqwid": {"staked": [{"token": "LQ", "amount": 2089.17}],
               "total_positions": 1},
    "Iagon": {"staked": [{"token": "IAG", "amount": 3858.0}],
              "total_positions": 1},
}


# ---------------------------------------------------------------------------
# DB preparation
# ---------------------------------------------------------------------------

def prepare_db(source_db: Path, workdir: Path) -> Path:
    """Clone the source DB (APFS clonefile when possible) and warm the
    staking cache rows so reads have data to serve."""
    workdir.mkdir(parents=True, exist_ok=True)
    clone = workdir / "portfolio.db"
    if clone.exists():
        clone.unlink()
    try:
        subprocess.run(["cp", "-c", str(source_db), str(clone)], check=True)
    except subprocess.CalledProcessError:
        shutil.copyfile(source_db, clone)

    db = sqlite3.connect(clone)
    addrs = [r[0] for r in db.execute(
        "SELECT DISTINCT address FROM wallets WHERE blockchain='cardano'"
    ).fetchall()]
    # Warm rows: fresh for reads (expires in the future), but scanned long
    # enough ago that a hard pull legitimately triggers rescans
    cached_at = (datetime.now() - timedelta(hours=2)).isoformat()
    expires_at = (datetime.now() + timedelta(hours=22)).isoformat()
    for addr in addrs:
        payload = {
            "address": addr,
            "protocols": WARM_PROTOCOLS,
            "total_positions": 3,
            "confirmed_empty": [],
            "cached_at": cached_at,
            "from_cache": False,
        }
        db.execute(
            "INSERT OR REPLACE INTO cache (user_id, key, value, expires_at) "
            "VALUES (1, ?, ?, ?)",
            (f"staking_positions_{addr}", json.dumps(payload), expires_at),
        )
    # Warm token metadata like production (cold metadata makes every read
    # pay a fake-network fallback per position and skews the measurement)
    for sym in ("INDY", "LQ", "IAG", "ADA", "STRIKE"):
        db.execute(
            "INSERT OR REPLACE INTO token_metadata_cache (symbol, name, image_url) "
            "VALUES (?, ?, ?)",
            (sym, sym.title(), f"https://img.example/{sym.lower()}.png"),
        )
    db.commit()
    db.close()
    print(f"[repro] DB ready: {clone} ({len(addrs)} cardano wallets warmed)")
    return clone


# ---------------------------------------------------------------------------
# Server mode: patch config + network, run the REAL app
# ---------------------------------------------------------------------------

def serve(db_path: str):
    # Local harness only: no auth so the driver can hit endpoints as user 1
    os.environ["ABCT_REQUIRE_AUTH"] = "false"

    import config
    config.DATABASE_PATH = Path(db_path)

    import database
    database.DATABASE_PATH = Path(db_path)

    # --- Fake ALL external network; keep pacing/semaphores/DB REAL ---
    import services.http_client as http_client

    class FakeResponse:
        def __init__(self, status_code=404, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text or (json.dumps(payload) if payload is not None else "")

        def json(self):
            return self._payload

    STRIKE_PAGE = [{"amount": [], "tx_hash": "x", "output_index": 0}] * 100

    async def fake_blockfrost_once(path, method="GET", timeout=30.0, **kwargs):
        # Simulated upstream latency; the REAL bucket paces callers
        await asyncio.sleep(SCAN_SLEEP_S)
        if path.startswith("/accounts/") and path.count("/") == 2:
            return FakeResponse(200, {
                "stake_address": path.rsplit("/", 1)[-1], "active": True,
                "controlled_amount": "1000000000", "rewards_sum": "0",
                "withdrawable_amount": "0", "pool_id": "pool1fake",
            })
        if "/utxos" in path:
            page = (kwargs.get("params") or {}).get("page", 1)
            # Full pages keep the Strike scan fetching its whole window —
            # realistic scan volume (~15 paced requests per wallet)
            if page <= 15:
                return FakeResponse(200, STRIKE_PAGE)
            return FakeResponse(404, text="no page")
        return FakeResponse(404, text="fake: not found")

    http_client._blockfrost_fetch_once = fake_blockfrost_once

    class FakeClient:
        async def get(self, url, **kwargs):
            await asyncio.sleep(0.02)
            return FakeResponse(404, text="fake client")

        async def post(self, url, **kwargs):
            await asyncio.sleep(0.02)
            return FakeResponse(404, text="fake client")

        async def request(self, *a, **k):
            await asyncio.sleep(0.02)
            return FakeResponse(404, text="fake client")

    http_client.get_client = lambda *a, **k: FakeClient()

    from services.pricing import pricing_service

    async def fake_prices():
        return PRICES

    pricing_service.get_all_tracked_prices = fake_prices

    import main  # noqa: E402  (imports routers with patched deps)

    # Debug probe so the driver can count in-flight/scheduled scans
    import routers.defi as defi_router

    async def staking_tasks_probe():
        bucket = http_client._blockfrost_bucket
        return {
            "in_flight": sorted(defi_router._staking_refresh_tasks.keys()),
            "bucket_tokens": bucket.tokens,
            "bucket_deficit_s": max(0.0, -bucket.tokens) / bucket.refill,
        }

    main.app.add_api_route("/debug/staking-tasks", staking_tasks_probe,
                           methods=["GET"])

    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=PORT, log_level="warning")


# ---------------------------------------------------------------------------
# Driver mode
# ---------------------------------------------------------------------------

async def drive() -> int:
    import httpx

    base = f"http://127.0.0.1:{PORT}"
    failures = []

    async with httpx.AsyncClient(timeout=70) as client:
        # Wait for the server
        for _ in range(120):
            try:
                r = await client.get(f"{base}/health")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        else:
            print("[repro] server never became healthy")
            return 2

        warm = (await client.get(f"{base}/api/mobile/defi/staking")).json()
        print(f"[repro] warm read OK: {len(warm.get('positions', []))} positions")
        # A per-address route read goes through the DB only (no Blockfrost)
        import sqlite3 as _sq
        _db = _sq.connect(DB_PATH_FOR_DRIVER)
        one_addr = _db.execute(
            "SELECT address FROM wallets WHERE blockchain='cardano' LIMIT 1"
        ).fetchone()[0]
        _db.close()

        # 1. Fire the hard pull (async refresh contract: should return fast)
        t0 = time.monotonic()
        r = await client.get(f"{base}/api/mobile/defi/staking?refresh=true")
        trigger_s = time.monotonic() - t0
        print(f"[repro] refresh trigger: {trigger_s:.2f}s "
              f"refreshing={r.json().get('refreshing')}")
        if trigger_s > 30:
            failures.append(f"refresh trigger took {trigger_s:.1f}s")

        tasks_now = (await client.get(f"{base}/debug/staking-tasks")).json()
        scans_round1 = len(tasks_now["in_flight"])
        print(f"[repro] scans in flight: {scans_round1}")

        # 2. Time no-refresh reads WHILE the paced rescan runs.
        # Mobile endpoint AND the per-address route are timed separately to
        # separate DB-path latency from anything upstream-facing.
        worst_read = 0.0
        worst_route_read = 0.0
        reads = []
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            t = time.monotonic()
            try:
                resp = await asyncio.wait_for(
                    client.get(f"{base}/api/mobile/defi/staking"), timeout=10)
                dt = time.monotonic() - t
                ok = resp.status_code == 200 and resp.json().get("positions")
            except asyncio.TimeoutError:
                dt = 10.0
                ok = False
                failures.append("mobile read timed out (>10s)")
            reads.append(dt)
            worst_read = max(worst_read, dt)

            t = time.monotonic()
            try:
                r2 = await asyncio.wait_for(
                    client.get(f"{base}/api/defi/staking/{one_addr}"), timeout=10)
                dt2 = time.monotonic() - t
            except asyncio.TimeoutError:
                dt2 = 10.0
            worst_route_read = max(worst_route_read, dt2)

            probe = (await client.get(f"{base}/debug/staking-tasks")).json()
            if dt > READ_BUDGET_S or dt2 > READ_BUDGET_S:
                print(f"[repro] SLOW mobile={dt:.2f}s route={dt2:.2f}s "
                      f"bucket_deficit={probe['bucket_deficit_s']:.1f}s "
                      f"at t+{time.monotonic()-t0:.0f}s")
            if not ok:
                failures.append("mobile read failed or empty during scan")
            # 2b. Second refresh mid-flight must JOIN, not re-schedule
            if len(reads) == 5:
                await client.get(f"{base}/api/mobile/defi/staking?refresh=true")
                tasks_mid = (await client.get(f"{base}/debug/staking-tasks")).json()
                if len(tasks_mid["in_flight"]) > scans_round1:
                    failures.append(
                        f"mid-flight refresh grew scans: {scans_round1} -> "
                        f"{len(tasks_mid['in_flight'])}")
            tasks_now = (await client.get(f"{base}/debug/staking-tasks")).json()
            if not tasks_now["in_flight"] and len(reads) > 5:
                break
            await asyncio.sleep(1.0)

        print(f"[repro] reads during scan: n={len(reads)} "
              f"worst mobile={worst_read:.2f}s worst per-address route="
              f"{worst_route_read:.2f}s p50={sorted(reads)[len(reads)//2]:.2f}s")
        if worst_read > READ_BUDGET_S:
            failures.append(f"worst read {worst_read:.2f}s > {READ_BUDGET_S}s budget")

        # 3. Refresh AFTER completion: per-wallet cooldown must not
        #    reschedule wallets that just finished scanning
        for _ in range(60):
            tasks_now = (await client.get(f"{base}/debug/staking-tasks")).json()
            if not tasks_now["in_flight"]:
                break
            await asyncio.sleep(1.0)
        await client.get(f"{base}/api/mobile/defi/staking?refresh=true")
        tasks_after = (await client.get(f"{base}/debug/staking-tasks")).json()
        rescheduled = len(tasks_after["in_flight"])
        print(f"[repro] post-completion refresh rescheduled: {rescheduled} scans")
        if rescheduled > 0:
            failures.append(
                f"post-completion refresh rescheduled {rescheduled} scans "
                f"(cooldown must key on scan completion)")

    if failures:
        print("[repro] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[repro] PASS: reads bounded, cooldown holds")
    return 0


def main_entry():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", default=str(REPO / "data" / "portfolio.db"))
    parser.add_argument("--workdir", default="/tmp/staking-repro")
    parser.add_argument("--serve", metavar="DB", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.serve:
        serve(args.serve)
        return

    clone = prepare_db(Path(args.source_db), Path(args.workdir))
    global DB_PATH_FOR_DRIVER
    DB_PATH_FOR_DRIVER = str(clone)
    server = subprocess.Popen(
        [sys.executable, __file__, "--serve", str(clone)],
        cwd=str(REPO),
    )
    try:
        rc = asyncio.run(drive())
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    sys.exit(rc)


if __name__ == "__main__":
    main_entry()
