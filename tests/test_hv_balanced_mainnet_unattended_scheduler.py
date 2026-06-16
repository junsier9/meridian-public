from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
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

from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmResponse  # noqa: E402
from enhengclaw.live_trading.mainnet_unattended_scheduler import run_mainnet_unattended_scheduler  # noqa: E402
from enhengclaw.quant_research.contracts import write_json  # noqa: E402


class HvBalancedMainnetUnattendedSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-unattended-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_scheduler_blocks_low_margin_cushion_before_plan(self) -> None:
        config_path = self._config_path(enforcement="active")
        plan_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_unattended_scheduler(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=40.0, wallet=1000.0),
            plan_runner=_plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "mainnet_unattended_observation_blocked")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(plan_calls, [])
        self.assertTrue(any(item.startswith("available_balance_below_min_after_plan:") for item in summary["blockers"]))

    def test_scheduler_records_removed_daily_pnl_gate_and_runs_plan_only(self) -> None:
        config_path = self._config_path(enforcement="active")
        plan_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_unattended_scheduler(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=_plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": [{"income": "-1.0", "time": "1779000000000"}]}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_unattended_observation_completed")
        self.assertEqual(summary["clean_cycle_count"], 1)
        self.assertFalse(summary["live_delta_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(plan_calls), 1)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["daily_realized_pnl_gate"]["status"], "removed")

    def test_scheduler_does_not_require_active_daily_pnl_gate(self) -> None:
        config_path = self._config_path(enforcement="review_only_not_active")
        plan_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_unattended_scheduler(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=_plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(len(plan_calls), 1)

    def _monitor_runner(self, *, available: float, wallet: float):
        def run(args: Namespace, **_kwargs):
            root = self.temp_dir / "monitor-artifacts" / "cycle"
            root.mkdir(parents=True, exist_ok=True)
            write_json(
                root / "monitor_report.json",
                {
                    "account": {
                        "available_balance_usdt": available,
                        "total_wallet_balance_usdt": wallet,
                    }
                },
            )
            return (
                {
                    "status": "passed_live_position_monitor",
                    "blockers": [],
                    "artifact_root": str(root),
                    "open_order_count": 0,
                    "open_position_count": 2,
                },
                0,
            )

        return run

    def _config_path(self, *, enforcement: str) -> Path:
        path = self.temp_dir / "unattended.yaml"
        path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  venue: usdm_futures",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    "  max_leverage: 2",
                    "risk:",
                    "  trading_enabled: false",
                    "  max_daily_realized_loss_usdt: 10.0",
                    f"  max_daily_realized_loss_enforcement: {enforcement}",
                    "  daily_realized_pnl_income_types: REALIZED_PNL",
                    "  min_available_balance_after_plan_usdt: 100.0",
                    "  min_available_balance_ratio_after_plan: 0.05",
                    "  min_margin_cushion_after_plan_usdt: 100.0",
                    "unattended_scheduler:",
                    "  max_cycles_per_invocation: 1",
                    "  interval_seconds: 0",
                    "  live_delta_enabled: false",
                    "  min_clean_cycles_before_live_delta: 3",
                    "state:",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return path


class _FakeIncomeClient:
    def __init__(self, rows_by_type: dict[str, list[dict]]) -> None:
        self.rows_by_type = rows_by_type

    def income_history(self, *, income_type: str, **_kwargs):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=list(self.rows_by_type.get(income_type, [])))


def _plan_runner(calls: list[Namespace], *, status: str):
    def run(args: Namespace, **_kwargs):
        calls.append(args)
        return (
            {
                "status": status,
                "blockers": [],
                "artifact_root": "plan-root",
                "planned_delta_order_count": 0,
            },
            0,
        )

    return run


def _args(config_path: Path) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel="",
        symbols="",
        public_market_data=False,
        reference_run="",
        cycles=None,
        interval_seconds=None,
        allow_live_delta=False,
        max_abs_position_drift_qty=1e-9,
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 15, 30, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
