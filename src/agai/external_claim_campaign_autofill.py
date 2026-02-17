from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any


class ExternalClaimCampaignAutofillService:
    _PLACEHOLDER_TOKENS = ("unknown", "pending", "placeholder", "tbd")

    def build(
        self,
        *,
        scaffold_payload: dict[str, Any],
        evidence_map: dict[str, Any],
        eval_report: dict[str, Any],
        output_dir: str,
    ) -> dict[str, Any]:
        if not isinstance(scaffold_payload, dict):
            return {"status": "error", "reason": "scaffold_payload must be an object"}
        if not isinstance(evidence_map, dict):
            return {"status": "error", "reason": "evidence_map must be an object"}
        if not isinstance(eval_report, dict):
            return {"status": "error", "reason": "eval_report must be an object"}

        generated_files = scaffold_payload.get("generated_files", [])
        if not isinstance(generated_files, list):
            generated_files = []
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        defaults = evidence_map.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
        baseline_values = evidence_map.get("baselines", {})
        if not isinstance(baseline_values, dict):
            baseline_values = {}
        explicit_ingest_paths = evidence_map.get("ingest_payload_paths", [])
        if not isinstance(explicit_ingest_paths, list):
            explicit_ingest_paths = []

        filled_patch_map: dict[str, dict[str, Any]] = {}
        filled_files: list[dict[str, Any]] = []
        unresolved_baselines: list[dict[str, Any]] = []
        generated_ingest_payloads: list[dict[str, Any]] = []
        generated_ingest_paths: list[str] = []
        for row in generated_files:
            if not isinstance(row, dict):
                continue
            baseline_id = str(row.get("baseline_id", "")).strip()
            patch_path = str(row.get("patch_overrides_path", "")).strip()
            if not baseline_id or not patch_path:
                continue

            load_result = self._load_json_object(path=patch_path)
            if load_result.get("status") != "ok":
                unresolved_baselines.append(
                    {
                        "baseline_id": baseline_id,
                        "reason": str(load_result.get("reason", "unable to load scaffold patch")),
                    }
                )
                continue
            scaffold_patch = load_result["payload"]
            baseline_entry = baseline_values.get(baseline_id)
            if not isinstance(baseline_entry, dict):
                baseline_entry = {}
            merged = self._merge_patch(
                base_patch=scaffold_patch,
                baseline_entry=baseline_entry,
                defaults=defaults,
                eval_report=eval_report,
            )
            unresolved_fields = self._unresolved_fields(merged)
            filled_patch_path = out_dir / f"patch_overrides_filled_{self._safe_name(baseline_id)}.json"
            filled_patch_path.write_text(json.dumps(merged, indent=2, ensure_ascii=True), encoding="utf-8")

            align_to_eval = bool(baseline_entry.get("align_to_eval", defaults.get("align_to_eval", True)))
            replace_metrics = bool(
                baseline_entry.get("replace_metrics", defaults.get("replace_metrics", False))
            )
            max_metric_delta = float(
                baseline_entry.get("max_metric_delta", defaults.get("max_metric_delta", 0.02))
            )
            filled_patch_map[baseline_id] = {
                "patch_overrides_path": str(filled_patch_path),
                "align_to_eval": align_to_eval,
                "replace_metrics": replace_metrics,
                "max_metric_delta": max_metric_delta,
            }
            if unresolved_fields:
                unresolved_baselines.append(
                    {
                        "baseline_id": baseline_id,
                        "reason": "autofill still has unresolved fields",
                        "unresolved_fields": unresolved_fields,
                    }
                )
            filled_files.append(
                {
                    "baseline_id": baseline_id,
                    "patch_overrides_path": str(filled_patch_path),
                    "unresolved_fields": unresolved_fields,
                    "resolved": len(unresolved_fields) == 0,
                }
            )

            ingest_payload_result = self._build_inline_ingest_payload(
                baseline_id=baseline_id,
                baseline_entry=baseline_entry,
                defaults=defaults,
                merged_patch=merged,
                eval_report=eval_report,
                output_dir=out_dir,
            )
            ingest_status = str(ingest_payload_result.get("status", "skip"))
            if ingest_status == "ok":
                ingest_payload_path = str(ingest_payload_result.get("ingest_payload_path", "")).strip()
                if ingest_payload_path:
                    generated_ingest_paths.append(ingest_payload_path)
                    generated_ingest_payloads.append(
                        {
                            "baseline_id": baseline_id,
                            "ingest_payload_path": ingest_payload_path,
                            "resolved": True,
                        }
                    )
            elif ingest_status == "error":
                unresolved_baselines.append(
                    {
                        "baseline_id": baseline_id,
                        "reason": str(
                            ingest_payload_result.get("reason", "autofill could not generate ingest payload")
                        ),
                        "unresolved_fields": list(ingest_payload_result.get("unresolved_fields", [])),
                    }
                )
                generated_ingest_payloads.append(
                    {
                        "baseline_id": baseline_id,
                        "ingest_payload_path": "",
                        "resolved": False,
                        "reason": str(
                            ingest_payload_result.get("reason", "autofill could not generate ingest payload")
                        ),
                    }
                )

        ingest_manifest = self._build_ingest_manifest(
            explicit_paths=explicit_ingest_paths,
            baseline_values=baseline_values,
            generated_paths=generated_ingest_paths,
        )
        patch_map_path = out_dir / "patch_map.autofilled.json"
        patch_map_path.write_text(json.dumps(filled_patch_map, indent=2, ensure_ascii=True), encoding="utf-8")
        ingest_manifest_path = out_dir / "ingest_manifest.autofilled.json"
        ingest_manifest_path.write_text(json.dumps(ingest_manifest, indent=2, ensure_ascii=True), encoding="utf-8")

        total_baselines = len(filled_files)
        resolved_baselines = sum(1 for row in filled_files if bool(row.get("resolved", False)))
        unresolved_count = len(
            {
                str(row.get("baseline_id", "")).strip()
                for row in unresolved_baselines
                if str(row.get("baseline_id", "")).strip()
            }
        )
        status = "ok"
        if total_baselines == 0:
            status = "empty"
        elif unresolved_count == total_baselines:
            status = "blocked"
        elif unresolved_count > 0:
            status = "partial"

        return {
            "status": status,
            "output_dir": str(out_dir),
            "patch_map_path": str(patch_map_path),
            "ingest_manifest_path": str(ingest_manifest_path),
            "summary": {
                "baselines_total": total_baselines,
                "baselines_resolved": resolved_baselines,
                "baselines_unresolved": unresolved_count,
                "ingest_payload_paths": len(ingest_manifest),
                "generated_ingest_payloads": len(
                    [row for row in generated_ingest_payloads if bool(row.get("resolved", False))]
                ),
            },
            "filled_files": filled_files,
            "generated_ingest_payloads": generated_ingest_payloads,
            "unresolved_baselines": unresolved_baselines,
            "disclaimer": (
                "Autofill only applies user-provided evidence values and defaults. "
                "Unresolved fields remain blocked until explicitly supplied."
            ),
        }

    def _merge_patch(
        self,
        *,
        base_patch: dict[str, Any],
        baseline_entry: dict[str, Any],
        defaults: dict[str, Any],
        eval_report: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base_patch)
        source = self._pick_value(
            baseline_entry.get("source"),
            defaults.get("source"),
            merged.get("source"),
        )
        if source is not None:
            merged["source"] = source
        source_date = self._pick_value(
            baseline_entry.get("source_date"),
            defaults.get("source_date"),
            merged.get("source_date"),
        )
        if source_date is not None:
            merged["source_date"] = source_date

        evidence = merged.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}
        evidence_entry = baseline_entry.get("evidence", {})
        if not isinstance(evidence_entry, dict):
            evidence_entry = {}
        evidence_defaults = defaults.get("evidence", {})
        if not isinstance(evidence_defaults, dict):
            evidence_defaults = {}
        citation = self._pick_value(
            evidence_entry.get("citation"),
            baseline_entry.get("citation"),
            evidence_defaults.get("citation"),
            defaults.get("citation"),
            evidence.get("citation"),
        )
        retrieval_date = self._pick_value(
            evidence_entry.get("retrieval_date"),
            baseline_entry.get("retrieval_date"),
            evidence_defaults.get("retrieval_date"),
            defaults.get("retrieval_date"),
            evidence.get("retrieval_date"),
        )
        verification_method = self._pick_value(
            evidence_entry.get("verification_method"),
            baseline_entry.get("verification_method"),
            evidence_defaults.get("verification_method"),
            defaults.get("verification_method"),
            evidence.get("verification_method"),
        )
        if citation is not None:
            evidence["citation"] = citation
        if retrieval_date is not None:
            evidence["retrieval_date"] = retrieval_date
        if verification_method is not None:
            evidence["verification_method"] = verification_method
        if evidence:
            merged["evidence"] = evidence

        metrics = merged.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        metrics_entry = baseline_entry.get("metrics", {})
        if not isinstance(metrics_entry, dict):
            metrics_entry = {}
        metrics_defaults = defaults.get("metrics", {})
        if not isinstance(metrics_defaults, dict):
            metrics_defaults = {}
        for key, value in metrics_defaults.items():
            if key not in metrics or self._is_missing(metrics.get(key)):
                metrics[key] = value
        for key, value in metrics_entry.items():
            metrics[key] = value
        if metrics:
            merged["metrics"] = metrics

        align_to_eval = bool(baseline_entry.get("align_to_eval", defaults.get("align_to_eval", True)))
        if align_to_eval:
            suite_id = str(eval_report.get("benchmark_progress", {}).get("suite_id", "")).strip()
            scoring_reference = str(eval_report.get("benchmark_provenance", {}).get("scoring_reference", "")).strip()
            if suite_id:
                merged["suite_id"] = suite_id
            if scoring_reference:
                merged["scoring_protocol"] = scoring_reference
        return merged

    def _build_ingest_manifest(
        self,
        *,
        explicit_paths: list[str],
        baseline_values: dict[str, Any],
        generated_paths: list[str],
    ) -> list[str]:
        paths: list[str] = []
        for raw in explicit_paths:
            value = str(raw).strip()
            if value:
                paths.append(value)
        for row in baseline_values.values():
            if not isinstance(row, dict):
                continue
            single = str(row.get("ingest_payload_path", "")).strip()
            if single:
                paths.append(single)
            plural = row.get("ingest_payload_paths", [])
            if isinstance(plural, list):
                for raw in plural:
                    item = str(raw).strip()
                    if item:
                        paths.append(item)
        for raw in generated_paths:
            value = str(raw).strip()
            if value:
                paths.append(value)
        return list(dict.fromkeys(paths))

    def _build_inline_ingest_payload(
        self,
        *,
        baseline_id: str,
        baseline_entry: dict[str, Any],
        defaults: dict[str, Any],
        merged_patch: dict[str, Any],
        eval_report: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        ingest_entry = baseline_entry.get("ingest_payload", {})
        if not isinstance(ingest_entry, dict):
            ingest_entry = {}
        defaults_ingest = defaults.get("ingest_payload", {})
        if not isinstance(defaults_ingest, dict):
            defaults_ingest = {}
        generate_ingest = bool(
            baseline_entry.get(
                "generate_ingest_payload",
                defaults.get("generate_ingest_payload", False),
            )
        )
        if not ingest_entry and not generate_ingest:
            return {"status": "skip"}

        merged_evidence = merged_patch.get("evidence", {})
        if not isinstance(merged_evidence, dict):
            merged_evidence = {}
        ingest_evidence_entry = ingest_entry.get("evidence", {})
        if not isinstance(ingest_evidence_entry, dict):
            ingest_evidence_entry = {}
        defaults_evidence_entry = defaults_ingest.get("evidence", {})
        if not isinstance(defaults_evidence_entry, dict):
            defaults_evidence_entry = {}

        merged_metrics = merged_patch.get("metrics", {})
        if not isinstance(merged_metrics, dict):
            merged_metrics = {}
        ingest_metrics_entry = ingest_entry.get("metrics", {})
        if not isinstance(ingest_metrics_entry, dict):
            ingest_metrics_entry = {}
        defaults_metrics_entry = defaults_ingest.get("metrics", {})
        if not isinstance(defaults_metrics_entry, dict):
            defaults_metrics_entry = {}
        metrics: dict[str, Any] = {}
        for key, value in defaults_metrics_entry.items():
            metrics[str(key)] = value
        for key, value in merged_metrics.items():
            metrics[str(key)] = value
        for key, value in ingest_metrics_entry.items():
            metrics[str(key)] = value

        suite_id = self._pick_value(
            ingest_entry.get("suite_id"),
            defaults_ingest.get("suite_id"),
            merged_patch.get("suite_id"),
            eval_report.get("benchmark_progress", {}).get("suite_id", ""),
        )
        scoring_protocol = self._pick_value(
            ingest_entry.get("scoring_protocol"),
            defaults_ingest.get("scoring_protocol"),
            merged_patch.get("scoring_protocol"),
            eval_report.get("benchmark_provenance", {}).get("scoring_reference", ""),
        )

        ingest_payload: dict[str, Any] = {
            "baseline_id": self._pick_value(
                ingest_entry.get("baseline_id"),
                baseline_entry.get("ingest_baseline_id"),
                f"{baseline_id}-autofilled",
            ),
            "label": self._pick_value(
                ingest_entry.get("label"),
                baseline_entry.get("ingest_label"),
                f"Autofilled {baseline_id}",
            ),
            "source_type": str(
                self._pick_value(
                    ingest_entry.get("source_type"),
                    baseline_entry.get("source_type"),
                    defaults_ingest.get("source_type"),
                    "external_reported",
                )
            ),
            "source": self._pick_value(
                ingest_entry.get("source"),
                defaults_ingest.get("source"),
                merged_patch.get("source"),
            ),
            "source_date": self._pick_value(
                ingest_entry.get("source_date"),
                defaults_ingest.get("source_date"),
                merged_patch.get("source_date"),
            ),
            "verified": bool(
                ingest_entry.get("verified", baseline_entry.get("verified", defaults_ingest.get("verified", False)))
            ),
            "enabled": bool(
                ingest_entry.get("enabled", baseline_entry.get("enabled", defaults_ingest.get("enabled", True)))
            ),
            "suite_id": suite_id,
            "scoring_protocol": scoring_protocol,
            "evidence": {
                "citation": self._pick_value(
                    ingest_evidence_entry.get("citation"),
                    defaults_evidence_entry.get("citation"),
                    merged_evidence.get("citation"),
                ),
                "artifact_hash": self._pick_value(
                    ingest_evidence_entry.get("artifact_hash"),
                    defaults_evidence_entry.get("artifact_hash"),
                    "",
                ),
                "retrieval_date": self._pick_value(
                    ingest_evidence_entry.get("retrieval_date"),
                    defaults_evidence_entry.get("retrieval_date"),
                    merged_evidence.get("retrieval_date"),
                ),
                "verification_method": self._pick_value(
                    ingest_evidence_entry.get("verification_method"),
                    defaults_evidence_entry.get("verification_method"),
                    merged_evidence.get("verification_method"),
                ),
                "replication_status": self._pick_value(
                    ingest_evidence_entry.get("replication_status"),
                    defaults_evidence_entry.get("replication_status"),
                    "pending",
                ),
            },
            "metrics": metrics,
            "notes": str(
                self._pick_value(
                    ingest_entry.get("notes"),
                    baseline_entry.get("ingest_notes"),
                    defaults_ingest.get("notes"),
                    "",
                )
            ),
        }
        unresolved_fields = self._validate_inline_ingest_payload(ingest_payload)
        if unresolved_fields:
            return {
                "status": "error",
                "reason": "autofill ingest payload has unresolved or invalid fields",
                "unresolved_fields": unresolved_fields,
            }
        payload_baseline_id = str(ingest_payload.get("baseline_id", baseline_id)).strip() or baseline_id
        out_path = output_dir / f"ingest_payload_autofilled_{self._safe_name(payload_baseline_id)}.json"
        out_path.write_text(json.dumps(ingest_payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return {
            "status": "ok",
            "ingest_payload_path": str(out_path),
        }

    def _validate_inline_ingest_payload(self, payload: dict[str, Any]) -> list[str]:
        unresolved: list[str] = []
        required_fields = (
            "baseline_id",
            "label",
            "source_type",
            "source",
            "source_date",
            "suite_id",
            "scoring_protocol",
        )
        for field in required_fields:
            value = payload.get(field)
            if self._is_missing(value):
                unresolved.append(field)
        source_type = str(payload.get("source_type", "")).strip().lower()
        if source_type and not source_type.startswith("external"):
            unresolved.append("source_type (must start with external)")
        source = str(payload.get("source", "")).strip()
        if self._contains_placeholder_token(source):
            unresolved.append("source (placeholder token)")
        source_date = str(payload.get("source_date", "")).strip()
        if source_date and not self._is_iso_date(source_date):
            unresolved.append("source_date (invalid iso date)")

        evidence = payload.get("evidence", {})
        if not isinstance(evidence, dict):
            unresolved.append("evidence (must be object)")
            evidence = {}
        citation = str(evidence.get("citation", "")).strip()
        retrieval_date = str(evidence.get("retrieval_date", "")).strip()
        verification_method = str(evidence.get("verification_method", "")).strip()
        if self._is_missing(citation):
            unresolved.append("evidence.citation")
        elif self._contains_placeholder_token(citation):
            unresolved.append("evidence.citation (placeholder token)")
        if self._is_missing(retrieval_date):
            unresolved.append("evidence.retrieval_date")
        elif not self._is_iso_date(retrieval_date):
            unresolved.append("evidence.retrieval_date (invalid iso date)")
        if self._is_missing(verification_method):
            unresolved.append("evidence.verification_method")
        elif self._contains_placeholder_token(verification_method):
            unresolved.append("evidence.verification_method (placeholder token)")

        metrics = payload.get("metrics", {})
        if not isinstance(metrics, dict) or not metrics:
            unresolved.append("metrics")
        else:
            for key, value in metrics.items():
                if self._is_missing(value):
                    unresolved.append(f"metrics.{key}")
                    continue
                try:
                    float(value)
                except (TypeError, ValueError):
                    unresolved.append(f"metrics.{key} (non-numeric)")
        return sorted(dict.fromkeys(unresolved))

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

    def _pick_value(self, *values: Any) -> Any:
        for value in values:
            if self._is_missing(value):
                continue
            return value
        return None

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    def _contains_placeholder_token(self, value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return True
        return any(token in normalized for token in self._PLACEHOLDER_TOKENS)

    def _is_iso_date(self, value: str) -> bool:
        payload = value.strip()
        if not payload:
            return False
        try:
            datetime.fromisoformat(payload)
            return len(payload) == 10
        except ValueError:
            return False

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

    def _safe_name(self, value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
        return normalized or "baseline"
