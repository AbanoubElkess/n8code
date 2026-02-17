from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ExternalBaselineAttestationService:
    def __init__(
        self,
        registry_path: str = "config/frontier_baselines.json",
        policy_path: str = "config/repro_policy.json",
    ) -> None:
        self.registry_path = Path(registry_path)
        self.policy_path = Path(policy_path)

    def _load_policy(self) -> dict[str, Any]:
        default_policy: dict[str, Any] = {
            "min_overlap_metrics": 2,
            "disallowed_placeholder_tokens": ["unknown", "pending", "placeholder", "tbd"],
        }
        if not self.policy_path.exists():
            return default_policy
        try:
            payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
            gates = payload.get("attestation_gates", {})
            tokens = gates.get("disallowed_placeholder_tokens", default_policy["disallowed_placeholder_tokens"])
            token_list = [str(token).strip().lower() for token in tokens if str(token).strip()]
            if not token_list:
                token_list = list(default_policy["disallowed_placeholder_tokens"])
            return {
                "min_overlap_metrics": max(1, int(gates.get("min_overlap_metrics", default_policy["min_overlap_metrics"]))),
                "disallowed_placeholder_tokens": token_list,
            }
        except Exception:  # noqa: BLE001
            return default_policy

    def attest_from_eval_report(
        self,
        baseline_id: str,
        eval_report: dict[str, Any],
        max_metric_delta: float = 0.02,
    ) -> dict[str, Any]:
        policy = self._load_policy()
        min_overlap_metrics = int(policy["min_overlap_metrics"])
        placeholder_tokens = list(policy["disallowed_placeholder_tokens"])
        registry = self._load_registry()
        baselines = registry.get("baselines", [])
        if not isinstance(baselines, list):
            baselines = []
        index = self._find_index(baselines=baselines, baseline_id=baseline_id)
        if index < 0:
            return {
                "status": "error",
                "reason": f"baseline not found: {baseline_id}",
                "baseline_id": baseline_id,
                "registry_path": str(self.registry_path),
            }

        baseline = dict(baselines[index])
        reasons: list[str] = []
        metric_report: dict[str, dict[str, Any]] = {}
        pass_flag = True

        source_type = str(baseline.get("source_type", "")).lower()
        if not source_type.startswith("external"):
            pass_flag = False
            reasons.append("attestation is only allowed for external baselines")
        source = str(baseline.get("source", ""))
        source_date = str(baseline.get("source_date", ""))
        if self._contains_placeholder_token(source, placeholder_tokens):
            pass_flag = False
            reasons.append("source metadata appears placeholder or unknown")
        if not self._is_iso_date(source_date):
            pass_flag = False
            reasons.append("source_date must be ISO-8601 date (YYYY-MM-DD)")

        progress = eval_report.get("benchmark_progress", {})
        observed = progress.get("observed", {})
        observed_suite = str(progress.get("suite_id", "unknown-suite"))
        observed_scoring = str(eval_report.get("benchmark_provenance", {}).get("scoring_reference", "unknown-scoring"))

        expected_suite = str(baseline.get("suite_id", "unknown-suite"))
        if expected_suite != observed_suite:
            pass_flag = False
            reasons.append("suite mismatch between baseline and eval report")

        expected_scoring = str(baseline.get("scoring_protocol", "unknown-scoring"))
        if expected_scoring != observed_scoring:
            pass_flag = False
            reasons.append("scoring protocol mismatch between baseline and eval report")

        evidence = baseline.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}
        missing_evidence_fields = [
            name
            for name in ("citation", "artifact_hash", "retrieval_date", "verification_method")
            if not str(evidence.get(name, "")).strip()
        ]
        if missing_evidence_fields:
            pass_flag = False
            reasons.append(f"missing evidence fields: {missing_evidence_fields}")
        citation = str(evidence.get("citation", ""))
        verification_method = str(evidence.get("verification_method", ""))
        retrieval_date = str(evidence.get("retrieval_date", ""))
        if citation and self._contains_placeholder_token(citation, placeholder_tokens):
            pass_flag = False
            reasons.append("citation appears placeholder or unknown")
        if verification_method and self._contains_placeholder_token(verification_method, placeholder_tokens):
            pass_flag = False
            reasons.append("verification_method appears placeholder or unknown")
        if retrieval_date and not self._is_iso_date(retrieval_date):
            pass_flag = False
            reasons.append("retrieval_date must be ISO-8601 date (YYYY-MM-DD)")

        baseline_metrics = baseline.get("metrics", {})
        if not isinstance(baseline_metrics, dict) or not baseline_metrics:
            pass_flag = False
            reasons.append("baseline metrics missing")
            baseline_metrics = {}
        if not isinstance(observed, dict):
            pass_flag = False
            reasons.append("eval report observed metrics missing")
            observed = {}

        overlap = sorted(key for key in baseline_metrics if key in observed)
        if not overlap:
            pass_flag = False
            reasons.append("no overlapping metrics between baseline and eval report")
        elif len(overlap) < min_overlap_metrics:
            pass_flag = False
            reasons.append(f"insufficient overlapping metrics: {len(overlap)} < {min_overlap_metrics}")

        for metric in overlap:
            ours = float(observed[metric])
            theirs = float(baseline_metrics[metric])
            abs_delta = abs(ours - theirs)
            metric_pass = abs_delta <= max_metric_delta
            if not metric_pass:
                pass_flag = False
                reasons.append(f"metric delta exceeds threshold for {metric}")
            metric_report[metric] = {
                "observed": ours,
                "baseline": theirs,
                "abs_delta": round(abs_delta, 6),
                "threshold": round(max_metric_delta, 6),
                "pass": metric_pass,
            }

        replication_status = "replicated-internal-harness" if pass_flag else "replication-failed"
        verified_effective = pass_flag
        evidence["replication_status"] = replication_status
        evidence["attestation"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "suite_id": observed_suite,
            "scoring_protocol": observed_scoring,
            "max_metric_delta": round(max_metric_delta, 6),
            "min_overlap_metrics": min_overlap_metrics,
            "metrics_checked": overlap,
            "pass": pass_flag,
            "reasons": reasons,
        }
        baseline["evidence"] = evidence
        baseline["verified"] = verified_effective
        baselines[index] = baseline
        registry["baselines"] = baselines
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=True), encoding="utf-8")

        return {
            "status": "ok",
            "baseline_id": baseline_id,
            "action": "attested" if pass_flag else "rejected",
            "attestation_passed": pass_flag,
            "verified_effective": verified_effective,
            "replication_status": replication_status,
            "max_metric_delta": round(max_metric_delta, 6),
            "min_overlap_metrics": min_overlap_metrics,
            "metric_report": metric_report,
            "reasons": reasons,
            "registry_path": str(self.registry_path),
        }

    def _contains_placeholder_token(self, value: str, tokens: list[str]) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return True
        for token in tokens:
            if token and token in normalized:
                return True
        return False

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

    def _find_index(self, baselines: list[dict[str, Any]], baseline_id: str) -> int:
        for idx, row in enumerate(baselines):
            if str(row.get("baseline_id", "")) == baseline_id:
                return idx
        return -1
