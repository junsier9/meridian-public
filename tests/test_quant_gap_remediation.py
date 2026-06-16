from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import QuantUniverseCandidate
from enhengclaw.quant_research.data_readiness import CROSS_SECTIONAL_SPOT_BLOCKER
from enhengclaw.quant_research.gap_remediation import (
    build_gap_remediation_plan,
    execute_gap_remediation_backfill,
)
from enhengclaw.quant_research.lab import _apply_gap_driven_backfill_and_targeted_rerun
from tests.quant_pit_test_helpers import pit_candidate


class QuantGapRemediationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-gap-remediation-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.quant_input_root = self.temp_dir / "quant_inputs"
        self.quant_input_root.mkdir(parents=True, exist_ok=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.cycle_root = self.artifacts_root / "cycles" / "2026-04-23"
        self.cycle_root.mkdir(parents=True, exist_ok=True)
        self.universe_candidates = (
            QuantUniverseCandidate.from_payload(pit_candidate("ETH", 2, listing_age_days_as_of=2200)),
            QuantUniverseCandidate.from_payload(pit_candidate("SUI", 28, listing_age_days_as_of=650)),
            QuantUniverseCandidate.from_payload(
                pit_candidate("JTO", 95, usdm_symbol=None, first_perp_bar_utc=None, listing_age_days_as_of=500)
            ),
        )

    def test_build_gap_remediation_plan_targets_only_resolvable_symbols(self) -> None:
        strategies = [
            {
                "strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                "shape": "single_asset",
                "subject": "ETH",
            },
            {
                "strategy_id": "baseline-balanced-logistic-regression-cross-sectional",
                "shape": "cross_sectional",
                "universe_filter": {"subjects": ["ETH", "SUI"]},
            },
        ]
        experiments = [
            {
                "strategy_id": "baseline-eth-balanced-logistic-regression-single-asset",
                "shape": "single_asset",
                "subject": "ETH",
                "data_gap_blockers": ["ETH: missing trade liquidity proxy for perp"],
            },
            {
                "strategy_id": "baseline-balanced-logistic-regression-cross-sectional",
                "shape": "cross_sectional",
                "validation_blocker_codes": [CROSS_SECTIONAL_SPOT_BLOCKER],
                "data_gap_blockers": [],
            },
        ]

        plan = build_gap_remediation_plan(
            as_of="2026-04-23",
            experiments=experiments,
            strategies=strategies,
            universe_candidates=self.universe_candidates,
        )

        self.assertTrue(plan["should_attempt"])
        self.assertEqual(
            plan["affected_strategy_ids"],
            [
                "baseline-balanced-logistic-regression-cross-sectional",
                "baseline-eth-balanced-logistic-regression-single-asset",
            ],
        )
        self.assertEqual(plan["perp_symbols"], ["ETHUSDT"])
        self.assertEqual(plan["spot_symbols"], ["ETHUSDT", "SUIUSDT"])

    def test_execute_gap_remediation_backfill_uses_targeted_symbols(self) -> None:
        plan = {
            "should_attempt": True,
            "affected_strategy_ids": ["baseline-eth-balanced-logistic-regression-single-asset"],
            "spot_symbols": ["ETHUSDT"],
            "perp_symbols": ["ETHUSDT", "SUIUSDT"],
            "universe_perp_symbols": ["ETHUSDT", "SUIUSDT", "BTCUSDT"],
        }
        with patch("enhengclaw.quant_research.gap_remediation.run_quant_coinapi_spot_sync") as mock_spot:
            with patch("enhengclaw.quant_research.gap_remediation.run_quant_derivatives_sync_cycle") as mock_derivatives:
                with patch(
                    "enhengclaw.quant_research.gap_remediation.write_quant_derivatives_sync_summary_for_as_of"
                ) as mock_rebuild:
                    mock_spot.return_value = {"status": "success"}
                    mock_derivatives.return_value = {"status": "success"}
                    mock_rebuild.return_value = ({}, self.temp_dir / "sync_summary.json")
                    summary = execute_gap_remediation_backfill(
                        as_of="2026-04-23",
                        plan=plan,
                        quant_input_root=self.quant_input_root,
                        spot_ohlcv_external_root=self.temp_dir / "coinapi_spot",
                        derivatives_external_root=self.temp_dir / "derivatives",
                    )

        self.assertTrue(summary["attempted"])
        self.assertEqual(mock_spot.call_args.kwargs["spot_symbols"], ["ETHUSDT"])
        self.assertEqual(mock_derivatives.call_args.kwargs["symbols"], ["ETHUSDT", "SUIUSDT"])
        self.assertEqual(mock_derivatives.call_args.kwargs["mode"], "bootstrap")
        self.assertEqual(mock_rebuild.call_args.kwargs["symbols"], ["ETHUSDT", "SUIUSDT", "BTCUSDT"])

    def test_apply_gap_driven_backfill_and_targeted_rerun_reruns_only_affected_strategies(self) -> None:
        strategies = [
            {"strategy_id": "s1", "shape": "single_asset", "subject": "ETH"},
            {"strategy_id": "s2", "shape": "single_asset", "subject": "SUI"},
        ]
        original_experiments = [
            {"strategy_id": "s1", "experiment_id": "2026-04-23-s1", "data_gap_blockers": ["ETH: missing perp_close for execution path"]},
            {"strategy_id": "s2", "experiment_id": "2026-04-23-s2", "data_gap_blockers": []},
        ]
        patched_plan = {
            "should_attempt": True,
            "affected_strategy_ids": ["s1"],
            "spot_symbols": [],
            "perp_symbols": ["ETHUSDT"],
            "universe_perp_symbols": ["ETHUSDT"],
        }
        patched_execution = {
            "attempted": True,
            "spot_backfill": {"attempted": False, "status": "skipped"},
            "derivatives_backfill": {"attempted": True, "status": "success"},
        }
        rerun_experiments = [
            {"strategy_id": "s1", "experiment_id": "2026-04-23-s1", "data_gap_blockers": []},
        ]
        with patch("enhengclaw.quant_research.lab.build_gap_remediation_plan", return_value=patched_plan):
            with patch("enhengclaw.quant_research.lab.execute_gap_remediation_backfill", return_value=patched_execution):
                with patch(
                    "enhengclaw.quant_research.lab.require_derivatives_sync_summary",
                    return_value=({"status": "success"}, self.temp_dir / "reloaded_sync_summary.json"),
                ):
                    with patch("enhengclaw.quant_research.lab.build_quant_datasets", return_value=[{"dataset_id": "d1"}]):
                        with patch("enhengclaw.quant_research.lab.build_quant_feature_sets", return_value=[{"shape": "single_asset"}, {"shape": "cross_sectional"}]):
                            with patch(
                                "enhengclaw.quant_research.lab.run_quant_experiments_for_strategies",
                                return_value=rerun_experiments,
                            ) as mock_rerun:
                                datasets, feature_sets, experiments, _, _, summary = _apply_gap_driven_backfill_and_targeted_rerun(
                                    as_of="2026-04-23",
                                    cycle_root=self.cycle_root,
                                    artifacts_root=self.artifacts_root,
                                    quant_input_root=self.quant_input_root,
                                    ohlcv_external_root=None,
                                    spot_ohlcv_external_root=None,
                                    derivatives_external_root=self.temp_dir / "derivatives",
                                    compiler_backend="deterministic",
                                    source_commit_sha="abc123",
                                    universe_candidates=self.universe_candidates,
                                    daily_strategies=strategies,
                                    datasets=[{"dataset_id": "old"}],
                                    feature_sets=[{"shape": "single_asset"}, {"shape": "cross_sectional"}],
                                    experiments=original_experiments,
                                    derivatives_sync={"status": "success"},
                                    derivatives_sync_summary_path=self.temp_dir / "old_sync_summary.json",
                                )

        self.assertEqual(datasets, [{"dataset_id": "d1"}])
        self.assertEqual(feature_sets, [{"shape": "single_asset"}, {"shape": "cross_sectional"}])
        self.assertEqual(
            [experiment["strategy_id"] for experiment in experiments],
            ["s1", "s2"],
        )
        self.assertEqual(experiments[0]["data_gap_blockers"], [])
        self.assertEqual(experiments[1]["strategy_id"], "s2")
        self.assertEqual(
            [item["strategy_id"] for item in mock_rerun.call_args.kwargs["strategies"]],
            ["s1"],
        )
        self.assertTrue((self.cycle_root / "gap_remediation_summary.json").exists())
        self.assertTrue(summary["attempted"])


if __name__ == "__main__":
    unittest.main()
