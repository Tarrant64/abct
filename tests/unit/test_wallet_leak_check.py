"""
SEC-HOOK-1: wallet-address leak detection in the pre-push security gate.

Covers: per-chain true positives (checksum-validated), checksum and
length/case false-positive guards, the allowlist mechanism, the baseline
exclusion (WALLET-* findings cannot be re-baselined away), and the
regression that motivated the check: a stake-derivation fixture full of
non-allowlisted addresses gets BLOCKED, while the current scrubbed fixture
(allowlisted spec vectors) passes.

All "personal-looking" addresses in this file are constructed at runtime
from fixed byte patterns — nothing here is a real wallet. The few literal
addresses used are famous public constants (Bitcoin genesis, BIP-173 and
EIP-55 spec vectors, XRP genesis) and are present in sec/wallet_allowlist.txt.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

SEC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "sec")
)
if SEC_DIR not in sys.path:
    sys.path.insert(0, SEC_DIR)

from security_audit import SecurityAuditor  # noqa: E402
from security_agent import SecurityAgent  # noqa: E402


# ---------------------------------------------------------------------------
# Independent encoders (encode side only — the checker implements decode/verify,
# so agreement between the two is a genuine cross-check, not circularity).
# ---------------------------------------------------------------------------

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def b58encode(raw: bytes) -> str:
    num = int.from_bytes(raw, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = B58[rem] + out
    pad = 0
    for b in raw:
        if b == 0:
            pad += 1
        else:
            break
    return B58[0] * pad + out


def b58check(version: bytes, payload: bytes) -> str:
    data = version + payload
    checksum = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    return b58encode(data + checksum)


def _polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= gen[i] if ((top >> i) & 1) else 0
    return chk


def _hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _to5bit(data: bytes):
    acc = bits = 0
    out = []
    for b in data:
        acc = (acc << 8) | b
        bits += 8
        while bits >= 5:
            bits -= 5
            out.append((acc >> bits) & 31)
    if bits:
        out.append((acc << (5 - bits)) & 31)
    return out

def bech32encode(hrp: str, data: bytes) -> str:
    values = _to5bit(data)
    polymod = _polymod(_hrp_expand(hrp) + values + [0] * 6) ^ 1
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32[v] for v in values + checksum)


def ss58encode(pubkey: bytes, addr_type: int = 0) -> str:
    data = bytes([addr_type]) + pubkey
    checksum = hashlib.blake2b(b"SS58PRE" + data, digest_size=64).digest()[:2]
    return b58encode(data + checksum)


# Synthetic, checksum-valid addresses per chain (fixed byte patterns)
CARDANO_ADDR = bech32encode("addr", bytes([0x01]) + b"\x33" * 28 + b"\x44" * 28)
CARDANO_STAKE = bech32encode("stake", bytes([0xE1]) + b"\x44" * 28)
COSMOS_ADDR = bech32encode("cosmos", b"\x55" * 20)
TRON_ADDR = b58check(b"\x41", b"\x22" * 20)
LTC_ADDR = b58check(b"\x30", b"\x11" * 20)
DOGE_ADDR = b58check(b"\x1e", b"\x66" * 20)
DOT_ADDR = ss58encode(b"\x77" * 32)

# Famous public constants (also in sec/wallet_allowlist.txt)
BTC_GENESIS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
BTC_BECH32 = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
EIP55_ADDR = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
XRP_GENESIS = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def scan(tmp_path: Path, files: dict, allowlist=None):
    """Write files into a scratch project, run only the wallet check."""
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if allowlist is not None:
        d = tmp_path / "sec"
        d.mkdir(exist_ok=True)
        (d / "wallet_allowlist.txt").write_text(
            "\n".join(allowlist) + "\n", encoding="utf-8")
    auditor = SecurityAuditor(tmp_path)
    auditor.findings.clear()  # only wallet findings matter here
    auditor.check_wallet_addresses()
    return auditor.findings


def ids(findings):
    return sorted(f.check_id for f in findings)


# ---------------------------------------------------------------------------
# True positives: checksum-validated chains block as WALLET-001 (CRITICAL)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,address", [
    ("cardano-addr", CARDANO_ADDR),
    ("cardano-stake", CARDANO_STAKE),
    ("bitcoin-base58", BTC_GENESIS),
    ("bitcoin-bech32", BTC_BECH32),
    ("cosmos", COSMOS_ADDR),
    ("tron", TRON_ADDR),
    ("litecoin", LTC_ADDR),
    ("dogecoin", DOGE_ADDR),
    ("xrp", XRP_GENESIS),
    ("polkadot-ss58", DOT_ADDR),
])
def test_validated_chain_blocks(tmp_path, label, address):
    findings = scan(tmp_path, {"app.py": f'X = "{address}"\n'})
    assert [f.check_id for f in findings] == ["WALLET-001"], label
    assert findings[0].severity == "CRITICAL"
    # full address never appears in the finding text
    assert address not in findings[0].description


def test_corrupted_checksum_not_flagged(tmp_path):
    # Flip the final character: every checksum scheme must reject it
    bad = []
    for addr in [CARDANO_ADDR, BTC_GENESIS, BTC_BECH32, TRON_ADDR, DOT_ADDR]:
        last = addr[-1]
        repl = "2" if last != "2" else "3"
        bad.append(addr[:-1] + repl)
    content = "\n".join(f'A{i} = "{a}"' for i, a in enumerate(bad)) + "\n"
    assert scan(tmp_path, {"app.py": content}) == []


# ---------------------------------------------------------------------------
# EVM: EIP-55 case heuristic and length guards
# ---------------------------------------------------------------------------

def test_evm_mixed_case_is_high(tmp_path):
    findings = scan(tmp_path, {"app.py": f'W = "{EIP55_ADDR}"\n'})
    assert ids(findings) == ["WALLET-002"]
    assert findings[0].severity == "HIGH"


def test_evm_uniform_case_is_medium(tmp_path):
    findings = scan(tmp_path, {"app.py": f'W = "{EIP55_ADDR.lower()}"\n'})
    assert ids(findings) == ["WALLET-003"]
    assert findings[0].severity == "MEDIUM"


def test_evm_tx_hash_not_flagged(tmp_path):
    tx = "0x" + "ab12" * 16  # 64 hex chars = tx hash, not an address
    assert scan(tmp_path, {"app.py": f'TX = "{tx}"\n'}) == []


def test_bare_hex_not_flagged(tmp_path):
    bare = "ab12" * 10  # 40 hex chars but no 0x prefix
    assert scan(tmp_path, {"app.py": f'H = "{bare}"\n'}) == []


# ---------------------------------------------------------------------------
# Solana: context-gated, hex-excluded
# ---------------------------------------------------------------------------

SOLANA_LIKE = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"


def test_solana_with_context_is_medium(tmp_path):
    findings = scan(
        tmp_path, {"app.py": f'wallet_address = "{SOLANA_LIKE}"\n'})
    assert ids(findings) == ["WALLET-004"]
    assert findings[0].severity == "MEDIUM"


def test_solana_without_context_not_flagged(tmp_path):
    assert scan(tmp_path, {"app.py": f'x = "{SOLANA_LIKE}"\n'}) == []


def test_hex_string_on_context_line_not_flagged(tmp_path):
    hexish = "deadbeef" * 5  # 40 hex chars, base58-charset subset
    assert scan(
        tmp_path, {"app.py": f'wallet = "{hexish}"\n'}) == []


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

def test_allowlist_clears_finding(tmp_path):
    files = {"app.py": f'X = "{CARDANO_ADDR}"\n'}
    assert len(scan(tmp_path, files)) == 1
    assert scan(tmp_path, files, allowlist=[CARDANO_ADDR]) == []


def test_allowlist_inline_comments_and_blanks(tmp_path):
    allow = [
        "# comment line",
        "",
        f"{CARDANO_ADDR}  # inline comment with provenance",
    ]
    assert scan(
        tmp_path, {"app.py": f'X = "{CARDANO_ADDR}"\n'}, allowlist=allow) == []


def test_allowlist_is_exact_not_prefix(tmp_path):
    findings = scan(
        tmp_path, {"app.py": f'X = "{CARDANO_ADDR}"\n'},
        allowlist=[CARDANO_STAKE])
    assert ids(findings) == ["WALLET-001"]


# ---------------------------------------------------------------------------
# The motivating regression: leaky fixture blocked, scrubbed fixture passes
# ---------------------------------------------------------------------------

def leaky_fixture(a1, s1, a2, s2):
    return (
        "# Koios-verified pairs\n"
        "KNOWN_PAIRS = [\n"
        f'    ("{a1}",\n     "{s1}"),\n'
        f'    ("{a2}",\n     "{s2}"),\n'
        "]\n"
    )


def test_leaky_fixture_content_is_blocked(tmp_path):
    """A stake-derivation fixture holding NON-allowlisted (i.e. personal)
    addresses — the shape of the original leak — must block the push."""
    addr2 = bech32encode("addr", bytes([0x11]) + b"\x0a" * 28 + b"\x0b" * 28)
    stake2 = bech32encode("stake", bytes([0xE1]) + b"\x0b" * 28)
    findings = scan(tmp_path, {
        "tests_fixture.py": leaky_fixture(
            CARDANO_ADDR, CARDANO_STAKE, addr2, stake2),
    })
    crits = [f for f in findings if f.check_id == "WALLET-001"]
    assert len(crits) == 4  # every address caught
    assert all(f.severity == "CRITICAL" for f in crits)


def test_scrubbed_fixture_content_passes(tmp_path):
    """The same fixture shape with allowlisted spec/synthetic vectors —
    the current tests/unit/test_stake_derivation.py situation — is clean."""
    addr2 = bech32encode("addr", bytes([0x11]) + b"\x0a" * 28 + b"\x0b" * 28)
    stake2 = bech32encode("stake", bytes([0xE1]) + b"\x0b" * 28)
    findings = scan(
        tmp_path,
        {"tests_fixture.py": leaky_fixture(
            CARDANO_ADDR, CARDANO_STAKE, addr2, stake2)},
        allowlist=[CARDANO_ADDR, CARDANO_STAKE, addr2, stake2],
    )
    assert findings == []


def test_real_repo_tree_is_clean():
    """The actual repo (with its committed allowlist) must scan clean —
    this is the invariant that lets the pre-push hook stay green."""
    root = Path(SEC_DIR).parent
    auditor = SecurityAuditor(root)
    auditor.findings.clear()
    auditor.check_wallet_addresses()
    assert auditor.findings == [], [
        f"{f.check_id} {f.file_path}:{f.line_number}" for f in auditor.findings
    ]


# ---------------------------------------------------------------------------
# Baseline exclusion: WALLET-* findings cannot be waved through
# ---------------------------------------------------------------------------

def test_save_baseline_excludes_wallet_findings(tmp_path):
    agent = SecurityAgent(tmp_path)
    agent.auditor.findings.clear()
    agent.auditor.add_finding(
        "CRITICAL", "WALLET-001", "Wallet Address Leak (Cardano)",
        tmp_path / "app.py", 1, "leak", "remove")
    agent.auditor.add_finding(
        "MEDIUM", "MED-SEC", "Potential Hardcoded Secrets",
        tmp_path / "app.py", 2, "secret", "env var")
    agent.save_baseline()

    data = json.loads((tmp_path / "sec" / "baseline_audit.json").read_text())
    check_ids = [f["check_id"] for f in data["findings"]]
    assert "MED-SEC" in check_ids
    assert not any(c.startswith("WALLET") for c in check_ids)
    assert data["summary"]["total"] == 1


def test_load_baseline_ignores_wallet_entries(tmp_path):
    """Even a hand-edited baseline containing WALLET entries must not
    suppress wallet findings."""
    d = tmp_path / "sec"
    d.mkdir()
    (d / "baseline_audit.json").write_text(json.dumps({
        "findings": [
            {"check_id": "WALLET-001", "file_path": "app.py", "line_number": 1},
            {"check_id": "MED-SEC", "file_path": "app.py", "line_number": 2},
        ]
    }))
    agent = SecurityAgent(tmp_path)
    baseline = agent._load_baseline()
    assert "MED-SEC:app.py:2" in baseline
    assert "WALLET-001:app.py:1" not in baseline
