from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ExternalClaimCampaignDraftService:
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
        patch_overrides_map: dict[str, Any] | None = None,
        ingest_payload_paths: list[str] | None = None,
        default_max_metric_delta: float = 0.02,
    ) -> dict[str, Any]:
        if not isinstance(claim_plan, dict):
            return {
                "status": "error",
                "reason": "claim_plan must be an object",
            }

        row_plans = claim_plan.get("row_plans", [])
        if not isinstance(row_plans, list):
            row_plans = []
        patch_map = patch_overrides_map if isinstance(patch_overrides_map, dict) else {}
        ingest_paths = ingest_payload_paths if isinstance(ingest_payload_paths, list) else []

        baseline_runs: list[dict[str, Any]] = []
        unresolved_dependencies: list[dict[str, Any]] = []
        staged_rows = 0
        for row in row_plans:
            if not isinstance(row, dict):
                continue
            baseline_id = str(row.get("baseline_id", "")).strip()
            if not baseline_id:
                continue
            staged_rows += 1
            actions = row.get("actions", [])
            if not isinstance(actions, list):
                actions = []
            action_types = {
                str(action.get("action_type", "")).strip()
                for action in actions
                if isinstance(action, dict)
            }
            requires_patch = len(action_types & self._MANUAL_PATCH_ACTIONS) > 0
            if requires_patch:
                resolved = self._resolve_patch_step(
                    baseline_id=baseline_id,
                    entry=patch_map.get(baseline_id),
                    default_max_metric_delta=default_max_metric_delta,
                )
                if resolved.get("status") != "ok":
                    unresolved_dependencies.append(
                        {
                            "baseline_id": baseline_id,
                            "reason": str(resolved.get("reason", "unable to resolve patch overrides")),
                            "requires_actions": sorted(action_types & self._MANUAL_PATCH_ACTIONS),
                        }
                    )
                    continue
                step = resolved.get("baseline_run", {})
                if isinstance(step, dict):
                    baseline_runs.append(step)
                continue

            if "attest_baseline" in action_types:
                baseline_runs.append(
                    {
                        "baseline_id": baseline_id,
                        "align_to_eval": True,
                        "replace_metrics": False,
                        "max_metric_delta": float(default_max_metric_delta),
                    }
                )

        ingest_stage = self._validate_ingest_paths(ingest_paths=ingest_paths)
        status = "ok"
        if unresolved_dependencies and (baseline_runs or ingest_stage["ingest_payload_paths"]):
            status = "partial"
        elif unresolved_dependencies and not baseline_runs and not ingest_stage["ingest_payload_paths"]:
            status = "blocked"
        elif not unresolved_dependencies and not baseline_runs and not ingest_stage["ingest_payload_paths"]:
            status = "empty"

        campaign_config = {
            "ingest_payload_paths": ingest_stage["ingest_payload_paths"],
            "baseline_runs": baseline_runs,
        }
        return {
            "status": status,
            "campaign_config": campaign_config,
            "summary": {
                "staged_rows": staged_rows,
                "baseline_runs_ready": len(baseline_runs),
                "ingest_payloads_ready": len(ingest_stage["ingest_payload_paths"]),
                "unresolved_dependencies": len(unresolved_dependencies),
            },
            "ingest_manifest_errors": ingest_stage["errors"],
            "unresolved_dependencies": unresolved_dependencies,
            "disclaimer": (
                "Draft generation stages only entries with concrete local payload files. "
                "Any unresolved dependencies must be filled manually before promotion."
            ),
        }

    def _resolve_patch_step(
        self,
        *,
        baseline_id: str,
        entry: Any,
        default_max_metric_delta: float,
    ) -> dict[str, Any]:
        if entry is None:
            return {"status": "error", "reason": "missing patch_overrides mapping for baseline"}

        patch_path = ""
        align_to_eval = True
        replace_metrics = False
        max_metric_delta = float(default_max_metric_delta)
        if isinstance(entry, str):
            patch_path = entry
        elif isinstance(entry, dict):
            patch_path = str(entry.get("patch_overrides_path", "")).strip()
            align_to_eval = bool(entry.get("align_to_eval", True))
            replace_metrics = bool(entry.get("replace_metrics", False))
            max_metric_delta = float(entry.get("max_metric_delta", default_max_metric_delta))
        else:
            return {
                "status": "error",
                "reason": "patch_overrides entry must be a path string or object",
            }

        if not patch_path:
            return {
                "status": "error",
                "reason": "patch_overrides_path is required",
            }

        payload = self._load_json_object(path=patch_path)
        if payload.get("status") != "ok":
            return payload
        patch_obj = payload.get("payload", {})
        if not isinstance(patch_obj, dict):
            return {"status": "error", "reason": "patch overrides payload must be an object"}

        unresolved_fields = self._unresolved_fields(patch_obj)
        if unresolved_fields:
            return {
                "status": "error",
                "reason": (
                    "patch overrides contains unresolved empty/null fields: "
                    + ", ".join(sorted(unresolved_fields))
                ),
            }

        return {
            "status": "ok",
            "baseline_run": {
                "baseline_id": baseline_id,
                "patch_overrides_path": str(Path(patch_path)),
                "align_to_eval": align_to_eval,
                "replace_metrics": replace_metrics,
                "max_metric_delta": max_metric_delta,
            },
        }

    def _validate_ingest_paths(self, *, ingest_paths: list[str]) -> dict[str, Any]:
        ready: list[str] = []
        errors: list[dict[str, str]] = []
        for raw_path in ingest_paths:
            path = str(raw_path).strip()
            if not path:
                continue
            loaded = self._load_json_object(path=path)
            if loaded.get("status") != "ok":
                errors.append(
                    {
                        "payload_path": path,
                        "reason": str(loaded.get("reason", "invalid ingest payload")),
                    }
                )
                continue
            payload = loaded.get("payload", {})
            baseline_id = str(payload.get("baseline_id", "")).strip() if isinstance(payload, dict) else ""
            if not baseline_id:
                errors.append(
                    {
                        "payload_path": path,
                        "reason": "ingest payload missing baseline_id",
                    }
                )
                continue
            ready.append(str(Path(path)))
        deduped = list(dict.fromkeys(ready))
        return {"ingest_payload_paths": deduped, "errors": errors}

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
