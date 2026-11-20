"""verify_admin accepts the admin's normal session login (no HTTP Basic).

Admin = user id 1, non-demo (the users table has no role/is_admin column).
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import middleware.auth as mauth  # noqa: E402
import routers.security as security  # noqa: E402
import routers.nfts as nfts  # noqa: E402

FUTURE = (datetime.utcnow() + timedelta(days=20)).isoformat()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, is_demo BOOLEAN DEFAULT 0)")
    con.executemany("INSERT INTO users VALUES (?,?,?)",
                    [(1, "owner", 0), (2, "demo", 1), (3, "other", 0)])
    con.commit()
    con.close()
    monkeypatch.setattr(mauth, "DATABASE_PATH", str(db))

    sessions = {
        "adm": {"user_id": 1, "is_demo": 0, "expires_at": FUTURE},
        "dem": {"user_id": 2, "is_demo": 1, "expires_at": FUTURE},
        "oth": {"user_id": 3, "is_demo": 0, "expires_at": FUTURE},
    }

    async def get_session(token):
        return sessions.get(token)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(database, "get_session", get_session)
    monkeypatch.setattr(database, "cleanup_expired_sessions", noop)
    monkeypatch.setattr(database, "renew_session", noop)

    app = FastAPI()

    @app.post("/admin-only")
    async def admin_only(who: str = Depends(mauth.verify_admin)):
        return {"who": who}

    return TestClient(app, raise_server_exceptions=False)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_admin_session_ok(client, monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    r = client.post("/admin-only", headers=_h("adm"))
    assert r.status_code == 200 and r.json()["who"] == "owner"


def test_non_admin_403(client, monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    assert client.post("/admin-only", headers=_h("oth")).status_code == 403


def test_demo_403(client, monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    assert client.post("/admin-only", headers=_h("dem")).status_code == 403


def test_no_token_401(client, monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    assert client.post("/admin-only").status_code == 401


def test_bad_token_401(client, monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    assert client.post("/admin-only", headers=_h("nope")).status_code == 401


def test_basic_credentials_no_longer_accepted(client, monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    monkeypatch.setenv("ABCT_ADMIN_USER", "u")
    monkeypatch.setenv("ABCT_ADMIN_PASSWORD", "p")
    r = client.post("/admin-only", auth=("u", "p"))
    assert r.status_code == 401


@pytest.mark.parametrize("hdr", [None, "dem", "oth", "adm"])
def test_auth_off_unchanged(client, monkeypatch, hdr):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "false")
    r = client.post("/admin-only", headers=_h(hdr) if hdr else None)
    assert r.status_code == 200 and r.json()["who"] == "localhost"


def _verify_admin_routes():
    out = []
    for router in (security.router, nfts.router):
        for r in router.routes:
            for dep in r.dependencies:
                if dep.dependency is mauth.verify_admin:
                    out.append((sorted(r.methods)[0], r.path))
    return out


def test_ten_admin_routes_use_new_verify_admin():
    assert len(_verify_admin_routes()) == 10


def test_security_router_uses_real_verify_admin():
    assert security.verify_admin is mauth.verify_admin
    assert not hasattr(security, "AUTH_AVAILABLE")
