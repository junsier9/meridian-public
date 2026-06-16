from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.execution_backtest import (
    _cross_sectional_target_weights,
    _drawdown_throttle_multiplier,
    _scale_cross_sectional_turnover,
    _trade_liquidity_volume_proxy_usd,
    backtest_cross_sectional,
    filter_cross_sectional_execution_frame,
)
from enhengclaw.quant_research.lab import _available_quote_volume_usd_for_row


class ExecutionBacktestTests(unittest.TestCase):
    def test_spot_liquidity_proxy_prefers_spot_quote_volume_over_dirty_daily_quote_volume(self) -> None:
        row = pd.Series(
            {
                "daily_quote_volume": 38.928244,
                "spot_quote_volume": 151_873_100.0,
                "intraday_quote_volume_4h": None,
                "intraday_quote_volume_1d": None,
            }
        )
        self.assertEqual(_trade_liquidity_volume_proxy_usd(row=row, execution_venue="spot"), 151_873_100.0)

    def test_available_quote_volume_for_row_prefers_spot_quote_volume_over_dirty_daily_quote_volume(self) -> None:
        row = pd.Series(
            {
                "daily_quote_volume": 38.928244,
                "spot_quote_volume": 151_873_100.0,
                "intraday_quote_volume_4h": None,
                "rolling_median_quote_volume_usd_30d": 275_000_000.0,
            }
        )
        self.assertEqual(_available_quote_volume_usd_for_row(row), 151_873_100.0)

    def test_perp_liquidity_proxy_prefers_quote_volume_usd(self) -> None:
        row = pd.Series(
            {
                "perp_quote_volume_usd": 2_200_000.0,
                "perp_volume": None,
                "perp_close": None,
            }
        )
        self.assertEqual(_trade_liquidity_volume_proxy_usd(row=row, execution_venue="perp"), 2_200_000.0)

    def test_perp_liquidity_proxy_falls_back_to_volume_times_price(self) -> None:
        row = pd.Series(
            {
                "perp_quote_volume_usd": None,
                "perp_volume": 1_250.0,
                "perp_close": 2_000.0,
            }
        )
        self.assertEqual(_trade_liquidity_volume_proxy_usd(row=row, execution_venue="perp"), 2_500_000.0)

    def test_drawdown_throttle_supports_soft_linear_budget(self) -> None:
        constraints = {
            "dd_throttle_mode": "soft_linear",
            "dd_throttle_start_threshold": 0.10,
            "dd_throttle_full_threshold": 0.25,
            "dd_throttle_min_multiplier": 0.80,
        }

        self.assertIsNone(_drawdown_throttle_multiplier(current_drawdown=0.05, constraints=constraints))
        self.assertAlmostEqual(
            _drawdown_throttle_multiplier(current_drawdown=0.175, constraints=constraints),
            0.90,
        )
        self.assertAlmostEqual(
            _drawdown_throttle_multiplier(current_drawdown=0.30, constraints=constraints),
            0.80,
        )

    def test_drawdown_throttle_preserves_legacy_step_budget(self) -> None:
        constraints = {
            "dd_throttle_5pct_threshold": 0.05,
            "dd_throttle_10pct_threshold": 0.10,
            "dd_throttle_5pct_multiplier": 0.70,
            "dd_throttle_10pct_multiplier": 0.50,
        }

        self.assertIsNone(_drawdown_throttle_multiplier(current_drawdown=0.04, constraints=constraints))
        self.assertAlmostEqual(
            _drawdown_throttle_multiplier(current_drawdown=0.06, constraints=constraints),
            0.70,
        )
        self.assertAlmostEqual(
            _drawdown_throttle_multiplier(current_drawdown=0.12, constraints=constraints),
            0.50,
        )

    def test_filter_cross_sectional_execution_frame_excludes_subjects_without_perp(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 0,
                    "subject": "BTC",
                    "score": 0.5,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                },
                {
                    "timestamp_ms": 0,
                    "subject": "PEPE",
                    "score": 10.0,
                    "has_perp": False,
                    "usdm_symbol": None,
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": None,
                },
                {
                    "timestamp_ms": 86_400_000,
                    "subject": "BTC",
                    "score": 0.6,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                },
                {
                    "timestamp_ms": 86_400_000,
                    "subject": "PEPE",
                    "score": 11.0,
                    "has_perp": False,
                    "usdm_symbol": None,
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": None,
                },
            ]
        )
        filtered = filter_cross_sectional_execution_frame(frame=frame, constraints={"execution_venue": "perp"})
        self.assertEqual(sorted(filtered["subject"].unique().tolist()), ["BTC"])
        self.assertNotIn("PEPE", filtered["subject"].tolist())

    def test_filter_cross_sectional_execution_frame_respects_subject_executable_start(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 0,
                    "subject": "BTC",
                    "score": 0.5,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                },
                {
                    "timestamp_ms": 0,
                    "subject": "PAXG",
                    "score": 0.9,
                    "has_perp": True,
                    "usdm_symbol": "PAXGUSDT",
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": 2 * 86_400_000,
                },
                {
                    "timestamp_ms": 86_400_000,
                    "subject": "BTC",
                    "score": 0.6,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                },
                {
                    "timestamp_ms": 86_400_000,
                    "subject": "PAXG",
                    "score": 1.0,
                    "has_perp": True,
                    "usdm_symbol": "PAXGUSDT",
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": 2 * 86_400_000,
                },
                {
                    "timestamp_ms": 2 * 86_400_000,
                    "subject": "BTC",
                    "score": 0.7,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                },
                {
                    "timestamp_ms": 2 * 86_400_000,
                    "subject": "PAXG",
                    "score": 1.1,
                    "has_perp": True,
                    "usdm_symbol": "PAXGUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 2 * 86_400_000,
                },
            ]
        )
        filtered = filter_cross_sectional_execution_frame(frame=frame, constraints={"execution_venue": "perp"})
        early_subjects = filtered.loc[filtered["timestamp_ms"] < 2 * 86_400_000, "subject"].unique().tolist()
        late_subjects = filtered.loc[filtered["timestamp_ms"] == 2 * 86_400_000, "subject"].unique().tolist()
        self.assertEqual(early_subjects, ["BTC"])
        self.assertEqual(sorted(late_subjects), ["BTC", "PAXG"])

    def test_cross_sectional_target_weights_supports_separate_long_and_short_eligibility(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "CORE_HIGH", "score": 3.0, "all_ok": True, "long_ok": True, "short_ok": False},
                {"subject": "NONCORE_HIGH", "score": 2.0, "all_ok": True, "long_ok": False, "short_ok": True},
                {"subject": "CORE_LOW", "score": -3.0, "all_ok": True, "long_ok": True, "short_ok": False},
                {"subject": "NONCORE_LOW", "score": -2.0, "all_ok": True, "long_ok": False, "short_ok": True},
            ]
        )

        weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                "decision_eligible_column": "all_ok",
                "long_decision_eligible_column": "long_ok",
                "short_decision_eligible_column": "short_ok",
                "top_long_count": 1,
                "bottom_short_count": 1,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "short_allowed": True,
            },
        )

        self.assertEqual(weights, {"CORE_HIGH": 0.5, "NONCORE_LOW": -0.5})

    def test_cross_sectional_target_weights_can_soft_cap_pair_strength(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "L1", "score": 0.90, "relative_strength_20": 0.5, "ema_slope_5_20": 0.2, "distance_to_low_20": 0.3, "intraday_realized_vol_4h_to_1d": 0.1, "realized_volatility_20": 0.1},
                {"subject": "L2", "score": 0.25, "relative_strength_20": 0.5, "ema_slope_5_20": 0.2, "distance_to_low_20": 0.3, "intraday_realized_vol_4h_to_1d": 0.1, "realized_volatility_20": 0.1},
                {"subject": "S2", "score": -0.20, "relative_strength_20": 0.5, "ema_slope_5_20": 0.2, "distance_to_low_20": 0.3, "intraday_realized_vol_4h_to_1d": 0.1, "realized_volatility_20": 0.1},
                {"subject": "S1", "score": -0.70, "relative_strength_20": 0.5, "ema_slope_5_20": 0.2, "distance_to_low_20": 0.3, "intraday_realized_vol_4h_to_1d": 0.1, "realized_volatility_20": 0.1},
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.35,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        uncapped = _cross_sectional_target_weights(decision_group=decision_group, constraints=base_constraints)
        capped = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={**base_constraints, "pair_strength_soft_cap": 0.30},
        )

        self.assertEqual(set(uncapped), {"L1", "S1"})
        self.assertEqual(set(capped), {"L1", "S1"})
        self.assertLess(abs(capped["L1"]), abs(uncapped["L1"]))
        self.assertLess(abs(capped["S1"]), abs(uncapped["S1"]))

    def test_cross_sectional_target_weights_can_soft_scale_trend_crowded_pairs(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "L1", "score": 0.90, "relative_strength_20": 0.95, "ema_slope_5_20": 0.90, "distance_to_low_20": 0.95, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "L2", "score": 0.25, "relative_strength_20": 0.20, "ema_slope_5_20": 0.20, "distance_to_low_20": 0.20, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S2", "score": -0.20, "relative_strength_20": 0.15, "ema_slope_5_20": 0.15, "distance_to_low_20": 0.15, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S1", "score": -0.70, "relative_strength_20": 0.10, "ema_slope_5_20": 0.10, "distance_to_low_20": 0.10, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.35,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        uncapped = _cross_sectional_target_weights(decision_group=decision_group, constraints=base_constraints)
        softened = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                **base_constraints,
                "pair_trend_crowding_soft_threshold": 0.85,
                "pair_trend_crowding_soft_scale": 0.7,
            },
        )

        self.assertIn("L1", softened)
        self.assertLess(abs(softened["L1"]), abs(uncapped["L1"]))
        self.assertLess(sum(abs(value) for value in softened.values()), sum(abs(value) for value in uncapped.values()))

    def test_cross_sectional_target_weights_can_soft_scale_trend_crowded_short_leg(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "L1", "score": 0.90, "relative_strength_20": 0.40, "ema_slope_5_20": 0.40, "distance_to_low_20": 0.40, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "L2", "score": 0.20, "relative_strength_20": 0.20, "ema_slope_5_20": 0.20, "distance_to_low_20": 0.20, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S2", "score": -0.10, "relative_strength_20": 0.10, "ema_slope_5_20": 0.10, "distance_to_low_20": 0.10, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S1", "score": -0.70, "relative_strength_20": 0.95, "ema_slope_5_20": 0.95, "distance_to_low_20": 0.95, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.35,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        uncapped = _cross_sectional_target_weights(decision_group=decision_group, constraints=base_constraints)
        softened = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                **base_constraints,
                "pair_short_trend_crowding_soft_threshold": 0.80,
                "pair_short_trend_crowding_soft_scale": 0.70,
            },
        )

        self.assertIn("L1", softened)
        self.assertLess(abs(softened["L1"]), abs(uncapped["L1"]))
        self.assertLess(sum(abs(value) for value in softened.values()), sum(abs(value) for value in uncapped.values()))

    def test_cross_sectional_target_weights_can_soft_scale_low_quality_balance_pair(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "L1", "score": 0.90, "relative_strength_20": 0.95, "ema_slope_5_20": 0.95, "distance_to_low_20": 0.95, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "L2", "score": 0.20, "relative_strength_20": 0.20, "ema_slope_5_20": 0.20, "distance_to_low_20": 0.20, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S2", "score": -0.10, "relative_strength_20": 0.18, "ema_slope_5_20": 0.18, "distance_to_low_20": 0.18, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S1", "score": -0.70, "relative_strength_20": 0.05, "ema_slope_5_20": 0.05, "distance_to_low_20": 0.05, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.35,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        uncapped = _cross_sectional_target_weights(decision_group=decision_group, constraints=base_constraints)
        softened = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                **base_constraints,
                "pair_quality_balance_soft_floor": 0.80,
                "pair_quality_balance_soft_scale": 0.70,
            },
        )

        self.assertIn("L1", softened)
        self.assertLess(abs(softened["L1"]), abs(uncapped["L1"]))
        self.assertLess(sum(abs(value) for value in softened.values()), sum(abs(value) for value in uncapped.values()))

    def test_scale_cross_sectional_turnover_can_prioritize_pair_exits_before_entries(self) -> None:
        previous_weights = {"ETH": 0.5, "UNI": -0.5}
        raw_target_weights = {"BTC": 0.5, "SUI": -0.5}

        blended = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=0.5,
        )
        exit_first = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=0.5,
            turnover_mode="exit_first",
        )

        self.assertEqual(set(blended), {"BTC", "ETH", "SUI", "UNI"})
        self.assertEqual(set(exit_first), {"ETH", "UNI"})
        self.assertAlmostEqual(exit_first["ETH"], 0.25)
        self.assertAlmostEqual(exit_first["UNI"], -0.25)

    def test_scale_cross_sectional_turnover_can_hold_previous_pair_when_rotation_is_capped(self) -> None:
        previous_weights = {"ETH": 0.5, "UNI": -0.5}
        raw_target_weights = {"BTC": 0.5, "SUI": -0.5}

        held = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=0.5,
            turnover_mode="pair_hold",
        )

        self.assertEqual(held, previous_weights)

    def test_scale_cross_sectional_turnover_can_project_back_to_single_pair(self) -> None:
        previous_weights = {"ETH": 0.5, "UNI": -0.5}
        raw_target_weights = {"BTC": 0.5, "SUI": -0.5}

        projected = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=0.5,
            turnover_mode="pair_project",
        )

        self.assertEqual(set(projected), {"ETH", "UNI"})
        self.assertAlmostEqual(projected["ETH"], 0.5)
        self.assertAlmostEqual(projected["UNI"], -0.5)

    def test_cross_sectional_target_weights_can_soft_scale_high_quality_short_leg(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "L1", "score": 0.90, "relative_strength_20": 0.40, "ema_slope_5_20": 0.40, "distance_to_low_20": 0.40, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "L2", "score": 0.20, "relative_strength_20": 0.20, "ema_slope_5_20": 0.20, "distance_to_low_20": 0.20, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S2", "score": -0.10, "relative_strength_20": 0.10, "ema_slope_5_20": 0.10, "distance_to_low_20": 0.10, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S1", "score": -0.70, "relative_strength_20": 0.85, "ema_slope_5_20": 0.85, "distance_to_low_20": 0.85, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.35,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        uncapped = _cross_sectional_target_weights(decision_group=decision_group, constraints=base_constraints)
        softened = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                **base_constraints,
                "pair_short_quality_soft_threshold": 0.75,
                "pair_short_quality_soft_scale": 0.70,
            },
        )

        self.assertIn("L1", softened)
        self.assertLess(abs(softened["L1"]), abs(uncapped["L1"]))
        self.assertLess(sum(abs(value) for value in softened.values()), sum(abs(value) for value in uncapped.values()))

    def test_cross_sectional_target_weights_can_hard_filter_high_quality_short_leg(self) -> None:
        decision_group = pd.DataFrame(
            [
                {"subject": "L1", "score": 0.90, "relative_strength_20": 0.40, "ema_slope_5_20": 0.40, "distance_to_low_20": 0.40, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "L2", "score": 0.20, "relative_strength_20": 0.20, "ema_slope_5_20": 0.20, "distance_to_low_20": 0.20, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S2", "score": -0.10, "relative_strength_20": 0.10, "ema_slope_5_20": 0.10, "distance_to_low_20": 0.10, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
                {"subject": "S1", "score": -0.70, "relative_strength_20": 0.85, "ema_slope_5_20": 0.85, "distance_to_low_20": 0.85, "intraday_realized_vol_4h_to_1d": 0.10, "realized_volatility_20": 0.10},
            ]
        )
        weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                "pair_construction": "quality_bucket_pairs",
                "pair_bucket_count": 2,
                "pair_count": 1,
                "pair_score_spread_min": 0.08,
                "pair_quality_floor": 0.35,
                "pair_short_quality_max": 0.75,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "short_allowed": True,
            },
        )

        self.assertNotIn("S1", weights)
        self.assertEqual(weights["L1"], 0.5)
        self.assertEqual(weights["L2"], -0.5)

    def test_backtest_cross_sectional_filters_non_executable_perp_subjects(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "timestamp_ms": 0,
                    "subject": "BTC",
                    "score": 1.0,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                    "perp_close": 100.0,
                    "perp_quote_volume_usd": 5_000_000.0,
                    "open_interest_value": 10_000_000.0,
                    "funding_rate": 0.0,
                    "funding_sample_count": 0.0,
                },
                {
                    "timestamp_ms": 0,
                    "subject": "SHIB",
                    "score": 10.0,
                    "has_perp": False,
                    "usdm_symbol": None,
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": None,
                    "perp_close": None,
                    "perp_quote_volume_usd": None,
                    "open_interest_value": None,
                    "funding_rate": 0.0,
                    "funding_sample_count": 0.0,
                },
                {
                    "timestamp_ms": 86_400_000,
                    "subject": "BTC",
                    "score": 1.0,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                    "perp_close": 110.0,
                    "perp_quote_volume_usd": 5_000_000.0,
                    "open_interest_value": 10_000_000.0,
                    "funding_rate": 0.0,
                    "funding_sample_count": 0.0,
                },
                {
                    "timestamp_ms": 86_400_000,
                    "subject": "SHIB",
                    "score": 11.0,
                    "has_perp": False,
                    "usdm_symbol": None,
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": None,
                    "perp_close": None,
                    "perp_quote_volume_usd": None,
                    "open_interest_value": None,
                    "funding_rate": 0.0,
                    "funding_sample_count": 0.0,
                },
                {
                    "timestamp_ms": 2 * 86_400_000,
                    "subject": "BTC",
                    "score": 1.0,
                    "has_perp": True,
                    "usdm_symbol": "BTCUSDT",
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": 0,
                    "perp_close": 121.0,
                    "perp_quote_volume_usd": 5_000_000.0,
                    "open_interest_value": 10_000_000.0,
                    "funding_rate": 0.0,
                    "funding_sample_count": 0.0,
                },
                {
                    "timestamp_ms": 2 * 86_400_000,
                    "subject": "SHIB",
                    "score": 12.0,
                    "has_perp": False,
                    "usdm_symbol": None,
                    "perp_execution_eligible": False,
                    "perp_executable_start_ms": None,
                    "perp_close": None,
                    "perp_quote_volume_usd": None,
                    "open_interest_value": None,
                    "funding_rate": 0.0,
                    "funding_sample_count": 0.0,
                },
            ]
        )
        metrics = backtest_cross_sectional(
            frame=frame,
            constraints={
                "execution_venue": "perp",
                "short_allowed": False,
                "long_leverage": 1.0,
                "strategy_profile": "balanced",
            },
            split_realization_contract={
                "bar_interval_ms": 86_400_000,
                "realization_step_bars": 1,
            },
            execution_cost_model={
                "contract_version": "quant_execution_cost_model.v1",
                "scenario": "base",
                "latency_bars": 1,
                "spot_short_borrow_bps_per_day": 15.0,
                "liquidity_volume_scale": 1.0,
                "venues": {
                    "spot": {
                        "fee_bps_one_way": 0.0,
                        "half_spread_bps": 0.0,
                        "impact_coefficient_bps": 0.0,
                    },
                    "perp": {
                        "fee_bps_one_way": 0.0,
                        "half_spread_bps": 0.0,
                        "impact_coefficient_bps": 0.0,
                    },
                },
            },
            reference_capital_usd=100_000.0,
            capacity_limits={
                "max_trade_participation_rate_max": 1.0,
                "max_inventory_participation_rate_max": 1.0,
            },
        )
        self.assertGreater(metrics["rebalance_count"], 0)
        self.assertFalse(any("SHIB" in blocker for blocker in metrics["data_gap_blockers"]))
        self.assertEqual(metrics["execution_venue"], "perp")

    def test_cross_sectional_target_weights_constructs_pairs_within_quality_buckets(self) -> None:
        decision_group = pd.DataFrame(
            [
                {
                    "subject": "L1",
                    "score": 0.90,
                    "relative_strength_20": 0.20,
                    "ema_slope_5_20": 0.15,
                    "distance_to_low_20": 0.08,
                    "intraday_realized_vol_4h_to_1d": 0.04,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "S1",
                    "score": -0.85,
                    "relative_strength_20": 0.22,
                    "ema_slope_5_20": 0.14,
                    "distance_to_low_20": 0.07,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "L2",
                    "score": 0.70,
                    "relative_strength_20": 0.05,
                    "ema_slope_5_20": 0.04,
                    "distance_to_low_20": 0.03,
                    "intraday_realized_vol_4h_to_1d": 0.06,
                    "realized_volatility_20": 0.07,
                },
                {
                    "subject": "S2",
                    "score": -0.75,
                    "relative_strength_20": 0.06,
                    "ema_slope_5_20": 0.03,
                    "distance_to_low_20": 0.02,
                    "intraday_realized_vol_4h_to_1d": 0.06,
                    "realized_volatility_20": 0.07,
                },
            ]
        )
        weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                "execution_venue": "perp",
                "spot_only": False,
                "long_only": False,
                "short_allowed": True,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "pair_construction": "quality_bucket_pairs",
                "pair_bucket_count": 4,
                "pair_count": 2,
                "pair_score_spread_min": 0.08,
                "pair_quality_floor": 0.0,
            },
        )
        self.assertAlmostEqual(sum(weight for weight in weights.values() if weight > 0.0), 0.5)
        self.assertAlmostEqual(sum(-weight for weight in weights.values() if weight < 0.0), 0.5)
        self.assertIn("L1", weights)
        self.assertIn("S1", weights)

    def test_cross_sectional_target_weights_can_require_strong_second_pair(self) -> None:
        decision_group = pd.DataFrame(
            [
                {
                    "subject": "L1",
                    "score": 0.90,
                    "relative_strength_20": 0.20,
                    "ema_slope_5_20": 0.15,
                    "distance_to_low_20": 0.08,
                    "intraday_realized_vol_4h_to_1d": 0.04,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "S1",
                    "score": -0.85,
                    "relative_strength_20": 0.22,
                    "ema_slope_5_20": 0.14,
                    "distance_to_low_20": 0.07,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "L2",
                    "score": 0.58,
                    "relative_strength_20": 0.05,
                    "ema_slope_5_20": 0.04,
                    "distance_to_low_20": 0.03,
                    "intraday_realized_vol_4h_to_1d": 0.06,
                    "realized_volatility_20": 0.07,
                },
                {
                    "subject": "S2",
                    "score": -0.32,
                    "relative_strength_20": 0.06,
                    "ema_slope_5_20": 0.03,
                    "distance_to_low_20": 0.02,
                    "intraday_realized_vol_4h_to_1d": 0.06,
                    "realized_volatility_20": 0.07,
                },
            ]
        )
        unconstrained = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                "execution_venue": "perp",
                "spot_only": False,
                "long_only": False,
                "short_allowed": True,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "pair_construction": "quality_bucket_pairs",
                "pair_bucket_count": 4,
                "pair_count": 2,
                "pair_score_spread_min": 0.08,
                "pair_quality_floor": 0.0,
            },
        )
        constrained = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                "execution_venue": "perp",
                "spot_only": False,
                "long_only": False,
                "short_allowed": True,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "pair_construction": "quality_bucket_pairs",
                "pair_bucket_count": 4,
                "pair_count": 2,
                "pair_score_spread_min": 0.08,
                "pair_quality_floor": 0.0,
                "pair_additional_strength_ratio_min": 0.90,
            },
        )
        self.assertEqual(set(unconstrained), {"L1", "S1", "L2", "S2"})
        self.assertEqual(set(constrained), {"L1", "S1"})

    def test_cross_sectional_target_weights_can_buffer_pair_switches(self) -> None:
        decision_group = pd.DataFrame(
            [
                {
                    "subject": "A",
                    "score": 0.60,
                    "relative_strength_20": 0.90,
                    "ema_slope_5_20": 0.90,
                    "distance_to_low_20": 0.90,
                    "intraday_realized_vol_4h_to_1d": 0.10,
                    "realized_volatility_20": 0.10,
                },
                {
                    "subject": "B",
                    "score": 0.00,
                    "relative_strength_20": 0.85,
                    "ema_slope_5_20": 0.85,
                    "distance_to_low_20": 0.85,
                    "intraday_realized_vol_4h_to_1d": 0.10,
                    "realized_volatility_20": 0.10,
                },
                {
                    "subject": "C",
                    "score": 0.80,
                    "relative_strength_20": 0.10,
                    "ema_slope_5_20": 0.10,
                    "distance_to_low_20": 0.10,
                    "intraday_realized_vol_4h_to_1d": 0.10,
                    "realized_volatility_20": 0.10,
                },
                {
                    "subject": "D",
                    "score": 0.10,
                    "relative_strength_20": 0.05,
                    "ema_slope_5_20": 0.05,
                    "distance_to_low_20": 0.05,
                    "intraday_realized_vol_4h_to_1d": 0.10,
                    "realized_volatility_20": 0.10,
                },
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        unconstrained = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints=base_constraints,
            previous_weights={"A": 0.5, "B": -0.5},
        )
        buffered = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                **base_constraints,
                "pair_switch_strength_ratio_min": 1.50,
            },
            previous_weights={"A": 0.5, "B": -0.5},
        )

        self.assertEqual(set(unconstrained), {"B", "C"})
        self.assertEqual(set(buffered), {"A", "B"})

    def test_cross_sectional_target_weights_can_soft_scale_shorts_in_broad_trend(self) -> None:
        decision_group = pd.DataFrame(
            [
                {
                    "subject": "L1",
                    "score": 0.90,
                    "momentum_20": 0.18,
                    "relative_strength_20": 0.80,
                    "ema_slope_5_20": 0.06,
                    "distance_to_low_20": 0.70,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "S1",
                    "score": -0.70,
                    "momentum_20": 0.14,
                    "relative_strength_20": 0.55,
                    "ema_slope_5_20": 0.05,
                    "distance_to_low_20": 0.52,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
            ]
        )
        base_constraints = {
            "pair_construction": "quality_bucket_pairs",
            "pair_bucket_count": 2,
            "pair_count": 1,
            "pair_score_spread_min": 0.08,
            "pair_quality_floor": 0.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "short_allowed": True,
        }
        uncapped = _cross_sectional_target_weights(decision_group=decision_group, constraints=base_constraints)
        softened = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                **base_constraints,
                "pair_market_momentum_soft_threshold": 0.05,
                "pair_market_ema_soft_threshold": 0.015,
                "pair_market_trend_short_scale": 0.75,
            },
        )
        self.assertAlmostEqual(softened["L1"], uncapped["L1"])
        self.assertLess(abs(softened["S1"]), abs(uncapped["S1"]))

    def test_cross_sectional_target_weights_can_filter_extreme_trend_crowding(self) -> None:
        decision_group = pd.DataFrame(
            [
                {
                    "subject": "L1",
                    "score": 0.90,
                    "relative_strength_20": 0.95,
                    "ema_slope_5_20": 0.80,
                    "distance_to_low_20": 0.80,
                    "intraday_realized_vol_4h_to_1d": 0.04,
                    "realized_volatility_20": 0.04,
                },
                {
                    "subject": "S1",
                    "score": -0.85,
                    "relative_strength_20": 0.88,
                    "ema_slope_5_20": 0.72,
                    "distance_to_low_20": 0.75,
                    "intraday_realized_vol_4h_to_1d": 0.04,
                    "realized_volatility_20": 0.04,
                },
                {
                    "subject": "L2",
                    "score": 0.70,
                    "relative_strength_20": 0.20,
                    "ema_slope_5_20": 0.12,
                    "distance_to_low_20": 0.18,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "S2",
                    "score": -0.75,
                    "relative_strength_20": 0.19,
                    "ema_slope_5_20": 0.11,
                    "distance_to_low_20": 0.17,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "L3",
                    "score": 0.60,
                    "relative_strength_20": 0.18,
                    "ema_slope_5_20": 0.10,
                    "distance_to_low_20": 0.16,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
                {
                    "subject": "S3",
                    "score": -0.65,
                    "relative_strength_20": 0.17,
                    "ema_slope_5_20": 0.09,
                    "distance_to_low_20": 0.15,
                    "intraday_realized_vol_4h_to_1d": 0.05,
                    "realized_volatility_20": 0.05,
                },
            ]
        )
        weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints={
                "execution_venue": "perp",
                "spot_only": False,
                "long_only": False,
                "short_allowed": True,
                "long_leverage": 0.5,
                "short_leverage": 0.5,
                "pair_construction": "quality_bucket_pairs",
                "pair_bucket_count": 2,
                "pair_count": 1,
                "pair_score_spread_min": 0.08,
                "pair_quality_floor": 0.0,
                "pair_trend_crowding_max": 0.85,
            },
        )
        self.assertNotIn("L1", weights)
        self.assertIn("L2", weights)
        self.assertIn("S1", weights)


if __name__ == "__main__":
    unittest.main()
