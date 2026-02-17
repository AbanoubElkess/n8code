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
    sub.add_parser("direction-status", help="Show benchmark, claim-distance, and naming-risk direction telemetry")
    sub.add_parser("external-claim-plan", help="Generate actionable remediation plan for external-claim distance")
    replay = sub.add_parser(
        "external-claim-replay",
        help="Run attestation replay for auto-fixable external-claim rows and report distance deltas",
    )
    replay.add_argument(
        "--registry-path",
        default="config/frontier_baselines.json",
        help="Path to baseline registry json",
    )
    replay.add_argument("--max-metric-delta", type=float, default=0.02, help="Maximum allowed absolute metric delta")
    replay.add_argument("--eval-path", default="", help="Optional path to evaluation artifact json")
    replay.add_argument("--dry-run", action="store_true", help="Preview replay candidates without mutating registry")
    normalize = sub.add_parser(
        "normalize-external-baseline",
        help="Apply explicit metadata patch to an external baseline and optionally align harness ids to eval",
    )
    normalize.add_argument("--baseline-id", required=True, help="Baseline ID in registry")
    normalize.add_argument("--input", required=True, help="Path to normalization patch json")
    normalize.add_argument("--registry-path", default="config/frontier_baselines.json", help="Path to baseline registry json")
    normalize.add_argument("--eval-path", default="", help="Optional path to evaluation artifact json")
    normalize.add_argument("--align-to-eval", action="store_true", help="Align suite_id/scoring_protocol to eval artifact")
    normalize.add_argument("--replace-metrics", action="store_true", help="Replace baseline metrics with patch.metrics")
    ingest = sub.add_parser("ingest-external-baseline", help="Validate and ingest external baseline evidence payload")
    ingest.add_argument("--input", required=True, help="Path to ingestion payload json")
    ingest.add_argument("--registry-path", default="config/frontier_baselines.json", help="Path to baseline registry json")
    attest = sub.add_parser("attest-external-baseline", help="Replay-check external baseline against eval artifact")
    attest.add_argument("--baseline-id", required=True, help="Baseline ID in registry")
    attest.add_argument("--registry-path", default="config/frontier_baselines.json", help="Path to baseline registry json")
    attest.add_argument("--max-metric-delta", type=float, default=0.02, help="Maximum allowed absolute metric delta")
    attest.add_argument("--eval-path", default="", help="Optional path to evaluation artifact json")
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
    elif args.command == "direction-status":
        output = runtime.run_direction_status()
    elif args.command == "external-claim-plan":
        output = runtime.run_external_claim_plan()
    elif args.command == "external-claim-replay":
        output = runtime.run_external_claim_replay(
            registry_path=str(args.registry_path),
            max_metric_delta=float(args.max_metric_delta),
            eval_path=str(args.eval_path or "") or None,
            dry_run=bool(args.dry_run),
        )
    elif args.command == "normalize-external-baseline":
        output = runtime.run_normalize_external_baseline(
            baseline_id=str(args.baseline_id),
            input_path=str(args.input),
            registry_path=str(args.registry_path),
            eval_path=str(args.eval_path or "") or None,
            align_to_eval=bool(args.align_to_eval),
            replace_metrics=bool(args.replace_metrics),
        )
    elif args.command == "ingest-external-baseline":
        output = runtime.run_ingest_external_baseline(input_path=args.input, registry_path=args.registry_path)
    elif args.command == "attest-external-baseline":
        output = runtime.run_attest_external_baseline(
            baseline_id=args.baseline_id,
            registry_path=args.registry_path,
            max_metric_delta=float(args.max_metric_delta),
            eval_path=str(args.eval_path or "") or None,
        )
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
