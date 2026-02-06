#!/usr/bin/env python3
"""
ABCT Security Audit Script
Automated security checks for pre-commit/pre-push validation
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

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
            "archive"
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
                                'Depends(require_localhost)' in l or
                                'user: str = Depends' in l
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
                    # Check for unsafe innerHTML usage
                    if 'innerHTML' in line and 'DOMPurify' not in line and 'setSafeHTML' not in line:
                        # Skip comments
                        if line.strip().startswith('//') or line.strip().startswith('*'):
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
