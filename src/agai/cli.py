from __future__ import annotations

import argparse
import json
from pathlib import Path

from .architecture_guard import ArchitectureGuard
from .benchmark_tracker import BenchmarkTracker
from .moonshot_tracker import MoonshotTracker
from .runtime import AgenticRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AGAI low-cost multi-agent runtime CLI")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Path for local artifacts")
    parser.add_argument("--use-ollama", action="store_true", help="Use local Ollama endpoint if available")
    parser.add_argument("--ollama-model", default="llama3.2:3b", help="Ollama model name")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("market-report", help="Generate market gap analysis report")

    qdemo = sub.add_parser("quantum-demo", help="Run quantum research demonstration")
    qdemo.add_argument(
        "--question",
        default="Propose a testable strategy to reduce logical error rate under strict laptop compute limits.",
        help="Research question",
    )

    sub.add_parser("quantum-eval", help="Run quantum hard-suite evaluation")
    sub.add_parser("distill", help="Distill trace logs into compact policy artifacts")
    sub.add_parser("validate-architecture", help="Validate implementation against architecture reference")
    sub.add_parser("benchmark-status", help="Show benchmark distance trend from history")
    sub.add_parser("moonshot-status", help="Show moonshot tracking trend (non-gating KPI)")
    sub.add_parser("release-status", help="Show release claim scope status from latest evaluation artifact")
    sub.add_parser("scale-path", help="Run scale-path decision framework and scenario analysis")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    runtime = AgenticRuntime(
        use_ollama=args.use_ollama,
        ollama_model=args.ollama_model,
        artifacts_dir=args.artifacts_dir,
    )

    output: dict[str, object]
    if args.command == "market-report":
        output = runtime.generate_market_gap_report()
    elif args.command == "quantum-demo":
        output = runtime.run_quantum_research_demo(question=args.question)
    elif args.command == "quantum-eval":
        output = runtime.run_quantum_hard_suite()
    elif args.command == "distill":
        output = runtime.run_trace_distillation()
    elif args.command == "validate-architecture":
        output = ArchitectureGuard().validate()
    elif args.command == "benchmark-status":
        output = BenchmarkTracker(history_path=str(Path(args.artifacts_dir) / "benchmark_history.jsonl")).summary()
    elif args.command == "moonshot-status":
        output = MoonshotTracker(history_path=str(Path(args.artifacts_dir) / "moonshot_history.jsonl")).summary()
    elif args.command == "release-status":
        output = runtime.run_release_status()
    elif args.command == "scale-path":
        output = runtime.run_scale_path_decision_framework()
    else:
        parser.error(f"Unsupported command: {args.command}")
        return

    print(json.dumps(output, indent=2, ensure_ascii=True))
    out_file = Path(args.artifacts_dir) / f"last_{args.command}.json"
    out_file.write_text(json.dumps(output, indent=2, ensure_ascii=True), encoding="utf-8")


if __name__ == "__main__":
    main()
