from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReleaseStatusEvaluator:
    def __init__(self, policy_path: str = "config/repro_policy.json") -> None:
        self.policy_path = Path(policy_path)

    def _load_policy(self) -> dict[str, Any]:
        default_policy: dict[str, Any] = {
            "hard_suite_absolute_win_required": True,
            "moonshot_general_benchmarks_gate": False,
            "min_comparable_external_baselines_for_external_claim": 1,
        }
        if not self.policy_path.exists():
            return default_policy
        try:
            payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
            release_gates = payload.get("release_gates", {})
            return {
                "hard_suite_absolute_win_required": bool(
                    release_gates.get("hard_suite_absolute_win_required", True)
                ),
                "moonshot_general_benchmarks_gate": bool(
                    release_gates.get("moonshot_general_benchmarks_gate", False)
                ),
                "min_comparable_external_baselines_for_external_claim": int(
                    release_gates.get("min_comparable_external_baselines_for_external_claim", 1)
                ),
            }
        except Exception:  # noqa: BLE001
            return default_policy

    def evaluate(self, eval_report: dict[str, Any]) -> dict[str, Any]:
        policy = self._load_policy()
        progress = eval_report.get("benchmark_progress", {})
        gaps = progress.get("gaps", {})
        hard_suite_ready = bool(progress.get("ready", False))
        remaining_distance = float(gaps.get("remaining_distance", 0.0))

        comparable_external = self._count_comparable_external(eval_report)
        required_external = max(1, int(policy["min_comparable_external_baselines_for_external_claim"]))
        external_claim_distance = max(0, required_external - comparable_external)
        external_claim_ready = comparable_external >= required_external
        external_blockers = self._external_blockers(eval_report)
        non_comparable_external = self._count_non_comparable_external(eval_report)

        moonshot_summary = eval_report.get("moonshot_tracking", {}).get("summary", {})
        moonshot_gate_enabled = bool(policy["moonshot_general_benchmarks_gate"])
        moonshot_signal = float(moonshot_summary.get("best_signal", 0.0))
        moonshot_gate_pass = True
        moonshot_gate_reason = "moonshot gate disabled by policy"
        if moonshot_gate_enabled:
            moonshot_gate_pass = moonshot_signal > 0.0
            moonshot_gate_reason = (
                "moonshot signal present"
                if moonshot_gate_pass
                else "moonshot gate enabled but no positive signal observed"
            )

        hard_suite_gate_pass = True
        hard_suite_gate_reason = "hard-suite gate disabled by policy"
        if bool(policy["hard_suite_absolute_win_required"]):
            hard_suite_gate_pass = hard_suite_ready
            hard_suite_gate_reason = (
                "hard-suite release target reached"
                if hard_suite_gate_pass
                else "hard-suite release target not reached"
            )

        release_ready_internal = hard_suite_gate_pass and moonshot_gate_pass
        if not release_ready_internal:
            claim_scope = "not-ready-for-release-claims"
        elif external_claim_ready:
            claim_scope = "internal-and-declared-external-comparative"
        else:
            claim_scope = "internal-comparative-only"

        return {
            "status": "ok",
            "release_ready_internal": release_ready_internal,
            "external_claim_ready": external_claim_ready,
            "claim_scope": claim_scope,
            "policy": {
                "hard_suite_absolute_win_required": bool(policy["hard_suite_absolute_win_required"]),
                "moonshot_general_benchmarks_gate": moonshot_gate_enabled,
                "min_comparable_external_baselines_for_external_claim": required_external,
            },
            "gates": {
                "hard_suite_gate": {
                    "pass": hard_suite_gate_pass,
                    "reason": hard_suite_gate_reason,
                    "remaining_distance": remaining_distance,
                },
                "moonshot_gate": {
                    "pass": moonshot_gate_pass,
                    "reason": moonshot_gate_reason,
                    "best_signal": moonshot_signal,
                },
                "external_claim_gate": {
                    "pass": external_claim_ready,
                    "reason": (
                        "external comparable baseline threshold reached"
                        if external_claim_ready
                        else "external comparable baseline threshold not reached"
                    ),
                    "comparable_external_baselines": comparable_external,
                    "required_external_baselines": required_external,
                    "external_claim_distance": external_claim_distance,
                    "non_comparable_external_baselines": non_comparable_external,
                    "blockers": external_blockers,
                },
            },
            "disclaimer": (
                "Internal release readiness does not imply external leaderboard parity unless "
                "external_claim_gate.pass=true."
            ),
        }

    def _count_comparable_external(self, eval_report: dict[str, Any]) -> int:
        comparison = eval_report.get("declared_baseline_comparison", {})
        rows = comparison.get("comparisons", [])
        if not isinstance(rows, list) or not rows:
            summary = comparison.get("summary", {})
            if isinstance(summary, dict):
                return int(summary.get("comparable_external_baselines", 0))
            return 0
        count = 0
        for row in rows:
            source_type = str(row.get("source_type", "")).lower()
            comparable = bool(row.get("comparability", {}).get("comparable", False))
            if comparable and source_type.startswith("external"):
                count += 1
        return count

    def _external_blockers(self, eval_report: dict[str, Any]) -> dict[str, int]:
        comparison = eval_report.get("declared_baseline_comparison", {})
        rows = comparison.get("comparisons", [])
        counts: dict[str, int] = {}
        if not isinstance(rows, list):
            return counts
        for row in rows:
            source_type = str(row.get("source_type", "")).lower()
            if not source_type.startswith("external"):
                continue
            comparability = row.get("comparability", {})
            comparable = bool(comparability.get("comparable", False))
            if comparable:
                continue
            reasons = comparability.get("reasons", [])
            if not isinstance(reasons, list) or not reasons:
                key = "unspecified-comparability-reason"
                counts[key] = counts.get(key, 0) + 1
                continue
            for reason in reasons:
                key = str(reason)
                counts[key] = counts.get(key, 0) + 1
        return counts

    def _count_non_comparable_external(self, eval_report: dict[str, Any]) -> int:
        comparison = eval_report.get("declared_baseline_comparison", {})
        rows = comparison.get("comparisons", [])
        if not isinstance(rows, list):
            return 0
        count = 0
        for row in rows:
            source_type = str(row.get("source_type", "")).lower()
            if not source_type.startswith("external"):
                continue
            comparable = bool(row.get("comparability", {}).get("comparable", False))
            if not comparable:
                count += 1
        return count
