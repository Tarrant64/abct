#!/usr/bin/env python3
"""
ABCT Security Audit Script
Automated security checks for pre-commit/pre-push validation
"""

import os
import re
import json
import sys
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Wallet-address validation helpers (WALLET-* checks)
#
# Checksum verification is done wherever the address format supports it with
# stdlib primitives only (sha256d for Base58Check, the BIP-173/350 polymod
# for bech32/bech32m, blake2b for SS58). A candidate that fails its checksum
# is NOT a wallet address and is never flagged — this is what keeps hashes,
# identifiers, and random base58-ish tokens from producing false positives.
# ---------------------------------------------------------------------------

_B58_BTC_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_XRP_ALPHABET = "rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz"

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _b58decode(s: str, alphabet: str = _B58_BTC_ALPHABET) -> Optional[bytes]:
    """Decode a base58 string; None on any invalid character."""
    num = 0
    for ch in s:
        idx = alphabet.find(ch)
        if idx == -1:
            return None
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    # Leading zero bytes are encoded as the alphabet's zero character
    pad = 0
    zero = alphabet[0]
    for ch in s:
        if ch == zero:
            pad += 1
        else:
            break
    return b"\x00" * pad + raw


def _b58check_valid(s: str, alphabet: str = _B58_BTC_ALPHABET) -> bool:
    """True if s is valid Base58Check (4-byte double-SHA256 checksum)."""
    raw = _b58decode(s, alphabet)
    if raw is None or len(raw) < 5:
        return False
    payload, checksum = raw[:-4], raw[-4:]
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] == checksum


