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
from enhengclaw.live_trading.unattended_epoch_controller import (  # noqa: E402
    UNATTENDED_EPOCH_APPROVAL_CONTRACT,
    build_fast_follow_entry_second_owner_payload,
    evaluate_unattended_epoch_runtime_gate,
    run_unattended_epoch_controller,
    terminal_cleanup,
)
from enhengclaw.quant_research.contracts import write_json  # noqa: E402


class UnattendedEpochControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="unattended-epoch-controller-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_apply_fresh_no_order_proof_opens_epoch_and_arms_owner_approval(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary(slot_status="open")

        summary, exit_code = run_unattended_epoch_controller(
            _args(config_path, apply=True),
            env={},
            no_order_runner=_runner(no_order_summary, 0),
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            notification_sender=_notification_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_epoch_armed")
        self.assertEqual(summary["fresh_no_order_proof"]["status"], "passed")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        state = store.read_operator_state()
        self.assertTrue(state["live_delta_armed"])
        latest_arm = store.latest_operator_action(action_type="arm-live-delta", status="applied")
        self.assertEqual(latest_arm["contract_version"], UNATTENDED_EPOCH_APPROVAL_CONTRACT)
        self.assertEqual(latest_arm["slot_id"], "slot-20260518")
        self.assertEqual(latest_arm["target_hash"], "hash-20260518")
        self.assertEqual(latest_arm["approval_expires_at_utc"], "2026-05-18T00:25:00Z")
        self.assertEqual(latest_arm["timer_window"]["max_timer_fires_authorized"], 1)
        epoch = UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch()
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.epoch_id, latest_arm["epoch_id"])
        gate = evaluate_unattended_epoch_runtime_gate(
            state_store=store,
            payload={"state": {"sqlite_path": (self.temp_dir / "state.sqlite3").as_posix()}},
            now=_fixed_now(),
            approval_action=latest_arm,
        )
        self.assertEqual(gate["status"], "passed")

    def test_completed_slot_holds_without_opening_epoch_or_arming(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary(slot_status="completed", gate_status="hold_until_next_rebalance_slot")

        summary, exit_code = run_unattended_epoch_controller(
            _args(config_path, apply=True),
            env={},
            no_order_runner=_runner(no_order_summary, 0),
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            notification_sender=_notification_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "hold_until_next_rebalance_slot")
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["live_delta_armed"])
        self.assertIsNone(UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch())

    def test_no_order_runner_ignores_controller_and_parent_heartbeat_ids(self) -> None:
        config_path = self._config_path()
        no_order_summary = self._write_no_order_summary(slot_status="open")
        captured: list[str] = []

        def no_order_runner(no_order_args: Namespace, **_kwargs):
            captured.append(str(no_order_args.ignore_heartbeat_run_id))
            return no_order_summary, 0

        summary, exit_code = run_unattended_epoch_controller(
            _args(config_path, apply=False, ignore_heartbeat_run_id="parent-daily-policy"),
            env={},
            no_order_runner=no_order_runner,
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            notification_sender=_notification_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_epoch_dry_run_ready")
        self.assertEqual(
            captured,
            ["20260518T001000000000Z-unattended-epoch-controller,parent-daily-policy"],
        )

    def test_local_state_health_expands_comma_separated_ignore_ids(self) -> None:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        store.write_heartbeat(
            run_id="parent-daily-policy",
            mode="unattended_daily_policy",
            status="running",
            started_at_utc="2026-05-18T00:10:00Z",
            updated_at_utc="2026-05-18T00:10:00Z",
            artifact_root=str(self.temp_dir / "parent"),
        )
        store.write_heartbeat(
            run_id="unrelated",
            mode="live",
            status="running",
            started_at_utc="2026-05-18T00:10:00Z",
            updated_at_utc="2026-05-18T00:10:00Z",
            artifact_root=str(self.temp_dir / "other"),
        )

        health = store.evaluate_local_state_health(
            now="2026-05-18T00:10:30Z",
            ignore_run_ids=["controller,parent-daily-policy"],
        )

        self.assertNotIn("active_run_in_progress:parent-daily-policy", health["blockers"])
        self.assertIn("active_run_in_progress:unrelated", health["blockers"])

    def test_fast_follow_initial_approval_requires_fresh_entry_second_proof(self) -> None:
        config_path = self._config_path(fast_follow=True)
        no_order_summary = self._write_no_order_summary(slot_status="open")

        summary, exit_code = run_unattended_epoch_controller(
            _args(config_path, apply=True),
            env={},
            no_order_runner=_runner(no_order_summary, 0),
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            notification_sender=_notification_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_epoch_armed")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        latest_arm = store.latest_operator_action(action_type="arm-live-delta", status="applied")
        self.assertFalse(latest_arm["fast_follow_authorized"])
        self.assertEqual(latest_arm["fast_follow_owner_decision"], "pending_fresh_entry_second_no_order_proof")
        self.assertEqual(latest_arm["fast_follow_epoch_id"], latest_arm["epoch_id"])
        self.assertEqual(latest_arm["fast_follow_max_chain_depth"], 1)
        self.assertTrue(latest_arm["fast_follow_cleanup_required"])
        self.assertTrue(latest_arm["fast_follow_requires_fresh_no_order_proof"])
        self.assertNotIn("fast_follow_expected_symbols", latest_arm)
        self.assertNotIn("fast_follow_expected_max_turnover_usdt", latest_arm)
        epoch = UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch()
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.max_live_cycles, 2)
        self.assertEqual(latest_arm["max_timer_fires"], 2)

    def test_fast_follow_entry_second_payload_is_bound_to_entry_proof_symbols(self) -> None:
        source_approval = {
            "contract_version": UNATTENDED_EPOCH_APPROVAL_CONTRACT,
            "action_id": "source-arm",
            "epoch_id": "epoch-1",
            "expected_epoch_id": "epoch-1",
            "budget_epoch_id": "epoch-1",
            "slot_id": "slot-20260518",
            "target_hash": "hash-20260518",
            "expected_execution_stage": "reduce_first",
            "expected_symbols": ["AAVEUSDT", "BNBUSDT"],
            "expected_sides": ["BUY", "SELL"],
            "expected_reduce_only": True,
            "expected_max_order_count": 2,
            "expected_max_turnover_usdt": 100.0,
            "approval_expires_at_utc": "2026-05-18T00:25:00Z",
            "timer_window": {
                "timer_name": "timer",
                "timer_enable_earliest_utc": "2026-05-18T00:10:00Z",
                "timer_enable_latest_utc": "2026-05-18T00:25:00Z",
                "max_timer_fires_authorized": 2,
            },
            "max_timer_fires": 2,
            "fast_follow_max_chain_depth": 1,
        }
        proof = {
            "status": "passed",
            "run_id": "entry-proof",
            "artifact_root": "artifact/entry-proof",
            "execution_stage": "entry_second",
            "orders_submitted": 0,
            "fill_count": 0,
            "planned_order_count": 2,
            "projected_turnover_usdt": 42.0,
            "slot": {
                "slot_id": "slot-20260518",
                "target_hash": "hash-20260518",
                "status": "open",
            },
            "planned_orders": {
                "row_count": 2,
                "rows": [
                    {"symbol": "BCHUSDT", "side": "SELL", "reduce_only": False, "rounded_notional_usdt": 21.0},
                    {"symbol": "ETHUSDT", "side": "BUY", "reduce_only": False, "rounded_notional_usdt": 21.0},
                ],
            },
        }

        result = build_fast_follow_entry_second_owner_payload(
            run_id="daily-policy",
            now=_fixed_now(),
            proof=proof,
            source_approval=source_approval,
            bounds={
                "blockers": [],
                "max_gross_turnover_usdt": 0.0,
                "operator_hard_cap_usdt": None,
                "turnover_budget_mode": "proof_buffered",
                "turnover_buffer": 2.5,
                "max_live_cycles": 2,
                "approval_ttl_seconds": 900,
                "timer_window_seconds": 900,
                "max_timer_fires": 2,
                "fast_follow_max_chain_depth": 1,
            },
            source_supervisor_run_id="reduce-supervisor",
            source_core_run_id="reduce-core",
        )

        self.assertEqual(result["status"], "ready")
        payload = result["payload"]
        self.assertEqual(payload["expected_execution_stage"], "reduce_first")
        self.assertEqual(payload["expected_symbols"], ["AAVEUSDT", "BNBUSDT"])
        self.assertTrue(payload["fast_follow_authorized"])
        self.assertEqual(payload["fast_follow_expected_execution_stage"], "entry_second")
        self.assertEqual(payload["fast_follow_expected_symbols"], ["BCHUSDT", "ETHUSDT"])
        self.assertEqual(payload["fast_follow_allowed_symbols"], ["BCHUSDT", "ETHUSDT"])
        self.assertEqual(payload["fast_follow_expected_sides"], ["BUY", "SELL"])
        self.assertFalse(payload["fast_follow_expected_reduce_only"])
        self.assertEqual(payload["fast_follow_expected_max_order_count"], 2)
        self.assertEqual(payload["fast_follow_expected_max_turnover_usdt"], 105.0)
        self.assertEqual(payload["fast_follow_no_order_canary"]["orders_submitted"], 0)

    def test_dynamic_budget_uses_projected_turnover_buffer_without_hard_cap(self) -> None:
        config_path = self._config_path(dynamic_budget=True, hard_cap=None, turnover_buffer=1.25)
        no_order_summary = self._write_no_order_summary(slot_status="open", rounded_notional=6.0)

        summary, exit_code = run_unattended_epoch_controller(
            _args(config_path, apply=True),
            env={},
            no_order_runner=_runner(no_order_summary, 0),
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            notification_sender=_notification_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_epoch_armed")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        latest_arm = store.latest_operator_action(action_type="arm-live-delta", status="applied")
        turnover_budget = latest_arm["turnover_budget"]
        self.assertEqual(turnover_budget["mode"], "proof_buffered")
        self.assertEqual(turnover_budget["projected_turnover_usdt"], 6.0)
        self.assertEqual(turnover_budget["turnover_buffer"], 1.25)
        self.assertEqual(turnover_budget["buffered_turnover_usdt"], 7.5)
        self.assertIsNone(turnover_budget["operator_hard_cap_usdt"])
        self.assertFalse(turnover_budget["operator_hard_cap_enforced"])
        self.assertEqual(turnover_budget["resolved_max_gross_turnover_usdt"], 7.5)
        self.assertEqual(latest_arm["expected_max_turnover_usdt"], 7.5)
        epoch = UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch()
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.max_gross_turnover_usdt, 7.5)

    def test_dynamic_budget_allows_projected_turnover_above_legacy_hard_cap(self) -> None:
        config_path = self._config_path(dynamic_budget=True, hard_cap=20.0, turnover_buffer=1.25)
        no_order_summary = self._write_no_order_summary(slot_status="open", rounded_notional=25.0)

        summary, exit_code = run_unattended_epoch_controller(
            _args(config_path, apply=True),
            env={},
            no_order_runner=_runner(no_order_summary, 0),
            now_fn=_fixed_now,
            command_runner=_command_runner([]),
            notification_sender=_notification_sender([]),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "unattended_epoch_armed")
        self.assertEqual(summary["blockers"], [])
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        latest_arm = store.latest_operator_action(action_type="arm-live-delta", status="applied")
        turnover_budget = latest_arm["turnover_budget"]
        self.assertEqual(turnover_budget["projected_turnover_usdt"], 25.0)
        self.assertEqual(turnover_budget["buffered_turnover_usdt"], 31.25)
        self.assertEqual(turnover_budget["operator_hard_cap_usdt"], 20.0)
        self.assertFalse(turnover_budget["operator_hard_cap_enforced"])
        self.assertEqual(turnover_budget["resolved_max_gross_turnover_usdt"], 31.25)
        epoch = UnattendedBudgetStore(self.temp_dir / "state.sqlite3").read_current_epoch()
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.max_gross_turnover_usdt, 31.25)

    def test_terminal_cleanup_disables_timer_disarms_closes_epoch_and_preserves_orphans(self) -> None:
        db = self.temp_dir / "state.sqlite3"
        state_store = LiveTradingStateStore(db)
        budget_store = UnattendedBudgetStore(db)
        budget_store.open_epoch(
            epoch_id="cleanup-epoch",
            max_live_cycles=2,
            max_gross_turnover_usdt=100.0,
            max_age_seconds=900,
            now_utc=_fixed_now(),
            reason="unit test",
        )
        budget_store.reserve(
            epoch_id="cleanup-epoch",
            reservation_key="cleanup-reservation",
            run_id="live-run",
            projected_turnover_usdt=10.0,
            now_utc=_fixed_now(),
        )
        state_store.record_operator_action(
            run_id="operator-arm",
            action_type="arm-live-delta",
            reason="unit test arm",
            created_at_utc="2026-05-18T00:00:00Z",
        )
        commands: list[list[str]] = []
        notifications: list[tuple[str, dict]] = []

        result = terminal_cleanup(
            state_store=state_store,
            budget_store=budget_store,
            run_id="controller-failure",
            now=_fixed_now(),
            reason="unit test cleanup",
            blockers=["unattended_approval_expired"],
            epoch_id="cleanup-epoch",
            timer_name="meridian-alpha-mainnet-supervisor-live.timer",
            artifact_root=self.temp_dir / "cleanup",
            command_runner=_command_runner(commands),
            notification_sender=_notification_sender(notifications),
            env={},
        )

        self.assertEqual(result["status"], "terminal_cleanup_completed")
        self.assertEqual(commands, [["systemctl", "disable", "--now", "meridian-alpha-mainnet-supervisor-live.timer"]])
        self.assertFalse(state_store.read_operator_state()["live_delta_armed"])
        self.assertIsNone(budget_store.read_current_epoch())
        self.assertEqual(len(result["orphan_reservations_preserved"]), 1)
        self.assertEqual(result["orphan_reservations_preserved"][0]["reservation_key"], "cleanup-reservation")
        self.assertEqual(len(notifications), 1)
        self.assertTrue((self.temp_dir / "cleanup" / "terminal_cleanup.json").exists())

    def _config_path(
        self,
        *,
        fast_follow: bool = False,
        dynamic_budget: bool = False,
        hard_cap: float | None = 20.0,
        turnover_buffer: float = 1.25,
    ) -> Path:
        path = self.temp_dir / "controller.yaml"
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
                    *(
                        [
                            "  turnover_budget_mode: proof_buffered",
                            f"  turnover_buffer: {float(turnover_buffer)}",
                            *([] if hard_cap is None else [f"  operator_hard_cap_usdt: {float(hard_cap)}"]),
                        ]
                        if dynamic_budget
                        else [f"  max_gross_turnover_usdt: {float(hard_cap)}"]
                    ),
                    f"  max_live_cycles: {2 if fast_follow else 1}",
                    "  max_age_seconds: 900",
                    "  approval_ttl_seconds: 900",
                    "  timer_window_seconds: 900",
                    f"  max_timer_fires: {2 if fast_follow else 1}",
                    f"  fast_follow_entry_second_authorized: {str(bool(fast_follow)).lower()}",
                    "  fast_follow_max_chain_depth: 1",
                    "  systemd_timer_name: meridian-alpha-mainnet-supervisor-live.timer",
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
        slot_status: str,
        gate_status: str = "freeze_new_slot_target",
        rounded_notional: float = 6.0,
    ) -> dict:
        plan_root = self.temp_dir / "proof" / "plan"
        delta_root = self.temp_dir / "proof" / "delta"
        plan_root.mkdir(parents=True, exist_ok=True)
        delta_root.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "schema_version": "daily_rebalance_slot_target.v1",
            "slot_id": "slot-20260518",
            "target_hash": "hash-20260518",
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
        if slot_status == "completed":
            snapshot["completed_at_utc"] = "2026-05-18T00:00:00Z"
        gate = {
            "status": gate_status,
            "slot_id": "slot-20260518",
            "active_target_hash": "hash-20260518",
            "blockers": [],
            "warnings": [],
        }
        write_json(plan_root / "frozen_target_snapshot.json", snapshot)
        write_json(plan_root / "frozen_slot_gate.json", gate)
        write_json(
            delta_root / "planned_delta_orders.json",
            {
                "row_count": 1,
                "rows": [
                    {
                        "symbol": "AAVEUSDT",
                        "side": "BUY",
                        "reduce_only": True,
                        "rounded_notional_usdt": float(rounded_notional),
                    }
                ],
            },
        )
        LiveTradingStateStore(self.temp_dir / "state.sqlite3").write_rebalance_slot_target(snapshot)
        return {
            "run_id": "proof-run",
            "status": "mainnet_core_loop_completed",
            "mode": "core_loop",
            "artifact_root": str(self.temp_dir / "proof" / "core"),
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
                        "slot_id": "slot-20260518",
                        "target_hash": "hash-20260518",
                        "status": slot_status,
                    },
                    "frozen_slot_gate": gate,
                    "delta_preflight": {
                        "execution_stage": "reduce_first",
                        "planned_delta_order_count": 1,
                    },
                    "live_delta_policy_gate": {
                        "execution_stage": "reduce_first",
                        "planned_delta_order_count": 1,
                    },
                }
            ],
        }


def _args(config_path: Path, *, apply: bool, ignore_heartbeat_run_id: str = "") -> Namespace:
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
        max_gross_turnover_usdt=None,
        max_live_cycles=None,
        max_age_seconds=None,
        approval_ttl_seconds=None,
        timer_window_seconds=None,
        max_timer_fires=None,
        systemd_timer_name="",
        ignore_heartbeat_run_id=ignore_heartbeat_run_id,
        no_terminal_cleanup_on_failure=False,
    )


def _fixed_now() -> datetime:
    return datetime(2026, 5, 18, 0, 10, 0, tzinfo=UTC)


def _runner(summary: dict, exit_code: int):
    def run(_args: Namespace, **_kwargs):
        return summary, exit_code

    return run


def _command_runner(calls: list[list[str]]):
    def run(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(list(cmd))
        return 0, "ok\n", ""

    return run


def _notification_sender(calls: list[tuple[str, dict]]):
    def send(text: str, payload: dict) -> dict:
        calls.append((text, payload))
        return {"status": "sent"}

    return send


if __name__ == "__main__":
    unittest.main()
