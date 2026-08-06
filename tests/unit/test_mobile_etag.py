"""
Unit tests for the mobile router's ETag / If-None-Match support
(DASHBOARD-3, _ConditionalGetRoute in routers/mobile.py).

Uses a minimal FastAPI app with the same route class — no DB, no server.
"""

import os
import sys

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.testclient import TestClient

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from routers.mobile import _ConditionalGetRoute, _etag_matches  # noqa: E402


@pytest.fixture
def client():
    router = APIRouter(route_class=_ConditionalGetRoute)
    state = {"payload": {"value": 1}}

    @router.get("/static")
    async def static_endpoint(refresh: bool = Query(False)):
        return state["payload"]

    @router.post("/static")
    async def post_endpoint():
        return {"posted": True}

    @router.get("/empty")
    async def empty_endpoint():
        from fastapi import Response
        return Response(status_code=204)

    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    c.state_ref = state
    return c


def test_no_header_gets_200_with_etag(client):
    r = client.get("/static")
    assert r.status_code == 200
    assert r.json() == {"value": 1}
    etag = r.headers.get("etag")
    assert etag and etag.startswith('"') and etag.endswith('"')


def test_etag_stable_for_identical_payload(client):
    assert client.get("/static").headers["etag"] == client.get("/static").headers["etag"]


def test_matching_if_none_match_returns_empty_304(client):
    etag = client.get("/static").headers["etag"]
    r = client.get("/static", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.content == b""
    assert r.headers.get("etag") == etag


def test_mismatching_if_none_match_returns_full_200(client):
    r = client.get("/static", headers={"If-None-Match": '"nope"'})
    assert r.status_code == 200
    assert r.json() == {"value": 1}


def test_weak_prefix_list_and_wildcard_match(client):
    etag = client.get("/static").headers["etag"]
    assert client.get("/static", headers={"If-None-Match": f"W/{etag}"}).status_code == 304
    assert client.get("/static", headers={"If-None-Match": f'"a", "b", {etag}'}).status_code == 304
    assert client.get("/static", headers={"If-None-Match": "*"}).status_code == 304


def test_refresh_true_bypasses_304(client):
    etag = client.get("/static").headers["etag"]
    r = client.get("/static?refresh=true", headers={"If-None-Match": etag})
    assert r.status_code == 200
    assert r.json() == {"value": 1}


def test_etag_rotates_when_payload_changes(client):
    old = client.get("/static").headers["etag"]
    client.state_ref["payload"] = {"value": 2}
    r = client.get("/static", headers={"If-None-Match": old})
    assert r.status_code == 200  # stale client tag -> fresh body
    assert r.headers["etag"] != old


def test_non_get_and_bodyless_responses_untouched(client):
    assert "etag" not in client.post("/static").headers
    r = client.get("/empty")
    assert r.status_code == 204
    assert "etag" not in r.headers


def test_etag_matches_helper():
    assert _etag_matches('"abc"', '"abc"')
    assert _etag_matches('W/"abc"', '"abc"')
    assert _etag_matches('w/"abc"', '"abc"')
    assert _etag_matches('"x", "abc"', '"abc"')
    assert _etag_matches('*', '"abc"')
    assert not _etag_matches('"x"', '"abc"')
    assert not _etag_matches('', '"abc"')
