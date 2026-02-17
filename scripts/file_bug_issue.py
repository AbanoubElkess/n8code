#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a phase-labeled bug issue via gh issue.")
    parser.add_argument("--jira-id", required=True, help="Example: AGAI-900")
    parser.add_argument("--phase", required=True, help="Example: Phase-2")
    parser.add_argument("--title", required=True, help="Bug title")
    parser.add_argument("--impact", required=True, help="Impact summary")
    parser.add_argument("--repro", required=True, help="Reproduction steps")
    parser.add_argument("--expected", required=True, help="Expected behavior")
    parser.add_argument("--actual", required=True, help="Actual behavior")
    args = parser.parse_args()

    gh = shutil.which("gh")
    if not gh:
        print("gh is not installed.")
        return 1

    body = (
        "Bug Report\n\n"
        f"Jira: {args.jira_id}\n"
        f"Phase: {args.phase}\n"
        f"Impact: {args.impact}\n\n"
        "Reproduction:\n"
        f"{args.repro}\n\n"
        "Expected:\n"
        f"{args.expected}\n\n"
        "Actual:\n"
        f"{args.actual}\n\n"
        "Actions:\n"
        "- [ ] Root cause identified\n"
        "- [ ] Fix implemented\n"
        "- [ ] Regression test added\n"
    )
    title = f"[{args.jira_id}][{args.phase}] BUG: {args.title}"
    cmd = [gh, "issue", "create", "--title", title, "--body", body, "--label", "bug"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(proc.stdout.strip())
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())

