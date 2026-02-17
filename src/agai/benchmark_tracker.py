from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class BenchmarkTracker:
    def __init__(self, history_path: str = "artifacts/benchmark_history.jsonl") -> None:
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, eval_report: dict[str, Any]) -> dict[str, Any]:
        progress = eval_report.get("benchmark_progress", {})
        observed = progress.get("observed", {})
        gaps = progress.get("gaps", {})
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "quality": float(observed.get("quality", 0.0)),
            "pass_rate": float(observed.get("pass_rate", 0.0)),
            "aggregate_delta": float(observed.get("aggregate_delta", 0.0)),
            "remaining_distance": float(gaps.get("remaining_distance", 0.0)),
            "ready": bool(progress.get("ready", False)),
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
        rows = self.load()
        if not rows:
            return {
                "count": 0,
                "latest": {},
                "best_quality": 0.0,
                "best_distance": None,
                "distance_trend": 0.0,
            }
        latest = rows[-1]
        best_quality = max(float(row.get("quality", 0.0)) for row in rows)
        best_distance = min(float(row.get("remaining_distance", 0.0)) for row in rows)
        distance_trend = 0.0
        if len(rows) >= 2:
            distance_trend = float(rows[-2].get("remaining_distance", 0.0)) - float(rows[-1].get("remaining_distance", 0.0))
        return {
            "count": len(rows),
            "latest": latest,
            "best_quality": best_quality,
            "best_distance": best_distance,
            "distance_trend": distance_trend,
        }

