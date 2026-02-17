from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from .baseline_attestation import ExternalBaselineAttestationService
from .baseline_ingestion import ExternalBaselineIngestionService
from .baseline_normalization import ExternalBaselineNormalizationService
from .baseline_patch_template import ExternalBaselinePatchTemplateService
from .external_claim_campaign import ExternalClaimSandboxCampaignRunner
from .external_claim_replay import ExternalClaimReplayRunner


class ExternalClaimPromotionService:
    def __init__(self, policy_path: str = "config/repro_policy.json") -> None:
        self.policy_path = policy_path
        self.replay = ExternalClaimReplayRunner(policy_path=policy_path)
        self.campaign = ExternalClaimSandboxCampaignRunner(policy_path=policy_path)

    def preview(
        self,
        *,
        eval_report: dict[str, Any],
        source_registry_path: str,
        campaign_config: dict[str, Any],
        default_max_metric_delta: float,
    ) -> dict[str, Any]:
        source_path = Path(source_registry_path)
        if not source_path.exists():
            return {
                "status": "error",
                "reason": f"source registry not found: {source_path}",
                "source_registry_path": str(source_path),
            }
        source_hash = self._sha256(source_path)
        before = self._distance_snapshot(
            eval_report=eval_report,
            registry_path=str(source_path),
            max_metric_delta=default_max_metric_delta,
        )
        with tempfile.TemporaryDirectory(prefix="agai-promotion-preview-") as temp_dir:
            sandbox_path = Path(temp_dir) / "campaign.registry.json"
            projected = self.campaign.run(
                eval_report=eval_report,
                source_registry_path=str(source_path),
                sandbox_registry_path=str(sandbox_path),
                campaign_config=campaign_config,
                default_max_metric_delta=default_max_metric_delta,
            )
        after = projected.get("after", {})
        projected_distance = int(after.get("external_claim_distance", before["external_claim_distance"]))
        projected_reduction = int(before["external_claim_distance"]) - projected_distance
        promotable = bool(
            projected.get("status") == "ok"
            and projected_reduction > 0
            and projected_distance <= int(before["external_claim_distance"])
        )
        return {
            "status": "ok",
            "source_registry_path": str(source_path),
            "required_confirmation_hash": source_hash,
            "promotable": promotable,
            "before": before,
            "projected_after": {
                "external_claim_distance": projected_distance,
                "external_claim_ready": bool(after.get("external_claim_ready", False)),
                "comparable_external_baselines": int(after.get("comparable_external_baselines", 0)),
                "required_external_baselines": int(after.get("required_external_baselines", 0)),
            },
            "projected_delta": {
                "external_claim_distance_reduction": projected_reduction,
                "comparable_external_baselines_increase": int(
                    projected.get("delta", {}).get("comparable_external_baselines_increase", 0)
                ),
            },
            "projected_campaign_status": str(projected.get("status", "unknown")),
            "projected_campaign_summary": {
                "ingest_count": int(projected.get("ingest_stage", {}).get("count", 0)),
                "baseline_step_count": int(projected.get("baseline_steps", {}).get("count", 0)),
            },
            "disclaimer": (
                "Preview runs only in sandbox. Promotion still requires explicit execute mode "
                "with matching confirmation hash."
            ),
        }

    def execute(
        self,
        *,
        eval_report: dict[str, Any],
        source_registry_path: str,
        campaign_config: dict[str, Any],
        default_max_metric_delta: float,
        confirmation_hash: str,
    ) -> dict[str, Any]:
        source_path = Path(source_registry_path)
        if not source_path.exists():
            return {
                "status": "error",
                "reason": f"source registry not found: {source_path}",
                "source_registry_path": str(source_path),
            }
        current_hash = self._sha256(source_path)
        if not confirmation_hash.strip():
            return {
                "status": "error",
                "reason": "confirmation hash is required for execute mode",
                "required_confirmation_hash": current_hash,
                "source_registry_path": str(source_path),
            }
        if confirmation_hash.strip() != current_hash:
            return {
                "status": "error",
                "reason": "confirmation hash mismatch",
                "required_confirmation_hash": current_hash,
                "provided_confirmation_hash": confirmation_hash.strip(),
                "source_registry_path": str(source_path),
            }

        before = self._distance_snapshot(
            eval_report=eval_report,
            registry_path=str(source_path),
            max_metric_delta=default_max_metric_delta,
        )
        ingest_results = self._run_ingest_stage(
            source_registry_path=str(source_path),
            ingest_payload_paths=campaign_config.get("ingest_payload_paths", []),
        )
        step_results = self._run_baseline_steps(
            eval_report=eval_report,
            source_registry_path=str(source_path),
            baseline_runs=campaign_config.get("baseline_runs", []),
            default_max_metric_delta=default_max_metric_delta,
        )
        after = self._distance_snapshot(
            eval_report=eval_report,
            registry_path=str(source_path),
            max_metric_delta=default_max_metric_delta,
        )

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
            "source_registry_mutated": True,
            "before": before,
            "after": after,
            "delta": {
                "external_claim_distance_reduction": int(before["external_claim_distance"])
                - int(after["external_claim_distance"]),
                "comparable_external_baselines_increase": int(after["comparable_external_baselines"])
                - int(before["comparable_external_baselines"]),
            },
            "ingest_stage": {
                "count": len(ingest_results),
                "results": ingest_results,
            },
            "baseline_steps": {
                "count": len(step_results),
                "results": step_results,
            },
            "used_confirmation_hash": confirmation_hash.strip(),
            "disclaimer": (
                "Execute mode mutates source registry. Use preview mode and hash confirmation to "
                "control promotion scope."
            ),
        }

    def _run_ingest_stage(
        self,
        *,
        source_registry_path: str,
        ingest_payload_paths: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(ingest_payload_paths, list):
            return []
        service = ExternalBaselineIngestionService(registry_path=source_registry_path)
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
        source_registry_path: str,
        baseline_runs: Any,
        default_max_metric_delta: float,
    ) -> list[dict[str, Any]]:
        if not isinstance(baseline_runs, list):
            return []

        template_service = ExternalBaselinePatchTemplateService(registry_path=source_registry_path)
        normalizer = ExternalBaselineNormalizationService(registry_path=source_registry_path)
        attestor = ExternalBaselineAttestationService(
            registry_path=source_registry_path,
            policy_path=self.policy_path,
        )
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
                registry_path=source_registry_path,
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
                    }
                )
                continue
            override_payload = overrides.get("payload", {})
            if not isinstance(override_payload, dict):
                override_payload = {}
            effective_patch = self._deep_merge(copy.deepcopy(patch_template), override_payload)
            unresolved_fields = self._unresolved_fields(effective_patch)
            if unresolved_fields:
                rows.append(
                    {
                        "step_index": index,
                        "status": "blocked",
                        "baseline_id": baseline_id,
                        "unresolved_fields": unresolved_fields,
                        "before": before,
                        "after": before,
                        "delta": {
                            "external_claim_distance_reduction": 0,
                            "comparable_external_baselines_increase": 0,
                        },
                    }
                )
                continue

            align_to_eval = bool(payload.get("align_to_eval", True))
            replace_metrics = bool(payload.get("replace_metrics", False))
            max_metric_delta = float(payload.get("max_metric_delta", default_max_metric_delta))
            normalization_result = normalizer.normalize_payload(
                baseline_id=baseline_id,
                patch=effective_patch,
                eval_report=eval_report,
                align_to_eval=align_to_eval,
                replace_metrics=replace_metrics,
            )
            if normalization_result.get("status") != "ok":
                rows.append(
                    {
                        "step_index": index,
                        "status": "error",
                        "baseline_id": baseline_id,
                        "reason": str(normalization_result.get("reason", "normalization failed")),
                        "normalization_result": normalization_result,
                    }
                )
                continue
            attestation_result = attestor.attest_from_eval_report(
                baseline_id=baseline_id,
                eval_report=eval_report,
                max_metric_delta=max_metric_delta,
            )
            after = self._distance_snapshot(
                eval_report=eval_report,
                registry_path=source_registry_path,
                max_metric_delta=max_metric_delta,
            )
            step_status = "ok" if bool(attestation_result.get("attestation_passed", False)) else "error"
            rows.append(
                {
                    "step_index": index,
                    "status": step_status,
                    "baseline_id": baseline_id,
                    "before": before,
                    "after": after,
                    "delta": {
                        "external_claim_distance_reduction": int(before["external_claim_distance"])
                        - int(after["external_claim_distance"]),
                        "comparable_external_baselines_increase": int(after["comparable_external_baselines"])
                        - int(before["comparable_external_baselines"]),
                    },
                    "normalization_result": normalization_result,
                    "attestation_result": attestation_result,
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
        return {
            "external_claim_distance": int(before.get("external_claim_distance", 0)),
            "external_claim_ready": bool(before.get("external_claim_ready", False)),
            "comparable_external_baselines": int(before.get("comparable_external_baselines", 0)),
            "required_external_baselines": int(before.get("required_external_baselines", 0)),
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
