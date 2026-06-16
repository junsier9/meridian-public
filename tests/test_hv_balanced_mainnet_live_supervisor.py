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

from enhengclaw.live_trading.mainnet_live_supervisor import run_mainnet_live_supervisor  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402


class HvBalancedMainnetLiveSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-live-supervisor-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_unarmed_supervisor_calls_core_loop_without_live_delta_execution(self) -> None:
        config_path = self._config_path()
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertFalse(summary["live_delta_armed_at_start"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(len(core_calls), 1)
        self.assertFalse(core_calls[0].execute_live_delta)
        self.assertFalse(core_calls[0].operator_enable_live_delta_for_this_run)
        self.assertFalse(core_calls[0].i_understand_this_places_real_mainnet_delta_orders)
        self.assertFalse(core_calls[0].i_understand_daily_realized_pnl_gate_is_active)
        self.assertTrue(core_calls[0].ignore_heartbeat_run_id.endswith("-mainnet-live-supervisor"))

    def test_unarmed_supervisor_passes_multiphase_target_engine_to_core_loop(self) -> None:
        config_path = self._config_path(target_engine="multiphase_equal_sleeve")
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertEqual(summary["target_engine"], "multiphase_equal_sleeve")
        self.assertEqual(len(core_calls), 1)
        self.assertEqual(core_calls[0].target_engine, "multiphase_equal_sleeve")
        self.assertFalse(core_calls[0].execute_live_delta)

    def test_armed_supervisor_passes_live_delta_flags_to_core_loop(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls, orders_submitted=1, fill_count=1),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertTrue(summary["live_delta_armed_at_start"])
        self.assertTrue(summary["live_delta_armed_at_finish"])
        self.assertTrue(summary["live_delta_authorized"])
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(len(core_calls), 1)
        self.assertTrue(core_calls[0].execute_live_delta)
        self.assertTrue(core_calls[0].operator_enable_live_delta_for_this_run)
        self.assertTrue(core_calls[0].i_understand_this_places_real_mainnet_delta_orders)
        self.assertFalse(core_calls[0].i_understand_daily_realized_pnl_gate_is_active)
        self.assertFalse(core_calls[0].capital_topup)

    def test_armed_multiphase_target_engine_fails_closed_without_explicit_allow_flag(self) -> None:
        config_path = self._config_path(target_engine="multiphase_equal_sleeve")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("supervisor_multiphase_target_engine_live_delta_not_explicitly_allowed", summary["blockers"])
        self.assertEqual(core_calls, [])
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_armed_multiphase_target_engine_passes_live_delta_flags_when_explicitly_allowed(self) -> None:
        config_path = self._config_path(target_engine="multiphase_equal_sleeve", allow_multiphase_live_delta=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls, orders_submitted=1, fill_count=1),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertEqual(summary["target_engine"], "multiphase_equal_sleeve")
        self.assertEqual(len(core_calls), 1)
        self.assertEqual(core_calls[0].target_engine, "multiphase_equal_sleeve")
        self.assertTrue(core_calls[0].execute_live_delta)
        self.assertTrue(summary["live_delta_authorized"])

    def test_supervisor_passes_controlled_capital_topup_flag_when_enabled(self) -> None:
        config_path = self._config_path(capital_topup_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertTrue(core_calls[0].execute_live_delta)
        self.assertTrue(core_calls[0].capital_topup)

    def test_successful_reduce_first_schedules_fast_follow_entry_second(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=3)
        core_calls: list[Namespace] = []
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                core_calls,
                orders_submitted=2,
                fill_count=2,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "scheduled")
        self.assertEqual(schedule["delay_seconds"], 90)
        self.assertEqual(schedule["source_gate"]["execution_stage"], "reduce_first")
        self.assertEqual(schedule["authorization_gate"]["status"], "passed")
        self.assertEqual(schedule["authorization_gate"]["authorized_epoch_id"], "ff-epoch")
        self.assertEqual(schedule["chain_depth"], 1)
        self.assertEqual(schedule["max_chain_depth"], 3)
        self.assertEqual(len(commands), 1)
        self.assertIn("--collect", commands[0])
        self.assertIn("--property=RuntimeMaxSec=420", commands[0])
        self.assertIn("--fast-follow-entry-second", commands[0])
        self.assertIn("--fast-follow-chain-depth", commands[0])
        self.assertIn("1", commands[0])
        self.assertIn("--on-active=90s", commands[0])

    def test_fast_follow_skips_without_owner_authorization_even_after_reduce_first(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm without fast-follow authorization",
            created_at_utc="2026-05-18T00:00:00Z",
            payload={"epoch_id": "ff-epoch"},
        )
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                [],
                orders_submitted=2,
                fill_count=2,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "skipped")
        self.assertEqual(schedule["reason"], "fast_follow_owner_authorization_gate_blocked")
        self.assertIn("fast_follow_owner_authorization_missing", schedule["authorization_gate"]["blockers"])
        self.assertEqual(commands, [])

    def test_fast_follow_skips_when_epoch_is_not_open(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=3)
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                [],
                orders_submitted=1,
                fill_count=1,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "skipped")
        self.assertIn("fast_follow_requires_open_budget_epoch", schedule["authorization_gate"]["blockers"])
        self.assertEqual(commands, [])

    def test_reconcile_aware_fast_follow_respects_core_min_delay_and_dynamic_chain_cap(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True, reconcile_aware_fast_follow=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=4)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=4)
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                [],
                orders_submitted=2,
                fill_count=2,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
                deferred_phase_counts={"entry_second": 4},
                target_position_count=11,
                current_position_count=11,
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "scheduled")
        self.assertEqual(schedule["delay_seconds"], 60)
        self.assertEqual(schedule["delay_reason"], "deferred_entry_second_after_reconciled_reduce")
        self.assertEqual(schedule["delay_context"]["raw_delay_seconds"], 20)
        self.assertEqual(schedule["delay_context"]["configured_delay_seconds"], 20)
        self.assertEqual(schedule["delay_context"]["core_min_delay_seconds"], 60)
        self.assertEqual(schedule["max_chain_depth"], 4)
        self.assertIn("--on-active=60s", commands[0])

    def test_fast_follow_invocation_passes_flag_and_reschedules_reduce_first_residual(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=3)
        core_calls: list[Namespace] = []
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path, fast_follow_entry_second=True, fast_follow_chain_depth=1),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                core_calls,
                orders_submitted=1,
                fill_count=1,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(core_calls[0].fast_follow_entry_second)
        self.assertTrue(core_calls[0].execute_live_delta)
        self.assertTrue(core_calls[0].operator_enable_live_delta_for_this_run)
        self.assertTrue(core_calls[0].i_understand_this_places_real_mainnet_delta_orders)
        invocation_gate = summary["cycles"][0]["fast_follow_invocation_authorization_gate"]
        self.assertEqual(invocation_gate["status"], "passed")
        self.assertEqual(invocation_gate["validation_mode"], "fast_follow_invocation")
        self.assertEqual(invocation_gate["current_chain_depth"], 1)
        self.assertEqual(invocation_gate["authorized_epoch_id"], "ff-epoch")
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "scheduled")
        self.assertEqual(schedule["chain_depth"], 2)
        self.assertEqual(len(commands), 1)
        self.assertIn("--fast-follow-chain-depth", commands[0])
        self.assertIn("2", commands[0])

    def test_fast_follow_invocation_blocks_without_owner_payload_before_core_loop(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm without fast-follow authorization",
            created_at_utc="2026-05-18T00:00:00Z",
            payload={"epoch_id": "ff-epoch"},
        )
        core_calls: list[Namespace] = []
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path, fast_follow_entry_second=True, fast_follow_chain_depth=1),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls, orders_submitted=1, fill_count=1),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(core_calls, [])
        self.assertEqual(commands, [])
        self.assertIn("fast_follow_invocation_owner_authorization_gate_blocked", summary["blockers"])
        self.assertIn("fast_follow_owner_authorization_missing", summary["blockers"])
        invocation_gate = summary["cycles"][0]["fast_follow_invocation_authorization_gate"]
        self.assertEqual(invocation_gate["status"], "blocked")
        self.assertEqual(invocation_gate["current_chain_depth"], 1)
        self.assertEqual(invocation_gate["authorized_epoch_id"], "ff-epoch")
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_fast_follow_invocation_respects_zero_policy_chain_cap(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True, fast_follow_max_chain_invocations=0)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=3)
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path, fast_follow_entry_second=True, fast_follow_chain_depth=1),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls, orders_submitted=1, fill_count=1),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(core_calls, [])
        self.assertIn("fast_follow_policy_chain_depth_exhausted:1>0", summary["blockers"])
        invocation_gate = summary["cycles"][0]["fast_follow_invocation_authorization_gate"]
        self.assertEqual(invocation_gate["status"], "blocked")
        self.assertEqual(invocation_gate["policy_max_chain_depth"], 0)

    def test_fast_follow_skips_when_owner_chain_depth_is_exhausted(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=1)
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path, fast_follow_entry_second=True, fast_follow_chain_depth=1),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                [],
                orders_submitted=1,
                fill_count=1,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "skipped")
        self.assertEqual(schedule["reason"], "fast_follow_owner_authorization_gate_blocked")
        self.assertIn("fast_follow_owner_chain_depth_exhausted:2>1", schedule["authorization_gate"]["blockers"])
        self.assertEqual(commands, [])

    def test_fast_follow_reduce_first_residual_stops_rescheduling_at_chain_limit(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=3)
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path, fast_follow_entry_second=True, fast_follow_chain_depth=3),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                [],
                orders_submitted=1,
                fill_count=1,
                execution_stage="reduce_first",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedule"]
        self.assertEqual(schedule["status"], "skipped")
        self.assertEqual(schedule["reason"], "fast_follow_chain_depth_exhausted")
        self.assertEqual(schedule["chain_depth"], 3)
        self.assertEqual(commands, [])

    def test_entry_second_execution_does_not_schedule_fast_follow(self) -> None:
        config_path = self._config_path(fast_follow_enabled=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _open_budget_epoch(self.temp_dir / "state.sqlite3", max_live_cycles=3)
        _arm_fast_follow(store, epoch_id="ff-epoch", max_chain_depth=3)
        commands: list[list[str]] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                [],
                orders_submitted=1,
                fill_count=1,
                execution_stage="entry_second",
                core_cycle_status="cycle_executed_reconciled",
                post_trade_reconcile_status="passed_live_position_monitor",
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
            command_runner=_command_runner(commands),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["fast_follow_entry_second_schedule"]["status"], "skipped")
        self.assertEqual(summary["fast_follow_entry_second_schedule"]["reason"], "latest_cycle_not_reduce_first_source")
        self.assertEqual(commands, [])

    def test_pause_skips_core_loop_and_disarms_live_delta(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        store.record_operator_action(
            run_id="operator-pause",
            action_type="pause",
            reason="operator pause",
            created_at_utc="2026-05-18T00:01:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("operator_paused", summary["blockers"])
        self.assertEqual(core_calls, [])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_core_loop_blocker_disarms_live_delta(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(
                core_calls,
                status="mainnet_core_loop_blocked",
                exit_code=2,
                blockers=["daily_realized_pnl_breach:-11.0<-10.0"],
            ),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertTrue(core_calls[0].execute_live_delta)
        self.assertIn("daily_realized_pnl_breach:-11.0<-10.0", summary["blockers"])
        self.assertTrue(any(item.startswith("core_loop_failed:") for item in summary["blockers"]))
        state = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()
        self.assertFalse(state["live_delta_armed"])
        self.assertEqual(state["live_delta_last_action_type"], "disarm-live-delta")

    def test_supervisor_recovers_stale_heartbeat_before_core_loop(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="crashed-core-loop",
            mode="live",
            status="running",
            started_at_utc="2026-05-18T00:00:00Z",
            updated_at_utc="2026-05-18T00:00:00Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["recovered_heartbeat_count"], 1)
        self.assertEqual(len(core_calls), 1)

    def test_supervisor_ignores_concurrent_health_monitor_heartbeat(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="health-monitor-running",
            mode="mainnet_health_monitor",
            status="running",
            started_at_utc="2026-05-18T00:08:00Z",
            updated_at_utc="2026-05-18T00:09:30Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(len(core_calls), 1)
        local_state = json.loads((Path(summary["artifact_root"]) / "local_state_health.json").read_text(encoding="utf-8"))
        self.assertEqual(local_state["ignored_running_health_monitor_run_ids"], ["health-monitor-running"])
        self.assertEqual(local_state["status"], "ok")

    def test_supervisor_ignores_concurrent_daily_policy_orchestrator_heartbeat(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="daily-policy-running",
            mode="unattended_daily_policy",
            status="running",
            started_at_utc="2026-05-18T00:08:00Z",
            updated_at_utc="2026-05-18T00:09:30Z",
        )
        core_calls: list[Namespace] = []

        summary, exit_code = run_mainnet_live_supervisor(
            _args(config_path),
            env=_env(),
            core_loop_runner=_core_loop_runner(core_calls),
            now_fn=_fixed_now,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_live_supervisor_completed")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(len(core_calls), 1)
        local_state = json.loads((Path(summary["artifact_root"]) / "local_state_health.json").read_text(encoding="utf-8"))
        self.assertEqual(local_state["ignored_orchestrator_run_ids"], ["daily-policy-running"])
        self.assertEqual(local_state["status"], "ok")

    def _config_path(
        self,
        *,
        fast_follow_enabled: bool = False,
        capital_topup_enabled: bool = False,
        target_engine: str = "",
        allow_multiphase_live_delta: bool = False,
        reconcile_aware_fast_follow: bool = False,
        fast_follow_max_chain_invocations: int = 3,
    ) -> Path:
        path = self.temp_dir / "supervisor.yaml"
        path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  venue: usdm_futures",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "risk:",
                    "  trading_enabled: false",
                    "  max_daily_realized_loss_usdt: 10.0",
                    "  max_daily_realized_loss_enforcement: active",
                    "  daily_realized_pnl_income_types: REALIZED_PNL",
                    "  max_heartbeat_age_seconds: 300",
                    *(
                        [
                            "capital_topup:",
                            "  enabled: true",
                            "  min_additional_allocated_capital_usdt: 25.0",
                            "  allowed_delta_classifications: increase_same_side,new_entry,dust_residual,no_delta",
                            "  live_execution_enabled: true",
                        ]
                        if capital_topup_enabled
                        else []
                    ),
                    "core_loop:",
                    *([f"  target_engine: {target_engine}"] if target_engine else []),
                    "  target_as_of: latest_closed_rebalance_slot",
                    "  capital_topup_after_static_noop: true",
                    "  max_cycles_per_invocation: 1",
                    "  interval_seconds: 0",
                    "  live_delta_enabled: true",
                    "  submit_orders: true",
                    "  auto_confirm_delta_after_preflight: true",
                    "  allowed_execution_stages: reduce_first,entry_second",
                    f"  allow_multiphase_live_delta: {str(allow_multiphase_live_delta).lower()}",
                    "  max_live_delta_order_count_per_cycle: 6",
                    "  min_seconds_between_live_delta_executions: 300",
                    "  fast_follow_entry_second_min_delay_seconds: 60",
                    f"  unattended_budget_gate_enabled: {str(fast_follow_enabled).lower()}",
                    "mainnet_live_supervisor:",
                    *([f"  target_engine: {target_engine}"] if target_engine else []),
                    "  max_cycles_per_invocation: 1",
                    "  interval_seconds: 0",
                    "  allow_live_delta_when_armed: true",
                    f"  allow_multiphase_live_delta: {str(allow_multiphase_live_delta).lower()}",
                    "  recover_stale_heartbeats: true",
                    "  disarm_on_blocker: true",
                    f"  capital_topup_enabled: {str(capital_topup_enabled).lower()}",
                    f"  fast_follow_entry_second_enabled: {str(fast_follow_enabled).lower()}",
                    "  fast_follow_entry_second_delay_seconds: 90",
                    f"  fast_follow_max_chain_invocations: {int(fast_follow_max_chain_invocations)}",
                    *(
                        [
                            "  fast_follow_policy:",
                            "    mode: reconcile_aware",
                            "    entry_after_reduce_delay_seconds: 20",
                            "    residual_reduce_delay_seconds: 30",
                            "    min_delay_seconds: 10",
                            "    max_delay_seconds: 90",
                            "    max_chain_invocations_hard_cap: 4",
                            "    owner_authorization_required: true",
                            "    runtime_max_seconds: 420",
                        ]
                        if reconcile_aware_fast_follow
                        else []
                    ),
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return path


def _core_loop_runner(
    calls: list[Namespace],
    *,
    status: str = "mainnet_core_loop_completed",
    exit_code: int = 0,
    blockers: list[str] | None = None,
    orders_submitted: int = 0,
    fill_count: int = 0,
    execution_stage: str = "entry_second",
    core_cycle_status: str | None = None,
    post_trade_reconcile_status: str = "",
    deferred_phase_counts: dict[str, int] | None = None,
    target_position_count: int = 1,
    current_position_count: int = 1,
):
    def run(args: Namespace, **_kwargs):
        calls.append(args)
        cycle_status = core_cycle_status or ("cycle_executed_reconciled" if orders_submitted else "cycle_plan_only_ready")
        post_trade = (
            {"status": post_trade_reconcile_status, "exit_code": 0, "blockers": []}
            if post_trade_reconcile_status
            else {}
        )
        return (
            {
                "run_id": "core-loop-1",
                "status": status,
                "blockers": list(blockers or []),
                "artifact_root": "core-loop-artifact-root",
                "execution_requested": bool(args.execute_live_delta),
                "orders_submitted": int(orders_submitted),
                "fill_count": int(fill_count),
                "live_delta_authorized": bool(args.execute_live_delta and orders_submitted > 0 and exit_code == 0),
                "cycles": [
                    {
                        "status": cycle_status,
                        "blockers": list(blockers or []),
                        "live_delta_policy_gate": {
                            "execution_stage": execution_stage,
                            "status": "passed",
                            "deferred_phase_counts": dict(deferred_phase_counts or {}),
                            "target_position_count": int(target_position_count),
                            "current_position_count": int(current_position_count),
                        },
                        "post_trade_reconcile": post_trade,
                    }
                ],
            },
            int(exit_code),
        )

    return run


def _args(config_path: Path, *, fast_follow_entry_second: bool = False, fast_follow_chain_depth: int = 0) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel="",
        symbols="",
        public_market_data=False,
        reference_run="",
        cycles=None,
        interval_seconds=None,
        position_tolerance=1e-9,
        fast_follow_entry_second=fast_follow_entry_second,
        fast_follow_chain_depth=fast_follow_chain_depth,
    )


def _open_budget_epoch(path: Path, *, max_live_cycles: int) -> None:
    UnattendedBudgetStore(path).open_epoch(
        epoch_id="ff-epoch",
        max_live_cycles=max_live_cycles,
        max_gross_turnover_usdt=1000.0,
        max_age_seconds=900,
        now_utc=datetime(2026, 5, 18, 0, 9, 0, tzinfo=UTC),
        reason="unit test fast-follow budget epoch",
    )


def _arm_fast_follow(store: LiveTradingStateStore, *, epoch_id: str, max_chain_depth: int) -> None:
    store.record_operator_action(
        run_id="operator-arm",
        action_type="arm-live-delta",
        reason="unit test arm with fast-follow authorization",
        created_at_utc="2026-05-18T00:00:00Z",
        payload={
            "epoch_id": epoch_id,
            "fast_follow_authorized": True,
            "fast_follow_owner_decision": "approve_fast_follow_under_current_budget_epoch",
            "fast_follow_epoch_id": epoch_id,
            "fast_follow_max_chain_depth": int(max_chain_depth),
            "fast_follow_cleanup_required": True,
        },
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 18, 0, 10, 0, tzinfo=UTC)


def _command_runner(calls: list[list[str]]):
    def run(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(list(cmd))
        return 0, "scheduled\n", ""

    return run


if __name__ == "__main__":
    unittest.main()
