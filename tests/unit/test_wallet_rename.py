"""
Server-fixes item 8 (2026-11-20): wallet rename hardening.

PUT /wallets/{wallet_id}/label and PATCH /wallets/{address}:
- behind verify_session (as every state-changing wallet route);
- the wallet must belong to the caller (404 for missing OR foreign wallets);
- null / empty / >64 / control-character labels -> 422;
- demo users are blocked.
"""

import os
import sqlite3
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import routers.wallets as wallets_router  # noqa: E402
import services.portfolio_freshness as freshness  # noqa: E402
from auth_utils import verify_session  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "w.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE wallets (id INTEGER PRIMARY KEY, user_id INTEGER, address TEXT,
            blockchain TEXT, label TEXT, updated_at TIMESTAMP);
        INSERT INTO wallets (id, user_id, address, blockchain, label) VALUES
            (1, 7, 'addr_mine', 'cardano', 'Old'),
            (2, 8, 'addr_theirs', 'cardano', 'Theirs');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE_PATH", path)

    async def noop(*a, **k):
        return "v"
    monkeypatch.setattr(freshness, "invalidate_user_portfolio_caches", noop)

    state = {"demo": False}

    async def username(uid):
        return "demo" if state["demo"] else "chris"

    async def is_demo(name):
        return name == "demo"
    monkeypatch.setattr(wallets_router, "get_username_by_user_id", username)
    monkeypatch.setattr(wallets_router, "is_demo_user", is_demo)

    app = FastAPI()
    app.include_router(wallets_router.router)
    app.dependency_overrides[verify_session] = lambda: 7
    client = TestClient(app)
    client.state = state
    client.path = path
    return client


def _label(client, wid):
    conn = sqlite3.connect(client.path)
    try:
        return conn.execute("SELECT label FROM wallets WHERE id = ?", (wid,)).fetchone()[0]
    finally:
        conn.close()


def test_routes_depend_on_verify_session():
    for route in wallets_router.router.routes:
        if route.path in ("/wallets/{wallet_id}/label", "/wallets/{address}") and (
                route.methods & {"PUT", "PATCH"}):
            calls = [d.call for d in route.dependant.dependencies]
            assert verify_session in calls, route.path


def test_rename_ok_strips_and_persists(env):
    r = env.put("/wallets/1/label", json={"label": "  Cold storage  "})
    assert r.status_code == 200 and r.json()["label"] == "Cold storage"
    assert _label(env, 1) == "Cold storage"


@pytest.mark.parametrize("bad", ["x" * 65, "line\nbreak", "nul\x00", "tab\there",
                                 "c1\x85ctl", "sep x", 123, ["a"]])
def test_invalid_labels_are_422_and_do_not_write(env, bad):
    r = env.put("/wallets/1/label", json={"label": bad})
    assert r.status_code == 422
    assert _label(env, 1) == "Old"


@pytest.mark.parametrize("clear", [None, "", "   "])
def test_null_or_empty_label_clears_it(env, clear):
    """2026-11-21: clearing a name is allowed (stored as NULL), unlike other invalid values."""
    r = env.put("/wallets/1/label", json={"label": clear})
    assert r.status_code == 200 and r.json()["label"] is None
    assert _label(env, 1) is None


def test_clear_keeps_ownership_and_demo_rules(env):
    assert env.put("/wallets/2/label", json={"label": None}).status_code == 404
    assert _label(env, 2) == "Theirs"
    assert env.put("/wallets/999/label", json={"label": ""}).status_code == 404
    env.state["demo"] = True
    assert env.put("/wallets/1/label", json={"label": None}).json().get("demo_mode") is True
    assert _label(env, 1) == "Old"


def test_missing_label_key_is_422(env):
    assert env.put("/wallets/1/label", json={}).status_code == 422


def test_exactly_64_chars_is_allowed(env):
    assert env.put("/wallets/1/label", json={"label": "a" * 64}).status_code == 200


def test_unknown_wallet_404(env):
    assert env.put("/wallets/999/label", json={"label": "x"}).status_code == 404


def test_other_users_wallet_is_404_and_untouched(env):
    r = env.put("/wallets/2/label", json={"label": "hijack"})
    assert r.status_code == 404
    assert _label(env, 2) == "Theirs"


def test_demo_user_blocked(env):
    env.state["demo"] = True
    r = env.put("/wallets/1/label", json={"label": "x"})
    assert r.status_code == 200 and r.json().get("demo_mode") is True
    assert _label(env, 1) == "Old"


def test_patch_by_address_same_rules(env, monkeypatch):
    async def get_wallet_by_address(address, blockchain=None, user_id=None):
        conn = sqlite3.connect(env.path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM wallets WHERE address = ? AND user_id = ?",
                               (address, user_id)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    monkeypatch.setattr(wallets_router, "get_wallet_by_address", get_wallet_by_address)

    assert env.patch("/wallets/addr_mine", json={"label": "New"}).status_code == 200
    assert _label(env, 1) == "New"
    assert env.patch("/wallets/addr_mine", json={}).status_code == 422          # omitted key
    assert env.patch("/wallets/addr_mine", json={"label": ""}).status_code == 200      # clears
    assert _label(env, 1) is None
    assert env.patch("/wallets/addr_mine", json={"label": "New"}).status_code == 200
    assert env.patch("/wallets/addr_mine", json={"label": None}).status_code == 200    # clears
    assert _label(env, 1) is None
    assert env.patch("/wallets/addr_mine", json={"label": "New"}).status_code == 200
    assert env.patch("/wallets/addr_mine", json={"label": "a\nb"}).status_code == 422
    assert env.patch("/wallets/addr_mine", json={"label": "z" * 65}).status_code == 422
    # another user's address: 404 and untouched
    assert env.patch("/wallets/addr_theirs", json={"label": "hijack"}).status_code == 404
    assert _label(env, 2) == "Theirs"
    env.state["demo"] = True
    assert env.patch("/wallets/addr_mine", json={"label": "demo"}).json().get("demo_mode") is True
    assert _label(env, 1) == "New"
