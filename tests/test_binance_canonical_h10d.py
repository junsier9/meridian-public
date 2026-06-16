from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

import pandas as pd

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.binance_canonical_h10d import (
    ALLOWED_ALPHA_FEATURES,
    aggregate_1m_klines,
    apply_point_in_time_rolling_universe,
    apply_selected_path_gap_symbol_exclusion,
    attach_funding_cost_to_panel,
    build_paper_shadow_execution_ledger,
    build_symbol_feature_frame,
    compute_factor_leave_one_out_attribution,
    compute_position_attribution,
    freeze_binance_ohlcv_universe,
    load_funding_cost_daily,
    prepare_scored_backtest_frame,
    run_binance_core_ablations,
    score_binance_ohlcv_core,
    sync_funding_cost_history,
    validate_alpha_feature_columns,
    _funding_cost_status,
    _paper_shadow_action,
    _row_float,
    _run_backtest,
    _run_falsification_suite,
    _run_stratified_repeated_symbol_holdout,
    _subjects_from_data_gap_blockers,
    _validation_status,
    add_binance_risk_brake_columns,
)
from enhengclaw.quant_research.execution_backtest import _trade_costs


class BinanceCanonicalH10DTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="binance-canonical-h10d-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_aggregation_keeps_only_complete_minute_buckets(self) -> None:
        complete = _minute_frame(symbol="BTCUSDT", start=datetime(2026, 1, 1, tzinfo=UTC), minutes=60)
        aggregated = aggregate_1m_klines(complete, interval="1h")
        self.assertEqual(len(aggregated), 1)
        self.assertTrue(bool(aggregated.iloc[0]["bar_complete"]))
        self.assertEqual(int(aggregated.iloc[0]["trade_count"]), int(complete["trade_count"].sum()))

        missing_one = complete.iloc[:-1].copy()
        self.assertTrue(aggregate_1m_klines(missing_one, interval="1h").empty)
        audited = aggregate_1m_klines(missing_one, interval="1h", drop_incomplete=False)
        self.assertFalse(bool(audited.iloc[0]["bar_complete"]))
        self.assertEqual(int(audited.iloc[0]["observed_minute_row_count"]), 59)

    def test_feature_purity_rejects_sidecar_and_derivatives_alpha_columns(self) -> None:
        result = validate_alpha_feature_columns(
            [
                *ALLOWED_ALPHA_FEATURES,
                "coinglass_top_trader_long_pct_smooth_5",
                "open_interest_value",
                "funding_basis_residual_implied_repo_30",
            ]
        )
        self.assertFalse(result["passed"])
        self.assertIn("coinglass_top_trader_long_pct_smooth_5", result["forbidden_columns"])
        self.assertIn("open_interest_value", result["forbidden_columns"])
        self.assertIn("funding_basis_residual_implied_repo_30", result["forbidden_columns"])

    def test_feature_purity_allows_preregistered_canonical_subset(self) -> None:
        subset = [
            "intraday_realized_vol_4h_to_1d_smooth_60",
            "realized_volatility_5",
            "distance_to_high_60",
            "distance_to_high_5",
            "downside_upside_vol_ratio_30",
        ]

        strict = validate_alpha_feature_columns(subset)
        pruned = validate_alpha_feature_columns(subset, require_all_allowed=False)

        self.assertFalse(strict["passed"])
        self.assertTrue(pruned["passed"])
        self.assertIn("settlement_cycle_premium_60d", pruned["missing_columns"])

    def test_score_uses_only_allowed_feature_columns(self) -> None:
        frame = pd.DataFrame(
            [
                _feature_row("BTC", 0, 0.1),
                _feature_row("ETH", 0, 0.2),
                _feature_row("SOL", 0, 0.3),
                _feature_row("BTC", 86_400_000, 0.2),
                _feature_row("ETH", 86_400_000, 0.1),
                _feature_row("SOL", 86_400_000, 0.4),
            ]
        )
        baseline = score_binance_ohlcv_core(frame)
        contaminated = frame.copy()
        contaminated["coinglass_top_trader_long_pct_smooth_5"] = [999, -999, 500, -500, 123, -123]
        repeated = score_binance_ohlcv_core(contaminated)
        pd.testing.assert_series_equal(baseline, repeated)

    def test_prepare_scored_frame_drops_non_core_sidecar_columns(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    **_feature_row("BTC", 0, 0.1),
                    "target_execution_forward_return": 0.02,
                    "target_forward_return": 0.01,
                    "target_up": 1,
                    "target_execution_up": 1,
                    "date_utc": "2026-01-01",
                    "usdm_symbol": "BTCUSDT",
                    "liquidity_bucket": "top_liquidity",
                    "perp_close": 100.0,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "coinglass_top_trader_long_pct_smooth_5": 999.0,
                    "taker_buy_quote_volume": 123.0,
                },
                {
                    **_feature_row("ETH", 0, 0.2),
                    "target_execution_forward_return": -0.01,
                    "target_forward_return": -0.02,
                    "target_up": 0,
                    "target_execution_up": 0,
                    "date_utc": "2026-01-01",
                    "usdm_symbol": "ETHUSDT",
                    "liquidity_bucket": "top_liquidity",
                    "perp_close": 50.0,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "coinglass_top_trader_long_pct_smooth_5": -999.0,
                    "taker_buy_quote_volume": 456.0,
                },
                {
                    **_feature_row("SOL", 0, 0.3),
                    "target_execution_forward_return": 0.01,
                    "target_forward_return": 0.01,
                    "target_up": 1,
                    "target_execution_up": 1,
                    "date_utc": "2026-01-01",
                    "usdm_symbol": "SOLUSDT",
                    "liquidity_bucket": "mid_liquidity",
                    "perp_close": 25.0,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "coinglass_top_trader_long_pct_smooth_5": 500.0,
                    "taker_buy_quote_volume": 789.0,
                },
            ]
        )
        scored, audit = prepare_scored_backtest_frame(frame)
        self.assertEqual(audit["blockers"], [])
        self.assertIn("score", scored.columns)
        self.assertNotIn("coinglass_top_trader_long_pct_smooth_5", scored.columns)
        self.assertNotIn("taker_buy_quote_volume", scored.columns)

    def test_pit_top_mid_eligibility_uses_recent_visible_completeness(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        rows = []
        for day in range(2):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            for subject, bucket in (("BTC", "top_liquidity"), ("SOL", "mid_liquidity")):
                rows.append(
                    {
                        **_feature_row(subject, timestamp_ms, 0.1 + day * 0.01),
                        "target_execution_forward_return": 0.02,
                        "target_forward_return": 0.01,
                        "target_up": 1,
                        "target_execution_up": 1,
                        "date_utc": (start + timedelta(days=day)).date().isoformat(),
                        "usdm_symbol": f"{subject}USDT",
                        "liquidity_bucket": bucket,
                        "universe_active": True,
                        "universe_rank": 1 if bucket == "top_liquidity" else 11,
                        "perp_close": 100.0,
                        "perp_quote_volume_usd": 1_000_000.0,
                        "funding_rate": 0.0,
                        "funding_sample_count": 3,
                    }
                )
        config = {
            "pit_data_eligibility_policy": {
                "mode": "rolling_recent_completeness",
                "lookback_days": 2,
                "min_coverage_ratio": 1.0,
                "min_consecutive_valid_days": 2,
                "min_same_bucket_days": 2,
                "require_current_funding_sample": True,
                "min_funding_sample_count": 1,
            }
        }

        scored, audit = prepare_scored_backtest_frame(pd.DataFrame(rows), config=config)

        self.assertEqual(audit["blockers"], [])
        first_day = scored.loc[scored["timestamp_ms"].eq(int(start.timestamp() * 1000))]
        second_day = scored.loc[scored["timestamp_ms"].eq(int((start + timedelta(days=1)).timestamp() * 1000))]
        self.assertFalse(first_day["binance_pit_data_eligible"].any())
        self.assertTrue(second_day["binance_pit_data_eligible"].all())
        second_by_subject = second_day.set_index("subject")
        self.assertTrue(bool(second_by_subject.loc["BTC", "binance_pit_top_long_eligible"]))
        self.assertFalse(bool(second_by_subject.loc["BTC", "binance_pit_mid_short_eligible"]))
        self.assertFalse(bool(second_by_subject.loc["SOL", "binance_pit_top_long_eligible"]))
        self.assertTrue(bool(second_by_subject.loc["SOL", "binance_pit_mid_short_eligible"]))

    def test_pit_mid_short_eligibility_requires_visible_bucket_stability(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        rows = []
        for day, bucket in enumerate(["top_liquidity", "mid_liquidity", "mid_liquidity"]):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            rows.append(
                {
                    **_feature_row("SOL", timestamp_ms, 0.1 + day * 0.01),
                    "target_execution_forward_return": 0.02,
                    "target_forward_return": 0.01,
                    "target_up": 1,
                    "target_execution_up": 1,
                    "date_utc": (start + timedelta(days=day)).date().isoformat(),
                    "usdm_symbol": "SOLUSDT",
                    "liquidity_bucket": bucket,
                    "universe_active": True,
                    "universe_rank": 5 if bucket == "top_liquidity" else 11,
                    "perp_close": 100.0,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "funding_rate": 0.0,
                    "funding_sample_count": 3,
                }
            )
        config = {
            "pit_data_eligibility_policy": {
                "mode": "rolling_recent_completeness",
                "lookback_days": 2,
                "min_coverage_ratio": 1.0,
                "min_consecutive_valid_days": 2,
                "min_same_bucket_days": 2,
                "require_current_funding_sample": True,
                "min_funding_sample_count": 1,
            }
        }

        scored, audit = prepare_scored_backtest_frame(pd.DataFrame(rows), config=config)

        self.assertEqual(audit["blockers"], [])
        by_day = scored.set_index("date_utc")
        self.assertFalse(bool(by_day.loc["2026-01-02", "binance_pit_mid_short_eligible"]))
        self.assertTrue(bool(by_day.loc["2026-01-03", "binance_pit_mid_short_eligible"]))
        self.assertEqual(float(by_day.loc["2026-01-02", "pit_recent_mid_bucket_day_count"]), 1.0)
        self.assertEqual(float(by_day.loc["2026-01-03", "pit_recent_mid_bucket_day_count"]), 2.0)

    def test_pit_mid_short_eligibility_can_exclude_edge_rank_symbols(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        rows = []
        for day in range(2):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            rows.append(
                {
                    **_feature_row("EDGE", timestamp_ms, 0.1 + day * 0.01),
                    "target_execution_forward_return": 0.02,
                    "target_forward_return": 0.01,
                    "target_up": 1,
                    "target_execution_up": 1,
                    "date_utc": (start + timedelta(days=day)).date().isoformat(),
                    "usdm_symbol": "EDGEUSDT",
                    "liquidity_bucket": "mid_liquidity",
                    "universe_active": True,
                    "universe_rank": 19,
                    "perp_close": 100.0,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "funding_rate": 0.0,
                    "funding_sample_count": 3,
                }
            )
        config = {
            "pit_data_eligibility_policy": {
                "mode": "rolling_recent_completeness",
                "lookback_days": 2,
                "min_coverage_ratio": 1.0,
                "min_consecutive_valid_days": 2,
                "min_same_bucket_days": 2,
                "short_max_universe_rank": 18,
                "require_current_funding_sample": True,
                "min_funding_sample_count": 1,
            }
        }

        scored, audit = prepare_scored_backtest_frame(pd.DataFrame(rows), config=config)

        self.assertEqual(audit["blockers"], [])
        second = scored.loc[scored["date_utc"].eq("2026-01-02")].iloc[0]
        self.assertTrue(bool(second["binance_pit_data_eligible"]))
        self.assertFalse(bool(second["binance_pit_mid_short_eligible"]))

    def test_pit_data_eligibility_requires_point_in_time_lifetime_history(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        rows = []
        for day in range(2):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            rows.append(
                {
                    **_feature_row("NEW", timestamp_ms, 0.1 + day * 0.01),
                    "target_execution_forward_return": 0.02,
                    "target_forward_return": 0.01,
                    "target_up": 1,
                    "target_execution_up": 1,
                    "date_utc": (start + timedelta(days=day)).date().isoformat(),
                    "usdm_symbol": "NEWUSDT",
                    "liquidity_bucket": "mid_liquidity",
                    "universe_active": True,
                    "universe_rank": 12,
                    "perp_close": 100.0,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "funding_rate": 0.0,
                    "funding_sample_count": 3,
                }
            )
        config = {
            "pit_data_eligibility_policy": {
                "mode": "rolling_recent_completeness",
                "lookback_days": 2,
                "min_coverage_ratio": 1.0,
                "min_consecutive_valid_days": 2,
                "min_lifetime_valid_days": 3,
                "require_current_funding_sample": True,
                "min_funding_sample_count": 1,
            }
        }

        scored, audit = prepare_scored_backtest_frame(pd.DataFrame(rows), config=config)

        self.assertEqual(audit["blockers"], [])
        second = scored.loc[scored["date_utc"].eq("2026-01-02")].iloc[0]
        self.assertEqual(float(second["pit_lifetime_valid_day_count"]), 2.0)
        self.assertFalse(bool(second["binance_pit_data_eligible"]))
        self.assertFalse(bool(second["binance_pit_mid_short_eligible"]))

    def test_liquidity_bucket_falsification_filters_decisions_not_execution_path(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        rows = []
        for day in range(5):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "date_utc": (start + timedelta(days=day)).date().isoformat(),
                    "subject": "ROTATE",
                    "usdm_symbol": "ROTATEUSDT",
                    "score": 1.0,
                    "perp_close": 100.0 + day,
                    "perp_quote_volume_usd": 1_000_000.0,
                    "has_perp": True,
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": int(start.timestamp() * 1000),
                    "funding_rate": 0.0,
                    "funding_sample_count": 3.0,
                    "liquidity_bucket": "top_liquidity" if day == 0 else "mid_liquidity",
                    "universe_active": True,
                    "binance_decision_eligible": True,
                    "target_execution_forward_return": 0.01,
                }
            )
        config = _test_config()
        config["strategy_profile"] = {
            **config["strategy_profile"],
            "short_allowed": False,
            "top_long_count": 1,
            "bottom_short_count": 0,
        }
        config["split_realization"] = {"interval": "1d", "target_horizon_bars": 2}

        suite = _run_falsification_suite(pd.DataFrame(rows), config=config)
        top_bucket = suite["liquidity_bucket"]["top_liquidity"]

        self.assertEqual(top_bucket["bucket_path_policy"], "decision_time_bucket_full_execution_path")
        self.assertEqual(top_bucket["data_gap_blockers"], [])
        self.assertGreater(float(top_bucket["turnover"]), 0.0)

    def test_falsification_suite_marks_legacy_holdout_diagnostic(self) -> None:
        frame = _scored_price_panel(days=12)
        config = _test_config()
        config["validation_gates"] = {"stratified_holdout_repeat_count": 1}

        suite = _run_falsification_suite(frame, config=config)

        self.assertEqual(suite["symbol_holdout_role"], "diagnostic")
        self.assertTrue(all(item["role"] == "diagnostic" for item in suite["symbol_holdout"].values()))
        self.assertIn("stratified_repeated_symbol_holdout", suite)
        self.assertEqual(suite["stratified_repeated_symbol_holdout"]["summary"]["fold_count"], 2)

    def test_stratified_holdout_direct_smoke_keeps_policy_and_fold_shape(self) -> None:
        frame = _scored_price_panel(days=12)
        config = _test_config()
        config["validation_gates"] = {
            "stratified_holdout_repeat_count": 1,
            "stratified_holdout_min_positive_fraction": 0.50,
            "stratified_holdout_require_gap_free": False,
        }

        holdout = _run_stratified_repeated_symbol_holdout(frame, config=config)

        self.assertEqual(holdout["summary"]["status"], "ok")
        self.assertEqual(holdout["summary"]["fold_count"], 2)
        self.assertEqual(holdout["policy"]["repeat_count"], 1)
        self.assertEqual(holdout["policy"]["min_positive_fraction"], 0.50)
        self.assertFalse(holdout["policy"]["require_gap_free"])
        self.assertTrue(all(item["subjects"] for item in holdout["folds"]))
        self.assertTrue(all("stratum_counts" in item for item in holdout["folds"]))

    def test_run_backtest_wrapper_smoke_keeps_scenario_and_period_shape(self) -> None:
        frame = _scored_price_panel(days=12)
        config = _test_config()

        base = _run_backtest(frame, config=config, scenario="base", include_periods=True)
        stress = _run_backtest(frame, config=config, scenario="stress", include_periods=False)

        for metrics in (base, stress):
            with self.subTest(scenario=metrics.get("scenario")):
                self.assertIn("net_return", metrics)
                self.assertIn("max_drawdown", metrics)
                self.assertIn("max_trade_participation_rate", metrics)
                self.assertIn("capacity_breach_count", metrics)
                self.assertEqual(metrics["data_gap_blockers"], [])
        self.assertTrue(base.get("periods"))
        self.assertNotIn("periods", stress)

    def test_validation_status_uses_stratified_holdout_as_hard_gate(self) -> None:
        status, gate_results = _validation_status(
            metrics=_passing_metrics(),
            falsification={
                "liquidity_bucket": _passing_liquidity_buckets(),
                "symbol_holdout": {
                    "holdout_a": {"metrics": {"net_return": 0.10}},
                    "holdout_b": {"metrics": {"net_return": -0.10}},
                },
                "stratified_repeated_symbol_holdout": {
                    "policy": {"min_positive_fraction": 0.75, "require_gap_free": True},
                    "summary": {
                        "fold_count": 4,
                        "positive_fold_count": 3,
                        "gap_free_fold_count": 4,
                        "positive_fraction": 0.75,
                    },
                },
            },
            blockers=[],
            config=_test_config(),
        )

        self.assertEqual(status, "passed")
        self.assertEqual(gate_results["holdout_gate_role"], "diagnostic")
        self.assertFalse(gate_results["holdout_positive_gate"])
        self.assertTrue(gate_results["stratified_holdout_gate"])

    def test_validation_status_fails_when_stratified_holdout_has_gaps(self) -> None:
        status, gate_results = _validation_status(
            metrics=_passing_metrics(),
            falsification={
                "liquidity_bucket": _passing_liquidity_buckets(),
                "symbol_holdout": {
                    "holdout_a": {"metrics": {"net_return": 0.10}},
                    "holdout_b": {"metrics": {"net_return": 0.20}},
                },
                "stratified_repeated_symbol_holdout": {
                    "policy": {"min_positive_fraction": 0.75, "require_gap_free": True},
                    "summary": {
                        "fold_count": 4,
                        "positive_fold_count": 4,
                        "gap_free_fold_count": 3,
                        "positive_fraction": 1.0,
                    },
                },
            },
            blockers=[],
            config=_test_config(),
        )

        self.assertEqual(status, "failed")
        self.assertFalse(gate_results["stratified_holdout_gap_gate"])
        self.assertFalse(gate_results["stratified_holdout_gate"])

    def test_universe_freeze_uses_quote_volume_without_open_interest(self) -> None:
        rows = []
        start = datetime(2026, 1, 1, tzinfo=UTC)
        for day in range(5):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            rows.extend(
                [
                    _panel_row("BTC", "BTCUSDT", timestamp_ms, 100_000_000),
                    _panel_row("ETH", "ETHUSDT", timestamp_ms, 90_000_000),
                    _panel_row("DOGE", "DOGEUSDT", timestamp_ms, 20_000_000),
                ]
            )
        universe = freeze_binance_ohlcv_universe(
            pd.DataFrame(rows),
            as_of="2026-01-05",
            top_n=2,
            coverage_threshold=1.0,
            lookback_days=3,
        )
        self.assertEqual([item["symbol"] for item in universe], ["BTCUSDT", "ETHUSDT"])
        self.assertTrue(all(item["selection_rule"] == "binance_perp_quote_volume_only" for item in universe))

    def test_pit_rolling_universe_uses_only_point_in_time_quote_volume(self) -> None:
        rows = []
        start = datetime(2026, 1, 1, tzinfo=UTC)
        daily_qv = {
            "BTC": [100.0, 100.0],
            "ETH": [1.0, 1_000.0],
        }
        for subject, volumes in daily_qv.items():
            for day, quote_volume in enumerate(volumes):
                timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
                rows.append(_panel_row(subject, f"{subject}USDT", timestamp_ms, quote_volume))

        selected, universe = apply_point_in_time_rolling_universe(
            pd.DataFrame(rows),
            as_of="2026-01-02",
            top_n=1,
            coverage_threshold=1.0,
            lookback_days=1,
        )

        active = selected.loc[selected["universe_active"]].sort_values("timestamp_ms")
        self.assertEqual(active["usdm_symbol"].tolist(), ["BTCUSDT", "ETHUSDT"])
        self.assertEqual({item["symbol"] for item in universe}, {"BTCUSDT", "ETHUSDT"})
        self.assertTrue((selected.loc[~selected["universe_active"], "liquidity_bucket"] == "not_in_universe").all())

    def test_attribution_exposes_short_leg_loss(self) -> None:
        frame = _scored_price_panel(days=12)
        attribution = compute_position_attribution(frame, config=_test_config())
        side_summary = {item["side"]: item for item in attribution["summary"]["side_summary"]}
        self.assertGreater(side_summary["long"]["gross_contribution"], 0.0)
        self.assertLess(side_summary["short"]["gross_contribution"], 0.0)
        self.assertLess(
            side_summary["short"]["net_before_trade_cost_contribution"],
            side_summary["long"]["net_before_trade_cost_contribution"],
        )

    def test_factor_leave_one_out_reports_realized_metric_deltas(self) -> None:
        frame = _feature_scored_price_panel(days=14)
        attribution = compute_factor_leave_one_out_attribution(frame, config=_test_config())
        rows = attribution["leave_one_out"]

        self.assertEqual(attribution["summary"]["status"], "ok")
        self.assertEqual(set(rows["feature"]), set(_test_config()["feature_columns"]))
        self.assertIn("net_return_delta_baseline_minus_loo", rows.columns)
        self.assertTrue(pd.to_numeric(rows["absolute_weight_share"]).gt(0.0).all())
        self.assertFalse(attribution["by_side"].empty)
        self.assertFalse(attribution["by_side_year"].empty)
        self.assertIn("net_before_trade_cost_contribution_delta_baseline_minus_loo", attribution["by_side"].columns)

    def test_paper_shadow_execution_ledger_records_no_live_orders(self) -> None:
        frame = _scored_price_panel(days=12)
        ledger = build_paper_shadow_execution_ledger(frame, config=_test_config())
        rows = ledger["ledger"]

        self.assertEqual(ledger["summary"]["execution_mode"], "paper_shadow_no_live_orders")
        self.assertFalse(rows.empty)
        self.assertTrue(rows["execution_mode"].eq("paper_shadow_no_live_orders").all())
        self.assertIn("trade_participation_rate", rows.columns)
        self.assertGreater(float(pd.to_numeric(rows["trade_notional_usd"]).sum()), 0.0)
        self.assertEqual(ledger["summary"]["data_gap_blockers"], [])

    def test_paper_shadow_tiny_helpers_use_synthetic_inputs(self) -> None:
        row = pd.Series({"price": "12.5", "bad": "nan"})

        self.assertEqual(_row_float(row, "price"), 12.5)
        self.assertEqual(_row_float(row, "bad"), 0.0)
        self.assertEqual(_row_float(None, "price"), 0.0)
        self.assertEqual(_paper_shadow_action(previous_weight=0.0, target_weight=0.5), "open_long")
        self.assertEqual(_paper_shadow_action(previous_weight=0.5, target_weight=0.0), "close_long")
        self.assertEqual(_paper_shadow_action(previous_weight=-0.5, target_weight=0.5), "flip_to_long")
        self.assertEqual(_paper_shadow_action(previous_weight=0.25, target_weight=0.5), "increase_long")
        self.assertEqual(_paper_shadow_action(previous_weight=-0.75, target_weight=-0.25), "reduce_short")

    def test_ablation_runner_reports_long_only_short_disabled_and_short_veto(self) -> None:
        frame = _scored_price_panel(days=12)
        ablations = run_binance_core_ablations(frame, config=_test_config())
        self.assertIn("long_only_gross_1x", ablations["summary"])
        self.assertIn("short_disabled_cash_half", ablations["summary"])
        self.assertIn("short_veto_ohlcv_squeeze_guard", ablations["summary"])
        self.assertIn("core20_long_noncore_mid_short", ablations["summary"])
        self.assertIn("core20_short_disabled", ablations["summary"])
        self.assertFalse(ablations["period_returns"].empty)

    def test_risk_brake_columns_are_retained_without_entering_alpha_features(self) -> None:
        frame = _feature_scored_price_panel(days=28)
        config = _test_config()
        config["feature_subset_policy"] = {"allow_pruned_subset": True}
        config["feature_columns"] = [
            "intraday_realized_vol_4h_to_1d_smooth_60",
            "realized_volatility_5",
            "distance_to_high_60",
            "distance_to_high_5",
            "downside_upside_vol_ratio_30",
        ]
        config["strategy_profile"] = {
            **config["strategy_profile"],
            "short_position_weight_multiplier_column": "binance_risk_brake_short_multiplier",
        }
        config["risk_overlay_policy"] = {
            "enabled": True,
            "short_squeeze_brake": {"enabled": True},
            "high_vol_rebound_short_brake": {"enabled": False},
        }

        scored, audit = prepare_scored_backtest_frame(frame, config=config)

        self.assertEqual(audit["blockers"], [])
        self.assertIn("binance_risk_brake_short_multiplier", scored.columns)
        self.assertIn("binance_short_squeeze_veto_multiplier", scored.columns)
        self.assertNotIn("momentum_20", scored.columns)
        self.assertTrue(pd.to_numeric(scored["binance_risk_brake_short_multiplier"], errors="coerce").between(0.0, 1.0).all())

    def test_high_vol_rebound_brake_uses_decision_time_market_state(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        subjects = ["A", "B", "C", "D"]
        rows = []
        for day in range(30):
            timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
            for subject in subjects:
                rows.append(
                    {
                        "timestamp_ms": timestamp_ms,
                        "date_utc": (start + timedelta(days=day)).date().isoformat(),
                        "subject": subject,
                        "universe_active": True,
                        "binance_decision_eligible": True,
                        "realized_volatility_5": 0.01 if day < 24 else 0.10,
                        "momentum_20": 0.0 if day < 24 else 0.06,
                        "distance_to_high_5": -0.20 if day < 24 else -0.01,
                    }
                )
        config = {
            "strategy_profile": {"short_position_weight_multiplier_column": "binance_risk_brake_short_multiplier"},
            "risk_overlay_policy": {
                "enabled": True,
                "short_squeeze_brake": {"enabled": False},
                "high_vol_rebound_short_brake": {
                    "enabled": True,
                    "lookback_decisions": 20,
                    "min_periods": 10,
                    "vol_quantile": 0.5,
                    "min_median_momentum_20": 0.03,
                    "min_positive_momentum_share": 0.6,
                    "min_close_to_high_share": 0.4,
                    "short_multiplier": 0.5,
                },
            },
        }

        braked = add_binance_risk_brake_columns(pd.DataFrame(rows), config=config)

        last_day = braked.loc[braked["date_utc"].eq("2026-01-30")]
        self.assertTrue(last_day["binance_high_vol_rebound_flag"].all())
        self.assertTrue(pd.to_numeric(last_day["binance_risk_brake_short_multiplier"]).le(0.5).all())
        first_day = braked.loc[braked["date_utc"].eq("2026-01-01")]
        self.assertTrue(pd.to_numeric(first_day["binance_risk_brake_short_multiplier"]).eq(1.0).all())

    def test_validation_status_can_hard_fail_drawdown_cap(self) -> None:
        metrics = _passing_metrics()
        metrics["base"]["max_drawdown"] = 0.40
        config = _test_config()
        config["validation_gates"] = {"base_max_drawdown_max": 0.325}

        status, gate_results = _validation_status(
            metrics=metrics,
            falsification={
                "liquidity_bucket": _passing_liquidity_buckets(),
                "stratified_repeated_symbol_holdout": {
                    "policy": {"min_positive_fraction": 0.75, "require_gap_free": True},
                    "summary": {
                        "fold_count": 4,
                        "positive_fold_count": 4,
                        "gap_free_fold_count": 4,
                        "positive_fraction": 1.0,
                    },
                },
            },
            blockers=[],
            config=config,
        )

        self.assertEqual(status, "failed")
        self.assertFalse(gate_results["base_max_drawdown_under_cap"])

    def test_selected_path_gap_policy_excludes_entire_gap_symbols(self) -> None:
        frame = _scored_price_panel(days=12)
        exit_timestamp = frame["timestamp_ms"].max()
        frame = frame.loc[~((frame["subject"] == "S3") & (frame["timestamp_ms"] == exit_timestamp))].copy()
        config = _test_config()
        config["execution_gap_policy"] = {"mode": "drop_selected_path_gap_symbols", "max_iterations": 3}

        cleaned, audit = apply_selected_path_gap_symbol_exclusion(frame, config=config)

        self.assertEqual(audit["status"], "ok")
        self.assertIn("S3", audit["excluded_subjects"])
        self.assertNotIn("S3", set(cleaned["subject"]))
        self.assertEqual(audit["residual_data_gap_blockers"], [])

    def test_gap_policy_subject_parser_uses_only_missing_blocker_prefix(self) -> None:
        blockers = [
            "BTC: missing fill row for execution venue",
            " ETH : missing exit row for execution venue",
            "SOL: no selected-path gap",
            "missing subject prefix",
            "DOGE: missing trade liquidity proxy for perp",
            "",
        ]

        self.assertEqual(_subjects_from_data_gap_blockers(blockers), ["BTC", "ETH", "DOGE"])

    def test_funding_status_ignores_inactive_price_rows(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "subject": "ACTIVE",
                    "universe_active": True,
                    "funding_rate": 0.0001,
                    "funding_sample_count": 3,
                },
                {
                    "subject": "INACTIVE",
                    "universe_active": False,
                    "funding_rate": None,
                    "funding_sample_count": 0,
                },
            ]
        )
        status = _funding_cost_status(frame)
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["coverage_scope"], "universe_active_rows")
        self.assertEqual(status["coverage_ratio"], 1.0)

    def test_perp_trade_cost_can_disable_open_interest_inventory_requirement(self) -> None:
        costs = _trade_costs(
            row=pd.Series({"perp_quote_volume_usd": 100_000_000.0, "perp_close": 100.0}),
            delta_weight=0.10,
            target_weight=0.20,
            execution_venue="perp",
            execution_cost_model={
                "latency_bars": 1,
                "liquidity_volume_scale": 1.0,
                "require_perp_inventory_open_interest": False,
                "venues": {
                    "perp": {
                        "fee_bps_one_way": 6.0,
                        "half_spread_bps": 1.5,
                        "impact_coefficient_bps": 25.0,
                    }
                },
            },
            reference_capital_usd=1_000_000.0,
            capacity_limits={"max_trade_participation_rate_max": 0.005},
            subject="BTC",
        )
        self.assertEqual(costs["data_gap_blockers"], [])
        self.assertAlmostEqual(costs["trade_participation_rate"], 0.001)
        self.assertEqual(costs["capacity_breach_count"], 0)

    def test_symbol_feature_builder_reads_archive_partition_and_marks_daily_coverage(self) -> None:
        store_root = self.temp_dir / "store"
        path = store_root / "data" / "usdm_perp" / "BTCUSDT" / "1m" / "2026-01.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = _minute_frame(symbol="BTCUSDT", start=datetime(2026, 1, 1, tzinfo=UTC), minutes=2 * 24 * 60)
        frame.to_csv(path, index=False, compression="gzip")

        panel, audit = build_symbol_feature_frame(
            store_root=store_root,
            symbol="BTCUSDT",
            as_of="2026-01-02",
            start_month="2026-01",
            end_month="2026-01",
        )

        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["valid_daily_bucket_count"], 2)
        self.assertEqual(len(panel), 2)
        self.assertIn("intraday_realized_vol_4h_to_1d", panel.columns)
        self.assertIn("settlement_cycle_premium_60d", panel.columns)

    def test_funding_cost_sync_writes_daily_cost_only_rows_and_attaches_to_panel(self) -> None:
        funding_root = self.temp_dir / "funding"
        base = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)

        def fake_http(url: str):
            query = parse_qs(urlparse(url).query)
            symbol = query["symbol"][0]
            self.assertEqual(symbol, "BTCUSDT")
            return [
                {"symbol": symbol, "fundingTime": base, "fundingRate": "0.0001"},
                {"symbol": symbol, "fundingTime": base + 8 * 60 * 60 * 1000, "fundingRate": "0.0002"},
                {"symbol": symbol, "fundingTime": base + 16 * 60 * 60 * 1000, "fundingRate": "-0.0001"},
                {"symbol": symbol, "fundingTime": base + 24 * 60 * 60 * 1000, "fundingRate": "0.0003"},
            ]

        summary = sync_funding_cost_history(
            symbols=["BTCUSDT"],
            start="2026-01-01",
            end="2026-01-02",
            funding_root=funding_root,
            http_get_json_fn=fake_http,
        )
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["row_count"], 4)

        daily = load_funding_cost_daily(
            funding_root=funding_root,
            symbols=["BTCUSDT"],
            start_time_ms=base,
            end_time_ms=base + 2 * 86_400_000 - 1,
        )
        self.assertEqual(daily["funding_sample_count"].tolist(), [3, 1])
        self.assertAlmostEqual(float(daily.iloc[0]["funding_rate"]), (0.0001 + 0.0002 - 0.0001) / 3)

        panel = pd.DataFrame(
            [
                {
                    "timestamp_ms": base,
                    "date_utc": "2026-01-01",
                    "subject": "BTC",
                    "usdm_symbol": "BTCUSDT",
                },
                {
                    "timestamp_ms": base + 86_400_000,
                    "date_utc": "2026-01-02",
                    "subject": "BTC",
                    "usdm_symbol": "BTCUSDT",
                },
            ]
        )
        attached = attach_funding_cost_to_panel(panel, funding_root=funding_root)
        self.assertEqual(attached["funding_sample_count"].tolist(), [3, 1])
        self.assertIn("funding_rate", attached.columns)


