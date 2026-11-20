"""/logs/stream is consumed by EventSource (no headers): must accept ?token=."""
import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.logs as logs  # noqa: E402
from auth_utils import verify_session_sse  # noqa: E402


def test_logs_stream_uses_sse_dependency():
    route = next(r for r in logs.router.routes if r.path == "/logs/stream")
    assert verify_session_sse in [d.call for d in route.dependant.dependencies]


def test_logs_stream_401_without_token(monkeypatch):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    app = FastAPI()
    app.include_router(logs.router)
    r = TestClient(app, raise_server_exceptions=False).get("/logs/stream")
    assert r.status_code == 401
