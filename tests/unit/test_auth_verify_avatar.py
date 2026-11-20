"""/auth/verify returns username + is_demo (for the UI avatar), never secrets."""

import os
import sys
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from routers import auth  # noqa: E402


def _client(monkeypatch, session):
    async def fake_cleanup():
        return None

    async def fake_get_session(_token):
        return session

    async def fake_renew(*_a, **_k):
        return None

    monkeypatch.setattr(auth, "cleanup_expired_sessions", fake_cleanup)
    monkeypatch.setattr(auth, "get_session", fake_get_session)
    monkeypatch.setattr(auth, "renew_session", fake_renew)
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


def _session(username, is_demo):
    return {
        "username": username,
        "is_demo": is_demo,
        "expires_at": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        "token": "x",
    }


def test_verify_returns_username_and_demo_flag(monkeypatch):
    c = _client(monkeypatch, _session("demo", 1))
    body = c.get("/auth/verify", params={"token": "t"}).json()
    assert body == {"valid": True, "username": "demo", "is_demo": True}


def test_verify_non_demo_has_no_secrets(monkeypatch):
    c = _client(monkeypatch, _session("alice", 0))
    body = c.get("/auth/verify", params={"token": "t"}).json()
    assert body["username"] == "alice" and body["is_demo"] is False
    assert set(body) == {"valid", "username", "is_demo"}


def test_verify_invalid_token(monkeypatch):
    c = _client(monkeypatch, None)
    assert c.get("/auth/verify", params={"token": "t"}).json()["valid"] is False
