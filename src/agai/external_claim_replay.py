from __future__ import annotations

from typing import Any

from .baseline_attestation import ExternalBaselineAttestationService
from .baseline_registry import DeclaredBaselineComparator
from .external_claim_plan import ExternalClaimPlanner
from .release_status import ReleaseStatusEvaluator


class ExternalClaimReplayRunner:
    _MANUAL_BLOCKING_ACTIONS = {
        "refresh_evidence_payload",
        "replace_placeholder_metadata",
        "normalize_metadata_dates",
        "normalize_harness_alignment",
        "add_overlapping_metrics",
        "increase_metric_overlap",
    }

    def __init__(self, policy_path: str = "config/repro_policy.json") -> None:
        self.policy_path = policy_path
        self.release_status = ReleaseStatusEvaluator(policy_path=policy_path)
        self.planner = ExternalClaimPlanner()

    def run(
        self,
        *,
        eval_report: dict[str, Any],
        registry_path: str = "config/frontier_baselines.json",
        max_metric_delta: float = 0.02,
        release_status: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        comparator = DeclaredBaselineComparator(registry_path=registry_path)
        eval_before = dict(eval_report)
        eval_before["declared_baseline_comparison"] = comparator.compare(eval_before)
        release_before = (
            release_status if isinstance(release_status, dict) else self.release_status.evaluate(eval_before)
        )
        plan_before = self.planner.plan(
            eval_report=eval_before,
            release_status=release_before,
            registry_path=registry_path,
            default_max_metric_delta=max_metric_delta,
        )

        row_plans = plan_before.get("row_plans", [])
        candidates, skipped_manual_rows = self._select_attestation_candidates(row_plans=row_plans)
        attempts: list[dict[str, Any]] = []
        passed = 0
        failed = 0

        if dry_run:
            for baseline_id in candidates:
                attempts.append(
                    {
                        "baseline_id": baseline_id,
                        "status": "dry-run-not-executed",
                        "attestation_passed": False,
                        "reasons": ["dry-run enabled"],
                    }
                )
        else:
            service = ExternalBaselineAttestationService(
                registry_path=registry_path,
                policy_path=self.policy_path,
            )
            for baseline_id in candidates:
                result = service.attest_from_eval_report(
                    baseline_id=baseline_id,
                    eval_report=eval_before,
                    max_metric_delta=max_metric_delta,
                )
                attestation_passed = bool(result.get("attestation_passed", False))
                if attestation_passed:
                    passed += 1
                else:
                    failed += 1
                attempts.append(
                    {
                        "baseline_id": baseline_id,
                        "status": str(result.get("status", "unknown")),
                        "action": str(result.get("action", "")),
                        "attestation_passed": attestation_passed,
                        "replication_status": str(result.get("replication_status", "")),
                        "reasons": list(result.get("reasons", []))
                        if isinstance(result.get("reasons"), list)
                        else [],
                    }
                )

        eval_after = dict(eval_before)
        if dry_run:
            eval_after["declared_baseline_comparison"] = eval_before["declared_baseline_comparison"]
        else:
            eval_after["declared_baseline_comparison"] = comparator.compare(eval_after)
        release_after = self.release_status.evaluate(eval_after)
        plan_after = self.planner.plan(
            eval_report=eval_after,
            release_status=release_after,
            registry_path=registry_path,
            default_max_metric_delta=max_metric_delta,
        )

        before_gate = release_before.get("gates", {}).get("external_claim_gate", {})
        after_gate = release_after.get("gates", {}).get("external_claim_gate", {})
        before_distance = int(before_gate.get("external_claim_distance", 0))
        after_distance = int(after_gate.get("external_claim_distance", 0))
        before_comparable = int(before_gate.get("comparable_external_baselines", 0))
        after_comparable = int(after_gate.get("comparable_external_baselines", 0))
        before_progress = self._distance_progress_summary(plan_before)
        after_progress = self._distance_progress_summary(plan_after)
        before_total_claim_distance = int(before_progress.get("current_total_distance", before_distance))
        after_total_claim_distance = int(after_progress.get("current_total_distance", after_distance))
        before_max_total_claim_distance = int(before_progress.get("max_total_distance", 0))
        after_max_total_claim_distance = int(after_progress.get("max_total_distance", 0))
        before_total_progress_ratio = float(before_progress.get("current_progress_ratio", 0.0))
        after_total_progress_ratio = float(after_progress.get("current_progress_ratio", 0.0))

        return {
            "status": "ok",
            "registry_path": registry_path,
            "dry_run": dry_run,
            "max_metric_delta": float(max_metric_delta),
            "before": {
                "external_claim_ready": bool(release_before.get("external_claim_ready", False)),
                "claim_scope": str(release_before.get("claim_scope", "unknown")),
                "external_claim_distance": before_distance,
                "comparable_external_baselines": before_comparable,
                "required_external_baselines": int(before_gate.get("required_external_baselines", 0)),
                "total_claim_distance": before_total_claim_distance,
                "max_total_claim_distance": before_max_total_claim_distance,
                "total_progress_ratio": before_total_progress_ratio,
            },
            "after": {
                "external_claim_ready": bool(release_after.get("external_claim_ready", False)),
                "claim_scope": str(release_after.get("claim_scope", "unknown")),
                "external_claim_distance": after_distance,
                "comparable_external_baselines": after_comparable,
                "required_external_baselines": int(after_gate.get("required_external_baselines", 0)),
                "total_claim_distance": after_total_claim_distance,
                "max_total_claim_distance": after_max_total_claim_distance,
                "total_progress_ratio": after_total_progress_ratio,
            },
            "delta": {
                "external_claim_distance_reduction": before_distance - after_distance,
                "comparable_external_baselines_increase": after_comparable - before_comparable,
                "total_claim_distance_reduction": before_total_claim_distance - after_total_claim_distance,
                "total_progress_ratio_gain": after_total_progress_ratio - before_total_progress_ratio,
            },
            "replay_summary": {
                "candidate_rows": len(candidates),
                "attempted_rows": 0 if dry_run else len(attempts),
                "passed_rows": 0 if dry_run else passed,
                "failed_rows": 0 if dry_run else failed,
                "skipped_manual_rows": len(skipped_manual_rows),
            },
            "attempts": attempts,
            "skipped_manual_rows": skipped_manual_rows,
            "before_external_claim_plan": {
                "estimated_distance_after_recoverable_actions": int(
                    plan_before.get("estimated_distance_after_recoverable_actions", 0)
                ),
                "estimated_total_distance_after_recoverable_actions": int(
                    plan_before.get("estimated_total_distance_after_recoverable_actions", 0)
                ),
                "additional_baselines_needed": int(plan_before.get("additional_baselines_needed", 0)),
                "claim_calibration_distance": int(plan_before.get("claim_calibration_distance", 0)),
                "distance_progress": before_progress,
            },
            "after_external_claim_plan": {
                "estimated_distance_after_recoverable_actions": int(
                    plan_after.get("estimated_distance_after_recoverable_actions", 0)
                ),
                "estimated_total_distance_after_recoverable_actions": int(
                    plan_after.get("estimated_total_distance_after_recoverable_actions", 0)
                ),
                "additional_baselines_needed": int(plan_after.get("additional_baselines_needed", 0)),
                "claim_calibration_distance": int(plan_after.get("claim_calibration_distance", 0)),
                "distance_progress": after_progress,
            },
            "disclaimer": (
                "Replay automation only executes attestation for rows without manual metadata/harness blockers. "
                "All other blockers remain manual work."
            ),
        }

    def _distance_progress_summary(self, plan: Any) -> dict[str, Any]:
        payload = plan if isinstance(plan, dict) else {}
        progress = payload.get("distance_progress", {})
        if not isinstance(progress, dict):
            progress = {}
        return {
            "max_total_distance": int(progress.get("max_total_distance", 0)),
            "current_total_distance": int(progress.get("current_total_distance", 0)),
            "projected_total_distance_after_recoverable_actions": int(
                progress.get("projected_total_distance_after_recoverable_actions", 0)
            ),
            "recoverable_distance_reduction": int(progress.get("recoverable_distance_reduction", 0)),
            "current_progress_ratio": float(progress.get("current_progress_ratio", 0.0)),
            "projected_progress_ratio": float(progress.get("projected_progress_ratio", 0.0)),
            "current_remaining_ratio": float(progress.get("current_remaining_ratio", 1.0)),
            "projected_remaining_ratio": float(progress.get("projected_remaining_ratio", 1.0)),
        }

    def _select_attestation_candidates(
        self,
        *,
        row_plans: Any,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if not isinstance(row_plans, list):
            return [], []
        staged: list[str] = []
        skipped: list[dict[str, Any]] = []
        for row in row_plans:
            if not isinstance(row, dict):
                continue
            baseline_id = str(row.get("baseline_id", "")).strip()
            if not baseline_id:
                continue
            actions = row.get("actions", [])
            if not isinstance(actions, list):
                actions = []
            action_types = {
                str(action.get("action_type", "")).strip()
                for action in actions
                if isinstance(action, dict)
            }
            if "attest_baseline" not in action_types:
                skipped.append(
                    {
                        "baseline_id": baseline_id,
                        "blocking_action_types": ["missing_attest_baseline_action"],
                    }
                )
                continue
            blockers = sorted(
                action_type for action_type in action_types if action_type in self._MANUAL_BLOCKING_ACTIONS
            )
            if blockers:
                skipped.append(
                    {
                        "baseline_id": baseline_id,
                        "blocking_action_types": blockers,
                    }
                )
                continue
            staged.append(baseline_id)
        candidates = list(dict.fromkeys(staged))
        return candidates, skipped