def _minute_frame(*, symbol: str, start: datetime, minutes: int) -> pd.DataFrame:
    rows = []
    base_ms = int(start.timestamp() * 1000)
    for offset in range(minutes):
        open_time_ms = base_ms + offset * 60_000
        price = 100.0 + offset * 0.001
        rows.append(
            {
                "exchange": "binance",
                "market_type": "usdm_perp",
                "symbol": symbol,
                "interval": "1m",
                "open_time_ms": open_time_ms,
                "close_time_ms": open_time_ms + 59_999,
                "open": price,
                "high": price + 0.05,
                "low": price - 0.05,
                "close": price + 0.01,
                "volume": 10.0,
                "quote_volume": 1_000.0 + offset,
                "trade_count": 3,
                "taker_buy_base_volume": 5.0,
                "taker_buy_quote_volume": 500.0,
                "source": "fixture",
            }
        )
    return pd.DataFrame(rows)


def _feature_row(subject: str, timestamp_ms: int, base: float) -> dict:
    return {
        "subject": subject,
        "timestamp_ms": timestamp_ms,
        "intraday_realized_vol_4h_to_1d_smooth_60": base,
        "realized_volatility_5": base + 0.01,
        "distance_to_high_60": base + 0.02,
        "distance_to_high_5": base + 0.03,
        "liquidity_stress_qv_iv": base + 0.04,
        "momentum_decay_5_20": base + 0.05,
        "downside_upside_vol_ratio_30": base + 0.06,
        "settlement_cycle_premium_60d": base + 0.07,
    }


