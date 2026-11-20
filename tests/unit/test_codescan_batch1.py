"""Tests for code-scanning batch 1: path validation, /auth/status errors, ReDoS bounds."""

import os
import sys
import time

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services import image_cache  # noqa: E402
from services.image_cache import ImageCacheService, is_safe_symbol  # noqa: E402
from services.logging_service import LogEntry, LogLevel  # noqa: E402


# --- image symbol validation -------------------------------------------------

@pytest.mark.parametrize("symbol", ["BTC", "ada", "WETH.e", "1INCH", "$ADA", "tBTC-v2", "SNEK_2", "₿TC"])
def test_legit_symbols_accepted(symbol):
    assert is_safe_symbol(symbol)


@pytest.mark.parametrize("symbol", ["", "..", "a..b", "../etc/passwd", "a/b", "a\\b", "x" * 65, "a\x00b", "a b"])
def test_unsafe_symbols_rejected(symbol):
    assert not is_safe_symbol(symbol)


async def test_cache_serves_legit_and_rejects_traversal(tmp_path, monkeypatch):
    svc = ImageCacheService()
    monkeypatch.setattr(svc, "_dir", tmp_path / "token_images")
    (tmp_path / "token_images").mkdir()
    (tmp_path / "token_images" / "btc.png").write_bytes(b"png")
    (tmp_path / "secret.png").write_bytes(b"secret")

    assert await svc.get_image_path("BTC") == str((tmp_path / "token_images" / "btc.png").resolve())
    assert await svc.get_image_path("../secret") is None
    assert await svc.get_image_path("..") is None
    assert await svc.cache_image("../evil", "http://example.invalid/x.png") is False
    assert not (tmp_path / "evil.png").exists()


# --- /next and /legacy page lookup -------------------------------------------

def test_safe_page_file(tmp_path):
    import main

    (tmp_path / "wallets.html").write_text("x")
    (tmp_path.parent / "outside.html").write_text("x")
    assert main._safe_page_file(tmp_path, "wallets") == str((tmp_path / "wallets.html").resolve())
    assert main._safe_page_file(tmp_path, "missing") is None
    assert main._safe_page_file(tmp_path, "../outside") is None
    assert main._safe_page_file(tmp_path, "..") is None
    assert main._safe_page_file(tmp_path, "a/b") is None
    assert main._safe_page_file(tmp_path, "") is None


def test_real_frontend_pages_resolve():
    import main

    for base in (main.v2_path, main.frontend_path):
        pages = [f[:-5] for f in os.listdir(base) if f.endswith(".html")]
        assert pages
        for name in pages:
            assert main._safe_page_file(base, name) is not None, name


# --- /auth/status error text -------------------------------------------------

async def test_auth_status_hides_exception_text(monkeypatch):
    from routers import auth

    async def _noop():
        return None

    def _boom(*a, **k):
        raise RuntimeError("secret-db-path /var/lib/x.db")

    monkeypatch.setattr(auth, "cleanup_expired_sessions", _noop)
    monkeypatch.setattr(auth.aiosqlite, "connect", _boom)
    result = await auth.auth_status()
    assert result["users_in_database"] == "unavailable"
    assert "secret" not in str(result)


# --- logging sanitizer ReDoS bounds ------------------------------------------

def _msg(text):
    return LogEntry(LogLevel.INFO, "t", text).message


def test_path_sanitizing_still_works():
    assert _msg("err in /home/u/app/backend/main.py") == "err in .../backend/main.py"
    assert _msg("x /opt/proj/frontend/a.js y") == "x .../frontend/a.js y"
    assert _msg("/srv/Deployment/x") == ".../Deployment/x"
    assert "C:" not in _msg(r"C:\Users\me\app\backend\x.py")


@pytest.mark.parametrize("prefix", ["/", "C:\\"])
def test_adversarial_input_finishes_quickly(prefix):
    text = prefix + ("a/" * 20000)  # many separators, never a backend/frontend segment
    start = time.perf_counter()
    _msg(text)
    assert time.perf_counter() - start < 5
