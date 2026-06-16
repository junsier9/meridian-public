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

from enhengclaw.live_trading.mainnet_health_monitor import run_mainnet_health_monitor  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore  # noqa: E402
from enhengclaw.live_trading.unattended_epoch_controller import (  # noqa: E402
    UNATTENDED_EPOCH_APPROVAL_CONTRACT,
)
from enhengclaw.quant_research.contracts import write_json  # noqa: E402


class HvBalancedMainnetHealthMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-health-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_clean_recent_noorder_timer_runs_pass_without_telegram(self) -> None:
        config_path = self._config_path()
        self._write_clean_runs()
        sent: list[tuple[str, str, str]] = []

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender(sent),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_health_monitor_passed")
        self.assertEqual(summary["alerts"], [])
        self.assertEqual(summary["recent_run_count_observed"], 3)
        self.assertEqual(summary["telegram"]["status"], "skipped_no_alerts")
        self.assertEqual(sent, [])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def test_handoff_observation_can_scope_to_latest_clean_supervisor_run(self) -> None:
        config_path = self._config_path(recent_run_count=1)
        for minute, blocker in ((10, "operator_paused"), (20, "old_position_reference_blocked")):
            run_id = f"20260518T00{minute:02d}00000000Z-mainnet-live-supervisor"
            root = self.temp_dir / "mainnet_live_supervisor" / run_id
            root.mkdir(parents=True, exist_ok=True)
            payload = _supervisor_summary(run_id, minute=minute)
            payload["status"] = "mainnet_live_supervisor_blocked"
            payload["blockers"] = [blocker]
            write_json(root / "run_summary.json", payload)
        clean_run_id = "20260518T002500000000Z-mainnet-live-supervisor"
        clean_root = self.temp_dir / "mainnet_live_supervisor" / clean_run_id
        clean_root.mkdir(parents=True, exist_ok=True)
        write_json(clean_root / "run_summary.json", _supervisor_summary(clean_run_id, minute=25))

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_health_monitor_passed")
        self.assertEqual(summary["alerts"], [])
        self.assertEqual(summary["recent_run_count_required"], 1)
        self.assertEqual(summary["recent_run_count_observed"], 1)
        self.assertEqual([run["run_id"] for run in summary["supervisor_runs"]], [clean_run_id])

    def test_budget_disarm_relays_blockers_so_auto_rearm_is_blocked(self) -> None:
        # B2: a budget-exhaustion disarm relayed by the health monitor must carry the underlying
        # supervisor blockers so the TERMINAL unattended_budget auto-rearm guard fires. Previously
        # the relay recorded only alert_codes, so _auto_rearm_disarm_is_recoverable (which matches
        # the unattended_budget fragment against `blockers`) saw nothing and auto-rearm could resume
        # against an exhausted epoch.
        from enhengclaw.live_trading.mainnet_health_monitor import _auto_rearm_disarm_is_recoverable

        config_path = self._config_path(recent_run_count=1)
        run_id = "20260518T002000000000Z-mainnet-live-supervisor"
        root = self.temp_dir / "mainnet_live_supervisor" / run_id
        root.mkdir(parents=True, exist_ok=True)
        payload = _supervisor_summary(run_id, minute=20)
        payload["status"] = "mainnet_live_supervisor_blocked"
        payload["blockers"] = ["unattended_budget_cycle_exhausted:6>=6"]
        write_json(root / "run_summary.json", payload)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm", action_type="arm-live-delta", reason="t",
            created_at_utc="2026-05-18T00:00:00Z",
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path), env={}, now_fn=_fixed_now,
            command_runner=_systemd_active, telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("supervisor_run_blockers", {item["code"] for item in summary["alerts"]})
        last_disarm = store.latest_operator_action(action_type="disarm-live-delta", status="applied")
        self.assertIn("unattended_budget_cycle_exhausted:6>=6", list(last_disarm.get("blockers") or []))
        recoverable = _auto_rearm_disarm_is_recoverable(last_disarm, health_cfg={})
        self.assertEqual(recoverable["status"], "blocked_hard_disarm_reason")
        self.assertTrue(any("unattended_budget" in f for f in recoverable["blocked_blocker_fragments"]))

    def test_nonzero_order_alert_sends_telegram_and_disarms(self) -> None:
        config_path = self._config_path()
        self._write_clean_runs(order_on_latest=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        sent: list[tuple[str, str, str]] = []

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender(sent),
        )

        self.assertEqual(exit_code, 2)
        codes = {item["code"] for item in summary["alerts"]}
        self.assertIn("supervisor_order_or_fill_nonzero", codes)
        self.assertEqual(summary["telegram"]["status"], "sent")
        self.assertEqual(len(sent), 1)
        self.assertIn("supervisor_order_or_fill_nonzero", sent[0][2])
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNotNone(summary["disarm_record"])

    def test_live_capable_mode_allows_authorized_order_and_keeps_armed(self) -> None:
        config_path = self._config_path(no_order_expected=False, timer_name="enhengclaw-mainnet-supervisor-live.timer")
        self._write_clean_runs(order_on_latest=True, live_authorized=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        sent: list[tuple[str, str, str]] = []

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender(sent),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_health_monitor_passed")
        self.assertFalse(summary["no_order_expected"])
        self.assertEqual(summary["alerts"], [])
        self.assertTrue(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertEqual(sent, [])

    def test_auto_rearm_after_recoverable_disarm_and_clean_live_timer_runs(self) -> None:
        config_path = self._config_path(
            no_order_expected=False,
            timer_name="enhengclaw-mainnet-supervisor-live.timer",
            auto_rearm=True,
        )
        self._write_clean_runs()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _write_valid_unattended_approval(self.temp_dir)
        store.record_operator_action(
            run_id="health-alert",
            action_type="disarm-live-delta",
            reason="mainnet health monitor alert",
            created_at_utc="2026-05-18T00:00:00Z",
            payload={
                "source": "mainnet_health_monitor",
                "alert_codes": [
                    "supervisor_run_not_completed",
                    "account_reconcile_not_passed",
                    "core_loop_not_completed",
                    "margin_cushion_gate_not_passed",
                ],
            },
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_health_monitor_passed")
        self.assertEqual(summary["auto_rearm_gate"]["status"], "auto_rearmed")
        self.assertIsNotNone(summary["auto_rearm_record"])
        state = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()
        self.assertTrue(state["live_delta_armed"])
        self.assertEqual(state["live_delta_last_action_type"], "arm-live-delta")

    def test_auto_rearm_blocks_without_valid_unattended_approval(self) -> None:
        config_path = self._config_path(
            no_order_expected=False,
            timer_name="enhengclaw-mainnet-supervisor-live.timer",
            auto_rearm=True,
        )
        self._write_clean_runs()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="health-alert",
            action_type="disarm-live-delta",
            reason="mainnet health monitor alert",
            created_at_utc="2026-05-18T00:00:00Z",
            payload={
                "source": "mainnet_health_monitor",
                "alert_codes": ["account_reconcile_not_passed"],
            },
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["auto_rearm_gate"]["status"], "blocked_unattended_epoch_runtime_gate")
        nested = summary["auto_rearm_gate"]["unattended_epoch_runtime_gate"]
        self.assertIn("unattended_approval_missing_arm_action", nested["blockers"])
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_auto_rearm_can_recover_legacy_daily_pnl_disarm(self) -> None:
        config_path = self._config_path(
            no_order_expected=False,
            timer_name="enhengclaw-mainnet-supervisor-live.timer",
            auto_rearm=True,
        )
        self._write_clean_runs()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _write_valid_unattended_approval(self.temp_dir)
        store.record_operator_action(
            run_id="health-alert",
            action_type="disarm-live-delta",
            reason="mainnet health monitor alert",
            created_at_utc="2026-05-18T00:00:00Z",
            payload={"source": "mainnet_health_monitor", "alert_codes": ["daily_pnl_gate_not_passed"]},
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["auto_rearm_gate"]["status"], "auto_rearmed")
        self.assertTrue(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_auto_rearm_daily_pnl_allow_flag_is_legacy_noop(self) -> None:
        config_path = self._config_path(
            no_order_expected=False,
            timer_name="enhengclaw-mainnet-supervisor-live.timer",
            auto_rearm=True,
            allow_daily_pnl_auto_rearm=True,
        )
        self._write_clean_runs()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        _write_valid_unattended_approval(self.temp_dir)
        store.record_operator_action(
            run_id="health-alert",
            action_type="disarm-live-delta",
            reason="mainnet health monitor alert",
            created_at_utc="2026-05-18T00:00:00Z",
            payload={"source": "mainnet_health_monitor", "alert_codes": ["daily_pnl_gate_not_passed"]},
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["auto_rearm_gate"]["status"], "auto_rearmed")
        self.assertTrue(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_auto_rearm_requires_clean_runs_after_disarm(self) -> None:
        config_path = self._config_path(
            no_order_expected=False,
            timer_name="enhengclaw-mainnet-supervisor-live.timer",
            auto_rearm=True,
        )
        self._write_clean_runs()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="health-alert",
            action_type="disarm-live-delta",
            reason="mainnet health monitor alert",
            created_at_utc="2026-05-18T00:24:30Z",
            payload={"source": "mainnet_health_monitor", "alert_codes": ["account_reconcile_not_passed"]},
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["auto_rearm_gate"]["status"], "blocked_insufficient_post_disarm_supervisor_runs")
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_live_capable_mode_alerts_order_without_authorization(self) -> None:
        config_path = self._config_path(no_order_expected=False, timer_name="enhengclaw-mainnet-supervisor-live.timer")
        self._write_clean_runs(order_on_latest=True, live_authorized=False)

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 2)
        codes = {item["code"] for item in summary["alerts"]}
        self.assertIn("live_order_or_fill_without_authorization", codes)

    def test_missing_or_stale_timer_artifact_alerts(self) -> None:
        config_path = self._config_path()

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_inactive,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 2)
        codes = {item["code"] for item in summary["alerts"]}
        self.assertIn("missing_supervisor_artifacts", codes)
        self.assertIn("systemd_timer_not_active", codes)
        self.assertFalse(summary["live_delta_armed_after"])

    def test_scoped_timer_checks_skip_disabled_timer_without_active_unattended_epoch(self) -> None:
        config_path = self._config_path(scope_timer_checks_to_active_unattended_epoch=True)

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_inactive,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_health_monitor_passed")
        self.assertEqual(summary["alerts"], [])
        self.assertFalse(summary["supervisor_timer_checks_required"])
        self.assertEqual(summary["systemd_timer_status"]["status"], "skipped_inactive_unattended_epoch")
        self.assertEqual(summary["supervisor_artifact_checks"]["status"], "skipped_inactive_unattended_epoch")

    def test_scoped_timer_checks_alert_when_active_unattended_epoch_timer_inactive(self) -> None:
        config_path = self._config_path(
            no_order_expected=False,
            timer_name="enhengclaw-mainnet-supervisor-live.timer",
            scope_timer_checks_to_active_unattended_epoch=True,
        )
        _write_valid_unattended_approval(self.temp_dir)
        self._write_clean_runs()

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_inactive,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 2)
        self.assertTrue(summary["supervisor_timer_checks_required"])
        self.assertEqual(summary["active_unattended_epoch_gate"]["status"], "passed")
        codes = {item["code"] for item in summary["alerts"]}
        self.assertIn("systemd_timer_not_active", codes)

    def test_scoped_timer_checks_disarm_live_delta_without_active_unattended_epoch(self) -> None:
        config_path = self._config_path(scope_timer_checks_to_active_unattended_epoch=True)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test invalid arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_inactive,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(summary["supervisor_timer_checks_required"])
        codes = {item["code"] for item in summary["alerts"]}
        self.assertIn("live_delta_armed_without_active_unattended_epoch", codes)
        self.assertNotIn("systemd_timer_not_active", codes)
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])

    def test_stale_running_heartbeat_alerts(self) -> None:
        config_path = self._config_path()
        self._write_clean_runs()
        LiveTradingStateStore(self.temp_dir / "state.sqlite3").write_heartbeat(
            run_id="stale-supervisor",
            mode="live_supervisor",
            status="running",
            started_at_utc="2026-05-18T00:00:00Z",
            updated_at_utc="2026-05-18T00:00:00Z",
        )

        summary, exit_code = run_mainnet_health_monitor(
            _args(config_path),
            env={},
            now_fn=_fixed_now,
            command_runner=_systemd_active,
            telegram_sender=_sender([]),
        )

        self.assertEqual(exit_code, 2)
        codes = {item["code"] for item in summary["alerts"]}
        self.assertIn("heartbeat_residue", codes)

    def _config_path(
        self,
        *,
        no_order_expected: bool = True,
        timer_name: str = "enhengclaw-mainnet-supervisor-noorder.timer",
        auto_rearm: bool = False,
        allow_daily_pnl_auto_rearm: bool = False,
        recent_run_count: int = 3,
        scope_timer_checks_to_active_unattended_epoch: bool = False,
    ) -> Path:
        path = self.temp_dir / "health.yaml"
        path.write_text(
            "\n".join(
                [
                    "binance:",
                    "  venue: usdm_futures",
                    "risk:",
                    "  trading_enabled: false",
                    "  max_heartbeat_age_seconds: 900",
                    "mainnet_health_monitor:",
                    f"  recent_run_count: {recent_run_count}",
                    "  max_seconds_since_latest_supervisor_run: 1200",
                    "  max_running_heartbeat_age_seconds: 900",
                    "  require_systemd_timer_active: true",
                    f"  scope_timer_checks_to_active_unattended_epoch: {str(bool(scope_timer_checks_to_active_unattended_epoch)).lower()}",
                    f"  systemd_timer_name: {timer_name}",
                    f"  no_order_expected: {str(bool(no_order_expected)).lower()}",
                    "  disarm_on_alert: true",
                    f"  auto_rearm_live_delta: {str(bool(auto_rearm)).lower()}",
                    "  auto_rearm_requires_live_capable_timer: true",
                    "  auto_rearm_required_clean_supervisor_runs: 3",
                    "  auto_rearm_min_seconds_since_disarm: 300",
                    *(
                        [
                            "  auto_rearm_blocked_alert_codes: heartbeat_residue,live_delta_armed_during_noorder_timer,live_delta_execution_requested,live_order_fill_count_mismatch,live_order_or_fill_without_authorization,open_orders_present,orphan_paper_fills_present,orphan_paper_orders_present,supervisor_order_or_fill_nonzero",
                            "  auto_rearm_blocked_blocker_fragments: heartbeat_residue,open_orders,order_or_fill,position_drift,pnl_breach,unauthorized,unknown_status",
                        ]
                        if allow_daily_pnl_auto_rearm
                        else []
                    ),
                    "  exit_code_on_alert: 2",
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _write_clean_runs(self, *, order_on_latest: bool = False, live_authorized: bool = False) -> None:
        for index, minute in enumerate((10, 20, 25), start=1):
            run_id = f"20260518T00{minute:02d}00000000Z-mainnet-live-supervisor"
            root = self.temp_dir / "mainnet_live_supervisor" / run_id
            root.mkdir(parents=True, exist_ok=True)
            orders = 1 if order_on_latest and minute == 25 else 0
            write_json(
                root / "run_summary.json",
                _supervisor_summary(run_id, minute=minute, orders=orders, live_authorized=bool(live_authorized and orders)),
            )


def _supervisor_summary(run_id: str, *, minute: int, orders: int = 0, live_authorized: bool = False) -> dict:
    started = f"2026-05-18T00:{minute:02d}:00Z"
    finished = f"2026-05-18T00:{minute:02d}:15Z"
    return {
        "run_id": run_id,
        "status": "mainnet_live_supervisor_completed",
        "blockers": [],
        "started_at_utc": started,
        "finished_at_utc": finished,
        "artifact_root": f"artifact/{run_id}",
        "live_delta_armed_at_start": bool(live_authorized),
        "live_delta_armed_at_finish": bool(live_authorized),
        "live_delta_authorized": bool(live_authorized),
        "orders_submitted": orders,
        "fill_count": orders,
        "cycles": [
            {
                "status": "cycle_live_delta_completed" if live_authorized else "cycle_observed_no_order",
                "execute_live_delta_requested": bool(live_authorized),
                "live_delta_authorized": bool(live_authorized),
                "core_loop_status": "mainnet_core_loop_completed",
                "core_loop_execution_requested": bool(live_authorized),
                "core_loop_summary": {
                    "status": "mainnet_core_loop_completed",
                    "execution_requested": bool(live_authorized),
                    "orders_submitted": orders,
                    "fill_count": orders,
                    "cycles": [
                        {
                            "account_reconcile": {"status": "passed_live_position_monitor"},
                            "open_order_count": 0,
                            "daily_realized_pnl_gate": {"status": "passed", "daily_realized_pnl_usdt": 0.0},
                            "margin_cushion_gate": {"status": "passed", "available_balance_usdt": 200.0},
                            "delta_preflight": {"status": "mainnet_delta_execution_ready"},
                            "live_delta_policy_gate": {
                                "execution_stage": "reduce_first",
                                "planned_delta_order_count": 4,
                                "planned_execution_phases": ["reduce_first"],
                            },
                            "planned_delta_order_count": 4,
                        }
                    ],
                },
            }
        ],
    }


def _args(config_path: Path) -> Namespace:
    return Namespace(
        config=str(config_path),
        recent_runs=None,
        max_seconds_since_latest_run=None,
        systemd_timer_name="",
        skip_systemd_check=False,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 5, 18, 0, 30, 0, tzinfo=UTC)


def _write_valid_unattended_approval(temp_dir: Path) -> None:
    db = temp_dir / "state.sqlite3"
    epoch_id = "health-auto-rearm-epoch"
    budget_store = UnattendedBudgetStore(db)
    budget_store.open_epoch(
        epoch_id=epoch_id,
        max_live_cycles=1,
        max_gross_turnover_usdt=50.0,
        max_age_seconds=3600,
        now_utc=datetime(2026, 5, 18, 0, 0, 0, tzinfo=UTC),
        reason="unit test health auto rearm approval",
    )
    store = LiveTradingStateStore(db)
    store.write_rebalance_slot_target(
        {
            "schema_version": "daily_rebalance_slot_target.v1",
            "slot_id": "health-auto-rearm-slot",
            "target_hash": "health-auto-rearm-hash",
            "status": "open",
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
    )
    store.record_operator_action(
        run_id="operator-approval",
        action_type="arm-live-delta",
        reason="unit test valid unattended approval",
        created_at_utc="2026-05-18T00:00:00Z",
        payload={
            "contract_version": UNATTENDED_EPOCH_APPROVAL_CONTRACT,
            "epoch_id": epoch_id,
            "expected_epoch_id": epoch_id,
            "budget_epoch_id": epoch_id,
            "slot_id": "health-auto-rearm-slot",
            "target_hash": "health-auto-rearm-hash",
            "approval_created_at_utc": "2026-05-18T00:00:00Z",
            "approval_expires_at_utc": "2026-05-18T00:45:00Z",
            "timer_window": {
                "timer_name": "enhengclaw-mainnet-supervisor-live.timer",
                "timer_enable_earliest_utc": "2026-05-18T00:00:00Z",
                "timer_enable_latest_utc": "2026-05-18T00:45:00Z",
                "max_timer_fires_authorized": 1,
            },
            "max_timer_fires": 1,
            "expected_execution_stage": "reduce_first",
            "expected_symbols": ["AAVEUSDT"],
            "expected_sides": ["BUY"],
            "expected_reduce_only": True,
            "expected_max_order_count": 1,
            "expected_max_turnover_usdt": 50.0,
        },
    )


def _systemd_active(cmd: list[str]) -> tuple[int, str, str]:
    joined = " ".join(cmd)
    if "is-active" in joined:
        return 0, "active\n", ""
    if "is-enabled" in joined:
        return 0, "enabled\n", ""
    return 0, "NEXT LEFT LAST PASSED UNIT ACTIVATES\n", ""


def _systemd_inactive(cmd: list[str]) -> tuple[int, str, str]:
    joined = " ".join(cmd)
    if "is-active" in joined:
        return 3, "inactive\n", ""
    if "is-enabled" in joined:
        return 1, "disabled\n", ""
    return 0, "", ""


def _sender(calls: list[tuple[str, str, str]]):
    def send(token: str, chat_id: str, text: str) -> dict:
        calls.append((token, chat_id, text))
        return {"ok": True}

    return send


if __name__ == "__main__":
    unittest.main()
