from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT

import sys

SCRIPT_DIR = ROOT / "scripts" / "quant_research"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_baseline_alpha_confidence import build_payload


class BaselineAlphaConfidenceValidationTests(unittest.TestCase):
    def test_build_payload_scores_paired_path_confidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="baseline-confidence-") as temp_dir:
            path = Path(temp_dir) / "aligned_period_returns.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["timestamp_ms", "timestamp_utc", "baseline", "comparator"],
                )
                writer.writeheader()
                for idx, (baseline, comparator) in enumerate(
                    [
                        (0.03, 0.01),
                        (0.02, -0.01),
                        (-0.01, -0.02),
                        (0.04, 0.02),
                        (0.01, 0.00),
                        (-0.02, -0.03),
                    ]
                ):
                    writer.writerow(
                        {
                            "timestamp_ms": 0,
                            "timestamp_utc": f"2024-01-{idx + 1:02d}T00:00:00Z",
                            "baseline": baseline,
                            "comparator": comparator,
                        }
                    )

            payload = build_payload(
                aligned_returns_path=path,
                baseline="baseline",
                comparators=["comparator"],
            )

        self.assertEqual(payload["window"]["period_count"], 6)
        self.assertGreater(payload["standalone"]["overall"]["sum"], 0.0)
        self.assertGreater(payload["pairwise"]["comparator"]["overall"]["sum"], 0.0)
        self.assertTrue(payload["verdict"]["checks"]["paired_all_comparators_positive_sum"])

    def test_missing_candidate_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="baseline-confidence-") as temp_dir:
            path = Path(temp_dir) / "aligned_period_returns.csv"
            path.write_text(
                "timestamp_ms,timestamp_utc,baseline\n0,2024-01-01T00:00:00Z,0.01\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing candidates"):
                build_payload(
                    aligned_returns_path=path,
                    baseline="baseline",
                    comparators=["missing"],
                )


if __name__ == "__main__":
    unittest.main()
