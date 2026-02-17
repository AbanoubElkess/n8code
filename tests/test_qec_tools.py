from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.qec_tools import QECSimulatorHook


class TestQECTools(unittest.TestCase):
    def test_qec_hook_fallback(self) -> None:
        hook = QECSimulatorHook()
        output = hook.run(
            {
                "baseline_error": 0.02,
                "physical_error": 0.01,
                "rounds": 15,
                "decoder_gain": 0.12,
                "runtime_penalty": 0.1,
            }
        )
        self.assertIn("engine", output)
        self.assertIn("status", output)
        self.assertIn("consistency", output)
        self.assertTrue(output["consistency"]["passed"])
        self.assertIn("projected_logical_error_rate", output)
        self.assertGreater(output["projected_logical_error_rate"], 0.0)
        self.assertLess(output["projected_logical_error_rate"], 0.02)

    def test_qec_hook_rejects_invalid_payload(self) -> None:
        hook = QECSimulatorHook()
        output = hook.run(
            {
                "baseline_error": 1.2,
                "physical_error": -0.1,
                "rounds": 0,
                "decoder_gain": 1.1,
                "runtime_penalty": -0.4,
            }
        )
        self.assertEqual(output["status"], "rejected")
        self.assertEqual(output["engine"], "consistency-gate")
        self.assertFalse(output["consistency"]["passed"])
        self.assertGreater(len(output["consistency"]["hard_failures"]), 0)

    def test_qec_hook_warns_on_runtime_budget_exceedance(self) -> None:
        hook = QECSimulatorHook()
        output = hook.run(
            {
                "baseline_error": 0.02,
                "physical_error": 0.01,
                "rounds": 20,
                "decoder_gain": 0.12,
                "runtime_penalty": 0.2,
                "max_runtime_penalty": 0.15,
            }
        )
        self.assertEqual(output["status"], "accepted-with-warnings")
        joined = " ".join(output["consistency"]["soft_failures"]).lower()
        self.assertIn("runtime", joined)


if __name__ == "__main__":
    unittest.main()
