"""ABCT leak fix 20261120: /portfolio/chart/unified decorator placement and
auth on settings/backup/security GET routes."""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers.portfolio as portfolio  # noqa: E402
from routers import settings, backup, security  # noqa: E402
from auth_utils import verify_session  # noqa: E402

PROTECTED = [
    "/settings/apis",
    "/settings/apis/blockfrost",
    "/settings/apis/blockfrost/test",
    "/settings/api-utilization",
    "/settings/api-utilization/blockfrost",
    "/backup/info",
    "/security/settings",
    "/security/certificate/info",
]


def _app(*routers):
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    return app


def test_unified_chart_route_is_real_endpoint():
    routes = {r.path: r for r in portfolio.router.routes}
    assert routes["/portfolio/chart/unified"].endpoint is portfolio.get_unified_chart
    assert not any(
        getattr(r, "endpoint", None) is portfolio._stock_chart_overlay
        for r in portfolio.router.routes
    )
    deps = [d.call for d in routes["/portfolio/chart/unified"].dependant.dependencies]
    assert verify_session in deps


def test_unified_chart_authed_200(monkeypatch):
    async def fake_username(_uid):
        return "demo"

    async def fake_is_demo(_u):
        return True

    async def fake_demo_chart(_range):
        return {"data": [], "range": _range}

    monkeypatch.setattr(portfolio, "get_username_by_user_id", fake_username)
    monkeypatch.setattr(portfolio, "is_demo_user", fake_is_demo)
    monkeypatch.setattr(portfolio, "_get_demo_unified_chart", fake_demo_chart)
    app = _app(portfolio.router)
    app.dependency_overrides[verify_session] = lambda: 1
    r = TestClient(app).get("/portfolio/chart/unified?range=1w")
    assert r.status_code == 200


def test_helper_path_not_a_route():
    app = _app(portfolio.router)
    app.dependency_overrides[verify_session] = lambda: 1
    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/portfolio/_stock_chart_overlay").status_code in (404, 405)


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_routes_reject_without_session(monkeypatch, path):
    monkeypatch.setenv("ABCT_REQUIRE_AUTH", "true")
    c = TestClient(_app(settings.router, backup.router, security.router),
                   raise_server_exceptions=False)
    assert c.get(path).status_code == 401


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_routes_declare_verify_session(path):
    app = _app(settings.router, backup.router, security.router)
    route = next(r for r in app.routes
                 if getattr(r, "path_regex", None) and r.path_regex.match(path)
                 and "GET" in r.methods)
    deps = [d.call for d in route.dependant.dependencies]
    assert verify_session in deps
