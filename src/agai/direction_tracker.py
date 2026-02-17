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
            "total_claim_distance": int(
                distance.get("total_claim_distance", distance.get("external_claim_distance", 0))
            ),
            "max_total_claim_distance": int(
                distance.get("max_total_claim_distance", distance.get("external_claim_distance", 0))
            ),
            "total_progress_ratio": float(distance.get("total_progress_ratio", 0.0)),
            "projected_total_claim_distance": int(
                distance.get(
                    "projected_total_claim_distance",
                    distance.get("total_claim_distance", distance.get("external_claim_distance", 0)),
                )
            ),
            "projected_total_progress_ratio": float(
                distance.get("projected_total_progress_ratio", distance.get("total_progress_ratio", 0.0))
            ),
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
                "best_total_claim_distance": None,
                "best_reality_score": 0.0,
                "best_total_progress_ratio": 0.0,
                "internal_distance_trend": 0.0,
                "external_distance_trend": 0.0,
                "total_distance_trend": 0.0,
                "reality_score_trend": 0.0,
                "total_progress_ratio_trend": 0.0,
                "projection_delivery_samples": 0,
                "latest_projection_distance_shortfall": 0.0,
                "latest_projection_progress_delivery_ratio": 1.0,
                "mean_projection_distance_shortfall": 0.0,
                "mean_projection_progress_delivery_ratio": 1.0,
            }
        latest = rows[-1]
        best_internal_distance = min(float(row.get("internal_remaining_distance", 0.0)) for row in rows)
        best_external_distance = min(int(row.get("external_claim_distance", 0)) for row in rows)
        best_total_claim_distance = min(
            int(row.get("total_claim_distance", row.get("external_claim_distance", 0))) for row in rows
        )
        best_reality_score = max(float(row.get("combined_average_reality_score", 0.0)) for row in rows)
        best_total_progress_ratio = max(float(row.get("total_progress_ratio", 0.0)) for row in rows)
        internal_distance_trend = 0.0
        external_distance_trend = 0.0
        total_distance_trend = 0.0
        reality_score_trend = 0.0
        total_progress_ratio_trend = 0.0
        projection_shortfalls: list[float] = []
        projection_delivery_ratios: list[float] = []
        for index in range(1, len(rows)):
            prev_row = rows[index - 1]
            curr_row = rows[index]
            prev_total = float(prev_row.get("total_claim_distance", prev_row.get("external_claim_distance", 0.0)))
            projected_total = float(prev_row.get("projected_total_claim_distance", prev_total))
            curr_total = float(curr_row.get("total_claim_distance", curr_row.get("external_claim_distance", 0.0)))
            projected_reduction = prev_total - projected_total
            actual_reduction = prev_total - curr_total
            shortfall = curr_total - projected_total
            if projected_reduction > 1e-9:
                delivery_ratio = actual_reduction / projected_reduction
            else:
                delivery_ratio = 1.0 if actual_reduction >= -1e-9 else 0.0
            projection_shortfalls.append(shortfall)
            projection_delivery_ratios.append(delivery_ratio)
        if len(rows) >= 2:
            prev = rows[-2]
            internal_distance_trend = float(prev.get("internal_remaining_distance", 0.0)) - float(
                latest.get("internal_remaining_distance", 0.0)
            )
            external_distance_trend = float(prev.get("external_claim_distance", 0.0)) - float(
                latest.get("external_claim_distance", 0.0)
            )
            total_distance_trend = float(
                prev.get("total_claim_distance", prev.get("external_claim_distance", 0.0))
            ) - float(latest.get("total_claim_distance", latest.get("external_claim_distance", 0.0)))
            reality_score_trend = float(latest.get("combined_average_reality_score", 0.0)) - float(
                prev.get("combined_average_reality_score", 0.0)
            )
            total_progress_ratio_trend = float(latest.get("total_progress_ratio", 0.0)) - float(
                prev.get("total_progress_ratio", 0.0)
            )
        latest_projection_distance_shortfall = projection_shortfalls[-1] if projection_shortfalls else 0.0
        latest_projection_progress_delivery_ratio = projection_delivery_ratios[-1] if projection_delivery_ratios else 1.0
        mean_projection_distance_shortfall = (
            sum(projection_shortfalls) / len(projection_shortfalls) if projection_shortfalls else 0.0
        )
        mean_projection_progress_delivery_ratio = (
            sum(projection_delivery_ratios) / len(projection_delivery_ratios)
            if projection_delivery_ratios
            else 1.0
        )
        return {
            "count": len(rows),
            "latest": latest,
            "best_internal_distance": best_internal_distance,
            "best_external_claim_distance": best_external_distance,
            "best_total_claim_distance": best_total_claim_distance,
            "best_reality_score": best_reality_score,
            "best_total_progress_ratio": best_total_progress_ratio,
            "internal_distance_trend": internal_distance_trend,
            "external_distance_trend": external_distance_trend,
            "total_distance_trend": total_distance_trend,
            "reality_score_trend": reality_score_trend,
            "total_progress_ratio_trend": total_progress_ratio_trend,
            "projection_delivery_samples": len(projection_delivery_ratios),
            "latest_projection_distance_shortfall": latest_projection_distance_shortfall,
            "latest_projection_progress_delivery_ratio": latest_projection_progress_delivery_ratio,
            "mean_projection_distance_shortfall": mean_projection_distance_shortfall,
            "mean_projection_progress_delivery_ratio": mean_projection_progress_delivery_ratio,
        }
