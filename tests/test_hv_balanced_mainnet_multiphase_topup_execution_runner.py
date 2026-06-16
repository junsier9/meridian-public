from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
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

from enhengclaw.live_trading.mainnet_multiphase_topup_execution_runner import (  # noqa: E402
    _required_topup_confirmation,
    run_mainnet_multiphase_topup_execution,
)


class HvBalancedMainnetMultiphaseTopupExecutionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-topup-exec-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_validates_topup_gate_before_delta_runner(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        calls: list[Namespace] = []

        summary, exit_code = run_mainnet_multiphase_topup_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env={},
            delta_runner=_fake_delta_runner(calls, status="mainnet_delta_execution_ready"),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_multiphase_topup_execution_ready")
        self.assertEqual(summary["topup_preflight_status"], "passed")
        self.assertEqual(summary["topup_gate_status"], "passed")
        self.assertEqual(summary["margin_cushion_gate_status"], "passed")
        self.assertEqual(summary["execution_stage"], "entry_second")
        self.assertFalse(calls[0].execute_mainnet_delta_orders)
        self.assertEqual(calls[0].confirm_mainnet_delta_execution, "")
        self.assertIn(":RESERVE=150:", summary["required_confirmation"])
        self.assertIn(":ENTRY_SECOND:ALL_OR_NONE:MARGIN_PASSED:NO_REDUCE:NO_DUST:", summary["required_confirmation"])

    def test_execute_requires_exact_topup_confirmation_before_delta_runner(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        calls: list[Namespace] = []

        summary, exit_code = run_mainnet_multiphase_topup_execution(
            _args(config_path=config_path, plan_root=plan_root, execute=True),
            env={},
            delta_runner=_fake_delta_runner(calls, status="mainnet_delta_orders_submitted"),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_exact_mainnet_topup_confirmation", summary["blockers"])
        self.assertEqual(calls, [])

        plan_hash = json.loads((Path(summary["artifact_root"]) / "run_summary.json").read_text(encoding="utf-8"))[
            "topup_plan_hash"
        ]
        confirmation = _required_topup_confirmation(
            plan_hash=plan_hash,
            reserve_usdt=150.0,
        )
        ok_summary, ok_exit = run_mainnet_multiphase_topup_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_active_ack=True,
                confirmation=confirmation,
            ),
            env={},
            delta_runner=_fake_delta_runner(calls, status="mainnet_delta_orders_submitted"),
            now_fn=_fixed_now,
        )

        self.assertEqual(ok_exit, 0)
        self.assertEqual(ok_summary["status"], "mainnet_multiphase_topup_orders_submitted")
        self.assertTrue(calls[-1].execute_mainnet_delta_orders)
        self.assertTrue(calls[-1].operator_enable_mainnet_delta_for_this_run)
        self.assertTrue(calls[-1].i_understand_this_places_real_mainnet_delta_orders)
        self.assertFalse(calls[-1].i_understand_daily_realized_pnl_gate_is_active)
        self.assertTrue(calls[-1].confirm_mainnet_delta_execution.startswith("LIVE_DELTA_EXECUTION:"))

    def test_blocks_non_all_or_none_topup_gate(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        gate = json.loads((plan_root / "capital_topup_gate.json").read_text(encoding="utf-8"))
        gate["require_balanced_all_or_none"] = False
        (plan_root / "capital_topup_gate.json").write_text(json.dumps(gate), encoding="utf-8")
        calls: list[Namespace] = []

        summary, exit_code = run_mainnet_multiphase_topup_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env={},
            delta_runner=_fake_delta_runner(calls, status="mainnet_delta_execution_ready"),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("topup_gate_not_all_or_none", summary["blockers"])
        self.assertEqual(calls, [])

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "topup-live.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  frozen_config_path: config/quant_research/binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json",
                    "binance:",
                    "  venue: usdm_futures",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    "  max_leverage: 2",
                    "capital:",
                    "  allocated_capital_usdt: 500.0",
                    "capital_topup:",
                    "  enabled: true",
                    "  reserve_available_balance_usdt: 150.0",
                    "  live_execution_enabled: true",
                    "risk:",
                    "  trading_enabled: false",
                    "  require_manual_live_confirm: true",
                    "  max_daily_realized_loss_enforcement: active",
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def _plan_artifact(self) -> Path:
        plan_root = self.temp_dir / "topup-plan"
        plan_root.mkdir(parents=True, exist_ok=True)
        run_summary = {
            "run_id": "topup-plan-1",
            "status": "mainnet_current_position_rebalance_plan_ready",
            "blockers": [],
            "target_engine": "multiphase_equal_sleeve",
            "capital_topup_requested": True,
            "capital_topup_gate_status": "passed",
            "current_position_aware": True,
            "plan_only": True,
            "mainnet_order_submission_authorized": False,
            "recurring_mainnet_enabled": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "risk_gate_status": "passed",
            "execution_plan_status": "ok",
            "active_execution_phase": "entry_second",
            "phase_counts": {"entry_second": 2},
            "deferred_phase_counts": {},
            "dust_delta_noop": False,
            "dust_delta_symbols": [],
            "dust_delta_blockers": [],
            "planned_delta_order_count": 2,
        }
        (plan_root / "run_summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
        (plan_root / "runtime_gate_context.json").write_text(
            json.dumps(
                {
                    "target_engine": "multiphase_equal_sleeve",
                    "current_position_aware": True,
                    "mainnet_order_submission_authorized": False,
                    "recurring_mainnet_authorized": False,
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "capital_allocation_context.json").write_text(
            json.dumps(
                {
                    "status": "capital_topup_resolved",
                    "baseline_allocated_capital_usdt": 500.0,
                    "resolved_allocated_capital_usdt": 1700.0,
                    "additional_allocated_capital_usdt": 1200.0,
                    "total_wallet_balance_usdt": 1000.0,
                    "reserve_available_balance_usdt": 150.0,
                    "sizing_multiplier": 2.0,
                    "gross_notional_safety_buffer_usdt": 0.0,
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "capital_topup_gate.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "require_balanced_all_or_none": True,
                    "active_execution_phase": "entry_second",
                    "planned_delta_order_count": 2,
                    "target_leg_count": 2,
                    "executable_entry_leg_count": 2,
                    "dust_leg_count": 0,
                    "reduce_like_row_count": 0,
                    "incomplete_entry_leg_count": 0,
                    "disallowed_row_count": 0,
                    "blockers": [],
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "margin_cushion_gate.json").write_text(
            json.dumps({"status": "passed", "passed": True, "blockers": [], "post_plan_available_balance_usdt": 200.0}),
            encoding="utf-8",
        )
        (plan_root / "execution_plan.json").write_text(
            json.dumps(
                {
                    "plan_id": "portfolio-1:plan:plan_only",
                    "portfolio_id": "portfolio-1",
                    "mode": "plan_only",
                    "status": "ok",
                    "blockers": [],
                    "active_execution_phase": "entry_second",
                    "phase_counts": {"entry_second": 2},
                    "deferred_phase_counts": {},
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "risk_gate.json").write_text(json.dumps({"decision": "allow_plan", "passed": True, "blockers": []}), encoding="utf-8")
        (plan_root / "target_portfolio.json").write_text(
            json.dumps({"portfolio_id": "portfolio-1", "allocated_capital_usdt": 1700.0, "status": "ok", "blockers": []}),
            encoding="utf-8",
        )
        intents = [
            {
                "intent_id": "intent-1",
                "portfolio_id": "portfolio-1",
                "symbol": "L1USDT",
                "side": "BUY",
                "position_side": "BOTH",
                "order_type": "MARKET",
                "quantity": 2.0,
                "reduce_only": False,
                "target_position_amt": 3.0,
                "current_position_amt": 1.0,
                "delta_position_amt": 2.0,
                "max_slippage_bps": 20.0,
                "client_order_id": "hvbal-pl-old-1",
                "execution_phase": "entry_second",
                "delta_classification": "increase_same_side",
                "final_target_position_amt": 3.0,
                "second_phase_required": False,
            },
            {
                "intent_id": "intent-2",
                "portfolio_id": "portfolio-1",
                "symbol": "S1USDT",
                "side": "SELL",
                "position_side": "BOTH",
                "order_type": "MARKET",
                "quantity": 2.0,
                "reduce_only": False,
                "target_position_amt": -3.0,
                "current_position_amt": -1.0,
                "delta_position_amt": -2.0,
                "max_slippage_bps": 20.0,
                "client_order_id": "hvbal-pl-old-2",
                "execution_phase": "entry_second",
                "delta_classification": "increase_same_side",
                "final_target_position_amt": -3.0,
                "second_phase_required": False,
            },
        ]
        pd.DataFrame(intents).to_csv(plan_root / "execution_plan.csv", index=False)
        pd.DataFrame(
            [
                {"symbol": "L1USDT", "rounded_notional_usdt": 200.0, "blockers": "", "execution_phase": "entry_second"},
                {"symbol": "S1USDT", "rounded_notional_usdt": 200.0, "blockers": "", "execution_phase": "entry_second"},
            ]
        ).to_csv(plan_root / "order_sizing_report.csv", index=False)
        pd.DataFrame(
            [
                {"symbol": "L1USDT", "positionAmt": 1.0, "markPrice": 100.0, "marginType": "cross", "leverage": "2"},
                {"symbol": "S1USDT", "positionAmt": -1.0, "markPrice": 100.0, "marginType": "cross", "leverage": "2"},
            ]
        ).to_csv(plan_root / "current_positions.csv", index=False)
        return plan_root


def _args(
    *,
    config_path: Path,
    plan_root: Path,
    execute: bool = False,
    enable: bool = False,
    understand: bool = False,
    daily_active_ack: bool = False,
    confirmation: str = "",
) -> Namespace:
    return Namespace(
        config=str(config_path),
        plan_artifact=str(plan_root),
        expected_reserve_usdt=150.0,
        allowed_delta_classifications="increase_same_side",
        execute_mainnet_topup_orders=execute,
        operator_enable_mainnet_topup_for_this_run=enable,
        i_understand_this_places_real_mainnet_topup_orders=understand,
        i_understand_daily_realized_pnl_gate_is_active=daily_active_ack,
        confirm_mainnet_topup_execution=confirmation,
        position_tolerance=1e-9,
        ignore_heartbeat_run_id="",
    )


def _fake_delta_runner(calls: list[Namespace], *, status: str):
    def _runner(args: Namespace, **_kwargs):
        calls.append(args)
        return (
            {
                "status": status,
                "blockers": [],
                "artifact_root": "/tmp/delta",
                "submitted_order_count": 2 if status == "mainnet_delta_orders_submitted" else 0,
                "fill_count": 2 if status == "mainnet_delta_orders_submitted" else 0,
            },
            0,
        )

    return _runner


def _fixed_now() -> datetime:
    return datetime(2026, 5, 23, 8, 0, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
