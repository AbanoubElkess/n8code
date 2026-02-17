from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any


class DeclaredBaselineComparator:
    def __init__(self, registry_path: str = "config/frontier_baselines.json") -> None:
        self.registry_path = Path(registry_path)
        self._metric_specs: dict[str, bool] = {
            "quality": True,
            "aggregate_delta": True,
            "holdout_quality": True,
            "adversarial_quality": True,
            "public_overclaim_rate": False,
        }

    def compare(self, eval_report: dict[str, Any]) -> dict[str, Any]:
        registry = self._load_registry()
        observed = eval_report.get("benchmark_progress", {}).get("observed", {})
        suite_id = str(eval_report.get("benchmark_progress", {}).get("suite_id", "unknown-suite"))
        scoring_reference = str(eval_report.get("benchmark_provenance", {}).get("scoring_reference", "unknown-scoring"))

        baselines = registry.get("baselines", [])
        if not isinstance(baselines, list) or not baselines:
            return {
                "status": "no_baselines_configured",
                "suite_id": suite_id,
                "registry_path": str(self.registry_path),
                "registry_version": str(registry.get("registry_version", "unknown")),
                "comparisons": [],
                "summary": {
                    "total_baselines": 0,
                    "comparable_baselines": 0,
                    "comparable_external_baselines": 0,
                    "comparable_internal_baselines": 0,
                    "non_comparable_baselines": 0,
                    "best_mean_advantage": 0.0,
                },
            }

        comparisons = [
            self._compare_baseline(
                baseline=entry,
                observed=observed,
                suite_id=suite_id,
                scoring_reference=scoring_reference,
            )
            for entry in baselines
        ]
        comparable = [row for row in comparisons if bool(row["comparability"]["comparable"])]
        comparable_external = [row for row in comparable if str(row.get("source_type", "")).lower().startswith("external")]
        comparable_internal = [row for row in comparable if str(row.get("source_type", "")).lower().startswith("internal")]
        best_mean_advantage = max((float(row["mean_advantage"]) for row in comparable), default=0.0)
        return {
            "status": "ok",
            "suite_id": suite_id,
            "registry_path": str(self.registry_path),
            "registry_version": str(registry.get("registry_version", "unknown")),
            "comparisons": comparisons,
            "summary": {
                "total_baselines": len(comparisons),
                "comparable_baselines": len(comparable),
                "comparable_external_baselines": len(comparable_external),
                "comparable_internal_baselines": len(comparable_internal),
                "non_comparable_baselines": len(comparisons) - len(comparable),
                "best_mean_advantage": round(best_mean_advantage, 6),
            },
            "disclaimer": (
                "Declared baseline comparisons are only actionable when comparability.comparable=true. "
                "Do not present non-comparable rows as wins."
            ),
        }

    def _load_registry(self) -> dict[str, Any]:
        default_payload: dict[str, Any] = {"registry_version": "none", "baselines": []}
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

    def _compare_baseline(
        self,
        baseline: dict[str, Any],
        observed: dict[str, Any],
        suite_id: str,
        scoring_reference: str,
    ) -> dict[str, Any]:
        baseline_id = str(baseline.get("baseline_id", "unknown-baseline"))
        expected_suite = str(baseline.get("suite_id", "unknown-suite"))
        expected_scoring = str(baseline.get("scoring_protocol", "unknown-scoring"))
        verified = bool(baseline.get("verified", False))
        enabled = bool(baseline.get("enabled", True))
        source_type = str(baseline.get("source_type", "unknown"))
        evidence = baseline.get("evidence", {})
        baseline_metrics = baseline.get("metrics", {})

        reasons: list[str] = []
        comparable = True
        evidence_status = self._evaluate_evidence(
            evidence=evidence,
            source_type=source_type,
            verified=verified,
        )

        if not enabled:
            comparable = False
            reasons.append("baseline disabled")
        if not verified:
            comparable = False
            reasons.append("baseline unverified")
        if not evidence_status["evidence_valid"]:
            comparable = False
            reasons.extend(evidence_status["reasons"])
        if expected_suite != suite_id:
            comparable = False
            reasons.append("suite mismatch")
        if expected_scoring != scoring_reference:
            comparable = False
            reasons.append("scoring protocol mismatch")
        if not isinstance(baseline_metrics, dict) or not baseline_metrics:
            comparable = False
            reasons.append("missing metric payload")

        metric_comparison: dict[str, dict[str, Any]] = {}
        wins = 0
        losses = 0
        ties = 0
        advantages: list[float] = []

        if isinstance(baseline_metrics, dict):
            for metric, higher_is_better in self._metric_specs.items():
                if metric not in baseline_metrics or metric not in observed:
                    continue
                ours = float(observed[metric])
                theirs = float(baseline_metrics[metric])
                raw_delta = ours - theirs
                advantage = raw_delta if higher_is_better else -raw_delta
                outcome = "tie"
                if advantage > 1e-9:
                    wins += 1
                    outcome = "win"
                elif advantage < -1e-9:
                    losses += 1
                    outcome = "loss"
                else:
                    ties += 1
                metric_comparison[metric] = {
                    "ours": ours,
                    "baseline": theirs,
                    "raw_delta": round(raw_delta, 6),
                    "advantage": round(advantage, 6),
                    "higher_is_better": higher_is_better,
                    "outcome": outcome,
                }
                advantages.append(advantage)

        if not metric_comparison:
            comparable = False
            reasons.append("no overlapping metrics")

        mean_advantage = mean(advantages) if advantages else 0.0
        comparability = {
            "comparable": comparable,
            "reasons": reasons,
        }
        return {
            "baseline_id": baseline_id,
            "label": str(baseline.get("label", baseline_id)),
            "source_type": source_type,
            "source": str(baseline.get("source", "unknown")),
            "source_date": str(baseline.get("source_date", "unknown")),
            "suite_id": expected_suite,
            "scoring_protocol": expected_scoring,
            "comparability": comparability,
            "verification": evidence_status,
            "metric_comparison": metric_comparison,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "mean_advantage": round(mean_advantage, 6),
            "notes": str(baseline.get("notes", "")),
        }

    def _evaluate_evidence(self, evidence: Any, source_type: str, verified: bool) -> dict[str, Any]:
        required_fields = [
            "citation",
            "artifact_hash",
            "retrieval_date",
            "verification_method",
        ]
        reasons: list[str] = []
        evidence_valid = True
        evidence_payload: dict[str, Any] = evidence if isinstance(evidence, dict) else {}
        missing = [field for field in required_fields if not evidence_payload.get(field)]
        if missing:
            evidence_valid = False
            reasons.append(f"missing verification evidence fields: {missing}")

        replication_status = str(evidence_payload.get("replication_status", "unspecified"))
        source_key = source_type.lower()
        external_source = source_key.startswith("external")
        if verified and external_source and replication_status != "replicated-internal-harness":
            evidence_valid = False
            reasons.append("external baseline missing replicated-internal-harness status")

        return {
            "verified_flag": verified,
            "evidence_valid": evidence_valid,
            "missing_fields": missing,
            "replication_status": replication_status,
            "reasons": reasons,
        }
