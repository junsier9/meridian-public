from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import csv
import json
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase4_paired_target_plan_shadow import (  # noqa: E402
    OVERLAY_MULTIPLIER_COLUMN,
    TARGET_FACTOR,
    build_phase4_candidate_panel,
    build_phase_contexts,
    run_phase4_shadow,
)


FEATURE_COLUMNS = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "downside_upside_vol_ratio_30",
]
FEATURE_WEIGHTS = {
    "distance_to_high_5": 0.15,
    "distance_to_high_60": 0.18,
    "downside_upside_vol_ratio_30": 0.1,
    "intraday_realized_vol_4h_to_1d_smooth_60": -0.2,
    "realized_volatility_5": -0.1,
}


class HvBalancedDth60CoinglassPhase4PairedTargetPlanShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase4-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_run_phase4_writes_ready_paired_target_plan_shadow(self) -> None:
        output_root = self.temp_dir / "phase4-artifacts"
        summary, exit_code = run_phase4_shadow(
            self._args(output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 6, 13, 45, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["phase2_pit_proof_loaded"])
        self.assertTrue(summary["phase2b_pit_proof_loaded"])
        self.assertTrue(summary["combined_candidate_trigger_proven"])
        self.assertTrue(summary["phase3_parity_proof_loaded"])
        self.assertTrue(summary["same_timestamp_context_proven"])
        self.assertTrue(summary["same_symbol_set_proven"])
        self.assertTrue(summary["same_portfolio_engine_proven"])
        self.assertTrue(summary["same_risk_inputs_proven"])
        self.assertTrue(summary["deterministic_target_difference_proven"])
        self.assertTrue(summary["no_missing_data_fallbacks_proven"])
        self.assertEqual(summary["baseline_existing_engine_parity_max_abs_target_weight_diff"], 0.0)
        self.assertGreater(summary["target_weight_delta_symbol_count"], 0)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertFalse(summary["mainnet_order_submission_authorized"])
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "target_plan_diff.csv").exists())
        diff_rows = self._read_csv(output_root / "target_plan_diff.csv")
        self.assertGreater(sum(row["changed"] == "True" for row in diff_rows), 0)

    def test_run_phase4_blocks_without_phase3_parity_proof(self) -> None:
        args = self._args(output_root=self.temp_dir / "missing-phase3")
        args.phase3_summary = str(self.temp_dir / "missing_phase3_summary.json")

        summary, exit_code = run_phase4_shadow(
            args,
            now_fn=lambda: datetime(2026, 6, 6, 13, 50, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase3_parity_proof_missing", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertFalse(summary["applied_to_live"])

    def test_run_phase4_blocks_when_candidate_target_plan_has_no_difference(self) -> None:
        args = self._args(output_root=self.temp_dir / "identity-overlay")
        now = datetime(2026, 6, 6, 13, 55, tzinfo=UTC)
        phase_contexts = build_phase_contexts(
            started_at=now,
            rebalance_interval_days=10,
            rebalance_epoch_ms=0,
            phase_cycle_index=-1,
        )
        panel = build_phase4_candidate_panel(
            symbols=self._symbols(),
            feature_columns=FEATURE_COLUMNS,
            phase_contexts=phase_contexts,
            target_factor=TARGET_FACTOR,
            overlay_multiplier_column=OVERLAY_MULTIPLIER_COLUMN,
            overlay_trigger_column="dth60_candidate_overlay_trigger",
        )
        panel[TARGET_FACTOR] = 0.0

        summary, exit_code = run_phase4_shadow(args, now_fn=lambda: now, panel=panel)

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("candidate_target_plan_has_no_deterministic_difference", summary["blockers"])
        self.assertFalse(summary["deterministic_target_difference_proven"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(self, *, output_root: Path) -> Namespace:
        strategy_path = self.temp_dir / "strategy.json"
        strategy_path.write_text(
            json.dumps(
                {
                    "feature_columns": FEATURE_COLUMNS,
                    "feature_weights": FEATURE_WEIGHTS,
                    "feature_subset_policy": {"allow_pruned_subset": True},
                    "pit_data_eligibility_policy": {"mode": "disabled"},
                    "risk_overlay_policy": {"enabled": False, "high_vol_rebound_short_brake": {"enabled": False}},
                    "strategy_label": "v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    "strategy_profile": {
                        "bottom_short_count": 3,
                        "decision_eligible_column": "binance_decision_eligible",
                        "long_decision_eligible_column": "binance_pit_top_long_eligible",
                        "long_leverage": 0.5,
                        "max_gross_leverage": 1.0,
                        "max_turnover_per_rebalance": 1.0,
                        "short_allowed": True,
                        "short_decision_eligible_column": "binance_pit_mid_short_eligible",
                        "short_leverage": 0.5,
                        "short_position_weight_multiplier_column": "binance_risk_brake_short_multiplier",
                        "top_long_count": 3,
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        live_config_path = self.temp_dir / "hv_balanced_live_timer.yaml"
        live_config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    f"  frozen_config_path: {strategy_path.as_posix()}",
                    "  rebalance_interval_days: 10",
                    "binance:",
                    "  venue: usdm_futures",
                    "  max_leverage: 2",
                    "capital:",
                    "  allocated_capital_usdt: 500.0",
                    "risk:",
                    "  max_allocated_capital_usdt: 1000.0",
                    "  max_gross_notional_usdt: 1000.0",
                    "  max_symbol_notional_usdt: 500.0",
                    "market_data:",
                    f"  symbols: {','.join(self._symbols())}",
                    "state:",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        phase2_snapshot = self.temp_dir / "phase2_joined_snapshot.csv"
        phase2_snapshot.write_text(
            "\n".join(
                [
                    "symbol,join_status,provider_timestamp_ms,coinglass_top_trader_long_pct_smooth_5",
                    *[
                        f"{symbol},joined,1780617600000,{50.0 + index}"
                        for index, symbol in enumerate(self._symbols())
                    ],
                ]
            ),
            encoding="utf-8",
        )
        phase2_summary = self.temp_dir / "phase2_summary.json"
        phase2_summary.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "run_id": "phase2-test-proof",
                    "requested_symbol_count": 20,
                    "joined_symbol_count": 20,
                    "no_future_fill_proven": True,
                    "no_stale_fill_proven": True,
                    "no_zero_fill_proven": True,
                    "artifacts": {
                        "joined_snapshot_csv": str(phase2_snapshot),
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        phase2b_snapshot = self.temp_dir / "phase2b_shock_joined_snapshot.csv"
        phase2b_snapshot.write_text(
            "\n".join(
                [
                    "symbol,join_status,provider_timestamp_ms,dth60_shock_branch_trigger,shock_co_occurrence_index,co_jump_count_3d",
                    *[
                        f"{symbol},joined,1780617600000,{str(index < 3)},{0.3 if index < 3 else 0.0},{6 if index < 3 else 0}"
                        for index, symbol in enumerate(self._symbols())
                    ],
                ]
            ),
            encoding="utf-8",
        )
        phase2b_summary = self.temp_dir / "phase2b_summary.json"
        phase2b_summary.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "run_id": "phase2b-test-proof",
                    "requested_symbol_count": 20,
                    "joined_symbol_count": 20,
                    "no_future_fill_proven": True,
                    "no_stale_fill_proven": True,
                    "no_zero_fill_proven": True,
                    "current_row_excluded_from_threshold": True,
                    "train_includes_decision_row": False,
                    "train_future_row_count": 0,
                    "output_files": {
                        "shock_joined_snapshot": str(phase2b_snapshot),
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        phase3_summary = self.temp_dir / "phase3_summary.json"
        phase3_summary.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "run_id": "phase3-test-proof",
                    "blockers": [],
                    "disabled_wrapper_score_matches_core": True,
                    "overlay_enabled_only_target_contribution_changed": True,
                    "phase2_pit_proof_loaded": True,
                    "phase2b_pit_proof_loaded": True,
                    "combined_candidate_trigger_proven": True,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return Namespace(
            config=str(live_config_path),
            strategy_config="",
            symbols="",
            output_root=str(output_root),
            phase2_summary=str(phase2_summary),
            phase2b_summary=str(phase2b_summary),
            phase3_summary=str(phase3_summary),
            allocated_capital_usdt=0.0,
            phase_cycle_index=-1,
            target_factor=TARGET_FACTOR,
            overlay_multiplier_column=OVERLAY_MULTIPLIER_COLUMN,
            overlay_trigger_column="dth60_candidate_overlay_trigger",
            crowded_distance_rank_min=0.75,
            crowded_coinglass_rank_min=0.80,
        )

    def _symbols(self) -> list[str]:
        return [f"SYM{index:02d}USDT" for index in range(1, 21)]

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
