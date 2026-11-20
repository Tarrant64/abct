"""LogoKit / Logostream: web-only, majors-only, hotlink-only (no server-side use)."""
import asyncio
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import services.api_key_manager as akm  # noqa: E402
from services.logokit_service import LogoKitService, MAJOR_SYMBOLS, is_major  # noqa: E402
from services.logostream import LogostreamService  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _patch_db_key(monkeypatch, value):
    async def fake(api_name, user_id=None):
        return value
    monkeypatch.setattr(akm, "get_api_key", fake)


def test_logokit_key_read_from_db_first(monkeypatch):
    _patch_db_key(monkeypatch, "db-key")
    monkeypatch.setenv("LOGOKIT_API_KEY", "env-key")
    assert run(LogoKitService().get_public_token()) == "db-key"


def test_logokit_key_falls_back_to_env(monkeypatch):
    _patch_db_key(monkeypatch, "")
    monkeypatch.setenv("LOGOKIT_API_KEY", "env-key")
    assert run(LogoKitService().get_public_token()) == "env-key"


def test_keyless_returns_empty(monkeypatch):
    _patch_db_key(monkeypatch, "")
    monkeypatch.delenv("LOGOKIT_API_KEY", raising=False)
    monkeypatch.delenv("LOGOSTREAM_API_KEY", raising=False)
    assert run(LogoKitService().get_public_token()) == ""
    assert run(LogostreamService().get_public_key()) == ""
    assert run(LogostreamService().is_configured()) is False


def test_majors_allowlist():
    for s in ("BTC", "eth", " ADA ", "USDC"):
        assert is_major(s)
    # Cardano native tokens / obscure tickers must never match (ticker collisions)
    for s in ("SNEK", "INDY", "HOSKY", "MIN", "", None, "BTC/../x"):
        assert not is_major(s)
    assert "SNEK" not in MAJOR_SYMBOLS


def test_services_have_no_url_builders_or_fetchers():
    for svc in (LogoKitService(), LogostreamService()):
        for name in ("get_crypto_logo_url", "get_token_logo_url", "get_blockchain_logo_url",
                     "get_token_logo", "search_token"):
            assert not hasattr(svc, name), f"{type(svc).__name__}.{name} would allow server-side use"


def test_no_logo_api_urls_in_backend_code():
    """Backend never emits or fetches img.logokit.com / logostream logo URLs."""
    allowed = {"logokit_service.py", "logostream.py", "api_health.py", "settings.py", "main.py"}
    pat = re.compile(r"img\.logokit\.com|logostream\.dev/api/logo|logokit_service\.get_")
    offenders = []
    for p in BACKEND.rglob("*.py"):
        if "venv" in p.parts or p.name in allowed or "tests" in p.parts:
            continue
        if pat.search(p.read_text(errors="ignore")):
            offenders.append(str(p.relative_to(BACKEND)))
    assert offenders == []


def test_mobile_router_has_no_logokit_reference():
    src = (BACKEND / "routers" / "mobile.py").read_text()
    assert "logokit" not in src.lower().replace("metadata_cache", "")


def test_images_router_does_not_redirect_to_logokit():
    src = (BACKEND / "routers" / "images.py").read_text()
    assert "RedirectResponse" not in src and "logokit_service" not in src


def test_logostream_health_uses_documented_crypto_endpoint():
    from services.api_health import API_HEALTH_TESTS
    kind, url = API_HEALTH_TESTS["logostream"][:2]
    assert kind == "query"
    assert url.startswith("https://api.logostream.dev/cryptos/") and "{key}" in url


def test_config_public_requires_session():
    import main
    from auth_utils import verify_session
    route = next(r for r in main.app.routes if getattr(r, "path", "") == "/api/config/public")
    deps = [d.call for d in route.dependant.dependencies]
    assert verify_session in deps


def test_config_public_returns_keys_and_majors(monkeypatch):
    import main
    import services.logokit_service as lk
    import services.logostream as ls

    async def k1(self, user_id=1): return "lk"
    async def k2(self, user_id=1): return "ls"
    monkeypatch.setattr(akm.APIKeyManager, "get_api_key", k1)
    out = run(main.public_config(_user_id=1))
    assert out["logokit_token"] == "lk" and out["logostream_key"] == "lk"
    assert "BTC" in out["logo_majors"] and "SNEK" not in out["logo_majors"]


def test_config_public_empty_when_no_keys(monkeypatch):
    import main

    async def none(self, user_id=1): return ""
    monkeypatch.setattr(akm.APIKeyManager, "get_api_key", none)
    out = run(main.public_config(_user_id=1))
    assert out == {"logokit_token": "", "logostream_key": "", "logo_majors": []}
