from __future__ import annotations

from typing import Any


class ExternalClaimCampaignReadinessService:
    def evaluate(
        self,
        *,
        draft_payload: dict[str, Any],
        preview_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(draft_payload, dict):
            return {
                "status": "error",
                "reason": "draft_payload must be an object",
            }

        draft_status = str(draft_payload.get("status", "unknown"))
        summary = draft_payload.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        campaign_config = draft_payload.get("campaign_config", {})
        if not isinstance(campaign_config, dict):
            campaign_config = {}
        baseline_runs = campaign_config.get("baseline_runs", [])
        if not isinstance(baseline_runs, list):
            baseline_runs = []
        ingest_paths = campaign_config.get("ingest_payload_paths", [])
        if not isinstance(ingest_paths, list):
            ingest_paths = []

        unresolved_dependencies = int(summary.get("unresolved_dependencies", 0))
        staged_actions = len(baseline_runs) + len(ingest_paths)
        draft_reasons: list[str] = []
        if draft_status != "ok":
            draft_reasons.append(f"draft status is {draft_status}, expected ok")
        if unresolved_dependencies > 0:
            draft_reasons.append(f"draft has {unresolved_dependencies} unresolved dependencies")
        if staged_actions == 0:
            draft_reasons.append("draft has no staged baseline_runs or ingest payloads")
        ready_for_preview = len(draft_reasons) == 0

        preview_executed = isinstance(preview_payload, dict)
        preview_status = "not-executed"
        preview_promotable = False
        preview_reasons: list[str] = []
        if preview_executed:
            payload = preview_payload if isinstance(preview_payload, dict) else {}
            preview_status = str(payload.get("status", "unknown"))
            preview_promotable = bool(payload.get("promotable", False))
            if preview_status != "ok":
                preview_reasons.append(f"preview status is {preview_status}")
            if not preview_promotable:
                gate_eval = payload.get("gate_evaluation", {})
                if isinstance(gate_eval, dict):
                    reasons = gate_eval.get("reasons", [])
                    if isinstance(reasons, list) and reasons:
                        preview_reasons.extend(str(reason) for reason in reasons)
                    else:
                        preview_reasons.append(str(gate_eval.get("reason", "preview gate did not pass")))
                else:
                    preview_reasons.append("preview reported promotable=false")
        else:
            preview_reasons.append("preview not executed because draft gate is not satisfied")
        ready_for_execute = preview_executed and preview_status == "ok" and preview_promotable

        status = "blocked"
        if ready_for_preview and not preview_executed:
            status = "ready-for-preview"
        elif ready_for_preview and preview_executed and not ready_for_execute:
            status = "preview-gate-failed"
        elif ready_for_execute:
            status = "ready-for-execute"

        return {
            "status": status,
            "ready_for_preview": ready_for_preview,
            "ready_for_execute": ready_for_execute,
            "draft_gate": {
                "pass": ready_for_preview,
                "status": draft_status,
                "unresolved_dependencies": unresolved_dependencies,
                "staged_actions": staged_actions,
                "reasons": draft_reasons,
            },
            "preview_gate": {
                "executed": preview_executed,
                "pass": ready_for_execute,
                "status": preview_status,
                "promotable": preview_promotable,
                "reasons": preview_reasons,
            },
            "disclaimer": (
                "Readiness gate is an operational preflight check. "
                "ready-for-execute requires a promotable preview and still does not execute mutations."
            ),
        }
