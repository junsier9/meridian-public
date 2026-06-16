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

from enhengclaw.live_trading.testnet_recurring_runner import (  # noqa: E402
    TESTNET_RECURRING_CONFIRMATION,
    run_testnet_recurring_auto_order_loop,
)


class HvBalancedTestnetRecurringRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-testnet-recurring-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_missing_confirmation_blocks_before_strategy_or_flatten_calls(self) -> None:
        calls: list[str] = []

        summary, exit_code = run_testnet_recurring_auto_order_loop(
            _args(config_path=self._config_path(), execute=False),
            strategy_runner=_forbidden_runner(calls, "strategy"),
            flatten_runner=_forbidden_runner(calls, "flatten"),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "testnet_recurring_loop_blocked")
        self.assertIn("missing_execute_testnet_recurring_loop_flag", summary["blockers"])
        self.assertIn("missing_exact_testnet_recurring_confirmation", summary["blockers"])
        self.assertEqual(calls, [])

    def test_successful_recurring_loop_forces_flatten_every_cycle(self) -> None:
        strategy_calls: list[Namespace] = []
        flatten_calls: list[Namespace] = []

        summary, exit_code = run_testnet_recurring_auto_order_loop(
            _args(config_path=self._config_path(), max_cycles=2),
            env={"DEMO_KEY": "key", "DEMO_SECRET": "secret"},
            strategy_runner=_strategy_runner(strategy_calls),
            flatten_runner=_flatten_runner(flatten_calls),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "testnet_recurring_loop_completed")
        self.assertEqual(summary["completed_cycle_count"], 2)
        self.assertEqual(summary["strategy_submitted_order_count_total"], 12)
        self.assertEqual(summary["strategy_fill_count_total"], 12)
        self.assertEqual(summary["flatten_submitted_order_count_total"], 12)
        self.assertEqual(summary["flatten_fill_count_total"], 12)
        self.assertEqual(summary["final_open_order_count"], 0)
        self.assertEqual(summary["final_open_position_count"], 0)
        self.assertEqual(len(strategy_calls), 2)
        self.assertEqual(len(flatten_calls), 2)
        self.assertTrue(all(call.execute_testnet_strategy_orders for call in strategy_calls))
        self.assertTrue(all(call.execute_testnet_flatten for call in flatten_calls))
        artifact_root = Path(summary["artifact_root"])
        self.assertTrue((artifact_root / "cycle_001.json").exists())
        self.assertTrue((artifact_root / "cycle_002.json").exists())
        stored_summary = json.loads((artifact_root / "testnet_recurring_loop_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(stored_summary["status"], "testnet_recurring_loop_completed")

    def test_strategy_failure_still_runs_flatten_and_stops_loop(self) -> None:
        strategy_calls: list[Namespace] = []
        flatten_calls: list[Namespace] = []

        summary, exit_code = run_testnet_recurring_auto_order_loop(
            _args(config_path=self._config_path(), max_cycles=2),
            env={"DEMO_KEY": "key", "DEMO_SECRET": "secret"},
            strategy_runner=_strategy_runner(strategy_calls, status="blocked", exit_code=2, submitted=0, fills=0),
            flatten_runner=_flatten_runner(flatten_calls, status="testnet_already_flat", planned=0, submitted=0, fills=0),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "testnet_recurring_loop_blocked")
        self.assertEqual(summary["completed_cycle_count"], 1)
        self.assertEqual(len(strategy_calls), 1)
        self.assertEqual(len(flatten_calls), 1)
        self.assertIn("recurring_strategy_cycle_failed:1:blocked", summary["blockers"])
        self.assertIn("recurring_strategy_no_submitted_orders:1", summary["blockers"])
        self.assertNotIn("recurring_flatten_cycle_failed:1:testnet_already_flat", summary["blockers"])

    def test_operator_pause_in_recurring_loop_blocks_opening_but_still_flattens(self) -> None:
        strategy_calls: list[Namespace] = []
        flatten_calls: list[Namespace] = []

        summary, exit_code = run_testnet_recurring_auto_order_loop(
            _args(config_path=self._config_path(), max_cycles=2),
            env={"DEMO_KEY": "key", "DEMO_SECRET": "secret"},
            strategy_runner=_strategy_runner(
                strategy_calls,
                status="blocked",
                exit_code=2,
                blockers=["operator_paused"],
                submitted=0,
                fills=0,
            ),
            flatten_runner=_flatten_runner(
                flatten_calls,
                status="testnet_already_flat",
                planned=0,
                submitted=0,
                fills=0,
            ),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "testnet_recurring_loop_blocked")
        self.assertEqual(summary["completed_cycle_count"], 1)
        self.assertEqual(summary["strategy_submitted_order_count_total"], 0)
        self.assertEqual(summary["strategy_fill_count_total"], 0)
        self.assertEqual(summary["flatten_submitted_order_count_total"], 0)
        self.assertEqual(summary["flatten_fill_count_total"], 0)
        self.assertEqual(summary["final_open_order_count"], 0)
        self.assertEqual(summary["final_open_position_count"], 0)
        self.assertEqual(len(strategy_calls), 1)
        self.assertEqual(len(flatten_calls), 1)
        self.assertIn("operator_paused", summary["blockers"])
        self.assertIn("recurring_strategy_cycle_failed:1:blocked", summary["blockers"])
        self.assertIn("recurring_strategy_no_submitted_orders:1", summary["blockers"])
        self.assertNotIn("recurring_flatten_cycle_failed:1:testnet_already_flat", summary["blockers"])

    def _config_path(self, *, venue: str = "usdm_futures_testnet") -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm_testnet.yaml"
        artifact_root = (self.temp_dir / "runs").as_posix()
        config_path.write_text(
            "\n".join(
                [
                    "binance:",
                    f"  venue: {venue}",
                    "  api_key_env: DEMO_KEY",
                    "  api_secret_env: DEMO_SECRET",
                    "state:",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


def _args(
    *,
    config_path: Path,
    execute: bool = True,
    max_cycles: int = 2,
) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel="",
        symbols="",
        public_market_data=False,
        max_cycles=max_cycles,
        interval_seconds=0.0,
        execute_testnet_recurring_loop=execute,
        i_understand_this_uses_binance_usdm_testnet=execute,
        confirm_testnet_recurring_risk=TESTNET_RECURRING_CONFIRMATION if execute else "",
    )


def _strategy_runner(
    calls: list[Namespace],
    *,
    status: str = "testnet_strategy_orders_submitted",
    exit_code: int = 0,
    blockers: list[str] | None = None,
    submitted: int = 6,
    fills: int = 6,
):
    def run(args: Namespace, **_kwargs):
        calls.append(args)
        return (
            {
                "status": status,
                "blockers": [] if blockers is None and exit_code == 0 else (blockers or ["strategy_fixture_blocker"]),
                "artifact_root": f"strategy-{len(calls)}",
                "submitted_order_count": submitted,
                "fill_count": fills,
            },
            exit_code,
        )

    return run


def _flatten_runner(
    calls: list[Namespace],
    *,
    status: str = "testnet_reduce_only_flatten_executed",
    exit_code: int = 0,
    planned: int = 6,
    submitted: int = 6,
    fills: int = 6,
):
    def run(args: Namespace, **_kwargs):
        calls.append(args)
        return (
            {
                "status": status,
                "blockers": [] if exit_code == 0 else ["flatten_fixture_blocker"],
                "artifact_root": f"flatten-{len(calls)}",
                "planned_order_count": planned,
                "submitted_order_count": submitted,
                "fill_count": fills,
                "open_order_count_before": 0,
                "open_position_count_before": planned,
                "open_order_count_after": 0,
                "open_position_count_after": 0,
            },
            exit_code,
        )

    return run


def _forbidden_runner(calls: list[str], name: str):
    def run(*_args, **_kwargs):
        calls.append(name)
        raise AssertionError(f"{name} runner should not be called")

    return run


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 8, 30, 0, tzinfo=UTC)
