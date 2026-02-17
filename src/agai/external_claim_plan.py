from __future__ import annotations

from typing import Any


class ExternalClaimPlanner:
    def plan(
        self,
        *,
        eval_report: dict[str, Any],
        release_status: dict[str, Any],
        registry_path: str = "config/frontier_baselines.json",
        default_max_metric_delta: float = 0.02,
    ) -> dict[str, Any]:
        progress = eval_report.get("benchmark_progress", {})
        suite_id = str(progress.get("suite_id", "unknown-suite"))
        scoring_protocol = str(
            eval_report.get("benchmark_provenance", {}).get("scoring_reference", "unknown-scoring")
        )
        comparison = eval_report.get("declared_baseline_comparison", {})
        rows = comparison.get("comparisons", [])
        if not isinstance(rows, list):
            rows = []

        external_gate = release_status.get("gates", {}).get("external_claim_gate", {})
        required_external = int(external_gate.get("required_external_baselines", 0))
        comparable_external = int(external_gate.get("comparable_external_baselines", 0))
        external_distance = int(external_gate.get("external_claim_distance", 0))
        blocker_counts = external_gate.get("blockers", {})
        if not isinstance(blocker_counts, dict):
            blocker_counts = {}

        non_comparable_external_rows = [
            row
            for row in rows
            if str(row.get("source_type", "")).lower().startswith("external")
            and not bool(row.get("comparability", {}).get("comparable", False))
        ]
        row_plans = [
            self._row_plan(
                row=row,
                suite_id=suite_id,
                scoring_protocol=scoring_protocol,
                registry_path=registry_path,
                default_max_metric_delta=default_max_metric_delta,
            )
            for row in non_comparable_external_rows
        ]
        recoverable_rows = sum(1 for row in row_plans if bool(row.get("recoverable", False)))
        estimated_distance_after_recoverable_actions = max(0, external_distance - recoverable_rows)
        additional_baselines_needed = max(0, estimated_distance_after_recoverable_actions)

        priority_actions = self._priority_actions(row_plans=row_plans)
        if additional_baselines_needed > 0:
            priority_actions.append(
                {
                    "priority": 4,
                    "action_type": "source_additional_external_baselines",
                    "description": (
                        "Current recoverable rows are insufficient; ingest additional external baselines that "
                        "match suite and scoring protocol."
                    ),
                    "additional_baselines_needed": additional_baselines_needed,
                    "command_hint": (
                        "ingest-external-baseline --input <new_external_payload.json> "
                        f"--registry-path {registry_path}"
                    ),
                }
            )

        readiness_after_plan = additional_baselines_needed == 0
        return {
            "status": "ok",
            "suite_id": suite_id,
            "scoring_protocol": scoring_protocol,
            "registry_path": registry_path,
            "required_external_baselines": required_external,
            "comparable_external_baselines": comparable_external,
            "external_claim_distance": external_distance,
            "blocker_counts": blocker_counts,
            "non_comparable_external_rows": len(non_comparable_external_rows),
            "recoverable_external_rows": recoverable_rows,
            "estimated_distance_after_recoverable_actions": estimated_distance_after_recoverable_actions,
            "additional_baselines_needed": additional_baselines_needed,
            "row_plans": row_plans,
            "priority_actions": priority_actions,
            "readiness_after_plan": readiness_after_plan,
            "disclaimer": (
                "Plan output is an internal remediation aid. External claim readiness still requires successful "
                "attestation outcomes."
            ),
        }

    def _row_plan(
        self,
        *,
        row: dict[str, Any],
        suite_id: str,
        scoring_protocol: str,
        registry_path: str,
        default_max_metric_delta: float,
    ) -> dict[str, Any]:
        baseline_id = str(row.get("baseline_id", "unknown-baseline"))
        reasons = row.get("comparability", {}).get("reasons", [])
        if not isinstance(reasons, list):
            reasons = []
        reason_set = {str(reason) for reason in reasons}
        missing_evidence = any("missing verification evidence fields" in reason for reason in reason_set)
        suite_mismatch = "suite mismatch" in reason_set
        scoring_mismatch = "scoring protocol mismatch" in reason_set
        missing_metrics = "missing metric payload" in reason_set or "no overlapping metrics" in reason_set
        unverified = "baseline unverified" in reason_set

        actions: list[dict[str, Any]] = []
        if missing_evidence or unverified:
            actions.append(
                {
                    "priority": 1,
                    "action_type": "refresh_evidence_payload",
                    "description": (
                        "Populate required evidence fields and re-ingest baseline payload before attestation."
                    ),
                    "command_hint": (
                        "ingest-external-baseline --input <updated_payload.json> "
                        f"--registry-path {registry_path}"
                    ),
                }
            )
        if suite_mismatch or scoring_mismatch:
            actions.append(
                {
                    "priority": 2,
                    "action_type": "normalize_harness_alignment",
                    "description": "Align suite_id and scoring_protocol with current internal hard-suite harness.",
                    "target_suite_id": suite_id,
                    "target_scoring_protocol": scoring_protocol,
                }
            )
        if missing_metrics:
            actions.append(
                {
                    "priority": 2,
                    "action_type": "add_overlapping_metrics",
                    "description": (
                        "Add overlapping metrics (for example quality, aggregate_delta, holdout/adversarial "
                        "quality, overclaim rate) so comparability can be computed."
                    ),
                }
            )

        actions.append(
            {
                "priority": 3,
                "action_type": "attest_baseline",
                "description": "Run replay attestation to upgrade replication status and effective verification.",
                "command_hint": (
                    "attest-external-baseline "
                    f"--baseline-id {baseline_id} "
                    f"--registry-path {registry_path} "
                    f"--max-metric-delta {default_max_metric_delta:.2f}"
                ),
            }
        )

        return {
            "baseline_id": baseline_id,
            "source_type": str(row.get("source_type", "unknown")),
            "reasons": sorted(reason_set),
            "recoverable": len(actions) > 0,
            "actions": actions,
        }

    def _priority_actions(self, row_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        staged: list[tuple[int, dict[str, Any]]] = []
        for row in row_plans:
            baseline_id = str(row.get("baseline_id", "unknown-baseline"))
            actions = row.get("actions", [])
            if not isinstance(actions, list):
                continue
            for action in actions:
                priority = int(action.get("priority", 9))
                staged.append(
                    (
                        priority,
                        {
                            "priority": priority,
                            "baseline_id": baseline_id,
                            "action_type": str(action.get("action_type", "unknown")),
                            "description": str(action.get("description", "")),
                            "command_hint": str(action.get("command_hint", "")),
                        },
                    )
                )
        staged.sort(key=lambda pair: (pair[0], pair[1]["baseline_id"], pair[1]["action_type"]))
        return [item for _, item in staged]
