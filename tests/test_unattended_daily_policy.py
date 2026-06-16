from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
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

from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402
from enhengclaw.live_trading.unattended_daily_policy import (  # noqa: E402
    classify_unattended_daily_policy_service_state,
    run_unattended_daily_policy,
)
from enhengclaw.live_trading.unattended_epoch_controller import run_unattended_epoch_controller  # noqa: E402
from enhengclaw.quant_research.contracts import write_json  # noqa: E402


class UnattendedDailyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="unattended-daily-policy-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_proves_fresh_slot_without_arming_or_timer(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary()
        commands: list[list[str]] = []

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=False),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_runner(no_order_summary),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_daily_policy_dry_run_ready")
        self.assertEqual(summary["invocation_marker"]["invocation_id"], summary["run_id"])
        self.assertTrue((Path(summary["invocation_marker_path"])).exists())
        self.assertEqual(commands, [])
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())

    def test_apply_without_timer_opens_epoch_and_arms_for_timer_off_canary(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary()

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            epoch_controller_runner=_controller_runner(no_order_summary),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_daily_policy_armed_timer_off")
        self.assertTrue(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        epoch = UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch()
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.max_live_cycles, 1)

    def test_completed_slot_holds_without_arming_or_enabling_timer(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary(slot_status="completed")
        commands: list[list[str]] = []

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True, enable_supervisor_timer=True),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_runner(no_order_summary),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "hold_until_next_rebalance_slot")
        self.assertEqual(commands, [])
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())

    def test_daily_policy_passes_own_run_id_to_epoch_controller(self) -> None:
        config_path = self._config_path()
        captured: list[str] = []

        def controller_runner(controller_args: Namespace, **_kwargs):
            captured.append(str(controller_args.ignore_heartbeat_run_id))
            return {"status": "unattended_epoch_dry_run_ready", "blockers": []}, 0

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=False),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            epoch_controller_runner=controller_runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_daily_policy_dry_run_ready")
        self.assertEqual(captured, ["20260518T001000000000Z-unattended-daily-policy"])

    def test_single_timer_fire_success_disables_timer_disarms_and_closes_epoch(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary()
        commands: list[list[str]] = []
        notifications: list[tuple[str, dict]] = []
        health_observed_armed: list[bool] = []

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True, enable_supervisor_timer=True, run_health_monitor=True),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_runner(no_order_summary),
            supervisor_summary_reader=_supervisor_reader(_supervisor_summary(orders=1, fills=1)),
            health_monitor_runner=_health_runner(self.temp_dir, health_observed_armed),
            notification_sender=_notification_sender(notifications),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_daily_policy_timer_fire_completed")
        self.assertEqual(commands[0], ["systemctl", "enable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertEqual(commands[-1], ["systemctl", "disable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertEqual(summary["fill_count"], 1)
        self.assertEqual(summary["terminal_cleanup"]["status"], "terminal_cleanup_completed")
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())
        self.assertIn("unattended_approval_requires_open_budget_epoch", summary["runtime_gate_after"]["blockers"])
        self.assertEqual(len(notifications), 1)
        self.assertEqual(health_observed_armed, [False])

    def test_two_phase_fast_follow_waits_for_second_supervisor_before_cleanup(self) -> None:
        config_path = self._config_path(fast_follow=True)
        reduce_proof = self._write_no_order_summary(label="reduce-proof")
        entry_proof = self._write_no_order_summary(
            label="entry-proof",
            execution_stage="entry_second",
            planned_rows=[
                {"symbol": "BCHUSDT", "side": "SELL", "reduce_only": False, "rounded_notional_usdt": 12.0},
                {"symbol": "ETHUSDT", "side": "BUY", "reduce_only": False, "rounded_notional_usdt": 18.0},
            ],
        )
        commands: list[list[str]] = []
        notifications: list[tuple[str, dict]] = []

        first = _supervisor_summary(
            run_id="20260518T001100000000Z-mainnet-live-supervisor",
            orders=1,
            fills=1,
            execution_stage="reduce_first",
            fast_follow_status="skipped",
            deferred_phase_counts={"entry_second": 2},
        )
        second = _supervisor_summary(
            run_id="20260518T001300000000Z-mainnet-live-supervisor",
            orders=1,
            fills=1,
            execution_stage="entry_second",
            fast_follow_status="skipped",
        )
        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True, enable_supervisor_timer=True),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_sequence_runner([reduce_proof, entry_proof]),
            supervisor_summary_reader=_supervisor_sequence_reader([first, second]),
            notification_sender=_notification_sender(notifications),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_daily_policy_timer_fire_completed")
        self.assertEqual(len(summary["supervisor_summaries"]), 2)
        self.assertEqual([item["run_id"] for item in summary["supervisor_summaries"]], [first["run_id"], second["run_id"]])
        self.assertEqual(summary["orders_submitted"], 2)
        self.assertEqual(summary["fill_count"], 2)
        self.assertEqual(commands[0], ["systemctl", "enable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertEqual(commands[1][0], "systemd-run")
        self.assertIn("--fast-follow-entry-second", commands[1])
        self.assertEqual(commands[-1], ["systemctl", "disable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertEqual(summary["fast_follow_entry_second_authorizations"][0]["status"], "authorized")
        self.assertEqual(summary["fast_follow_entry_second_schedules"][0]["status"], "scheduled")
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())
        latest_arm = LiveTradingStateStore(self.temp_dir / "state.sqlite3").latest_operator_action(
            action_type="arm-live-delta", status="applied"
        )
        self.assertTrue(latest_arm["fast_follow_authorized"])
        self.assertEqual(latest_arm["fast_follow_expected_execution_stage"], "entry_second")
        self.assertEqual(latest_arm["fast_follow_expected_symbols"], ["BCHUSDT", "ETHUSDT"])
        self.assertEqual(latest_arm["fast_follow_expected_sides"], ["BUY", "SELL"])
        self.assertFalse(latest_arm["fast_follow_expected_reduce_only"])
        self.assertEqual(latest_arm["fast_follow_expected_max_order_count"], 2)
        self.assertEqual(latest_arm["max_timer_fires"], 2)

    def test_fast_follow_entry_second_schedule_uses_approval_window_not_legacy_180s_age(self) -> None:
        config_path = self._config_path(fast_follow=True)
        reduce_proof = self._write_no_order_summary(label="reduce-proof")
        entry_proof = self._write_no_order_summary(
            label="entry-proof",
            execution_stage="entry_second",
            planned_rows=[
                {"symbol": "BCHUSDT", "side": "SELL", "reduce_only": False, "rounded_notional_usdt": 12.0},
            ],
        )
        commands: list[list[str]] = []
        first = _supervisor_summary(
            run_id="20260518T001100000000Z-mainnet-live-supervisor",
            orders=1,
            fills=1,
            execution_stage="reduce_first",
            fast_follow_status="skipped",
            deferred_phase_counts={"entry_second": 1},
        )
        first["finished_at_utc"] = "2026-05-18T00:11:30Z"
        second = _supervisor_summary(
            run_id="20260518T001600000000Z-mainnet-live-supervisor",
            orders=1,
            fills=1,
            execution_stage="entry_second",
            fast_follow_status="skipped",
        )

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True, enable_supervisor_timer=True),
            env={},
            now_fn=_fixed_now_late,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_sequence_runner([reduce_proof, entry_proof]),
            supervisor_summary_reader=_supervisor_sequence_reader([first, second]),
        )

        self.assertEqual(exit_code, 0)
        schedule = summary["fast_follow_entry_second_schedules"][0]
        self.assertEqual(schedule["status"], "scheduled")
        self.assertGreater(schedule["age_seconds"], 180.0)
        self.assertEqual(schedule["configured_max_age_seconds"], 180.0)
        self.assertEqual(schedule["max_age_source"], "owner_approval_timer_window")
        self.assertEqual(schedule["delay_seconds"], 0)

    def test_daily_policy_service_failed_classifier_treats_old_failed_state_as_carryover(self) -> None:
        result = classify_unattended_daily_policy_service_state(
            {"ActiveState": "failed", "Result": "exit-code"},
            expected_timer_fire_after_utc="2026-05-18T00:20:00Z",
            latest_invocation_started_at_utc="2026-05-17T00:20:10Z",
            latest_summary_status="unattended_daily_policy_blocked",
            latest_summary_finished_at_utc="2026-05-17T00:21:00Z",
        )

        self.assertEqual(result["status"], "stale_failed_service_carryover")
        self.assertFalse(result["fresh_failure"])

    def test_daily_policy_service_failed_classifier_flags_new_failed_invocation(self) -> None:
        result = classify_unattended_daily_policy_service_state(
            {"ActiveState": "failed", "Result": "exit-code"},
            expected_timer_fire_after_utc="2026-05-18T00:20:00Z",
            latest_invocation_started_at_utc="2026-05-18T00:20:10Z",
            latest_summary_status="unattended_daily_policy_blocked",
            latest_summary_finished_at_utc="2026-05-18T00:21:00Z",
        )

        self.assertEqual(result["status"], "fresh_failed_service_invocation")
        self.assertTrue(result["fresh_failure"])

    def test_fast_follow_entry_second_proof_mismatch_fails_closed_before_schedule(self) -> None:
        config_path = self._config_path(fast_follow=True)
        reduce_proof = self._write_no_order_summary(label="reduce-proof")
        entry_proof = self._write_no_order_summary(
            label="entry-proof",
            execution_stage="entry_second",
            slot_id="different-slot",
            target_hash="different-hash",
            planned_rows=[
                {"symbol": "BCHUSDT", "side": "SELL", "reduce_only": False, "rounded_notional_usdt": 12.0},
            ],
        )
        commands: list[list[str]] = []

        first = _supervisor_summary(
            run_id="20260518T001100000000Z-mainnet-live-supervisor",
            orders=1,
            fills=1,
            execution_stage="reduce_first",
            fast_follow_status="skipped",
            deferred_phase_counts={"entry_second": 1},
        )
        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True, enable_supervisor_timer=True),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_sequence_runner([reduce_proof, entry_proof]),
            supervisor_summary_reader=_supervisor_sequence_reader([first]),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "unattended_daily_policy_blocked")
        self.assertIn("fast_follow_entry_second_slot_mismatch:different-slot!=slot-20260518", summary["blockers"])
        self.assertEqual(commands[0], ["systemctl", "enable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertEqual(commands[-1], ["systemctl", "disable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertFalse(any(cmd and cmd[0] == "systemd-run" for cmd in commands))
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())

    def test_timer_artifact_timeout_runs_terminal_cleanup(self) -> None:
        config_path = self._config_path(wait_seconds=0)
        no_order_summary = self._write_no_order_summary()
        commands: list[list[str]] = []

        summary, exit_code = run_unattended_daily_policy(
            _args(config_path, apply=True, enable_supervisor_timer=True),
            env={},
            now_fn=_fixed_now,
            command_runner=_command_runner(commands),
            epoch_controller_runner=_controller_runner(no_order_summary),
            supervisor_summary_reader=_supervisor_reader(None),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "unattended_daily_policy_blocked")
        self.assertIn("unattended_daily_policy_supervisor_artifact_timeout", summary["blockers"])
        self.assertEqual(commands[0], ["systemctl", "enable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertEqual(commands[-1], ["systemctl", "disable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"])
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())

    def _config_path(self, *, wait_seconds: int = 30, fast_follow: bool = False) -> Path:
        path = self.temp_dir / "daily_policy.yaml"
        path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  venue: usdm_futures",
                    "risk:",
                    "  trading_enabled: false",
                    "core_loop:",
                    "  unattended_budget_gate_enabled: true",
                    "unattended_epoch_controller:",
                    f"  max_gross_turnover_usdt: {80.0 if fast_follow else 20.0}",
                    f"  max_live_cycles: {2 if fast_follow else 1}",
                    "  max_age_seconds: 900",
                    "  approval_ttl_seconds: 900",
                    "  timer_window_seconds: 900",
                    f"  max_timer_fires: {2 if fast_follow else 1}",
                    f"  fast_follow_entry_second_authorized: {str(bool(fast_follow)).lower()}",
                    "  fast_follow_max_chain_depth: 1",
                    "  systemd_timer_name: meridian-alpha-mainnet-supervisor-live.timer",
                    "unattended_daily_policy:",
                    "  mode: daily_closed_slot_single_fire",
                    "  enable_supervisor_timer: false",
                    "  terminal_cleanup_after_success: true",
                    "  terminal_cleanup_on_failure: true",
                    f"  wait_for_supervisor_artifact_seconds: {wait_seconds}",
                    "  poll_interval_seconds: 0.1",
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _write_no_order_summary(
        self,
        *,
        label: str = "proof",
        slot_status: str = "open",
        slot_id: str = "slot-20260518",
        target_hash: str = "hash-20260518",
        execution_stage: str = "reduce_first",
        planned_rows: list[dict] | None = None,
    ) -> dict:
        plan_root = self.temp_dir / label / "plan"
        delta_root = self.temp_dir / label / "delta"
        plan_root.mkdir(parents=True, exist_ok=True)
        delta_root.mkdir(parents=True, exist_ok=True)
        rows = planned_rows or [
            {
                "symbol": "AAVEUSDT",
                "side": "BUY",
                "reduce_only": True,
                "rounded_notional_usdt": 6.0,
            }
        ]
        snapshot = {
            "schema_version": "daily_rebalance_slot_target.v1",
            "slot_id": slot_id,
            "target_hash": target_hash,
            "status": slot_status,
            "target_engine": "multiphase_current_position_target",
            "strategy_label": "hv_balanced",
            "resolved_capital_usdt": 1000.0,
            "positions": [
                {
                    "symbol": "AAVEUSDT",
                    "target_weight": 0.1,
                    "target_notional_usdt": 100.0,
                    "resolved_capital_usdt": 1000.0,
                    "reference_price": 100.0,
                    "target_position_amt": 1.0,
                }
            ],
        }
        write_json(plan_root / "frozen_target_snapshot.json", snapshot)
        write_json(
            plan_root / "frozen_slot_gate.json",
            {
                "status": "freeze_new_slot_target",
                "slot_id": slot_id,
                "active_target_hash": target_hash,
                "blockers": [],
                "warnings": [],
            },
        )
        write_json(
            delta_root / "planned_delta_orders.json",
            {
                "row_count": len(rows),
                "rows": rows,
            },
        )
        LiveTradingStateStore(self.temp_dir / "state.sqlite3").write_rebalance_slot_target(snapshot)
        return {
            "run_id": f"{label}-run",
            "status": "mainnet_core_loop_completed",
            "mode": "core_loop",
            "artifact_root": str(self.temp_dir / label / "core"),
            "execution_requested": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "cycles": [
                {
                    "status": "cycle_plan_only_ready",
                    "plan_artifact_root": str(plan_root),
                    "delta_preflight_artifact_root": str(delta_root),
                    "frozen_target_snapshot": {
                        "slot_id": slot_id,
                        "target_hash": target_hash,
                        "status": slot_status,
                    },
                    "frozen_slot_gate": {
                        "status": "freeze_new_slot_target",
                        "slot_id": slot_id,
                        "active_target_hash": target_hash,
                    },
                    "delta_preflight": {"execution_stage": execution_stage, "planned_delta_order_count": len(rows)},
                    "live_delta_policy_gate": {"execution_stage": execution_stage, "planned_delta_order_count": len(rows)},
                }
            ],
        }


def _args(
    config_path: Path,
    *,
    apply: bool,
    enable_supervisor_timer: bool = False,
    run_health_monitor: bool = False,
) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel="",
        symbols="",
        public_market_data=False,
        reference_run="",
        target_engine="",
        position_tolerance=1e-9,
        apply=apply,
        enable_supervisor_timer=enable_supervisor_timer,
        run_health_monitor=run_health_monitor,
        max_gross_turnover_usdt=None,
        max_live_cycles=None,
        max_age_seconds=None,
        approval_ttl_seconds=None,
        timer_window_seconds=None,
        max_timer_fires=None,
        systemd_timer_name="",
        wait_for_supervisor_artifact_seconds=None,
        poll_interval_seconds=None,
        no_terminal_cleanup_after_success=False,
        no_terminal_cleanup_on_failure=False,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 5, 18, 0, 10, 0, tzinfo=UTC)


def _fixed_now_late() -> datetime:
    return datetime(2026, 5, 18, 0, 15, 0, tzinfo=UTC)


def _controller_runner(no_order_summary: dict):
    def run(controller_args: Namespace, **kwargs):
        return run_unattended_epoch_controller(
            controller_args,
            no_order_runner=lambda _args, **_kwargs: (no_order_summary, 0),
            **kwargs,
        )

    return run


def _controller_sequence_runner(no_order_summaries: list[dict]):
    rows = list(no_order_summaries)

    def run(controller_args: Namespace, **kwargs):
        if not rows:
            raise AssertionError("unexpected unattended epoch controller invocation")
        return run_unattended_epoch_controller(
            controller_args,
            no_order_runner=lambda _args, **_kwargs: (rows.pop(0), 0),
            **kwargs,
        )

    return run


def _command_runner(calls: list[list[str]]):
    def run(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(list(cmd))
        return 0, "ok\n", ""

    return run


def _supervisor_summary(
    *,
    orders: int,
    fills: int,
    run_id: str = "20260518T001100000000Z-mainnet-live-supervisor",
    execution_stage: str = "reduce_first",
    fast_follow_status: str = "skipped",
    deferred_phase_counts: dict | None = None,
) -> dict:
    deferred = deferred_phase_counts or {}
    return {
        "run_id": run_id,
        "status": "mainnet_live_supervisor_completed",
        "blockers": [],
        "started_at_utc": "2026-05-18T00:11:00Z",
        "finished_at_utc": "2026-05-18T00:11:30Z",
        "artifact_root": "artifact/supervisor",
        "orders_submitted": int(orders),
        "fill_count": int(fills),
        "live_delta_authorized": bool(orders),
        "fast_follow_entry_second_schedule": {"status": fast_follow_status},
        "cycles": [
            {
                "core_loop_summary": {
                    "run_id": run_id.replace("mainnet-live-supervisor", "mainnet-core-loop"),
                    "status": "mainnet_core_loop_completed",
                    "orders_submitted": int(orders),
                    "fill_count": int(fills),
                    "cycles": [
                        {
                            "status": "cycle_executed_reconciled",
                            "post_trade_reconcile": {"status": "passed_live_position_monitor"},
                            "live_delta_policy_gate": {
                                "execution_stage": execution_stage,
                                "planned_delta_order_count": int(orders),
                                "phase_counts": {"reduce_first": int(orders)} if execution_stage == "reduce_first" else {"entry_second": int(orders)},
                                "deferred_phase_counts": deferred,
                            },
                            "strategy_target": {
                                "deferred_phase_counts": deferred,
                            },
                        }
                    ],
                },
            }
        ],
    }


def _supervisor_reader(summary: dict | None):
    def read(_root: Path, _existing_run_ids: set[str], _started_after: datetime) -> dict | None:
        return summary

    return read


def _supervisor_sequence_reader(summaries: list[dict]):
    rows = list(summaries)

    def read(_root: Path, _existing_run_ids: set[str], _started_after: datetime) -> dict | None:
        if not rows:
            return None
        return rows.pop(0)

    return read


def _health_runner(temp_dir: Path, observed_armed: list[bool]):
    def run(_args: Namespace, **_kwargs):
        observed_armed.append(
            bool(LiveTradingStateStore(temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        )
        return {"status": "mainnet_health_monitor_passed", "alerts": []}, 0

    return run


def _notification_sender(calls: list[tuple[str, dict]]):
    def send(text: str, payload: dict) -> dict:
        calls.append((text, payload))
        return {"status": "sent"}

    return send


if __name__ == "__main__":
    unittest.main()
