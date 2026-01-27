#!/usr/bin/env python3
"""
ABCT Security Agent
Standby agent that runs security audit before git pushes and prompts for fixes
"""

import os
import sys
import json
import subprocess
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
        """Prompt user for yes/no decision"""
        while True:
            response = input(f"\n{question} (y/n): ").strip().lower()
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

    def run_pre_push_check(self, remote: str = None, url: str = None) -> int:
        """
        Run pre-push security check
        Returns: 0 to allow push, 1 to block push
        """
        critical_high, medium, low = self.run_audit()

        total_issues = len(critical_high) + len(medium) + len(low)

        if total_issues == 0:
            print("\n✓ No security issues found. Safe to push!")
            return 0

        # Display all findings
        if critical_high:
            self.display_findings(critical_high, "CRITICAL/HIGH SEVERITY ISSUES (BLOCKING)")

        if medium:
            self.display_findings(medium, "MEDIUM SEVERITY ISSUES (WARNING)")

        if low:
            self.display_findings(low, "LOW SEVERITY ISSUES (INFO)")

        print("\n" + "=" * 80)
        print(f"TOTAL: {len(critical_high)} Critical/High, {len(medium)} Medium, {len(low)} Low")
        print("=" * 80)

        # Handle critical/high issues
        if critical_high:
            print("\n⚠️  CRITICAL/HIGH severity issues found!")
            print("These issues should be fixed before pushing to production.")

            self.suggest_fixes(critical_high)

            if self.prompt_user("Would you like to fix these issues before pushing?"):
                print("\nPlease fix the issues listed above and try pushing again.")
                print("Blocking push until issues are resolved.")
                return 1
            else:
                print("\n⚠️  WARNING: Proceeding with push despite critical/high issues!")
                if not self.prompt_user("Are you sure you want to continue?"):
                    print("Push cancelled.")
                    return 1

        # Handle medium/low issues (warning only)
        if medium or low:
            print(f"\nℹ️  Found {len(medium)} medium and {len(low)} low severity issues.")
            print("These are informational warnings and won't block the push.")

            if medium:
                print("\nMedium severity issues should be addressed in future commits.")
                self.suggest_fixes(medium)

        # Ask if user wants to proceed
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
