"""
Import-level smoke tests (DEPLOY-FIX-1).

Every router module and the FastAPI app itself must be importable. Decorator
misconfiguration (e.g. slowapi's limiter.limit requiring a parameter literally
named "request") raises at import time, which unit tests that stub routers
never exercise — the 2026-07-12 deploy crash-looped on exactly that in
routers/auth.py while the whole offline suite was green.
"""

import importlib
import os
import pkgutil
import sys

import pytest

# Add backend to sys.path so imports work
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import routers  # noqa: E402

ROUTER_MODULES = sorted(m.name for m in pkgutil.iter_modules(routers.__path__))


@pytest.mark.parametrize("modname", ROUTER_MODULES)
def test_router_module_imports(modname):
    importlib.import_module(f"routers.{modname}")


def test_main_app_imports():
    importlib.import_module("main")
