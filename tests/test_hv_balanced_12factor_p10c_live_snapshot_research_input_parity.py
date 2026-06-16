from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import json
import shutil
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_12factor_p10c_live_snapshot_research_input_parity import (  # noqa: E402
    build_scorer_input_matrix,
    run_p10c_live_snapshot_research_input_parity,
)


REQUIRED_FACTORS = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
    "settlement_cycle_premium_60d",
]


class HvBalanced12FactorP10cLiveSnapshotResearchInputParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10c-live-parity-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.p10a_root = self.temp_dir / "p10a"
        self.p10a_root.mkdir(parents=True, exist_ok=True)
        self.joined_path = self.p10a_root / "pit_live_feature_joined_snapshot.csv"
        self.summary_path = self.p10a_root / "summary.json"
        self._write_p10a_artifacts(status="ready")

    def test_p10c_ready_when_research_input_matches_live_builder_values(self) -> None:
        summary, exit_code = run_p10c_live_snapshot_research_input_parity(
            self._args(output_root=self.temp_dir / "ready"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["comparison_cell_count"], 24)
        self.assertEqual(summary["mismatch_count"], 0)
        self.assertEqual(summary["max_abs_diff"], 0.0)
        self.assertTrue(summary["factor_order_matches_research_contract"])

    def test_p10c_detects_research_scorer_input_value_drift(self) -> None:
        joined = pd.read_csv(self.joined_path)
        live_long = joined.rename(columns={"value": "live_builder_value"})
        live_long["factor_position"] = live_long["factor_id"].map({factor: i for i, factor in enumerate(REQUIRED_FACTORS)})
        matrix = build_scorer_input_matrix(
            live_long[["symbol", "subject", "factor_id", "factor_position", "live_builder_value"]],
            required_factors=REQUIRED_FACTORS,
        )
        matrix.loc[("BTCUSDT", "BTC"), "quality_funding_oi"] += 0.25

        summary, exit_code = run_p10c_live_snapshot_research_input_parity(
            self._args(output_root=self.temp_dir / "drift"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 0, tzinfo=UTC),
            research_input_frame=matrix,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("factor_value_parity_mismatch", summary["blockers"])
        self.assertEqual(summary["mismatch_count"], 1)
        mismatch = pd.read_csv(self.temp_dir / "drift" / "factor_value_parity_mismatch_sample.csv")
        self.assertEqual(mismatch.iloc[0]["factor_id"], "quality_funding_oi")

    def test_p10c_blocks_when_p10a_summary_is_not_ready(self) -> None:
        self._write_p10a_artifacts(status="blocked")

        summary, exit_code = run_p10c_live_snapshot_research_input_parity(
            self._args(output_root=self.temp_dir / "blocked-p10a"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10a_summary_not_ready", summary["blockers"])

    def _args(self, *, output_root: Path) -> Namespace:
        return Namespace(
            p10a_summary=self.summary_path,
            research_input_override=None,
            output_root=output_root,
            active_h10d_registry=ROOT / "config" / "quant_research" / "active_h10d_registry.json",
            research_parent_manifest=None,
            tolerance=1e-12,
            row_sample_limit=200,
        )

    def _write_p10a_artifacts(self, *, status: str) -> None:
        rows = []
        symbols = [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")]
        for factor_index, factor in enumerate(REQUIRED_FACTORS):
            for symbol_index, (symbol, subject) in enumerate(symbols):
                rows.append(
                    {
                        "symbol": symbol,
                        "subject": subject,
                        "factor_id": factor,
                        "join_status": "joined",
                        "decision_time_utc": "2026-06-08T12:00:00Z",
                        "decision_time_ms": 1780920000000,
                        "provider_timestamp_ms": 1780916400000,
                        "available_at_ms": 1780916460000,
                        "value": float(factor_index + symbol_index / 10.0),
                        "source": "test",
                        "future_fill_violation": False,
                        "stale_fill_violation": False,
                        "zero_fill_violation": False,
                    }
                )
        pd.DataFrame(rows).to_csv(self.joined_path, index=False)
        summary = {
            "status": status,
            "candidate_executed": False,
            "executor_invoked": False,
            "orders_submitted": 0,
            "fills_observed": 0,
            "decision_time_utc": "2026-06-08T12:00:00Z",
            "output_root": str(self.p10a_root),
            "required_feature_columns": REQUIRED_FACTORS,
            "artifacts": {
                "pit_live_feature_joined_snapshot": str(self.joined_path),
            },
        }
        self.summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
