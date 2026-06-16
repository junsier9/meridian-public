from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import csv
import json
import shutil
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_shock_phase2b_builder import (  # noqa: E402
    COJUMP_FACTOR_ID,
    OVERLAY_MULTIPLIER_COLUMN,
    OVERLAY_TRIGGER_COLUMN,
    SHOCK_FACTOR_ID,
    build_deterministic_shock_panel,
    run_phase2b_shock_builder,
)


class HvBalancedDth60ShockPhase2bBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-shock-phase2b-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.now = datetime(2026, 6, 6, 13, 40, tzinfo=UTC)

    def test_ready_builder_excludes_current_row_from_threshold_and_joins_all_symbols(self) -> None:
        output_root = self.temp_dir / "ready"
        summary, exit_code = run_phase2b_shock_builder(
            self._args(output_root=output_root),
            now_fn=lambda: self.now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["joined_symbol_count"], 20)
        self.assertTrue(summary["shock_branch_triggered"])
        self.assertTrue(summary["current_row_excluded_from_threshold"])
        self.assertFalse(summary["train_includes_decision_row"])
        self.assertEqual(summary["train_future_row_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_stale_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(output_root / "shock_joined_snapshot.csv")
        self.assertEqual(len(joined), 20)
        self.assertTrue(all(row["join_status"] == "joined" for row in joined))
        self.assertTrue(all(row[OVERLAY_TRIGGER_COLUMN] == "True" for row in joined))
        self.assertTrue(all(row[OVERLAY_MULTIPLIER_COLUMN] == "0.0" for row in joined))

    def test_future_rows_are_blocked_and_not_selected(self) -> None:
        output_root = self.temp_dir / "future"
        panel = build_deterministic_shock_panel(symbols=self._symbols(), now=self.now)
        future_time = self.now + timedelta(days=1)
        future_panel = build_deterministic_shock_panel(symbols=self._symbols(), now=future_time, lookback_days=1)
        future_panel["return_1"] = 0.50
        panel = pd.concat([panel, future_panel], ignore_index=True)

        summary, exit_code = run_phase2b_shock_builder(
            self._args(output_root=output_root),
            now_fn=lambda: self.now,
            input_panel=panel,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertGreater(summary["future_blocked_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertEqual(summary["selected_provider_timestamp_utc"], "2026-06-06T00:00:00Z")

    def test_stale_selected_row_blocks_without_zero_fill(self) -> None:
        output_root = self.temp_dir / "stale"
        args = self._args(output_root=output_root)
        args.freshness_seconds = 60

        summary, exit_code = run_phase2b_shock_builder(
            args,
            now_fn=lambda: self.now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase2b_shock_missing_eligible_timestamp", summary["blockers"])
        self.assertGreater(summary["stale_blocked_count"], 0)
        self.assertTrue(summary["no_future_fill_proven"])
        self.assertTrue(summary["no_zero_fill_proven"])
        joined = self._read_csv(output_root / "shock_joined_snapshot.csv")
        self.assertTrue(all(row[SHOCK_FACTOR_ID] == "" for row in joined))
        self.assertTrue(all(row[COJUMP_FACTOR_ID] == "" for row in joined))

    def test_insufficient_train_window_blocks_threshold(self) -> None:
        output_root = self.temp_dir / "short-train"
        args = self._args(output_root=output_root)
        args.min_train_timestamps = 200

        summary, exit_code = run_phase2b_shock_builder(
            args,
            now_fn=lambda: self.now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("shock_threshold_insufficient_train_timestamps", summary["blockers"])
        joined = self._read_csv(output_root / "shock_joined_snapshot.csv")
        self.assertTrue(all(row["join_status"] == "blocked_no_ready_threshold" for row in joined))

    def _args(self, *, output_root: Path) -> Namespace:
        config_path = self.temp_dir / "hv_balanced_live_timer.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "market_data:",
                    f"  symbols: {','.join(self._symbols())}",
                    "state:",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return Namespace(
            config=str(config_path),
            symbols="",
            input_panel="",
            output_root=str(output_root),
            decision_time="now",
            availability_lag_seconds=60,
            freshness_seconds=36 * 3600,
            train_window_days=60,
            min_train_timestamps=20,
            min_universe_coverage=0.95,
            shock_quantile=0.90,
        )

    def _symbols(self) -> list[str]:
        return [
            "BTCUSDT",
            "ETHUSDT",
            "BNBUSDT",
            "SOLUSDT",
            "XRPUSDT",
            "DOGEUSDT",
            "ADAUSDT",
            "AVAXUSDT",
            "LINKUSDT",
            "LTCUSDT",
            "BCHUSDT",
            "TRXUSDT",
            "DOTUSDT",
            "UNIUSDT",
            "AAVEUSDT",
            "NEARUSDT",
            "FILUSDT",
            "ETCUSDT",
            "APTUSDT",
            "ARBUSDT",
        ]

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
