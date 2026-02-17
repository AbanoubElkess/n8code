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
        projected_snapshot = {
            "external_claim_distance": int(after.get("external_claim_distance", before["external_claim_distance"])),
            "external_claim_ready": bool(after.get("external_claim_ready", False)),
            "comparable_external_baselines": int(after.get("comparable_external_baselines", 0)),
            "required_external_baselines": int(after.get("required_external_baselines", 0)),
        }
        promotion_gates = self._load_promotion_gates()
        gate_evaluation = self._evaluate_execute_gates(
            before=before,
            after=projected_snapshot,
            stage_status=str(projected.get("status", "unknown")),
            promotion_gates=promotion_gates,
        )
        projected_distance = int(projected_snapshot["external_claim_distance"])
        projected_reduction = int(before["external_claim_distance"]) - projected_distance
        promotable = bool(gate_evaluation.get("pass", False))
        return {
            "status": "ok",
            "source_registry_path": str(source_path),
            "required_confirmation_hash": source_hash,
            "promotable": promotable,
            "before": before,
            "projected_after": projected_snapshot,
            "projected_delta": {
                "external_claim_distance_reduction": projected_reduction,
                "comparable_external_baselines_increase": int(
                    projected.get("delta", {}).get("comparable_external_baselines_increase", 0)
                ),
            },
            "projected_campaign_status": str(projected.get("status", "unknown")),
            "promotion_gates": promotion_gates,
            "gate_evaluation": gate_evaluation,
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
        registry_bytes_before = source_path.read_bytes()
        promotion_gates = self._load_promotion_gates()
        ingest_results: list[dict[str, Any]] = []
        step_results: list[dict[str, Any]] = []
        executed_after = dict(before)
        execution_status = "error"
        gate_evaluation = {
            "pass": False,
            "reason": "execute path did not complete",
            "stage_status": "error",
            "distance_reduction": 0,
            "min_distance_reduction": int(promotion_gates["min_distance_reduction"]),
            "max_after_external_claim_distance": promotion_gates["max_after_external_claim_distance"],
            "require_external_claim_ready": bool(promotion_gates["require_external_claim_ready"]),
            "after_external_claim_distance": int(before["external_claim_distance"]),
            "after_external_claim_ready": bool(before["external_claim_ready"]),
            "reasons": ["execute path did not complete"],
        }
        rollback_applied = False
        rollback_reason = ""
        execution_error = ""

        try:
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
            executed_after = self._distance_snapshot(
                eval_report=eval_report,
                registry_path=str(source_path),
                max_metric_delta=default_max_metric_delta,
            )
            execution_status = self._derive_stage_status(ingest_results=ingest_results, step_results=step_results)
            gate_evaluation = self._evaluate_execute_gates(
                before=before,
                after=executed_after,
                stage_status=execution_status,
                promotion_gates=promotion_gates,
            )
            if not gate_evaluation.get("pass", False):
                rollback_reason = "promotion gates failed"
                self._restore_registry(path=source_path, payload=registry_bytes_before)
                rollback_applied = True
        except Exception as exc:  # noqa: BLE001
            execution_error = str(exc)
            rollback_reason = "execute raised exception"
            self._restore_registry(path=source_path, payload=registry_bytes_before)
            rollback_applied = True
            execution_status = "error"

        after = self._distance_snapshot(
            eval_report=eval_report,
            registry_path=str(source_path),
            max_metric_delta=default_max_metric_delta,
        )
        source_hash_after = self._sha256(source_path)
        source_registry_mutated = bool(source_hash_after != current_hash)
        status = "ok" if execution_status == "ok" and not rollback_applied else "error"
        if rollback_applied and execution_error:
            gate_reasons = list(gate_evaluation.get("reasons", []))
            gate_reasons.append(f"execute_exception={execution_error}")
            gate_evaluation["reasons"] = gate_reasons
            gate_evaluation["reason"] = "; ".join(gate_reasons)

        return {
            "status": status,
            "execution_status": execution_status,
            "source_registry_path": str(source_path),
            "source_registry_mutated": source_registry_mutated,
            "before": before,
            "executed_after": executed_after,
            "after": after,
            "delta": {
                "external_claim_distance_reduction": int(before["external_claim_distance"])
                - int(after["external_claim_distance"]),
                "comparable_external_baselines_increase": int(after["comparable_external_baselines"])
                - int(before["comparable_external_baselines"]),
            },
            "execution_delta": {
                "external_claim_distance_reduction": int(before["external_claim_distance"])
                - int(executed_after["external_claim_distance"]),
                "comparable_external_baselines_increase": int(executed_after["comparable_external_baselines"])
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
            "promotion_gates": promotion_gates,
            "gate_evaluation": gate_evaluation,
            "rollback_applied": rollback_applied,
            "rollback_reason": rollback_reason,
            "source_hash_before": current_hash,
            "source_hash_after": source_hash_after,
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

    def _derive_stage_status(
        self,
        *,
        ingest_results: list[dict[str, Any]],
        step_results: list[dict[str, Any]],
    ) -> str:
        status = "ok"
        if any(str(row.get("status", "")) == "error" for row in ingest_results):
            status = "error"
        elif any(str(row.get("status", "")) == "error" for row in step_results):
            status = "error"
        elif any(str(row.get("status", "")) == "blocked" for row in step_results):
            status = "partial"
        return status

    def _load_promotion_gates(self) -> dict[str, Any]:
        default_policy = {
            "min_distance_reduction": 1,
            "max_after_external_claim_distance": None,
            "require_external_claim_ready": False,
        }
        policy_path = Path(self.policy_path)
        if not policy_path.exists():
            return default_policy
        try:
            payload = json.loads(policy_path.read_text(encoding="utf-8"))
            gates = payload.get("promotion_gates", {})
            if not isinstance(gates, dict):
                return default_policy
            raw_max_after = gates.get("max_after_external_claim_distance")
            max_after = None
            if raw_max_after is not None:
                max_after = max(0, int(raw_max_after))
            return {
                "min_distance_reduction": max(0, int(gates.get("min_distance_reduction", 1))),
                "max_after_external_claim_distance": max_after,
                "require_external_claim_ready": bool(gates.get("require_external_claim_ready", False)),
            }
        except Exception:  # noqa: BLE001
            return default_policy

    def _evaluate_execute_gates(
        self,
        *,
        before: dict[str, Any],
        after: dict[str, Any],
        stage_status: str,
        promotion_gates: dict[str, Any],
    ) -> dict[str, Any]:
        before_distance = int(before.get("external_claim_distance", 0))
        after_distance = int(after.get("external_claim_distance", 0))
        distance_reduction = before_distance - after_distance
        min_distance_reduction = int(promotion_gates.get("min_distance_reduction", 1))
        max_after = promotion_gates.get("max_after_external_claim_distance")
        require_ready = bool(promotion_gates.get("require_external_claim_ready", False))
        reasons: list[str] = []

        if stage_status != "ok":
            reasons.append(f"stage status must be ok, got {stage_status}")
        if distance_reduction < min_distance_reduction:
            reasons.append(
                f"distance reduction {distance_reduction} is below min_distance_reduction {min_distance_reduction}"
            )
        if max_after is not None and after_distance > int(max_after):
            reasons.append(
                f"after external_claim_distance {after_distance} exceeds max_after_external_claim_distance {int(max_after)}"
            )
        if require_ready and not bool(after.get("external_claim_ready", False)):
            reasons.append("after external_claim_ready is false but required by promotion gate")

        gate_pass = len(reasons) == 0
        reason = "promotion execute gates satisfied" if gate_pass else "; ".join(reasons)
        return {
            "pass": gate_pass,
            "reason": reason,
            "stage_status": stage_status,
            "distance_reduction": distance_reduction,
            "min_distance_reduction": min_distance_reduction,
            "max_after_external_claim_distance": max_after,
            "require_external_claim_ready": require_ready,
            "after_external_claim_distance": after_distance,
            "after_external_claim_ready": bool(after.get("external_claim_ready", False)),
            "reasons": reasons,
        }

    def _restore_registry(self, *, path: Path, payload: bytes) -> None:
        path.write_bytes(payload)

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
