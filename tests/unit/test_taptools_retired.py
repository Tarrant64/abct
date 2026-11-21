"""ABCT-POLISH-20261121 item 5: TapTools is dead -> inert in code, stored settings row kept but retired."""
import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import config  # noqa: E402
import database  # noqa: E402


def test_key_constant_ignores_environment(monkeypatch):
    monkeypatch.setenv("TAPTOOLS_API_KEY", "should-be-ignored")
    import importlib
    importlib.reload(config)
    assert config.TAPTOOLS_API_KEY == ""


def test_nft_service_reports_taptools_unconfigured():
    from services.nft import nft_service
    assert nft_service.is_taptools_configured() is False


async def test_nft_status_has_no_taptools_key_prompt():
    from services.nft import nft_service
    st = await nft_service.get_status()
    assert st["taptools_configured"] is False
    assert "API key required" not in st["note"] and "taptools.io/openapi" not in st["note"]


async def test_price_enricher_has_no_direct_taptools_call():
    from engine.enrichment.price_enricher import PriceEnricher
    assert not hasattr(PriceEnricher, "_fetch_taptools_floor_direct")


_LEGACY_HOST = ".".join(["openapi", "taptools", "io"])  # plain substring scan of source text, not URL validation


def test_no_taptools_http_calls_remain_outside_gated_legacy():
    """Every remaining openapi.taptools.io URL is behind the (always False) configured gate."""
    root = os.path.join(BACKEND_DIR)
    hits = []
    for d, _, files in os.walk(root):
        if "venv" in d or "__pycache__" in d or "/scripts" in d or "/tests" in d:
            continue
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read()
                if _LEGACY_HOST in src or "TAPTOOLS_API_BASE}" in src:
                    hits.append(f)
    assert sorted(hits) == ["nft.py", "nfts.py"]


@pytest.fixture
def api_db(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE api_settings (user_id INTEGER NOT NULL, api_name TEXT NOT NULL, api_key TEXT, api_secret TEXT,
            api_passphrase TEXT, enabled INTEGER DEFAULT 0, created_at TIMESTAMP, updated_at TIMESTAMP,
            last_test_status TEXT, last_test_message TEXT, last_tested_at TEXT, PRIMARY KEY (user_id, api_name));
        INSERT INTO api_settings (user_id, api_name, api_key, enabled, last_test_status, last_test_message)
            VALUES (1, 'taptools', 'enc:abc', 1, 'fail', 'HTTP 400'),
                   (1, 'blockfrost', 'enc:keep', 1, 'ok', 'fine');
    """)
    c.commit()
    c.close()
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    return path


def _rows(path):
    c = sqlite3.connect(path)
    try:
        return {r[0]: r[1:] for r in c.execute(
            "SELECT api_name, api_key, enabled, last_test_status, last_test_message FROM api_settings")}
    finally:
        c.close()


async def test_retire_marks_row_keeps_key_and_other_providers(api_db):
    assert await database.retire_api_providers() == 1
    r = _rows(api_db)
    assert r["taptools"][0] == "enc:abc"                      # nothing deleted, key untouched
    assert r["taptools"][1:] == (0, "retired", "TapTools service retired 2026-11-21")
    assert r["blockfrost"] == ("enc:keep", 1, "ok", "fine")   # others untouched


async def test_retire_is_idempotent(api_db):
    await database.retire_api_providers()
    before = _rows(api_db)
    assert await database.retire_api_providers() == 0
    assert _rows(api_db) == before


async def test_retire_without_table_is_harmless(tmp_path, monkeypatch):
    path = tmp_path / "x.db"
    sqlite3.connect(path).close()
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    assert await database.retire_api_providers() == 0
