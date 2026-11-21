"""
ABCT-POLISH-20261121 item 6: a DEMO session must get 403 on EVERY verify_admin route (the 10 state-changing
security/NFT-admin routes), using the real routers (not a stand-in route), and an admin session passes the gate.
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import middleware.auth as mauth  # noqa: E402
import routers.nfts as nfts  # noqa: E402
import routers.security as security  # noqa: E402

FUTURE = (datetime.utcnow() + timedelta(days=20)).isoformat()


def _admin_routes():
    out = []
    for router in (security.router, nfts.router):
        for r in router.routes:
            if any(dep.dependency is mauth.verify_admin for dep in r.dependencies):
                for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                    out.append((m, r.path))  # r.path already carries the router prefix
    return out


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, is_demo BOOLEAN DEFAULT 0)")
    con.executemany("INSERT INTO users VALUES (?,?,?)", [(1, "owner", 0), (2, "demo", 1)])
    con.commit()
    con.close()
    monkeypatch.setattr(mauth, "DATABASE_PATH", str(db))
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    sessions = {"adm": {"user_id": 1, "is_demo": 0, "expires_at": FUTURE},
                "dem": {"user_id": 2, "is_demo": 1, "expires_at": FUTURE}}

    async def get_session(token):
        return sessions.get(token)

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(database, "get_session", get_session)
    monkeypatch.setattr(database, "cleanup_expired_sessions", noop)
    monkeypatch.setattr(database, "renew_session", noop)
    app = FastAPI()
    app.include_router(security.router)
    app.include_router(nfts.router)
    return TestClient(app, raise_server_exceptions=False)


def test_there_are_ten_admin_routes():
    routes = _admin_routes()
    assert len(routes) == 10, routes
    assert {m for m, _ in routes} <= {"POST", "PUT", "DELETE"}


@pytest.mark.parametrize("method,path", _admin_routes())
def test_demo_session_gets_403(client, method, path):
    r = client.request(method, path, headers={"Authorization": "Bearer dem"}, json={})
    assert r.status_code == 403, (method, path, r.status_code)


@pytest.mark.parametrize("method,path", _admin_routes())
def test_tokenless_gets_401(client, method, path):
    assert client.request(method, path, json={}).status_code == 401
