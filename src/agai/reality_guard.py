from __future__ import annotations

import re
from typing import Any


class RealityGuard:
    _TOKEN_RE = re.compile(r"[a-zA-Z0-9%+-]+")
    _OVERCLAIM_TERMS = {
        "guarantee",
        "guaranteed",
        "always",
        "never",
        "perfect",
        "infinite",
        "certain",
        "certainty",
        "proof",
        "prove",
        "proves",
        "sota",
        "state-of-the-art",
        "frontier",
        "best",
        "impossible",
        "unbeatable",
    }
    _CALIBRATION_TERMS = {
        "estimate",
        "proxy",
        "confidence",
        "uncertainty",
        "ablation",
        "falsification",
        "baseline",
        "tradeoff",
        "trade",
        "constraint",
        "bounded",
        "simulate",
        "simulator",
        "risk",
        "variance",
    }

    def _tokenize(self, text: str) -> list[str]:
        return [token.lower() for token in self._TOKEN_RE.findall(text)]

    def audit_text(self, text: str) -> dict[str, Any]:
        tokens = self._tokenize(text)
        overclaim_tokens = [token for token in tokens if token in self._OVERCLAIM_TERMS]
        calibration_tokens = [token for token in tokens if token in self._CALIBRATION_TERMS]
        overclaim_hits = len(overclaim_tokens)
        calibration_hits = len(calibration_tokens)
        score = max(0.0, min(1.0, 0.75 + (0.03 * calibration_hits) - (0.10 * overclaim_hits)))
        if overclaim_hits == 0:
            risk = "low"
        elif overclaim_hits <= 2:
            risk = "medium"
        else:
            risk = "high"
        return {
            "overclaim_hits": overclaim_hits,
            "overclaim_terms": sorted(set(overclaim_tokens)),
            "calibration_hits": calibration_hits,
            "calibration_terms": sorted(set(calibration_tokens)),
            "reality_score": score,
            "risk_level": risk,
        }

    def maturity_band(self, feasibility: float, accessibility: float) -> str:
        if feasibility >= 0.80 and accessibility >= 0.85:
            return "deployable"
        if feasibility >= 0.65:
            return "prototype"
        return "exploratory"

    def audit_market_opportunities(self, opportunities: list[dict[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        risk_counts = {"low": 0, "medium": 0, "high": 0}
        for row in opportunities:
            payload = " ".join(
                [
                    str(row.get("description", "")),
                    str(row.get("why_now", "")),
                    str(row.get("first_experiment", "")),
                ]
            )
            audit = self.audit_text(payload)
            risk = str(audit.get("risk_level", "low"))
            if risk in risk_counts:
                risk_counts[risk] += 1
            rows.append(
                {
                    "key": row.get("key", ""),
                    "risk_level": risk,
                    "overclaim_hits": int(audit.get("overclaim_hits", 0)),
                    "reality_score": float(audit.get("reality_score", 0.0)),
                }
            )
        return {
            "risk_counts": risk_counts,
            "rows": rows,
            "average_reality_score": (
                sum(float(item["reality_score"]) for item in rows) / len(rows)
                if rows
                else 0.0
            ),
        }

