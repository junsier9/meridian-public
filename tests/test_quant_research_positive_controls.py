from __future__ import annotations

from datetime import UTC, datetime, timedelta
import math
import tempfile
from pathlib import Path
import shutil
import unittest

import pandas as pd

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.positive_controls import (
    MIN_SINGLE_ASSET_POSITIVE_CONTROL_WALK_FORWARD_WINDOWS,
    _execute_control_case,
    _pipeline_health,
    has_momentum_12_1_history,
    strong_oracle_score,
    weak_oracle_score,
)


class QuantResearchPositiveControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-positive-controls-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_strong_oracle_is_raw_positive_on_toy_single_asset_and_cross_sectional_frames(self) -> None:
        single_asset_case = _execute_control_case(
            as_of="2026-04-20",
            shape="single_asset",
            control_kind="strong_oracle",
            frame=self._single_asset_frame(periods=1500),
            dataset_id="toy-single-asset",
            feature_set_id="toy-single-asset-features",
            subject="ETH",
            expected_future_dependency=True,
        )
        cross_sectional_case = _execute_control_case(
            as_of="2026-04-20",
            shape="cross_sectional",
            control_kind="strong_oracle",
            frame=self._cross_sectional_frame(periods=220),
            dataset_id="toy-cross-sectional",
            feature_set_id="toy-cross-sectional-features",
            subject=None,
            expected_future_dependency=True,
        )

        self.assertEqual(single_asset_case["status"], "executed")
        self.assertTrue(single_asset_case["raw_positive"])
        self.assertGreater(single_asset_case["nonzero_position_fraction"], 0.0)
        self.assertGreater(single_asset_case["position_sign_counts"]["positive"], 0)
        self.assertEqual(cross_sectional_case["status"], "executed")
        self.assertTrue(cross_sectional_case["raw_positive"])

    def test_single_asset_strong_oracle_skips_when_walk_forward_coverage_is_below_threshold(self) -> None:
        case = _execute_control_case(
            as_of="2026-04-20",
            shape="single_asset",
            control_kind="strong_oracle",
            frame=self._single_asset_frame(periods=1200),
            dataset_id="toy-single-asset",
            feature_set_id="toy-single-asset-features",
            subject="ETH",
            expected_future_dependency=True,
        )

        self.assertEqual(case["status"], "skipped_insufficient_history")
        self.assertIsNone(case["raw_positive"])
        self.assertEqual(case["minimum_walk_forward_windows_required"], MIN_SINGLE_ASSET_POSITIVE_CONTROL_WALK_FORWARD_WINDOWS)
        self.assertEqual(case["available_walk_forward_window_count"], 2)
        self.assertEqual(case["walk_forward"]["window_count"], 2)

    def test_pipeline_health_is_marginal_when_only_skipped_short_history_oracles_exist(self) -> None:
        health, rationale = _pipeline_health(
            [
                {
                    "control_id": "2026-04-20-single-asset-eth-strong-oracle",
                    "control_kind": "strong_oracle",
                    "status": "skipped_insufficient_history",
                },
                {
                    "control_id": "2026-04-20-single-asset-eth-weak-oracle",
                    "control_kind": "weak_oracle",
                    "status": "skipped_insufficient_history",
                },
            ]
        )

        self.assertEqual(health, "marginal")
        self.assertIn("coverage is insufficient", rationale)
        self.assertIn("skipped 1 strong-oracle", rationale)

    def test_weak_oracle_noise_is_reproducible(self) -> None:
        frame = self._single_asset_frame(periods=120)
        score_a = weak_oracle_score(frame, seed=17)
        score_b = weak_oracle_score(frame, seed=17)
        score_c = weak_oracle_score(frame, seed=23)

        pd.testing.assert_series_equal(score_a, score_b)
        self.assertFalse(score_a.equals(score_c))

    def test_momentum_12_1_skips_without_enough_history(self) -> None:
        frame = self._cross_sectional_frame(periods=200)
        self.assertFalse(has_momentum_12_1_history(frame))
        case = _execute_control_case(
            as_of="2026-04-20",
            shape="cross_sectional",
            control_kind="momentum_12_1",
            frame=frame,
            dataset_id="toy-cross-sectional",
            feature_set_id="toy-cross-sectional-features",
            subject=None,
            expected_future_dependency=False,
        )
        self.assertEqual(case["status"], "skipped_insufficient_history")
        self.assertIsNone(case["raw_positive"])

    def _single_asset_frame(self, *, periods: int) -> pd.DataFrame:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        close = 100.0
        closes: list[float] = []
        for index in range(periods):
            step_return = 0.010 + (0.0020 * math.sin(index / 18.0))
            close *= 1.0 + step_return
            closes.append(close)
        frame = pd.DataFrame(
            {
                "timestamp_ms": [int((start + timedelta(hours=4 * index)).timestamp() * 1000) for index in range(periods)],
                "spot_close": closes,
                "subject": "ETH",
            }
        )
        frame["target_forward_return"] = frame["spot_close"].shift(-6) / frame["spot_close"] - 1.0
        return frame.dropna().reset_index(drop=True)

    def _cross_sectional_frame(self, *, periods: int) -> pd.DataFrame:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        subject_params = {
            "A": (0.030, 0.000),
            "B": (0.020, 0.005),
            "C": (0.010, 0.010),
            "D": (-0.010, 0.005),
            "E": (-0.020, 0.000),
        }
        subject_closes = {subject: 100.0 for subject in subject_params}
        rows: list[dict[str, object]] = []
        for index in range(periods):
            timestamp = start + timedelta(days=index)
            for subject, (base_return, amplitude) in subject_params.items():
                step_return = base_return + (amplitude * math.sin(index / 9.0))
                subject_closes[subject] *= 1.0 + step_return
                rows.append(
                    {
                        "timestamp_ms": int(timestamp.timestamp() * 1000),
                        "spot_close": subject_closes[subject],
                        "subject": subject,
                    }
                )
        frame = pd.DataFrame(rows).sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
        frame["target_forward_return"] = frame.groupby("subject", sort=False)["spot_close"].shift(-1) / frame["spot_close"] - 1.0
        return frame.dropna().sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)


if __name__ == "__main__":
    unittest.main()
