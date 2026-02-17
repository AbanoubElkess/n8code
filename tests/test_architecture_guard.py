from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.architecture_guard import ArchitectureGuard


class TestArchitectureGuard(unittest.TestCase):
    def test_reference_alignment(self) -> None:
        guard = ArchitectureGuard(reference_path="config/architecture_reference.json")
        result = guard.validate()
        self.assertTrue(result["ok"], msg=str(result["errors"]))


if __name__ == "__main__":
    unittest.main()