def _panel_row(subject: str, symbol: str, timestamp_ms: int, quote_volume: float) -> dict:
    return {
        "subject": subject,
        "usdm_symbol": symbol,
        "timestamp_ms": timestamp_ms,
        "perp_close": 100.0,
        "perp_quote_volume_usd": quote_volume,
    }


def _scored_price_panel(*, days: int) -> pd.DataFrame:
    subjects = ["L1", "L2", "L3", "S1", "S2", "S3"]
    scores = {"L1": 3.0, "L2": 2.0, "L3": 1.0, "S1": -1.0, "S2": -2.0, "S3": -3.0}
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for day in range(days):
        timestamp_ms = int((start + timedelta(days=day)).timestamp() * 1000)
        for subject in subjects:
            is_short_leg = subject.startswith("S")
            price = 100.0 * (1.0 + (0.05 if is_short_leg else 0.01) * day)
            rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "date_utc": (start + timedelta(days=day)).date().isoformat(),
                    "subject": subject,
                    "usdm_symbol": f"{subject}USDT",
                    "score": scores[subject],
                    "perp_close": price,
                    "perp_quote_volume_usd": 100_000_000.0,
                    "has_perp": True,
                    "perp_execution_eligible": True,
                    "perp_executable_start_ms": int(start.timestamp() * 1000),
                    "funding_rate": 0.0,
                    "funding_sample_count": 3.0,
                    "liquidity_bucket": "top_liquidity",
                    "universe_active": True,
                    "binance_decision_eligible": True,
                    "universe_rank": subjects.index(subject) + 1,
                    "realized_volatility_5": 0.10 if is_short_leg else 0.01,
                    "distance_to_high_5": -0.01 if is_short_leg else -0.20,
                    "target_execution_forward_return": 0.0,
                }
            )
    return pd.DataFrame(rows)


