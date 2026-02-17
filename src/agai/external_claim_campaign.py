from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .baseline_ingestion import ExternalBaselineIngestionService
from .baseline_normalization import ExternalBaselineNormalizationService
from .baseline_patch_template import ExternalBaselinePatchTemplateService
from .external_claim_replay import ExternalClaimReplayRunner


class ExternalClaimSandboxCampaignRunner:
    def __init__(self, policy_path: str = "config/repro_policy.json") -> None:
        self.policy_path = policy_path
        self.replay = ExternalClaimReplayRunner(policy_path=policy_path)

    def run(
        self,
        *,
        eval_report: dict[str, Any],
        source_registry_path: str = "config/frontier_baselines.json",
        sandbox_registry_path: str,
        campaign_config: dict[str, Any],
        default_max_metric_delta: float = 0.02,
    ) -> dict[str, Any]:
        source_path = Path(source_registry_path)
        sandbox_path = Path(sandbox_registry_path)
        if not source_path.exists():
            return {
                "status": "error",
                "reason": f"source registry not found: {source_path}",
                "source_registry_path": str(source_path),
            }
        if not isinstance(eval_report, dict):
            return {
                "status": "error",
                "reason": "eval_report must be an object",
                "source_registry_path": str(source_path),
            }
        if not isinstance(campaign_config, dict):
            return {
                "status": "error",
                "reason": "campaign_config must be an object",
                "source_registry_path": str(source_path),
            }

        source_hash_before = self._sha256(source_path)
        sandbox_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, sandbox_path)

        ingest_results = self._run_ingest_stage(
            sandbox_registry_path=sandbox_path,
            ingest_payload_paths=campaign_config.get("ingest_payload_paths", []),
        )
        step_results = self._run_baseline_steps(
            eval_report=eval_report,
            sandbox_registry_path=sandbox_path,
            baseline_runs=campaign_config.get("baseline_runs", []),
            default_max_metric_delta=default_max_metric_delta,
        )

        before_snapshot = self._distance_snapshot(
            eval_report=eval_report,
            registry_path=str(source_path),
            max_metric_delta=default_max_metric_delta,
        )
        final_snapshot = self._distance_snapshot(
            eval_report=eval_report,
            registry_path=str(sandbox_path),
            max_metric_delta=default_max_metric_delta,
        )

        source_hash_after = self._sha256(source_path)
        status = "ok"
        if any(str(row.get("status", "")) == "error" for row in ingest_results):
            status = "error"
        elif any(str(row.get("status", "")) == "error" for row in step_results):
            status = "error"
        elif any(str(row.get("status", "")) == "blocked" for row in step_results):
            status = "partial"

        return {
            "status": status,
            "source_registry_path": str(source_path),
            "sandbox_registry_path": str(sandbox_path),
            "source_registry_unchanged": source_hash_before == source_hash_after,
            "ingest_stage": {
                "count": len(ingest_results),
                "results": ingest_results,
            },
            "baseline_steps": {
                "count": len(step_results),
                "results": step_results,
            },
            "before": before_snapshot,
            "after": final_snapshot,
            "delta": {
                "external_claim_distance_reduction": int(before_snapshot["external_claim_distance"])
                - int(final_snapshot["external_claim_distance"]),
                "comparable_external_baselines_increase": int(final_snapshot["comparable_external_baselines"])
                - int(before_snapshot["comparable_external_baselines"]),
                "total_claim_distance_reduction": int(before_snapshot["total_claim_distance"])
                - int(final_snapshot["total_claim_distance"]),
                "total_progress_ratio_gain": float(final_snapshot["total_progress_ratio"])
                - float(before_snapshot["total_progress_ratio"]),
            },
            "disclaimer": (
                "Campaign output is a sandbox projection from explicit user-provided evidence patches and payloads. "
                "It does not mutate source registry or imply external claim readiness in production artifacts."
            ),
        }

    def _run_ingest_stage(
        self,
        *,
        sandbox_registry_path: Path,
        ingest_payload_paths: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(ingest_payload_paths, list):
            return [
                {
                    "status": "error",
                    "reason": "ingest_payload_paths must be a list",
                    "payload_path": "",
                }
            ]
        service = ExternalBaselineIngestionService(registry_path=str(sandbox_registry_path))
        rows: list[dict[str, Any]] = []
        for payload_path in ingest_payload_paths:
            path_str = str(payload_path)
            result = service.ingest_file(path_str)
            rows.append(
                {
                    "status": str(result.get("status", "error")),
                    "payload_path": path_str,
                    "action": str(result.get("action", "")),
                    "baseline_id": str(result.get("baseline_id", "")),
                    "reason": str(result.get("reason", "")),
                    "errors": list(result.get("errors", [])) if isinstance(result.get("errors"), list) else [],
                }
            )
        return rows

    def _run_baseline_steps(
        self,
        *,
        eval_report: dict[str, Any],
        sandbox_registry_path: Path,
        baseline_runs: Any,
        default_max_metric_delta: float,
    ) -> list[dict[str, Any]]:
        if not isinstance(baseline_runs, list):
            return [
                {
                    "status": "error",
                    "reason": "baseline_runs must be a list",
                    "baseline_id": "",
                }
            ]

        template_service = ExternalBaselinePatchTemplateService(registry_path=str(sandbox_registry_path))
        normalizer = ExternalBaselineNormalizationService(registry_path=str(sandbox_registry_path))
        rows: list[dict[str, Any]] = []
        for index, payload in enumerate(baseline_runs, start=1):
            if not isinstance(payload, dict):
                rows.append(
                    {
                        "step_index": index,
                        "status": "error",
                        "reason": "baseline run payload must be an object",
                        "baseline_id": "",
                    }
                )
                continue
            baseline_id = str(payload.get("baseline_id", "")).strip()
            if not baseline_id:
                rows.append(
                    {
                        "step_index": index,
                        "status": "error",
                        "reason": "baseline_id is required",
                        "baseline_id": "",
                    }
                )
                continue

            before = self._distance_snapshot(
                eval_report=eval_report,
                registry_path=str(sandbox_registry_path),
                max_metric_delta=float(payload.get("max_metric_delta", default_max_metric_delta)),
            )

            template = template_service.build_template(
                baseline_id=baseline_id,
                eval_report=eval_report,
            )
            if template.get("status") != "ok":
                rows.append(
                    {
                        "step_index": index,
                        "status": "error",
                        "reason": str(template.get("reason", "template generation failed")),
                        "baseline_id": baseline_id,
                    }
                )
                continue

            patch_template = template.get("patch_template", {})
            if not isinstance(patch_template, dict):
                patch_template = {}
            overrides = self._load_overrides(path=str(payload.get("patch_overrides_path", "") or ""))
            if overrides.get("status") == "error":
                rows.append(
                    {
                        "step_index": index,
                        "status": "error",
                        "reason": str(overrides.get("reason", "invalid patch overrides")),
                        "baseline_id": baseline_id,
                        "patch_overrides_path": str(payload.get("patch_overrides_path", "")),
                    }
                )
                continue
            override_payload = overrides.get("payload", {})
            if not isinstance(override_payload, dict):
                override_payload = {}

            effective_patch = self._deep_merge(copy.deepcopy(patch_template), override_payload)
            unresolved_fields = self._unresolved_fields(effective_patch)
            step_dry_run = bool(payload.get("dry_run", False))
            align_to_eval = bool(payload.get("align_to_eval", True))
            replace_metrics = bool(payload.get("replace_metrics", False))
            max_metric_delta = float(payload.get("max_metric_delta", default_max_metric_delta))

            normalization_result: dict[str, Any] = {}
            replay_result: dict[str, Any] = {}
            step_status = "dry-run" if step_dry_run else "blocked"
            apply_executed = False
            if step_dry_run:
                step_status = "dry-run"
            elif unresolved_fields:
                step_status = "blocked"
            else:
                normalization_result = normalizer.normalize_payload(
                    baseline_id=baseline_id,
                    patch=effective_patch,
                    eval_report=eval_report,
                    align_to_eval=align_to_eval,
                    replace_metrics=replace_metrics,
                )
                if normalization_result.get("status") != "ok":
                    step_status = "error"
                else:
                    apply_executed = True
                    replay_result = self.replay.run(
                        eval_report=eval_report,
                        release_status=None,
                        registry_path=str(sandbox_registry_path),
                        max_metric_delta=max_metric_delta,
                        dry_run=False,
                    )
                    step_status = "ok" if replay_result.get("status") == "ok" else "error"

            after = self._distance_snapshot(
                eval_report=eval_report,
                registry_path=str(sandbox_registry_path),
                max_metric_delta=max_metric_delta,
            )
            rows.append(
                {
                    "step_index": index,
                    "status": step_status,
                    "baseline_id": baseline_id,
                    "patch_overrides_path": str(payload.get("patch_overrides_path", "")),
                    "align_to_eval": align_to_eval,
                    "replace_metrics": replace_metrics,
                    "max_metric_delta": max_metric_delta,
                    "template_blocking_categories": list(template.get("blocking_categories", [])),
                    "unresolved_fields": unresolved_fields,
                    "apply_executed": apply_executed,
                    "before": before,
                    "after": after,
                    "delta": {
                        "external_claim_distance_reduction": int(before["external_claim_distance"])
                        - int(after["external_claim_distance"]),
                        "comparable_external_baselines_increase": int(after["comparable_external_baselines"])
                        - int(before["comparable_external_baselines"]),
                        "total_claim_distance_reduction": int(before["total_claim_distance"])
                        - int(after["total_claim_distance"]),
                        "total_progress_ratio_gain": float(after["total_progress_ratio"])
                        - float(before["total_progress_ratio"]),
                    },
                    "normalization_result": normalization_result,
                    "replay_result": replay_result,
                }
            )
        return rows

    def _distance_snapshot(
        self,
        *,
        eval_report: dict[str, Any],
        registry_path: str,
        max_metric_delta: float,
    ) -> dict[str, Any]:
        payload = self.replay.run(
            eval_report=eval_report,
            release_status=None,
            registry_path=registry_path,
            max_metric_delta=max_metric_delta,
            dry_run=True,
        )
        before = payload.get("before", {})
        before_plan = payload.get("before_external_claim_plan", {})
        if not isinstance(before_plan, dict):
            before_plan = {}
        progress = before_plan.get("distance_progress", {})
        if not isinstance(progress, dict):
            progress = {}
        total_claim_distance = int(
            before.get("total_claim_distance", progress.get("current_total_distance", int(before.get("external_claim_distance", 0))))
        )
        max_total_claim_distance = int(
            before.get(
                "max_total_claim_distance",
                progress.get(
                    "max_total_distance",
                    int(before.get("required_external_baselines", 0)),
                ),
            )
        )
        total_progress_ratio = float(before.get("total_progress_ratio", progress.get("current_progress_ratio", 0.0)))
        return {
            "external_claim_distance": int(before.get("external_claim_distance", 0)),
            "external_claim_ready": bool(before.get("external_claim_ready", False)),
            "comparable_external_baselines": int(before.get("comparable_external_baselines", 0)),
            "required_external_baselines": int(before.get("required_external_baselines", 0)),
            "total_claim_distance": total_claim_distance,
            "max_total_claim_distance": max_total_claim_distance,
            "total_progress_ratio": total_progress_ratio,
        }

    def _load_overrides(self, *, path: str) -> dict[str, Any]:
        if not path.strip():
            return {"status": "ok", "payload": {}}
        payload_path = Path(path)
        if not payload_path.exists():
            return {"status": "error", "reason": f"patch overrides file not found: {payload_path}"}
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"status": "error", "reason": f"invalid json in patch overrides: {exc}"}
        if not isinstance(payload, dict):
            return {"status": "error", "reason": "patch overrides payload must be an object"}
        return {"status": "ok", "payload": payload}

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._deep_merge(dict(base.get(key, {})), value)
            else:
                base[key] = value
        return base

    def _unresolved_fields(self, payload: Any, prefix: str = "") -> list[str]:
        unresolved: list[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                name = f"{prefix}.{key}" if prefix else str(key)
                unresolved.extend(self._unresolved_fields(value, name))
            return unresolved
        if payload is None:
            return [prefix] if prefix else []
        if isinstance(payload, str) and not payload.strip():
            return [prefix] if prefix else []
        return []

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
