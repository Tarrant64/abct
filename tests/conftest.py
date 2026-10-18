"""
Shared fixtures for the unit tests (WQ-0058).

The hub test boundary runs tests in a minimal, offline environment (system
python3 + pytest only, no network). Several backend modules import third-party
packages (httpx, fastapi, starlette, pydantic, aiosqlite, python-dotenv) at
module import time even for pure-math code paths. The `offline_stubs` fixture
below stubs exactly those packages (and their submodules) when the real
package is not importable, so offline unit tests can exercise the real
aggregation logic without a full application stack.

The stubs are OPT-IN and MODULE-SCOPED (WQ-0368 review): a test module asks
for them with `pytestmark = pytest.mark.usefixtures("offline_stubs")` and
imports backend modules inside its tests. Nothing is stubbed while other test
modules are collected or run, so a missing dependency there still fails with
an honest ModuleNotFoundError, and at teardown every stub module and every
backend module imported against the stubs is dropped from sys.modules so no
stub leaks into a later test. A real installed package always wins: a root is
only stubbed when importlib cannot find it.

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
import importlib.util
import os
import sys
import types

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Top-level third-party packages the backend modules exercised by the opt-in
# tests import at module scope. Keep this list to what those tests need: a
# package whose behaviour a test depends on (bech32, cbor2, msgpack, ...) must
# never be stubbed, or its test passes or fails against a fake.
STUB_ROOTS = frozenset({
    "httpx", "dotenv", "aiosqlite", "fastapi", "starlette", "pydantic",
})


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
    __test__ = False  # never collected, even if named like TestClient

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
    """Last-resort finder: any module under one of `roots` gets a stub."""

    def __init__(self, roots):
        self.roots = frozenset(roots)

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in self.roots:
            return None
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec):
        stub = _StubAttr(spec.name)
        stub.__path__ = []
        return stub

    def exec_module(self, module):
        pass


def _missing_roots():
    return sorted(r for r in STUB_ROOTS if importlib.util.find_spec(r) is None)


def _imported_against_stubs(name, module, roots):
    if name.split(".")[0] in roots:
        return True
    path = getattr(module, "__file__", None) or ""
    return os.path.abspath(path).startswith(BACKEND_DIR + os.sep)


@pytest.fixture(scope="module")
def offline_stubs():
    """Stub the missing STUB_ROOTS packages for one test module only.

    Yields the sorted list of roots that were actually stubbed (empty when the
    full stack is installed). Backend modules must be imported inside the
    tests, not at the test module's top level, unless they import no
    third-party package.
    """
    roots = _missing_roots()
    before = set(sys.modules)
    finder = _StubFinder(roots)
    sys.meta_path.append(finder)
    try:
        yield roots
    finally:
        sys.meta_path.remove(finder)
        for name in set(sys.modules) - before:
            if _imported_against_stubs(name, sys.modules[name], roots):
                del sys.modules[name]


@pytest.fixture
def backend():
    """Backend directory for path math in tests."""
    return BACKEND_DIR
