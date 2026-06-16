from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission import (
    build_feature_admission_policy,
    build_feature_admission_section,
    classify_feature_manifest_columns,
)
from enhengclaw.quant_research.governance import select_feature_columns
from enhengclaw.quant_research.lab import _derivatives_first_cross_section_feature_columns


class FeatureAdmissionTests(unittest.TestCase):
    def test_classify_feature_manifest_columns_excludes_time_price_and_identity_proxies(self) -> None:
        manifest = classify_feature_manifest_columns(
            [
                "timestamp_ms",
                "spot_open",
                "spot_close",
                "selection_rank",
                "rolling_median_quote_volume_usd_30d",
                "listing_age_days_as_of",
                "perp_quote_volume_usd",
                "momentum_6",
                "ema_slope_6_18",
                "quote_volume_expansion",
                "funding_zscore_20",
                "basis_zscore_20",
                "event__unlock",
            ]
        )
        self.assertIn("timestamp_ms", manifest["excluded_numeric_columns"])
        self.assertIn("spot_open", manifest["excluded_numeric_columns"])
        self.assertIn("selection_rank", manifest["excluded_numeric_columns"])
        self.assertIn("listing_age_days_as_of", manifest["excluded_numeric_columns"])
        self.assertIn("perp_quote_volume_usd", manifest["excluded_numeric_columns"])
        self.assertIn("momentum_6", manifest["numeric_feature_columns"])
        self.assertIn("ema_slope_6_18", manifest["numeric_feature_columns"])
        self.assertIn("quote_volume_expansion", manifest["numeric_feature_columns"])
        self.assertIn("funding_zscore_20", manifest["numeric_feature_columns"])
        self.assertIn("basis_zscore_20", manifest["numeric_feature_columns"])
        self.assertIn("event__unlock", manifest["excluded_numeric_columns"])

    def test_select_feature_columns_fails_closed_for_core_context_and_unknown_columns(self) -> None:
        selected = select_feature_columns(
            numeric_feature_columns=["momentum_6", "quote_volume_expansion", "mystery_signal"],
            feature_groups=["core_context"],
        )
        self.assertEqual(selected, [])

        selected = select_feature_columns(
            numeric_feature_columns=["momentum_6", "quote_volume_expansion", "mystery_signal"],
            feature_groups=["trend", "volume"],
        )
        self.assertEqual(selected, ["momentum_6", "quote_volume_expansion"])

    def test_derivatives_first_cross_section_feature_columns_keeps_only_admitted_derivatives(self) -> None:
        selected = _derivatives_first_cross_section_feature_columns(
            [
                "funding_rate",
                "funding_zscore_20",
                "oi_change_5",
                "basis_proxy",
                "basis_zscore_20",
                "selection_rank",
                "rolling_median_quote_volume_usd_30d",
                "listing_age_days_as_of",
                "open_interest",
                "has_perp_as_of",
            ]
        )
        self.assertEqual(
            selected,
            ["funding_rate", "funding_zscore_20", "oi_change_5", "basis_proxy", "basis_zscore_20"],
        )

    def test_feature_admission_section_rejects_unknown_generated_columns(self) -> None:
        section = build_feature_admission_section(
            feature_admission_policy=build_feature_admission_policy(),
            available_numeric_columns=["momentum_6", "timestamp_ms"],
            numeric_feature_columns=["momentum_6"],
            excluded_numeric_columns=["timestamp_ms"],
            selected_feature_columns=["momentum_6", "custom_generated_signal"],
            generated_feature_columns=["custom_generated_signal"],
        )
        self.assertFalse(section["passed"])
        self.assertEqual(section["unknown_numeric_columns_present"], ["custom_generated_signal"])


if __name__ == "__main__":
    unittest.main()
