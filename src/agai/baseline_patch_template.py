from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .baseline_registry import DeclaredBaselineComparator


class ExternalBaselinePatchTemplateService:
    def __init__(self, registry_path: str = "config/frontier_baselines.json") -> None:
        self.registry_path = Path(registry_path)

    def build_template(
        self,
        *,
        baseline_id: str,
        eval_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        baseline = self._load_baseline(baseline_id=baseline_id)
        if baseline is None:
            return {
                "status": "error",
                "reason": f"baseline not found: {baseline_id}",
                "baseline_id": baseline_id,
                "registry_path": str(self.registry_path),
            }

        reasons = self._comparability_reasons(baseline_id=baseline_id, eval_report=eval_report)
        reason_set = {str(reason) for reason in reasons}
        patch_template: dict[str, Any] = {}
        checklist: list[str] = []
        blocking_categories: list[str] = []

        need_source = (
            "source metadata appears placeholder or unknown" in reason_set
            or self._contains_placeholder_token(str(baseline.get("source", "")))
        )
        need_source_date = (
            "source_date must be ISO-8601 date (YYYY-MM-DD)" in reason_set
            or not self._is_iso_date(str(baseline.get("source_date", "")))
        )
        if need_source:
            patch_template["source"] = ""
            checklist.append("Set source to concrete external reference (paper URL, dataset URL, or report ID).")
            blocking_categories.append("source-metadata")
        if need_source_date:
            patch_template["source_date"] = ""
            checklist.append("Set source_date as ISO date (YYYY-MM-DD).")
            blocking_categories.append("source-date")

        evidence = baseline.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}
        evidence_patch: dict[str, Any] = {}
        need_citation = self._needs_evidence_field(
            field="citation",
            reasons=reason_set,
            current_value=str(evidence.get("citation", "")),
        )
        need_retrieval_date = self._needs_evidence_field(
            field="retrieval_date",
            reasons=reason_set,
            current_value=str(evidence.get("retrieval_date", "")),
        )
        need_verification_method = self._needs_evidence_field(
            field="verification_method",
            reasons=reason_set,
            current_value=str(evidence.get("verification_method", "")),
        )
        if need_citation:
            evidence_patch["citation"] = ""
            checklist.append("Set evidence.citation to traceable source citation.")
            blocking_categories.append("evidence-citation")
        if need_retrieval_date:
            evidence_patch["retrieval_date"] = ""
            checklist.append("Set evidence.retrieval_date as ISO date (YYYY-MM-DD).")
            blocking_categories.append("evidence-retrieval-date")
        if need_verification_method:
            evidence_patch["verification_method"] = ""
            checklist.append("Set evidence.verification_method to concrete verification procedure.")
            blocking_categories.append("evidence-verification-method")
        if evidence_patch:
            patch_template["evidence"] = evidence_patch

        suite_mismatch = "suite mismatch" in reason_set
        scoring_mismatch = "scoring protocol mismatch" in reason_set
        target_suite = str((eval_report or {}).get("benchmark_progress", {}).get("suite_id", "")).strip()
        target_scoring = str(
            (eval_report or {}).get("benchmark_provenance", {}).get("scoring_reference", "")
        ).strip()
        if suite_mismatch:
            patch_template["suite_id"] = target_suite
            checklist.append("Align suite_id to current internal hard-suite harness.")
            blocking_categories.append("suite-alignment")
        if scoring_mismatch:
            patch_template["scoring_protocol"] = target_scoring
            checklist.append("Align scoring_protocol to current scoring reference.")
            blocking_categories.append("scoring-alignment")

        metrics_reason = (
            "missing metric payload" in reason_set
            or "no overlapping metrics" in reason_set
            or any(reason.startswith("insufficient overlapping metrics") for reason in reason_set)
        )
        if metrics_reason:
            patch_template["metrics"] = {
                "quality": None,
                "aggregate_delta": None,
            }
            checklist.append("Fill metrics from external source results (numeric values only).")
            blocking_categories.append("metrics-overlap")

        if not patch_template:
            checklist.append("No normalization patch required from current comparability reasons.")

        comparability_row = self._comparability_row(
            baseline_id=baseline_id,
            eval_report=eval_report,
        )
        comparable = bool(comparability_row.get("comparability", {}).get("comparable", False))
        template = {
            "status": "ok",
            "baseline_id": baseline_id,
            "registry_path": str(self.registry_path),
            "comparability_reasons": sorted(reason_set),
            "comparable": comparable,
            "blocking_categories": sorted(set(blocking_categories)),
            "patch_template": patch_template,
            "checklist": checklist,
            "baseline_snapshot": {
                "source_type": str(baseline.get("source_type", "")),
                "source": str(baseline.get("source", "")),
                "source_date": str(baseline.get("source_date", "")),
                "suite_id": str(baseline.get("suite_id", "")),
                "scoring_protocol": str(baseline.get("scoring_protocol", "")),
                "verified": bool(baseline.get("verified", False)),
                "metric_keys": sorted(str(key) for key in dict(baseline.get("metrics", {})).keys()),
            },
            "generated_at": datetime.utcnow().isoformat(),
            "disclaimer": (
                "Template fields are intentionally incomplete and must be filled from real external evidence. "
                "Using this template does not imply comparability, replication, or external-claim readiness."
            ),
        }
        return template

    def _load_baseline(self, *, baseline_id: str) -> dict[str, Any] | None:
        registry = self._load_registry()
        baselines = registry.get("baselines", [])
        if not isinstance(baselines, list):
            return None
        for row in baselines:
            if str(row.get("baseline_id", "")) == baseline_id:
                return dict(row)
        return None

    def _comparability_row(self, *, baseline_id: str, eval_report: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(eval_report, dict):
            return {}
        comparator = DeclaredBaselineComparator(registry_path=str(self.registry_path))
        comparison = comparator.compare(eval_report)
        rows = comparison.get("comparisons", [])
        if not isinstance(rows, list):
            return {}
        for row in rows:
            if str(row.get("baseline_id", "")) == baseline_id:
                return row
        return {}

    def _comparability_reasons(self, *, baseline_id: str, eval_report: dict[str, Any] | None) -> list[str]:
        row = self._comparability_row(baseline_id=baseline_id, eval_report=eval_report)
        reasons = row.get("comparability", {}).get("reasons", [])
        if not isinstance(reasons, list):
            return []
        return [str(reason) for reason in reasons]

    def _needs_evidence_field(self, *, field: str, reasons: set[str], current_value: str) -> bool:
        missing_reason = any(
            reason.startswith("missing verification evidence fields") and field in reason
            for reason in reasons
        )
        placeholder_reason_map = {
            "citation": "citation appears placeholder or unknown",
            "retrieval_date": "retrieval_date must be ISO-8601 date (YYYY-MM-DD)",
            "verification_method": "verification_method appears placeholder or unknown",
        }
        reason_hit = placeholder_reason_map.get(field, "") in reasons
        empty_value = not current_value.strip()
        placeholder_value = self._contains_placeholder_token(current_value)
        if field == "retrieval_date":
            return missing_reason or reason_hit or not self._is_iso_date(current_value)
        return missing_reason or reason_hit or empty_value or placeholder_value

    def _contains_placeholder_token(self, value: str) -> bool:
        tokens = ["unknown", "pending", "placeholder", "tbd"]
        normalized = value.strip().lower()
        if not normalized:
            return True
        return any(token in normalized for token in tokens)

    def _is_iso_date(self, value: str) -> bool:
        payload = value.strip()
        if not payload:
            return False
        try:
            datetime.fromisoformat(payload)
            return len(payload) == 10
        except ValueError:
            return False

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
