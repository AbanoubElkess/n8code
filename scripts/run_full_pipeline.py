#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agai.runtime import AgenticRuntime


def main() -> int:
    runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(ROOT / "artifacts"))
    market = runtime.generate_market_gap_report()
    demo = runtime.run_quantum_research_demo(
        "Develop a falsifiable path to improve logical error rate under strict laptop budget."
    )
    evaluation = runtime.run_quantum_hard_suite()
    distilled = runtime.run_trace_distillation()
    summary = {
        "market_top_opportunity": market["opportunities"][0]["key"],
        "quantum_final_answer_preview": str(demo["result"]["outcomes"]["final_answer"])[:180],
        "aggregate_delta": evaluation["aggregate_delta"],
        "distilled_policy_count": len(distilled["policies"]),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

