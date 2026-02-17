from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ExternalClaimCampaignEvidenceSchemaService:
    def build(
        self,
        *,
        scaffold_payload: dict[str, Any],
        eval_report: dict[str, Any],
        output_path: str,
        default_max_metric_delta: float = 0.02,
    ) -> dict[str, Any]:
        if not isinstance(scaffold_payload, dict):
            return {"status": "error", "reason": "scaffold_payload must be an object"}
        if not isinstance(eval_report, dict):
            return {"status": "error", "reason": "eval_report must be an object"}

        generated_files = scaffold_payload.get("generated_files", [])
        if not isinstance(generated_files, list):
            generated_files = []

        suite_id = str(eval_report.get("benchmark_progress", {}).get("suite_id", "")).strip()
        scoring_reference = str(
            eval_report.get("benchmark_provenance", {}).get("scoring_reference", "")
        ).strip()
        defaults = {
            "align_to_eval": True,
            "replace_metrics": False,
            "max_metric_delta": float(default_max_metric_delta),
            "generate_ingest_payload": False,
            "ingest_payload": {
                "source_type": "external_reported",
                "verified": False,
                "enabled": True,
                "evidence": {
                    "replication_status": "pending",
                },
            },
        }

        baselines: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []
        template_errors: list[dict[str, str]] = []
        for row in generated_files:
            if not isinstance(row, dict):
                continue
            baseline_id = str(row.get("baseline_id", "")).strip()
            patch_path = str(row.get("patch_overrides_path", "")).strip()
            if not baseline_id:
                continue
            load_result = self._load_json_object(path=patch_path)
            if load_result.get("status") != "ok":
                template_errors.append(
                    {
                        "baseline_id": baseline_id,
                        "reason": str(load_result.get("reason", "failed to load patch template")),
                    }
                )
                continue

            patch_template = load_result["payload"]
            normalized_template = self._normalize_template(patch_template)
            unresolved_fields = self._unresolved_fields(normalized_template)
            baseline_entry: dict[str, Any] = dict(normalized_template)
            baseline_entry["align_to_eval"] = True
            baseline_entry["replace_metrics"] = False
            baseline_entry["max_metric_delta"] = float(default_max_metric_delta)
            baseline_entry["generate_ingest_payload"] = False
            baseline_entry["ingest_payload"] = self._build_ingest_template(
                baseline_id=baseline_id,
                suite_id=suite_id,
                scoring_reference=scoring_reference,
                patch_template=normalized_template,
            )
            baselines[baseline_id] = baseline_entry
            rows.append(
                {
                    "baseline_id": baseline_id,
                    "patch_overrides_path": patch_path,
                    "blocking_categories": list(row.get("blocking_categories", []))
                    if isinstance(row.get("blocking_categories"), list)
                    else [],
                    "unresolved_fields": unresolved_fields,
                }
            )

        evidence_map = {
            "defaults": defaults,
            "baselines": baselines,
            "ingest_payload_paths": [],
        }

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence_map, indent=2, ensure_ascii=True), encoding="utf-8")

        status = "ok"
        if not generated_files:
            status = "empty"
        elif generated_files and not baselines:
            status = "error"
        elif template_errors:
            status = "partial"

        return {
            "status": status,
            "output_path": str(out_path),
            "summary": {
                "targeted_baselines": len(generated_files),
                "schema_baselines": len(baselines),
                "template_errors": len(template_errors),
                "total_unresolved_fields": sum(len(row.get("unresolved_fields", [])) for row in rows),
            },
            "defaults": {
                "suite_id": suite_id,
                "scoring_protocol": scoring_reference,
                "align_to_eval": True,
                "replace_metrics": False,
                "max_metric_delta": float(default_max_metric_delta),
                "generate_ingest_payload": False,
            },
            "rows": rows,
            "template_errors": template_errors,
            "next_command_hint": (
                "external-claim-campaign-autofill --evidence-map "
                f"{out_path}"
            ),
            "disclaimer": (
                "Schema file is a required-input template. "
                "All placeholder fields must be filled with concrete evidence before readiness can pass."
            ),
        }

    def _normalize_template(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, dict):
                normalized[key] = self._normalize_template(value)
            elif value is None:
                normalized[key] = ""
            else:
                normalized[key] = value
        return normalized

    def _load_json_object(self, *, path: str) -> dict[str, Any]:
        payload_path = Path(path)
        if not payload_path.exists():
            return {"status": "error", "reason": f"file not found: {payload_path}"}
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"status": "error", "reason": f"invalid json: {exc}"}
        if not isinstance(payload, dict):
            return {"status": "error", "reason": "payload must be an object"}
        return {"status": "ok", "payload": payload}

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

    def _build_ingest_template(
        self,
        *,
        baseline_id: str,
        suite_id: str,
        scoring_reference: str,
        patch_template: dict[str, Any],
    ) -> dict[str, Any]:
        template_evidence = patch_template.get("evidence", {})
        if not isinstance(template_evidence, dict):
            template_evidence = {}
        template_metrics = patch_template.get("metrics", {})
        if not isinstance(template_metrics, dict):
            template_metrics = {}

        source = str(patch_template.get("source", ""))
        source_date = str(patch_template.get("source_date", ""))
        citation = str(template_evidence.get("citation", ""))
        retrieval_date = str(template_evidence.get("retrieval_date", ""))
        verification_method = str(template_evidence.get("verification_method", ""))
        metrics: dict[str, Any] = {}
        for key, value in template_metrics.items():
            metrics[str(key)] = value

        return {
            "baseline_id": f"{baseline_id}-extra",
            "label": "",
            "source_type": "external_reported",
            "source": source,
            "source_date": source_date,
            "verified": False,
            "enabled": True,
            "suite_id": suite_id,
            "scoring_protocol": scoring_reference,
            "evidence": {
                "citation": citation,
                "artifact_hash": "",
                "retrieval_date": retrieval_date,
                "verification_method": verification_method,
                "replication_status": "pending",
            },
            "metrics": metrics,
            "notes": "",
        }
