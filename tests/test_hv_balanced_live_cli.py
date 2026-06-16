from __future__ import annotations

from argparse import Namespace
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

from enhengclaw.live_trading.cli import run_from_args
from enhengclaw.live_trading.daily_rebalance_slot_gate import REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION
from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256
from enhengclaw.live_trading.state_store import LiveTradingStateStore


class HvBalancedLiveCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-live-cli-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_cli_defaults_to_blocked_without_market_data_source(self) -> None:
        config_path = self._config_path()

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_fixture_panel_or_live_market_data_source", summary["blockers"])

    def test_cli_live_without_confirmation_is_blocked(self) -> None:
        config_path = self._config_path()

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="live",
                as_of="now",
                fixture_panel="",
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("missing_live_confirmation_flag", summary["blockers"])
        self.assertIn("live_execution_not_enabled_in_phase1", summary["blockers"])

    def test_cli_plan_only_writes_artifacts_for_fixture_panel(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel=str(panel_path),
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "passed_plan_only")
        artifact_root = Path(summary["artifact_root"])
        self.assertTrue((artifact_root / "run_summary.json").exists())
        self.assertTrue((artifact_root / "decision_scores.csv").exists())
        self.assertTrue((artifact_root / "execution_plan.csv").exists())

    def test_cli_blocks_when_as_of_precedes_available_panel(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="-1",
                fixture_panel=str(panel_path),
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("as_of_before_available_panel", summary["blockers"])

    def test_cli_paper_uses_public_market_data_path_without_order_submission(self) -> None:
        config_path = self._config_path(public_market_data=True)
        symbol_filters = {
            f"{subject}USDT": {"step_size": 0.001, "min_qty": 0.0, "min_notional": 0.0}
            for subject in ["L1", "L2", "L3", "S1", "S2", "S3"]
        }

        with patch(
            "enhengclaw.live_trading.cli.fetch_public_live_feature_panel",
            return_value=(
                _fixture_panel(),
                {"source": "unit_test_public_rest", "row_count": 6},
                symbol_filters,
            ),
        ) as fetch_panel:
            summary, exit_code = run_from_args(
                Namespace(
                    config=str(config_path),
                    mode="paper",
                    as_of="now",
                    fixture_panel="",
                    symbols="BTCUSDT,ETHUSDT",
                    public_market_data=False,
                    i_understand_this_is_live=False,
                )
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "paper_executed")
        fetch_panel.assert_called_once()
        artifact_root = Path(summary["artifact_root"])
        self.assertTrue((artifact_root / "market_data_audit.json").exists())
        self.assertTrue((artifact_root / "symbol_exchange_filters.json").exists())
        self.assertTrue((artifact_root / "order_sizing_report.csv").exists())
        self.assertTrue((artifact_root / "min_executable_capital_report.json").exists())
        self.assertTrue((artifact_root / "paper_execution.json").exists())
        sizing_summary = json.loads((artifact_root / "min_executable_capital_report.json").read_text(encoding="utf-8"))
        submitted_orders = pd.read_csv(artifact_root / "submitted_orders.csv")
        fills = pd.read_csv(artifact_root / "fills.csv")
        self.assertGreater(len(submitted_orders), 0)
        self.assertEqual(len(submitted_orders), len(fills))
        self.assertTrue(fills["liquidity"].eq("TAKER_SIM").all())
        self.assertEqual(sizing_summary["status"], "passed")
        positions = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_paper_positions()
        self.assertGreater(len(positions), 0)

    def test_cli_paper_blocks_duplicate_decision_after_persisted_execution(self) -> None:
        config_path = self._config_path(public_market_data=True)
        symbol_filters = {
            f"{subject}USDT": {"step_size": 0.001, "min_qty": 0.0, "min_notional": 0.0}
            for subject in ["L1", "L2", "L3", "S1", "S2", "S3"]
        }
        fetch_result = (
            _fixture_panel(),
            {"source": "unit_test_public_rest", "row_count": 6},
            symbol_filters,
        )

        with patch("enhengclaw.live_trading.cli.fetch_public_live_feature_panel", return_value=fetch_result):
            first_summary, first_exit_code = run_from_args(
                Namespace(
                    config=str(config_path),
                    mode="paper",
                    as_of="now",
                    fixture_panel="",
                    symbols="BTCUSDT,ETHUSDT",
                    public_market_data=False,
                    i_understand_this_is_live=False,
                )
            )
            second_summary, second_exit_code = run_from_args(
                Namespace(
                    config=str(config_path),
                    mode="paper",
                    as_of="now",
                    fixture_panel="",
                    symbols="BTCUSDT,ETHUSDT",
                    public_market_data=False,
                    i_understand_this_is_live=False,
                )
            )

        self.assertEqual(first_exit_code, 0)
        self.assertEqual(first_summary["status"], "paper_executed")
        self.assertEqual(second_exit_code, 2)
        self.assertEqual(second_summary["status"], "blocked")
        self.assertTrue(
            any(blocker.startswith("duplicate_paper_plan_already_executed:") for blocker in second_summary["blockers"])
        )

    def test_cli_blocks_when_local_state_has_stale_running_heartbeat(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="stale-run",
            mode="paper",
            status="running",
            started_at_utc="2026-05-16T00:00:00Z",
            updated_at_utc="2026-05-16T00:00:00Z",
        )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel=str(panel_path),
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("stale_running_heartbeat:stale-run", summary["blockers"])
        health = json.loads((Path(summary["artifact_root"]) / "local_state_health.json").read_text(encoding="utf-8"))
        self.assertEqual(health["status"], "blocked")

    def test_cli_operator_pause_blocks_normal_run_until_resume(self) -> None:
        config_path = self._config_path()

        pause_summary, pause_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action="pause",
                operator_reason="manual pause",
                i_understand_this_is_live=False,
            )
        )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        blocked_summary, blocked_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel=str(panel_path),
                operator_action="none",
                operator_reason="",
                i_understand_this_is_live=False,
            )
        )
        resume_summary, resume_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action="resume",
                operator_reason="manual resume",
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(pause_exit_code, 0)
        self.assertEqual(pause_summary["status"], "operator_paused")
        self.assertEqual(blocked_exit_code, 2)
        self.assertIn("operator_paused", blocked_summary["blockers"])
        self.assertEqual(resume_exit_code, 0)
        self.assertEqual(resume_summary["status"], "operator_resumed")
        self.assertFalse(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()["paused"])

    def test_cli_operator_arm_and_disarm_live_delta(self) -> None:
        config_path = self._config_path()

        arm_summary, arm_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action="arm-live-delta",
                operator_reason="approved supervisor",
                i_understand_this_is_live=False,
            )
        )
        armed_state = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()
        disarm_summary, disarm_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action="disarm-live-delta",
                operator_reason="stop live delta",
                i_understand_this_is_live=False,
            )
        )
        disarmed_state = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_operator_state()

        self.assertEqual(arm_exit_code, 0)
        self.assertEqual(arm_summary["status"], "operator_live_delta_armed")
        self.assertTrue(armed_state["live_delta_armed"])
        self.assertEqual(disarm_exit_code, 0)
        self.assertEqual(disarm_summary["status"], "operator_live_delta_disarmed")
        self.assertFalse(disarmed_state["live_delta_armed"])

    def test_cli_operator_arm_persists_owner_payload_json(self) -> None:
        config_path = self._config_path()
        payload = {
            "epoch_id": "owner-epoch",
            "expected_execution_stage": "reduce_first",
            "expected_symbols": ["AAVEUSDT"],
            "expected_max_turnover_usdt": 10.0,
        }

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action="arm-live-delta",
                operator_reason="approved bounded owner intent",
                operator_payload_json=json.dumps(payload),
                i_understand_this_is_live=False,
            )
        )
        action = LiveTradingStateStore(self.temp_dir / "state.sqlite3").latest_operator_action(
            action_type="arm-live-delta",
            status="applied",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "operator_live_delta_armed")
        self.assertIsNotNone(action)
        self.assertEqual(action["epoch_id"], "owner-epoch")
        self.assertEqual(action["expected_execution_stage"], "reduce_first")
        self.assertEqual(action["expected_symbols"], ["AAVEUSDT"])
        self.assertEqual(action["expected_max_turnover_usdt"], 10.0)

    def test_cli_authorizes_risk_only_reduce_cleanup_only_with_budgeted_no_order_canary(self) -> None:
        config_path = self._config_path()
        blocked_summary, blocked_exit = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
                operator_reason="missing canary should block",
                operator_payload_json="{}",
                i_understand_this_is_live=False,
            )
        )
        self.assertEqual(blocked_exit, 2)
        self.assertEqual(blocked_summary["status"], "blocked")
        self.assertIn("risk_only_reduce_cleanup_authorization_missing_slot_id", blocked_summary["blockers"])

        payload_path = self.temp_dir / "risk_cleanup_payload.json"
        payload_path.write_text(
            json.dumps(
                {
                    "slot_id": "slot-1",
                    "target_hash": "hash-1",
                    "budget_epoch_id": "epoch-1",
                    "no_order_canary": {
                        "status": "passed",
                        "artifact_root": "artifact-root",
                        "orders_submitted": 0,
                        "mainnet_order_submission_authorized": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel="",
                operator_action=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
                operator_reason="unit risk cleanup authorization",
                operator_payload_json=f"@{payload_path}",
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "risk_only_reduce_cleanup_authorized")
        action = LiveTradingStateStore(self.temp_dir / "state.sqlite3").latest_operator_action(
            action_type=REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION,
            status="applied",
            slot_id="slot-1",
            target_hash="hash-1",
        )
        self.assertIsNotNone(action)
        self.assertTrue(action["single_use"])
        self.assertEqual(action["budget_epoch_id"], "epoch-1")
        self.assertFalse(action["mainnet_order_submission_authorized"])

    def test_cli_operator_kill_switch_force_reconcile_and_flatten_drill(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        store.write_heartbeat(
            run_id="crashed-paper-run",
            mode="paper",
            status="running",
            started_at_utc="2026-05-16T00:00:00Z",
            updated_at_utc="2026-05-16T00:00:00Z",
        )
        with sqlite3.connect(store.path) as conn:
            for symbol, amount in {"L1USDT": 0.5, "S1USDT": -0.25}.items():
                conn.execute(
                    "INSERT OR REPLACE INTO paper_positions(symbol, position_amt, updated_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (symbol, amount, "2026-05-16T00:00:00Z", "{}"),
                )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        kill_summary, kill_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="kill-switch",
                operator_reason="abnormal fill requires operator halt",
                confirm_plan_id="",
                i_understand_this_is_live=False,
            )
        )
        blocked_summary, blocked_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel=str(panel_path),
                operator_action="none",
                operator_reason="",
                confirm_plan_id="",
                i_understand_this_is_live=False,
            )
        )
        reconcile_summary, reconcile_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="force-reconcile",
                operator_reason="read-only reconcile after halt",
                confirm_plan_id="",
                i_understand_this_is_live=False,
            )
        )
        flatten_summary, flatten_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel=str(panel_path),
                operator_action="flatten-plan",
                operator_reason="plan reduce-only flatten",
                confirm_plan_id="",
                i_understand_this_is_live=False,
            )
        )
        flatten_action = json.loads((Path(flatten_summary["artifact_root"]) / "operator_action.json").read_text(encoding="utf-8"))
        plan_id = str(flatten_action["plan_id"])
        confirm_summary, confirm_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="confirm-flatten-plan",
                operator_reason="confirm reduce-only flatten",
                confirm_plan_id=plan_id,
                i_understand_this_is_live=False,
            )
        )
        execute_summary, execute_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="execute-flatten-paper",
                operator_reason="execute confirmed paper flatten",
                confirm_plan_id=plan_id,
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(kill_exit_code, 0)
        self.assertEqual(kill_summary["status"], "operator_kill_switch_engaged")
        self.assertEqual(blocked_exit_code, 2)
        self.assertIn("operator_paused", blocked_summary["blockers"])
        self.assertEqual(reconcile_exit_code, 0)
        self.assertEqual(reconcile_summary["status"], "forced_reconcile_completed")
        reconcile_root = Path(reconcile_summary["artifact_root"])
        reconciliation = json.loads((reconcile_root / "reconciliation.json").read_text(encoding="utf-8"))
        submitted_orders = pd.read_csv(reconcile_root / "submitted_orders.csv")
        self.assertTrue(reconciliation["read_only"])
        self.assertEqual(reconciliation["exchange_order_submission"], "disabled")
        self.assertEqual(reconciliation["recovered_heartbeat_count"], 1)
        self.assertTrue(reconciliation["operator_paused"])
        self.assertTrue(submitted_orders.empty)
        self.assertEqual(flatten_exit_code, 0)
        self.assertEqual(flatten_summary["status"], "flatten_plan_generated")
        self.assertEqual(confirm_exit_code, 0)
        self.assertEqual(confirm_summary["status"], "flatten_plan_confirmed")
        self.assertEqual(execute_exit_code, 0)
        self.assertEqual(execute_summary["status"], "flatten_paper_executed")
        self.assertEqual(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_paper_positions(), {})

    def test_cli_operator_flatten_plan_generates_reduce_only_intents(self) -> None:
        config_path = self._config_path()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        with sqlite3.connect(store.path) as conn:
            for symbol, amount in {"L1USDT": 0.5, "S1USDT": -0.25}.items():
                conn.execute(
                    "INSERT OR REPLACE INTO paper_positions(symbol, position_amt, updated_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (symbol, amount, "2026-05-16T00:00:00Z", "{}"),
                )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="plan_only",
                as_of="now",
                fixture_panel=str(panel_path),
                operator_action="flatten-plan",
                operator_reason="manual flatten",
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "flatten_plan_generated")
        artifact_root = Path(summary["artifact_root"])
        action = json.loads((artifact_root / "operator_action.json").read_text(encoding="utf-8"))
        plan = pd.read_csv(artifact_root / "execution_plan.csv")
        self.assertEqual(action["action_type"], "flatten-plan")
        self.assertEqual(set(plan["symbol"]), {"L1USDT", "S1USDT"})
        self.assertTrue(plan["reduce_only"].all())
        self.assertEqual(set(plan["side"]), {"BUY", "SELL"})

    def test_cli_confirm_flatten_plan_requires_matching_plan_id(self) -> None:
        config_path = self._config_path()

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="confirm-flatten-plan",
                operator_reason="wrong plan",
                confirm_plan_id="missing-plan",
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("flatten_plan_not_found_for_confirmation:missing-plan", summary["blockers"])

    def test_cli_execute_flatten_paper_requires_prior_confirmation(self) -> None:
        config_path = self._config_path()
        plan_id = self._generate_flatten_plan(config_path)

        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="execute-flatten-paper",
                operator_reason="execute without confirm",
                confirm_plan_id=plan_id,
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(f"flatten_plan_confirmation_missing:{plan_id}", summary["blockers"])

    def test_cli_confirmed_flatten_paper_execution_updates_positions(self) -> None:
        config_path = self._config_path()
        plan_id = self._generate_flatten_plan(config_path)

        confirm_summary, confirm_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="confirm-flatten-plan",
                operator_reason="confirm flatten",
                confirm_plan_id=plan_id,
                i_understand_this_is_live=False,
            )
        )
        execute_summary, execute_exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel="",
                operator_action="execute-flatten-paper",
                operator_reason="execute confirmed flatten",
                confirm_plan_id=plan_id,
                i_understand_this_is_live=False,
            )
        )

        self.assertEqual(confirm_exit_code, 0)
        self.assertEqual(confirm_summary["status"], "flatten_plan_confirmed")
        self.assertEqual(execute_exit_code, 0)
        self.assertEqual(execute_summary["status"], "flatten_paper_executed")
        artifact_root = Path(execute_summary["artifact_root"])
        fills = pd.read_csv(artifact_root / "fills.csv")
        self.assertEqual(set(fills["symbol"]), {"L1USDT", "S1USDT"})
        self.assertEqual(LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_paper_positions(), {})

    def _config_path(self, *, public_market_data: bool = False) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm.yaml"
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
                    "capital:",
                    "  allocated_capital_usdt: 100.0",
                    "risk:",
                    "  trading_enabled: false",
                    "  max_allocated_capital_usdt: 100.0",
                    "  max_gross_notional_usdt: 100.0",
                    "  max_symbol_notional_usdt: 20.0",
                    "market_data:",
                    f"  public_data_enabled: {str(public_market_data).lower()}",
                    "state:",
                    f"  sqlite_path: {sqlite_path}",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _generate_flatten_plan(self, config_path: Path) -> str:
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        with sqlite3.connect(store.path) as conn:
            for symbol, amount in {"L1USDT": 0.5, "S1USDT": -0.25}.items():
                conn.execute(
                    "INSERT OR REPLACE INTO paper_positions(symbol, position_amt, updated_at_utc, payload_json) VALUES (?, ?, ?, ?)",
                    (symbol, amount, "2026-05-16T00:00:00Z", "{}"),
                )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        summary, exit_code = run_from_args(
            Namespace(
                config=str(config_path),
                mode="paper",
                as_of="now",
                fixture_panel=str(panel_path),
                operator_action="flatten-plan",
                operator_reason="generate flatten",
                confirm_plan_id="",
                i_understand_this_is_live=False,
            )
        )
        self.assertEqual(exit_code, 0)
        action = json.loads((Path(summary["artifact_root"]) / "operator_action.json").read_text(encoding="utf-8"))
        return str(action["plan_id"])


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
