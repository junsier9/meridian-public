from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.data_readiness import (
    CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
    CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE,
    CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
    DISCOVERY_DERIVATIVES_BLOCKER,
    DISCOVERY_EVENT_BLOCKER,
    blocked_discovery_reason,
    build_dataset_data_readiness,
    evaluate_derivatives_history_gap,
    is_daily_executable_strategy,
    resolve_default_spot_ohlcv_external_root,
)


class QuantDataReadinessTests(unittest.TestCase):
    def test_build_dataset_data_readiness_blocks_cross_sectional_under_min_subjects(self) -> None:
        readiness = build_dataset_data_readiness(
            dataset_id="2026-04-22-cross-sectional-1d",
            shape="cross_sectional",
            subject_count=3,
            requested_universe_count=100,
            spot_ohlcv_external_root=None,
            dataset_profile=CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
        )
        self.assertEqual(readiness["cross_sectional_executable_subject_count"], 3)
        self.assertIn(CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER, readiness["data_gap_blockers"])

    def test_build_dataset_data_readiness_blocks_cross_sectional_on_thin_coverage(self) -> None:
        readiness = build_dataset_data_readiness(
            dataset_id="2026-04-22-cross-sectional-1d",
            shape="cross_sectional",
            subject_count=30,
            requested_universe_count=100,
            spot_ohlcv_external_root=Path("C:/tmp/coinapi"),
            dataset_profile=CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
        )
        self.assertEqual(readiness["cross_sectional_executable_subject_count"], 30)
        self.assertIn(CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER, readiness["data_gap_blockers"])
        self.assertFalse(readiness["cross_sectional_daily_lane_eligible"])
        self.assertAlmostEqual(readiness["spot_subject_coverage"]["coverage_fraction"], 0.3)
        self.assertEqual(readiness["spot_subject_coverage"]["required_subject_count_min"], 85)
        self.assertFalse(readiness["spot_subject_coverage"]["coverage_requirement_met"])
        self.assertEqual(readiness["spot_subject_coverage"]["required_spot_intervals"], ["1d", "4h"])

    def test_build_dataset_data_readiness_allows_cross_sectional_at_required_coverage(self) -> None:
        readiness = build_dataset_data_readiness(
            dataset_id="2026-04-22-cross-sectional-1d",
            shape="cross_sectional",
            subject_count=85,
            requested_universe_count=100,
            spot_ohlcv_external_root=Path("C:/tmp/coinapi"),
            dataset_profile=CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
        )
        self.assertEqual(readiness["cross_sectional_executable_subject_count"], 85)
        self.assertEqual(readiness["data_gap_blockers"], [])
        self.assertTrue(readiness["cross_sectional_daily_lane_eligible"])
        self.assertTrue(readiness["spot_subject_coverage"]["coverage_requirement_met"])

    def test_build_dataset_data_readiness_uses_intraday_profile_requirements(self) -> None:
        readiness = build_dataset_data_readiness(
            dataset_id="2026-04-22-cross-sectional-intraday-1h",
            shape="cross_sectional",
            subject_count=37,
            requested_universe_count=99,
            spot_ohlcv_external_root=Path("C:/tmp/coinapi"),
            dataset_profile=CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE,
            missing_spot_symbols_by_interval={"1h": ["APTUSDT", "ARBUSDT"]},
        )
        self.assertIn(CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER, readiness["data_gap_blockers"])
        self.assertEqual(readiness["dataset_profile"], CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE)
        self.assertEqual(readiness["spot_subject_coverage"]["required_spot_intervals"], ["1h"])
        self.assertEqual(
            readiness["spot_subject_coverage"]["missing_spot_symbols_by_interval"],
            {"1h": ["APTUSDT", "ARBUSDT"]},
        )

    def test_evaluate_derivatives_history_gap_fails_on_open_interest_readiness(self) -> None:
        blockers = evaluate_derivatives_history_gap(
            strategy_entry={
                "data_dependencies": {
                    "derivatives_fields": ["funding_rate", "open_interest"],
                }
            },
            derivatives_strategy_quality={
                "funding_family": {
                    "train_ready_row_fraction": 0.95,
                    "validation_ready_row_fraction": 0.95,
                    "test_ready_row_fraction": 0.95,
                    "warning_counts": {},
                },
                "open_interest_family": {
                    "train_ready_row_fraction": 0.0,
                    "validation_ready_row_fraction": 0.0,
                    "test_ready_row_fraction": 0.0,
                    "warning_counts": {},
                },
            },
        )
        self.assertEqual(blockers, [DISCOVERY_DERIVATIVES_BLOCKER])

    def test_evaluate_derivatives_history_gap_ignores_provider_warnings_when_split_ready_passes(self) -> None:
        blockers = evaluate_derivatives_history_gap(
            strategy_entry={
                "data_dependencies": {
                    "derivatives_fields": ["funding_rate", "open_interest"],
                }
            },
            derivatives_strategy_quality={
                "funding_family": {
                    "train_ready_row_fraction": 0.95,
                    "validation_ready_row_fraction": 0.95,
                    "test_ready_row_fraction": 0.95,
                    "warning_counts": {"funding_rate_provider_data_start_after_requested_window": 3},
                },
                "open_interest_family": {
                    "train_ready_row_fraction": 0.91,
                    "validation_ready_row_fraction": 0.92,
                    "test_ready_row_fraction": 0.93,
                    "warning_counts": {"open_interest_provider_data_start_after_requested_window": 2},
                },
            },
        )
        self.assertEqual(blockers, [])

    def test_is_daily_executable_strategy_blocks_blocked_discovery_families(self) -> None:
        self.assertFalse(
            is_daily_executable_strategy(
                strategy_entry={
                    "model_family": "carry_funding",
                    "daily_executable": True,
                    "research_lane": "hypothesis_factor",
                    "thesis_profile": {"thesis_id": "funding-extreme-reversal"},
                    "data_dependencies": {"derivatives_fields": ["funding_rate", "open_interest"]},
                }
            )
        )
        self.assertFalse(
            is_daily_executable_strategy(
                strategy_entry={
                    "model_family": "basis_divergence",
                    "daily_executable": True,
                    "research_lane": "hypothesis_factor",
                    "thesis_profile": {"thesis_id": "basis-mean-reversion"},
                    "data_dependencies": {"derivatives_fields": ["perp_close"]},
                }
            )
        )
        self.assertFalse(
            is_daily_executable_strategy(
                strategy_entry={
                    "model_family": "event_drift",
                    "daily_executable": True,
                    "research_lane": "hypothesis_factor",
                    "thesis_profile": {"thesis_id": "event-drift"},
                    "data_dependencies": {"derivatives_fields": []},
                }
            )
        )
        self.assertTrue(
            is_daily_executable_strategy(
                strategy_entry={
                    "model_family": "logistic_regression",
                    "daily_executable": True,
                    "research_lane": "hypothesis_factor",
                    "thesis_profile": {"thesis_id": "cross-logit"},
                    "data_dependencies": {"derivatives_fields": []},
                }
            )
        )

    def test_blocked_discovery_reason_rejects_event_and_derivatives_families(self) -> None:
        self.assertEqual(blocked_discovery_reason(model_family="carry_funding"), DISCOVERY_DERIVATIVES_BLOCKER)
        self.assertEqual(blocked_discovery_reason(model_family="basis_divergence"), DISCOVERY_DERIVATIVES_BLOCKER)
        self.assertEqual(blocked_discovery_reason(model_family="event_drift"), DISCOVERY_EVENT_BLOCKER)
        self.assertIsNone(blocked_discovery_reason(model_family="logistic_regression"))

    def test_resolve_default_spot_ohlcv_external_root_detects_localappdata_sidecar(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coinapi-root-") as tmp_dir:
            localappdata_root = Path(tmp_dir)
            sidecar_root = localappdata_root / "EnhengClaw" / "market_history" / "coinapi_ohlcv"
            sidecar_root.mkdir(parents=True, exist_ok=True)
            with patch.dict(os.environ, {"LOCALAPPDATA": str(localappdata_root)}, clear=False):
                resolved = resolve_default_spot_ohlcv_external_root(spot_ohlcv_external_root=None)
            self.assertEqual(resolved, sidecar_root.resolve())
