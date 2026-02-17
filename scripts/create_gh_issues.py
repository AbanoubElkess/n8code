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


def label_color(name: str) -> str:
    palette = {
        "phase-0": "0052CC",
        "phase-1": "0E8A16",
        "phase-2": "5319E7",
        "phase-3": "FBCA04",
        "phase-4": "D93F0B",
        "phase-5": "B60205",
        "program": "1D76DB",
        "governance": "C2E0C6",
        "eval": "EDEDED",
        "market": "5319E7",
        "core": "0E8A16",
        "performance": "FBCA04",
        "quantum": "0052CC",
        "validation": "B60205",
    }
    return palette.get(name, "D4C5F9")


def ensure_labels(gh: str, labels: set[str]) -> None:
    for label in sorted(labels):
        color = label_color(label)
        description = f"Auto-managed label: {label}"
        run([gh, "label", "create", label, "--color", color, "--description", description, "--force"])


def existing_issue_titles(gh: str, limit: int = 200) -> set[str]:
    rc, output = run([gh, "issue", "list", "--state", "all", "--limit", str(limit), "--json", "title"])
    if rc != 0:
        return set()
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return set()
    titles: set[str] = set()
    for item in data:
        title = item.get("title")
        if isinstance(title, str):
            titles.add(title)
    return titles


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

    all_labels: set[str] = set()
    for issue in issues:
        all_labels.update(issue.get("labels", []))
    ensure_labels(gh=gh, labels=all_labels)
    existing_titles = existing_issue_titles(gh=gh)

    created = 0
    skipped = 0
    for issue in issues:
        title = f"[{issue['jira_id']}][{issue['phase']}] {issue['title']}"
        if title in existing_titles:
            skipped += 1
            print(f"Skipped existing issue: {title}")
            continue
        cmd = [gh, "issue", "create", "--title", title, "--body", issue["body"]]
        for label in issue.get("labels", []):
            cmd.extend(["--label", label])
        rc, out = run(cmd)
        if rc == 0:
            created += 1
            print(out)
            existing_titles.add(title)
        else:
            print(f"Failed to create issue: {title}")
            print(out)

    print(f"Created {created}/{len(issues)} issues. Skipped {skipped}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