def _bech32_polymod(values) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= gen[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_valid(addr: str) -> Optional[str]:
    """Verify bech32/bech32m checksum. Returns the hrp if valid, else None."""
    if addr != addr.lower() and addr != addr.upper():
        return None  # mixed case is invalid bech32
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        return None
    hrp, data_part = addr[:pos], addr[pos + 1:]
    data = []
    for ch in data_part:
        idx = _BECH32_CHARSET.find(ch)
        if idx == -1:
            return None
        data.append(idx)
    const = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if const in (1, 0x2BC830A3):  # bech32, bech32m
        return hrp
    return None


def _ss58_valid(s: str) -> bool:
    """Verify a short-form SS58 (Substrate/Polkadot) address checksum."""
    raw = _b58decode(s)
    if raw is None or len(raw) != 35:  # 1-byte type + 32-byte key + 2 checksum
        return False
    check = hashlib.blake2b(b"SS58PRE" + raw[:-2], digest_size=64).digest()[:2]
    return check == raw[-2:]

@dataclass
class SecurityFinding:
    """Represents a security vulnerability finding"""
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    check_id: str
    check_name: str
    file_path: str
    line_number: int
    description: str
    recommendation: str

    def to_dict(self):
        return asdict(self)


class SecurityAuditor:
    """Performs automated security checks on ABCT codebase"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.findings: List[SecurityFinding] = []

        # Define file patterns to check
        self.python_files = list(project_root.rglob("*.py"))
        self.html_files = list(project_root.rglob("*.html"))
        self.js_files = list(project_root.rglob("*.js"))

        # Exclude certain directories
        self.exclude_patterns = [
            "__pycache__",
            ".git",
            "node_modules",
            "venv",
            ".pytest_cache",
            "backups",
            "archive",
            "EXCLUDE",
            "/sec/"
        ]

        self._filter_excluded_files()

    def _filter_excluded_files(self):
        """Remove files in excluded directories"""
        def should_include(file_path: Path) -> bool:
            return not any(pattern in str(file_path) for pattern in self.exclude_patterns)

        self.python_files = [f for f in self.python_files if should_include(f)]
        self.html_files = [f for f in self.html_files if should_include(f)]
        self.js_files = [f for f in self.js_files if should_include(f)]

    def add_finding(self, severity: str, check_id: str, check_name: str,
                   file_path: Path, line_number: int, description: str,
                   recommendation: str):
        """Add a security finding"""
        finding = SecurityFinding(
            severity=severity,
            check_id=check_id,
            check_name=check_name,
            file_path=str(file_path.relative_to(self.project_root)),
            line_number=line_number,
            description=description,
            recommendation=recommendation
        )
        self.findings.append(finding)

    def check_auth_on_endpoints(self):
        """CRIT-001: Check for authentication on state-changing endpoints"""
        check_id = "CRIT-001"
        check_name = "Missing Authentication on State-Changing Endpoints"

        # Look for FastAPI endpoints without authentication
        protected_methods = ["POST", "PUT", "DELETE", "PATCH"]

        for py_file in self.python_files:
            if "routers" not in str(py_file):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    # Check for router decorators
                    for method in protected_methods:
                        pattern = rf'@router\.{method.lower()}\('
                        if re.search(pattern, line, re.IGNORECASE):
                            # Check next 5 lines for auth dependency
                            check_lines = lines[i:min(i+5, len(lines))]
                            has_auth = any(
                                'Depends(verify_admin)' in l or
                                'Depends(verify_session)' in l or
                                'Depends(verify_session_sse)' in l or
                                'Depends(verify_session_optional)' in l or
                                'Depends(require_localhost)' in l or
                                'user: str = Depends' in l or
                                'user_id: int = Depends' in l
                                for l in check_lines
                            )

                            if not has_auth and 'health' not in line:
                                self.add_finding(
                                    severity="CRITICAL",
                                    check_id=check_id,
                                    check_name=check_name,
                                    file_path=py_file,
                                    line_number=i,
                                    description=f"{method} endpoint without authentication dependency",
                                    recommendation="Add user: str = Depends(verify_admin) parameter"
                                )
            except Exception as e:
                print(f"Warning: Could not check {py_file}: {e}", file=sys.stderr)

    def check_xss_vulnerabilities(self):
        """HIGH-001: Check for XSS vulnerabilities in JavaScript"""
        check_id = "HIGH-001"
        check_name = "Potential XSS via innerHTML"

        for js_file in self.js_files:
            try:
                with open(js_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    # Check for unsafe innerHTML assignment (write, not read)
                    if '.innerHTML' in line and 'DOMPurify' not in line and 'setSafeHTML' not in line:
                        # Skip comments
                        if line.strip().startswith('//') or line.strip().startswith('*'):
                            continue
                        # Skip innerHTML reads (no assignment operator after innerHTML)
                        # Match patterns like `.innerHTML =` but not `.innerHTML.trim()` or `.innerHTML}`
                        if not re.search(r'\.innerHTML\s*=', line):
                            continue

                        self.add_finding(
                            severity="HIGH",
                            check_id=check_id,
                            check_name=check_name,
                            file_path=js_file,
                            line_number=i,
                            description="Direct innerHTML assignment without sanitization",
                            recommendation="Use setSafeHTML() or DOMPurify.sanitize()"
                        )
            except Exception as e:
                print(f"Warning: Could not check {js_file}: {e}", file=sys.stderr)

    def check_dompurify_loaded(self):
        """HIGH-001: Check that DOMPurify is loaded in HTML files"""
        check_id = "HIGH-001-DEP"
        check_name = "Missing DOMPurify Library"

        for html_file in self.html_files:
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                if 'dompurify' not in content.lower():
                    self.add_finding(
                        severity="HIGH",
                        check_id=check_id,
                        check_name=check_name,
                        file_path=html_file,
                        line_number=1,
                        description="HTML file does not load DOMPurify library",
                        recommendation='Add <script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.8/dist/purify.min.js"></script>'
                    )
            except Exception as e:
                print(f"Warning: Could not check {html_file}: {e}", file=sys.stderr)

    def check_cors_configuration(self):
        """CRIT-002: Check for overly permissive CORS"""
        check_id = "CRIT-002"
        check_name = "Overly Permissive CORS Configuration"

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    if 'CORSMiddleware' in line or 'allow_origins' in line:
                        # Check for wildcard CORS
                        if 'allow_origins=["*"]' in line or "allow_origins=['*']" in line:
                            self.add_finding(
                                severity="CRITICAL",
                                check_id=check_id,
                                check_name=check_name,
                                file_path=py_file,
                                line_number=i,
                                description="CORS configured with wildcard (*) origins",
                                recommendation="Restrict to specific origins or use environment variable"
                            )

                        # Check for allow_credentials with wildcard
                        if 'allow_credentials=True' in line:
                            # Check surrounding lines for wildcard
                            context = '\n'.join(lines[max(0, i-3):min(i+3, len(lines))])
                            if '["*"]' in context or "['*']" in context:
                                self.add_finding(
                                    severity="CRITICAL",
                                    check_id=check_id,
                                    check_name=check_name,
                                    file_path=py_file,
                                    line_number=i,
                                    description="allow_credentials=True with wildcard origins",
                                    recommendation="Set allow_credentials=False or restrict origins"
                                )
            except Exception as e:
                print(f"Warning: Could not check {py_file}: {e}", file=sys.stderr)

    def check_error_disclosure(self):
        """CRIT-003: Check for error information disclosure"""
        check_id = "CRIT-003"
        check_name = "Detailed Error Information Disclosure"

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    # Check for exception re-raising with details
                    if 'raise HTTPException' in line and 'str(e)' in line:
                        # Check if it's in an exception handler
                        context = '\n'.join(lines[max(0, i-10):i])
                        if 'except' in context and 'logging_service' not in context:
                            self.add_finding(
                                severity="HIGH",
                                check_id=check_id,
                                check_name=check_name,
                                file_path=py_file,
                                line_number=i,
                                description="Exception details exposed in HTTP response",
                                recommendation="Log full error, return generic message to client"
                            )
            except Exception as e:
                print(f"Warning: Could not check {py_file}: {e}", file=sys.stderr)

    def check_request_size_limits(self):
        """HIGH-002: Check for request size limiting"""
        check_id = "HIGH-002"
        check_name = "Missing Request Size Limits"

        # Check main.py for size limit middleware
        main_files = [f for f in self.python_files if f.name == 'main.py']

        for main_file in main_files:
            try:
                with open(main_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                if 'size_limit' not in content and 'SizeLimitMiddleware' not in content:
                    self.add_finding(
                        severity="HIGH",
                        check_id=check_id,
                        check_name=check_name,
                        file_path=main_file,
                        line_number=1,
                        description="No request size limiting middleware detected",
                        recommendation="Add size_limit middleware to prevent DoS attacks"
                    )
            except Exception as e:
                print(f"Warning: Could not check {main_file}: {e}", file=sys.stderr)

    def check_network_binding(self):
        """HIGH-003: Check for insecure network binding"""
        check_id = "HIGH-003"
        check_name = "Insecure Network Binding"

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    # Check for uvicorn.run with 0.0.0.0
                    if 'uvicorn.run' in line and '0.0.0.0' in line:
                        self.add_finding(
                            severity="MEDIUM",
                            check_id=check_id,
                            check_name=check_name,
                            file_path=py_file,
                            line_number=i,
                            description="Server binding to all interfaces (0.0.0.0)",
                            recommendation="Bind to 127.0.0.1 or use environment variable"
                        )
            except Exception as e:
                print(f"Warning: Could not check {py_file}: {e}", file=sys.stderr)

    def check_input_validation(self):
        """MED-004: Check for input validation on file uploads"""
        check_id = "MED-004"
        check_name = "Insufficient Input Validation"

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    # Check for file upload endpoints
                    if 'UploadFile' in line and '@router' in '\n'.join(lines[max(0,i-5):i]):
                        # Check next 20 lines for validation
                        check_lines = lines[i:min(i+20, len(lines))]
                        has_validation = any(
                            'filename' in l and ('endswith' in l or 'allowed' in l)
                            for l in check_lines
                        )

                        if not has_validation:
                            self.add_finding(
                                severity="MEDIUM",
                                check_id=check_id,
                                check_name=check_name,
                                file_path=py_file,
                                line_number=i,
                                description="File upload without extension/type validation",
                                recommendation="Validate file extensions and MIME types"
                            )
            except Exception as e:
                print(f"Warning: Could not check {py_file}: {e}", file=sys.stderr)

    def check_secrets_in_code(self):
        """MEDIUM: Check for hardcoded secrets"""
        check_id = "MED-SEC"
        check_name = "Potential Hardcoded Secrets"

        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
            (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
        ]

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    for pattern, desc in secret_patterns:
                        # Skip if using os.getenv
                        if 'os.getenv' in line or 'os.environ' in line:
                            continue

                        if re.search(pattern, line, re.IGNORECASE):
                            self.add_finding(
                                severity="MEDIUM",
                                check_id=check_id,
                                check_name=check_name,
                                file_path=py_file,
                                line_number=i,
                                description=desc,
                                recommendation="Use environment variables or secure secret management"
                            )
            except Exception as e:
                print(f"Warning: Could not check {py_file}: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # WALLET-*: wallet-address leak detection
    # ------------------------------------------------------------------

    WALLET_TEXT_EXTENSIONS = {
        ".py", ".js", ".html", ".css", ".md", ".txt", ".json", ".yaml",
        ".yml", ".sh", ".xml", ".example", ".cfg", ".ini", ".toml", ".sql",
        ".env", ".conf",
    }
    WALLET_MAX_FILE_BYTES = 1_000_000
    _SOLANA_CONTEXT = re.compile(
        r"wallet|address|pubkey|public[_ ]key|account|recipient|solana|\bsol\b",
        re.IGNORECASE,
    )

    # (name, regex, validator) — validator returns True when the candidate is
    # a checksum-valid address of that chain.
    _WALLET_VALIDATED_PATTERNS = [
        ("Cardano",
         re.compile(r"\b(?:addr|stake)(?:_test)?1[02-9ac-hj-np-z]{20,110}\b"),
         lambda m: _bech32_valid(m) in ("addr", "stake", "addr_test", "stake_test")),
        ("Bitcoin bech32",
         re.compile(r"\bbc1[02-9ac-hj-np-z]{11,87}\b"),
         lambda m: _bech32_valid(m) == "bc"),
        ("Cosmos-family",
         re.compile(r"\b(?:cosmos|osmo)1[02-9ac-hj-np-z]{20,60}\b"),
         lambda m: _bech32_valid(m) in ("cosmos", "osmo")),
        ("Bitcoin/Litecoin/Dogecoin/TRON base58",
         re.compile(r"\b[13LMDT][1-9A-HJ-NP-Za-km-z]{24,34}\b"),
         lambda m: _b58check_valid(m)),
        ("XRP",
         re.compile(r"\br[1-9A-HJ-NP-Za-km-z]{24,34}\b"),
         lambda m: _b58check_valid(m, _B58_XRP_ALPHABET)),
        ("Polkadot SS58",
         re.compile(r"\b1[1-9A-HJ-NP-Za-km-z]{44,47}\b"),
         lambda m: _ss58_valid(m)),
    ]
    _EVM_PATTERN = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
    _SOLANA_PATTERN = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

    def _load_wallet_allowlist(self) -> set:
        """Addresses the repo legitimately contains (spec vectors, protocol
        contracts, demo data). One address per line; # comments allowed."""
        path = self.project_root / "sec" / "wallet_allowlist.txt"
        allow = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    allow.add(line)
        return allow

    def _wallet_scan_files(self) -> List[Path]:
        """Scan git-TRACKED text files only — untracked/ignored files cannot
        leak through a push, and scanning them (local .env, venvs) would
        produce blocking false positives. Falls back to the auditor's file
        lists if git is unavailable."""
        try:
            out = subprocess.run(
                ["git", "ls-files"], cwd=self.project_root,
                capture_output=True, text=True, check=True, timeout=30,
            ).stdout.splitlines()
            files = [self.project_root / p for p in out]
        except Exception:
            files = self.python_files + self.js_files + self.html_files
        result = []
        for f in files:
            rel = str(f.relative_to(self.project_root)) if f.is_absolute() else str(f)
            if rel.startswith("sec/"):
                continue  # the allowlist itself and audit tooling
            if f.suffix.lower() not in self.WALLET_TEXT_EXTENSIONS:
                continue
            try:
                if f.stat().st_size > self.WALLET_MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            result.append(f)
        return result

    def check_wallet_addresses(self):
        """WALLET-001/002/003/004: wallet-address leak detection.

        - WALLET-001 (CRITICAL, blocks): checksum-VALIDATED address of any
          supported chain that is not in sec/wallet_allowlist.txt.
        - WALLET-002 (HIGH, blocks): EVM 0x address in EIP-55 mixed case
          (case pattern implies a checksummed real address; true keccak
          verification needs a non-stdlib dependency, so case is the signal).
        - WALLET-003 (MEDIUM, warns): EVM 0x address in uniform case —
          could be a contract constant or copied address.
        - WALLET-004 (MEDIUM, warns): Solana-shaped base58 on a line with
          wallet context words. Solana has no checksum, so this class is
          context-gated to stay usable.

        WALLET-* findings are excluded from the accepted baseline snapshot:
        the ONLY way to clear one is to remove the address or explicitly
        allowlist it. A re-baseline cannot wave a wallet leak through.
        """
        allowlist = self._load_wallet_allowlist()

        for path in self._wallet_scan_files():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                claimed_spans = []

                def overlaps(span):
                    return any(s < span[1] and span[0] < e for s, e in claimed_spans)

                for chain, pattern, validator in self._WALLET_VALIDATED_PATTERNS:
                    for m in pattern.finditer(line):
                        addr = m.group(0)
                        if not validator(addr):
                            continue
                        claimed_spans.append(m.span())
                        if addr in allowlist:
                            continue
                        self.add_finding(
                            severity="CRITICAL",
                            check_id="WALLET-001",
                            check_name=f"Wallet Address Leak ({chain})",
                            file_path=path,
                            line_number=lineno,
                            description=(f"Checksum-valid {chain} address "
                                         f"{addr[:12]}… not in the allowlist"),
                            recommendation=("Remove the address, or if it is a "
                                            "public/spec/demo constant add the full "
                                            "address to sec/wallet_allowlist.txt"),
                        )

                for m in self._EVM_PATTERN.finditer(line):
                    addr = m.group(0)
                    if overlaps(m.span()):
                        continue
                    claimed_spans.append(m.span())
                    if addr in allowlist:
                        continue
                    hex_part = addr[2:]
                    mixed_case = (hex_part != hex_part.lower()
                                  and hex_part != hex_part.upper())
                    if mixed_case:
                        self.add_finding(
                            severity="HIGH",
                            check_id="WALLET-002",
                            check_name="Wallet Address Leak (EVM, EIP-55 case)",
                            file_path=path,
                            line_number=lineno,
                            description=(f"EIP-55 mixed-case EVM address "
                                         f"{addr[:12]}… not in the allowlist"),
                            recommendation=("Remove the address or add it to "
                                            "sec/wallet_allowlist.txt"),
                        )
                    else:
                        self.add_finding(
                            severity="MEDIUM",
                            check_id="WALLET-003",
                            check_name="Possible Wallet Address (EVM, uniform case)",
                            file_path=path,
                            line_number=lineno,
                            description=(f"EVM-shaped address {addr[:12]}… "
                                         f"(uniform case) not in the allowlist"),
                            recommendation=("Verify it is not a personal wallet; "
                                            "allowlist contract constants in "
                                            "sec/wallet_allowlist.txt"),
                        )

                if self._SOLANA_CONTEXT.search(line):
                    for m in self._SOLANA_PATTERN.finditer(line):
                        addr = m.group(0)
                        if overlaps(m.span()) or addr in allowlist:
                            continue
                        # Pure-hex tokens are hashes/ids, not base58 addresses
                        if re.fullmatch(r"[0-9a-fA-F]+", addr):
                            continue
                        self.add_finding(
                            severity="MEDIUM",
                            check_id="WALLET-004",
                            check_name="Possible Wallet Address (Solana-shaped base58)",
                            file_path=path,
                            line_number=lineno,
                            description=(f"Solana-shaped base58 string "
                                         f"{addr[:12]}… on a wallet-context line"),
                            recommendation=("Verify it is not a personal wallet; "
                                            "allowlist legitimate constants in "
                                            "sec/wallet_allowlist.txt"),
                        )

    def run_all_checks(self) -> Tuple[int, int, int, int]:
        """Run all security checks and return counts by severity"""
        print("Running security audit...", file=sys.stderr)

        checks = [
            ("Authentication on endpoints", self.check_auth_on_endpoints),
            ("XSS vulnerabilities", self.check_xss_vulnerabilities),
            ("DOMPurify library", self.check_dompurify_loaded),
            ("CORS configuration", self.check_cors_configuration),
            ("Error disclosure", self.check_error_disclosure),
            ("Request size limits", self.check_request_size_limits),
            ("Network binding", self.check_network_binding),
            ("Input validation", self.check_input_validation),
            ("Hardcoded secrets", self.check_secrets_in_code),
            ("Wallet address leakage", self.check_wallet_addresses),
        ]

        for check_name, check_func in checks:
            print(f"  Checking {check_name}...", file=sys.stderr)
            try:
                check_func()
            except Exception as e:
                print(f"  Error in {check_name}: {e}", file=sys.stderr)

        # Count by severity
        critical = sum(1 for f in self.findings if f.severity == "CRITICAL")
        high = sum(1 for f in self.findings if f.severity == "HIGH")
        medium = sum(1 for f in self.findings if f.severity == "MEDIUM")
        low = sum(1 for f in self.findings if f.severity == "LOW")

        return critical, high, medium, low

    def generate_report(self, format: str = "json") -> str:
        """Generate audit report in specified format"""
        if format == "json":
            report = {
                "timestamp": datetime.now().isoformat(),
                "project_root": str(self.project_root),
                "summary": {
                    "total": len(self.findings),
                    "critical": sum(1 for f in self.findings if f.severity == "CRITICAL"),
                    "high": sum(1 for f in self.findings if f.severity == "HIGH"),
                    "medium": sum(1 for f in self.findings if f.severity == "MEDIUM"),
                    "low": sum(1 for f in self.findings if f.severity == "LOW"),
                },
                "findings": [f.to_dict() for f in self.findings]
            }
            return json.dumps(report, indent=2)

        elif format == "text":
            lines = []
            lines.append("=" * 80)
            lines.append("ABCT Security Audit Report")
            lines.append("=" * 80)
            lines.append(f"Timestamp: {datetime.now().isoformat()}")
            lines.append(f"Project Root: {self.project_root}")
            lines.append("")

            summary = {
                "CRITICAL": sum(1 for f in self.findings if f.severity == "CRITICAL"),
                "HIGH": sum(1 for f in self.findings if f.severity == "HIGH"),
                "MEDIUM": sum(1 for f in self.findings if f.severity == "MEDIUM"),
                "LOW": sum(1 for f in self.findings if f.severity == "LOW"),
            }

            lines.append("Summary:")
            lines.append(f"  Total Findings: {len(self.findings)}")
            for severity, count in summary.items():
                lines.append(f"  {severity}: {count}")
            lines.append("")

            if self.findings:
                lines.append("Findings:")
                lines.append("-" * 80)

                for f in sorted(self.findings, key=lambda x: (x.severity, x.file_path)):
                    lines.append(f"\n[{f.severity}] {f.check_id}: {f.check_name}")
                    lines.append(f"  File: {f.file_path}:{f.line_number}")
                    lines.append(f"  Description: {f.description}")
                    lines.append(f"  Recommendation: {f.recommendation}")
            else:
                lines.append("No security issues found!")

            lines.append("\n" + "=" * 80)
            return "\n".join(lines)

        else:
            raise ValueError(f"Unknown format: {format}")


def main():
    """Main entry point for security audit script"""
    import argparse

    parser = argparse.ArgumentParser(description="ABCT Security Audit")
    parser.add_argument("--project-root", type=str, default=".",
                       help="Project root directory (default: current directory)")
    parser.add_argument("--format", choices=["json", "text"], default="text",
                       help="Output format (default: text)")
    parser.add_argument("--output", type=str,
                       help="Output file (default: stdout)")
    parser.add_argument("--exit-code", action="store_true",
                       help="Exit with non-zero code if critical/high issues found")

    args = parser.parse_args()

    # Determine project root
    project_root = Path(args.project_root).resolve()

    # Check if this is Deployment directory, use parent if so
    if project_root.name == "Deployment":
        # Check if we should scan Deployment or parent
        backend_dir = project_root / "backend"
        if backend_dir.exists():
            # Scan Deployment directory
            pass
        else:
            # Use parent ABCT directory
            project_root = project_root.parent

    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    # Run audit
    auditor = SecurityAuditor(project_root)
    critical, high, medium, low = auditor.run_all_checks()

    # Generate report
    report = auditor.generate_report(format=args.format)

    # Output report
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)

    # Print summary to stderr
    print(f"\nSummary: {critical} CRITICAL, {high} HIGH, {medium} MEDIUM, {low} LOW",
          file=sys.stderr)

    # Exit with appropriate code
    if args.exit_code and (critical > 0 or high > 0):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
