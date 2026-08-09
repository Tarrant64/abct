"""
Tests for credential encryption at rest (_encrypt_value / _decrypt_value).

_decrypt_value has four paths and they are deliberately NOT symmetric:

  1. falsy input                      -> returned as-is
  2. no 'enc:' prefix                 -> returned as-is (pre-migration plaintext;
                                         must keep round-tripping or legitimately
                                         stored legacy credentials become unusable)
  3. 'enc:' prefix but no Fernet      -> fails closed (None)
  4. 'enc:' prefix that won't decrypt -> fails closed (None)

Paths 3 and 4 used to return the stored value, handing raw ciphertext to callers
as though it were a credential. Callers then signed requests with it, producing a
confusing auth failure instead of "not configured".
"""

import os
import sys

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402


@pytest.fixture
def fernet(monkeypatch):
    """Install a throwaway Fernet so tests never touch the real key file."""
    f = Fernet(Fernet.generate_key())
    monkeypatch.setattr(database, "_fernet", f)
    return f


@pytest.fixture
def no_fernet(monkeypatch):
    monkeypatch.setattr(database, "_fernet", None)


# --- path 1: falsy input ----------------------------------------------------

@pytest.mark.parametrize("value", [None, ""])
def test_falsy_values_pass_through(fernet, value):
    assert database._decrypt_value(value) == value


@pytest.mark.parametrize("value", [None, ""])
def test_falsy_values_are_not_encrypted(fernet, value):
    assert database._encrypt_value(value) == value


# --- path 2: legacy plaintext (must NOT change) -----------------------------

def test_legacy_plaintext_round_trips(fernet):
    """Pre-migration plaintext has no 'enc:' prefix and must be returned as-is."""
    assert database._decrypt_value("legacy-plaintext-key") == "legacy-plaintext-key"


def test_legacy_plaintext_round_trips_without_fernet(no_fernet):
    """Plaintext must survive even when encryption is unavailable."""
    assert database._decrypt_value("legacy-plaintext-key") == "legacy-plaintext-key"


# --- happy path: encrypt/decrypt round trip ---------------------------------

def test_encrypt_decrypt_round_trip(fernet):
    encrypted = database._encrypt_value("s3cret-api-key")
    assert encrypted.startswith("enc:")
    assert "s3cret-api-key" not in encrypted
    assert database._decrypt_value(encrypted) == "s3cret-api-key"


# --- path 3: encrypted value, encryption not initialized --------------------

def test_encrypted_value_without_fernet_fails_closed(no_fernet, caplog):
    stored = "enc:gAAAAABsomethingthatlooksliketoken"
    with caplog.at_level("ERROR"):
        result = database._decrypt_value(stored)
    assert result is None, "must not hand ciphertext back to callers"
    assert result != stored
    assert "Encryption not initialized" in caplog.text


# --- path 4: encrypted value that will not decrypt --------------------------

def test_corrupt_ciphertext_fails_closed(fernet, caplog):
    """The original bug: a bad token returned the ciphertext itself."""
    stored = "enc:this-is-not-a-valid-fernet-token"
    with caplog.at_level("ERROR"):
        result = database._decrypt_value(stored)
    assert result is None
    assert result != stored


def test_wrong_key_fails_closed(monkeypatch, caplog):
    """Value encrypted with one key must not leak when read back with another."""
    original = Fernet(Fernet.generate_key())
    monkeypatch.setattr(database, "_fernet", original)
    stored = database._encrypt_value("s3cret-api-key")

    monkeypatch.setattr(database, "_fernet", Fernet(Fernet.generate_key()))
    with caplog.at_level("ERROR"):
        result = database._decrypt_value(stored)

    assert result is None
    assert result != stored, "ciphertext must never be returned as a credential"


def test_failed_decrypt_is_falsy_so_callers_see_not_configured(fernet):
    """
    get_api_key/get_api_credentials gate on truthiness, so None is what makes a
    provider report "not configured" rather than authenticating with garbage.
    """
    assert not database._decrypt_value("enc:not-a-valid-token")


# --- file permission hardening ----------------------------------------------

def test_restrict_file_permissions_sets_owner_only(tmp_path):
    target = tmp_path / "portfolio.db"
    target.write_bytes(b"")
    target.chmod(0o644)

    database.restrict_file_permissions(target)

    assert (target.stat().st_mode & 0o777) == 0o600


def test_restrict_file_permissions_ignores_missing_file(tmp_path):
    """The -wal/-shm sidecars may not exist yet; that must not raise."""
    database.restrict_file_permissions(tmp_path / "does-not-exist.db-wal")
