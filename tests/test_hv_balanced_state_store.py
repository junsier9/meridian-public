from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.models import ExecutionPlan, OrderIntent
from enhengclaw.live_trading.paper_broker import simulate_paper_execution
from enhengclaw.live_trading.state_store import LiveTradingStateStore


class HvBalancedStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-state-store-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_record_paper_execution_persists_positions_and_duplicate_key(self) -> None:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        plan = ExecutionPlan(
            plan_id="portfolio:plan:paper",
            portfolio_id="portfolio",
            mode="paper",
            status="ok",
            intents=[
                _intent(symbol="BTCUSDT", side="BUY", quantity=0.01, seq=1),
                _intent(symbol="ETHUSDT", side="SELL", quantity=0.20, seq=2),
            ],
        )
        execution = simulate_paper_execution(
            plan,
            mark_prices={"BTCUSDT": 100_000.0, "ETHUSDT": 5_000.0},
            run_id="run",
            created_at_utc="2026-05-16T00:00:00Z",
        )

        store.record_paper_execution(execution)

        positions = store.read_paper_positions()
        self.assertTrue(store.has_paper_execution("portfolio:plan:paper"))
        self.assertAlmostEqual(positions["BTCUSDT"], 0.01)
        self.assertAlmostEqual(positions["ETHUSDT"], -0.20)

    def test_local_state_health_blocks_stale_running_heartbeat(self) -> None:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="stale-run",
            mode="paper",
            status="running",
            started_at_utc="2026-05-16T00:00:00Z",
            updated_at_utc="2026-05-16T00:00:00Z",
        )

        health = store.evaluate_local_state_health(
            now="2026-05-16T00:20:00Z",
            max_heartbeat_age_seconds=300,
        )

        self.assertEqual(health["status"], "blocked")
        self.assertIn("stale_running_heartbeat:stale-run", health["blockers"])

    def test_stale_running_heartbeat_can_be_explicitly_recovered_after_restart(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        first_process = LiveTradingStateStore(sqlite_path)
        first_process.write_heartbeat(
            run_id="crashed-run",
            mode="testnet",
            status="running",
            started_at_utc="2026-05-16T00:00:00Z",
            updated_at_utc="2026-05-16T00:00:00Z",
            artifact_root=str(self.temp_dir / "runs" / "crashed-run"),
        )

        restarted_process = LiveTradingStateStore(sqlite_path)
        before = restarted_process.evaluate_local_state_health(
            now="2026-05-16T00:20:00Z",
            max_heartbeat_age_seconds=300,
        )
        recovered = restarted_process.recover_stale_running_heartbeats(
            now="2026-05-16T00:20:00Z",
            max_heartbeat_age_seconds=300,
            recovery_run_id="restart-reconcile-1",
            reason="fixture restart recovery",
        )
        after = LiveTradingStateStore(sqlite_path).evaluate_local_state_health(
            now="2026-05-16T00:20:01Z",
            max_heartbeat_age_seconds=300,
        )

        self.assertIn("stale_running_heartbeat:crashed-run", before["blockers"])
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["run_id"], "crashed-run")
        self.assertEqual(recovered[0]["previous_status"], "running")
        self.assertEqual(recovered[0]["new_status"], "reconcile_required")
        self.assertIn("stale_running_heartbeat_recovered:crashed-run", recovered[0]["blockers"])
        self.assertEqual(after["status"], "ok")
        with sqlite3.connect(sqlite_path) as conn:
            status = conn.execute("SELECT status FROM heartbeats WHERE run_id = ?", ("crashed-run",)).fetchone()[0]
        self.assertEqual(status, "reconcile_required")

    def test_local_state_health_blocks_orphan_paper_order(self) -> None:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        with sqlite3.connect(store.path) as conn:
            conn.execute(
                "INSERT INTO paper_orders(paper_order_id, plan_id, created_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                ("paper-order-1", "missing-plan", "2026-05-16T00:00:00Z", "{}"),
            )

        health = store.evaluate_local_state_health(now="2026-05-16T00:00:01Z")

        self.assertEqual(health["status"], "blocked")
        self.assertIn("orphan_paper_orders_without_execution:1", health["blockers"])

    def test_operator_pause_and_resume_update_operator_state(self) -> None:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")

        pause = store.record_operator_action(
            run_id="run-1",
            action_type="pause",
            reason="manual stop",
            created_at_utc="2026-05-16T00:00:00Z",
        )
        paused_state = store.read_operator_state()
        resume = store.record_operator_action(
            run_id="run-2",
            action_type="resume",
            reason="manual restart",
            created_at_utc="2026-05-16T00:01:00Z",
        )
        resumed_state = store.read_operator_state()

        self.assertEqual(pause["action_type"], "pause")
        self.assertTrue(paused_state["paused"])
        self.assertEqual(paused_state["last_reason"], "manual stop")
        self.assertEqual(resume["action_type"], "resume")
        self.assertFalse(resumed_state["paused"])
        self.assertEqual(resumed_state["last_reason"], "manual restart")

    def test_operator_kill_switch_sets_paused_state(self) -> None:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")

        action = store.record_operator_action(
            run_id="run-kill",
            action_type="kill-switch",
            reason="abnormal condition",
            created_at_utc="2026-05-16T00:00:00Z",
        )
        state = store.read_operator_state()

        self.assertEqual(action["action_type"], "kill-switch")
        self.assertTrue(state["paused"])
        self.assertEqual(state["last_action_type"], "kill-switch")
        self.assertEqual(state["last_reason"], "abnormal condition")
        self.assertFalse(state["live_delta_armed"])
        self.assertEqual(state["live_delta_last_action_type"], "kill-switch")

    def test_operator_arm_and_disarm_live_delta_are_persistent_and_separate_from_pause(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        store = LiveTradingStateStore(sqlite_path)

        armed = store.record_operator_action(
            run_id="run-arm",
            action_type="arm-live-delta",
            reason="server supervisor approved",
            created_at_utc="2026-05-16T00:00:00Z",
        )
        paused = store.record_operator_action(
            run_id="run-pause",
            action_type="pause",
            reason="temporary inspection",
            created_at_utc="2026-05-16T00:01:00Z",
        )
        state_after_pause = LiveTradingStateStore(sqlite_path).read_operator_state()
        disarmed = store.record_operator_action(
            run_id="run-disarm",
            action_type="disarm-live-delta",
            reason="blocker",
            created_at_utc="2026-05-16T00:02:00Z",
        )
        state_after_disarm = LiveTradingStateStore(sqlite_path).read_operator_state()

        self.assertEqual(armed["action_type"], "arm-live-delta")
        self.assertEqual(paused["action_type"], "pause")
        self.assertTrue(state_after_pause["paused"])
        self.assertTrue(state_after_pause["live_delta_armed"])
        self.assertEqual(state_after_pause["live_delta_last_reason"], "server supervisor approved")
        self.assertEqual(disarmed["action_type"], "disarm-live-delta")
        self.assertFalse(state_after_disarm["live_delta_armed"])
        self.assertEqual(state_after_disarm["live_delta_last_reason"], "blocker")

    def test_record_live_artifact_persists_stage_payload(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        store = LiveTradingStateStore(sqlite_path)

        record = store.record_live_artifact(
            run_id="core-loop-1",
            artifact_type="account reconcile",
            artifact_id="artifact-1",
            payload={"open_order_count": 0, "available_balance_usdt": 123.0},
        )

        self.assertEqual(record["artifact_type"], "account_reconcile")
        with sqlite3.connect(sqlite_path) as conn:
            row = conn.execute(
                "SELECT run_id, artifact_type, payload_json FROM live_artifacts WHERE artifact_id = ?",
                ("artifact-1",),
            ).fetchone()
        self.assertEqual(row[0], "core-loop-1")
        self.assertEqual(row[1], "account_reconcile")
        self.assertIn('"available_balance_usdt": 123.0', row[2])

    def test_latest_live_submission_skips_daily_policy_wrapper_summary(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        store = LiveTradingStateStore(sqlite_path)
        store.initialize()
        core_payload = {
            "run_id": "core-run",
            "status": "mainnet_core_loop_completed",
            "orders_submitted": 4,
            "fill_count": 4,
            "live_delta_authorized": True,
            "started_at_utc": "2026-06-14T01:42:10Z",
            "finished_at_utc": "2026-06-14T01:45:05Z",
            "cycles": [
                {
                    "status": "cycle_executed_reconciled",
                    "live_delta_policy_gate": {"execution_stage": "reduce_first"},
                    "post_trade_reconcile": {"status": "passed_live_position_monitor"},
                }
            ],
        }
        wrapper_payload = {
            "run_id": "daily-policy",
            "status": "unattended_daily_policy_timer_fire_completed",
            "orders_submitted": 4,
            "fill_count": 4,
            "started_at_utc": "2026-06-14T01:39:19Z",
            "finished_at_utc": "2026-06-14T01:49:09Z",
        }
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute(
                "INSERT INTO run_summaries(run_id, created_at_utc, payload_json) VALUES (?, ?, ?)",
                ("core-run", "2026-06-14T01:45:05Z", json.dumps(core_payload)),
            )
            conn.execute(
                "INSERT INTO run_summaries(run_id, created_at_utc, payload_json) VALUES (?, ?, ?)",
                ("daily-policy", "2026-06-14T01:49:10Z", json.dumps(wrapper_payload)),
            )

        latest = store.latest_live_order_submission()

        self.assertEqual(latest["run_id"], "core-run")
        self.assertEqual(latest["execution_stage"], "reduce_first")
        self.assertEqual(latest["post_trade_reconcile_status"], "passed_live_position_monitor")

    def test_latest_live_submission_reads_top_level_post_trade_reconcile(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        store = LiveTradingStateStore(sqlite_path)
        store.initialize()
        payload = {
            "run_id": "direct-delta",
            "status": "mainnet_delta_orders_submitted",
            "execution_stage": "entry_second",
            "submitted_order_count": 2,
            "fill_count": 2,
            "post_trade_reconcile": {"status": "passed_live_position_monitor"},
        }
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute(
                "INSERT INTO run_summaries(run_id, created_at_utc, payload_json) VALUES (?, ?, ?)",
                ("direct-delta", "2026-06-15T02:07:23Z", json.dumps(payload)),
            )

        latest = store.latest_live_order_submission()

        self.assertEqual(latest["run_id"], "direct-delta")
        self.assertEqual(latest["execution_stage"], "entry_second")
        self.assertEqual(latest["post_trade_reconcile_status"], "passed_live_position_monitor")

    def test_latest_live_submission_does_not_promote_direct_delta_reconcile(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        store = LiveTradingStateStore(sqlite_path)
        store.initialize()
        payload = {
            "run_id": "direct-delta",
            "status": "mainnet_delta_orders_submitted",
            "execution_stage": "entry_second",
            "submitted_order_count": 2,
            "fill_count": 2,
            "reconciliation_status": "reconciled",
            "post_trade_reconcile": {"status": "direct_delta_reconciled"},
        }
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute(
                "INSERT INTO run_summaries(run_id, created_at_utc, payload_json) VALUES (?, ?, ?)",
                ("direct-delta", "2026-06-15T02:07:23Z", json.dumps(payload)),
            )

        latest = store.latest_live_order_submission()

        self.assertEqual(latest["post_trade_reconcile_status"], "direct_delta_reconciled")

    def test_multiphase_sleeve_target_store_replaces_by_sleeve_id(self) -> None:
        sqlite_path = self.temp_dir / "state.sqlite3"
        store = LiveTradingStateStore(sqlite_path)

        first = store.write_multiphase_sleeve_target(
            {
                "sleeve_id": "hv:phase:3",
                "strategy_label": "hv",
                "phase_offset_days": 3,
                "decision_time_ms": 86_400_000,
                "decision_date_utc": "1970-01-02",
                "status": "ok",
                "target_positions": [{"usdm_symbol": "BTCUSDT", "target_weight": 0.1}],
            }
        )
        second = store.write_multiphase_sleeve_target(
            {
                "sleeve_id": "hv:phase:3",
                "strategy_label": "hv",
                "phase_offset_days": 3,
                "decision_time_ms": 172_800_000,
                "decision_date_utc": "1970-01-03",
                "status": "ok",
                "target_positions": [{"usdm_symbol": "ETHUSDT", "target_weight": -0.2}],
            }
        )

        rows = store.read_multiphase_sleeve_targets(strategy_label="hv")

        self.assertEqual(first["sleeve_id"], "hv:phase:3")
        self.assertEqual(second["decision_time_ms"], 172_800_000)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target_positions"][0]["usdm_symbol"], "ETHUSDT")


def _intent(*, symbol: str, side: str, quantity: float, seq: int) -> OrderIntent:
    signed = quantity if side == "BUY" else -quantity
    return OrderIntent(
        intent_id=f"intent-{seq}",
        portfolio_id="portfolio",
        symbol=symbol,
        side=side,
        position_side="BOTH",
        order_type="MARKET",
        quantity=quantity,
        reduce_only=False,
        target_position_amt=signed,
        current_position_amt=0.0,
        delta_position_amt=signed,
        max_slippage_bps=20.0,
        client_order_id=f"client-{seq}",
    )
