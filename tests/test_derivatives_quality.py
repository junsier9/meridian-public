from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.derivatives_quality import (
    build_derivatives_provider_index,
    summarize_dataset_derivatives_quality,
    summarize_strategy_derivatives_quality,
)
from enhengclaw.quant_research.features import build_cross_sectional_feature_bundle


class DerivativesQualityTests(unittest.TestCase):
    def test_dataset_summary_exposes_funding_open_interest_gap(self) -> None:
        panel = pd.DataFrame(
            [
                {
                    "subject": "ETH",
                    "timestamp_ms": index * 14_400_000,
                    "usdm_symbol": "ETHUSDT",
                    "has_perp": True,
                    "funding_rate": 0.0001,
                    "open_interest": 1000.0 if index >= 2 else None,
                }
                for index in range(6)
            ]
            + [
                {
                    "subject": "SUI",
                    "timestamp_ms": index * 14_400_000,
                    "usdm_symbol": "SUIUSDT",
                    "has_perp": True,
                    "funding_rate": 0.0002,
                    "open_interest": 500.0 if index >= 4 else None,
                }
                for index in range(6)
            ]
        )
        provider_index = build_derivatives_provider_index(
            {
                "sync_results": [
                    {
                        "status": "success",
                        "symbol": "ETHUSDT",
                        "interval": "4h",
                        "coverage_validation": {
                            "status": "warning",
                            "warning_codes": ["open_interest_provider_latest_window_cap"],
                        },
                        "field_coverage": {
                            "funding_rate": {"coverage_days": 730.0},
                            "open_interest": {"coverage_days": 29.0},
                        },
                    },
                    {
                        "status": "success",
                        "symbol": "SUIUSDT",
                        "interval": "4h",
                        "coverage_validation": {
                            "status": "warning",
                            "warning_codes": ["open_interest_provider_latest_window_cap"],
                        },
                        "field_coverage": {
                            "funding_rate": {"coverage_days": 710.0},
                            "open_interest": {"coverage_days": 28.0},
                        },
                    },
                ]
            }
        )

        summary = summarize_dataset_derivatives_quality(
            panel=panel,
            interval="4h",
            provider_index=provider_index,
        )

        self.assertEqual(summary["subject_count_with_perp"], 2)
        self.assertEqual(summary["subject_count_with_funding_rows"], 2)
        self.assertEqual(summary["subject_count_with_open_interest_rows"], 2)
        self.assertAlmostEqual(float(summary["funding_coverage_days"]["median"]), 720.0)
        self.assertAlmostEqual(float(summary["open_interest_coverage_days"]["median"]), 28.5)
        self.assertAlmostEqual(float(summary["funding_minus_open_interest_gap_days"]["median"]), 691.5)
        self.assertEqual(summary["warning_counts"]["open_interest_provider_latest_window_cap"], 2)

    def test_feature_bundle_tracks_ready_rows_before_fillna(self) -> None:
        rows: list[dict[str, object]] = []
        open_interest_values = [100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 110.0, 120.0]
        for index, open_interest in enumerate(open_interest_values):
            rows.append(
                {
                    "subject": "ETH",
                    "timestamp_ms": index * 86_400_000,
                    "asset_bucket": "large_cap",
                    "usdm_symbol": "ETHUSDT",
                    "spot_close": 100.0 + index,
                    "spot_high": 101.0 + index,
                    "spot_low": 99.0 + index,
                    "spot_quote_volume": 1_000_000.0 + (index * 10_000.0),
                    "open_interest": open_interest,
                    "funding_rate": 0.0001,
                    "basis_proxy": 0.0,
                    "market_cap_rank": 1,
                }
            )

        bundle = build_cross_sectional_feature_bundle(panel=pd.DataFrame(rows))
        target_row = bundle["dataframe"].loc[bundle["dataframe"]["timestamp_ms"] == 6 * 86_400_000].iloc[0]

        self.assertEqual(float(target_row["oi_change_5"]), 0.0)
        self.assertEqual(bundle["derivatives_feature_quality"]["features"]["oi_change_5"]["row_ready_fraction"], 0.0)
        self.assertEqual(bundle["derivatives_feature_quality"]["features"]["oi_change_5"]["subject_ready_count"], 0)

    def test_strategy_summary_marks_derivatives_strategy_warning_and_spot_only_not_applicable(self) -> None:
        rows: list[dict[str, object]] = []
        for index in range(40):
            rows.append(
                {
                    "subject": "ETH",
                    "timestamp_ms": index * 86_400_000,
                    "asset_bucket": "large_cap",
                    "usdm_symbol": "ETHUSDT",
                    "spot_close": 100.0 + index,
                    "spot_high": 101.0 + index,
                    "spot_low": 99.0 + index,
                    "spot_quote_volume": 1_000_000.0 + (index * 10_000.0),
                    "open_interest": 1_000.0 if index >= 30 else None,
                    "funding_rate": 0.0001,
                    "basis_proxy": 0.001,
                    "market_cap_rank": 1,
                }
            )
        provider_index = build_derivatives_provider_index(
            {
                "sync_results": [
                    {
                        "status": "success",
                        "symbol": "ETHUSDT",
                        "interval": "1d",
                        "coverage_validation": {
                            "status": "warning",
                            "warning_codes": ["open_interest_provider_latest_window_cap"],
                        },
                        "field_coverage": {
                            "funding_rate": {"coverage_days": 730.0},
                            "open_interest": {"coverage_days": 29.0},
                        },
                    }
                ]
            }
        )
        bundle = build_cross_sectional_feature_bundle(panel=pd.DataFrame(rows), provider_index=provider_index)
        features = bundle["dataframe"].copy()
        quality_frame = bundle["quality_frame"].copy()
        train_df = features.iloc[:20].copy()
        validation_df = features.iloc[20:30].copy()
        test_df = features.iloc[30:].copy()

        derivatives_quality = summarize_strategy_derivatives_quality(
            feature_frame=features,
            quality_frame=quality_frame,
            feature_columns=["funding_zscore_20", "oi_change_5", "basis_zscore_20"],
            derivatives_feature_quality=bundle["derivatives_feature_quality"],
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
        )
        spot_only_quality = summarize_strategy_derivatives_quality(
            feature_frame=features,
            quality_frame=quality_frame,
            feature_columns=["momentum_20"],
            derivatives_feature_quality=bundle["derivatives_feature_quality"],
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
        )

        self.assertEqual(derivatives_quality["status"], "warning")
        self.assertTrue(derivatives_quality["uses_derivatives_features"])
        self.assertEqual(
            derivatives_quality["open_interest_family"]["warning_counts"]["open_interest_provider_latest_window_cap"],
            1,
        )
        self.assertEqual(spot_only_quality["status"], "not_applicable")
        self.assertFalse(spot_only_quality["uses_derivatives_features"])

    def test_strategy_summary_tracks_subject_level_split_readiness_for_late_start_symbols(self) -> None:
        feature_frame = pd.DataFrame(
            [
                {"subject": "BTC", "timestamp_ms": 0},
                {"subject": "PAXG", "timestamp_ms": 0},
                {"subject": "BTC", "timestamp_ms": 86_400_000},
                {"subject": "PAXG", "timestamp_ms": 86_400_000},
                {"subject": "BTC", "timestamp_ms": 2 * 86_400_000},
                {"subject": "PAXG", "timestamp_ms": 2 * 86_400_000},
                {"subject": "BTC", "timestamp_ms": 3 * 86_400_000},
                {"subject": "PAXG", "timestamp_ms": 3 * 86_400_000},
            ]
        )
        quality_frame = feature_frame.copy()
        quality_frame["__derivatives_ready__funding_zscore_20"] = [
            True,
            False,
            True,
            False,
            True,
            True,
            True,
            True,
        ]
        quality_frame["__derivatives_source__funding_zscore_20"] = quality_frame["__derivatives_ready__funding_zscore_20"]
        quality_frame["funding_rate"] = [0.0001] * len(quality_frame)
        quality_frame["usdm_symbol"] = [
            "BTCUSDT",
            "PAXGUSDT",
            "BTCUSDT",
            "PAXGUSDT",
            "BTCUSDT",
            "PAXGUSDT",
            "BTCUSDT",
            "PAXGUSDT",
        ]
        derivatives_quality = summarize_strategy_derivatives_quality(
            feature_frame=feature_frame,
            quality_frame=quality_frame,
            feature_columns=["funding_zscore_20"],
            train_df=feature_frame.iloc[:4].copy(),
            validation_df=feature_frame.iloc[4:6].copy(),
            test_df=feature_frame.iloc[6:].copy(),
            required_families=["funding"],
            split_ready_row_fraction_thresholds={"train": 0.8, "validation": 0.8, "test": 0.8},
        )

        panel = derivatives_quality["subject_panel_readiness"]
        self.assertEqual(panel["eligible_subjects"], ["BTC"])
        self.assertEqual(panel["excluded_subjects"], ["PAXG"])
        self.assertEqual(panel["late_start_subjects"], ["PAXG"])
        self.assertEqual(panel["split_ready_subjects"]["train"], ["BTC"])
        self.assertEqual(panel["split_ready_subjects"]["validation"], ["BTC", "PAXG"])
        self.assertEqual(panel["split_ready_subjects"]["test"], ["BTC", "PAXG"])


if __name__ == "__main__":
    unittest.main()
