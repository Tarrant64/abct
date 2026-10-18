"""
Shared fixtures for the unit tests (WQ-0058).

The hub test boundary runs tests in a minimal, offline environment (system
python3 + pytest only, no network). Several backend modules import third-party
packages (httpx, fastapi, starlette, pydantic, aiosqlite, python-dotenv) at
module import time even for pure-math code paths. This conftest installs a
last-resort meta-path finder that stubs any package on a fixed third-party
list (and its submodules, at any depth) when the real package is not
importable, so offline unit tests can exercise the real aggregation logic
without a full application stack. The finder sits AFTER the normal path
finder, so a real installed package always wins. Tests that care about network
behaviour stub the transport themselves (monkeypatch), exactly as the
httpx-mocking tests do.

The stubs are auto-extending classes: they can be instantiated, subclassed
(e.g. `class X(BaseHTTPMiddleware)`), and chained through any attribute path.
They also act as pass-through decorators: called with exactly one positional
function (the `@router.get("/x")` second stage), they return that function
unchanged, so decorated endpoints stay real coroutines a test can await.

Async tests in this suite drive coroutines with asyncio.run() directly, so
they work with and without pytest-asyncio.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Top-level third-party distribution names the backend imports at module
# scope. Anything under these names (including submodules) is stubbed when the
# real package is not installed.
STUB_ROOTS = {
    "httpx", "dotenv", "aiosqlite", "fastapi", "starlette", "pydantic",
    "jwt", "PIL", "multipart", "bcrypt", "websockets", "uvicorn", "slowapi",
    "bech32", "cbor2", "msgpack",
}


def _passthrough(args, kwargs):
    """Decorator stage: exactly one positional plain function -> return it."""
    if len(args) == 1 and not kwargs and isinstance(
        args[0], (types.FunctionType, types.CoroutineType)
    ):
        return args[0]
    return None


class _StubMeta(type):
    def __call__(cls, *args, **kwargs):
        passed = _passthrough(args, kwargs)
        return passed if passed is not None else super().__call__(*args, **kwargs)

    def __getattr__(cls, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _stub_class(f"{cls.__name__}.{name}")

    def __iter__(cls):
        return iter(())


class _StubBase(metaclass=_StubMeta):
    def __init__(self, *args, **kwargs):
        self._stub_args = args

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _stub_class(f"{type(self).__name__}.{name}")()

    def __call__(self, *args, **kwargs):
        passed = _passthrough(args, kwargs)
        return passed if passed is not None else _stub_class(type(self).__name__ + "call")()

    def __iter__(self):
        return iter(())


def _stub_class(name):
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    return _StubMeta(safe, (_StubBase,), {"__module__": __name__})


class _StubAttr(types.ModuleType):
    """Module whose missing attributes are auto-extending stub classes."""

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        stub = _stub_class(f"{self.__name__}.{name}")
        setattr(self, name, stub)
        return stub


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Last-resort finder: any module under a STUB_ROOTS name gets a stub."""

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in STUB_ROOTS:
            return None
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec):
        stub = _StubAttr(spec.name)
        stub.__path__ = []
        return stub

    def exec_module(self, module):
        pass


if not any(isinstance(f, _StubFinder) for f in sys.meta_path):
    sys.meta_path.append(_StubFinder())


@pytest.fixture
def backend():
    """Backend directory for path math in tests."""
    return BACKEND_DIR
