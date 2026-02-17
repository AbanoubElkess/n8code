from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .baseline_patch_template import ExternalBaselinePatchTemplateService


class ExternalClaimCampaignScaffoldService:
    _MANUAL_PATCH_ACTIONS = {
        "refresh_evidence_payload",
        "replace_placeholder_metadata",
        "normalize_metadata_dates",
        "normalize_harness_alignment",
        "add_overlapping_metrics",
        "increase_metric_overlap",
    }

    def build(
        self,
        *,
        claim_plan: dict[str, Any],
        eval_report: dict[str, Any],
        registry_path: str,
        output_dir: str,
        default_max_metric_delta: float = 0.02,
    ) -> dict[str, Any]:
        if not isinstance(claim_plan, dict):
            return {"status": "error", "reason": "claim_plan must be an object"}
        if not isinstance(eval_report, dict):
            return {"status": "error", "reason": "eval_report must be an object"}

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        patch_service = ExternalBaselinePatchTemplateService(registry_path=registry_path)
        row_plans = claim_plan.get("row_plans", [])
        if not isinstance(row_plans, list):
            row_plans = []

        patch_map: dict[str, dict[str, Any]] = {}
        generated_files: list[dict[str, Any]] = []
        template_errors: list[dict[str, str]] = []
        targeted_rows = 0

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
            if not (action_types & self._MANUAL_PATCH_ACTIONS):
                continue
            targeted_rows += 1

            template = patch_service.build_template(
                baseline_id=baseline_id,
                eval_report=eval_report,
            )
            if template.get("status") != "ok":
                template_errors.append(
                    {
                        "baseline_id": baseline_id,
                        "reason": str(template.get("reason", "template generation failed")),
                    }
                )
                continue

            patch_payload = template.get("patch_template", {})
            if not isinstance(patch_payload, dict):
                patch_payload = {}

            file_name = f"patch_overrides_{self._safe_name(baseline_id)}.json"
            patch_path = out_dir / file_name
            patch_path.write_text(json.dumps(patch_payload, indent=2, ensure_ascii=True), encoding="utf-8")
            unresolved_fields = self._unresolved_fields(patch_payload)
            patch_map[baseline_id] = {
                "patch_overrides_path": str(patch_path),
                "align_to_eval": True,
                "replace_metrics": False,
                "max_metric_delta": float(default_max_metric_delta),
            }
            generated_files.append(
                {
                    "baseline_id": baseline_id,
                    "patch_overrides_path": str(patch_path),
                    "blocking_categories": list(template.get("blocking_categories", [])),
                    "unresolved_fields": unresolved_fields,
                    "requires_manual_fill": len(unresolved_fields) > 0,
                }
            )

        patch_map_path = out_dir / "patch_map.generated.json"
        patch_map_path.write_text(json.dumps(patch_map, indent=2, ensure_ascii=True), encoding="utf-8")
        ingest_manifest_path = out_dir / "ingest_manifest.generated.json"
        ingest_manifest_path.write_text(json.dumps([], indent=2, ensure_ascii=True), encoding="utf-8")

        status = "ok"
        if targeted_rows == 0:
            status = "empty"
        elif template_errors and generated_files:
            status = "partial"
        elif template_errors and not generated_files:
            status = "error"
        unresolved_total = sum(len(item.get("unresolved_fields", [])) for item in generated_files)
        return {
            "status": status,
            "registry_path": str(Path(registry_path)),
            "output_dir": str(out_dir),
            "patch_map_path": str(patch_map_path),
            "ingest_manifest_path": str(ingest_manifest_path),
            "summary": {
                "targeted_rows": targeted_rows,
                "generated_patch_files": len(generated_files),
                "template_errors": len(template_errors),
                "unresolved_fields": unresolved_total,
            },
            "generated_files": generated_files,
            "template_errors": template_errors,
            "next_command_hint": (
                "external-claim-campaign-draft --patch-map "
                f"{patch_map_path} --ingest-manifest {ingest_manifest_path}"
            ),
            "disclaimer": (
                "Scaffold files contain template placeholders derived from comparability blockers. "
                "They must be filled with real evidence values before campaign draft can reach ready state."
            ),
        }

    def _safe_name(self, value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
        return normalized or "baseline"

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
