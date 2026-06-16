from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
import gzip
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.binance_derivatives import CSV_HEADERS as DERIVATIVE_HEADERS
from enhengclaw.quant_research.binance_derivatives import write_derivatives_sync_summary_for_as_of
from enhengclaw.quant_research.baseline_alpha_proof import run_baseline_alpha_proof
from enhengclaw.quant_research.contracts import portable_path, write_json
from enhengclaw.quant_research.deterministic_core import load_deterministic_strategy_manifest
from enhengclaw.quant_research.falsification_audit import run_falsification_audit
from enhengclaw.quant_research.leakage_audit import write_pending_leakage_audit
from enhengclaw.quant_research.runtime_support import run_quant_universe_freeze
from enhengclaw.quant_research.universe_input_producer import run_quant_universe_input_producer
from scripts.market_data.binance_ohlcv import CSV_HEADERS as OHLCV_HEADERS
from tests.quant_pit_test_helpers import pit_candidate, write_pit_quant_input


class DeterministicQuantCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="deterministic-quant-core-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_inputs_root = self.artifacts_root / "_quant_inputs"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
        self.ohlcv_root = self.temp_dir / "external" / "ohlcv"
        self.derivatives_root = self.temp_dir / "external" / "derivatives"
        self.quant_inputs_root.mkdir(parents=True, exist_ok=True)
        self.workbench_root.mkdir(parents=True, exist_ok=True)
        env_patcher = patch.dict(
            os.environ,
            {
                "SOURCE_COMMIT_SHA": "abc123",
                "LOCALAPPDATA": str(self.temp_dir / "localappdata"),
            },
            clear=False,
        )
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        self.as_of = "2026-04-20"
        self._seed_quant_input()
        self._seed_market_history()
        run_quant_universe_freeze(
            as_of=self.as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        write_derivatives_sync_summary_for_as_of(
            as_of=self.as_of,
            symbols=["ETHUSDT", "BTCUSDT", "SOLUSDT"],
            intervals=("4h", "1d"),
            external_root=self.derivatives_root,
        )

    def test_cycle_uses_core_artifacts_only_and_blocks_cross_sectional_lane(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        summary = lab.run_quant_research_cycle(
            as_of=self.as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
            auto_detect_spot_ohlcv_external_root=False,
        )

        self.assertEqual(summary["cycle_mode"], "deterministic_core")
        self.assertEqual(summary["strategy_manifest_contract_version"], "quant_deterministic_strategy_manifest.v1")
        self.assertEqual(summary["readiness_verdict"], "blocked")
        self.assertIn("core-liquidity-balanced-ranking-scorer-cross-sectional", summary["blocked_strategy_ids"])
        self.assertIn("core-liquidity-balanced-ranking-scorer-intraday-cross-sectional", summary["blocked_strategy_ids"])
        self.assertEqual(len(summary["experiment_ids"]), 2)
        self.assertNotIn("governance", summary)
        self.assertNotIn("bridge_summary_path", summary)
        self.assertNotIn("registry_path", summary)

        for legacy_family in ("governance", "proposals", "bridge_exports", "ops", "assessments", "registry"):
            self.assertFalse((self.artifacts_root / legacy_family).exists(), legacy_family)

        frozen_modules = (
            "enhengclaw.quant_research.bridge",
            "enhengclaw.quant_research.discovery",
            "enhengclaw.quant_research.governance",
            "enhengclaw.quant_research.promotion",
            "enhengclaw.quant_research.proposals",
            "enhengclaw.quant_research.repo_health",
        )
        for module_name in frozen_modules:
            self.assertNotIn(module_name, sys.modules, module_name)

    def test_cycle_rerun_is_stable_for_experiment_ids_and_summary_hash(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        first = lab.run_quant_research_cycle(
            as_of=self.as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
            auto_detect_spot_ohlcv_external_root=False,
        )
        second = lab.run_quant_research_cycle(
            as_of=self.as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
            auto_detect_spot_ohlcv_external_root=False,
        )

        self.assertEqual(first["experiment_ids"], second["experiment_ids"])
        self.assertEqual(first["summary_hash"], second["summary_hash"])

    def test_cycle_allowlist_restricts_to_pinned_single_asset_strategies(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        allowlist = [
            "core-eth-conservative-breakout-volatility-expansion-single-asset",
            "core-btc-balanced-mean-reversion-single-asset",
        ]
        summary = lab.run_quant_research_cycle(
            as_of=self.as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
            auto_detect_spot_ohlcv_external_root=False,
            strategy_id_allowlist=allowlist,
        )

        self.assertEqual(summary["strategy_id_allowlist"], allowlist)
        self.assertEqual(summary["daily_strategy_ids"], allowlist)
        self.assertEqual(summary["experiment_count"], 2)
        self.assertNotIn("core-liquidity-balanced-ranking-scorer-cross-sectional", summary["blocked_strategy_ids"])
        self.assertNotIn("core-liquidity-balanced-ranking-scorer-intraday-cross-sectional", summary["blocked_strategy_ids"])

    def test_cycle_builds_split_cross_sectional_dataset_profiles(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        summary = lab.run_quant_research_cycle(
            as_of=self.as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
            auto_detect_spot_ohlcv_external_root=False,
        )

        self.assertIn(f"{self.as_of}-cross-sectional-daily-1d", summary["dataset_subject_counts"])
        self.assertIn(f"{self.as_of}-cross-sectional-intraday-1h", summary["dataset_subject_counts"])
        self.assertEqual(
            summary["cross_sectional_dataset_subject_counts"][f"{self.as_of}-cross-sectional-daily-1d"],
            3,
        )
        self.assertEqual(
            summary["cross_sectional_dataset_subject_counts"][f"{self.as_of}-cross-sectional-intraday-1h"],
            3,
        )

    def test_cycle_uses_suite_specific_coinapi_gap_backfill(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        sync_payload = {"status": "success", "successful_sync_count": 1}
        with patch("enhengclaw.quant_research.lab.run_quant_coinapi_spot_sync", return_value=sync_payload) as mock_sync:
            summary = lab.run_quant_research_cycle(
                as_of=self.as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
                ohlcv_external_root=self.ohlcv_root,
                spot_ohlcv_external_root=self.ohlcv_root,
                derivatives_external_root=self.derivatives_root,
                auto_detect_spot_ohlcv_external_root=False,
                auto_api_gap_backfill=True,
            )

        self.assertTrue(summary["spot_gap_backfill_summary"]["attempted"])
        self.assertEqual(
            sorted(summary["spot_gap_backfill_summary"]["requested_intervals"]),
            ["1d", "1h", "4h"],
        )
        called_intervals = sorted(
            {
                tuple(call.kwargs["required_intervals"])
                for call in mock_sync.call_args_list
            }
        )
        self.assertEqual(called_intervals, [("1d",), ("1h",), ("4h",)])

    def test_deterministic_manifest_entries_have_non_empty_thesis_profiles(self) -> None:
        manifest = load_deterministic_strategy_manifest()
        entries = {entry["strategy_id"]: entry for entry in manifest["entries"]}

        btc = entries["core-btc-balanced-mean-reversion-single-asset"]
        eth = entries["core-eth-conservative-breakout-volatility-expansion-single-asset"]
        cross_daily = entries["core-liquidity-balanced-ranking-scorer-cross-sectional"]
        cross_intraday = entries["core-liquidity-balanced-ranking-scorer-intraday-cross-sectional"]

        self.assertEqual(btc["thesis_family"], "deterministic_mean_reversion")
        self.assertEqual(btc["dataset_profile"], "single_asset")
        self.assertEqual(btc["thesis_profile"]["required_feature_columns"], ["range_position_20"])
        self.assertEqual(btc["thesis_profile"]["intended_holding_horizon_bars"], 6)
        self.assertEqual(eth["thesis_family"], "deterministic_breakout_volatility_expansion")
        self.assertEqual(eth["dataset_profile"], "single_asset")
        self.assertEqual(
            eth["thesis_profile"]["required_feature_columns"],
            ["distance_to_high_20", "momentum_3", "quote_volume_expansion", "realized_volatility_20", "atr_proxy_20"],
        )
        self.assertEqual(eth["thesis_profile"]["execution_venue"], "spot")
        self.assertEqual(cross_daily["dataset_profile"], "cross_sectional_daily_4h")
        self.assertEqual(cross_intraday["dataset_profile"], "cross_sectional_intraday_1h")
        self.assertEqual(cross_intraday["thesis_profile"]["dataset_profile"], "cross_sectional_intraday_1h")

    def test_rule_based_scoring_ignores_unadmitted_hidden_features(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        frame = pd.DataFrame(
            {
                "timestamp_ms": [1, 2, 3],
                "timestamp_utc": ["2026-04-20T00:00:00Z", "2026-04-20T04:00:00Z", "2026-04-20T08:00:00Z"],
                "range_position_20": [0.1, 0.5, 0.9],
                "basis_zscore_20": [25.0, -30.0, 10.0],
                "target_up": [1, 0, 0],
            }
        )

        bundle = lab._fit_and_score(
            model_family="mean_reversion",
            shape="single_asset",
            train_df=frame,
            validation_df=frame,
            test_df=frame,
            feature_columns=["range_position_20"],
        )

        self.assertEqual(
            [round(value, 6) for value in bundle["train"]["score"].tolist()],
            [0.4, 0.0, -0.4],
        )

    def test_single_asset_factor_evidence_uses_time_series_mode(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        rows: list[dict[str, object]] = []
        months = (1, 4, 7, 10)
        index = 0
        for month in months:
            for day in range(1, 9):
                score = -1.6 + (index * 0.1)
                rows.append(
                    {
                        "timestamp_ms": 1_700_000_000_000 + (index * 14_400_000),
                        "timestamp_utc": f"2025-{month:02d}-{day:02d}T00:00:00Z",
                        "score": score,
                        "target_forward_return": score * 0.02,
                    }
                )
                index += 1
        factor = lab._build_factor_evidence_section(
            prediction_frame=pd.DataFrame(rows),
            test_metrics={
                "turnover": 1.0,
                "max_trade_participation_rate": 0.001,
                "max_inventory_participation_rate": 0.001,
            },
            thesis_profile={
                "thesis_id": "core-btc-balanced-mean-reversion-single-asset",
                "required_feature_columns": ["range_position_20"],
                "intended_holding_horizon_bars": 6,
            },
            selected_feature_columns=["range_position_20"],
            strategy_entry={
                "shape": "single_asset",
                "strategy_id": "core-btc-balanced-mean-reversion-single-asset",
                "requires_derivatives_features": False,
            },
        )

        self.assertEqual(factor["evaluation_mode"], "single_asset_time_series")
        self.assertGreater(factor["top_minus_bottom_return"], 0.0)
        self.assertTrue(factor["monotonicity_passed"])
        self.assertTrue(factor["passed"])

    def test_cross_sectional_factor_evidence_uses_small_panel_spread_diagnostics(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        rows: list[dict[str, object]] = []
        months = (1, 4, 7, 10)
        timestamp_index = 0
        subject_offsets = (
            ("AAA", -1.5, -0.04),
            ("BBB", -0.5, -0.01),
            ("CCC", 0.5, 0.01),
            ("DDD", 1.5, 0.04),
        )
        for month in months:
            for day in (1, 8):
                timestamp_ms = 1_700_000_000_000 + (timestamp_index * 14_400_000)
                timestamp_utc = f"2025-{month:02d}-{day:02d}T00:00:00Z"
                for subject, score, target_forward_return in subject_offsets:
                    rows.append(
                        {
                            "subject": subject,
                            "timestamp_ms": timestamp_ms,
                            "timestamp_utc": timestamp_utc,
                            "score": score,
                            "target_forward_return": target_forward_return,
                        }
                    )
                timestamp_index += 1
        factor = lab._build_factor_evidence_section(
            prediction_frame=pd.DataFrame(rows),
            test_metrics={
                "turnover": 0.5,
                "max_trade_participation_rate": 0.001,
                "max_inventory_participation_rate": 0.001,
            },
            thesis_profile={
                "thesis_id": "xs-pair-book-small-panel",
                "required_feature_columns": ["basis_proxy"],
                "intended_holding_horizon_bars": 5,
            },
            selected_feature_columns=["basis_proxy"],
            strategy_entry={
                "shape": "cross_sectional",
                "strategy_id": "xs-pair-book-small-panel",
                "requires_derivatives_features": False,
            },
        )

        self.assertEqual(factor["evaluation_mode"], "cross_sectional_snapshot")
        self.assertGreater(factor["top_minus_bottom_return"], 0.0)
        self.assertTrue(factor["monotonicity_passed"])
        self.assertTrue(factor["passed"])

    def test_baseline_alpha_proof_reports_missing_exact_date_input(self) -> None:
        proof = run_baseline_alpha_proof(
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
            workbench_root=self.workbench_root,
            ohlcv_external_root=self.ohlcv_root,
            derivatives_external_root=self.derivatives_root,
            auto_detect_spot_ohlcv_external_root=False,
        )

        self.assertFalse(proof["proof_passed"])
        self.assertIn("missing_quant_input", proof["blocker_codes"])
        self.assertTrue((self.artifacts_root / "cycles" / "2026-04-23" / "baseline_alpha_proof.json").exists())

    def test_baseline_alpha_proof_chooses_first_passing_strategy_and_stable_hashes(self) -> None:
        proof_as_of = "2026-04-23"
        proof_strategy_ids = [
            "core-eth-conservative-breakout-volatility-expansion-single-asset",
            "core-btc-balanced-mean-reversion-single-asset",
        ]
        self._seed_quant_input_for(as_of=proof_as_of)
        run_quant_universe_freeze(
            as_of=proof_as_of,
            artifacts_root=self.artifacts_root,
            quant_input_root=self.quant_inputs_root,
        )
        write_derivatives_sync_summary_for_as_of(
            as_of=proof_as_of,
            symbols=["ETHUSDT", "BTCUSDT", "SOLUSDT"],
            intervals=("4h", "1d"),
            external_root=self.derivatives_root,
        )
        cycle_calls: list[list[str]] = []

        def fake_run_quant_research_cycle(**kwargs):
            cycle_calls.append(list(kwargs.get("strategy_id_allowlist") or []))
            self.assertEqual(kwargs["as_of"], proof_as_of)
            self.assertEqual(kwargs["strategy_id_allowlist"], proof_strategy_ids)
            experiments_root = self.artifacts_root / "experiments"
            experiment_ids: list[str] = []
            for strategy_id in proof_strategy_ids:
                experiment_id = f"{proof_as_of}-{strategy_id}"
                experiment_root = experiments_root / experiment_id
                experiment_root.mkdir(parents=True, exist_ok=True)
                subject = "ETH" if strategy_id.startswith("core-eth-") else "BTC"
                is_winner = strategy_id == proof_strategy_ids[0]
                reproducibility = {
                    "dataset_fingerprint": f"{subject.lower()}-dataset-fp",
                    "feature_hash": f"{subject.lower()}-feature-hash",
                }
                alpha_card = {
                    "experiment_id": experiment_id,
                    "strategy_id": strategy_id,
                    "subject": subject,
                    "model_family": "breakout_volatility_expansion" if is_winner else "mean_reversion",
                    "strategy_profile": "conservative" if is_winner else "balanced",
                    "reproducibility": reproducibility,
                    "split_realization_contract": {
                        "shape": "single_asset",
                        "interval": "4h",
                        "target_horizon_bars": 6,
                        "realization_step_bars": 1,
                        "partition_gap_bars": 6,
                        "bar_interval_ms": 14_400_000,
                    },
                    "falsification_status": "cleared" if is_winner else "failed",
                    "falsification_blocker_codes": [] if is_winner else ["falsification_not_cleared"],
                    "credible_research_evidence": is_winner,
                }
                validation_report = {
                    "validation_contract": {
                        "contract_version": "quant_validation_contract.v10",
                        "status": "passed" if is_winner else "failed",
                        "blockers": [] if is_winner else [{"code": "validation_contract_failed"}],
                    },
                    "validation_metrics": {"sharpe": 1.2 if is_winner else -0.4},
                    "test_metrics": {"sharpe": 1.1 if is_winner else -0.2},
                    "walk_forward_assessment": {"passed": is_winner, "median_oos_sharpe": 1.0 if is_winner else -0.1},
                    "execution_stress": {"passed": is_winner, "max_participation_rate": 0.001 if is_winner else 0.01},
                    "regime_holdout": {"passed": is_winner, "covered_regime_count": 3 if is_winner else 1},
                }
                write_json(experiment_root / "alpha_card.json", alpha_card)
                write_json(experiment_root / "validation_report.json", validation_report)
                experiment_ids.append(experiment_id)
            return {
                "summary_hash": "stable-summary-hash",
                "experiment_ids": experiment_ids,
                "summary_path": str(self.artifacts_root / "cycles" / proof_as_of / "quant_cycle_summary.json"),
            }

        with patch("enhengclaw.quant_research.lab.run_quant_research_cycle", side_effect=fake_run_quant_research_cycle):
            proof = run_baseline_alpha_proof(
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
                ohlcv_external_root=self.ohlcv_root,
                derivatives_external_root=self.derivatives_root,
                auto_detect_spot_ohlcv_external_root=False,
            )

        self.assertEqual(len(cycle_calls), 2)
        self.assertTrue(proof["proof_passed"])
        self.assertEqual(proof["passing_strategy_ids"], [proof_strategy_ids[0]])
        self.assertEqual(proof["winner_strategy_id"], proof_strategy_ids[0])
        self.assertEqual(proof["run_1_summary_hash"], "stable-summary-hash")
        self.assertEqual(proof["run_2_summary_hash"], "stable-summary-hash")
        self.assertTrue(proof["per_strategy_evidence_hashes"][proof_strategy_ids[0]]["evidence_hash_consistent"])
        self.assertFalse(proof["per_strategy_evidence_hashes"][proof_strategy_ids[1]]["passing"])
        self.assertNotIn("core-liquidity-balanced-ranking-scorer-cross-sectional", proof["strategy_ids"])

    def test_baseline_alpha_proof_prep_uses_dual_roots_for_snapshot_membership(self) -> None:
        proof_as_of = "2026-04-23"
        proof_strategy_ids = [
            "core-eth-conservative-breakout-volatility-expansion-single-asset",
            "core-btc-balanced-mean-reversion-single-asset",
        ]
        isolated_artifacts_root = self.temp_dir / "dual-root-artifacts" / "quant_research"
        isolated_quant_inputs_root = isolated_artifacts_root / "_quant_inputs"
        isolated_workbench_root = self.temp_dir / "dual-root-artifacts" / "research_workbench"
        isolated_spot_root = self.temp_dir / "dual-root-external" / "coinapi_ohlcv"
        isolated_perp_root = self.temp_dir / "dual-root-external" / "binance_ohlcv"
        isolated_derivatives_root = self.temp_dir / "dual-root-external" / "derivatives"
        isolated_quant_inputs_root.mkdir(parents=True, exist_ok=True)
        isolated_workbench_root.mkdir(parents=True, exist_ok=True)

        start_daily = datetime(2025, 9, 1, tzinfo=UTC)
        start_4h = datetime(2025, 12, 1, tzinfo=UTC)
        for symbol, base_price, drift, wiggle in (
            ("ETHUSDT", 2500.0, 0.004, 0.02),
            ("BTCUSDT", 43000.0, 0.003, 0.015),
        ):
            self._write_ohlcv_series("spot", symbol, "1d", start_daily, 230, base_price, drift, wiggle, external_root=isolated_spot_root)
            self._write_ohlcv_series(
                "spot",
                symbol,
                "4h",
                start_4h,
                1100,
                base_price,
                drift / 6.0,
                wiggle / 2.0,
                external_root=isolated_spot_root,
            )
            self._write_ohlcv_series(
                "usdm_perp",
                symbol,
                "1d",
                start_daily,
                230,
                base_price * 1.001,
                drift * 1.05,
                wiggle,
                external_root=isolated_perp_root,
            )
            self._write_derivative_series(symbol, "4h", start_4h, 1100, external_root=isolated_derivatives_root)
            self._write_derivative_series(symbol, "1d", start_daily, 230, external_root=isolated_derivatives_root)

        summary = run_quant_universe_input_producer(
            as_of=proof_as_of,
            artifacts_root=isolated_artifacts_root,
            quant_input_root=isolated_quant_inputs_root,
            spot_ohlcv_external_root=isolated_spot_root,
            perp_ohlcv_external_root=isolated_perp_root,
        )
        self.assertIn("BTC", summary["sample_subjects"])
        self.assertIn("ETH", summary["sample_subjects"])

        run_quant_universe_freeze(
            as_of=proof_as_of,
            artifacts_root=isolated_artifacts_root,
            quant_input_root=isolated_quant_inputs_root,
        )
        write_derivatives_sync_summary_for_as_of(
            as_of=proof_as_of,
            symbols=["ETHUSDT", "BTCUSDT"],
            intervals=("4h", "1d"),
            external_root=isolated_derivatives_root,
        )

        def fake_run_quant_research_cycle(**kwargs):
            self.assertEqual(kwargs["strategy_id_allowlist"], proof_strategy_ids)
            experiments_root = isolated_artifacts_root / "experiments"
            experiment_ids: list[str] = []
            for strategy_id in proof_strategy_ids:
                experiment_id = f"{proof_as_of}-{strategy_id}"
                experiment_root = experiments_root / experiment_id
                experiment_root.mkdir(parents=True, exist_ok=True)
                subject = "ETH" if strategy_id.startswith("core-eth-") else "BTC"
                reproducibility = {
                    "dataset_fingerprint": f"{subject.lower()}-dataset-fp",
                    "feature_hash": f"{subject.lower()}-feature-hash",
                }
                alpha_card = {
                    "experiment_id": experiment_id,
                    "strategy_id": strategy_id,
                    "subject": subject,
                    "model_family": "breakout_volatility_expansion" if subject == "ETH" else "mean_reversion",
                    "strategy_profile": "conservative" if subject == "ETH" else "balanced",
                    "reproducibility": reproducibility,
                    "split_realization_contract": {
                        "shape": "single_asset",
                        "interval": "4h",
                        "target_horizon_bars": 6,
                        "realization_step_bars": 1,
                        "partition_gap_bars": 6,
                        "bar_interval_ms": 14_400_000,
                    },
                    "falsification_status": "cleared",
                    "falsification_blocker_codes": [],
                    "credible_research_evidence": True,
                }
                validation_report = {
                    "validation_contract": {
                        "contract_version": "quant_validation_contract.v10",
                        "status": "passed",
                        "blockers": [],
                    },
                    "validation_metrics": {"sharpe": 1.2},
                    "test_metrics": {"sharpe": 1.1},
                    "walk_forward_assessment": {"passed": True, "median_oos_sharpe": 1.0},
                    "execution_stress": {"passed": True, "max_participation_rate": 0.001},
                    "regime_holdout": {"passed": True, "covered_regime_count": 3},
                }
                write_json(experiment_root / "alpha_card.json", alpha_card)
                write_json(experiment_root / "validation_report.json", validation_report)
                experiment_ids.append(experiment_id)
            return {
                "summary_hash": "dual-root-summary-hash",
                "experiment_ids": experiment_ids,
                "summary_path": str(isolated_artifacts_root / "cycles" / proof_as_of / "quant_cycle_summary.json"),
            }

        with patch("enhengclaw.quant_research.lab.run_quant_research_cycle", side_effect=fake_run_quant_research_cycle):
            proof = run_baseline_alpha_proof(
                artifacts_root=isolated_artifacts_root,
                quant_input_root=isolated_quant_inputs_root,
                workbench_root=isolated_workbench_root,
                ohlcv_external_root=isolated_perp_root,
                spot_ohlcv_external_root=isolated_spot_root,
                derivatives_external_root=isolated_derivatives_root,
                auto_detect_spot_ohlcv_external_root=False,
            )

        self.assertTrue(proof["proof_passed"])
        self.assertNotIn("missing_subject_in_universe_snapshot", proof["blocker_codes"])
        self.assertTrue(proof["spot_manifest_checks"][proof_strategy_ids[0]]["spot_4h_present"])
        self.assertTrue(proof["spot_manifest_checks"][proof_strategy_ids[1]]["spot_1d_present"])
        snapshot = json.loads(
            (
                isolated_artifacts_root
                / "universe"
                / proof_as_of
                / "universe_snapshot.json"
            ).read_text(encoding="utf-8")
        )
        snapshot_subjects = [item["subject"] for item in snapshot["candidates"]]
        self.assertIn("ETH", snapshot_subjects)
        self.assertIn("BTC", snapshot_subjects)

    def test_placeholder_leakage_audit_writer_is_retired(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "placeholder audit retired"):
            write_pending_leakage_audit(
                artifacts_root=self.artifacts_root,
                as_of=self.as_of,
                alpha_card_path=self.artifacts_root / "experiments" / "demo" / "alpha_card.json",
                alpha_card={},
            )

    def test_falsification_audit_fails_on_legacy_dataset_columns(self) -> None:
        fixture = self._write_falsification_fixture(
            experiment_id="legacy-dataset-columns",
            dataset_columns=["timestamp_ms", "subject", "market_cap_rank", "return_1"],
            feature_numeric_columns=["return_1"],
            selected_feature_columns=["return_1"],
        )
        audit = run_falsification_audit(
            experiment_root=fixture["experiment_root"],
            alpha_card=fixture["alpha_card"],
            validation_report=fixture["validation_report"],
        )

        self.assertEqual(audit["status"], "failed")
        self.assertIn("legacy_dataset_columns_present", audit["blocker_codes"])
        self.assertTrue((fixture["experiment_root"] / "falsification_audit.json").exists())

    def test_falsification_audit_ignores_unselected_legacy_feature_matrix_columns(self) -> None:
        fixture = self._write_falsification_fixture(
            experiment_id="unselected-legacy-feature-columns",
            dataset_columns=["timestamp_ms", "subject", "selection_rank", "return_1"],
            feature_numeric_columns=["return_1", "post_pump_stall_core_score_3d"],
            selected_feature_columns=["return_1"],
        )
        audit = run_falsification_audit(
            experiment_root=fixture["experiment_root"],
            alpha_card=fixture["alpha_card"],
            validation_report=fixture["validation_report"],
        )

        self.assertEqual(audit["status"], "cleared")
        self.assertNotIn("legacy_feature_columns_present", audit["blocker_codes"])

    def test_falsification_audit_fails_on_selected_legacy_feature_columns(self) -> None:
        fixture = self._write_falsification_fixture(
            experiment_id="selected-legacy-feature-columns",
            dataset_columns=["timestamp_ms", "subject", "selection_rank", "return_1"],
            feature_numeric_columns=["return_1", "selection_rank"],
            selected_feature_columns=["selection_rank"],
        )
        audit = run_falsification_audit(
            experiment_root=fixture["experiment_root"],
            alpha_card=fixture["alpha_card"],
            validation_report=fixture["validation_report"],
        )

        self.assertEqual(audit["status"], "failed")
        self.assertIn("legacy_feature_columns_present", audit["blocker_codes"])

    def test_lab_finalizer_writes_cleared_falsification_audit_when_triggered(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        fixture = self._write_falsification_fixture(
            experiment_id="lab-finalizer-falsification",
            dataset_columns=["timestamp_ms", "subject", "selection_rank", "return_1"],
            feature_numeric_columns=["return_1"],
            selected_feature_columns=["return_1"],
        )
        evidence_paths = lab._finalize_experiment_evidence(
            experiment_root=fixture["experiment_root"],
            experiment_spec=json.loads(json.dumps(fixture["alpha_card"])),
            backtest_report=json.loads(json.dumps(fixture["alpha_card"])),
            validation_report=fixture["validation_report"],
            alpha_card=fixture["alpha_card"],
            compiler_backend="deterministic",
        )

        falsification_audit_path = Path(evidence_paths["alpha_card_path"]).parent / "falsification_audit.json"
        self.assertTrue(falsification_audit_path.exists())
        audit = json.loads(falsification_audit_path.read_text(encoding="utf-8"))
        self.assertEqual(audit["contract_version"], "quant_falsification_audit.v2")
        self.assertEqual(audit["status"], "cleared")
        alpha_card = json.loads((falsification_audit_path.parent / "alpha_card.json").read_text(encoding="utf-8"))
        self.assertEqual(alpha_card["falsification_status"], "cleared")
        self.assertTrue(alpha_card["credible_research_evidence"])
        self.assertNotIn("pending", json.dumps(alpha_card))
        self.assertEqual(alpha_card["validation"], "deterministic_only")

    def test_lab_finalizer_writes_statistical_falsification_and_experiment_card_artifacts(self) -> None:
        lab = self._load_lab_module(clear_frozen_modules=True)
        fixture = self._write_falsification_fixture(
            experiment_id="lab-finalizer-statistical-artifacts",
            dataset_columns=["timestamp_ms", "subject", "selection_rank", "return_1"],
            feature_numeric_columns=["return_1"],
            selected_feature_columns=["return_1"],
        )
        fixture["validation_report"]["statistical_falsification"] = {
            "contract_version": "quant_statistical_falsification.v1",
            "status": "failed",
            "blocker_codes": ["delay_stress_failed"],
        }
        fixture["alpha_card"]["alpha_experiment_card"] = {
            "contract_version": "quant_alpha_experiment_card.v1",
            "status": "no_go",
            "blocker_codes": ["promotion_gate_fields_incomplete"],
        }

        evidence_paths = lab._finalize_experiment_evidence(
            experiment_root=fixture["experiment_root"],
            experiment_spec=json.loads(json.dumps(fixture["alpha_card"])),
            backtest_report=json.loads(json.dumps(fixture["alpha_card"])),
            validation_report=fixture["validation_report"],
            alpha_card=fixture["alpha_card"],
            compiler_backend="deterministic",
        )

        self.assertTrue(Path(evidence_paths["statistical_falsification_report_path"]).exists())
        self.assertTrue(Path(evidence_paths["alpha_experiment_card_path"]).exists())
        statistical = json.loads(Path(evidence_paths["statistical_falsification_report_path"]).read_text(encoding="utf-8"))
        experiment_card = json.loads(Path(evidence_paths["alpha_experiment_card_path"]).read_text(encoding="utf-8"))
        self.assertEqual(statistical["contract_version"], "quant_statistical_falsification.v1")
        self.assertEqual(experiment_card["contract_version"], "quant_alpha_experiment_card.v1")

    def _load_lab_module(self, *, clear_frozen_modules: bool) -> object:
        frozen_modules = (
            "enhengclaw.quant_research.bridge",
            "enhengclaw.quant_research.discovery",
            "enhengclaw.quant_research.governance",
            "enhengclaw.quant_research.promotion",
            "enhengclaw.quant_research.proposals",
            "enhengclaw.quant_research.repo_health",
            "enhengclaw.quant_research.lab",
        )
        if clear_frozen_modules:
            for module_name in frozen_modules:
                sys.modules.pop(module_name, None)
        return importlib.import_module("enhengclaw.quant_research.lab")

    def _seed_quant_input(self) -> None:
        self._seed_quant_input_for(as_of=self.as_of)

    def _seed_quant_input_for(self, *, as_of: str) -> None:
        candidates = [
            pit_candidate("ETH", 2, selection_score=18_000_000_000.0, listing_age_days_as_of=2200),
            pit_candidate("BTC", 5, selection_score=15_000_000_000.0, listing_age_days_as_of=3200),
            pit_candidate("SOL", 18, selection_score=4_200_000_000.0, listing_age_days_as_of=1800),
        ]
        for rank in range(4, 101):
            if rank in {5, 18}:
                continue
            symbol = f"TK{rank:03d}"
            candidates.append(
                pit_candidate(
                    symbol,
                    rank,
                    selection_score=max(50_000_000.0, 5_000_000_000.0 - (rank * 10_000_000.0)),
                    listing_age_days_as_of=max(120, 1200 - rank),
                )
            )
        write_pit_quant_input(
            root=self.quant_inputs_root,
            as_of=as_of,
            candidates=candidates,
        )

    def _seed_market_history(self) -> None:
        start_daily = datetime(2025, 9, 1, tzinfo=UTC)
        start_4h = datetime(2025, 12, 1, tzinfo=UTC)
        start_1h = datetime(2026, 2, 1, tzinfo=UTC)
        specs = [
            ("ETHUSDT", 2500.0, 0.004, 0.02),
            ("BTCUSDT", 43000.0, 0.003, 0.015),
            ("SOLUSDT", 120.0, 0.006, 0.04),
        ]
        for symbol, base_price, drift, wiggle in specs:
            self._write_ohlcv_series("spot", symbol, "1d", start_daily, 230, base_price, drift, wiggle)
            self._write_ohlcv_series("spot", symbol, "4h", start_4h, 1100, base_price, drift / 6.0, wiggle / 2.0)
            self._write_ohlcv_series("spot", symbol, "1h", start_1h, 1600, base_price, drift / 24.0, wiggle / 3.0)
            self._write_ohlcv_series("usdm_perp", symbol, "1d", start_daily, 230, base_price * 1.001, drift * 1.05, wiggle)
            self._write_ohlcv_series("usdm_perp", symbol, "4h", start_4h, 1100, base_price * 1.001, drift / 6.0, wiggle / 2.0)
            self._write_derivative_series(symbol, "4h", start_4h, 1100)
            self._write_derivative_series(symbol, "1d", start_daily, 230)

    def _write_ohlcv_series(
        self,
        market_type: str,
        symbol: str,
        interval: str,
        start: datetime,
        periods: int,
        base_price: float,
        drift: float,
        wiggle: float,
        external_root: Path | None = None,
    ) -> None:
        interval_delta = {"1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}[interval]
        rows = []
        current_price = base_price
        for index in range(periods):
            open_time = start + (interval_delta * index)
            close_time = open_time + interval_delta - timedelta(milliseconds=1)
            oscillation = math.sin(index / 7.0) * wiggle
            close_price = current_price * (1.0 + drift + oscillation / 100.0)
            high_price = max(current_price, close_price) * 1.01
            low_price = min(current_price, close_price) * 0.99
            volume = 1_000_000 + (index * 500)
            quote_volume = volume * ((current_price + close_price) / 2.0)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": market_type,
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "open": f"{current_price:.8f}",
                    "high": f"{high_price:.8f}",
                    "low": f"{low_price:.8f}",
                    "close": f"{close_price:.8f}",
                    "volume": f"{volume:.8f}",
                    "quote_volume": f"{quote_volume:.8f}",
                    "trade_count": "1000",
                    "taker_buy_base_volume": f"{volume * 0.51:.8f}",
                    "taker_buy_quote_volume": f"{quote_volume * 0.51:.8f}",
                    "source": "test",
                }
            )
            current_price = close_price
        self._write_partitioned_rows(
            root=(external_root or self.ohlcv_root) / market_type / symbol / interval,
            headers=OHLCV_HEADERS,
            rows=rows,
        )

    def _write_derivative_series(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        periods: int,
        external_root: Path | None = None,
    ) -> None:
        interval_delta = {"4h": timedelta(hours=4), "1d": timedelta(days=1)}[interval]
        rows = []
        for index in range(periods):
            open_time = start + (interval_delta * index)
            close_time = open_time + interval_delta - timedelta(milliseconds=1)
            rows.append(
                {
                    "exchange": "binance",
                    "market_type": "usdm_perp",
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": str(int(open_time.timestamp() * 1000)),
                    "close_time_ms": str(int(close_time.timestamp() * 1000)),
                    "funding_rate": f"{0.0001 + (index % 6) * 0.00001:.8f}",
                    "funding_sample_count": "1",
                    "open_interest": f"{1000000 + (index * 2500):.4f}",
                    "open_interest_value": f"{50000000 + (index * 75000):.4f}",
                    "perp_close": f"{100 + (index * 0.1):.8f}",
                    "perp_quote_volume_usd": f"{12000000 + (index * 10000):.4f}",
                    "source": "test",
                }
            )
        self._write_partitioned_rows(
            root=(external_root or self.derivatives_root) / symbol / interval,
            headers=DERIVATIVE_HEADERS,
            rows=rows,
        )

    def _write_falsification_fixture(
        self,
        *,
        experiment_id: str,
        dataset_columns: list[str],
        feature_numeric_columns: list[str],
        selected_feature_columns: list[str],
    ) -> dict[str, object]:
        experiment_root = self.artifacts_root / "experiments" / experiment_id
        dataset_root = self.artifacts_root / "datasets" / f"{experiment_id}-dataset"
        feature_root = self.artifacts_root / "features" / f"{experiment_id}-features"
        experiment_root.mkdir(parents=True, exist_ok=True)
        dataset_root.mkdir(parents=True, exist_ok=True)
        feature_root.mkdir(parents=True, exist_ok=True)
        universe_snapshot_path = self.artifacts_root / "universe" / self.as_of / "universe_snapshot.json"
        snapshot = json.loads(universe_snapshot_path.read_text(encoding="utf-8"))
        dataset_manifest_path = dataset_root / "dataset_manifest.json"
        feature_manifest_path = feature_root / "feature_manifest.json"
        dataset_manifest = {
            "dataset_id": f"{experiment_id}-dataset",
            "columns": list(dataset_columns),
            "subjects": ["ETH"],
            "dataset_fingerprint": "dataset-fp",
            "universe_definition_id": snapshot["universe_definition_id"],
            "universe_contract_version": snapshot["universe_contract_version"],
            "universe_snapshot_path": portable_path(universe_snapshot_path, repo_root=ROOT),
            "universe_selection_policy_hash": snapshot["universe_selection_policy_hash"],
        }
        feature_manifest = {
            "feature_set_id": f"{experiment_id}-features",
            "dataset_id": dataset_manifest["dataset_id"],
            "available_numeric_columns": list(feature_numeric_columns),
            "numeric_feature_columns": list(feature_numeric_columns),
            "excluded_numeric_columns": [],
            "feature_hash": "feature-hash",
            "dataset_fingerprint": "dataset-fp",
            "split_realization_contract": {
                "shape": "single_asset",
                "interval": "4h",
                "target_horizon_bars": 6,
                "realization_step_bars": 1,
                "partition_gap_bars": 6,
                "bar_interval_ms": 14_400_000,
            },
            "universe_definition_id": snapshot["universe_definition_id"],
            "universe_contract_version": snapshot["universe_contract_version"],
            "universe_snapshot_path": portable_path(universe_snapshot_path, repo_root=ROOT),
            "universe_selection_policy_hash": snapshot["universe_selection_policy_hash"],
        }
        write_json(dataset_manifest_path, dataset_manifest)
        write_json(feature_manifest_path, feature_manifest)
        shared_payload = {
            "experiment_id": experiment_id,
            "strategy_id": "core-liquidity-balanced-logistic-eth",
            "as_of": self.as_of,
            "experiment_status": "quarantined",
            "shape": "single_asset",
            "subject": "ETH",
            "liquidity_bucket": "top_liquidity",
            "market_symbols": {"spot_symbol": "ETHUSDT", "usdm_symbol": "ETHUSDT"},
            "reproducibility": {
                "dataset_manifest_path": portable_path(dataset_manifest_path, repo_root=ROOT),
                "feature_manifest_path": portable_path(feature_manifest_path, repo_root=ROOT),
                "dataset_fingerprint": "dataset-fp",
                "feature_hash": "feature-hash",
            },
            "validation_contract": {
                "contract_version": "quant_validation_contract.v10",
                "status": "falsification_required",
                "blockers": [
                    {
                        "code": "sharpe_anomaly_detected",
                        "message": "forced anomaly",
                        "scope": "validation_contract",
                    }
                ],
                "required_sections_present": [
                    "split_integrity",
                    "feature_admission",
                    "reproducibility",
                    "factor_evidence",
                    "walk_forward_assessment",
                    "execution_stress",
                    "regime_holdout",
                ],
            },
            "feature_admission": {
                "passed": True,
                "selected_feature_columns": list(selected_feature_columns),
            },
            "split_integrity": {
                "passed": True,
                "split_boundary_contamination_total": 0,
                "walk_forward_boundary_contamination_total": 0,
                "backtest_realization_mismatch": {"detected": False},
            },
            "leakage_checks": {
                "passed": True,
                "contract_assertions": {
                    "strict_ordering_passed": True,
                    "zero_boundary_contamination_passed": True,
                },
            },
            "walk_forward": {
                "windows": [
                    {
                        "contract_passed": True,
                    }
                ]
            },
            "split_realization_contract": dict(feature_manifest["split_realization_contract"]),
            "validation_metrics": {"sharpe": 6.5},
            "test_metrics": {"sharpe": 5.8},
            "top_long_candidates": [{"subject": "ETH", "score": 1.0, "liquidity_bucket": "top_liquidity"}],
            "universe_definition_id": snapshot["universe_definition_id"],
            "universe_contract_version": snapshot["universe_contract_version"],
            "universe_snapshot_path": portable_path(universe_snapshot_path, repo_root=ROOT),
            "universe_selection_policy_hash": snapshot["universe_selection_policy_hash"],
        }
        alpha_card = json.loads(json.dumps(shared_payload))
        validation_report = json.loads(json.dumps(shared_payload))
        return {
            "experiment_root": experiment_root,
            "alpha_card": alpha_card,
            "validation_report": validation_report,
        }

    def _write_partitioned_rows(self, *, root: Path, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        partition_path = root / "part-000.csv.gz"
        with gzip.open(partition_path, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        manifest = {
            "contract_version": "partitioned_rows_manifest.v1",
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "partitions": [
                {
                    "path": partition_path.name,
                    "row_count": len(rows),
                    "min_open_time_ms": int(rows[0]["open_time_ms"]),
                    "max_open_time_ms": int(rows[-1]["open_time_ms"]),
                }
            ],
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
