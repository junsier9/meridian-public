from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmResponse  # noqa: E402
from enhengclaw.live_trading.daily_rebalance_slot_gate import (  # noqa: E402
    REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
)
from enhengclaw.live_trading.mainnet_core_loop_runner import run_mainnet_core_loop  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402
from enhengclaw.live_trading.unattended_epoch_controller import (  # noqa: E402
    UNATTENDED_EPOCH_APPROVAL_CONTRACT,
)
from enhengclaw.quant_research.contracts import write_json  # noqa: E402


class HvBalancedMainnetCoreLoopRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-core-loop-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_core_loop_reconciles_plans_and_delta_dry_runs_without_live_orders(self) -> None:
        config_path = self._config_path()
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": [{"income": "-1.0", "time": "1779000000000"}]}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertFalse(summary["live_delta_authorized"])
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(len(delta_calls), 1)
        self.assertEqual(plan_calls[0].as_of, "latest_closed_rebalance_slot")
        self.assertFalse(delta_calls[0].execute_mainnet_delta_orders)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_plan_only_ready")
        self.assertEqual(cycle["account_reconcile_artifacts"]["account"]["available_balance_usdt"], 300.0)
        self.assertEqual(cycle["strategy_plan_artifacts"]["target_portfolio"]["portfolio_id"], "portfolio-1")
        self.assertEqual(cycle["delta_preflight_artifacts"]["mainnet_delta_preflight"]["status"], "passed")
        self.assertGreaterEqual(_live_artifact_count(self.temp_dir / "state.sqlite3"), 2)

    def test_core_loop_marks_noop_frozen_rebalance_slot_completed(self) -> None:
        config_path = self._config_path()
        snapshot = _frozen_slot_snapshot(status="open")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_rebalance_slot_target(snapshot)
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(
                [],
                status="mainnet_current_position_rebalance_noop",
                frozen_snapshot=snapshot,
            ),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_noop")
        self.assertEqual(cycle["frozen_rebalance_slot_completion"]["status"], "completed")
        self.assertEqual(cycle["frozen_rebalance_slot_completion"]["completion_reason"], "noop_no_delta")
        self.assertEqual(delta_calls, [])
        persisted = store.read_rebalance_slot_target(snapshot["slot_id"])
        self.assertEqual(persisted["status"], "completed")

    def test_core_loop_holds_completed_frozen_rebalance_slot_without_delta(self) -> None:
        config_path = self._config_path()
        snapshot = _frozen_slot_snapshot(status="completed")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_rebalance_slot_target(snapshot)
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(
                [],
                status="mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
                frozen_snapshot=snapshot,
            ),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_hold_until_next_rebalance_slot")
        self.assertEqual(cycle["execution_status"], "hold_until_next_rebalance_slot")
        self.assertNotIn("frozen_rebalance_slot_completion", cycle)
        self.assertEqual(delta_calls, [])

    def test_core_loop_hold_skips_margin_admission_when_no_delta_exists(self) -> None:
        config_path = self._config_path(include_margin_thresholds=False)
        snapshot = _frozen_slot_snapshot(status="completed")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_rebalance_slot_target(snapshot)
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=1.0, wallet=1000.0),
            plan_runner=self._plan_runner(
                [],
                status="mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
                frozen_snapshot=snapshot,
            ),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_hold_until_next_rebalance_slot")
        self.assertEqual(cycle["margin_cushion_gate"]["status"], "skipped")
        self.assertEqual(cycle["blockers"], [])
        self.assertEqual(delta_calls, [])

    def test_core_loop_consumes_single_use_risk_only_cleanup_after_live_success(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
        )
        snapshot = _frozen_slot_snapshot(status="completed")
        gate = {
            "status": "reuse_frozen_slot_target",
            "slot_id": snapshot["slot_id"],
            "active_target_hash": snapshot["target_hash"],
            "completed_slot_execution_gate": {
                "status": "risk_only_reduce_cleanup_allowed",
                "slot_id": snapshot["slot_id"],
                "target_hash": snapshot["target_hash"],
                "budget_epoch_id": "epoch-risk-cleanup",
                "authorization_action_id": "auth-risk-cleanup",
                "authorization": {
                    "status": "applied",
                    "action_id": "auth-risk-cleanup",
                    "slot_id": snapshot["slot_id"],
                    "target_hash": snapshot["target_hash"],
                    "budget_epoch_id": "epoch-risk-cleanup",
                    "single_use": True,
                },
                "no_order_canary": {
                    "status": "passed",
                    "artifact_root": "no-order-canary-root",
                    "orders_submitted": 0,
                    "mainnet_order_submission_authorized": False,
                },
            },
        }

        def plan_runner(_args: Namespace, **_kwargs):
            root = self.temp_dir / "plan-artifacts" / "risk-only-cleanup"
            _write_plan_artifact(
                root,
                status="mainnet_current_position_rebalance_plan_ready",
                execution_stage="reduce_first",
                frozen_snapshot=snapshot,
                frozen_slot_gate_override=gate,
            )
            return (
                {
                    "status": "mainnet_current_position_rebalance_plan_ready",
                    "blockers": [],
                    "artifact_root": str(root),
                    "planned_delta_order_count": 1,
                    "active_execution_phase": "reduce_first",
                },
                0,
            )

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=plan_runner,
            delta_runner=self._delta_runner(
                [],
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                submitted_on_execute=1,
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        cycle = summary["cycles"][0]
        self.assertTrue(cycle["live_delta_authorized"])
        self.assertEqual(cycle["risk_only_reduce_cleanup_consumption"]["source_authorization_action_id"], "auth-risk-cleanup")
        consumed = LiveTradingStateStore(self.temp_dir / "state.sqlite3").latest_operator_action(
            action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION,
            status="applied",
            slot_id=snapshot["slot_id"],
            target_hash=snapshot["target_hash"],
        )
        self.assertIsNotNone(consumed)
        self.assertEqual(consumed["source_authorization_action_id"], "auth-risk-cleanup")
        self.assertTrue(consumed["single_use_consumed"])

    def test_core_loop_passes_parent_heartbeat_through_to_delta_preflight(self) -> None:
        config_path = self._config_path()
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path, ignore_heartbeat_run_id="supervisor-parent"),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(len(delta_calls), 1)
        self.assertIn("mainnet-core-loop", delta_calls[0].ignore_heartbeat_run_id)
        self.assertIn("supervisor-parent", delta_calls[0].ignore_heartbeat_run_id)

    def test_core_loop_ignores_concurrent_health_monitor_heartbeat(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="health-monitor-running",
            mode="mainnet_health_monitor",
            status="running",
            started_at_utc=_fixed_now().isoformat().replace("+00:00", "Z"),
            updated_at_utc=_fixed_now().isoformat().replace("+00:00", "Z"),
            artifact_root=str(self.temp_dir / "health"),
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["blockers"], [])
        local_state = json.loads((Path(summary["artifact_root"]) / "local_state_health.json").read_text(encoding="utf-8"))
        self.assertEqual(local_state["status"], "ok")
        self.assertEqual(local_state["ignored_running_health_monitor_run_ids"], ["health-monitor-running"])
        self.assertTrue(local_state["running_heartbeats"][0]["ignored_for_core_loop"])

    def test_core_loop_ignores_concurrent_daily_policy_orchestrator_heartbeat(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="daily-policy-running",
            mode="unattended_daily_policy",
            status="running",
            started_at_utc=_fixed_now().isoformat().replace("+00:00", "Z"),
            updated_at_utc=_fixed_now().isoformat().replace("+00:00", "Z"),
            artifact_root=str(self.temp_dir / "daily-policy"),
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["blockers"], [])
        local_state = json.loads((Path(summary["artifact_root"]) / "local_state_health.json").read_text(encoding="utf-8"))
        self.assertEqual(local_state["status"], "ok")
        self.assertEqual(local_state["ignored_orchestrator_run_ids"], ["daily-policy-running"])
        self.assertTrue(local_state["running_heartbeats"][0]["ignored_for_core_loop"])

    def test_core_loop_blocks_margin_after_target_plan_and_before_delta_execution(self) -> None:
        config_path = self._config_path()
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=40.0, wallet=1000.0),
            plan_runner=self._plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "mainnet_core_loop_blocked")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(delta_calls, [])
        self.assertTrue(any(item.startswith("available_balance_below_min_after_plan:") for item in summary["blockers"]))
        self.assertEqual(summary["cycles"][0]["strategy_plan_artifacts"]["execution_plan"]["status"], "ok")

    def test_core_loop_treats_dust_delta_plan_as_noop_without_delta_runner(self) -> None:
        config_path = self._config_path()
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(plan_calls, status="mainnet_current_position_rebalance_dust_noop"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(delta_calls, [])
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_dust_noop")
        self.assertEqual(cycle["execution_status"], "noop_dust_delta")
        self.assertTrue(cycle["dust_delta_noop"])
        self.assertEqual(cycle["blockers"], [])

    def test_core_loop_treats_deferred_deployable_surplus_plan_as_no_order_cycle(self) -> None:
        config_path = self._config_path(live_delta_enabled=True, submit_orders=True, auto_confirm=True)
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=120.0, wallet=1000.0),
            plan_runner=self._plan_runner(plan_calls, status="mainnet_current_position_rebalance_deferred"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertFalse(summary["live_delta_authorized"])
        self.assertEqual(delta_calls, [])
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_deferred")
        self.assertEqual(cycle["execution_status"], "deferred_no_live_delta")
        self.assertTrue(cycle["capital_deployment_deferred"])
        self.assertEqual(cycle["margin_cushion_gate"]["status"], "passed")
        self.assertEqual(cycle["deferred_if_executed_margin_cushion_gate"]["status"], "blocked")
        self.assertEqual(cycle["blockers"], [])

    def test_core_loop_attempts_capital_topup_after_static_dust_noop(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="entry_second",
            capital_topup=True,
        )
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                capital_topup=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=500.0, wallet=1600.0),
            plan_runner=self._plan_runner_sequence(
                plan_calls,
                statuses=[
                    "mainnet_current_position_rebalance_dust_noop",
                    "mainnet_current_position_rebalance_plan_ready",
                ],
            ),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", submitted_on_execute=1),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(len(plan_calls), 2)
        self.assertFalse(plan_calls[0].capital_topup)
        self.assertTrue(plan_calls[1].capital_topup)
        cycle = summary["cycles"][0]
        self.assertTrue(cycle["capital_topup_attempted"])
        self.assertEqual(cycle["static_plan_status"], "mainnet_current_position_rebalance_dust_noop")
        self.assertEqual(cycle["plan_status"], "mainnet_current_position_rebalance_plan_ready")

    def test_core_loop_can_select_topup_target_over_static_rebalance_delta(self) -> None:
        config_path = self._config_path(capital_topup=True)
        plan_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path, capital_topup=True),
            env=_env(),
            monitor_runner=self._monitor_runner(available=500.0, wallet=1600.0),
            plan_runner=self._plan_runner_sequence(
                plan_calls,
                statuses=[
                    "mainnet_current_position_rebalance_plan_ready",
                    "mainnet_current_position_rebalance_dust_noop",
                ],
            ),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(plan_calls), 2)
        self.assertFalse(plan_calls[0].capital_topup)
        self.assertTrue(plan_calls[1].capital_topup)
        self.assertTrue(summary["cycles"][0]["capital_topup_attempted"])
        self.assertTrue(summary["cycles"][0]["capital_topup_selected"])
        self.assertEqual(summary["cycles"][0]["plan_status"], "mainnet_current_position_rebalance_dust_noop")

    def test_core_loop_margin_cushion_accounts_for_topup_entry_margin(self) -> None:
        config_path = self._config_path(capital_topup=True)
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path, capital_topup=True),
            env=_env(),
            monitor_runner=self._monitor_runner(available=120.0, wallet=1600.0),
            plan_runner=self._plan_runner_sequence(
                plan_calls,
                statuses=[
                    "mainnet_current_position_rebalance_dust_noop",
                    "mainnet_current_position_rebalance_plan_ready",
                ],
                topup_notional=80.0,
            ),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(delta_calls, [])
        margin_gate = summary["cycles"][0]["margin_cushion_gate"]
        self.assertEqual(margin_gate["planned_additional_initial_margin_usdt"], 40.0)
        self.assertIn("margin_cushion_below_min_after_plan:80.0<100.0", summary["blockers"])

    def test_core_loop_uses_plan_margin_gate_for_reduce_only_override(self) -> None:
        config_path = self._config_path()
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        def plan_runner(args: Namespace, **_kwargs):
            plan_calls.append(args)
            root = self.temp_dir / "plan-artifacts" / "reduce-only-override"
            _write_plan_artifact(
                root,
                status="mainnet_current_position_rebalance_plan_ready",
                execution_stage="reduce_first",
            )
            write_json(
                root / "margin_cushion_gate.json",
                {
                    "status": "passed",
                    "passed": True,
                    "blockers": [],
                    "warnings": ["reduce_only_plan_allowed_below_margin_floor"],
                    "planned_additional_initial_margin_usdt": 0.0,
                    "reduce_only_margin_floor_override": True,
                },
            )
            write_json(
                root / "pre_reduce_only_margin_cushion_gate.json",
                {
                    "status": "blocked",
                    "passed": False,
                    "blockers": ["available_balance_ratio_below_min_after_plan:0.04<0.05"],
                    "planned_additional_initial_margin_usdt": 0.0,
                },
            )
            return (
                {
                    "status": "mainnet_current_position_rebalance_plan_ready",
                    "blockers": [],
                    "artifact_root": str(root),
                    "planned_delta_order_count": 1,
                    "active_execution_phase": "reduce_first",
                },
                0,
            )

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=self._monitor_runner(available=40.0, wallet=1000.0),
            plan_runner=plan_runner,
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", execution_stage="reduce_first"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(len(delta_calls), 1)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_plan_only_ready")
        self.assertEqual(cycle["margin_cushion_gate"]["status"], "passed")
        self.assertTrue(cycle["margin_cushion_gate"]["reduce_only_margin_floor_override"])
        self.assertEqual(cycle["pre_reduce_only_margin_cushion_gate"]["status"], "blocked")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def test_core_loop_preserves_explicit_as_of_override(self) -> None:
        config_path = self._config_path()
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path, as_of="1778112000000"),
            env=_env(),
            monitor_runner=self._monitor_runner(available=40.0, wallet=1000.0),
            plan_runner=self._plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(plan_calls[0].as_of, "1778112000000")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(delta_calls, [])

    def test_core_loop_respects_operator_pause_before_account_reads(self) -> None:
        config_path = self._config_path()
        LiveTradingStateStore(self.temp_dir / "state.sqlite3").record_operator_action(
            run_id="operator",
            action_type="pause",
            reason="unit test",
            created_at_utc="2026-05-17T00:00:00Z",
        )
        monitor_calls: list[Namespace] = []

        def monitor(args: Namespace, **_kwargs):
            monitor_calls.append(args)
            return {}, 0

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path),
            env=_env(),
            monitor_runner=monitor,
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("operator_paused", summary["blockers"])
        self.assertEqual(monitor_calls, [])
        self.assertEqual(summary["cycles"][0]["status"], "cycle_skipped_prior_blocker")

    def test_core_loop_live_delta_requires_config_enable_before_any_order_path(self) -> None:
        config_path = self._config_path()
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path, execute_live_delta=True),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("mainnet_core_loop_live_delta_disabled_in_config", summary["blockers"])
        self.assertEqual(delta_calls, [])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_core_loop_live_delta_also_requires_submit_orders_config_gate(self) -> None:
        config_path = self._config_path(live_delta_enabled=True, submit_orders=False)
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(config_path, execute_live_delta=True),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("mainnet_core_loop_submit_orders_false", summary["blockers"])
        self.assertEqual(delta_calls, [])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_core_loop_multiphase_live_delta_fails_closed_without_explicit_allow_flag(self) -> None:
        config_path = self._config_path(
            target_engine="multiphase_equal_sleeve",
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("mainnet_core_loop_multiphase_target_engine_live_delta_not_explicitly_allowed", summary["blockers"])
        self.assertEqual(delta_calls, [])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_core_loop_multiphase_live_delta_executes_when_explicitly_allowed(self) -> None:
        config_path = self._config_path(
            target_engine="multiphase_equal_sleeve",
            allow_multiphase_live_delta=True,
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="entry_second",
        )
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        with patch(
            "enhengclaw.live_trading.mainnet_core_loop_runner.run_mainnet_multiphase_current_position_rebalance_plan",
            self._plan_runner(plan_calls, status="mainnet_current_position_rebalance_plan_ready"),
        ):
            summary, exit_code = run_mainnet_core_loop(
                _args(
                    config_path,
                    execute_live_delta=True,
                    operator_enable=True,
                    understand=True,
                    daily_active_ack=True,
                ),
                env=_env(),
                monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
                plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
                delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", submitted_on_execute=1),
                account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
                now_fn=_fixed_now,
                sleep_fn=lambda _seconds: None,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["target_engine"], "multiphase_equal_sleeve")
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertTrue(summary["live_delta_authorized"])
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(plan_calls[0].target_engine, "multiphase_equal_sleeve")
        self.assertEqual(len(delta_calls), 2)
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)

    def test_core_loop_auto_confirms_live_delta_after_clean_preflight_when_armed(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="entry_second",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", submitted_on_execute=1),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertTrue(summary["live_delta_authorized"])
        self.assertEqual(len(delta_calls), 2)
        self.assertFalse(delta_calls[0].execute_mainnet_delta_orders)
        self.assertTrue(delta_calls[0].prepare_planned_symbol_account_settings)
        self.assertTrue(delta_calls[0].operator_enable_mainnet_account_settings_for_this_run)
        self.assertTrue(delta_calls[0].i_understand_this_modifies_mainnet_account_settings)
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)
        self.assertEqual(delta_calls[1].confirm_mainnet_delta_execution, "CONFIRM")

    def test_live_reduce_first_keeps_slot_open_when_entry_second_is_deferred(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
        )
        snapshot = _frozen_slot_snapshot(status="open")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_rebalance_slot_target(snapshot)
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(
                [],
                status="mainnet_current_position_rebalance_plan_ready",
                execution_stage="reduce_first",
                frozen_snapshot=snapshot,
            ),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                submitted_on_execute=1,
                deferred_phase_counts={"entry_second": 2},
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["status"], "cycle_executed_reconciled")
        self.assertNotIn("frozen_rebalance_slot_completion", cycle)
        self.assertEqual(
            cycle["frozen_rebalance_slot_completion_deferred"]["status"],
            "deferred_pending_execution_phases",
        )
        self.assertEqual(
            cycle["frozen_rebalance_slot_completion_deferred"]["deferred_phase_counts"],
            {"entry_second": 2},
        )
        persisted = store.read_rebalance_slot_target(snapshot["slot_id"])
        self.assertEqual(persisted["status"], "open")

    def test_budgeted_live_delta_requires_matching_owner_intent_payload_at_runtime(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
            unattended_budget_gate=True,
        )
        epoch_id = "owner-aave-reduce-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=1,
            expected_max_turnover_usdt=10.0,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                submitted_on_execute=1,
                planned_rows=[
                    {
                        "symbol": "AAVEUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(len(delta_calls), 2)
        cycle = summary["cycles"][0]
        owner_gate = cycle["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "passed")
        self.assertEqual(owner_gate["current_open_epoch_id"], epoch_id)
        self.assertEqual(owner_gate["expected_symbols"], ["AAVEUSDT"])
        self.assertEqual(owner_gate["actual_symbols"], ["AAVEUSDT"])
        self.assertEqual(owner_gate["projected_turnover_usdt"], 6.0)
        self.assertEqual(cycle["unattended_budget_gate"]["status"], "reserved")
        self.assertEqual(cycle["unattended_budget_reconcile"]["status"], "reconciled")

    def test_budgeted_live_delta_allows_owner_intent_allowed_symbol_subset(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
            unattended_budget_gate=True,
        )
        epoch_id = "owner-wide-reduce-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            expected_execution_stage="reduce_first",
            allowed_symbols=["AAVEUSDT", "ENAUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=2,
            expected_max_turnover_usdt=10.0,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                submitted_on_execute=1,
                planned_rows=[
                    {
                        "symbol": "AAVEUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(len(delta_calls), 2)
        cycle = summary["cycles"][0]
        owner_gate = cycle["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "passed")
        self.assertEqual(owner_gate["expected_symbols"], [])
        self.assertEqual(owner_gate["allowed_symbols"], ["AAVEUSDT", "ENAUSDT"])
        self.assertEqual(owner_gate["actual_symbols"], ["AAVEUSDT"])
        self.assertEqual(cycle["unattended_budget_gate"]["status"], "reserved")

    def test_budgeted_live_delta_blocks_symbol_outside_owner_allowed_subset(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
            unattended_budget_gate=True,
        )
        epoch_id = "owner-wide-reduce-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            expected_execution_stage="reduce_first",
            allowed_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=2,
            expected_max_turnover_usdt=10.0,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                planned_rows=[
                    {
                        "symbol": "ENAUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(delta_calls), 1)
        cycle = summary["cycles"][0]
        owner_gate = cycle["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "blocked")
        self.assertEqual(owner_gate["allowed_symbols"], ["AAVEUSDT"])
        self.assertEqual(owner_gate["actual_symbols"], ["ENAUSDT"])
        self.assertIn(
            "live_delta_owner_intent_symbol_not_allowed:allowed=AAVEUSDT:actual=ENAUSDT",
            summary["blockers"],
        )
        self.assertNotIn("unattended_budget_gate", cycle)

    def test_budgeted_live_delta_blocks_runtime_plan_drift_before_budget_reserve(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            unattended_budget_gate=True,
        )
        epoch_id = "owner-aave-reduce-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=1,
            expected_max_turnover_usdt=10.0,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="entry_second"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                planned_rows=[
                    {
                        "symbol": "ENAUSDT",
                        "side": "SELL",
                        "reduce_only": False,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(delta_calls), 1)
        cycle = summary["cycles"][0]
        owner_gate = cycle["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "blocked")
        self.assertIn("live_delta_owner_intent_stage_mismatch:expected=reduce_first:actual=entry_second", summary["blockers"])
        self.assertIn(
            "live_delta_owner_intent_symbol_mismatch:expected=AAVEUSDT:actual=ENAUSDT",
            summary["blockers"],
        )
        self.assertIn("live_delta_owner_intent_reduce_only_mismatch:expected=true:actual=false", summary["blockers"])
        self.assertNotIn("unattended_budget_gate", cycle)

    def test_fast_follow_entry_second_owner_intent_uses_fast_follow_payload(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            fast_follow_enabled=True,
            unattended_budget_gate=True,
        )
        epoch_id = "owner-fast-follow-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            max_live_cycles=2,
            max_timer_fires=2,
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=1,
            expected_max_turnover_usdt=10.0,
            fast_follow_authorized=True,
            fast_follow_expected_execution_stage="entry_second",
            fast_follow_expected_symbols=["ENAUSDT"],
            fast_follow_allowed_symbols=["ENAUSDT", "WLDUSDT"],
            fast_follow_expected_side="SELL",
            fast_follow_allowed_sides=["BUY", "SELL"],
            fast_follow_expected_reduce_only=False,
            fast_follow_expected_max_order_count=1,
            fast_follow_expected_max_turnover_usdt=10.0,
        )
        self._record_prior_live_submission(
            execution_stage="reduce_first",
            finished_at="2026-05-17T16:28:30Z",
            post_trade_reconcile_status="passed_live_position_monitor",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="entry_second"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                submitted_on_execute=1,
                planned_rows=[
                    {
                        "symbol": "ENAUSDT",
                        "side": "SELL",
                        "reduce_only": False,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        cycle = summary["cycles"][0]
        owner_gate = cycle["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "passed")
        self.assertTrue(owner_gate["fast_follow_entry_second_requested"])
        self.assertTrue(owner_gate["fast_follow_authorized"])
        self.assertEqual(owner_gate["base_expected_execution_stage"], "reduce_first")
        self.assertEqual(owner_gate["expected_execution_stage"], "entry_second")
        self.assertEqual(owner_gate["expected_symbols"], ["ENAUSDT"])
        self.assertEqual(owner_gate["allowed_symbols"], ["ENAUSDT", "WLDUSDT"])
        self.assertEqual(owner_gate["allowed_sides"], ["BUY", "SELL"])
        self.assertEqual(owner_gate["expected_reduce_only"], False)
        self.assertEqual(cycle["unattended_budget_gate"]["status"], "reserved")

    def test_fast_follow_entry_second_requires_fresh_fast_follow_owner_payload(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            fast_follow_enabled=True,
            unattended_budget_gate=True,
        )
        epoch_id = "owner-fast-follow-missing-proof-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            max_live_cycles=2,
            max_timer_fires=2,
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=1,
            expected_max_turnover_usdt=10.0,
            fast_follow_authorized=True,
        )
        self._record_prior_live_submission(
            execution_stage="reduce_first",
            finished_at="2026-05-17T16:28:30Z",
            post_trade_reconcile_status="passed_live_position_monitor",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="entry_second"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                planned_rows=[
                    {
                        "symbol": "ENAUSDT",
                        "side": "SELL",
                        "reduce_only": False,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["orders_submitted"], 0)
        owner_gate = summary["cycles"][0]["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "blocked")
        self.assertIn("live_delta_owner_intent_fast_follow_missing_expected_symbols", summary["blockers"])
        self.assertIn("live_delta_owner_intent_fast_follow_missing_expected_max_turnover_usdt", summary["blockers"])
        self.assertEqual(owner_gate["base_expected_symbols"], ["AAVEUSDT"])
        self.assertEqual(owner_gate["expected_symbols"], [])

    def test_budgeted_live_delta_blocks_turnover_above_owner_payload_before_budget_reserve(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
            unattended_budget_gate=True,
        )
        epoch_id = "owner-aave-reduce-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=1,
            expected_max_turnover_usdt=5.0,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                planned_rows=[
                    {
                        "symbol": "AAVEUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(delta_calls), 1)
        cycle = summary["cycles"][0]
        owner_gate = cycle["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "blocked")
        self.assertEqual(owner_gate["expected_symbols"], ["AAVEUSDT"])
        self.assertEqual(owner_gate["actual_symbols"], ["AAVEUSDT"])
        self.assertEqual(owner_gate["projected_turnover_usdt"], 6.0)
        self.assertIn("live_delta_owner_intent_turnover_exceeds:6.00000000>5.00000000", summary["blockers"])
        self.assertNotIn("unattended_budget_gate", cycle)

    def test_budgeted_live_delta_blocks_expired_unattended_approval_before_budget_reserve(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
            unattended_budget_gate=True,
        )
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id="expired-approval-epoch",
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            approval_expires_at_utc="2026-05-17T16:29:30Z",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                planned_rows=[
                    {
                        "symbol": "AAVEUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(delta_calls), 1)
        owner_gate = summary["cycles"][0]["live_delta_owner_intent_gate"]
        self.assertEqual(owner_gate["status"], "blocked")
        self.assertTrue(any(str(item).startswith("unattended_approval_expired:") for item in summary["blockers"]))
        self.assertNotIn("unattended_budget_gate", summary["cycles"][0])

    def test_budgeted_live_delta_blocks_completed_slot_approval_before_budget_reserve(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
            unattended_budget_gate=True,
        )
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id="completed-slot-epoch",
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            slot_status="completed",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                planned_rows=[
                    {
                        "symbol": "AAVEUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(delta_calls), 1)
        self.assertIn("unattended_approval_slot_completed", summary["blockers"])
        self.assertNotIn("unattended_budget_gate", summary["cycles"][0])

    def test_core_loop_removed_daily_pnl_gate_allows_reduce_first_execution(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
        )
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(
                plan_calls,
                status="mainnet_current_position_rebalance_plan_ready",
                execution_stage="reduce_first",
            ),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                submitted_on_execute=1,
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient(
                {"REALIZED_PNL": [{"income": "-20.0", "time": "1779000000000"}]}
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(len(delta_calls), 2)
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["daily_realized_pnl_gate"]["status"], "removed")
        self.assertNotIn("daily_pnl_new_risk_gate", cycle)
        self.assertEqual(cycle["blockers"], [])

    def test_core_loop_removed_daily_pnl_gate_allows_entry_second_execution(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="entry_second",
        )
        plan_calls: list[Namespace] = []
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner(
                plan_calls,
                status="mainnet_current_position_rebalance_plan_ready",
                execution_stage="entry_second",
            ),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                submitted_on_execute=1,
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient(
                {"REALIZED_PNL": [{"income": "-20.0", "time": "1779000000000"}]}
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_core_loop_completed")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(len(delta_calls), 2)
        self.assertFalse(delta_calls[0].execute_mainnet_delta_orders)
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)
        cycle = summary["cycles"][0]
        self.assertEqual(cycle["daily_realized_pnl_gate"]["status"], "removed")
        self.assertNotIn("daily_pnl_new_risk_gate", cycle)

    def test_core_loop_blocks_live_delta_when_stage_not_allowlisted(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", execution_stage="entry_second"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("live_delta_execution_stage_not_allowed:entry_second", summary["blockers"])
        self.assertEqual(len(delta_calls), 1)
        self.assertFalse(delta_calls[0].execute_mainnet_delta_orders)
        self.assertEqual(summary["orders_submitted"], 0)

    def test_core_loop_blocks_live_delta_when_requested_cycles_exceed_config_cap(self) -> None:
        config_path = self._config_path(live_delta_enabled=True, submit_orders=True, auto_confirm=True)
        monitor_calls: list[Namespace] = []

        def monitor(args: Namespace, **_kwargs):
            monitor_calls.append(args)
            return {}, 0

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                cycles=2,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=monitor,
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("mainnet_core_loop_requested_cycles_above_config_max:2>1", summary["blockers"])
        self.assertEqual(monitor_calls, [])

    def test_core_loop_blocks_live_delta_during_cooldown(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            cooldown_seconds=600,
        )
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_json_row(
            "run_summaries",
            "run_id",
            "prior-live-delta",
            {
                "run_id": "prior-live-delta",
                "status": "mainnet_delta_orders_submitted",
                "submitted_order_count": 1,
                "started_at_utc": "2026-05-17T16:25:00Z",
                "finished_at_utc": "2026-05-17T16:25:00Z",
            },
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertTrue(any(item.startswith("live_delta_cooldown_active:") for item in summary["blockers"]))
        self.assertEqual(summary["orders_submitted"], 0)

    def test_reduce_first_bypasses_regular_cooldown_after_reconciled_submission(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            cooldown_seconds=600,
        )
        self._record_prior_live_submission(execution_stage="reduce_first", finished_at="2026-05-17T16:28:30Z")
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="reduce_first",
                submitted_on_execute=1,
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(summary["live_delta_cooldown"]["status"], "reduce_first_cooldown_bypassed")
        self.assertEqual(summary["live_delta_cooldown"]["cooldown_bypass_reason"], "reduce_first_risk_reduction_after_prior_reconcile")
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)

    def test_reduce_first_bypass_requires_prior_reconcile_to_be_present(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            cooldown_seconds=600,
        )
        self._record_prior_live_submission(
            execution_stage="reduce_first",
            finished_at="2026-05-17T16:28:30Z",
            post_trade_reconcile_status="",
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="reduce_first"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready", execution_stage="reduce_first"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("prior_live_submission_reconcile_not_passed:missing", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_entry_second_blocked_by_unreconciled_prior_submission(self) -> None:
        # Fix (2026-06-09): a regular (non-fast-follow) entry_second must fail closed
        # when the prior live submission has not reconciled. Previously only
        # reduce_first and the fast-follow branch ran the prior-reconcile integrity
        # check, so a restart after fill-but-before-reconcile could proceed on the
        # risk-adding stage. cooldown_seconds=0 removes the cooldown as a blocker so
        # the prior-reconcile integrity check is what stops it.
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            cooldown_seconds=0,
        )
        self._record_prior_live_submission(
            execution_stage="entry_second",
            finished_at="2026-05-17T16:28:30Z",
            post_trade_reconcile_status="",
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="entry_second"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready", execution_stage="entry_second"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("prior_live_submission_reconcile_not_passed:missing", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_fast_follow_entry_second_bypasses_cooldown_after_recent_reduce_first(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            cooldown_seconds=600,
            fast_follow_enabled=True,
        )
        self._record_prior_live_submission(execution_stage="reduce_first", finished_at="2026-05-17T16:28:30Z")
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", execution_stage="entry_second", submitted_on_execute=1),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(summary["live_delta_cooldown"]["status"], "fast_follow_entry_second_allowed")
        self.assertEqual(summary["cycles"][0]["live_delta_policy_gate"]["execution_stage"], "entry_second")
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)

    def test_fast_follow_entry_second_uses_unattended_approval_window_beyond_legacy_180s_age(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            cooldown_seconds=600,
            fast_follow_enabled=True,
            fast_follow_max_age_seconds=180,
            unattended_budget_gate=True,
        )
        epoch_id = "owner-fast-follow-window-epoch"
        _open_budget_epoch_and_arm_unattended_approval(
            self.temp_dir / "state.sqlite3",
            epoch_id=epoch_id,
            max_live_cycles=2,
            max_timer_fires=2,
            expected_execution_stage="reduce_first",
            expected_symbols=["AAVEUSDT"],
            expected_side="BUY",
            expected_reduce_only=True,
            expected_max_order_count=1,
            expected_max_turnover_usdt=10.0,
            fast_follow_authorized=True,
            fast_follow_expected_execution_stage="entry_second",
            fast_follow_expected_symbols=["ENAUSDT"],
            fast_follow_expected_side="SELL",
            fast_follow_expected_reduce_only=False,
            fast_follow_expected_max_order_count=1,
            fast_follow_expected_max_turnover_usdt=10.0,
        )
        self._record_prior_live_submission(
            execution_stage="reduce_first",
            finished_at="2026-05-17T16:26:00Z",
            post_trade_reconcile_status="passed_live_position_monitor",
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready", execution_stage="entry_second"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                submitted_on_execute=1,
                planned_rows=[
                    {
                        "symbol": "ENAUSDT",
                        "side": "SELL",
                        "reduce_only": False,
                        "rounded_notional_usdt": 6.0,
                    }
                ],
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        gate = summary["live_delta_cooldown"]["fast_follow_entry_second_gate"]
        self.assertEqual(gate["status"], "passed")
        self.assertGreater(summary["live_delta_cooldown"]["seconds_since_latest_live_order_submission"], 180.0)
        self.assertEqual(gate["configured_max_age_seconds"], 180.0)
        self.assertEqual(gate["max_age_source"], "unattended_approval_timer_window")
        self.assertEqual(gate["approval_gate_status"], "passed")
        self.assertEqual(summary["live_delta_cooldown"]["status"], "fast_follow_entry_second_allowed")

    def test_fast_follow_after_reduce_allows_residual_reduce_first_stage(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="reduce_first,entry_second",
            cooldown_seconds=600,
            fast_follow_enabled=True,
        )
        self._record_prior_live_submission(execution_stage="reduce_first", finished_at="2026-05-17T16:28:30Z")
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(delta_calls, status="mainnet_delta_execution_ready", execution_stage="reduce_first", submitted_on_execute=1),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(summary["cycles"][0]["live_delta_policy_gate"]["execution_stage"], "reduce_first")
        self.assertEqual(summary["cycles"][0]["live_delta_policy_gate"]["fast_follow_after_reduce_allowed_stages"], ["entry_second", "reduce_first"])
        self.assertEqual(len(delta_calls), 2)
        self.assertFalse(delta_calls[0].execute_mainnet_delta_orders)
        self.assertTrue(delta_calls[1].execute_mainnet_delta_orders)

    def test_fast_follow_entry_second_requires_recent_reduce_first_source(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            cooldown_seconds=600,
            fast_follow_enabled=True,
        )
        self._record_prior_live_submission(execution_stage="entry_second", finished_at="2026-05-17T16:28:30Z")

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("fast_follow_entry_second_requires_prior_reduce_first:entry_second", summary["blockers"])

    def test_fast_follow_entry_second_requires_prior_reconcile_to_be_present(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            cooldown_seconds=600,
            fast_follow_enabled=True,
        )
        self._record_prior_live_submission(
            execution_stage="reduce_first",
            finished_at="2026-05-17T16:28:30Z",
            post_trade_reconcile_status="",
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
                fast_follow_entry_second=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner([], status="mainnet_delta_execution_ready"),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("fast_follow_entry_second_prior_reconcile_not_passed:missing", summary["blockers"])

    def test_target_leg_aware_order_cap_allows_target_leg_batch_above_legacy_cap(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="entry_second",
            target_leg_order_cap_policy=True,
        )
        delta_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(
                delta_calls,
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                planned_order_count=11,
                submitted_on_execute=11,
                target_position_count=11,
                current_position_count=8,
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        policy = summary["cycles"][0]["live_delta_policy_gate"]
        self.assertEqual(policy["planned_delta_order_count"], 11)
        self.assertEqual(policy["live_delta_order_cap_gate"]["mode"], "target_leg_aware")
        self.assertEqual(policy["live_delta_order_cap_gate"]["effective_max_live_delta_order_count"], 11)
        self.assertEqual(summary["orders_submitted"], 11)

    def test_target_leg_aware_order_cap_still_blocks_above_hard_cap(self) -> None:
        config_path = self._config_path(
            live_delta_enabled=True,
            submit_orders=True,
            auto_confirm=True,
            allowed_execution_stages="entry_second",
            target_leg_order_cap_policy=True,
        )

        summary, exit_code = run_mainnet_core_loop(
            _args(
                config_path,
                execute_live_delta=True,
                operator_enable=True,
                understand=True,
                daily_active_ack=True,
            ),
            env=_env(),
            monitor_runner=self._monitor_runner(available=300.0, wallet=1000.0),
            plan_runner=self._plan_runner([], status="mainnet_current_position_rebalance_plan_ready"),
            delta_runner=self._delta_runner(
                [],
                status="mainnet_delta_execution_ready",
                execution_stage="entry_second",
                planned_order_count=21,
                target_position_count=21,
                current_position_count=8,
            ),
            account_client_factory=lambda **_kwargs: _FakeIncomeClient({"REALIZED_PNL": []}),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("live_delta_planned_order_count_above_effective_cap:21>20", summary["blockers"])

    def _monitor_runner(self, *, available: float, wallet: float, open_orders: int = 0):
        def run(_args: Namespace, **_kwargs):
            root = self.temp_dir / "monitor-artifacts" / f"monitor-{available}-{open_orders}"
            root.mkdir(parents=True, exist_ok=True)
            write_json(
                root / "monitor_report.json",
                {
                    "account": {
                        "available_balance_usdt": available,
                        "total_wallet_balance_usdt": wallet,
                        "open_order_count": open_orders,
                        "open_positions_redacted": [{"symbol": "L1USDT", "positionAmt": 1.0}],
                        "open_orders_redacted": [],
                    },
                    "reference": {"source": "unit_test"},
                },
            )
            return (
                {
                    "status": "passed_live_position_monitor",
                    "blockers": [],
                    "artifact_root": str(root),
                    "open_order_count": open_orders,
                    "open_position_count": 1,
                },
                0,
            )

        return run

    def _plan_runner(
        self,
        calls: list[Namespace],
        *,
        status: str,
        execution_stage: str = "entry_second",
        frozen_snapshot: dict | None = None,
    ):
        def run(args: Namespace, **_kwargs):
            calls.append(args)
            root = self.temp_dir / "plan-artifacts" / f"plan-{len(calls)}"
            _write_plan_artifact(
                root,
                status=status,
                execution_stage=execution_stage,
                frozen_snapshot=frozen_snapshot,
            )
            return (
                {
                    "status": status,
                    "blockers": [],
                    "artifact_root": str(root),
                    "planned_delta_order_count": (
                        1
                        if status
                        in {"mainnet_current_position_rebalance_plan_ready", "mainnet_current_position_rebalance_deferred"}
                        else 0
                    ),
                    "active_execution_phase": execution_stage,
                    "dust_delta_noop": status == "mainnet_current_position_rebalance_dust_noop",
                    "dust_delta_symbols": ["L1USDT"] if status == "mainnet_current_position_rebalance_dust_noop" else [],
                    "capital_topup_gate_status": "deferred"
                    if status == "mainnet_current_position_rebalance_deferred"
                    else "not_requested",
                    "capital_topup_gate_blockers": [],
                },
                0,
            )

        return run

    def _plan_runner_sequence(
        self,
        calls: list[Namespace],
        *,
        statuses: list[str],
        topup_notional: float = 100.0,
    ):
        def run(args: Namespace, **_kwargs):
            calls.append(args)
            status = statuses[min(len(calls) - 1, len(statuses) - 1)]
            root = self.temp_dir / "plan-artifacts" / f"plan-{len(calls)}"
            _write_plan_artifact(root, status=status, rounded_notional=topup_notional)
            return (
                {
                    "status": status,
                    "blockers": [],
                    "artifact_root": str(root),
                    "planned_delta_order_count": 1 if status == "mainnet_current_position_rebalance_plan_ready" else 0,
                    "dust_delta_noop": status == "mainnet_current_position_rebalance_dust_noop",
                    "dust_delta_symbols": ["L1USDT"] if status == "mainnet_current_position_rebalance_dust_noop" else [],
                    "capital_topup_requested": bool(getattr(args, "capital_topup", False)),
                },
                0,
            )

        return run

    def _delta_runner(
        self,
        calls: list[Namespace],
        *,
        status: str,
        execution_stage: str = "entry_second",
        submitted_on_execute: int = 0,
        planned_order_count: int = 1,
        target_position_count: int = 1,
        current_position_count: int = 1,
        planned_rows: list[dict] | None = None,
        deferred_phase_counts: dict[str, int] | None = None,
    ):
        def run(args: Namespace, **_kwargs):
            calls.append(args)
            root = self.temp_dir / "delta-artifacts" / f"delta-{len(calls)}"
            root.mkdir(parents=True, exist_ok=True)
            rows = (
                [dict(row) for row in planned_rows]
                if planned_rows is not None
                else [
                    {
                        "symbol": f"L{idx}USDT",
                        "side": "SELL" if execution_stage == "reduce_first" else "BUY",
                        "reduce_only": execution_stage == "reduce_first",
                        "rounded_notional_usdt": 10.0,
                    }
                    for idx in range(1, planned_order_count + 1)
                ]
            )
            row_count = len(rows) if planned_rows is not None else int(planned_order_count)
            submitted_count = min(int(submitted_on_execute), row_count) if bool(args.execute_mainnet_delta_orders) else 0
            write_json(root / "run_summary.json", {"status": status, "blockers": [], "required_confirmation": "CONFIRM"})
            write_json(root / "account_before.json", {"open_order_count": 0, "open_positions_redacted": []})
            write_json(root / "mainnet_delta_preflight.json", {"status": "passed", "blockers": [], "execution_stage": execution_stage})
            write_json(root / "daily_realized_pnl_gate.json", {"status": "removed", "blockers": [], "enforcement": "disabled"})
            write_json(
                root / "planned_delta_orders.json",
                {"row_count": int(row_count), "rows": rows},
            )
            submitted_rows = [
                {
                    "symbol": row.get("symbol"),
                    "planned_rounded_notional_usdt": row.get("rounded_notional_usdt", 0.0),
                }
                for row in rows[:submitted_count]
            ]
            fill_rows = [{"symbol": row["symbol"], "notional_usdt": row["planned_rounded_notional_usdt"]} for row in submitted_rows]
            pd.DataFrame(submitted_rows).to_csv(root / "submitted_orders.csv", index=False)
            pd.DataFrame(fill_rows).to_csv(root / "fills.csv", index=False)
            write_json(root / "mainnet_delta_execution.json", {"submitted_orders": submitted_rows, "fills": fill_rows})
            non_reduce_count = 0 if execution_stage in {"reduce_first", "noop", "dust_noop"} else int(row_count)
            return (
                {
                    "status": "mainnet_delta_orders_submitted" if submitted_count else status,
                    "blockers": [],
                    "artifact_root": str(root),
                    "required_confirmation": "CONFIRM",
                    "execution_stage": execution_stage,
                    "planned_execution_phases": [execution_stage],
                    "planned_delta_order_count": int(row_count),
                    "reduce_only_intent_count": int(row_count) if non_reduce_count == 0 else 0,
                    "non_reduce_only_intent_count": non_reduce_count,
                    "target_position_count": int(target_position_count),
                    "current_position_count": int(current_position_count),
                    "phase_counts": {execution_stage: int(row_count)},
                    "deferred_phase_counts": dict(deferred_phase_counts or {}),
                    "submitted_order_count": submitted_count,
                    "fill_count": submitted_count,
                },
                0,
            )

        return run

    def _config_path(
        self,
        *,
        daily_enforcement: str = "active",
        live_delta_enabled: bool = False,
        submit_orders: bool = False,
        auto_confirm: bool = False,
        allowed_execution_stages: str = "",
        cooldown_seconds: int = 0,
        fast_follow_enabled: bool = False,
        fast_follow_max_age_seconds: int = 900,
        capital_topup: bool = False,
        capital_topup_live_execution: bool = True,
        target_engine: str = "",
        allow_multiphase_live_delta: bool = False,
        target_leg_order_cap_policy: bool = False,
        unattended_budget_gate: bool = False,
        include_margin_thresholds: bool = True,
    ) -> Path:
        config_path = self.temp_dir / "core_loop.yaml"
        config_path.write_text(
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
                    "  require_manual_live_confirm: true",
                    "  max_daily_realized_loss_usdt: 10.0",
                    f"  max_daily_realized_loss_enforcement: {daily_enforcement}",
                    "  daily_realized_pnl_income_types: REALIZED_PNL",
                    *(
                        [
                            "  min_available_balance_after_plan_usdt: 100.0",
                            "  min_available_balance_ratio_after_plan: 0.05",
                            "  min_margin_cushion_after_plan_usdt: 100.0",
                        ]
                        if include_margin_thresholds
                        else []
                    ),
                    *(
                        [
                            "capital_topup:",
                            "  enabled: true",
                            "  min_additional_allocated_capital_usdt: 25.0",
                            "  require_balanced_all_or_none: true",
                            "  allowed_delta_classifications: increase_same_side,new_entry,dust_residual,no_delta",
                            f"  live_execution_enabled: {str(capital_topup_live_execution).lower()}",
                        ]
                        if capital_topup
                        else []
                    ),
                    "core_loop:",
                    *([f"  target_engine: {target_engine}"] if target_engine else []),
                    "  max_cycles_per_invocation: 1",
                    "  interval_seconds: 0",
                    "  target_as_of: latest_closed_rebalance_slot",
                    "  capital_topup_after_static_noop: true",
                    f"  live_delta_enabled: {str(live_delta_enabled).lower()}",
                    f"  submit_orders: {str(submit_orders).lower()}",
                    f"  auto_confirm_delta_after_preflight: {str(auto_confirm).lower()}",
                    f"  allowed_execution_stages: {allowed_execution_stages}",
                    f"  allow_multiphase_live_delta: {str(allow_multiphase_live_delta).lower()}",
                    f"  unattended_budget_gate_enabled: {str(unattended_budget_gate).lower()}",
                    "  max_live_delta_order_count_per_cycle: 6",
                    *(
                        [
                            "  live_delta_order_cap_policy:",
                            "    mode: target_leg_aware",
                            "    hard_max_order_count: 20",
                            "    reduce_first_extra_stale_exit_allowance: 5",
                            "    entry_second_cap_basis: target_position_count",
                            "    reduce_first_cap_basis: max_current_or_target_position_count",
                        ]
                        if target_leg_order_cap_policy
                        else []
                    ),
                    f"  min_seconds_between_live_delta_executions: {cooldown_seconds}",
                    f"  fast_follow_entry_second_enabled: {str(fast_follow_enabled).lower()}",
                    "  fast_follow_entry_second_min_delay_seconds: 60",
                    f"  fast_follow_entry_second_max_age_seconds: {int(fast_follow_max_age_seconds)}",
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _record_prior_live_submission(
        self,
        *,
        execution_stage: str,
        finished_at: str,
        post_trade_reconcile_status: str = "passed_live_position_monitor",
    ) -> None:
        post_trade = {"status": post_trade_reconcile_status} if post_trade_reconcile_status else {}
        LiveTradingStateStore(self.temp_dir / "state.sqlite3").write_json_row(
            "run_summaries",
            "run_id",
            f"prior-{execution_stage}",
            {
                "run_id": f"prior-{execution_stage}",
                "status": "mainnet_core_loop_completed",
                "orders_submitted": 2,
                "fill_count": 2,
                "live_delta_authorized": True,
                "started_at_utc": finished_at,
                "finished_at_utc": finished_at,
                "cycles": [
                    {
                        "status": "cycle_executed_reconciled",
                        "live_delta_policy_gate": {"execution_stage": execution_stage},
                        "post_trade_reconcile": post_trade,
                    }
                ],
            },
        )


class _FakeIncomeClient:
    def __init__(self, rows_by_type: dict[str, list[dict]]) -> None:
        self.rows_by_type = rows_by_type

    def income_history(self, *, income_type: str, **_kwargs):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=list(self.rows_by_type.get(income_type, [])))


def _write_plan_artifact(
    root: Path,
    *,
    status: str,
    rounded_notional: float = 100.0,
    execution_stage: str = "entry_second",
    frozen_snapshot: dict | None = None,
    frozen_slot_gate_override: dict | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    is_dust = status == "mainnet_current_position_rebalance_dust_noop"
    active_execution_phase = "dust_noop" if is_dust else str(execution_stage)
    reduce_only = active_execution_phase == "reduce_first"
    write_json(
        root / "run_summary.json",
        {
            "run_id": "plan-1",
            "status": status,
            "blockers": [],
            "current_position_aware": True,
            "plan_only": True,
            "mainnet_order_submission_authorized": False,
            "recurring_mainnet_enabled": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "risk_gate_status": "passed",
            "execution_plan_status": "dust_noop" if is_dust else "ok",
            "active_execution_phase": active_execution_phase,
            "phase_counts": {"dust_noop": 1} if is_dust else {active_execution_phase: 1},
            "deferred_phase_counts": {},
            "target_position_count": 1,
            "current_position_count": 1,
            "dust_delta_noop": is_dust,
            "dust_delta_symbols": ["L1USDT"] if is_dust else [],
            "dust_delta_blockers": ["quantity_below_min:L1USDT", "notional_below_min:L1USDT"] if is_dust else [],
        },
    )
    write_json(root / "market_data_audit.json", {"source": "unit_test", "row_count": 10})
    write_json(root / "decision_snapshot.json", {"status": "ok", "rebalance_slot": True, "decision_id": "decision-1"})
    write_json(root / "target_portfolio.json", {"portfolio_id": "portfolio-1", "status": "ok"})
    write_json(root / "risk_gate.json", {"decision": "allow_plan", "passed": True, "blockers": []})
    write_json(
        root / "execution_plan.json",
        {
            "status": "dust_noop" if is_dust else "ok",
            "mode": "plan_only",
            "blockers": ["quantity_below_min:L1USDT", "notional_below_min:L1USDT"] if is_dust else [],
            "active_execution_phase": active_execution_phase,
            "phase_counts": {"dust_noop": 1} if is_dust else {active_execution_phase: 1},
            "deferred_phase_counts": {},
        },
    )
    pd.DataFrame([{"symbol": "L1USDT", "positionAmt": 1.0}]).to_csv(root / "current_positions.csv", index=False)
    pd.DataFrame([{"symbol": "L1USDT", "target_position_amt": 2.0}]).to_csv(root / "target_positions.csv", index=False)
    pd.DataFrame(
        []
        if is_dust
        else [
            {
                "symbol": "L1USDT",
                "execution_phase": active_execution_phase,
                "delta_classification": "reduce_same_side" if reduce_only else "increase_same_side",
                "reduce_only": reduce_only,
                "no_order_required": False,
                "rounded_notional_usdt": 0.0 if reduce_only else float(rounded_notional),
                "order_delta_position_amt": -1.0 if reduce_only else 1.0,
                "mark_price": float(rounded_notional),
                "blockers": "",
            }
        ]
    ).to_csv(root / "order_sizing_report.csv", index=False)
    pd.DataFrame(
        []
        if is_dust
        else [
            {
                "symbol": "L1USDT",
                "quantity": 1.0,
                "side": "SELL" if reduce_only else "BUY",
                "execution_phase": active_execution_phase,
                "reduce_only": reduce_only,
            }
        ]
    ).to_csv(
        root / "execution_plan.csv",
        index=False,
    )
    if frozen_snapshot:
        write_json(root / "frozen_target_snapshot.json", frozen_snapshot)
        frozen_gate = frozen_slot_gate_override or {
            "status": "hold_until_next_rebalance_slot"
            if status == "mainnet_current_position_rebalance_hold_until_next_rebalance_slot"
            else "reuse_frozen_slot_target",
            "slot_id": str(frozen_snapshot.get("slot_id") or ""),
            "active_target_hash": str(frozen_snapshot.get("target_hash") or ""),
        }
        write_json(root / "frozen_slot_gate.json", frozen_gate)


def _frozen_slot_snapshot(*, status: str) -> dict:
    return {
        "schema_version": "daily_rebalance_slot_target.v1",
        "status": status,
        "slot_id": "multiphase_current_position_target:hv_balanced:1779004800000",
        "target_hash": "hash-1",
        "target_engine": "multiphase_current_position_target",
        "strategy_label": "hv_balanced",
        "decision_id": "decision-1",
        "portfolio_id": "portfolio-1",
        "resolved_capital_usdt": 1000.0,
        "positions": [
            {
                "symbol": "L1USDT",
                "target_weight": 0.1,
                "target_notional_usdt": 100.0,
                "resolved_capital_usdt": 1000.0,
                "reference_price": 100.0,
                "target_position_amt": 1.0,
            }
        ],
    }


def _open_budget_epoch_and_arm_unattended_approval(
    db_path: Path,
    *,
    epoch_id: str,
    max_live_cycles: int = 1,
    expected_execution_stage: str,
    expected_symbols: list[str] | None = None,
    allowed_symbols: list[str] | None = None,
    expected_side: str = "BUY",
    expected_reduce_only: bool = True,
    expected_max_order_count: int = 1,
    expected_max_turnover_usdt: float = 10.0,
    max_timer_fires: int = 1,
    fast_follow_authorized: bool = False,
    fast_follow_expected_execution_stage: str = "",
    fast_follow_expected_symbols: list[str] | None = None,
    fast_follow_allowed_symbols: list[str] | None = None,
    fast_follow_expected_side: str = "",
    fast_follow_allowed_sides: list[str] | None = None,
    fast_follow_expected_reduce_only: bool | None = None,
    fast_follow_expected_max_order_count: int | None = None,
    fast_follow_expected_max_turnover_usdt: float | None = None,
    slot_status: str = "open",
    approval_expires_at_utc: str = "2026-05-17T16:45:00Z",
) -> None:
    budget_store = UnattendedBudgetStore(db_path)
    budget_store.open_epoch(
        epoch_id=epoch_id,
        max_live_cycles=max_live_cycles,
        max_gross_turnover_usdt=20.0,
        max_age_seconds=900,
        now_utc=_fixed_now(),
        reason="unit test unattended owner approval epoch",
    )
    store = LiveTradingStateStore(db_path)
    snapshot = _frozen_slot_snapshot(status=slot_status)
    snapshot["slot_id"] = "unit-owner-intent-slot"
    snapshot["target_hash"] = "unit-owner-intent-hash"
    store.write_rebalance_slot_target(snapshot)
    payload = {
        "contract_version": UNATTENDED_EPOCH_APPROVAL_CONTRACT,
        "epoch_id": epoch_id,
        "expected_epoch_id": epoch_id,
        "budget_epoch_id": epoch_id,
        "slot_id": snapshot["slot_id"],
        "target_hash": snapshot["target_hash"],
        "approval_created_at_utc": "2026-05-17T16:29:00Z",
        "approval_expires_at_utc": approval_expires_at_utc,
        "timer_window": {
            "timer_name": "unit-test-supervisor.timer",
            "timer_enable_earliest_utc": "2026-05-17T16:29:00Z",
            "timer_enable_latest_utc": "2026-05-17T16:45:00Z",
            "max_timer_fires_authorized": int(max_timer_fires),
        },
        "max_timer_fires": int(max_timer_fires),
        "expected_execution_stage": expected_execution_stage,
        "expected_side": expected_side,
        "expected_reduce_only": expected_reduce_only,
        "expected_max_order_count": expected_max_order_count,
        "expected_max_turnover_usdt": expected_max_turnover_usdt,
    }
    if expected_symbols is not None:
        payload["expected_symbols"] = list(expected_symbols)
    if allowed_symbols is not None:
        payload["allowed_symbols"] = list(allowed_symbols)
    if fast_follow_authorized:
        payload.update(
            {
                "fast_follow_authorized": True,
                "fast_follow_owner_decision": "approve_fast_follow_under_current_budget_epoch",
                "fast_follow_epoch_id": epoch_id,
                "fast_follow_max_chain_depth": 1,
                "fast_follow_cleanup_required": True,
            }
        )
        if fast_follow_expected_execution_stage:
            payload["fast_follow_expected_execution_stage"] = fast_follow_expected_execution_stage
        if fast_follow_expected_symbols is not None:
            payload["fast_follow_expected_symbols"] = list(fast_follow_expected_symbols)
        if fast_follow_allowed_symbols is not None:
            payload["fast_follow_allowed_symbols"] = list(fast_follow_allowed_symbols)
        if fast_follow_expected_side:
            payload["fast_follow_expected_side"] = fast_follow_expected_side
        if fast_follow_allowed_sides is not None:
            payload["fast_follow_allowed_sides"] = list(fast_follow_allowed_sides)
        if fast_follow_expected_reduce_only is not None:
            payload["fast_follow_expected_reduce_only"] = bool(fast_follow_expected_reduce_only)
        if fast_follow_expected_max_order_count is not None:
            payload["fast_follow_expected_max_order_count"] = int(fast_follow_expected_max_order_count)
        if fast_follow_expected_max_turnover_usdt is not None:
            payload["fast_follow_expected_max_turnover_usdt"] = float(fast_follow_expected_max_turnover_usdt)
    store.record_operator_action(
        run_id="operator-arm-owner-intent",
        action_type="arm-live-delta",
        reason="unit test owner intent",
        created_at_utc="2026-05-17T16:29:00Z",
        payload=payload,
    )


def _args(
    config_path: Path,
    *,
    execute_live_delta: bool = False,
    as_of: str = "now",
    cycles: int | None = None,
    operator_enable: bool = False,
    understand: bool = False,
    daily_active_ack: bool = False,
    ignore_heartbeat_run_id: str = "",
    capital_topup: bool = False,
    fast_follow_entry_second: bool = False,
) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of=as_of,
        fixture_panel="",
        symbols="",
        public_market_data=False,
        reference_run="",
        cycles=cycles,
        interval_seconds=None,
        execute_live_delta=execute_live_delta,
        operator_enable_live_delta_for_this_run=operator_enable,
        i_understand_this_places_real_mainnet_delta_orders=understand,
        i_understand_daily_realized_pnl_gate_is_active=daily_active_ack,
        confirm_mainnet_delta_execution="",
        position_tolerance=1e-9,
        ignore_heartbeat_run_id=ignore_heartbeat_run_id,
        capital_topup=capital_topup,
        fast_follow_entry_second=fast_follow_entry_second,
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 16, 30, 0, tzinfo=UTC)


def _live_artifact_count(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM live_artifacts").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
