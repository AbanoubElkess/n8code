from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .baseline_ingestion import ExternalBaselineIngestionService


class ExternalClaimCampaignValidatorService:
    _MANUAL_PATCH_ACTIONS = {
        "refresh_evidence_payload",
        "replace_placeholder_metadata",
        "normalize_metadata_dates",
        "normalize_harness_alignment",
        "add_overlapping_metrics",
        "increase_metric_overlap",
    }

    def validate(
        self,
        *,
        claim_plan: dict[str, Any],
        patch_overrides_map: dict[str, Any] | None = None,
        ingest_payload_paths: list[str] | None = None,
        eval_report: dict[str, Any] | None = None,
        registry_path: str = "config/frontier_baselines.json",
    ) -> dict[str, Any]:
        if not isinstance(claim_plan, dict):
            return {"status": "error", "reason": "claim_plan must be an object"}
        patch_map = patch_overrides_map if isinstance(patch_overrides_map, dict) else {}
        ingest_paths = ingest_payload_paths if isinstance(ingest_payload_paths, list) else []
        eval_payload = eval_report if isinstance(eval_report, dict) else {}

        baseline_checks: list[dict[str, Any]] = []
        ingest_checks: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []

        rows = claim_plan.get("row_plans", [])
        if not isinstance(rows, list):
            rows = []
        checked_rows = 0
        for row in rows:
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
            required_actions = sorted(action_types & self._MANUAL_PATCH_ACTIONS)
            if not required_actions:
                continue
            checked_rows += 1
            row_issues = self._validate_patch_mapping(
                baseline_id=baseline_id,
                required_actions=required_actions,
                entry=patch_map.get(baseline_id),
                eval_report=eval_payload,
            )
            issues.extend(row_issues)
            baseline_checks.append(
                {
                    "baseline_id": baseline_id,
                    "required_actions": required_actions,
                    "status": "ok" if not row_issues else "error",
                    "issue_count": len(row_issues),
                }
            )

        ingest_issues, ingest_checks = self._validate_ingest_payloads(
            ingest_paths=ingest_paths,
            registry_path=registry_path,
        )
        issues.extend(ingest_issues)

        status = "ok" if not issues else "error"
        return {
            "status": status,
            "summary": {
                "checked_baselines": checked_rows,
                "checked_ingest_payloads": len(ingest_checks),
                "issues": len(issues),
            },
            "baseline_checks": baseline_checks,
            "ingest_checks": ingest_checks,
            "issues": issues,
            "disclaimer": (
                "Validator checks input completeness and format only. "
                "It does not attest external comparability or execute promotion."
            ),
        }

    def _validate_patch_mapping(
        self,
        *,
        baseline_id: str,
        required_actions: list[str],
        entry: Any,
        eval_report: dict[str, Any],
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        if entry is None:
            return [
                self._issue(
                    scope="patch-map",
                    baseline_id=baseline_id,
                    code="missing_patch_mapping",
                    field="patch_overrides_map",
                    message="missing patch map entry for baseline",
                    suggestion="Add baseline entry to patch map with patch_overrides_path.",
                )
            ]

        patch_path = ""
        align_to_eval = True
        if isinstance(entry, str):
            patch_path = entry
        elif isinstance(entry, dict):
            patch_path = str(entry.get("patch_overrides_path", "")).strip()
            align_to_eval = bool(entry.get("align_to_eval", True))
        else:
            return [
                self._issue(
                    scope="patch-map",
                    baseline_id=baseline_id,
                    code="invalid_patch_mapping_type",
                    field="patch_overrides_map",
                    message="patch map entry must be string path or object",
                    suggestion="Use {\"patch_overrides_path\": \"...\"}.",
                )
            ]

        if not patch_path:
            return [
                self._issue(
                    scope="patch-map",
                    baseline_id=baseline_id,
                    code="missing_patch_path",
                    field="patch_overrides_path",
                    message="patch_overrides_path is required",
                    suggestion="Point to a non-empty patch overrides json file.",
                )
            ]
        load_result = self._load_json_object(path=patch_path)
        if load_result.get("status") != "ok":
            return [
                self._issue(
                    scope="patch-file",
                    baseline_id=baseline_id,
                    code="patch_load_failed",
                    field="patch_overrides_path",
                    message=str(load_result.get("reason", "failed to load patch file")),
                    suggestion="Fix path and json formatting.",
                )
            ]
        patch = load_result["payload"]

        unresolved = self._unresolved_fields(patch)
        for field in unresolved:
            issues.append(
                self._issue(
                    scope="patch-file",
                    baseline_id=baseline_id,
                    code="unresolved_field",
                    field=field,
                    message=f"field is empty/null: {field}",
                    suggestion="Fill with concrete evidence-backed value.",
                )
            )

        if "refresh_evidence_payload" in required_actions or "replace_placeholder_metadata" in required_actions:
            source = str(patch.get("source", ""))
            if self._contains_placeholder_token(source):
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="placeholder_source",
                        field="source",
                        message="source is missing or placeholder",
                        suggestion="Set source to concrete external reference.",
                    )
                )
            evidence = patch.get("evidence", {})
            if not isinstance(evidence, dict):
                evidence = {}
            citation = str(evidence.get("citation", ""))
            verification_method = str(evidence.get("verification_method", ""))
            if self._contains_placeholder_token(citation):
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="placeholder_citation",
                        field="evidence.citation",
                        message="citation is missing or placeholder",
                        suggestion="Set evidence.citation to traceable source citation.",
                    )
                )
            if self._contains_placeholder_token(verification_method):
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="placeholder_verification_method",
                        field="evidence.verification_method",
                        message="verification_method is missing or placeholder",
                        suggestion="Set evidence.verification_method to concrete procedure.",
                    )
                )

        if "normalize_metadata_dates" in required_actions:
            source_date = str(patch.get("source_date", ""))
            if not self._is_iso_date(source_date):
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="invalid_source_date",
                        field="source_date",
                        message="source_date must be ISO-8601 (YYYY-MM-DD)",
                        suggestion="Set source_date like 2026-02-17.",
                    )
                )
            evidence = patch.get("evidence", {})
            if not isinstance(evidence, dict):
                evidence = {}
            retrieval_date = str(evidence.get("retrieval_date", ""))
            if not self._is_iso_date(retrieval_date):
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="invalid_retrieval_date",
                        field="evidence.retrieval_date",
                        message="retrieval_date must be ISO-8601 (YYYY-MM-DD)",
                        suggestion="Set retrieval_date like 2026-02-17.",
                    )
                )

        if "normalize_harness_alignment" in required_actions:
            suite_id_target = str(eval_report.get("benchmark_progress", {}).get("suite_id", "")).strip()
            scoring_target = str(eval_report.get("benchmark_provenance", {}).get("scoring_reference", "")).strip()
            suite_id_patch = str(patch.get("suite_id", "")).strip()
            scoring_patch = str(patch.get("scoring_protocol", "")).strip()
            if not align_to_eval:
                if suite_id_target and suite_id_patch != suite_id_target:
                    issues.append(
                        self._issue(
                            scope="patch-file",
                            baseline_id=baseline_id,
                            code="suite_alignment_mismatch",
                            field="suite_id",
                            message=f"suite_id mismatch: expected {suite_id_target}",
                            suggestion="Set align_to_eval=true or patch suite_id to eval suite.",
                        )
                    )
                if scoring_target and scoring_patch != scoring_target:
                    issues.append(
                        self._issue(
                            scope="patch-file",
                            baseline_id=baseline_id,
                            code="scoring_alignment_mismatch",
                            field="scoring_protocol",
                            message=f"scoring_protocol mismatch: expected {scoring_target}",
                            suggestion="Set align_to_eval=true or patch scoring_protocol to eval reference.",
                        )
                    )

        if "add_overlapping_metrics" in required_actions or "increase_metric_overlap" in required_actions:
            observed = eval_report.get("benchmark_progress", {}).get("observed", {})
            observed_keys = (
                {str(key) for key in observed.keys()}
                if isinstance(observed, dict)
                else set()
            )
            metrics = patch.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            if not metrics:
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="missing_metrics",
                        field="metrics",
                        message="metrics payload is required for overlap actions",
                        suggestion="Add numeric metrics matching eval observed keys.",
                    )
                )
            overlap_count = 0
            for key, value in metrics.items():
                try:
                    float(value)
                except (TypeError, ValueError):
                    issues.append(
                        self._issue(
                            scope="patch-file",
                            baseline_id=baseline_id,
                            code="non_numeric_metric",
                            field=f"metrics.{key}",
                            message=f"metric {key} must be numeric",
                            suggestion="Use numeric value (int/float).",
                        )
                    )
                    continue
                if str(key) in observed_keys:
                    overlap_count += 1
            if observed_keys and overlap_count == 0:
                issues.append(
                    self._issue(
                        scope="patch-file",
                        baseline_id=baseline_id,
                        code="zero_metric_overlap",
                        field="metrics",
                        message="no overlap with eval observed metrics",
                        suggestion="Include at least one metric key from eval observed metrics.",
                    )
                )
        return issues

    def _validate_ingest_payloads(
        self,
        *,
        ingest_paths: list[str],
        registry_path: str,
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        checks: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        with tempfile.TemporaryDirectory(prefix="agai-campaign-validate-") as temp_dir:
            temp_registry = Path(temp_dir) / "frontier_baselines.json"
            source_registry = Path(registry_path)
            if source_registry.exists():
                shutil.copy2(source_registry, temp_registry)
            else:
                temp_registry.write_text(
                    json.dumps(
                        {"registry_version": "validation-temp", "baselines": []},
                        ensure_ascii=True,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            service = ExternalBaselineIngestionService(registry_path=str(temp_registry))
            for raw_path in ingest_paths:
                payload_path = str(raw_path).strip()
                if not payload_path:
                    continue
                result = service.ingest_file(payload_path)
                status = str(result.get("status", "error"))
                errors = result.get("errors", [])
                if not isinstance(errors, list):
                    errors = []
                checks.append(
                    {
                        "payload_path": payload_path,
                        "status": status,
                        "error_count": len(errors),
                    }
                )
                if status != "ok":
                    if errors:
                        for err in errors:
                            issues.append(
                                self._issue(
                                    scope="ingest-payload",
                                    baseline_id="",
                                    code="ingest_validation_error",
                                    field=payload_path,
                                    message=str(err),
                                    suggestion="Fix ingest payload fields to satisfy ingestion validation.",
                                )
                            )
                    else:
                        issues.append(
                            self._issue(
                                scope="ingest-payload",
                                baseline_id="",
                                code="ingest_failed",
                                field=payload_path,
                                message=str(result.get("reason", "ingest payload validation failed")),
                                suggestion="Check payload format and required external baseline fields.",
                            )
                        )
        return issues, checks

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

    def _issue(
        self,
        *,
        scope: str,
        baseline_id: str,
        code: str,
        field: str,
        message: str,
        suggestion: str,
    ) -> dict[str, str]:
        return {
            "scope": scope,
            "baseline_id": baseline_id,
            "code": code,
            "field": field,
            "message": message,
            "suggestion": suggestion,
        }
