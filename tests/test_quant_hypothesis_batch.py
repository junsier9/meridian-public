from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
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

from enhengclaw.quant_research import hypothesis_batch
from enhengclaw.quant_research.contracts import read_json, write_json
from enhengclaw.quant_research.features import (
    DEFAULT_LABEL_CONTRACT_ID,
    PARTICIPATION_DRIFT_LABEL_CONTRACT_ID,
    build_cross_sectional_feature_bundle,
    xs_contraction_release_v1_score,
    xs_contraction_release_v2_score,
    xs_contraction_release_v3_score,
    xs_contraction_release_v4_score,
    xs_contraction_release_v5_score,
    xs_absorption_recovery_v1_score,
    xs_failed_breakdown_reclaim_v1_score,
    xs_regime_switch_ranking_v1_score,
    xs_basis_funding_dislocation_v1_score,
    xs_relative_value_spread_v1_score,
    xs_relative_value_spread_v2_score,
    xs_relative_value_spread_v3_score,
    xs_relative_value_spread_v4_score,
    xs_relative_value_spread_v5_score,
    xs_relative_value_spread_v6_score,
    xs_relative_value_spread_v7_score,
    xs_relative_value_spread_v8_score,
    xs_residualized_pair_book_v1_score,
    xs_residualized_pair_book_v2_score,
    xs_pair_spread_book_v1_score,
    xs_pair_spread_book_v2_score,
    xs_pair_spread_book_v3_score,
    xs_pair_spread_book_v4_score,
    xs_pair_spread_book_v5_score,
    xs_pair_spread_book_v6_score,
    xs_pair_spread_book_v7_score,
    xs_pair_spread_book_v8_score,
    xs_pair_spread_book_v9_score,
    xs_pair_spread_book_v10_score,
    xs_pair_spread_book_v11_score,
    xs_pair_spread_book_v12_score,
    xs_pair_spread_book_v16_score,
    xs_pair_spread_book_v17_score,
    xs_pair_spread_book_v18_score,
    xs_pair_spread_book_v19_score,
    xs_pair_spread_book_v20_score,
    xs_pair_spread_book_v21_score,
    xs_pair_spread_book_v22_score,
    xs_pair_spread_book_v23_score,
    xs_pair_spread_book_v24_score,
)


class QuantHypothesisBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="quant-hypothesis-batch-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.artifacts_root = self.temp_dir / "artifacts" / "quant_research"
        self.quant_inputs_root = self.artifacts_root / "_quant_inputs"
        self.workbench_root = self.temp_dir / "artifacts" / "research_workbench"
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
        self.as_of = "2026-04-24"

    def test_manifest_loads_all_expected_candidates(self) -> None:
        manifest = hypothesis_batch.load_cross_sectional_hypothesis_batch_manifest()

        self.assertEqual(manifest["contract_version"], hypothesis_batch.HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION)
        self.assertEqual(len(manifest["entries"]), 1)
        self.assertEqual(
            {entry["candidate_id"] for entry in manifest["entries"]},
            set(hypothesis_batch.EXPECTED_CANDIDATE_IDS),
        )
        self.assertTrue(all(entry["dataset_profile"] == "cross_sectional_daily_4h" for entry in manifest["entries"]))
        self.assertEqual(
            {entry["horizon_id"] for entry in manifest["entries"]},
            set(hypothesis_batch.EXPECTED_HORIZON_MAP.keys()),
        )
        self.assertEqual(
            {int(entry["target_horizon_bars"]) for entry in manifest["entries"]},
            set(hypothesis_batch.EXPECTED_HORIZON_MAP.values()),
        )
        self.assertEqual(
            {entry["base_mechanism_id"] for entry in manifest["entries"]},
            set(hypothesis_batch.EXPECTED_BASE_MECHANISM_IDS),
        )
        self.assertEqual(
            {entry["label_contract_id"] for entry in manifest["entries"]},
            {DEFAULT_LABEL_CONTRACT_ID},
        )

    def test_mutable_manifest_globals_round_trip_through_loader(self) -> None:
        original_values = {
            name: getattr(hypothesis_batch, name)
            for name in (
                "HYPOTHESIS_BATCH_MANIFEST_PATH",
                "HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION",
                "HYPOTHESIS_BATCH_SOURCE",
                "EXPECTED_BASE_MECHANISM_IDS",
                "EXPECTED_HORIZON_SPECS",
                "EXPECTED_HORIZON_MAP",
                "EXPECTED_CANDIDATE_IDS",
                "HYPOTHESIS_BATCH_TARGET_HORIZONS",
            )
        }
        default_manifest = hypothesis_batch.load_cross_sectional_hypothesis_batch_manifest()
        candidate_id = "xs_roundtrip_mutable_global_h3d"
        base_mechanism_id = "xs_roundtrip_mutable_global"
        horizon_id = "h3d"
        target_horizon_bars = 3
        patched_contract_version = "quant_cross_sectional_hypothesis_batch_manifest.roundtrip.v1"
        patched_manifest_path = self.temp_dir / "roundtrip_manifest.json"
        patched_entry = copy.deepcopy(default_manifest["entries"][0])
        patched_entry.update(
            {
                "candidate_id": candidate_id,
                "base_mechanism_id": base_mechanism_id,
                "horizon_id": horizon_id,
                "target_horizon_bars": target_horizon_bars,
            }
        )
        patched_entry["spec_hash"] = hypothesis_batch._compute_hypothesis_candidate_spec_hash(
            candidate_id=candidate_id,
            base_mechanism_id=base_mechanism_id,
            horizon_id=horizon_id,
            target_horizon_bars=target_horizon_bars,
            label_contract_id=str(patched_entry["label_contract_id"]),
            shape=str(patched_entry["shape"]),
            dataset_profile=str(patched_entry["dataset_profile"]),
            strategy_profile=str(patched_entry["strategy_profile"]),
            universe_filter=dict(patched_entry["universe_filter"]),
            model_family=str(patched_entry["model_family"]),
            feature_groups=list(patched_entry["feature_groups"]),
            required_feature_columns=list(patched_entry["required_feature_columns"]),
            requires_derivatives_features=bool(patched_entry["requires_derivatives_features"]),
            profile_constraints=dict(patched_entry["profile_constraints"]),
            thesis_profile=dict(patched_entry["thesis_profile"]),
        )
        write_json(
            patched_manifest_path,
            {
                "contract_version": patched_contract_version,
                "entries": [patched_entry],
            },
        )

        try:
            hypothesis_batch.HYPOTHESIS_BATCH_MANIFEST_PATH = patched_manifest_path
            hypothesis_batch.HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION = patched_contract_version
            hypothesis_batch.HYPOTHESIS_BATCH_SOURCE = "roundtrip_mutable_global_manifest"
            hypothesis_batch.EXPECTED_BASE_MECHANISM_IDS = (base_mechanism_id,)
            hypothesis_batch.EXPECTED_HORIZON_SPECS = ((horizon_id, target_horizon_bars),)
            hypothesis_batch.EXPECTED_HORIZON_MAP = dict(hypothesis_batch.EXPECTED_HORIZON_SPECS)
            hypothesis_batch.EXPECTED_CANDIDATE_IDS = (candidate_id,)
            hypothesis_batch.HYPOTHESIS_BATCH_TARGET_HORIZONS = tuple(
                int(bars) for _, bars in hypothesis_batch.EXPECTED_HORIZON_SPECS
            )

            loaded_manifest = hypothesis_batch.load_cross_sectional_hypothesis_batch_manifest()

            self.assertEqual(loaded_manifest["path"], str(patched_manifest_path.resolve()))
            self.assertEqual(loaded_manifest["contract_version"], patched_contract_version)
            self.assertEqual(
                [entry["candidate_id"] for entry in loaded_manifest["entries"]],
                [candidate_id],
            )
            self.assertEqual(hypothesis_batch.EXPECTED_CANDIDATE_IDS, (candidate_id,))
            self.assertEqual(hypothesis_batch.HYPOTHESIS_BATCH_TARGET_HORIZONS, (target_horizon_bars,))
        finally:
            for name, value in original_values.items():
                setattr(hypothesis_batch, name, value)

        restored_manifest = hypothesis_batch.load_cross_sectional_hypothesis_batch_manifest()

        self.assertEqual(
            hypothesis_batch.HYPOTHESIS_BATCH_MANIFEST_PATH.name,
            "cross_sectional_hypothesis_batch_manifest_v97.json",
        )
        self.assertEqual(restored_manifest["contract_version"], default_manifest["contract_version"])
        self.assertEqual(
            {entry["candidate_id"] for entry in restored_manifest["entries"]},
            {entry["candidate_id"] for entry in default_manifest["entries"]},
        )

    def test_strict_result_payload_requires_alpha_experiment_card_go(self) -> None:
        payload = hypothesis_batch._strict_result_payload(
            as_of=self.as_of,
            report={
                "candidate_id": "candidate",
                "base_mechanism_id": "base",
                "horizon_id": "h10d",
                "target_horizon_bars": 10,
                "label_contract_id": "forward_return_execution_aligned.v1",
                "path": self.artifacts_root / "fast.json",
            },
            experiment={
                "experiment_id": "exp",
                "experiment_status": "pass",
                "alpha_card_path": str(self.artifacts_root / "alpha_card.json"),
                "validation_report_path": str(self.artifacts_root / "validation_report.json"),
                "alpha_card": {
                    "falsification_status": "cleared",
                    "credible_research_evidence": True,
                },
                "validation_report": {
                    "validation_contract": {"status": "passed"},
                    "alpha_experiment_card": {
                        "status": "no_go",
                        "go_no_go": False,
                        "blocker_codes": ["cost_stress_failed"],
                    },
                    "statistical_falsification": {
                        "status": "failed",
                        "blocker_codes": ["cost_stress_failed"],
                    },
                },
            },
        )

        self.assertFalse(payload["strict_validation_passed"])
        self.assertEqual(payload["alpha_experiment_card_status"], "no_go")
        self.assertEqual(payload["statistical_falsification_status"], "failed")

    def test_pair_book_profile_constraints_normalize_valid_quality_bucket_pair_shape(self) -> None:
        normalized = hypothesis_batch._normalize_profile_constraints(
            candidate_id="xs_pair_spread_book_v8_h5d",
            model_family="xs_pair_spread_book_v8",
            profile_constraints={
                "allowed_liquidity_buckets": ["mid_liquidity", "top_liquidity"],
                "spot_only": False,
                "long_only": False,
                "short_allowed": True,
                "execution_venue": "perp",
                "max_gross_leverage": 1.0,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "max_turnover_per_rebalance": 0.5,
                "pair_construction": "QUALITY_BUCKET_PAIRS",
                "pair_bucket_count": 4,
                "pair_count": 2,
                "pair_score_spread_min": 0.12,
                "pair_quality_floor": 0.42,
                "pair_turnover_mode": "PAIR_HOLD",
                "pair_strength_soft_cap": 0.18,
                "pair_trend_crowding_soft_threshold": 0.88,
                "pair_trend_crowding_soft_scale": 0.70,
                "pair_short_trend_crowding_soft_threshold": 0.82,
                "pair_short_trend_crowding_soft_scale": 0.65,
                "pair_short_quality_max": 0.80,
                "pair_short_quality_soft_threshold": 0.78,
                "pair_short_quality_soft_scale": 0.60,
                "pair_quality_balance_soft_floor": 0.72,
                "pair_quality_balance_soft_scale": 0.75,
                "pair_additional_strength_ratio_min": 0.60,
                "pair_switch_strength_ratio_min": 1.20,
                "pair_market_momentum_soft_threshold": 0.10,
                "pair_market_ema_soft_threshold": 0.05,
                "pair_market_trend_short_scale": 0.80,
            },
        )

        expected_values = {
            "spot_only": False,
            "long_only": False,
            "short_allowed": True,
            "execution_venue": "perp",
            "max_gross_leverage": 1.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "max_turnover_per_rebalance": 0.5,
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 4,
            "pair_count": 2,
            "pair_score_spread_min": 0.12,
            "pair_quality_floor": 0.42,
            "pair_turnover_mode": "pair_hold",
            "pair_strength_soft_cap": 0.18,
            "pair_trend_crowding_soft_threshold": 0.88,
            "pair_trend_crowding_soft_scale": 0.70,
            "pair_short_trend_crowding_soft_threshold": 0.82,
            "pair_short_trend_crowding_soft_scale": 0.65,
            "pair_short_quality_max": 0.80,
            "pair_short_quality_soft_threshold": 0.78,
            "pair_short_quality_soft_scale": 0.60,
            "pair_quality_balance_soft_floor": 0.72,
            "pair_quality_balance_soft_scale": 0.75,
            "pair_additional_strength_ratio_min": 0.60,
            "pair_switch_strength_ratio_min": 1.20,
            "pair_market_momentum_soft_threshold": 0.10,
            "pair_market_ema_soft_threshold": 0.05,
            "pair_market_trend_short_scale": 0.80,
        }
        for key, expected in expected_values.items():
            with self.subTest(key=key):
                self.assertEqual(normalized[key], expected)
        self.assertEqual(normalized["allowed_liquidity_buckets"], ["mid_liquidity", "top_liquidity"])

    def test_pair_book_profile_constraints_reject_out_of_range_stability_constraints(self) -> None:
        base_constraints = {
            "allowed_liquidity_buckets": ["mid_liquidity", "top_liquidity"],
            "spot_only": False,
            "long_only": False,
            "short_allowed": True,
            "execution_venue": "perp",
            "max_gross_leverage": 1.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "max_turnover_per_rebalance": 0.5,
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 3,
            "pair_count": 1,
            "pair_score_spread_min": 0.12,
            "pair_quality_floor": 0.35,
        }

        with self.assertRaisesRegex(ValueError, "pair_count must be 1 or 2"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_count=3),
            )

        with self.assertRaisesRegex(ValueError, "pair_strength_soft_cap"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_strength_soft_cap=0.10),
            )

        with self.assertRaisesRegex(ValueError, "pair_trend_crowding_soft_scale"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_trend_crowding_soft_scale=1.0),
            )

        with self.assertRaisesRegex(ValueError, "pair_short_trend_crowding_soft_scale"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_short_trend_crowding_soft_scale=1.0),
            )

        with self.assertRaisesRegex(ValueError, "pair_quality_balance_soft_scale"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_quality_balance_soft_scale=1.0),
            )

        with self.assertRaisesRegex(ValueError, "pair_turnover_mode"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_turnover_mode="bad_mode"),
            )

        with self.assertRaisesRegex(ValueError, "pair_short_quality_soft_scale"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_short_quality_soft_scale=1.0),
            )

        with self.assertRaisesRegex(ValueError, "pair_short_quality_max"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_short_quality_max=0.5),
            )

        with self.assertRaisesRegex(ValueError, "pair_switch_strength_ratio_min"):
            hypothesis_batch._normalize_profile_constraints(
                candidate_id="xs_pair_spread_book_v8_h5d",
                model_family="xs_pair_spread_book_v8",
                profile_constraints=dict(base_constraints, pair_switch_strength_ratio_min=1.60),
            )

    def test_feature_set_selector_uses_candidate_horizon_and_label_contract(self) -> None:
        feature_sets = [
            {
                "dataset_profile": "cross_sectional_daily_4h",
                "feature_set_id": "features-h5d",
                "target_horizon_bars": 5,
                "split_realization_contract": {"target_horizon_bars": 5},
                "label_contract_id": DEFAULT_LABEL_CONTRACT_ID,
            },
        ]

        selected = hypothesis_batch._feature_set_for_candidate(
            feature_sets=feature_sets,
            candidate_entry={
                "dataset_profile": "cross_sectional_daily_4h",
                "target_horizon_bars": 5,
                "label_contract_id": DEFAULT_LABEL_CONTRACT_ID,
            },
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["feature_set_id"], "features-h5d")

    def test_participation_drift_label_contract_builds_custom_target_columns(self) -> None:
        rows: list[dict[str, object]] = []
        for offset in range(25):
            timestamp_ms = 1_700_000_000_000 + (offset * 86_400_000)
            rows.append(
                {
                    "subject": "AAA",
                    "timestamp_ms": timestamp_ms,
                    "spot_close": 100.0 + offset,
                    "spot_high": 101.0 + offset,
                    "spot_low": 99.0 + offset,
                    "spot_quote_volume": 1_000_000.0 + (offset * 10_000.0),
                    "funding_rate": 0.0,
                    "open_interest": 10_000_000.0,
                    "basis_proxy": 0.0,
                }
            )
            rows.append(
                {
                    "subject": "BBB",
                    "timestamp_ms": timestamp_ms,
                    "spot_close": 90.0 + (offset * 0.4),
                    "spot_high": 91.0 + (offset * 0.4),
                    "spot_low": 89.0 + (offset * 0.4),
                    "spot_quote_volume": 800_000.0 + (offset * 5_000.0),
                    "funding_rate": 0.0,
                    "open_interest": 8_000_000.0,
                    "basis_proxy": 0.0,
                }
            )
        panel = pd.DataFrame(rows)

        bundle = build_cross_sectional_feature_bundle(
            panel,
            interval="1d",
            target_shift_bars=3,
            label_contract_id=PARTICIPATION_DRIFT_LABEL_CONTRACT_ID,
        )

        self.assertEqual(bundle["label_contract_id"], PARTICIPATION_DRIFT_LABEL_CONTRACT_ID)
        self.assertEqual(bundle["target_column"], "target_participation_drift_up")
        self.assertEqual(bundle["forward_return_column"], "target_participation_drift_forward_return")
        self.assertIn("target_participation_drift_forward_return", bundle["dataframe"].columns)
        self.assertIn("target_participation_drift_up", bundle["dataframe"].columns)

    def test_contraction_release_prefers_orderly_squeeze_near_highs(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.8,
                    "ema_slope_5_20": 0.6,
                    "quote_volume_expansion": 1.2,
                    "realized_volatility_20": 0.03,
                    "atr_proxy_20": 0.02,
                    "range_position_20": 0.77,
                    "distance_to_high_20": -0.03,
                    "momentum_5": 0.02,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.1,
                    "ema_slope_5_20": 0.05,
                    "quote_volume_expansion": 2.4,
                    "realized_volatility_20": 0.12,
                    "atr_proxy_20": 0.10,
                    "range_position_20": 0.98,
                    "distance_to_high_20": -0.001,
                    "momentum_5": 0.08,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.5,
                    "ema_slope_5_20": 0.3,
                    "quote_volume_expansion": 0.9,
                    "realized_volatility_20": 0.05,
                    "atr_proxy_20": 0.04,
                    "range_position_20": 0.58,
                    "distance_to_high_20": -0.12,
                    "momentum_5": -0.01,
                },
            ]
        )

        scores = xs_contraction_release_v1_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[2])), 1.0)

    def test_contraction_release_v2_compresses_overheated_tail(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.9,
                    "ema_slope_5_20": 0.7,
                    "quote_volume_expansion": 1.18,
                    "realized_volatility_20": 0.03,
                    "atr_proxy_20": 0.02,
                    "range_position_20": 0.78,
                    "distance_to_high_20": -0.03,
                    "momentum_5": 0.03,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 1.6,
                    "ema_slope_5_20": 1.2,
                    "quote_volume_expansion": 2.5,
                    "realized_volatility_20": 0.12,
                    "atr_proxy_20": 0.10,
                    "range_position_20": 0.97,
                    "distance_to_high_20": -0.001,
                    "momentum_5": 0.14,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.5,
                    "ema_slope_5_20": 0.3,
                    "quote_volume_expansion": 1.0,
                    "realized_volatility_20": 0.06,
                    "atr_proxy_20": 0.05,
                    "range_position_20": 0.63,
                    "distance_to_high_20": -0.08,
                    "momentum_5": 0.01,
                },
            ]
        )

        scores = xs_contraction_release_v2_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(float(scores.iloc[1]), 0.5)

    def test_contraction_release_v3_prioritizes_rank_stability_over_tail_extremes(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.95,
                    "ema_slope_5_20": 0.72,
                    "quote_volume_expansion": 1.18,
                    "realized_volatility_20": 0.03,
                    "atr_proxy_20": 0.02,
                    "range_position_20": 0.78,
                    "distance_to_high_20": -0.03,
                    "momentum_5": 0.03,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 1.70,
                    "ema_slope_5_20": 1.25,
                    "quote_volume_expansion": 2.60,
                    "realized_volatility_20": 0.14,
                    "atr_proxy_20": 0.11,
                    "range_position_20": 0.98,
                    "distance_to_high_20": -0.001,
                    "momentum_5": 0.15,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.60,
                    "ema_slope_5_20": 0.40,
                    "quote_volume_expansion": 1.05,
                    "realized_volatility_20": 0.05,
                    "atr_proxy_20": 0.04,
                    "range_position_20": 0.72,
                    "distance_to_high_20": -0.05,
                    "momentum_5": 0.01,
                },
            ]
        )

        scores = xs_contraction_release_v3_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_contraction_release_v4_prefers_balanced_release_over_overheated_tail(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.95,
                    "ema_slope_5_20": 0.70,
                    "quote_volume_expansion": 1.14,
                    "realized_volatility_20": 0.03,
                    "atr_proxy_20": 0.02,
                    "range_position_20": 0.75,
                    "distance_to_high_20": -0.04,
                    "momentum_5": 0.03,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 1.70,
                    "ema_slope_5_20": 1.20,
                    "quote_volume_expansion": 2.35,
                    "realized_volatility_20": 0.14,
                    "atr_proxy_20": 0.11,
                    "range_position_20": 0.98,
                    "distance_to_high_20": -0.002,
                    "momentum_5": 0.15,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.58,
                    "ema_slope_5_20": 0.40,
                    "quote_volume_expansion": 0.92,
                    "realized_volatility_20": 0.05,
                    "atr_proxy_20": 0.04,
                    "range_position_20": 0.64,
                    "distance_to_high_20": -0.10,
                    "momentum_5": 0.01,
                },
            ]
        )

        scores = xs_contraction_release_v4_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_contraction_release_v5_prefers_calm_drift_after_release(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.95,
                    "ema_slope_5_20": 0.70,
                    "quote_volume_expansion": 1.12,
                    "realized_volatility_20": 0.03,
                    "atr_proxy_20": 0.02,
                    "range_position_20": 0.75,
                    "distance_to_high_20": -0.04,
                    "momentum_5": 0.012,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 1.55,
                    "ema_slope_5_20": 1.15,
                    "quote_volume_expansion": 1.75,
                    "realized_volatility_20": 0.11,
                    "atr_proxy_20": 0.09,
                    "range_position_20": 0.95,
                    "distance_to_high_20": -0.005,
                    "momentum_5": 0.12,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.55,
                    "ema_slope_5_20": 0.36,
                    "quote_volume_expansion": 0.95,
                    "realized_volatility_20": 0.05,
                    "atr_proxy_20": 0.04,
                    "range_position_20": 0.64,
                    "distance_to_high_20": -0.09,
                    "momentum_5": 0.0,
                },
            ]
        )

        scores = xs_contraction_release_v5_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_absorption_recovery_prefers_orderly_reset_over_hot_breakout(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.88,
                    "ema_slope_5_20": 0.58,
                    "intraday_realized_vol_4h_to_1d": 0.42,
                    "realized_volatility_20": 0.03,
                    "atr_proxy_20": 0.02,
                    "quote_volume_expansion": 1.08,
                    "range_position_20": 0.40,
                    "distance_to_low_20": -0.05,
                    "return_1": -0.012,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 1.35,
                    "ema_slope_5_20": 1.05,
                    "intraday_realized_vol_4h_to_1d": 1.10,
                    "realized_volatility_20": 0.11,
                    "atr_proxy_20": 0.09,
                    "quote_volume_expansion": 1.85,
                    "range_position_20": 0.94,
                    "distance_to_low_20": -0.28,
                    "return_1": 0.055,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.30,
                    "ema_slope_5_20": 0.15,
                    "intraday_realized_vol_4h_to_1d": 0.55,
                    "realized_volatility_20": 0.06,
                    "atr_proxy_20": 0.05,
                    "quote_volume_expansion": 0.92,
                    "range_position_20": 0.30,
                    "distance_to_low_20": -0.02,
                    "return_1": -0.045,
                },
            ]
        )

        scores = xs_absorption_recovery_v1_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_failed_breakdown_reclaim_prefers_support_reclaim_over_capitulation(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.85,
                    "ema_slope_5_20": 0.55,
                    "intraday_realized_vol_4h_to_1d": 0.45,
                    "realized_volatility_20": 0.03,
                    "quote_volume_expansion": 1.08,
                    "range_position_20": 0.52,
                    "distance_to_low_20": 0.08,
                    "distance_to_low_60": 0.22,
                    "return_1": 0.012,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.40,
                    "ema_slope_5_20": 0.12,
                    "intraday_realized_vol_4h_to_1d": 1.15,
                    "realized_volatility_20": 0.12,
                    "quote_volume_expansion": 1.80,
                    "range_position_20": 0.18,
                    "distance_to_low_20": 0.01,
                    "distance_to_low_60": 0.04,
                    "return_1": -0.08,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.62,
                    "ema_slope_5_20": 0.34,
                    "intraday_realized_vol_4h_to_1d": 0.62,
                    "realized_volatility_20": 0.05,
                    "quote_volume_expansion": 0.95,
                    "range_position_20": 0.40,
                    "distance_to_low_20": 0.04,
                    "distance_to_low_60": 0.16,
                    "return_1": 0.002,
                },
            ]
        )

        scores = xs_failed_breakdown_reclaim_v1_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_regime_switch_ranking_changes_leg_by_state(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.92,
                    "ema_slope_5_20": 0.66,
                    "intraday_realized_vol_4h_to_1d": 0.35,
                    "realized_volatility_20": 0.03,
                    "quote_volume_expansion": 1.08,
                    "range_position_20": 0.68,
                    "distance_to_high_20": -0.05,
                    "distance_to_low_20": 0.12,
                    "return_1": 0.01,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 0.86,
                    "ema_slope_5_20": 0.55,
                    "intraday_realized_vol_4h_to_1d": 0.65,
                    "realized_volatility_20": 0.05,
                    "quote_volume_expansion": 1.10,
                    "range_position_20": 0.50,
                    "distance_to_high_20": -0.16,
                    "distance_to_low_20": 0.08,
                    "return_1": 0.012,
                },
                {
                    "timestamp_ms": 1,
                    "relative_strength_20": 1.20,
                    "ema_slope_5_20": 0.98,
                    "intraday_realized_vol_4h_to_1d": 1.10,
                    "realized_volatility_20": 0.12,
                    "quote_volume_expansion": 1.85,
                    "range_position_20": 0.92,
                    "distance_to_high_20": -0.01,
                    "distance_to_low_20": 0.30,
                    "return_1": 0.055,
                },
            ]
        )

        scores = xs_regime_switch_ranking_v1_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertGreater(float(scores.iloc[1]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[2])), 1.0)

    def test_basis_funding_dislocation_prefers_orderly_negative_dislocation(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.3,
                    "funding_zscore_20": -1.1,
                    "oi_change_5": 0.03,
                    "relative_strength_20": 0.45,
                    "quote_volume_expansion": 1.08,
                    "realized_volatility_20": 0.04,
                    "return_1": -0.01,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": 1.0,
                    "funding_zscore_20": 0.9,
                    "oi_change_5": 0.22,
                    "relative_strength_20": 0.60,
                    "quote_volume_expansion": 1.55,
                    "realized_volatility_20": 0.10,
                    "return_1": 0.06,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -0.3,
                    "funding_zscore_20": -0.2,
                    "oi_change_5": 0.28,
                    "relative_strength_20": 0.10,
                    "quote_volume_expansion": 0.86,
                    "realized_volatility_20": 0.08,
                    "return_1": -0.08,
                },
            ]
        )

        scores = xs_basis_funding_dislocation_v1_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_relative_value_spread_prefers_derivatives_cheap_but_spot_intact(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.20,
                    "funding_zscore_20": -0.95,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.42,
                    "ema_slope_5_20": 0.24,
                    "quote_volume_expansion": 1.08,
                    "intraday_realized_vol_4h_to_1d": 0.35,
                    "realized_volatility_20": 0.04,
                    "distance_to_low_20": 0.12,
                    "return_1": -0.01,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.05,
                    "funding_zscore_20": -0.90,
                    "oi_change_5": 0.30,
                    "relative_strength_20": -0.25,
                    "ema_slope_5_20": -0.10,
                    "quote_volume_expansion": 1.55,
                    "intraday_realized_vol_4h_to_1d": 0.95,
                    "realized_volatility_20": 0.11,
                    "distance_to_low_20": -0.06,
                    "return_1": -0.09,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": 0.80,
                    "funding_zscore_20": 0.75,
                    "oi_change_5": 0.08,
                    "relative_strength_20": 0.48,
                    "ema_slope_5_20": 0.26,
                    "quote_volume_expansion": 1.02,
                    "intraday_realized_vol_4h_to_1d": 0.32,
                    "realized_volatility_20": 0.04,
                    "distance_to_low_20": 0.14,
                    "return_1": 0.02,
                },
            ]
        )

        scores = xs_relative_value_spread_v1_score(frame)

        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[1]))
        self.assertGreater(float(scores.iloc[0]), float(scores.iloc[2]))
        self.assertLess(abs(float(scores.iloc[1])), 1.0)

    def test_pair_spread_book_v8_adds_tiny_near_high_tiebreaker(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.25,
                    "funding_zscore_20": -1.00,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.48,
                    "ema_slope_5_20": 0.26,
                    "quote_volume_expansion": 1.05,
                    "intraday_realized_vol_4h_to_1d": 0.30,
                    "realized_volatility_20": 0.04,
                    "distance_to_low_20": 0.14,
                    "return_1": -0.01,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -0.40,
                    "funding_zscore_20": -0.30,
                    "oi_change_5": 0.03,
                    "relative_strength_20": 0.46,
                    "ema_slope_5_20": 0.25,
                    "quote_volume_expansion": 1.06,
                    "intraday_realized_vol_4h_to_1d": 0.31,
                    "realized_volatility_20": 0.04,
                    "distance_to_low_20": 0.13,
                    "return_1": -0.008,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.20,
                    "funding_zscore_20": -0.95,
                    "oi_change_5": 0.28,
                    "relative_strength_20": -0.22,
                    "ema_slope_5_20": -0.08,
                    "quote_volume_expansion": 1.50,
                    "intraday_realized_vol_4h_to_1d": 0.92,
                    "realized_volatility_20": 0.11,
                    "distance_to_low_20": -0.05,
                    "return_1": -0.08,
                },
            ]
        )

        v1_scores = xs_pair_spread_book_v1_score(frame)
        v2_scores = xs_pair_spread_book_v2_score(frame)
        v3_scores = xs_pair_spread_book_v3_score(frame)
        v4_scores = xs_pair_spread_book_v4_score(frame)
        v5_scores = xs_pair_spread_book_v5_score(frame)
        v6_scores = xs_pair_spread_book_v6_score(frame)
        v7_scores = xs_pair_spread_book_v7_score(frame)
        v8_scores = xs_pair_spread_book_v8_score(frame)
        v9_scores = xs_pair_spread_book_v9_score(frame)
        v10_scores = xs_pair_spread_book_v10_score(frame)
        v11_scores = xs_pair_spread_book_v11_score(frame)
        v12_scores = xs_pair_spread_book_v12_score(frame)

        self.assertAlmostEqual(float(v2_scores.iloc[0]), -float(v1_scores.iloc[0]), places=9)
        self.assertAlmostEqual(float(v2_scores.iloc[1]), -float(v1_scores.iloc[1]), places=9)
        self.assertAlmostEqual(float(v2_scores.iloc[2]), -float(v1_scores.iloc[2]), places=9)
        self.assertFalse(v3_scores.equals(v2_scores))
        self.assertLess(float(v3_scores.abs().max()), float(v2_scores.abs().max()))
        self.assertGreater(float(v3_scores.iloc[0]), 0.0)
        self.assertFalse(v4_scores.equals(v3_scores))
        self.assertLess(float(v4_scores.abs().max()), float(v3_scores.abs().max()))
        self.assertGreater(float(v4_scores.iloc[0]), 0.0)
        self.assertFalse(v5_scores.equals(v3_scores))
        self.assertLess(float(v5_scores.abs().max()), float(v3_scores.abs().max()))
        self.assertGreater(float(v5_scores.iloc[0]), 0.0)
        self.assertFalse(v6_scores.equals(v3_scores))
        self.assertGreater(float(v6_scores.iloc[0]), 0.0)
        self.assertFalse(v7_scores.equals(v3_scores))
        self.assertGreater(float(v7_scores.iloc[0]), 0.0)
        self.assertFalse(v8_scores.equals(v3_scores))
        self.assertGreater(float(v8_scores.iloc[0]), 0.0)
        self.assertFalse(v9_scores.equals(v8_scores))
        self.assertGreater(float(v9_scores.iloc[0]), 0.0)
        self.assertTrue(v10_scores.equals(v8_scores))
        self.assertTrue(v11_scores.equals(v8_scores))
        self.assertTrue(v12_scores.equals(v8_scores))

    def test_pair_spread_book_v16_v24_aliases_match_v8(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.25,
                    "funding_zscore_20": -1.00,
                    "basis_proxy": -0.030,
                    "funding_rate": -0.012,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.48,
                    "ema_slope_5_20": 0.26,
                    "quote_volume_expansion": 1.05,
                    "intraday_realized_vol_4h_to_1d": 0.30,
                    "realized_volatility_20": 0.04,
                    "distance_to_low_20": 0.14,
                    "distance_to_high_20": -0.02,
                    "return_1": -0.01,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -0.40,
                    "funding_zscore_20": -0.30,
                    "basis_proxy": -0.009,
                    "funding_rate": -0.003,
                    "oi_change_5": 0.03,
                    "relative_strength_20": 0.46,
                    "ema_slope_5_20": 0.25,
                    "quote_volume_expansion": 1.06,
                    "intraday_realized_vol_4h_to_1d": 0.31,
                    "realized_volatility_20": 0.04,
                    "distance_to_low_20": 0.13,
                    "distance_to_high_20": -0.03,
                    "return_1": -0.008,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.20,
                    "funding_zscore_20": -0.95,
                    "basis_proxy": -0.028,
                    "funding_rate": -0.011,
                    "oi_change_5": 0.28,
                    "relative_strength_20": -0.22,
                    "ema_slope_5_20": -0.08,
                    "quote_volume_expansion": 1.50,
                    "intraday_realized_vol_4h_to_1d": 0.92,
                    "realized_volatility_20": 0.11,
                    "distance_to_low_20": -0.05,
                    "distance_to_high_20": -0.18,
                    "return_1": -0.08,
                },
            ],
            index=["clean_cheap", "near_cheap", "broken_cheap"],
        )
        expected_scores = xs_pair_spread_book_v8_score(frame)

        for scorer in (
            xs_pair_spread_book_v16_score,
            xs_pair_spread_book_v17_score,
            xs_pair_spread_book_v18_score,
            xs_pair_spread_book_v19_score,
            xs_pair_spread_book_v20_score,
            xs_pair_spread_book_v21_score,
            xs_pair_spread_book_v22_score,
            xs_pair_spread_book_v23_score,
            xs_pair_spread_book_v24_score,
        ):
            with self.subTest(scorer=scorer.__name__):
                scores = scorer(frame)

                self.assertTrue(scores.index.equals(frame.index))
                self.assertEqual(len(scores), len(frame))
                self.assertEqual(str(scores.dtype), "float64")
                self.assertTrue(scores.equals(expected_scores))

    def test_relative_value_spread_v2_score_is_distinct_and_prefers_cheap_quality_names(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.030,
                    "funding_rate": -0.012,
                    "oi_change_5": 0.04,
                    "relative_strength_20": 0.44,
                    "ema_slope_5_20": 0.24,
                    "quote_volume_expansion": 1.04,
                    "intraday_realized_vol_4h_to_1d": 0.18,
                    "realized_volatility_20": 0.05,
                    "distance_to_low_20": 0.12,
                    "return_1": -0.006,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.010,
                    "funding_rate": -0.004,
                    "oi_change_5": 0.18,
                    "relative_strength_20": 0.10,
                    "ema_slope_5_20": 0.06,
                    "quote_volume_expansion": 1.18,
                    "intraday_realized_vol_4h_to_1d": 0.42,
                    "realized_volatility_20": 0.10,
                    "distance_to_low_20": 0.03,
                    "return_1": 0.008,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": 0.012,
                    "funding_rate": 0.006,
                    "oi_change_5": 0.30,
                    "relative_strength_20": -0.08,
                    "ema_slope_5_20": -0.04,
                    "quote_volume_expansion": 1.42,
                    "intraday_realized_vol_4h_to_1d": 0.88,
                    "realized_volatility_20": 0.14,
                    "distance_to_low_20": -0.04,
                    "return_1": 0.032,
                },
            ]
        )

        v1_scores = xs_relative_value_spread_v1_score(
            frame.rename(columns={"basis_proxy": "basis_zscore_20", "funding_rate": "funding_zscore_20"})
        )
        v2_scores = xs_relative_value_spread_v2_score(frame)

        self.assertFalse(v2_scores.equals(v1_scores))
        self.assertGreater(float(v2_scores.iloc[0]), float(v2_scores.iloc[1]))
        self.assertGreater(float(v2_scores.iloc[1]), float(v2_scores.iloc[2]))
        self.assertGreater(float(v2_scores.iloc[0]), 0.0)
        self.assertLess(float(v2_scores.iloc[2]), 0.0)

    def test_relative_value_spread_v3_score_penalizes_extreme_capitulation(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.020,
                    "funding_rate": -0.008,
                    "basis_zscore_20": -1.05,
                    "funding_zscore_20": -0.88,
                    "oi_change_5": 0.04,
                    "relative_strength_20": 0.34,
                    "ema_slope_5_20": 0.18,
                    "quote_volume_expansion": 1.03,
                    "intraday_realized_vol_4h_to_1d": 0.22,
                    "realized_volatility_20": 0.06,
                    "distance_to_low_20": 0.11,
                    "return_1": -0.004,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.055,
                    "funding_rate": -0.020,
                    "basis_zscore_20": -2.80,
                    "funding_zscore_20": -2.20,
                    "oi_change_5": 0.26,
                    "relative_strength_20": 0.08,
                    "ema_slope_5_20": 0.02,
                    "quote_volume_expansion": 1.36,
                    "intraday_realized_vol_4h_to_1d": 0.82,
                    "realized_volatility_20": 0.15,
                    "distance_to_low_20": 0.01,
                    "return_1": -0.034,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": 0.010,
                    "funding_rate": 0.004,
                    "basis_zscore_20": 0.65,
                    "funding_zscore_20": 0.50,
                    "oi_change_5": 0.15,
                    "relative_strength_20": -0.06,
                    "ema_slope_5_20": -0.03,
                    "quote_volume_expansion": 1.10,
                    "intraday_realized_vol_4h_to_1d": 0.28,
                    "realized_volatility_20": 0.08,
                    "distance_to_low_20": -0.02,
                    "return_1": 0.010,
                },
            ]
        )

        v2_scores = xs_relative_value_spread_v2_score(frame.drop(columns=["basis_zscore_20", "funding_zscore_20"]))
        v3_scores = xs_relative_value_spread_v3_score(frame)

        self.assertFalse(v3_scores.equals(v2_scores))
        self.assertGreater(float(v3_scores.iloc[0]), float(v3_scores.iloc[1]))
        self.assertGreater(float(v3_scores.iloc[0]), 0.0)
        self.assertLess(float(v3_scores.iloc[1]), 0.0)

    def test_relative_value_spread_v4_score_prefers_cheap_leaders_over_capitulation(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.018,
                    "funding_rate": -0.007,
                    "basis_zscore_20": -0.95,
                    "funding_zscore_20": -0.82,
                    "oi_change_5": 0.03,
                    "relative_strength_20": 0.36,
                    "ema_slope_5_20": 0.20,
                    "momentum_20": 0.18,
                    "quote_volume_expansion": 1.03,
                    "intraday_realized_vol_4h_to_1d": 0.20,
                    "realized_volatility_20": 0.06,
                    "distance_to_low_20": 0.10,
                    "distance_to_high_20": -0.03,
                    "return_1": 0.001,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.056,
                    "funding_rate": -0.021,
                    "basis_zscore_20": -2.90,
                    "funding_zscore_20": -2.35,
                    "oi_change_5": 0.28,
                    "relative_strength_20": 0.02,
                    "ema_slope_5_20": 0.01,
                    "momentum_20": -0.04,
                    "quote_volume_expansion": 1.42,
                    "intraday_realized_vol_4h_to_1d": 0.90,
                    "realized_volatility_20": 0.16,
                    "distance_to_low_20": 0.00,
                    "distance_to_high_20": -0.18,
                    "return_1": -0.036,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": 0.008,
                    "funding_rate": 0.003,
                    "basis_zscore_20": 0.55,
                    "funding_zscore_20": 0.46,
                    "oi_change_5": 0.14,
                    "relative_strength_20": -0.10,
                    "ema_slope_5_20": -0.05,
                    "momentum_20": -0.02,
                    "quote_volume_expansion": 1.10,
                    "intraday_realized_vol_4h_to_1d": 0.26,
                    "realized_volatility_20": 0.08,
                    "distance_to_low_20": -0.03,
                    "distance_to_high_20": -0.12,
                    "return_1": 0.009,
                },
            ]
        )

        v3_scores = xs_relative_value_spread_v3_score(frame.drop(columns=["momentum_20", "distance_to_high_20"]))
        v4_scores = xs_relative_value_spread_v4_score(frame)

        self.assertFalse(v4_scores.equals(v3_scores))
        self.assertGreater(float(v4_scores.iloc[0]), float(v4_scores.iloc[1]))
        self.assertGreater(float(v4_scores.iloc[0]), float(v4_scores.iloc[2]))
        self.assertGreater(float(v4_scores.iloc[0]), 0.0)
        self.assertLess(float(v4_scores.iloc[1]), 0.0)

    def test_relative_value_spread_v5_score_favors_light_discount_leaders(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.012,
                    "funding_rate": -0.004,
                    "basis_zscore_20": -0.55,
                    "funding_zscore_20": -0.42,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.38,
                    "ema_slope_5_20": 0.22,
                    "momentum_20": 0.21,
                    "quote_volume_expansion": 1.02,
                    "intraday_realized_vol_4h_to_1d": 0.18,
                    "realized_volatility_20": 0.05,
                    "distance_to_low_20": 0.11,
                    "distance_to_high_20": -0.02,
                    "return_1": 0.002,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.054,
                    "funding_rate": -0.020,
                    "basis_zscore_20": -2.70,
                    "funding_zscore_20": -2.10,
                    "oi_change_5": 0.28,
                    "relative_strength_20": 0.04,
                    "ema_slope_5_20": 0.02,
                    "momentum_20": -0.02,
                    "quote_volume_expansion": 1.38,
                    "intraday_realized_vol_4h_to_1d": 0.86,
                    "realized_volatility_20": 0.15,
                    "distance_to_low_20": 0.01,
                    "distance_to_high_20": -0.17,
                    "return_1": -0.030,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": 0.010,
                    "funding_rate": 0.005,
                    "basis_zscore_20": 0.70,
                    "funding_zscore_20": 0.58,
                    "oi_change_5": 0.14,
                    "relative_strength_20": -0.08,
                    "ema_slope_5_20": -0.04,
                    "momentum_20": -0.03,
                    "quote_volume_expansion": 1.10,
                    "intraday_realized_vol_4h_to_1d": 0.24,
                    "realized_volatility_20": 0.08,
                    "distance_to_low_20": -0.02,
                    "distance_to_high_20": -0.10,
                    "return_1": 0.010,
                },
            ]
        )

        v4_scores = xs_relative_value_spread_v4_score(frame)
        v5_scores = xs_relative_value_spread_v5_score(frame)

        self.assertFalse(v5_scores.equals(v4_scores))
        self.assertGreater(float(v5_scores.iloc[0]), float(v5_scores.iloc[1]))
        self.assertGreater(float(v5_scores.iloc[0]), float(v5_scores.iloc[2]))
        self.assertGreater(float(v5_scores.iloc[1]), float(v5_scores.iloc[2]))
        self.assertGreater(float(v5_scores.iloc[0]), 0.0)

    def test_relative_value_spread_v6_score_narrows_discount_and_keeps_leadership_first(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.010,
                    "funding_rate": -0.003,
                    "basis_zscore_20": -0.42,
                    "funding_zscore_20": -0.35,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.40,
                    "ema_slope_5_20": 0.24,
                    "momentum_20": 0.23,
                    "quote_volume_expansion": 1.01,
                    "intraday_realized_vol_4h_to_1d": 0.16,
                    "realized_volatility_20": 0.05,
                    "distance_to_low_20": 0.12,
                    "distance_to_high_20": -0.02,
                    "return_1": 0.003,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.050,
                    "funding_rate": -0.018,
                    "basis_zscore_20": -2.40,
                    "funding_zscore_20": -1.95,
                    "oi_change_5": 0.26,
                    "relative_strength_20": 0.06,
                    "ema_slope_5_20": 0.03,
                    "momentum_20": -0.01,
                    "quote_volume_expansion": 1.34,
                    "intraday_realized_vol_4h_to_1d": 0.80,
                    "realized_volatility_20": 0.14,
                    "distance_to_low_20": 0.02,
                    "distance_to_high_20": -0.15,
                    "return_1": -0.024,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": 0.012,
                    "funding_rate": 0.006,
                    "basis_zscore_20": 0.72,
                    "funding_zscore_20": 0.62,
                    "oi_change_5": 0.14,
                    "relative_strength_20": -0.10,
                    "ema_slope_5_20": -0.05,
                    "momentum_20": -0.04,
                    "quote_volume_expansion": 1.12,
                    "intraday_realized_vol_4h_to_1d": 0.26,
                    "realized_volatility_20": 0.08,
                    "distance_to_low_20": -0.03,
                    "distance_to_high_20": -0.11,
                    "return_1": 0.010,
                },
            ]
        )

        v5_scores = xs_relative_value_spread_v5_score(frame)
        v6_scores = xs_relative_value_spread_v6_score(frame)

        self.assertFalse(v6_scores.equals(v5_scores))
        self.assertGreater(float(v6_scores.iloc[0]), float(v6_scores.iloc[1]))
        self.assertGreater(float(v6_scores.iloc[0]), float(v6_scores.iloc[2]))
        self.assertGreater(float(v6_scores.iloc[1]), float(v6_scores.iloc[2]))
        self.assertGreater(float(v6_scores.iloc[0]), 0.0)

    def test_relative_value_spread_v7_score_prefers_leader_reset_window_over_froth(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.008,
                    "funding_rate": -0.002,
                    "basis_zscore_20": -0.20,
                    "funding_zscore_20": -0.16,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.39,
                    "ema_slope_5_20": 0.24,
                    "momentum_20": 0.21,
                    "quote_volume_expansion": 1.02,
                    "intraday_realized_vol_4h_to_1d": 0.15,
                    "realized_volatility_20": 0.05,
                    "distance_to_low_20": 0.11,
                    "distance_to_high_20": -0.03,
                    "return_1": 0.001,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.010,
                    "funding_rate": -0.003,
                    "basis_zscore_20": -0.24,
                    "funding_zscore_20": -0.18,
                    "oi_change_5": 0.06,
                    "relative_strength_20": 0.41,
                    "ema_slope_5_20": 0.25,
                    "momentum_20": 0.24,
                    "quote_volume_expansion": 1.22,
                    "intraday_realized_vol_4h_to_1d": 0.34,
                    "realized_volatility_20": 0.09,
                    "distance_to_low_20": 0.04,
                    "distance_to_high_20": 0.00,
                    "return_1": 0.018,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.044,
                    "funding_rate": -0.016,
                    "basis_zscore_20": -2.05,
                    "funding_zscore_20": -1.82,
                    "oi_change_5": 0.22,
                    "relative_strength_20": 0.05,
                    "ema_slope_5_20": 0.01,
                    "momentum_20": -0.02,
                    "quote_volume_expansion": 1.29,
                    "intraday_realized_vol_4h_to_1d": 0.74,
                    "realized_volatility_20": 0.13,
                    "distance_to_low_20": 0.01,
                    "distance_to_high_20": -0.19,
                    "return_1": -0.020,
                },
            ]
        )

        v6_scores = xs_relative_value_spread_v6_score(frame)
        v7_scores = xs_relative_value_spread_v7_score(frame)

        self.assertFalse(v7_scores.equals(v6_scores))
        self.assertGreater(float(v7_scores.iloc[0]), float(v7_scores.iloc[1]))
        self.assertGreater(float(v7_scores.iloc[0]), float(v7_scores.iloc[2]))
        self.assertGreater(float(v7_scores.iloc[1]), float(v7_scores.iloc[2]))
        self.assertGreater(float(v7_scores.iloc[0]), 0.0)
        self.assertLess(float(v7_scores.iloc[2]), 0.0)

    def test_relative_value_spread_v8_score_demotes_frothy_leaders_vs_v7(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.008,
                    "funding_rate": -0.002,
                    "basis_zscore_20": -0.20,
                    "funding_zscore_20": -0.16,
                    "oi_change_5": 0.02,
                    "relative_strength_20": 0.39,
                    "ema_slope_5_20": 0.24,
                    "momentum_20": 0.21,
                    "quote_volume_expansion": 1.02,
                    "intraday_realized_vol_4h_to_1d": 0.15,
                    "realized_volatility_20": 0.05,
                    "distance_to_low_20": 0.11,
                    "distance_to_high_20": -0.03,
                    "return_1": 0.001,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.009,
                    "funding_rate": -0.002,
                    "basis_zscore_20": -0.22,
                    "funding_zscore_20": -0.18,
                    "oi_change_5": 0.05,
                    "relative_strength_20": 0.43,
                    "ema_slope_5_20": 0.28,
                    "momentum_20": 0.27,
                    "quote_volume_expansion": 1.18,
                    "intraday_realized_vol_4h_to_1d": 0.30,
                    "realized_volatility_20": 0.08,
                    "distance_to_low_20": 0.06,
                    "distance_to_high_20": -0.002,
                    "return_1": 0.016,
                },
                {
                    "timestamp_ms": 1,
                    "basis_proxy": -0.044,
                    "funding_rate": -0.016,
                    "basis_zscore_20": -2.05,
                    "funding_zscore_20": -1.82,
                    "oi_change_5": 0.22,
                    "relative_strength_20": 0.05,
                    "ema_slope_5_20": 0.01,
                    "momentum_20": -0.02,
                    "quote_volume_expansion": 1.29,
                    "intraday_realized_vol_4h_to_1d": 0.74,
                    "realized_volatility_20": 0.13,
                    "distance_to_low_20": 0.01,
                    "distance_to_high_20": -0.19,
                    "return_1": -0.020,
                },
            ]
        )

        v7_scores = xs_relative_value_spread_v7_score(frame)
        v8_scores = xs_relative_value_spread_v8_score(frame)

        self.assertFalse(v8_scores.equals(v7_scores))
        self.assertGreater(float(v8_scores.iloc[0]), float(v8_scores.iloc[1]))
        self.assertGreater(float(v8_scores.iloc[0]), float(v8_scores.iloc[2]))
        self.assertLess(float(v8_scores.iloc[1]), float(v7_scores.iloc[1]))

    def test_residualized_pair_book_scores_prefer_clean_cheap_over_broken_cheap(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.20,
                    "funding_zscore_20": -0.95,
                    "basis_proxy": -0.030,
                    "funding_rate": -0.012,
                    "oi_change_5": 0.03,
                    "relative_strength_20": 0.46,
                    "ema_slope_5_20": 0.24,
                    "distance_to_low_20": 0.12,
                    "realized_volatility_20": 0.04,
                    "intraday_realized_vol_4h_to_1d": 0.18,
                    "quote_volume_expansion": 1.05,
                    "return_1": -0.010,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -1.10,
                    "funding_zscore_20": -0.88,
                    "basis_proxy": -0.028,
                    "funding_rate": -0.011,
                    "oi_change_5": 0.30,
                    "relative_strength_20": -0.28,
                    "ema_slope_5_20": -0.14,
                    "distance_to_low_20": -0.05,
                    "realized_volatility_20": 0.14,
                    "intraday_realized_vol_4h_to_1d": 0.92,
                    "quote_volume_expansion": 1.48,
                    "return_1": -0.080,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": 0.70,
                    "funding_zscore_20": 0.55,
                    "basis_proxy": 0.012,
                    "funding_rate": 0.006,
                    "oi_change_5": 0.06,
                    "relative_strength_20": 0.50,
                    "ema_slope_5_20": 0.26,
                    "distance_to_low_20": 0.14,
                    "realized_volatility_20": 0.05,
                    "intraday_realized_vol_4h_to_1d": 0.20,
                    "quote_volume_expansion": 1.02,
                    "return_1": 0.006,
                },
                {
                    "timestamp_ms": 1,
                    "basis_zscore_20": -0.20,
                    "funding_zscore_20": -0.12,
                    "basis_proxy": -0.004,
                    "funding_rate": -0.002,
                    "oi_change_5": 0.05,
                    "relative_strength_20": 0.16,
                    "ema_slope_5_20": 0.08,
                    "distance_to_low_20": 0.06,
                    "realized_volatility_20": 0.07,
                    "intraday_realized_vol_4h_to_1d": 0.28,
                    "quote_volume_expansion": 1.04,
                    "return_1": -0.004,
                },
            ],
            index=["clean_cheap", "broken_cheap", "expensive_quality", "neutral"],
        )

        for scorer in (xs_residualized_pair_book_v1_score, xs_residualized_pair_book_v2_score):
            with self.subTest(scorer=scorer.__name__):
                scores = scorer(frame)

                self.assertTrue(scores.index.equals(frame.index))
                self.assertEqual(len(scores), len(frame))
                self.assertEqual(str(scores.dtype), "float64")
                self.assertTrue(bool(scores.between(-1.0, 1.0).all()))
                self.assertGreater(float(scores.loc["clean_cheap"]), float(scores.loc["broken_cheap"]))

    def test_fast_reject_contract_rejects_strict_only_sections(self) -> None:
        contract_path = self.temp_dir / "fast_reject_contract.json"
        write_json(
            contract_path,
            {
                "contract_version": hypothesis_batch.FAST_REJECT_CONTRACT_VERSION,
                "factor_evidence_lite": {},
                "walk_forward_assessment_lite": {},
                "regime_holdout_lite": {},
                "execution_stress": {},
            },
        )

        with self.assertRaises(ValueError):
            hypothesis_batch.load_fast_reject_contract(path=contract_path)

    def test_batch_cycle_runs_fast_reject_for_all_candidates_and_strict_for_passers_only(self) -> None:
        manifest = hypothesis_batch.load_cross_sectional_hypothesis_batch_manifest()
        active_entry = manifest["entries"][0]
        active_candidate_id = str(active_entry["candidate_id"])
        active_base_mechanism_id = str(active_entry["base_mechanism_id"])
        active_horizon_id = str(active_entry["horizon_id"])
        active_target_horizon_bars = int(active_entry["target_horizon_bars"])
        pass_ids = {active_candidate_id}
        fast_reject_reports: list[str] = []
        strict_strategy_ids: list[str] = []
        strict_strategy_horizons: dict[str, int] = {}
        strict_strategy_label_contracts: dict[str, str] = {}
        build_feature_sets_kwargs: dict[str, object] = {}

        def _fake_load_snapshot(*, as_of: str, artifacts_root: Path):
            self.assertEqual(as_of, self.as_of)
            return {
                "as_of": self.as_of,
                "candidates": [],
                "selection_policy_hash": "policy",
            }

        def _fake_require_derivatives_sync_summary(*, as_of: str, derivatives_external_root: Path | None):
            return ({"status": "success"}, self.artifacts_root / "cycles" / as_of / "derivatives_sync_summary.json")

        def _fake_build_datasets(**_: object):
            return [{"dataset_id": f"{self.as_of}-cross-sectional-daily-1d"}]

        def _fake_gap_backfill(**_: object):
            return {
                "attempted": True,
                "status": "success",
                "requested_profiles": ["cross_sectional_daily_4h"],
                "requested_intervals": ["1d", "4h"],
                "rebuild_required": False,
                "summary_path": str(self.artifacts_root / "cycles" / self.as_of / "spot_gap_backfill_summary.json"),
            }

        def _fake_build_feature_sets(**kwargs: object):
            build_feature_sets_kwargs.update(kwargs)
            return [
                {
                    "feature_set_id": (
                        f"{self.as_of}-cross-sectional-daily-1d-{active_horizon_id}-features-"
                        f"{hypothesis_batch.HYPOTHESIS_BATCH_FEATURE_SET_VERSION}"
                    ),
                    "dataset_profile": "cross_sectional_daily_4h",
                    "target_horizon_bars": active_target_horizon_bars,
                    "split_realization_contract": {"target_horizon_bars": active_target_horizon_bars},
                    "label_contract_id": DEFAULT_LABEL_CONTRACT_ID,
                    "target_column": "target_up",
                    "forward_return_column": "target_forward_return",
                },
            ]

        def _fake_run_fast_reject_candidate(
            *,
            as_of: str,
            batch_root: Path,
            candidate_entry: dict[str, object],
            feature_sets: list[dict[str, object]],
            fast_reject_contract: dict[str, object],
            source_commit_sha: str,
        ):
            candidate_id = str(candidate_entry["candidate_id"])
            family_root = batch_root / "families" / candidate_id
            family_root.mkdir(parents=True, exist_ok=True)
            report_path = family_root / "fast_reject_report.json"
            payload = {
                "status": "success",
                "success": True,
                "as_of": as_of,
                "candidate_id": candidate_id,
                "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
                "horizon_id": str(candidate_entry["horizon_id"]),
                "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
                "path": str(report_path),
                "fast_reject_passed": candidate_id in pass_ids,
                "blocker_codes": [] if candidate_id in pass_ids else [hypothesis_batch.LITE_BLOCKER_FACTOR],
            }
            write_json(report_path, payload)
            fast_reject_reports.append(candidate_id)
            return payload

        def _fake_run_quant_experiments_for_strategies(*, strategies: list[dict[str, object]], **_: object):
            strict_strategy_ids.extend(str(strategy["strategy_id"]) for strategy in strategies)
            strict_strategy_horizons.update(
                {
                    str(strategy["strategy_id"]): int(strategy.get("target_horizon_bars") or 0)
                    for strategy in strategies
                }
            )
            strict_strategy_label_contracts.update(
                {
                    str(strategy["strategy_id"]): str(strategy.get("label_contract_id") or "")
                    for strategy in strategies
                }
            )
            experiments = []
            for strategy in strategies:
                candidate_id = str(strategy["strategy_id"])
                experiment_root = self.artifacts_root / "experiments" / f"{self.as_of}-{candidate_id}"
                experiment_root.mkdir(parents=True, exist_ok=True)
                alpha_card_path = experiment_root / "alpha_card.json"
                validation_report_path = experiment_root / "validation_report.json"
                alpha_card = {
                    "experiment_status": "quarantined",
                    "credible_research_evidence": candidate_id == active_candidate_id,
                    "falsification_status": "cleared",
                    "validation_contract": {"status": "passed" if candidate_id == active_candidate_id else "failed"},
                }
                validation_report = {
                    "credible_research_evidence": candidate_id == active_candidate_id,
                    "falsification_status": "cleared",
                    "validation_contract": {"status": "passed" if candidate_id == active_candidate_id else "failed"},
                }
                write_json(alpha_card_path, alpha_card)
                write_json(validation_report_path, validation_report)
                experiments.append(
                    {
                        "strategy_id": candidate_id,
                        "experiment_id": f"{self.as_of}-{candidate_id}",
                        "experiment_status": "quarantined",
                        "alpha_card": alpha_card,
                        "validation_report": validation_report,
                        "alpha_card_path": str(alpha_card_path),
                        "validation_report_path": str(validation_report_path),
                    }
                )
            return experiments

        with (
            patch("enhengclaw.quant_research.hypothesis_batch.load_quant_universe_snapshot", side_effect=_fake_load_snapshot),
            patch("enhengclaw.quant_research.hypothesis_batch.require_derivatives_sync_summary", side_effect=_fake_require_derivatives_sync_summary),
            patch("enhengclaw.quant_research.hypothesis_batch.build_quant_datasets", side_effect=_fake_build_datasets),
            patch("enhengclaw.quant_research.hypothesis_batch._apply_spot_gap_backfill_for_cross_sectional_profiles", side_effect=_fake_gap_backfill),
            patch("enhengclaw.quant_research.hypothesis_batch.build_quant_feature_sets", side_effect=_fake_build_feature_sets),
            patch("enhengclaw.quant_research.hypothesis_batch._run_fast_reject_candidate", side_effect=_fake_run_fast_reject_candidate),
            patch("enhengclaw.quant_research.hypothesis_batch.run_quant_experiments_for_strategies", side_effect=_fake_run_quant_experiments_for_strategies),
        ):
            summary = hypothesis_batch.run_quant_hypothesis_batch_cycle(
                as_of=self.as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
            )

        self.assertEqual(set(fast_reject_reports), set(hypothesis_batch.EXPECTED_CANDIDATE_IDS))
        self.assertEqual(set(strict_strategy_ids), pass_ids)
        self.assertEqual(
            build_feature_sets_kwargs.get("cross_sectional_daily_target_horizons"),
            (active_target_horizon_bars,),
        )
        self.assertEqual(
            build_feature_sets_kwargs.get("cross_sectional_daily_label_contract_ids"),
            (DEFAULT_LABEL_CONTRACT_ID,),
        )
        self.assertEqual(
            build_feature_sets_kwargs.get("feature_set_version"),
            hypothesis_batch.HYPOTHESIS_BATCH_FEATURE_SET_VERSION,
        )
        self.assertEqual(strict_strategy_horizons[active_candidate_id], active_target_horizon_bars)
        self.assertEqual(
            strict_strategy_label_contracts[active_candidate_id],
            DEFAULT_LABEL_CONTRACT_ID,
        )
        self.assertEqual(summary["fast_reject_pass_count"], 1)
        self.assertEqual(summary["strict_candidate_count"], 1)
        self.assertEqual(summary["strict_survivor_count"], 1)
        self.assertEqual(summary["candidate_count_by_horizon"], {active_horizon_id: 1})
        self.assertEqual(summary["fast_reject_pass_count_by_horizon"], {active_horizon_id: 1})
        self.assertEqual(
            summary["fast_reject_pass_count_by_mechanism"],
            {active_base_mechanism_id: 1},
        )
        self.assertEqual(summary["strict_survivor_count_by_horizon"], {active_horizon_id: 1})
        strict_candidate_list = read_json(self.artifacts_root / "hypothesis_batches" / self.as_of / "strict_candidate_list.json")
        self.assertEqual(strict_candidate_list["strict_candidate_count"], 1)
        self.assertEqual(strict_candidate_list["strict_survivor_count"], 1)
        self.assertEqual(strict_candidate_list["strict_survivors"][0]["candidate_id"], active_candidate_id)
        self.assertFalse((self.artifacts_root / "strategy_library").exists())
        self.assertFalse((self.artifacts_root / "promotion").exists())
        self.assertFalse((self.artifacts_root / "bridge").exists())
        self.assertFalse((self.artifacts_root / "proposals").exists())

    def test_batch_cycle_writes_empty_strict_candidate_list_when_no_fast_reject_passers(self) -> None:
        def _fake_load_snapshot(*, as_of: str, artifacts_root: Path):
            return {"as_of": self.as_of, "candidates": [], "selection_policy_hash": "policy"}

        def _fake_require_derivatives_sync_summary(*, as_of: str, derivatives_external_root: Path | None):
            return ({"status": "success"}, self.artifacts_root / "cycles" / as_of / "derivatives_sync_summary.json")

        def _fake_build_datasets(**_: object):
            return [{"dataset_id": f"{self.as_of}-cross-sectional-daily-1d"}]

        def _fake_gap_backfill(**_: object):
            return {
                "attempted": False,
                "status": "skipped",
                "requested_profiles": ["cross_sectional_daily_4h"],
                "requested_intervals": [],
                "rebuild_required": False,
                "summary_path": "",
            }

        def _fake_build_feature_sets(**_: object):
            active_entry = hypothesis_batch.load_cross_sectional_hypothesis_batch_manifest()["entries"][0]
            return [
                {
                    "feature_set_id": (
                        f"{self.as_of}-cross-sectional-daily-1d-{active_entry['horizon_id']}-features-"
                        f"{hypothesis_batch.HYPOTHESIS_BATCH_FEATURE_SET_VERSION}"
                    ),
                    "dataset_profile": "cross_sectional_daily_4h",
                    "target_horizon_bars": int(active_entry["target_horizon_bars"]),
                    "split_realization_contract": {"target_horizon_bars": int(active_entry["target_horizon_bars"])},
                    "label_contract_id": DEFAULT_LABEL_CONTRACT_ID,
                    "target_column": "target_up",
                    "forward_return_column": "target_forward_return",
                },
            ]

        def _fake_run_fast_reject_candidate(
            *,
            as_of: str,
            batch_root: Path,
            candidate_entry: dict[str, object],
            feature_sets: list[dict[str, object]],
            fast_reject_contract: dict[str, object],
            source_commit_sha: str,
        ):
            candidate_id = str(candidate_entry["candidate_id"])
            report_path = batch_root / "families" / candidate_id / "fast_reject_report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "success",
                "success": True,
                "as_of": as_of,
                "candidate_id": candidate_id,
                "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
                "horizon_id": str(candidate_entry["horizon_id"]),
                "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
                "path": str(report_path),
                "fast_reject_passed": False,
                "blocker_codes": [hypothesis_batch.LITE_BLOCKER_FACTOR],
            }
            write_json(report_path, payload)
            return payload

        with (
            patch("enhengclaw.quant_research.hypothesis_batch.load_quant_universe_snapshot", side_effect=_fake_load_snapshot),
            patch("enhengclaw.quant_research.hypothesis_batch.require_derivatives_sync_summary", side_effect=_fake_require_derivatives_sync_summary),
            patch("enhengclaw.quant_research.hypothesis_batch.build_quant_datasets", side_effect=_fake_build_datasets),
            patch("enhengclaw.quant_research.hypothesis_batch._apply_spot_gap_backfill_for_cross_sectional_profiles", side_effect=_fake_gap_backfill),
            patch("enhengclaw.quant_research.hypothesis_batch.build_quant_feature_sets", side_effect=_fake_build_feature_sets),
            patch("enhengclaw.quant_research.hypothesis_batch._run_fast_reject_candidate", side_effect=_fake_run_fast_reject_candidate),
            patch("enhengclaw.quant_research.hypothesis_batch.run_quant_experiments_for_strategies") as mock_strict,
        ):
            summary = hypothesis_batch.run_quant_hypothesis_batch_cycle(
                as_of=self.as_of,
                artifacts_root=self.artifacts_root,
                quant_input_root=self.quant_inputs_root,
                workbench_root=self.workbench_root,
            )

        self.assertEqual(summary["fast_reject_pass_count"], 0)
        self.assertEqual(summary["strict_candidate_count"], 0)
        self.assertEqual(summary["strict_survivor_count"], 0)
        mock_strict.assert_not_called()
        strict_candidate_list = read_json(self.artifacts_root / "hypothesis_batches" / self.as_of / "strict_candidate_list.json")
        self.assertEqual(strict_candidate_list["strict_candidates"], [])
        self.assertEqual(strict_candidate_list["strict_survivors"], [])

    def test_hypothesis_batch_cli_exit_codes_follow_strict_survivor_state(self) -> None:
        module = self._load_hypothesis_cli_module()

        module.run_quant_hypothesis_batch_cycle = lambda **_: {"strict_survivor_count": 1, "success": True}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--as-of", self.as_of]), 0)

        module.run_quant_hypothesis_batch_cycle = lambda **_: {"strict_survivor_count": 0, "success": True}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--as-of", self.as_of]), 2)

        module.run_quant_hypothesis_batch_cycle = lambda **_: {"strict_survivor_count": 0, "success": False}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--as-of", self.as_of]), 1)

    def _load_hypothesis_cli_module(self):
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_hypothesis_batch_cycle.py"
        spec = importlib.util.spec_from_file_location("quant_hypothesis_batch_cli", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
