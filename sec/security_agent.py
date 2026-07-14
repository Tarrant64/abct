#!/usr/bin/env python3
"""
ABCT Security Agent
Standby agent that runs security audit before git pushes and prompts for fixes
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
from security_audit import SecurityAuditor, SecurityFinding


class SecurityAgent:
    """Agent that manages security audits and git push workflow"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.auditor = SecurityAuditor(project_root)

    def run_audit(self) -> Tuple[List[SecurityFinding], List[SecurityFinding], List[SecurityFinding]]:
        """
        Run security audit and categorize findings
        Returns: (critical_high, medium, low) findings
        """
        print("\n" + "=" * 80)
        print("ABCT Security Pre-Push Audit")
        print("=" * 80)

        critical, high, medium, low = self.auditor.run_all_checks()

        # Categorize findings
        critical_high = [f for f in self.auditor.findings if f.severity in ["CRITICAL", "HIGH"]]
        medium_findings = [f for f in self.auditor.findings if f.severity == "MEDIUM"]
        low_findings = [f for f in self.auditor.findings if f.severity == "LOW"]

        return critical_high, medium_findings, low_findings

    def display_findings(self, findings: List[SecurityFinding], header: str):
        """Display findings with color coding"""
        if not findings:
            return

        print(f"\n{header}")
        print("-" * 80)

        for f in findings:
            # Color codes
            if f.severity == "CRITICAL":
                color = "\033[91m"  # Red
            elif f.severity == "HIGH":
                color = "\033[93m"  # Yellow
            elif f.severity == "MEDIUM":
                color = "\033[94m"  # Blue
            else:
                color = "\033[90m"  # Gray
            reset = "\033[0m"

            print(f"\n{color}[{f.severity}]{reset} {f.check_id}: {f.check_name}")
            print(f"  File: {f.file_path}:{f.line_number}")
            print(f"  Issue: {f.description}")
            print(f"  Fix: {f.recommendation}")

    def prompt_user(self, question: str) -> bool:
        """Prompt user for yes/no decision. Returns True in non-interactive mode."""
        if not sys.stdin.isatty():
            return True
        while True:
            try:
                response = input(f"\n{question} (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return True
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' or 'n'")

    def generate_generic_commit_message(self, findings: List[SecurityFinding]) -> str:
        """
        Generate generic commit message without exposing vulnerability details
        """
        if not findings:
            return "Security: General security improvements"

        # Count issues by component
        components = {}
        for f in findings:
            if 'backend' in f.file_path:
                component = 'backend'
            elif 'frontend' in f.file_path:
                component = 'frontend'
            elif 'nft-price-service' in f.file_path:
                component = 'NFT service'
            else:
                component = 'core'

            if component not in components:
                components[component] = set()

            # Generic categorization
            if 'auth' in f.check_name.lower():
                components[component].add('authentication')
            elif 'xss' in f.check_name.lower() or 'sanitiz' in f.check_name.lower():
                components[component].add('input sanitization')
            elif 'cors' in f.check_name.lower():
                components[component].add('CORS configuration')
            elif 'error' in f.check_name.lower():
                components[component].add('error handling')
            elif 'validation' in f.check_name.lower():
                components[component].add('input validation')
            elif 'size' in f.check_name.lower() or 'limit' in f.check_name.lower():
                components[component].add('request limiting')
            else:
                components[component].add('security hardening')

        # Build message
        messages = []
        for component, issues in components.items():
            issue_list = ", ".join(sorted(issues))
            messages.append(f"- {component}: {issue_list}")

        commit_msg = "Security: Enhanced security controls\n\n" + "\n".join(messages)
        commit_msg += "\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

        return commit_msg

    def suggest_fixes(self, findings: List[SecurityFinding]):
        """Provide guidance on fixing issues"""
        print("\n" + "=" * 80)
        print("SUGGESTED FIXES")
        print("=" * 80)

        # Group by check type
        by_check = {}
        for f in findings:
            if f.check_id not in by_check:
                by_check[f.check_id] = []
            by_check[f.check_id].append(f)

        for check_id, check_findings in by_check.items():
            print(f"\n{check_id}: {check_findings[0].check_name}")
            print(f"  Affects {len(check_findings)} location(s)")
            print(f"  Recommendation: {check_findings[0].recommendation}")

            # Show first 3 locations
            print(f"  Locations:")
            for f in check_findings[:3]:
                print(f"    - {f.file_path}:{f.line_number}")
            if len(check_findings) > 3:
                print(f"    ... and {len(check_findings) - 3} more")

    def _load_baseline(self) -> set:
        """Load baseline finding signatures from last saved audit report.

        WALLET-* findings are never honored from a baseline: a wallet-address
        leak can only be cleared by removing the address or allowlisting it
        in sec/wallet_allowlist.txt — re-baselining must not absorb one.
        """
        baseline_path = self.project_root / "sec" / "baseline_audit.json"
        if not baseline_path.exists():
            return set()
        try:
            with open(baseline_path) as f:
                data = json.load(f)
            return {
                f"{item['check_id']}:{item['file_path']}:{item['line_number']}"
                for item in data.get("findings", [])
                if not str(item.get("check_id", "")).startswith("WALLET")
            }
        except Exception:
            return set()

    def save_baseline(self):
        """Snapshot current findings as the accepted baseline.

        WALLET-* findings are excluded from the snapshot (see _load_baseline).
        """
        wallet = [f for f in self.auditor.findings if f.check_id.startswith("WALLET")]
        kept = [f for f in self.auditor.findings if not f.check_id.startswith("WALLET")]
        report = {
            "timestamp": datetime.now().isoformat(),
            "project_root": str(self.project_root),
            "summary": {
                "total": len(kept),
                "critical": sum(1 for f in kept if f.severity == "CRITICAL"),
                "high": sum(1 for f in kept if f.severity == "HIGH"),
                "medium": sum(1 for f in kept if f.severity == "MEDIUM"),
                "low": sum(1 for f in kept if f.severity == "LOW"),
            },
            "findings": [f.to_dict() for f in kept],
        }
        baseline_path = self.project_root / "sec" / "baseline_audit.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(baseline_path, "w") as f:
            f.write(json.dumps(report, indent=2))
        print(f"\n✓ Baseline saved to {baseline_path}")
        if wallet:
            print(f"  ({len(wallet)} WALLET-* findings NOT baselined — resolve "
                  f"via sec/wallet_allowlist.txt or by removing the address)")

    def run_pre_push_check(self, remote: str = None, url: str = None) -> int:
        """
        Run pre-push security check.
        Only blocks on NEW findings not present in the baseline.
        Returns: 0 to allow push, 1 to block push
        """
        critical_high, medium, low = self.run_audit()

        total_issues = len(critical_high) + len(medium) + len(low)

        if total_issues == 0:
            print("\n✓ No security issues found. Safe to push!")
            return 0

        # Separate new findings from pre-existing baseline
        baseline = self._load_baseline()
        def is_new(f):
            sig = f"{f.check_id}:{f.file_path}:{f.line_number}"
            return sig not in baseline

        new_critical_high = [f for f in critical_high if is_new(f)]
        new_medium = [f for f in medium if is_new(f)]
        new_low = [f for f in low if is_new(f)]
        new_total = len(new_critical_high) + len(new_medium) + len(new_low)

        # Display new findings (if any)
        if new_critical_high:
            self.display_findings(new_critical_high, "NEW CRITICAL/HIGH SEVERITY ISSUES (BLOCKING)")
        if new_medium:
            self.display_findings(new_medium, "NEW MEDIUM SEVERITY ISSUES (WARNING)")
        if new_low:
            self.display_findings(new_low, "NEW LOW SEVERITY ISSUES (INFO)")

        # Summary
        print("\n" + "=" * 80)
        baseline_count = total_issues - new_total
        print(f"NEW ISSUES: {new_total} ({len(new_critical_high)} critical/high, "
              f"{len(new_medium)} medium, {len(new_low)} low)")
        if baseline_count > 0:
            print(f"PRE-EXISTING (baseline): {baseline_count} (not blocking)")
        print("=" * 80)

        # Only block on NEW critical/high issues
        if new_critical_high:
            print("\n⚠️  NEW critical/high severity issues found!")
            print("These issues should be fixed before pushing to production.")
            self.suggest_fixes(new_critical_high)

            if self.prompt_user("Would you like to fix these issues before pushing?"):
                print("\nPlease fix the issues listed above and try pushing again.")
                print("Blocking push until issues are resolved.")
                return 1
            else:
                print("\n⚠️  WARNING: Proceeding with push despite new critical/high issues!")
                if not self.prompt_user("Are you sure you want to continue?"):
                    print("Push cancelled.")
                    return 1

        # Warn about new medium/low issues but don't block
        if new_medium or new_low:
            print(f"\nℹ️  Found {len(new_medium)} new medium and {len(new_low)} new low severity issues.")
            print("These are warnings and won't block the push.")
            if new_medium:
                self.suggest_fixes(new_medium)

        # If no new issues at all, just let it through
        if new_total == 0:
            print(f"\n✓ No new security issues. {baseline_count} pre-existing issues in baseline.")
            print("Proceeding with push...")
            return 0

        # Ask if user wants to proceed (only when there are new non-critical findings)
        if not self.prompt_user("Proceed with git push?"):
            print("Push cancelled by user.")
            return 1

        print("\n✓ Security check complete. Proceeding with push...")
        return 0

    def save_audit_report(self, output_file: Path = None):
        """Save audit report to file"""
        if output_file is None:
            output_file = self.project_root / "sec" / "last_audit.json"

        report = self.auditor.generate_report(format="json")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(report)

        print(f"\nAudit report saved to: {output_file}")


def main():
    """Main entry point for security agent"""
    import argparse

    parser = argparse.ArgumentParser(description="ABCT Security Agent")
    parser.add_argument("--project-root", type=str, default=".",
                       help="Project root directory")
    parser.add_argument("--mode", choices=["pre-push", "audit"], default="pre-push",
                       help="Operation mode")
    parser.add_argument("--remote", type=str,
                       help="Git remote (for pre-push hook)")
    parser.add_argument("--url", type=str,
                       help="Git remote URL (for pre-push hook)")
    parser.add_argument("--save-report", type=str,
                       help="Save audit report to file")
    parser.add_argument("--save-baseline", action="store_true",
                       help="Snapshot current findings as accepted baseline")

    args = parser.parse_args()

    # Determine project root
    project_root = Path(args.project_root).resolve()

    # If in Deployment directory, check if we should use parent
    if project_root.name == "Deployment":
        backend_dir = project_root / "backend"
        if not backend_dir.exists():
            project_root = project_root.parent

    # Create agent
    agent = SecurityAgent(project_root)

    if args.save_baseline:
        agent.run_audit()
        agent.save_baseline()
        print(f"Baseline contains {len(agent.auditor.findings)} findings.")
        print("Future pushes will only block on NEW issues not in this baseline.")
        sys.exit(0)

    if args.mode == "pre-push":
        # Run pre-push check
        exit_code = agent.run_pre_push_check(remote=args.remote, url=args.url)

        # Save report if requested
        if args.save_report:
            agent.save_audit_report(Path(args.save_report))

        sys.exit(exit_code)

    elif args.mode == "audit":
        # Run audit only
        critical_high, medium, low = agent.run_audit()

        # Display all findings
        if critical_high:
            agent.display_findings(critical_high, "CRITICAL/HIGH SEVERITY ISSUES")
        if medium:
            agent.display_findings(medium, "MEDIUM SEVERITY ISSUES")
        if low:
            agent.display_findings(low, "LOW SEVERITY ISSUES")

        # Summary
        total = len(critical_high) + len(medium) + len(low)
        print(f"\nTotal: {total} issues ({len(critical_high)} critical/high, "
              f"{len(medium)} medium, {len(low)} low)")

        # Save report if requested
        if args.save_report:
            agent.save_audit_report(Path(args.save_report))

        sys.exit(0)


if __name__ == "__main__":
    main()
