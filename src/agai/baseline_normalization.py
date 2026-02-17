from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .baseline_ingestion import ExternalBaselineIngestionService


class ExternalBaselineNormalizationService:
    def __init__(self, registry_path: str = "config/frontier_baselines.json") -> None:
        self.registry_path = Path(registry_path)
        self.ingestion = ExternalBaselineIngestionService(registry_path=registry_path)

    def normalize_payload(
        self,
        *,
        baseline_id: str,
        patch: dict[str, Any],
        eval_report: dict[str, Any] | None = None,
        align_to_eval: bool = False,
        replace_metrics: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(patch, dict):
            return {
                "status": "error",
                "reason": "patch must be an object",
                "baseline_id": baseline_id,
                "registry_path": str(self.registry_path),
            }

        registry = self._load_registry()
        baselines = registry.get("baselines", [])
        if not isinstance(baselines, list):
            baselines = []

        target = next((row for row in baselines if str(row.get("baseline_id", "")) == baseline_id), None)
        if target is None:
            return {
                "status": "error",
                "reason": f"baseline not found: {baseline_id}",
                "baseline_id": baseline_id,
                "registry_path": str(self.registry_path),
            }

        before_row = copy.deepcopy(target)
        merged = copy.deepcopy(target)
        merged["baseline_id"] = baseline_id

        top_level_fields = [
            "label",
            "source_type",
            "source",
            "source_date",
            "suite_id",
            "scoring_protocol",
            "verified",
            "enabled",
            "notes",
        ]
        for field in top_level_fields:
            if field in patch:
                merged[field] = patch[field]

        evidence_patch = patch.get("evidence")
        if evidence_patch is not None:
            if not isinstance(evidence_patch, dict):
                return {
                    "status": "error",
                    "reason": "patch.evidence must be an object when provided",
                    "baseline_id": baseline_id,
                    "registry_path": str(self.registry_path),
                }
            evidence = dict(merged.get("evidence", {}))
            evidence.update(evidence_patch)
            merged["evidence"] = evidence

        metrics_patch = patch.get("metrics")
        if metrics_patch is not None:
            if not isinstance(metrics_patch, dict):
                return {
                    "status": "error",
                    "reason": "patch.metrics must be an object when provided",
                    "baseline_id": baseline_id,
                    "registry_path": str(self.registry_path),
                }
            metrics = {} if replace_metrics else dict(merged.get("metrics", {}))
            metrics.update(metrics_patch)
            merged["metrics"] = metrics

        if align_to_eval:
            suite_id = str((eval_report or {}).get("benchmark_progress", {}).get("suite_id", "")).strip()
            scoring_protocol = str((eval_report or {}).get("benchmark_provenance", {}).get("scoring_reference", "")).strip()
            if suite_id:
                merged["suite_id"] = suite_id
            if scoring_protocol:
                merged["scoring_protocol"] = scoring_protocol

        patch_hash = self._patch_hash(
            baseline_id=baseline_id,
            patch=patch,
            align_to_eval=align_to_eval,
            replace_metrics=replace_metrics,
        )
        result = self.ingestion.ingest_payload(payload=merged, input_hash=patch_hash)
        result["baseline_id"] = baseline_id
        result["normalize_applied"] = result.get("status") == "ok"
        result["align_to_eval"] = align_to_eval
        result["replace_metrics"] = replace_metrics
        result["changed_fields"] = self._changed_fields(before=before_row, after=merged)
        result["patch_hash"] = patch_hash
        result["disclaimer"] = (
            "Normalization updates metadata only from explicit patch input. "
            "It does not prove external comparability or attest replication."
        )
        return result

    def _load_registry(self) -> dict[str, Any]:
        default_payload: dict[str, Any] = {"registry_version": "unspecified", "baselines": []}
        if not self.registry_path.exists():
            return default_payload
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return default_payload
            if "baselines" not in payload or not isinstance(payload.get("baselines"), list):
                payload["baselines"] = []
            return payload
        except Exception:  # noqa: BLE001
            return default_payload

    def _patch_hash(
        self,
        *,
        baseline_id: str,
        patch: dict[str, Any],
        align_to_eval: bool,
        replace_metrics: bool,
    ) -> str:
        payload = {
            "baseline_id": baseline_id,
            "patch": patch,
            "align_to_eval": align_to_eval,
            "replace_metrics": replace_metrics,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _changed_fields(self, *, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        changed: list[str] = []
        top_level_fields = [
            "label",
            "source_type",
            "source",
            "source_date",
            "suite_id",
            "scoring_protocol",
            "verified",
            "enabled",
            "notes",
        ]
        for field in top_level_fields:
            if before.get(field) != after.get(field):
                changed.append(field)

        before_evidence = before.get("evidence", {})
        after_evidence = after.get("evidence", {})
        if isinstance(before_evidence, dict) and isinstance(after_evidence, dict):
            for key in sorted(set(before_evidence.keys()) | set(after_evidence.keys())):
                if before_evidence.get(key) != after_evidence.get(key):
                    changed.append(f"evidence.{key}")

        before_metrics = before.get("metrics", {})
        after_metrics = after.get("metrics", {})
        if isinstance(before_metrics, dict) and isinstance(after_metrics, dict):
            for key in sorted(set(before_metrics.keys()) | set(after_metrics.keys())):
                if before_metrics.get(key) != after_metrics.get(key):
                    changed.append(f"metrics.{key}")
        return changed
