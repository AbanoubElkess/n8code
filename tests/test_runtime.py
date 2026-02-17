from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.runtime import AgenticRuntime


class TestRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_market_and_quantum_paths(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        market = runtime.generate_market_gap_report()
        self.assertIn("opportunities", market)

        demo = runtime.run_quantum_research_demo(
            "Propose a falsifiable strategy to reduce logical error rate under tight compute."
        )
        self.assertIn("result", demo)
        self.assertIn("claim_calibration", demo)
        self.assertIn("tool_reasoning", demo)
        self.assertIn("hypothesis_sandbox", demo)
        self.assertIn("acceptance_rate", demo["hypothesis_sandbox"])
        self.assertIn("researcher_guidance", demo)
        self.assertIn("execution_dag", demo["researcher_guidance"])
        self.assertIn("execution_validation", demo["researcher_guidance"])
        self.assertTrue(demo["researcher_guidance"]["execution_validation"]["ok"])
        self.assertIn("qec_simulator_hook", demo["tool_reasoning"])
        qec_tool = demo["tool_reasoning"]["qec_simulator_hook"]
        self.assertTrue(qec_tool["ok"])
        self.assertIn("status", qec_tool["output"])
        self.assertIn("consistency", qec_tool["output"])
        self.assertIn("final_answer", demo["claim_calibration"])
        self.assertIn("revised_answer", demo["claim_calibration"])
        self.assertIn("reality_score_delta", demo["claim_calibration"])
        self.assertIn("direction", demo["claim_calibration"])
        self.assertTrue((self.temp_dir / "quantum_demo_output.json").exists())

        eval_report = runtime.run_quantum_hard_suite()
        self.assertIn("scorecard", eval_report)
        self.assertIn("holdout_scorecard", eval_report)
        self.assertIn("adversarial_scorecard", eval_report)
        self.assertIn("benchmark_provenance", eval_report)
        self.assertFalse(eval_report["benchmark_provenance"]["external_sota_comparable"])
        self.assertIn("disclaimer", eval_report["benchmark_provenance"])
        self.assertIn("suite_id", eval_report["benchmark_provenance"])
        self.assertIn("specialist_reference", eval_report)
        self.assertIn("public", eval_report["specialist_reference"])
        self.assertIn("holdout", eval_report["specialist_reference"])
        self.assertIn("adversarial", eval_report["specialist_reference"])
        self.assertIn("benchmark_progress", eval_report)
        self.assertIn("suite_id", eval_report["benchmark_progress"])
        self.assertIn("remaining_distance", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("case_margin_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("adversarial_quality_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("adversarial_split_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("public_holdout_overlap_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("public_adversarial_overlap_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_public_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_holdout_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_adversarial_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn(
            "min_specialist_adversarial_aggregate_delta",
            eval_report["benchmark_progress"]["targets"],
        )
        self.assertIn("max_public_adversarial_overlap", eval_report["benchmark_progress"]["targets"])
        self.assertIn("suite_leakage", eval_report["benchmark_progress"]["observed"])
        self.assertIn("benchmark_tracking", eval_report)
        self.assertIn("summary", eval_report["benchmark_tracking"])
        self.assertTrue((self.temp_dir / "benchmark_history.jsonl").exists())
        self.assertIn("moonshot_tracking", eval_report)
        self.assertIn("snapshot", eval_report["moonshot_tracking"])
        self.assertIn("summary", eval_report["moonshot_tracking"])
        self.assertFalse(eval_report["moonshot_tracking"]["summary"]["release_gate_enabled"])
        self.assertTrue((self.temp_dir / "moonshot_history.jsonl").exists())
        ingest_input = self.temp_dir / "external_ingest_payload.json"
        ingest_input.write_text(
            '{'
            '"baseline_id":"external-runtime-ingest",'
            '"label":"External Runtime Ingest",'
            '"source_type":"external_reported",'
            '"source":"runtime-test",'
            '"source_date":"2026-02-17",'
            '"verified":true,'
            '"enabled":true,'
            '"suite_id":"quantum_hard_suite_v2_adversarial",'
            '"scoring_protocol":"src/agai/quantum_suite.py:263",'
            '"evidence":{'
            '"citation":"runtime-test-citation",'
            '"retrieval_date":"2026-02-17",'
            '"verification_method":"runtime-manual",'
            '"replication_status":"pending"'
            '},'
            '"metrics":{"quality":0.9,"aggregate_delta":0.48}'
            '}',
            encoding="utf-8",
        )
        ingest_registry = self.temp_dir / "frontier_baselines.json"
        ingest_result = runtime.run_ingest_external_baseline(
            input_path=str(ingest_input),
            registry_path=str(ingest_registry),
        )
        self.assertEqual(ingest_result["status"], "ok")
        self.assertFalse(ingest_result["verified_effective"])
        self.assertTrue((self.temp_dir / "baseline_ingest_result.json").exists())
        self.assertTrue(ingest_registry.exists())
        attest_result = runtime.run_attest_external_baseline(
            baseline_id="external-runtime-ingest",
            registry_path=str(ingest_registry),
            max_metric_delta=0.05,
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
        )
        self.assertEqual(attest_result["status"], "ok")
        self.assertTrue(attest_result["attestation_passed"])
        self.assertTrue(attest_result["verified_effective"])
        self.assertTrue((self.temp_dir / "baseline_attest_result.json").exists())
        release_status = runtime.run_release_status()
        self.assertIn("release_ready_internal", release_status)
        self.assertIn("external_claim_ready", release_status)
        self.assertIn("claim_scope", release_status)
        self.assertIn("gates", release_status)
        self.assertEqual(release_status["claim_scope"], "internal-comparative-only")
        self.assertIn("external_claim_gate", release_status["gates"])
        external_gate = release_status["gates"]["external_claim_gate"]
        self.assertIn("required_external_baselines", external_gate)
        self.assertIn("external_claim_distance", external_gate)
        self.assertIn("non_comparable_external_baselines", external_gate)
        self.assertIn("blockers", external_gate)
        self.assertIn("claim_calibration_pass", external_gate)
        self.assertIn("reality_score_gap", external_gate)
        self.assertIn("public_overclaim_rate_gap", external_gate)
        self.assertIn("external_claim_calibration_gate", release_status["gates"])
        calibration_gate = release_status["gates"]["external_claim_calibration_gate"]
        self.assertIn("combined_average_reality_score", calibration_gate)
        self.assertIn("public_overclaim_rate", calibration_gate)
        self.assertGreaterEqual(external_gate["required_external_baselines"], 1)
        self.assertGreaterEqual(external_gate["external_claim_distance"], 0)
        self.assertTrue((self.temp_dir / "release_status.json").exists())
        self.assertIn("failure_analysis", eval_report)
        self.assertIn("claim_calibration", eval_report)
        self.assertIn("combined_average_reality_score", eval_report["claim_calibration"])
        self.assertIn("combined_top_overclaim_terms", eval_report["claim_calibration"])
        self.assertIn("declared_baseline_comparison", eval_report)
        self.assertIn("summary", eval_report["declared_baseline_comparison"])
        self.assertGreaterEqual(eval_report["declared_baseline_comparison"]["summary"]["total_baselines"], 1)
        self.assertIn("combined", eval_report["failure_analysis"])
        self.assertIn("public_overclaim_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("max_public_overclaim_rate", eval_report["benchmark_progress"]["targets"])
        direction_status = runtime.run_direction_status()
        self.assertIn("distance", direction_status)
        self.assertIn("internal_remaining_distance", direction_status["distance"])
        self.assertIn("external_claim_distance", direction_status["distance"])
        self.assertIn("total_claim_distance", direction_status["distance"])
        self.assertIn("max_total_claim_distance", direction_status["distance"])
        self.assertIn("total_progress_ratio", direction_status["distance"])
        self.assertIn("projected_total_claim_distance", direction_status["distance"])
        self.assertIn("projected_total_progress_ratio", direction_status["distance"])
        self.assertIn("projected_total_claim_distance_reduction", direction_status["distance"])
        self.assertIn("projected_total_progress_ratio_gain", direction_status["distance"])
        self.assertIn("direction", direction_status)
        self.assertIn("claim_scope", direction_status["direction"])
        self.assertIn("gates", direction_status)
        self.assertIn("naming_reality_gate", direction_status["gates"])
        self.assertIn("projection_realism_gate", direction_status["gates"])
        self.assertTrue(direction_status["gates"]["projection_realism_gate"]["pass"])
        self.assertFalse(direction_status["gates"]["projection_realism_gate"]["evaluated"])
        self.assertIn("policy", direction_status)
        self.assertIn("direction_gates", direction_status["policy"])
        self.assertIn("max_projection_distance_shortfall", direction_status["policy"]["direction_gates"])
        self.assertIn("min_projection_progress_delivery_ratio", direction_status["policy"]["direction_gates"])
        self.assertIn("tracking", direction_status)
        self.assertIn("snapshot", direction_status["tracking"])
        self.assertIn("summary", direction_status["tracking"])
        self.assertGreaterEqual(direction_status["tracking"]["summary"]["count"], 1)
        self.assertIn("best_total_claim_distance", direction_status["tracking"]["summary"])
        self.assertIn("best_total_progress_ratio", direction_status["tracking"]["summary"])
        self.assertIn("total_distance_trend", direction_status["tracking"]["summary"])
        self.assertIn("total_progress_ratio_trend", direction_status["tracking"]["summary"])
        self.assertIn("projection_transition_samples", direction_status["tracking"]["summary"])
        self.assertIn("projection_delivery_samples", direction_status["tracking"]["summary"])
        self.assertIn("projection_pending_samples", direction_status["tracking"]["summary"])
        direction_status_second = runtime.run_direction_status()
        projection_gate_second = direction_status_second["gates"]["projection_realism_gate"]
        self.assertFalse(projection_gate_second["pass"])
        self.assertFalse(projection_gate_second["evaluated"])
        self.assertIn("projection delivery pending", projection_gate_second["reason"])
        self.assertGreaterEqual(projection_gate_second["projection_transition_samples"], 1)
        self.assertEqual(projection_gate_second["projection_delivery_samples"], 0)
        self.assertGreaterEqual(projection_gate_second["projection_pending_samples"], 1)
        self.assertIn("external_claim_plan", direction_status)
        self.assertIn("estimated_distance_after_recoverable_actions", direction_status["external_claim_plan"])
        self.assertIn("estimated_total_distance_after_recoverable_actions", direction_status["external_claim_plan"])
        self.assertIn("claim_calibration_distance", direction_status["external_claim_plan"])
        self.assertIn("claim_calibration_gate_pass", direction_status["external_claim_plan"])
        self.assertIn("distance_progress", direction_status["external_claim_plan"])
        self.assertIn("top_priority_actions", direction_status["external_claim_plan"])
        self.assertIn("next_priority", direction_status)
        self.assertTrue((self.temp_dir / "direction_status.json").exists())
        self.assertTrue((self.temp_dir / "direction_history.jsonl").exists())
        claim_plan = runtime.run_external_claim_plan()
        self.assertIn("external_claim_distance", claim_plan)
        self.assertIn("additional_baselines_needed", claim_plan)
        self.assertIn("distance_progress", claim_plan)
        self.assertIn("priority_actions", claim_plan)
        self.assertIn("sources", claim_plan)
        self.assertTrue((self.temp_dir / "external_claim_plan.json").exists())
        claim_replay = runtime.run_external_claim_replay(
            registry_path=str(ingest_registry),
            max_metric_delta=0.05,
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
            dry_run=True,
        )
        self.assertEqual(claim_replay["status"], "ok")
        self.assertTrue(claim_replay["dry_run"])
        self.assertIn("before", claim_replay)
        self.assertIn("after", claim_replay)
        self.assertIn("delta", claim_replay)
        self.assertIn("total_claim_distance", claim_replay["before"])
        self.assertIn("total_claim_distance", claim_replay["after"])
        self.assertIn("total_claim_distance_reduction", claim_replay["delta"])
        self.assertIn("total_progress_ratio_gain", claim_replay["delta"])
        self.assertIn("replay_summary", claim_replay)
        self.assertIn("skipped_manual_rows", claim_replay)
        self.assertIn("distance_progress", claim_replay["before_external_claim_plan"])
        self.assertIn("distance_progress", claim_replay["after_external_claim_plan"])
        self.assertTrue((self.temp_dir / "external_claim_replay.json").exists())
        normalize_input = self.temp_dir / "baseline_normalize_patch.json"
        normalize_input.write_text(
            '{'
            '"notes":"normalized during runtime test",'
            '"evidence":{"verification_method":"runtime-normalized-check"}'
            '}',
            encoding="utf-8",
        )
        normalize_result = runtime.run_normalize_external_baseline(
            baseline_id="external-runtime-ingest",
            input_path=str(normalize_input),
            registry_path=str(ingest_registry),
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
            align_to_eval=True,
            replace_metrics=False,
        )
        self.assertEqual(normalize_result["status"], "ok")
        self.assertTrue(normalize_result["normalize_applied"])
        self.assertIn("changed_fields", normalize_result)
        self.assertIn("sources", normalize_result)
        self.assertTrue((self.temp_dir / "baseline_normalize_result.json").exists())
        draft_result = runtime.run_draft_external_normalization_patch(
            baseline_id="external-runtime-ingest",
            registry_path=str(ingest_registry),
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
        )
        self.assertEqual(draft_result["status"], "ok")
        self.assertIn("patch_template", draft_result)
        self.assertIn("output_path", draft_result)
        self.assertTrue(Path(draft_result["output_path"]).exists())
        sandbox_result = runtime.run_external_claim_sandbox_pipeline(
            baseline_id="external-runtime-ingest",
            registry_path=str(ingest_registry),
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
            dry_run=True,
        )
        self.assertEqual(sandbox_result["status"], "dry-run")
        self.assertTrue(sandbox_result["source_registry_unchanged"])
        self.assertIn("before", sandbox_result)
        self.assertIn("after", sandbox_result)
        self.assertIn("template", sandbox_result)
        self.assertTrue((self.temp_dir / "external_claim_sandbox_pipeline.json").exists())
        campaign_config = self.temp_dir / "external_campaign_config.json"
        campaign_config.write_text(
            '{'
            '"baseline_runs":[{'
            '"baseline_id":"external-runtime-ingest",'
            '"dry_run":true'
            '}]}',
            encoding="utf-8",
        )
        campaign_result = runtime.run_external_claim_sandbox_campaign(
            config_path=str(campaign_config),
            registry_path=str(ingest_registry),
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
            default_max_metric_delta=0.05,
        )
        self.assertIn("status", campaign_result)
        self.assertIn("before", campaign_result)
        self.assertIn("after", campaign_result)
        self.assertIn("delta", campaign_result)
        self.assertIn("baseline_steps", campaign_result)
        self.assertTrue((self.temp_dir / "external_claim_sandbox_campaign.json").exists())
        promotion_preview = runtime.run_external_claim_promotion(
            config_path=str(campaign_config),
            registry_path=str(ingest_registry),
            eval_path=str(self.temp_dir / "quantum_hard_suite_eval.json"),
            default_max_metric_delta=0.05,
            execute=False,
        )
        self.assertEqual(promotion_preview["mode"], "preview")
        self.assertIn("required_confirmation_hash", promotion_preview)
        self.assertTrue((self.temp_dir / "external_claim_promotion.json").exists())

        distilled = runtime.run_trace_distillation()
        self.assertIn("policies", distilled)
        self.assertTrue((self.temp_dir / "distilled_policy.json").exists())

        scale_path = runtime.run_scale_path_decision_framework()
        self.assertIn("default_decision", scale_path)
        self.assertIn("scenario_analysis", scale_path)
        self.assertIn("recommended_profile", scale_path["default_decision"])
        self.assertTrue((self.temp_dir / "scale_path_decision.json").exists())


if __name__ == "__main__":
    unittest.main()
