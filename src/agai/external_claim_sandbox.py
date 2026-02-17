from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .baseline_normalization import ExternalBaselineNormalizationService
from .baseline_patch_template import ExternalBaselinePatchTemplateService
from .external_claim_replay import ExternalClaimReplayRunner


class ExternalClaimSandboxPipeline:
    def __init__(self, policy_path: str = "config/repro_policy.json") -> None:
        self.policy_path = policy_path
        self.replay = ExternalClaimReplayRunner(policy_path=policy_path)

    def run(
        self,
        *,
        baseline_id: str,
        eval_report: dict[str, Any],
        source_registry_path: str = "config/frontier_baselines.json",
        sandbox_registry_path: str,
        patch_overrides: dict[str, Any] | None = None,
        max_metric_delta: float = 0.02,
        align_to_eval: bool = True,
        replace_metrics: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        source_path = Path(source_registry_path)
        sandbox_path = Path(sandbox_registry_path)
        if not source_path.exists():
            return {
                "status": "error",
                "reason": f"source registry not found: {source_path}",
                "baseline_id": baseline_id,
                "source_registry_path": str(source_path),
            }
        if not isinstance(eval_report, dict):
            return {
                "status": "error",
                "reason": "eval_report must be an object",
                "baseline_id": baseline_id,
                "source_registry_path": str(source_path),
            }
        if patch_overrides is not None and not isinstance(patch_overrides, dict):
            return {
                "status": "error",
                "reason": "patch_overrides must be an object when provided",
                "baseline_id": baseline_id,
                "source_registry_path": str(source_path),
            }

        source_hash_before = self._sha256(source_path)
        sandbox_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, sandbox_path)

        template_service = ExternalBaselinePatchTemplateService(registry_path=str(sandbox_path))
        template = template_service.build_template(
            baseline_id=baseline_id,
            eval_report=eval_report,
        )
        if template.get("status") != "ok":
            return {
                "status": "error",
                "reason": str(template.get("reason", "template generation failed")),
                "baseline_id": baseline_id,
                "source_registry_path": str(source_path),
                "sandbox_registry_path": str(sandbox_path),
                "source_registry_unchanged": self._sha256(source_path) == source_hash_before,
            }

        patch_template = template.get("patch_template", {})
        if not isinstance(patch_template, dict):
            patch_template = {}
        effective_patch = self._deep_merge(
            copy.deepcopy(patch_template),
            patch_overrides if isinstance(patch_overrides, dict) else {},
        )
        unresolved_fields = self._unresolved_fields(effective_patch)

        before_replay = self.replay.run(
            eval_report=eval_report,
            release_status=None,
            registry_path=str(sandbox_path),
            max_metric_delta=max_metric_delta,
            dry_run=True,
        )

        apply_executed = False
        normalization_result: dict[str, Any] | None = None
        replay_result: dict[str, Any] | None = None

        if dry_run:
            status = "dry-run"
        elif unresolved_fields:
            status = "blocked"
        else:
            normalizer = ExternalBaselineNormalizationService(registry_path=str(sandbox_path))
            normalization_result = normalizer.normalize_payload(
                baseline_id=baseline_id,
                patch=effective_patch,
                eval_report=eval_report,
                align_to_eval=align_to_eval,
                replace_metrics=replace_metrics,
            )
            if normalization_result.get("status") != "ok":
                status = "error"
            else:
                apply_executed = True
                replay_result = self.replay.run(
                    eval_report=eval_report,
                    release_status=None,
                    registry_path=str(sandbox_path),
                    max_metric_delta=max_metric_delta,
                    dry_run=False,
                )
                status = "ok" if replay_result.get("status") == "ok" else "error"

        after_replay = replay_result if replay_result is not None else before_replay
        source_hash_after = self._sha256(source_path)
        return {
            "status": status,
            "baseline_id": baseline_id,
            "source_registry_path": str(source_path),
            "sandbox_registry_path": str(sandbox_path),
            "source_registry_unchanged": source_hash_before == source_hash_after,
            "dry_run": dry_run,
            "align_to_eval": align_to_eval,
            "replace_metrics": replace_metrics,
            "max_metric_delta": float(max_metric_delta),
            "template": {
                "blocking_categories": list(template.get("blocking_categories", [])),
                "comparability_reasons": list(template.get("comparability_reasons", [])),
                "patch_template": patch_template,
                "checklist": list(template.get("checklist", [])),
            },
            "patch_overrides_supplied": sorted(list((patch_overrides or {}).keys())),
            "effective_patch": effective_patch,
            "unresolved_fields": unresolved_fields,
            "apply_executed": apply_executed,
            "before": {
                "external_claim_distance": int(
                    before_replay.get("before", {}).get("external_claim_distance", 0)
                ),
                "external_claim_ready": bool(
                    before_replay.get("before", {}).get("external_claim_ready", False)
                ),
                "comparable_external_baselines": int(
                    before_replay.get("before", {}).get("comparable_external_baselines", 0)
                ),
                "required_external_baselines": int(
                    before_replay.get("before", {}).get("required_external_baselines", 0)
                ),
            },
            "after": {
                "external_claim_distance": int(
                    after_replay.get("after", {}).get("external_claim_distance", 0)
                ),
                "external_claim_ready": bool(
                    after_replay.get("after", {}).get("external_claim_ready", False)
                ),
                "comparable_external_baselines": int(
                    after_replay.get("after", {}).get("comparable_external_baselines", 0)
                ),
                "required_external_baselines": int(
                    after_replay.get("after", {}).get("required_external_baselines", 0)
                ),
            },
            "delta": {
                "external_claim_distance_reduction": int(
                    after_replay.get("delta", {}).get("external_claim_distance_reduction", 0)
                ),
                "comparable_external_baselines_increase": int(
                    after_replay.get("delta", {}).get("comparable_external_baselines_increase", 0)
                ),
            },
            "normalization_result": normalization_result or {},
            "replay_result": replay_result or {},
            "disclaimer": (
                "Pipeline runs in an isolated sandbox registry and never mutates source registry. "
                "Template fields must be filled from real evidence before non-dry execution."
            ),
        }

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
