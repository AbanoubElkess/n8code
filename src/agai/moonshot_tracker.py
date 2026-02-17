from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class MoonshotTracker:
    def __init__(
        self,
        history_path: str = "artifacts/moonshot_history.jsonl",
        policy_path: str = "config/repro_policy.json",
    ) -> None:
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path = Path(policy_path)

    def _load_policy(self) -> dict[str, Any]:
        default_policy: dict[str, Any] = {
            "moonshot_general_benchmarks_gate": False,
        }
        if not self.policy_path.exists():
            return default_policy
        try:
            payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
            release_gates = payload.get("release_gates", {})
            return {
                "moonshot_general_benchmarks_gate": bool(release_gates.get("moonshot_general_benchmarks_gate", False)),
            }
        except Exception:  # noqa: BLE001
            return default_policy

    def _extract_signal(self, eval_report: dict[str, Any]) -> dict[str, float | int]:
        comparison = eval_report.get("declared_baseline_comparison", {})
        rows = comparison.get("comparisons", [])
        if not isinstance(rows, list):
            rows = []
        comparable = [row for row in rows if bool(row.get("comparability", {}).get("comparable", False))]
        comparable_external = [
            row
            for row in comparable
            if str(row.get("source_type", "")).lower().startswith("external")
        ]
        comparable_internal = [
            row
            for row in comparable
            if str(row.get("source_type", "")).lower().startswith("internal")
        ]
        advantages = [float(row.get("mean_advantage", 0.0)) for row in comparable]
        best_advantage = max(advantages) if advantages else 0.0
        mean_advantage = (sum(advantages) / len(advantages)) if advantages else 0.0
        confidence = min(1.0, len(comparable_external) * 0.45 + len(comparable_internal) * 0.20)
        return {
            "comparable_total": len(comparable),
            "comparable_external": len(comparable_external),
            "comparable_internal": len(comparable_internal),
            "best_mean_advantage": best_advantage,
            "mean_mean_advantage": mean_advantage,
            "signal_confidence": confidence,
        }

    def record(self, eval_report: dict[str, Any]) -> dict[str, Any]:
        policy = self._load_policy()
        progress = eval_report.get("benchmark_progress", {})
        observed = progress.get("observed", {})
        gaps = progress.get("gaps", {})
        signal = self._extract_signal(eval_report)
        gate_enabled = bool(policy["moonshot_general_benchmarks_gate"])
        status = "gating-enabled" if gate_enabled else "tracking-only"
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "suite_id": str(progress.get("suite_id", "unknown-suite")),
            "release_gate_enabled": gate_enabled,
            "release_gate_effect": status,
            "internal_quality": float(observed.get("quality", 0.0)),
            "internal_remaining_distance": float(gaps.get("remaining_distance", 0.0)),
            "comparable_declared_baselines": int(signal["comparable_total"]),
            "comparable_external_baselines": int(signal["comparable_external"]),
            "comparable_internal_baselines": int(signal["comparable_internal"]),
            "best_mean_advantage": round(float(signal["best_mean_advantage"]), 6),
            "mean_mean_advantage": round(float(signal["mean_mean_advantage"]), 6),
            "signal_confidence": round(float(signal["signal_confidence"]), 6),
            "status": status,
        }
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=True) + "\n")
        return snapshot

    def load(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.history_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def summary(self) -> dict[str, Any]:
        policy = self._load_policy()
        gate_enabled = bool(policy["moonshot_general_benchmarks_gate"])
        status = "gating-enabled" if gate_enabled else "tracking-only"
        rows = self.load()
        if not rows:
            return {
                "count": 0,
                "latest": {},
                "best_signal": 0.0,
                "signal_trend": 0.0,
                "release_gate_enabled": gate_enabled,
                "status": status,
            }
        latest = rows[-1]
        best_signal = max(float(row.get("best_mean_advantage", 0.0)) for row in rows)
        signal_trend = 0.0
        if len(rows) >= 2:
            signal_trend = float(rows[-1].get("best_mean_advantage", 0.0)) - float(rows[-2].get("best_mean_advantage", 0.0))
        return {
            "count": len(rows),
            "latest": latest,
            "best_signal": best_signal,
            "signal_trend": signal_trend,
            "release_gate_enabled": gate_enabled,
            "status": status,
        }
