from __future__ import annotations

import os
import tempfile
from pathlib import Path
import shutil
import unittest
from unittest import mock

import pandas as pd

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.experiment_status import (
    EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
)
from enhengclaw.quant_research.lab import _backtest_single_asset, _single_asset_position_from_score
from enhengclaw.quant_research.research_health import build_research_quality_summary
from enhengclaw.quant_research.single_asset_repair import _build_single_asset_pre_fix_partition
from enhengclaw.quant_research.contracts import utc_now, write_json
from enhengclaw.quant_research.alpha_manifest import write_daily_alpha_manifest_from_artifacts


class QuantResearchSingleAssetRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-single-asset-repair-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        (self.artifacts_root / "experiments").mkdir(parents=True, exist_ok=True)
        source_commit_patcher = mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        source_commit_patcher.start()
        self.addCleanup(source_commit_patcher.stop)

    def test_single_asset_positions_use_zero_threshold_mapping(self) -> None:
        scores = pd.Series([0.001, 0.0, -0.001], dtype="float64")
        positions = _single_asset_position_from_score(
            scores,
            constraints={"long_only": False, "long_leverage": 1.0, "short_leverage": 0.5},
        )
        self.assertEqual(positions.tolist(), [1.0, 0.0, -0.5])

    def test_long_only_negative_scores_stay_flat(self) -> None:
        scores = pd.Series([-0.001, 0.0, 0.002], dtype="float64")
        positions = _single_asset_position_from_score(
            scores,
            constraints={
                "long_only": True,
                "long_leverage": 1.0,
                "short_leverage": 0.0,
                "execution_venue": "spot",
                "neutral_band_abs_score": 0.001,
                "long_only_full_size_abs_score": 0.003,
            },
        )
        self.assertEqual([round(value, 6) for value in positions.tolist()], [0.0, 0.0, 0.5])

    def test_single_asset_backtest_applies_one_bar_latency_and_costs(self) -> None:
        frame = pd.DataFrame(
            {
                "timestamp_ms": [0, 4 * 60 * 60 * 1000, 8 * 60 * 60 * 1000],
                "spot_close": [100.0, 101.0, 101.0],
                "score": [0.001, 0.0, 0.002],
                "target_forward_return": [0.01, 0.0, 0.02],
            }
        )
        metrics = _backtest_single_asset(
            frame,
            constraints={"long_only": True, "long_leverage": 1.0, "short_leverage": 0.0},
        )
        self.assertEqual(metrics["evaluation_step_bars"], 6)
        self.assertEqual(metrics["latency_bars"], 1)
        self.assertEqual(metrics["gross_return_before_costs"], 0.0)
        self.assertLess(metrics["net_return"], 0.0)
        self.assertGreater(metrics["fee_cost_return"], 0.0)
        self.assertGreater(metrics["slippage_cost_return"], 0.0)

    def test_research_health_excludes_pipeline_unreliable_status_from_decisive_denominator(self) -> None:
        summary = build_research_quality_summary(
            experiments=[
                {
                    "experiment_id": "a",
                    "experiment_status": "fail",
                    "shape": "cross_sectional",
                    "walk_forward": {"window_count": 10, "median_oos_sharpe": -0.1},
                },
                {
                    "experiment_id": "b",
                    "experiment_status": EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
                    "shape": "single_asset",
                    "walk_forward": {"window_count": 4, "median_oos_sharpe": 0.0},
                },
            ],
            artifacts_root=self.artifacts_root,
            scope="daily_cycle",
            as_of="2026-04-20",
            canonical_universe_count=2,
        )
        self.assertEqual(summary["experiment_count"], 2)
        self.assertEqual(summary["decisive_experiment_count"], 1)
        self.assertEqual(summary["experiment_status_counts"][EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX], 1)
        self.assertEqual(summary["raw_pass_rate"], 0.0)

    def test_partition_builder_separates_cross_sectional_and_single_asset_histories(self) -> None:
        self._write_alpha_card(
            experiment_id="2026-04-20-cross",
            as_of="2026-04-20",
            shape="cross_sectional",
            strategy_id="cross",
        )
        self._write_alpha_card(
            experiment_id="2026-04-20-single",
            as_of="2026-04-20",
            shape="single_asset",
            strategy_id="single",
        )
        write_daily_alpha_manifest_from_artifacts(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-20",
        )
        payload = _build_single_asset_pre_fix_partition(
            artifacts_root=self.artifacts_root,
            as_ofs=("2026-04-20",),
        )
        self.assertEqual(payload["cross_sectional_count"], 1)
        self.assertEqual(payload["single_asset_count"], 1)
        self.assertEqual(payload["by_as_of"]["2026-04-20"]["cross_sectional_count"], 1)
        self.assertEqual(payload["by_as_of"]["2026-04-20"]["single_asset_count"], 1)

    def _write_alpha_card(
        self,
        *,
        experiment_id: str,
        as_of: str,
        shape: str,
        strategy_id: str,
    ) -> None:
        root = self.artifacts_root / "experiments" / experiment_id
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at_utc": utc_now(),
            "experiment_id": experiment_id,
            "as_of": as_of,
            "shape": shape,
            "strategy_id": strategy_id,
            "backend_mode": "deterministic",
            "compiler_backend": "deterministic",
            "dataset_provenance": "live_ohlcv_dataset",
            "experiment_status": "fail",
            "validation": "failed",
            "publication_status": "archived_only",
            "walk_forward": {"window_count": 4, "median_oos_sharpe": -0.1},
        }
        write_json(root / "alpha_card.json", payload)


if __name__ == "__main__":
    unittest.main()
