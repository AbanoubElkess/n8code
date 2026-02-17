#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout.strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    plan_path = root / "config" / "phases.json"
    if not plan_path.exists():
        print(f"Missing plan file: {plan_path}")
        return 1

    gh = shutil.which("gh")
    if not gh:
        print("GitHub CLI (gh) not found on PATH.")
        return 1

    rc_repo, out_repo = run([gh, "repo", "view", "--json", "name"])
    if rc_repo != 0:
        print("No GitHub repository context available for issue creation.")
        print(out_repo)
        print("Fallback: run this in a configured git repo after `gh auth login`.")
        return 1

    rc_auth, out_auth = run([gh, "auth", "status"])
    if rc_auth != 0:
        print("GitHub authentication failed.")
        print(out_auth)
        print("Run: gh auth login -h github.com")
        return 1

    data = json.loads(plan_path.read_text(encoding="utf-8"))
    issues = data.get("issues", [])
    if not issues:
        print("No issues found in phases.json.")
        return 1

    created = 0
    for issue in issues:
        title = f"[{issue['jira_id']}][{issue['phase']}] {issue['title']}"
        cmd = [gh, "issue", "create", "--title", title, "--body", issue["body"]]
        for label in issue.get("labels", []):
            cmd.extend(["--label", label])
        rc, out = run(cmd)
        if rc == 0:
            created += 1
            print(out)
        else:
            print(f"Failed to create issue: {title}")
            print(out)

    print(f"Created {created}/{len(issues)} issues.")
    return 0 if created == len(issues) else 1


if __name__ == "__main__":
    sys.exit(main())