def _feature_scored_price_panel(*, days: int) -> pd.DataFrame:
    frame = _scored_price_panel(days=days)
    for index, row in frame.iterrows():
        base = 0.01 * (1 + int(index % 7))
        features = _feature_row(str(row["subject"]), int(row["timestamp_ms"]), base)
        for column, value in features.items():
            if column in {"subject", "timestamp_ms"}:
                continue
            frame.loc[index, column] = value
    return frame


def _test_config() -> dict:
    return {
        "reference_capital_usd": 1_000_000.0,
        "feature_columns": list(ALLOWED_ALPHA_FEATURES),
        "feature_weights": {
            "intraday_realized_vol_4h_to_1d_smooth_60": -0.20,
            "realized_volatility_5": -0.10,
            "distance_to_high_60": 0.18,
            "distance_to_high_5": 0.15,
            "liquidity_stress_qv_iv": -0.10,
            "momentum_decay_5_20": -0.06,
            "downside_upside_vol_ratio_30": 0.10,
            "settlement_cycle_premium_60d": -0.08,
        },
        "strategy_profile": {
            "execution_venue": "perp",
            "short_allowed": True,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "max_turnover_per_rebalance": 1.0,
            "top_long_count": 3,
            "bottom_short_count": 3,
            "decision_eligible_column": "binance_decision_eligible",
        },
        "split_realization": {"interval": "1d", "target_horizon_bars": 10},
        "capacity_limits": {"max_trade_participation_rate_max": 0.005},
    }


def _passing_metrics() -> dict:
    return {
        "base": {
            "net_return": 0.10,
            "sharpe": 1.0,
            "max_trade_participation_rate": 0.001,
            "capacity_breach_count": 0,
        },
        "stress": {"net_return": 0.05, "sharpe": 0.5},
    }


def _passing_liquidity_buckets() -> dict:
    return {
        "top_liquidity": {"net_return": 0.10},
        "mid_liquidity": {"net_return": 0.05},
    }


if __name__ == "__main__":
    unittest.main()
