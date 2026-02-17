from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_plan import ExternalClaimPlanner


class TestExternalClaimPlanner(unittest.TestCase):
    def test_plan_reports_distance_and_actions(self) -> None:
        planner = ExternalClaimPlanner()
        eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "declared_baseline_comparison": {
                "comparisons": [
                    {
                        "baseline_id": "external-a",
                        "source_type": "external_reported",
                        "comparability": {
                            "comparable": False,
                            "reasons": [
                                "baseline unverified",
                                "missing verification evidence fields: ['citation']",
                                "suite mismatch",
                                "no overlapping metrics",
                            ],
                        },
                    }
                ]
            },
        }
        release_status = {
            "gates": {
                "external_claim_gate": {
                    "required_external_baselines": 2,
                    "comparable_external_baselines": 0,
                    "external_claim_distance": 2,
                    "blockers": {"baseline unverified": 1},
                }
            }
        }
        plan = planner.plan(eval_report=eval_report, release_status=release_status)
        self.assertEqual(plan["status"], "ok")
        self.assertEqual(plan["external_claim_distance"], 2)
        self.assertEqual(plan["non_comparable_external_rows"], 1)
        self.assertEqual(plan["recoverable_external_rows"], 1)
        self.assertEqual(plan["estimated_distance_after_recoverable_actions"], 1)
        self.assertEqual(plan["claim_calibration_distance"], 0)
        self.assertEqual(plan["additional_baselines_needed"], 1)
        action_types = [row["action_type"] for row in plan["priority_actions"]]
        self.assertIn("refresh_evidence_payload", action_types)
        self.assertIn("attest_baseline", action_types)

    def test_plan_marks_ready_when_distance_is_zero(self) -> None:
        planner = ExternalClaimPlanner()
        eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "declared_baseline_comparison": {
                "comparisons": [
                    {
                        "baseline_id": "external-ok",
                        "source_type": "external_reported",
                        "comparability": {"comparable": True, "reasons": []},
                    }
                ]
            },
        }
        release_status = {
            "gates": {
                "external_claim_gate": {
                    "required_external_baselines": 1,
                    "comparable_external_baselines": 1,
                    "external_claim_distance": 0,
                    "blockers": {},
                }
            }
        }
        plan = planner.plan(eval_report=eval_report, release_status=release_status)
        self.assertEqual(plan["external_claim_distance"], 0)
        self.assertEqual(plan["additional_baselines_needed"], 0)
        self.assertTrue(plan["readiness_after_plan"])
        self.assertEqual(plan["estimated_total_distance_after_recoverable_actions"], 0)

    def test_plan_includes_metadata_normalization_actions(self) -> None:
        planner = ExternalClaimPlanner()
        eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "declared_baseline_comparison": {
                "comparisons": [
                    {
                        "baseline_id": "external-meta",
                        "source_type": "external_reported",
                        "comparability": {
                            "comparable": False,
                            "reasons": [
                                "source metadata appears placeholder or unknown",
                                "source_date must be ISO-8601 date (YYYY-MM-DD)",
                                "retrieval_date must be ISO-8601 date (YYYY-MM-DD)",
                            ],
                        },
                    }
                ]
            },
        }
        release_status = {
            "gates": {
                "external_claim_gate": {
                    "required_external_baselines": 1,
                    "comparable_external_baselines": 0,
                    "external_claim_distance": 1,
                    "blockers": {},
                }
            }
        }
        plan = planner.plan(eval_report=eval_report, release_status=release_status)
        action_types = [row["action_type"] for row in plan["priority_actions"]]
        self.assertIn("replace_placeholder_metadata", action_types)
        self.assertIn("normalize_metadata_dates", action_types)

    def test_plan_includes_claim_calibration_actions_when_gate_fails(self) -> None:
        planner = ExternalClaimPlanner()
        eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "declared_baseline_comparison": {
                "comparisons": [
                    {
                        "baseline_id": "external-ok",
                        "source_type": "external_reported",
                        "comparability": {"comparable": True, "reasons": []},
                    }
                ]
            },
        }
        release_status = {
            "gates": {
                "external_claim_gate": {
                    "required_external_baselines": 1,
                    "comparable_external_baselines": 1,
                    "external_claim_distance": 0,
                    "blockers": {},
                },
                "external_claim_calibration_gate": {
                    "pass": False,
                    "required": True,
                    "reality_score_gap": 0.04,
                    "public_overclaim_rate_gap": 0.02,
                    "missing_metrics": [],
                },
            }
        }
        plan = planner.plan(eval_report=eval_report, release_status=release_status)
        self.assertEqual(plan["claim_calibration_distance"], 1)
        self.assertEqual(plan["estimated_total_distance_after_recoverable_actions"], 1)
        self.assertFalse(plan["readiness_after_plan"])
        action_types = [row["action_type"] for row in plan["priority_actions"]]
        self.assertIn("raise_combined_reality_score", action_types)
        self.assertIn("reduce_public_overclaim_rate", action_types)

    def test_plan_does_not_require_refresh_for_unverified_only_rows(self) -> None:
        planner = ExternalClaimPlanner()
        eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "declared_baseline_comparison": {
                "comparisons": [
                    {
                        "baseline_id": "external-unverified-only",
                        "source_type": "external_reported",
                        "comparability": {
                            "comparable": False,
                            "reasons": ["baseline unverified"],
                        },
                    }
                ]
            },
        }
        release_status = {
            "gates": {
                "external_claim_gate": {
                    "required_external_baselines": 1,
                    "comparable_external_baselines": 0,
                    "external_claim_distance": 1,
                    "blockers": {"baseline unverified": 1},
                },
            }
        }
        plan = planner.plan(eval_report=eval_report, release_status=release_status)
        row_actions = plan["row_plans"][0]["actions"]
        action_types = [row["action_type"] for row in row_actions]
        self.assertIn("attest_baseline", action_types)
        self.assertNotIn("refresh_evidence_payload", action_types)


if __name__ == "__main__":
    unittest.main()
