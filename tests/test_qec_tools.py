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
        self.assertIn("projected_logical_error_rate", output)
        self.assertGreater(output["projected_logical_error_rate"], 0.0)
        self.assertLess(output["projected_logical_error_rate"], 0.02)


if __name__ == "__main__":
    unittest.main()

