from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
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

from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256  # noqa: E402
from enhengclaw.live_trading.shadow_loop_runner import _is_duplicate_paper_block, run_shadow_loop  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402


class HvBalancedShadowLoopRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-shadow-loop-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_shadow_loop_runs_paper_and_testnet_dry_run_without_testnet_orders(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_shadow_loop(
            Namespace(
                config=str(config_path),
                as_of="now",
                fixture_panel=str(panel_path),
                symbols="",
                public_market_data=False,
                cycles=2,
                interval_seconds=0.0,
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "shadow_loop_completed")
        self.assertEqual(summary["completed_cycle_count"], 2)
        self.assertEqual(summary["testnet_submitted_order_count_total"], 0)
        self.assertEqual(summary["paper_executed_cycle_count"], 1)
        self.assertEqual(summary["paper_duplicate_skipped_cycle_count"], 1)
        self.assertEqual(summary["exchange_order_submission"], "disabled")
        self.assertEqual(summary["cycles"][0]["paper_effective_status"], "paper_executed")
        self.assertEqual(summary["cycles"][1]["paper_effective_status"], "paper_duplicate_skipped_no_new_fill")
        self.assertEqual(summary["cycles"][0]["testnet_status"], "testnet_strategy_plan_ready")
        self.assertEqual(summary["cycles"][1]["testnet_status"], "testnet_strategy_plan_ready")
        artifact_root = Path(summary["artifact_root"])
        self.assertTrue((artifact_root / "shadow_loop_summary.json").exists())
        self.assertTrue((artifact_root / "cycle_001.json").exists())
        self.assertTrue((artifact_root / "cycle_002.json").exists())
        stored_summary = json.loads((artifact_root / "shadow_loop_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(stored_summary["status"], "shadow_loop_completed")
        self.assertGreater(len(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_paper_positions()), 0)

    def test_injected_paper_exception_blocks_before_testnet_dry_run(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_shadow_loop(
            self._shadow_args(
                config_path=config_path,
                panel_path=panel_path,
                cycles=3,
                inject_failure_cycle=1,
                inject_failure_stage="before_paper",
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "shadow_loop_blocked")
        self.assertEqual(summary["completed_cycle_count"], 1)
        self.assertEqual(summary["testnet_submitted_order_count_total"], 0)
        self.assertIn("paper_shadow_cycle_exception:1:InjectedShadowLoopFailure", summary["blockers"])
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["paper_effective_status"], "exception")
        self.assertEqual(cycle["testnet_status"], "skipped_due_to_prior_blocker")
        self.assertEqual(cycle["testnet_submitted_order_count"], 0)
        self.assertTrue(Path(summary["artifact_root"], "shadow_loop_summary.json").exists())

    def test_clean_run_recovers_after_injected_testnet_failure_without_orders(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        failed_summary, failed_exit_code = run_shadow_loop(
            self._shadow_args(
                config_path=config_path,
                panel_path=panel_path,
                cycles=2,
                inject_failure_cycle=1,
                inject_failure_stage="after_testnet",
            )
        )

        self.assertEqual(failed_exit_code, 2)
        self.assertEqual(failed_summary["status"], "shadow_loop_blocked")
        self.assertEqual(failed_summary["testnet_submitted_order_count_total"], 0)
        self.assertIn("testnet_shadow_cycle_exception:1:InjectedShadowLoopFailure", failed_summary["blockers"])
        self.assertEqual(failed_summary["cycles"][0]["testnet_status"], "testnet_strategy_plan_ready")
        self.assertEqual(failed_summary["cycles"][0]["testnet_submitted_order_count"], 0)

        recovered_summary, recovered_exit_code = run_shadow_loop(
            self._shadow_args(config_path=config_path, panel_path=panel_path, cycles=2)
        )

        self.assertEqual(recovered_exit_code, 0)
        self.assertEqual(recovered_summary["status"], "shadow_loop_completed")
        self.assertEqual(recovered_summary["completed_cycle_count"], 2)
        self.assertEqual(recovered_summary["testnet_submitted_order_count_total"], 0)
        self.assertEqual(recovered_summary["paper_executed_cycle_count"], 0)
        self.assertEqual(recovered_summary["paper_duplicate_skipped_cycle_count"], 2)
        self.assertEqual(recovered_summary["cycles"][0]["paper_effective_status"], "paper_duplicate_skipped_no_new_fill")
        self.assertEqual(recovered_summary["cycles"][1]["testnet_status"], "testnet_strategy_plan_ready")

    def test_duplicate_paper_skip_only_tolerates_dust_residual_blockers(self) -> None:
        self.assertTrue(
            _is_duplicate_paper_block(
                {
                    "status": "blocked",
                    "blockers": [
                        "duplicate_paper_plan_already_executed:demo",
                        "quantity_below_min:BTCUSDT",
                        "notional_below_min:BTCUSDT",
                    ],
                }
            )
        )
        self.assertFalse(
            _is_duplicate_paper_block(
                {
                    "status": "blocked",
                    "blockers": [
                        "duplicate_paper_plan_already_executed:demo",
                        "operator_paused",
                    ],
                }
            )
        )

    def _shadow_args(
        self,
        *,
        config_path: Path,
        panel_path: Path,
        cycles: int,
        inject_failure_cycle: int = 0,
        inject_failure_stage: str = "",
    ) -> Namespace:
        return Namespace(
            config=str(config_path),
            as_of="now",
            fixture_panel=str(panel_path),
            symbols="",
            public_market_data=False,
            cycles=cycles,
            interval_seconds=0.0,
            inject_failure_cycle=inject_failure_cycle,
            inject_failure_stage=inject_failure_stage,
            inject_failure_message="unit_test_injected_failure",
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_shadow_loop.yaml"
        sqlite_path = (self.temp_dir / "state.sqlite3").as_posix()
        artifact_root = (self.temp_dir / "runs").as_posix()
        frozen_config = self.temp_dir / "frozen_hv_balanced.json"
        payload = json.loads(
            (ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json").read_text(
                encoding="utf-8-sig"
            )
        )
        payload["pit_data_eligibility_policy"] = {"mode": "disabled"}
        frozen_config.write_text(json.dumps(payload), encoding="utf-8")
        frozen_hash = file_sha256(frozen_config)
        config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    f"  frozen_config_path: {frozen_config.as_posix()}",
                    f"  frozen_config_sha256: {frozen_hash}",
                    "  rebalance_interval_days: 10",
                    "binance:",
                    "  venue: usdm_futures_testnet",
                    "  api_key_env: TESTNET_KEY",
                    "  api_secret_env: TESTNET_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "capital:",
                    "  allocated_capital_usdt: 500.0",
                    "risk:",
                    "  trading_enabled: false",
                    "  max_allocated_capital_usdt: 500.0",
                    "  max_gross_notional_usdt: 500.0",
                    "  max_symbol_notional_usdt: 100.0",
                    "market_data:",
                    "  public_data_enabled: false",
                    "shadow_loop:",
                    "  interval_seconds: 0",
                    "  max_cycles_per_invocation: 2",
                    "  run_paper: true",
                    "  run_testnet_dry_run: true",
                    "  require_testnet_submitted_order_count_zero: true",
                    "state:",
                    f"  sqlite_path: {sqlite_path}",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


def _fixture_panel() -> pd.DataFrame:
    rows = []
    for index, subject in enumerate(["L1", "L2", "L3", "S1", "S2", "S3"]):
        base = 0.10 + index * 0.01
        rows.append(
            {
                "timestamp_ms": 0,
                "subject": subject,
                "usdm_symbol": f"{subject}USDT",
                "perp_close": 100.0,
                "perp_quote_volume_usd": 10_000_000.0,
                "universe_active": True,
                "universe_rank": index + 1,
                "liquidity_bucket": "top_liquidity" if subject.startswith("L") else "mid_liquidity",
                "funding_rate": 0.0,
                "funding_sample_count": 3.0,
                "intraday_realized_vol_4h_to_1d_smooth_60": base,
                "realized_volatility_5": base + 0.01,
                "distance_to_high_60": base + 0.02,
                "distance_to_high_5": -0.01 if subject.startswith("S") else -0.20,
                "downside_upside_vol_ratio_30": base + 0.03,
                "momentum_20": 0.05,
            }
        )
    return pd.DataFrame(rows)
