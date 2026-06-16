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

from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmResponse  # noqa: E402
from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256  # noqa: E402
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import (  # noqa: E402
    MULTIPHASE_TARGET_ENGINE,
    _maybe_allow_reduce_only_margin_gate_below_min,
    build_target_shadow_comparison,
    planned_additional_initial_margin_usdt,
    planned_additional_initial_margin_usdt_for_plan,
    run_mainnet_multiphase_current_position_rebalance_plan,
    run_mainnet_multiphase_target_shadow,
)
from enhengclaw.live_trading.models import ExecutionPlan, OrderIntent  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402


class HvBalancedMainnetMultiphaseTargetShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-multiphase-shadow-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_missing_credentials_blocks_before_clients_and_never_submits(self) -> None:
        config_path = self._config_path()

        def forbidden_client(**_kwargs):
            raise AssertionError("missing credentials should block before client construction")

        summary, exit_code = run_mainnet_multiphase_target_shadow(
            _args(config_path=config_path),
            env={},
            account_client_factory=forbidden_client,
            permission_client_factory=forbidden_client,
            market_client_factory=forbidden_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_api_key_env:LIVE_KEY", summary["blockers"])
        self.assertIn("missing_api_secret_env:LIVE_SECRET", summary["blockers"])
        self.assertTrue(summary["plan_only"])
        self.assertFalse(summary["mainnet_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        artifact_root = Path(summary["artifact_root"])
        self.assertTrue((artifact_root / "target_shadow_comparison.json").exists())

    def test_fixture_panel_builds_no_order_single_vs_multiphase_shadow(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_multiphase_target_shadow(
            _args(config_path=config_path, fixture_panel=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(summary["status"], {"passed", "passed_with_shadow_blockers"})
        self.assertTrue(summary["plan_only"])
        self.assertFalse(summary["mainnet_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertGreater(summary["comparison"]["target_symbol_union_count"], 0)
        artifact_root = Path(summary["artifact_root"])
        single_plan = json.loads((artifact_root / "single_phase" / "execution_plan.json").read_text(encoding="utf-8"))
        multi_plan = json.loads((artifact_root / "multiphase_aggregate" / "execution_plan.json").read_text(encoding="utf-8"))
        self.assertNotEqual(single_plan["mode"], "live")
        self.assertNotEqual(multi_plan["mode"], "live")
        self.assertEqual((artifact_root / "single_phase" / "submitted_orders.csv").read_text(encoding="utf-8").strip(), "")
        self.assertEqual((artifact_root / "multiphase_aggregate" / "fills.csv").read_text(encoding="utf-8").strip(), "")

    def test_fixture_panel_builds_reusable_multiphase_plan_and_persists_sleeves(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            summary["status"],
            {
                "mainnet_current_position_rebalance_plan_ready",
                "mainnet_current_position_rebalance_noop",
                "mainnet_current_position_rebalance_dust_noop",
            },
        )
        self.assertEqual(summary["target_engine"], MULTIPHASE_TARGET_ENGINE)
        self.assertTrue(summary["plan_only"])
        self.assertFalse(summary["mainnet_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["multiphase_sleeve_count"], 10)
        artifact_root = Path(summary["artifact_root"])
        decision = json.loads((artifact_root / "decision_snapshot.json").read_text(encoding="utf-8"))
        runtime = json.loads((artifact_root / "runtime_gate_context.json").read_text(encoding="utf-8"))
        sleeves = json.loads((artifact_root / "multiphase_sleeve_targets.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["status"], "ok")
        self.assertTrue(decision["rebalance_slot"])
        self.assertEqual(runtime["target_engine"], MULTIPHASE_TARGET_ENGINE)
        self.assertEqual(len(sleeves["sleeves"]), 10)
        rows = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_multiphase_sleeve_targets()
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row["target_engine"] == MULTIPHASE_TARGET_ENGINE for row in rows))

    def test_multiphase_plan_reuses_frozen_slot_quantity_when_prices_move(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        moved_panel_path = self.temp_dir / "panel_price_moved.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        moved = _fixture_panel()
        moved["perp_close"] = moved["perp_close"] * 1.25
        moved.to_csv(moved_panel_path, index=False)

        first, first_exit = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )
        first_root = Path(first["artifact_root"])
        first_sizing = pd.read_csv(first_root / "order_sizing_report.csv").set_index("symbol")
        second, second_exit = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=moved_panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now_later,
        )

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(first["rebalance_slot_id"], second["rebalance_slot_id"])
        self.assertEqual(first["rebalance_slot_target_hash"], second["rebalance_slot_target_hash"])
        self.assertIn("same_slot_candidate_target_drift_ignored_in_favor_of_frozen_snapshot", second["warnings"])
        second_root = Path(second["artifact_root"])
        second_sizing = pd.read_csv(second_root / "order_sizing_report.csv").set_index("symbol")
        symbol = str(first_sizing.index[0])
        self.assertAlmostEqual(
            float(first_sizing.loc[symbol, "target_position_amt"]),
            float(second_sizing.loc[symbol, "target_position_amt"]),
        )
        self.assertNotAlmostEqual(
            float(first_sizing.loc[symbol, "mark_price"]),
            float(second_sizing.loc[symbol, "mark_price"]),
        )
        self.assertTrue(bool(second_sizing.loc[symbol, "target_position_frozen"]))

    def test_completed_multiphase_slot_holds_until_next_rebalance_slot(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        moved_panel_path = self.temp_dir / "panel_price_moved.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        moved = _fixture_panel()
        moved["perp_close"] = moved["perp_close"] * 1.25
        moved.to_csv(moved_panel_path, index=False)

        first, first_exit = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )
        self.assertEqual(first_exit, 0)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        completed = store.mark_rebalance_slot_target_completed(
            slot_id=first["rebalance_slot_id"],
            run_id="unit-test-completion",
            artifact_root=first["artifact_root"],
            reason="cycle_executed_reconciled",
        )
        self.assertIsNotNone(completed)

        second, second_exit = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=moved_panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now_later,
        )

        self.assertEqual(second_exit, 0)
        self.assertEqual(second["status"], "mainnet_current_position_rebalance_hold_until_next_rebalance_slot")
        self.assertTrue(second["hold_until_next_rebalance_slot"])
        self.assertEqual(second["planned_delta_order_count"], 0)
        artifact_root = Path(second["artifact_root"])
        plan = json.loads((artifact_root / "execution_plan.json").read_text(encoding="utf-8"))
        slot_gate = json.loads((artifact_root / "frozen_slot_gate.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["status"], "hold_until_next_rebalance_slot")
        self.assertEqual(slot_gate["status"], "hold_until_next_rebalance_slot")

    def test_multiphase_capital_topup_resolves_wallet_scaled_capital_and_runs_gate(self) -> None:
        config_path = self._config_path(capital_topup=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertIn(exit_code, {0, 2})
        self.assertTrue(summary["capital_topup_requested"])
        self.assertAlmostEqual(summary["baseline_allocated_capital_usdt"], 500.0)
        self.assertAlmostEqual(summary["resolved_allocated_capital_usdt"], 2000.0)
        self.assertAlmostEqual(summary["additional_allocated_capital_usdt"], 1500.0)
        self.assertEqual(summary["capital_topup_gate_status"], "passed")
        artifact_root = Path(summary["artifact_root"])
        gate = json.loads((artifact_root / "capital_topup_gate.json").read_text(encoding="utf-8"))
        self.assertTrue(gate["require_balanced_all_or_none"])
        self.assertEqual(gate["target_engine"], MULTIPHASE_TARGET_ENGINE)

    def test_multiphase_primary_dynamic_capital_uses_wallet_minus_reserve_without_topup_flag(self) -> None:
        config_path = self._config_path(dynamic_primary=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path, capital_topup=False),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertIn(exit_code, {0, 2})
        self.assertFalse(summary["capital_topup_requested"])
        self.assertTrue(summary["capital_dynamic_requested"])
        self.assertAlmostEqual(summary["baseline_allocated_capital_usdt"], 500.0)
        self.assertAlmostEqual(summary["resolved_allocated_capital_usdt"], 1700.0)
        self.assertAlmostEqual(summary["additional_allocated_capital_usdt"], 1200.0)
        artifact_root = Path(summary["artifact_root"])
        capital_context = json.loads((artifact_root / "capital_allocation_context.json").read_text(encoding="utf-8"))
        self.assertEqual(capital_context["status"], "dynamic_config")
        self.assertEqual(capital_context["reserve_available_balance_usdt"], 150.0)

    def test_multiphase_primary_dynamic_capital_uses_target_safety_buffer(self) -> None:
        config_path = self._config_path(dynamic_primary=True, target_safety_buffer=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path, capital_topup=False),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertIn(exit_code, {0, 2})
        self.assertFalse(summary["capital_topup_requested"])
        self.assertTrue(summary["capital_dynamic_requested"])
        self.assertAlmostEqual(summary["baseline_allocated_capital_usdt"], 500.0)
        self.assertAlmostEqual(summary["resolved_allocated_capital_usdt"], 1300.0)
        self.assertAlmostEqual(summary["additional_allocated_capital_usdt"], 800.0)
        artifact_root = Path(summary["artifact_root"])
        capital_context = json.loads((artifact_root / "capital_allocation_context.json").read_text(encoding="utf-8"))
        self.assertEqual(capital_context["status"], "dynamic_config")
        self.assertEqual(capital_context["target_sizing_buffer_source"], "target_margin_safety_plus_operating_buffer")
        self.assertEqual(capital_context["target_margin_safety_buffer_usdt"], 300.0)
        self.assertEqual(capital_context["target_operating_buffer_usdt"], 50.0)
        self.assertEqual(capital_context["reserve_available_balance_usdt"], 350.0)

    def test_multiphase_dynamic_capital_can_truncate_to_margin_safe_plan(self) -> None:
        config_path = self._config_path(
            dynamic_primary=True,
            target_safety_buffer=True,
            margin_safe_truncation=True,
        )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_multiphase_current_position_rebalance_plan(
            _args(config_path=config_path, fixture_panel=panel_path, capital_topup=False),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(available_balance="120", total_wallet_balance="1000"),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_current_position_rebalance_plan_ready")
        self.assertLess(summary["resolved_allocated_capital_usdt"], 1300.0)
        self.assertGreater(summary["resolved_allocated_capital_usdt"], 0.0)
        artifact_root = Path(summary["artifact_root"])
        capital_context = json.loads((artifact_root / "capital_allocation_context.json").read_text(encoding="utf-8"))
        truncation = json.loads((artifact_root / "margin_safe_truncation.json").read_text(encoding="utf-8"))
        margin_gate = json.loads((artifact_root / "margin_cushion_gate.json").read_text(encoding="utf-8"))
        target_portfolio = json.loads((artifact_root / "target_portfolio.json").read_text(encoding="utf-8"))
        self.assertTrue(capital_context["margin_safe_truncation_applied"])
        self.assertTrue(truncation["applied"])
        self.assertEqual(truncation["status"], "applied")
        self.assertEqual(margin_gate["status"], "passed")
        self.assertEqual(margin_gate["blockers"], [])
        self.assertAlmostEqual(
            target_portfolio["allocated_capital_usdt"],
            summary["resolved_allocated_capital_usdt"],
            places=6,
        )
        rows = LiveTradingStateStore(self.temp_dir / "state.sqlite3").read_multiphase_sleeve_targets()
        self.assertEqual(len(rows), 10)

    def test_planned_margin_counts_only_executable_entry_second_orders(self) -> None:
        sizing = pd.DataFrame(
            [
                {
                    "symbol": "BTCUSDT",
                    "execution_phase": "entry_second",
                    "rounded_notional_usdt": 80.0,
                    "reduce_only": False,
                    "no_order_required": False,
                    "blockers": "",
                },
                {
                    "symbol": "ETHUSDT",
                    "execution_phase": "reduce_first",
                    "rounded_notional_usdt": 70.0,
                    "reduce_only": True,
                    "no_order_required": False,
                    "blockers": "",
                },
                {
                    "symbol": "SOLUSDT",
                    "execution_phase": "entry_second",
                    "rounded_notional_usdt": 60.0,
                    "reduce_only": False,
                    "no_order_required": False,
                    "blockers": "notional_below_min:SOLUSDT",
                },
                {
                    "symbol": "XRPUSDT",
                    "execution_phase": "dust_noop",
                    "rounded_notional_usdt": 10.0,
                    "reduce_only": False,
                    "no_order_required": False,
                    "blockers": "",
                },
            ]
        )

        margin = planned_additional_initial_margin_usdt(sizing, payload={"binance": {"max_leverage": 2}})

        self.assertAlmostEqual(margin, 40.0)

    def test_planned_margin_ignores_deferred_entry_second_when_active_plan_is_reduce_first(self) -> None:
        sizing = pd.DataFrame(
            [
                {
                    "symbol": "AAVEUSDT",
                    "execution_phase": "entry_second",
                    "rounded_notional_usdt": 2000.0,
                    "reduce_only": False,
                    "no_order_required": False,
                    "blockers": "",
                },
                {
                    "symbol": "TRXUSDT",
                    "execution_phase": "reduce_first",
                    "rounded_notional_usdt": 3000.0,
                    "reduce_only": True,
                    "no_order_required": False,
                    "blockers": "",
                },
            ]
        )
        plan = ExecutionPlan(
            plan_id="plan",
            portfolio_id="portfolio",
            mode="plan_only",
            status="ok",
            intents=[
                OrderIntent(
                    intent_id="reduce-trx",
                    portfolio_id="portfolio",
                    symbol="TRXUSDT",
                    side="SELL",
                    position_side="BOTH",
                    order_type="MARKET",
                    quantity=3000.0,
                    reduce_only=True,
                    target_position_amt=0.0,
                    current_position_amt=3000.0,
                    delta_position_amt=-3000.0,
                    max_slippage_bps=20.0,
                    client_order_id="reduce-trx",
                    execution_phase="reduce_first",
                )
            ],
            active_execution_phase="reduce_first",
            phase_counts={"entry_second": 1, "reduce_first": 1},
            deferred_phase_counts={"entry_second": 1},
        )

        margin = planned_additional_initial_margin_usdt_for_plan(
            sizing,
            plan=plan,
            payload={"binance": {"max_leverage": 2}},
        )

        self.assertEqual(margin, 0.0)

    def test_reduce_only_margin_floor_override_requires_explicit_risk_switch(self) -> None:
        plan = ExecutionPlan(
            plan_id="plan",
            portfolio_id="portfolio",
            mode="plan_only",
            status="ok",
            intents=[
                OrderIntent(
                    intent_id="reduce-trx",
                    portfolio_id="portfolio",
                    symbol="TRXUSDT",
                    side="SELL",
                    position_side="BOTH",
                    order_type="MARKET",
                    quantity=3000.0,
                    reduce_only=True,
                    target_position_amt=0.0,
                    current_position_amt=3000.0,
                    delta_position_amt=-3000.0,
                    max_slippage_bps=20.0,
                    client_order_id="reduce-trx",
                    execution_phase="reduce_first",
                )
            ],
            active_execution_phase="reduce_first",
        )
        blocked_gate = {
            "status": "blocked",
            "passed": False,
            "blockers": ["available_balance_ratio_below_min_after_plan:0.0499<0.05"],
            "warnings": [],
            "planned_additional_initial_margin_usdt": 0.0,
        }

        disabled_gate, disabled_pre = _maybe_allow_reduce_only_margin_gate_below_min(
            blocked_gate,
            plan=plan,
            payload={"risk": {}},
        )
        enabled_gate, enabled_pre = _maybe_allow_reduce_only_margin_gate_below_min(
            blocked_gate,
            plan=plan,
            payload={"risk": {"allow_reduce_only_plan_when_margin_below_min": True}},
        )

        self.assertEqual(disabled_gate["status"], "blocked")
        self.assertIsNone(disabled_pre)
        self.assertEqual(enabled_gate["status"], "passed")
        self.assertEqual(enabled_gate["blockers"], [])
        self.assertTrue(enabled_gate["reduce_only_margin_floor_override"])
        self.assertEqual(enabled_pre, blocked_gate)

    def test_target_shadow_comparison_reports_symbol_union_and_weight_difference(self) -> None:
        single_positions = pd.DataFrame(
            [
                {"usdm_symbol": "BTCUSDT", "target_weight": 0.30, "target_notional_usdt": 150.0},
                {"usdm_symbol": "ETHUSDT", "target_weight": -0.20, "target_notional_usdt": 100.0},
            ]
        )
        multiphase_positions = pd.DataFrame(
            [
                {"usdm_symbol": "BTCUSDT", "target_weight": 0.10, "target_notional_usdt": 50.0},
                {"usdm_symbol": "SOLUSDT", "target_weight": 0.05, "target_notional_usdt": 25.0},
            ]
        )
        single_sizing = pd.DataFrame([{"has_target": True, "executable": True, "no_order_required": False, "blockers": ""}])
        multi_sizing = pd.DataFrame([{"has_target": True, "executable": False, "no_order_required": False, "blockers": "notional_below_min:SOLUSDT"}])

        comparison = build_target_shadow_comparison(
            single_positions=single_positions,
            multiphase_positions=multiphase_positions,
            single_sizing=single_sizing,
            multiphase_sizing=multi_sizing,
            allocated_capital_usdt=500.0,
        )

        self.assertEqual(comparison["summary"]["target_symbol_union_count"], 3)
        self.assertAlmostEqual(comparison["summary"]["absolute_target_weight_difference_sum"], 0.45)
        self.assertAlmostEqual(comparison["summary"]["absolute_target_notional_difference_sum_usdt"], 225.0)
        by_symbol = comparison["by_symbol"].set_index("symbol")
        self.assertAlmostEqual(float(by_symbol.loc["BTCUSDT", "target_weight_delta_multiphase_minus_single"]), -0.20)
        self.assertAlmostEqual(float(by_symbol.loc["SOLUSDT", "target_weight_delta_multiphase_minus_single"]), 0.05)

    def _config_path(
        self,
        *,
        capital_topup: bool = False,
        dynamic_primary: bool = False,
        target_safety_buffer: bool = False,
        margin_safe_truncation: bool = False,
    ) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm_mainnet_shadow.yaml"
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
                    "binance:",
                    "  venue: usdm_futures",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    "  max_leverage: 2",
                    "capital:",
                    *(
                        [
                            "  sizing_basis: total_wallet_balance_usdt_x_2",
                            *(
                                [
                                    "  target_margin_safety_buffer_usdt: 300.0",
                                    "  target_operating_buffer_usdt: 50.0",
                                ]
                                if target_safety_buffer
                                else ["  reserve_available_balance_usdt: 150.0"]
                            ),
                            "  dynamic_risk_caps_from_resolved_capital: true",
                            "  max_symbol_weight_cap: 0.35",
                            "  max_order_weight_cap: 0.35",
                            *(
                                [
                                    "  auto_truncate_allocated_capital_to_margin_gate: true",
                                    "  margin_safe_truncation_tolerance_usdt: 0.5",
                                ]
                                if margin_safe_truncation
                                else []
                            ),
                        ]
                        if dynamic_primary
                        else []
                    ),
                    "  allocated_capital_usdt: 500.0",
                    "  max_gross_leverage: 2.0",
                    *(
                        [
                            "capital_topup:",
                            "  enabled: true",
                            "  sizing_basis: total_wallet_balance_usdt_x_2",
                            *(
                                [
                                    "  target_margin_safety_buffer_usdt: 300.0",
                                    "  target_operating_buffer_usdt: 50.0",
                                ]
                                if target_safety_buffer
                                else [f"  reserve_available_balance_usdt: {150.0 if dynamic_primary else 0.0}"]
                            ),
                            "  min_additional_allocated_capital_usdt: 25.0",
                            "  require_balanced_all_or_none: true",
                            "  enforce_all_or_none_for_dynamic_entries: true",
                            "  dynamic_risk_caps_from_resolved_capital: true",
                            "  max_symbol_weight_cap: 0.35",
                            "  max_order_weight_cap: 0.35",
                            "  allowed_delta_classifications: increase_same_side,new_entry,dust_residual,no_delta",
                            "  live_execution_enabled: false",
                        ]
                        if capital_topup or dynamic_primary
                        else []
                    ),
                    "risk:",
                    "  trading_enabled: false",
                    "  max_allocated_capital_usdt: 500.0",
                    "  max_gross_notional_usdt: 500.0",
                    "  max_symbol_notional_usdt: 100.0",
                    "  max_order_notional_usdt: 100.0",
                    "  min_available_balance_after_plan_usdt: 100.0",
                    "  min_available_balance_ratio_after_plan: 0.05",
                    "  min_margin_cushion_after_plan_usdt: 100.0",
                    "market_data:",
                    "  public_data_enabled: false",
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


def _args(*, config_path: Path, fixture_panel: Path | None = None, capital_topup: bool = False) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel="" if fixture_panel is None else str(fixture_panel),
        symbols="",
        public_market_data=False,
        api_key_env="",
        api_secret_env="",
        capital_topup=capital_topup,
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


def _fixed_now_later() -> datetime:
    return datetime(2026, 5, 22, 12, 1, 0, tzinfo=UTC)


class _FakePermissionClient:
    def api_key_restrictions(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "ipRestrict": True,
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": False,
                "enableMargin": True,
                "enableSpotAndMarginTrading": True,
                "permitsUniversalTransfer": True,
            },
        )


class _FakeAccountClient:
    def __init__(self, *, available_balance: str = "1000", total_wallet_balance: str = "1000") -> None:
        self.available_balance = str(available_balance)
        self.total_wallet_balance = str(total_wallet_balance)

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "canTrade": True,
                "availableBalance": self.available_balance,
                "totalWalletBalance": self.total_wallet_balance,
                "positions": [],
            },
        )

    def account_config(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"canTrade": True})

    def position_mode(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"dualSidePosition": False})

    def current_all_open_orders(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=[])

    def position_information_v2(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=[])

    def exchange_info(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"symbols": []})


def _forbidden_market_client(**_kwargs):
    raise AssertionError("fixture panel should not build public market data client")


def _fixture_panel() -> pd.DataFrame:
    rows = []
    subjects = ["L1", "L2", "L3", "S1", "S2", "S3"]
    for day in range(20):
        for index, subject in enumerate(subjects):
            base = 0.10 + index * 0.01
            rows.append(
                {
                    "timestamp_ms": day * 86_400_000,
                    "subject": subject,
                    "usdm_symbol": f"{subject}USDT",
                    "perp_close": 100.0 + day + index,
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


if __name__ == "__main__":
    unittest.main()
