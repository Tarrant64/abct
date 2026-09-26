"""
Regression tests for ABCT-ISSUE4-CIP68-2026-09-26 (GitHub issue #4).

Root cause: resolve_ada_handle() only ever built the legacy CIP-25
Blockfrost asset id (ADA_HANDLE_POLICY_ID + hex(handle)). ADA Handles
minted or upgraded since the standard moved to CIP-68 carry the (222)
user-token label prefix "000de140" under the same policy id, so
Blockfrost returns 200 + [] for the legacy id and the handle is
reported "not found" for the majority of handles in circulation today.

detect_ada_handle() (used when auto-detecting a handle already held by a
tracked wallet) has the mirror-image bug: the raw hex asset_name for a
CIP-68 handle fails the caller's utf-8 decode (the 000de140 label bytes
are not valid UTF-8 continuation bytes), so it falls back to leaving
asset_name as the undecoded hex string rather than the handle text.

These tests mock the Blockfrost client (services.cardano.blockfrost_fetch)
directly -- no live network calls, no API keys -- per the pattern used in
tests/unit/test_native_staking_types.py.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.cardano as cardano_module  # noqa: E402

ADA_HANDLE_POLICY_ID = cardano_module.ADA_HANDLE_POLICY_ID
CIP68_LABEL = cardano_module.CIP68_HANDLE_LABEL_HEX  # "000de140"


def _hex(name: str) -> str:
    return name.encode("utf-8").hex()


def cip68_asset_id(name: str) -> str:
    return f"{ADA_HANDLE_POLICY_ID}{CIP68_LABEL}{_hex(name)}"


def legacy_asset_id(name: str) -> str:
    return f"{ADA_HANDLE_POLICY_ID}{_hex(name)}"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


@pytest.fixture
def service(monkeypatch):
    svc = cardano_module.CardanoService()

    async def fake_headers():
        return {}

    monkeypatch.setattr(svc, "_get_blockfrost_headers", fake_headers)
    return svc


# ---------------------------------------------------------------------------
# resolve_ada_handle()
# ---------------------------------------------------------------------------

async def test_cip68_handle_resolves_on_first_try(service, monkeypatch):
    """A CIP-68 handle (the common case today) resolves via the (222)
    user-token asset id without ever needing the legacy fallback."""
    calls = []

    async def fake_fetch(path, **kwargs):
        calls.append(path)
        if path == f"/assets/{cip68_asset_id('jimothy')}/addresses":
            return FakeResponse(json_data=[{"address": "addr1cip68holder", "quantity": "1"}])
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$jimothy")

    assert result == "addr1cip68holder"
    # Must not have needed the legacy fallback call.
    assert calls == [f"/assets/{cip68_asset_id('jimothy')}/addresses"]


async def test_legacy_handle_falls_back_after_cip68_miss(service, monkeypatch):
    """An old-style CIP-25 handle: CIP-68 asset id returns empty, legacy
    asset id hits."""
    calls = []

    async def fake_fetch(path, **kwargs):
        calls.append(path)
        if path == f"/assets/{legacy_asset_id('tap')}/addresses":
            return FakeResponse(json_data=[{"address": "addr1legacyholder", "quantity": "1"}])
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$tap")

    assert result == "addr1legacyholder"
    assert calls == [
        f"/assets/{cip68_asset_id('tap')}/addresses",
        f"/assets/{legacy_asset_id('tap')}/addresses",
    ]


async def test_handle_not_found_on_either_asset_id(service, monkeypatch):
    async def fake_fetch(path, **kwargs):
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$nosuchhandle")

    assert result is None


async def test_handle_not_found_via_404(service, monkeypatch):
    """The Dolos RYO gate (or Blockfrost itself) may 404 instead of 200+[]
    for an asset that has never existed -- must also resolve to None, and
    must still try the legacy id after a CIP-68 404."""
    calls = []

    async def fake_fetch(path, **kwargs):
        calls.append(path)
        return FakeResponse(status_code=404, json_data=None)

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$nosuchhandle")

    assert result is None
    assert len(calls) == 2


async def test_dollar_prefix_and_bare_name_equivalent(service, monkeypatch):
    async def fake_fetch(path, **kwargs):
        if path == f"/assets/{cip68_asset_id('chriscata')}/addresses":
            return FakeResponse(json_data=[{"address": "addr1x", "quantity": "1"}])
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    with_dollar = await service.resolve_ada_handle("$chriscata")
    without_dollar = await service.resolve_ada_handle("chriscata")

    assert with_dollar == "addr1x"
    assert without_dollar == "addr1x"


async def test_case_is_normalised_to_lowercase(service, monkeypatch):
    """ADA Handles are minted lowercase-only; a user typing mixed case
    must still resolve against the lowercase on-chain asset name."""
    seen_paths = []

    async def fake_fetch(path, **kwargs):
        seen_paths.append(path)
        if path == f"/assets/{cip68_asset_id('jimothy')}/addresses":
            return FakeResponse(json_data=[{"address": "addr1x", "quantity": "1"}])
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$JimOthy")

    assert result == "addr1x"
    assert f"/assets/{cip68_asset_id('jimothy')}/addresses" in seen_paths


async def test_multi_holder_response_prefers_quantity_one(service, monkeypatch):
    """Edge case: Blockfrost returns more than one address entry for the
    asset id. The real owner is the one actually holding quantity '1';
    a stale/zero-quantity row must not win just by being first."""
    async def fake_fetch(path, **kwargs):
        if path == f"/assets/{cip68_asset_id('jimothy')}/addresses":
            return FakeResponse(json_data=[
                {"address": "addr1stale", "quantity": "0"},
                {"address": "addr1realholder", "quantity": "1"},
            ])
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$jimothy")

    assert result == "addr1realholder"


async def test_exception_on_cip68_attempt_still_tries_legacy(service, monkeypatch):
    """A transient error on the first (CIP-68) lookup must not abort the
    whole resolution -- the legacy id is still worth trying."""
    async def fake_fetch(path, **kwargs):
        if path == f"/assets/{cip68_asset_id('tap')}/addresses":
            raise RuntimeError("simulated network error")
        if path == f"/assets/{legacy_asset_id('tap')}/addresses":
            return FakeResponse(json_data=[{"address": "addr1legacyholder", "quantity": "1"}])
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$tap")

    assert result == "addr1legacyholder"


async def test_empty_handle_returns_none_without_network_call(service, monkeypatch):
    calls = []

    async def fake_fetch(path, **kwargs):
        calls.append(path)
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(cardano_module, "blockfrost_fetch", fake_fetch)

    result = await service.resolve_ada_handle("$")

    assert result is None
    assert calls == []


# ---------------------------------------------------------------------------
# detect_ada_handle()
# ---------------------------------------------------------------------------

def test_detect_ada_handle_decodes_cip68_label_prefix():
    """asset_name here is the raw hex fallback left behind by the caller's
    failed utf-8 decode of the 000de140-prefixed CIP-68 asset name."""
    raw_hex_asset_name = f"{CIP68_LABEL}{_hex('jimothy')}"
    native_assets = [
        {"policy_id": ADA_HANDLE_POLICY_ID, "asset_name": raw_hex_asset_name},
    ]

    assert cardano_module.detect_ada_handle(native_assets) == "$jimothy"


def test_detect_ada_handle_still_handles_legacy_decoded_name():
    """Legacy CIP-25 handles decode cleanly upstream to plain text --
    must be returned unchanged (no regression)."""
    native_assets = [
        {"policy_id": ADA_HANDLE_POLICY_ID, "asset_name": "chriscata"},
    ]

    assert cardano_module.detect_ada_handle(native_assets) == "$chriscata"


def test_detect_ada_handle_ignores_other_policies():
    native_assets = [
        {"policy_id": "someotherpolicy", "asset_name": "notahandle"},
    ]

    assert cardano_module.detect_ada_handle(native_assets) is None


def test_detect_ada_handle_returns_none_for_empty_list():
    assert cardano_module.detect_ada_handle([]) is None


def test_detect_ada_handle_skips_unparseable_cip68_entry():
    """If the bytes after the label somehow don't decode as utf-8, don't
    crash -- move on rather than returning garbage."""
    bad_hex = CIP68_LABEL + "ff"  # 0xff alone is never valid UTF-8
    native_assets = [
        {"policy_id": ADA_HANDLE_POLICY_ID, "asset_name": bad_hex},
        {"policy_id": ADA_HANDLE_POLICY_ID, "asset_name": "fallbackhandle"},
    ]

    assert cardano_module.detect_ada_handle(native_assets) == "$fallbackhandle"
