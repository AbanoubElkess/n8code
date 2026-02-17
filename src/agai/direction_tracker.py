from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class DirectionTracker:
    def __init__(self, history_path: str = "artifacts/direction_history.jsonl") -> None:
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, direction_status: dict[str, Any]) -> dict[str, Any]:
        distance = direction_status.get("distance", {})
        direction = direction_status.get("direction", {})
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "internal_remaining_distance": float(distance.get("internal_remaining_distance", 0.0)),
            "external_claim_distance": int(distance.get("external_claim_distance", 0)),
            "public_overclaim_rate_gap": float(distance.get("public_overclaim_rate_gap", 0.0)),
            "combined_average_reality_score": float(direction.get("combined_average_reality_score", 0.0)),
            "internal_ready": bool(direction.get("internal_ready", False)),
            "external_claim_ready": bool(direction.get("external_claim_ready", False)),
            "claim_scope": str(direction.get("claim_scope", "unknown")),
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
                "best_internal_distance": None,
                "best_external_claim_distance": None,
                "best_reality_score": 0.0,
                "internal_distance_trend": 0.0,
                "external_distance_trend": 0.0,
                "reality_score_trend": 0.0,
            }
        latest = rows[-1]
        best_internal_distance = min(float(row.get("internal_remaining_distance", 0.0)) for row in rows)
        best_external_distance = min(int(row.get("external_claim_distance", 0)) for row in rows)
        best_reality_score = max(float(row.get("combined_average_reality_score", 0.0)) for row in rows)
        internal_distance_trend = 0.0
        external_distance_trend = 0.0
        reality_score_trend = 0.0
        if len(rows) >= 2:
            prev = rows[-2]
            internal_distance_trend = float(prev.get("internal_remaining_distance", 0.0)) - float(
                latest.get("internal_remaining_distance", 0.0)
            )
            external_distance_trend = float(prev.get("external_claim_distance", 0.0)) - float(
                latest.get("external_claim_distance", 0.0)
            )
            reality_score_trend = float(latest.get("combined_average_reality_score", 0.0)) - float(
                prev.get("combined_average_reality_score", 0.0)
            )
        return {
            "count": len(rows),
            "latest": latest,
            "best_internal_distance": best_internal_distance,
            "best_external_claim_distance": best_external_distance,
            "best_reality_score": best_reality_score,
            "internal_distance_trend": internal_distance_trend,
            "external_distance_trend": external_distance_trend,
            "reality_score_trend": reality_score_trend,
        }
