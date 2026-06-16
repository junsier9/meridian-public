from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.binance_canonical_h10d import score_binance_ohlcv_core  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase3_parity import (  # noqa: E402
    OVERLAY_MULTIPLIER_COLUMN,
    TARGET_FACTOR,
    build_deterministic_candidate_panel,
    compute_candidate_score_layer,
    contribution_column_name,
    run_phase3_parity,
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


class HvBalancedDth60CoinglassPhase3ParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase3-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.panel = build_deterministic_candidate_panel(
            symbols=[f"SYM{index:02d}USDT" for index in range(12)],
            feature_columns=FEATURE_COLUMNS,
        )

    def test_disabled_wrapper_matches_core_score(self) -> None:
        disabled = compute_candidate_score_layer(
            self.panel,
            feature_columns=FEATURE_COLUMNS,
            feature_weights=FEATURE_WEIGHTS,
            target_factor=TARGET_FACTOR,
            overlay_enabled=False,
        )
        core_score = score_binance_ohlcv_core(
            self.panel,
            feature_columns=FEATURE_COLUMNS,
            feature_weights=FEATURE_WEIGHTS,
            require_complete_feature_set=False,
        )

        np.testing.assert_allclose(disabled["score"].to_numpy(), core_score.to_numpy(), rtol=0.0, atol=1e-12)

    def test_enabled_overlay_only_changes_distance_to_high_60_contribution(self) -> None:
        disabled = compute_candidate_score_layer(
            self.panel,
            feature_columns=FEATURE_COLUMNS,
            feature_weights=FEATURE_WEIGHTS,
            target_factor=TARGET_FACTOR,
            overlay_enabled=False,
        )
        enabled = compute_candidate_score_layer(
            self.panel,
            feature_columns=FEATURE_COLUMNS,
            feature_weights=FEATURE_WEIGHTS,
            target_factor=TARGET_FACTOR,
            overlay_enabled=True,
        )

        target_contribution = contribution_column_name(TARGET_FACTOR)
        changed_columns = []
        for feature in FEATURE_COLUMNS:
            contribution = contribution_column_name(feature)
            max_abs_diff = float((enabled[contribution] - disabled[contribution]).abs().max())
            if max_abs_diff > 1e-12:
                changed_columns.append(contribution)

        self.assertEqual(changed_columns, [target_contribution])
        self.assertGreater(float((enabled[target_contribution] - disabled[target_contribution]).abs().max()), 0.0)
        self.assertTrue((enabled["raw_score"] - disabled["raw_score"]).abs().max() > 0.0)

    def test_enabled_overlay_with_identity_multiplier_is_identical(self) -> None:
        identity_panel = self.panel.copy(deep=True)
        identity_panel[OVERLAY_MULTIPLIER_COLUMN] = 1.0
        disabled = compute_candidate_score_layer(
            identity_panel,
            feature_columns=FEATURE_COLUMNS,
            feature_weights=FEATURE_WEIGHTS,
            target_factor=TARGET_FACTOR,
            overlay_enabled=False,
        )
        enabled = compute_candidate_score_layer(
            identity_panel,
            feature_columns=FEATURE_COLUMNS,
            feature_weights=FEATURE_WEIGHTS,
            target_factor=TARGET_FACTOR,
            overlay_enabled=True,
        )

        for feature in FEATURE_COLUMNS:
            contribution = contribution_column_name(feature)
            np.testing.assert_allclose(
                enabled[contribution].to_numpy(),
                disabled[contribution].to_numpy(),
                rtol=0.0,
                atol=1e-12,
            )
        np.testing.assert_allclose(enabled["score"].to_numpy(), disabled["score"].to_numpy(), rtol=0.0, atol=1e-12)

    def test_bad_overlay_multiplier_fails_closed(self) -> None:
        bad_panel = self.panel.copy(deep=True)
        bad_panel.loc[bad_panel.index[0], OVERLAY_MULTIPLIER_COLUMN] = 1.5

        with self.assertRaisesRegex(ValueError, "must be in \\[0, 1\\]"):
            compute_candidate_score_layer(
                bad_panel,
                feature_columns=FEATURE_COLUMNS,
                feature_weights=FEATURE_WEIGHTS,
                target_factor=TARGET_FACTOR,
                overlay_enabled=True,
            )

    def test_run_phase3_writes_ready_summary_and_artifacts(self) -> None:
        output_root = self.temp_dir / "phase3-artifacts"
        summary, exit_code = run_phase3_parity(
            self._args(output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 6, 13, 30, tzinfo=UTC),
            panel=self.panel,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["disabled_wrapper_score_matches_core"])
        self.assertTrue(summary["overlay_enabled_only_target_contribution_changed"])
        self.assertEqual(summary["changed_contribution_columns"], [contribution_column_name(TARGET_FACTOR)])
        self.assertEqual(summary["changed_non_target_contribution_columns"], [])
        self.assertEqual(summary["non_target_contribution_max_abs_diff_enabled_vs_disabled"], 0.0)
        self.assertTrue(summary["phase2_pit_proof_loaded"])
        self.assertEqual(summary["phase2_pit_proof_status"], "ready")
        self.assertTrue(summary["phase2b_pit_proof_loaded"])
        self.assertEqual(summary["phase2b_pit_proof_status"], "ready")
        self.assertTrue(summary["combined_candidate_trigger_proven"])
        self.assertGreater(summary["combined_candidate_trigger_proof"]["combined_overlay_triggered_row_count"], 0)
        self.assertGreater(summary["target_contribution_changed_row_count"], 0)
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["live_config_changed"])
        self.assertEqual(summary["exchange_order_submission"], "disabled")
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "candidate_parity_rows.csv").exists())
        retained = json.loads((output_root / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(retained["run_id"], "20260606T133000Z")

    def test_run_phase3_blocks_without_phase2_proof(self) -> None:
        output_root = self.temp_dir / "missing-phase2-proof"
        args = self._args(output_root=output_root)
        args.phase2_summary = str(self.temp_dir / "missing-phase2-summary.json")

        summary, exit_code = run_phase3_parity(
            args,
            now_fn=lambda: datetime(2026, 6, 6, 13, 35, tzinfo=UTC),
            panel=self.panel,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase2_pit_proof_missing", summary["blockers"])
        self.assertFalse(summary["applied_to_live"])

    def _args(self, *, output_root: Path) -> Namespace:
        strategy_path = self.temp_dir / "strategy.json"
        strategy_path.write_text(
            json.dumps(
                {
                    "feature_columns": FEATURE_COLUMNS,
                    "feature_weights": FEATURE_WEIGHTS,
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
                    "market_data:",
                    f"  symbols: {','.join(str(item) for item in self.panel['subject'].tolist())}",
                    "strategy:",
                    f"  frozen_config_path: {strategy_path.as_posix()}",
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
                        f"{symbol},joined,1780704000000,{50.0 + index}"
                        for index, symbol in enumerate(self.panel["subject"].tolist())
                    ],
                ]
            ),
            encoding="utf-8",
        )
        phase2_summary_path = self.temp_dir / "phase2_summary.json"
        phase2_summary_path.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "run_id": "phase2-test-proof",
                    "requested_symbol_count": len(self.panel),
                    "joined_symbol_count": len(self.panel),
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
                        f"{symbol},joined,1780704000000,{str(index == 0)},{0.20 if index == 0 else 0.0},{3 if index == 0 else 0}"
                        for index, symbol in enumerate(self.panel["subject"].tolist())
                    ],
                ]
            ),
            encoding="utf-8",
        )
        phase2b_summary_path = self.temp_dir / "phase2b_summary.json"
        phase2b_summary_path.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "run_id": "phase2b-test-proof",
                    "requested_symbol_count": len(self.panel),
                    "joined_symbol_count": len(self.panel),
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
        return Namespace(
            config=str(live_config_path),
            strategy_config="",
            symbols="",
            output_root=str(output_root),
            target_factor=TARGET_FACTOR,
            overlay_multiplier_column=OVERLAY_MULTIPLIER_COLUMN,
            overlay_trigger_column="dth60_candidate_overlay_trigger",
            phase2_summary=str(phase2_summary_path),
            phase2b_summary=str(phase2b_summary_path),
            crowded_distance_rank_min=0.75,
            crowded_coinglass_rank_min=0.80,
        )


if __name__ == "__main__":
    unittest.main()
