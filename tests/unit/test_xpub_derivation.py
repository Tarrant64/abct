"""
Bitcoin xpub/ypub/zpub derivation regression tests.

Pins a bug that shipped silently: backend/services/bitcoin.py imported
``Bip49PublicKey``/``Bip84PublicKey``, which have never existed in any
bip_utils release, and called ``Bip44.ChainType(...)``, which does not exist
either. Both failures were swallowed — the import by a try/except that logged
at WARNING, the derivation by an ``except Exception: return []`` — so xpub
wallets reported a zero balance instead of an error.

These tests therefore assert that derivation actually PRODUCES the right
addresses, not merely that the import did not raise. All keys below are the
standard public BIP test vectors for the "abandon abandon ... about" mnemonic;
no real wallet is involved.
"""

import asyncio
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import services.bitcoin as bitcoin_module  # noqa: E402
from services.bitcoin import (  # noqa: E402
    XpubDerivationError,
    XpubError,
    bitcoin_service,
)

# Public BIP32/44/49/84 test vectors (mnemonic: "abandon" x11 + "about").
XPUB = ("xpub6BosfCnifzxcFwrSzQiqu2DBVTshkCXacvNsWGYJVVhhawA7d4R5WSWGFNbi8"
        "Aw6ZRc1brxMyWMzG3DSSSSoekkudhUd9yLb6qx39T9nMdj")
YPUB = ("ypub6Ww3ibxVfGzLrAH1PNcjyAWenMTbbAosGNB6VvmSEgytSER9azLDWCxoJwW7K"
        "e7icmizBMXrzBx9979FfaHxHcrArf3zbeJJJUZPf663zsP")
ZPUB = ("zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1A"
        "DqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs")

VECTORS = [
    # (key, receive addresses [0,1], change address [0], expected prefix)
    (XPUB,
     ["1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA", "1Ak8PffB2meyfYnbXZR9EGfLfFZVpzJvQP"],
     ["1J3J6EvPrv8q6AC3VCjWV45Uf3nssNMRtH"], "1"),
    (YPUB,
     ["37VucYSaXLCAsxYyAPfbSi9eh4iEcbShgf", "3LtMnn87fqUeHBUG414p9CWwnoV6E2pNKS"],
     ["34K56kSjgUCUSD8GTtuF7c9Zzwokbs6uZ7"], "3"),
    (ZPUB,
     ["bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu",
      "bc1qnjg0jd8228aq7egyzacy8cys3knf9xvrerkf9g"],
     ["bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el"], "bc1"),
]


def test_bip_utils_import_succeeds():
    """The bip_utils import must resolve — this is the guard that failed before."""
    assert bitcoin_module.BIP_UTILS_AVAILABLE, (
        f"bip_utils failed to import: {bitcoin_module.BIP_UTILS_ERROR}"
    )
    assert bitcoin_service.xpub_available()
    assert bitcoin_service.xpub_unavailable_reason() is None


@pytest.mark.parametrize("key,receive,change,prefix", VECTORS)
def test_derivation_matches_published_vectors(key, receive, change, prefix):
    """Derived addresses must equal the published vectors, not merely exist."""
    derived = bitcoin_service.derive_addresses_from_xpub(key, count=2)
    assert [addr for addr, _ in derived] == receive
    assert [idx for _, idx in derived] == [0, 1]
    assert all(addr.startswith(prefix) for addr, _ in derived)

    internal = bitcoin_service.derive_addresses_from_xpub(key, count=1, change=True)
    assert [addr for addr, _ in internal] == change


@pytest.mark.parametrize("key,receive,_change,_prefix", VECTORS)
def test_start_index_is_honoured(key, receive, _change, _prefix):
    """Batch scanning relies on start_index; an off-by-one would rescan index 0."""
    derived = bitcoin_service.derive_addresses_from_xpub(key, start_index=1, count=1)
    assert derived == [(receive[1], 1)]


def test_unrecognized_key_raises():
    """A bad key must raise, never return [] that reads as 'empty wallet'."""
    with pytest.raises(XpubDerivationError):
        bitcoin_service.derive_addresses_from_xpub("notanxpub")


def test_testnet_key_raises():
    with pytest.raises(XpubDerivationError):
        bitcoin_service.derive_addresses_from_xpub("tpub" + "0" * 100)


def test_discovery_reports_error_instead_of_zero_balance(monkeypatch):
    """A derivation failure must surface as an error, not a 0.00000000 balance."""
    def boom(*args, **kwargs):
        raise XpubError("simulated derivation failure")

    monkeypatch.setattr(bitcoin_service, "derive_addresses_from_xpub", boom)
    result = asyncio.run(bitcoin_service.discover_xpub_addresses(ZPUB))

    assert result.get("error") == "xpub_derivation_failed"
    assert "total_balance_btc" not in result


def test_unavailable_reason_is_actionable(monkeypatch):
    """When bip_utils is unusable the message must say so, not 'install it'."""
    monkeypatch.setattr(bitcoin_module, "BIP_UTILS_AVAILABLE", False)
    monkeypatch.setattr(bitcoin_module, "BIP_UTILS_ERROR", "ImportError: boom")

    reason = bitcoin_service.xpub_unavailable_reason()
    assert reason and "ImportError: boom" in reason

    result = asyncio.run(bitcoin_service.discover_xpub_addresses(ZPUB))
    assert result.get("error") == "xpub_unavailable"
