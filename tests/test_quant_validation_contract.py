from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.alpha_manifest import build_daily_alpha_manifest_entry, write_daily_alpha_manifest
from enhengclaw.quant_research.contracts import read_json, utc_now, write_json
from enhengclaw.quant_research.feature_admission import build_feature_admission_policy
from enhengclaw.quant_research.governance import build_strategy_entry, save_strategy_library
from enhengclaw.quant_research.legacy_surface import LegacyQuantSurfaceFrozenError
from enhengclaw.quant_research.reproducibility import build_reproducibility_section
from enhengclaw.quant_research.validation_contract import evaluate_validation_contract
from enhengclaw.quant_research.validation_remediation import (
    current_validation_contract_missing_blocker,
    current_validation_contract_pending_reason,
    remediate_historical_validation_contract_reruns,
)
from enhengclaw.quant_research.split_realization_contract import build_split_realization_contract


class QuantValidationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-validation-contract-tests-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        source_commit_patcher = mock.patch.dict(os.environ, {"SOURCE_COMMIT_SHA": "abc123"}, clear=False)
        source_commit_patcher.start()
        self.addCleanup(source_commit_patcher.stop)

    def test_evaluate_validation_contract_returns_passed_failed_incomplete_and_leakage_statuses(self) -> None:
        base_walk_forward = {
            "window_count": 12,
            "median_oos_sharpe": 1.0,
            "windows": [
                {
                    "sharpe": 1.0,
                    "stress_sharpe": 0.8,
                    "test_start_utc": "2025-08-05T00:00:00Z",
                    "test_end_utc": "2025-08-31T23:59:59Z",
                    "trade_count": 10,
                    "rebalance_count": 10,
                    "turnover": 1.0,
                    "max_participation_rate": 0.001,
                },
                {
                    "sharpe": 1.1,
                    "stress_sharpe": 0.9,
                    "test_start_utc": "2025-11-05T00:00:00Z",
                    "test_end_utc": "2025-11-30T23:59:59Z",
                    "trade_count": 10,
                    "rebalance_count": 10,
                    "turnover": 1.0,
                    "max_participation_rate": 0.001,
                },
                {
                    "sharpe": 0.9,
                    "stress_sharpe": 0.7,
                    "test_start_utc": "2026-02-05T00:00:00Z",
                    "test_end_utc": "2026-02-28T23:59:59Z",
                    "trade_count": 10,
                    "rebalance_count": 10,
                    "turnover": 1.0,
                    "max_participation_rate": 0.001,
                },
            ]
            * 4,
        }
        passing_sections = {
            "split_integrity": {
                "split_realization_contract": build_split_realization_contract(shape="single_asset", interval="4h"),
                "label_horizon_bars": 6,
                "bar_interval_ms": 14_400_000,
                "purge_gap_bars": 6,
                "split_boundary_contamination_total": 0,
                "walk_forward_boundary_contamination_total": 0,
                "backtest_realization_mismatch": {"detected": False},
                "overlap_integrity": {"passed": True},
                "leakage_checks": {"passed": True},
                "passed": True,
            },
            "feature_admission": {
                "feature_admission_policy": build_feature_admission_policy(),
                "selected_feature_columns": ["momentum_6", "basis_zscore_20"],
                "excluded_feature_columns": ["timestamp_ms", "market_cap_rank"],
                "banned_proxy_columns_present": [],
                "unknown_numeric_columns_present": [],
                "selected_feature_columns_outside_manifest": [],
                "passed": True,
            },
            "reproducibility": build_reproducibility_section(
                source_commit_sha="abc123",
                dataset_fingerprint="dataset-fingerprint",
                feature_hash="feature-hash",
                dataset_manifest_path="artifacts/quant_research/datasets/demo/dataset_manifest.json",
                feature_manifest_path="artifacts/quant_research/features/demo/feature_manifest.json",
            ),
            "factor_evidence": {
                "rank_ic_mean": 0.02,
                "rank_ic_positive_rate": 0.6,
                "top_minus_bottom_return": 0.03,
                "monotonicity_passed": True,
                "decay_curve": {"intended_horizon_return": 0.03},
                "turnover": 1.0,
                "max_trade_participation_rate": 0.001,
                "max_inventory_participation_rate": 0.001,
                "regime_split_results": [
                    {"quarter": "2025-08", "top_minus_bottom_return": 0.02, "positive": True},
                    {"quarter": "2025-11", "top_minus_bottom_return": 0.02, "positive": True},
                    {"quarter": "2026-02", "top_minus_bottom_return": 0.01, "positive": True},
                    {"quarter": "2026-03", "top_minus_bottom_return": -0.005, "positive": False}
                ],
                "passed": True,
            },
            "walk_forward_assessment": {
                "window_count": 12,
                "median_oos_sharpe": 1.0,
                "loss_window_fraction": 0.0,
                "passed": True,
            },
            "execution_stress": {
                "test_metrics": {"net_return": 0.12},
                "walk_forward_median_oos_sharpe": 0.8,
                "max_participation_rate": 0.001,
                "passed": True,
            },
            "regime_holdout": {
                "covered_regime_count": 3,
                "positive_regime_fraction": 1.0,
                "worst_regime_median_oos_sharpe": 0.9,
                "passed": True,
            },
        }
        passed = evaluate_validation_contract(
            validation_metrics={"sharpe": 1.2},
            test_metrics={"sharpe": 1.1},
            walk_forward=base_walk_forward,
            **passing_sections,
        )
        self.assertEqual(passed["status"], "passed")

        failed = evaluate_validation_contract(
            validation_metrics={"sharpe": 1.2},
            test_metrics={"sharpe": 1.1},
            walk_forward=base_walk_forward,
            split_integrity=passing_sections["split_integrity"],
            feature_admission=passing_sections["feature_admission"],
            reproducibility=passing_sections["reproducibility"],
            factor_evidence=passing_sections["factor_evidence"],
            walk_forward_assessment={**passing_sections["walk_forward_assessment"], "passed": False},
            execution_stress=passing_sections["execution_stress"],
            regime_holdout=passing_sections["regime_holdout"],
        )
        self.assertEqual(failed["status"], "failed")

        feature_failed = evaluate_validation_contract(
            validation_metrics={"sharpe": 1.2},
            test_metrics={"sharpe": 1.1},
            walk_forward=base_walk_forward,
            split_integrity=passing_sections["split_integrity"],
            feature_admission={**passing_sections["feature_admission"], "passed": False},
            reproducibility=passing_sections["reproducibility"],
            factor_evidence=passing_sections["factor_evidence"],
            walk_forward_assessment=passing_sections["walk_forward_assessment"],
            execution_stress=passing_sections["execution_stress"],
            regime_holdout=passing_sections["regime_holdout"],
        )
        self.assertEqual(feature_failed["status"], "failed")
        self.assertIn("feature_admission_failed", {item["code"] for item in feature_failed["blockers"]})

        incomplete = evaluate_validation_contract(
            validation_metrics={"sharpe": 1.2},
            test_metrics={"sharpe": 1.1},
            walk_forward=base_walk_forward,
            split_integrity=passing_sections["split_integrity"],
            feature_admission=passing_sections["feature_admission"],
            reproducibility=passing_sections["reproducibility"],
            factor_evidence=passing_sections["factor_evidence"],
            walk_forward_assessment=passing_sections["walk_forward_assessment"],
            execution_stress={},
            regime_holdout=passing_sections["regime_holdout"],
        )
        self.assertEqual(incomplete["status"], "incomplete")

        leakage = evaluate_validation_contract(
            validation_metrics={"sharpe": 22.0},
            test_metrics={"sharpe": 21.5},
            walk_forward=base_walk_forward,
            split_integrity=passing_sections["split_integrity"],
            feature_admission=passing_sections["feature_admission"],
            reproducibility=passing_sections["reproducibility"],
            factor_evidence=passing_sections["factor_evidence"],
            walk_forward_assessment=passing_sections["walk_forward_assessment"],
            execution_stress=passing_sections["execution_stress"],
            regime_holdout=passing_sections["regime_holdout"],
        )
        self.assertEqual(leakage["status"], "falsification_required")

        reproducibility_failed = evaluate_validation_contract(
            validation_metrics={"sharpe": 1.2},
            test_metrics={"sharpe": 1.1},
            walk_forward=base_walk_forward,
            split_integrity=passing_sections["split_integrity"],
            feature_admission=passing_sections["feature_admission"],
            reproducibility={**passing_sections["reproducibility"], "feature_hash": "", "passed": False},
            factor_evidence=passing_sections["factor_evidence"],
            walk_forward_assessment=passing_sections["walk_forward_assessment"],
            execution_stress=passing_sections["execution_stress"],
            regime_holdout=passing_sections["regime_holdout"],
        )
        self.assertEqual(reproducibility_failed["status"], "failed")
        self.assertIn("reproducibility_contract_failed", {item["code"] for item in reproducibility_failed["blockers"]})

        factor_failed = evaluate_validation_contract(
            validation_metrics={"sharpe": 1.2},
            test_metrics={"sharpe": 1.1},
            walk_forward=base_walk_forward,
            split_integrity=passing_sections["split_integrity"],
            feature_admission=passing_sections["feature_admission"],
            reproducibility=passing_sections["reproducibility"],
            factor_evidence={**passing_sections["factor_evidence"], "passed": False},
            walk_forward_assessment=passing_sections["walk_forward_assessment"],
            execution_stress=passing_sections["execution_stress"],
            regime_holdout=passing_sections["regime_holdout"],
        )
        self.assertEqual(factor_failed["status"], "failed")
        self.assertIn("factor_evidence_failed", {item["code"] for item in factor_failed["blockers"]})

    def test_validation_contract_remediation_invalidates_legacy_pass_experiment(self) -> None:
        strategy_entry = build_strategy_entry(
            strategy_id="baseline-eth-balanced-logistic-regression-single-asset",
            shape="single_asset",
            strategy_profile="balanced",
            subject="ETH",
            universe_filter=None,
            model_family="logistic_regression",
            feature_groups=["core_context", "trend", "derivatives"],
            profile_constraints_override=None,
            source="baseline",
            status="active",
        )
        save_strategy_library(
            artifacts_root=self.artifacts_root,
            payload={
                "generated_at_utc": utc_now(),
                "bootstrapped_as_of": "2026-04-20",
                "entries": [strategy_entry],
            },
        )

        experiment_root = self.artifacts_root / "experiments" / "legacy-pass-alpha"
        experiment_root.mkdir(parents=True, exist_ok=True)
        alpha_card = {
            "generated_at_utc": utc_now(),
            "experiment_id": "legacy-pass-alpha",
            "strategy_id": strategy_entry["strategy_id"],
            "spec_hash": strategy_entry["spec_hash"],
            "source": strategy_entry["source"],
            "as_of": "2026-04-20",
            "shape": "single_asset",
            "model_family": "logistic_regression",
            "strategy_profile": "balanced",
            "subject": "ETH",
            "compiler_backend": "live",
            "backend_mode": "live",
            "experiment_status": "pass",
            "validation": "passed",
            "publication_status": "publishable_to_incoming",
            "dataset_provenance": "live_ohlcv_dataset",
            "lifecycle": "active",
            "validation_metrics": {"net_return": 0.2, "sharpe": 1.0, "max_drawdown": 0.1},
            "test_metrics": {"net_return": 0.25, "sharpe": 1.1, "max_drawdown": 0.1, "trade_count": 40, "rebalance_count": 20},
            "walk_forward": {"window_count": 12, "median_oos_sharpe": 1.0, "windows": []},
            "quality_summary": {"quality_gate_passed": True, "quality_blockers": [], "metrics_snapshot": {}},
        }
        validation_report = {
            "generated_at_utc": utc_now(),
            "experiment_id": "legacy-pass-alpha",
            "experiment_status": "pass",
            "validation_metrics": dict(alpha_card["validation_metrics"]),
            "test_metrics": dict(alpha_card["test_metrics"]),
            "walk_forward": dict(alpha_card["walk_forward"]),
        }
        for file_name, payload in (
            ("alpha_card.json", alpha_card),
            ("validation_report.json", validation_report),
            ("backtest_report.json", {"experiment_id": "legacy-pass-alpha", "experiment_status": "pass"}),
            ("experiment_spec.json", {"experiment_id": "legacy-pass-alpha", "experiment_status": "pass"}),
        ):
            write_json(experiment_root / file_name, payload)

        write_daily_alpha_manifest(
            artifacts_root=self.artifacts_root,
            as_of="2026-04-20",
            entries=[
                build_daily_alpha_manifest_entry(
                    alpha_card_path=experiment_root / "alpha_card.json",
                    alpha_card=alpha_card,
                )
            ],
        )

        with self.assertRaises(LegacyQuantSurfaceFrozenError):
            remediate_historical_validation_contract_reruns(
                artifacts_root=self.artifacts_root,
                workbench_root=self.workbench_root,
                as_of="2026-04-20",
            )


if __name__ == "__main__":
    unittest.main()
