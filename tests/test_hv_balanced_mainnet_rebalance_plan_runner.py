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
from enhengclaw.live_trading.mainnet_rebalance_plan_runner import run_mainnet_current_position_rebalance_plan  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402


class HvBalancedMainnetRebalancePlanRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-rebalance-plan-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_plan_uses_current_positions_for_delta_not_flat_assumption(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        current = {"L1USDT": 0.2, "S1USDT": -0.2}
        created: list[_FakeAccountClient] = []

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env=_env(),
            account_client_factory=_account_factory(created, positions=current),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(summary["status"], {"mainnet_current_position_rebalance_plan_ready", "mainnet_current_position_rebalance_noop"})
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertTrue(summary["current_position_aware"])
        artifact_root = Path(summary["artifact_root"])
        sizing = pd.read_csv(artifact_root / "order_sizing_report.csv")
        current_rows = sizing.loc[sizing["current_position_amt"].abs().gt(0)]
        self.assertFalse(current_rows.empty)
        for _, row in current_rows.iterrows():
            expected_delta = float(row["target_position_amt"]) - float(row["current_position_amt"])
            self.assertAlmostEqual(float(row["delta_position_amt"]), expected_delta, places=12)
            self.assertLess(abs(float(row["raw_abs_delta_qty"])), abs(float(row["target_position_amt"])) + 1e-12)
        self.assertEqual(created[0].submitted, [])
        runtime_gate = json.loads((artifact_root / "runtime_gate_context.json").read_text(encoding="utf-8"))
        self.assertFalse(runtime_gate["mainnet_order_submission_authorized"])

    def test_blocks_when_open_orders_exist_before_building_plan(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        created: list[_FakeAccountClient] = []

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env=_env(),
            account_client_factory=_account_factory(
                created,
                positions={"L1USDT": 0.2},
                open_orders=[{"symbol": "L1USDT", "orderId": 1}],
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("mainnet_open_orders_exist:1", summary["blockers"])
        self.assertFalse((Path(summary["artifact_root"]) / "target_positions.csv").read_text(encoding="utf-8").strip())

    def test_missing_credentials_never_builds_clients(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        def forbidden_client(**_kwargs):
            raise AssertionError("missing credentials should block before client construction")

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env={},
            account_client_factory=forbidden_client,
            permission_client_factory=forbidden_client,
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("missing_api_key_env:LIVE_KEY", summary["blockers"])
        self.assertIn("missing_api_secret_env:LIVE_SECRET", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_on_position_mode_mismatch(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions={"L1USDT": 0.2},
                hedge=True,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("position_mode_mismatch:expected=one_way:actual=hedge", summary["blockers"])

    def test_latest_closed_rebalance_slot_as_of_uses_prior_slot_when_latest_bar_is_not_slot(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel_with_latest_non_rebalance_bar().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, as_of="latest_closed_rebalance_slot"),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(positions={"L1USDT": 0.2, "S1USDT": -0.2}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(summary["status"], {"mainnet_current_position_rebalance_plan_ready", "mainnet_current_position_rebalance_noop"})
        self.assertNotIn("non_rebalance_slot", summary["blockers"])
        artifact_root = Path(summary["artifact_root"])
        context = json.loads((artifact_root / "decision_time_context.json").read_text(encoding="utf-8"))
        decision = json.loads((artifact_root / "decision_snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(context["resolved_as_of_mode"], "latest_closed_rebalance_slot")
        self.assertEqual(context["decision_time_ms"], 0)
        self.assertEqual(context["latest_available_timestamp_ms"], 86_400_000)
        self.assertTrue(decision["rebalance_slot"])
        self.assertEqual(decision["decision_time_ms"], 0)

    def test_plan_reuses_frozen_slot_quantity_when_prices_move(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        moved_panel_path = self.temp_dir / "panel_price_moved.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        moved = _fixture_panel()
        moved["perp_close"] = moved["perp_close"] * 1.25
        moved.to_csv(moved_panel_path, index=False)

        first, first_exit = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(positions={"L1USDT": 0.2, "S1USDT": -0.2}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )
        first_root = Path(first["artifact_root"])
        first_sizing = pd.read_csv(first_root / "order_sizing_report.csv").set_index("symbol")

        second, second_exit = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=moved_panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(positions={"L1USDT": 0.2, "S1USDT": -0.2}),
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

    def test_completed_frozen_slot_holds_until_next_rebalance_slot(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        moved_panel_path = self.temp_dir / "panel_price_moved.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        moved = _fixture_panel()
        moved["perp_close"] = moved["perp_close"] * 1.25
        moved.to_csv(moved_panel_path, index=False)

        first, first_exit = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(positions={"L1USDT": 0.2, "S1USDT": -0.2}),
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

        second, second_exit = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=moved_panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(positions={"L1USDT": 0.2, "S1USDT": -0.2}),
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

    def test_dust_residual_min_order_blockers_are_noop_not_hard_blocked(self) -> None:
        config_path = self._config_path()
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        current = {
            "L1USDT": 0.01,
            "L2USDT": 0.01,
            "L3USDT": 0.01,
            "S1USDT": -0.01,
            "S2USDT": -0.01,
            "S3USDT": -0.01,
        }

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions=current,
                min_qty=100.0,
                min_notional=10_000.0,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_current_position_rebalance_dust_noop")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["dust_delta_noop"])
        self.assertIn("dust_delta_noop:all_delta_orders_below_min_order_constraints", summary["warnings"])
        artifact_root = Path(summary["artifact_root"])
        execution_plan = json.loads((artifact_root / "execution_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(execution_plan["status"], "dust_noop")
        self.assertTrue(execution_plan["blockers"])
        self.assertEqual((artifact_root / "execution_plan.csv").read_text(encoding="utf-8").strip(), "")

    def test_capital_topup_resolves_wallet_scaled_capital_and_allows_entry_second_only(self) -> None:
        config_path = self._config_path(capital_topup=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions={},
                total_wallet_balance=1000.0,
                available_balance=1000.0,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_current_position_rebalance_plan_ready")
        self.assertTrue(summary["capital_topup_requested"])
        self.assertEqual(summary["capital_topup_gate_status"], "passed")
        self.assertAlmostEqual(summary["baseline_allocated_capital_usdt"], 500.0)
        self.assertAlmostEqual(summary["resolved_allocated_capital_usdt"], 1800.0)
        self.assertAlmostEqual(summary["additional_allocated_capital_usdt"], 1300.0)
        self.assertEqual(summary["reduce_only_intent_count"], 0)
        self.assertEqual(summary["active_execution_phase"], "entry_second")
        artifact_root = Path(summary["artifact_root"])
        target = json.loads((artifact_root / "target_portfolio.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(target["allocated_capital_usdt"], 1800.0)
        gate = json.loads((artifact_root / "capital_topup_gate.json").read_text(encoding="utf-8"))
        self.assertEqual(gate["status"], "passed")

    def test_capital_topup_target_sizing_buffer_reserves_margin_and_operating_cash(self) -> None:
        config_path = self._config_path(capital_topup=True, target_safety_buffer=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions={},
                total_wallet_balance=1000.0,
                available_balance=1000.0,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_current_position_rebalance_plan_ready")
        self.assertAlmostEqual(summary["baseline_allocated_capital_usdt"], 500.0)
        self.assertAlmostEqual(summary["resolved_allocated_capital_usdt"], 1300.0)
        self.assertAlmostEqual(summary["additional_allocated_capital_usdt"], 800.0)
        artifact_root = Path(summary["artifact_root"])
        context = json.loads((artifact_root / "capital_allocation_context.json").read_text(encoding="utf-8"))
        self.assertEqual(context["target_sizing_buffer_source"], "target_margin_safety_plus_operating_buffer")
        self.assertAlmostEqual(context["target_margin_safety_buffer_usdt"], 300.0)
        self.assertAlmostEqual(context["target_operating_buffer_usdt"], 50.0)
        self.assertAlmostEqual(context["reserve_available_balance_usdt"], 350.0)

    def test_capital_topup_blocks_reduce_flip_or_exit_rows(self) -> None:
        config_path = self._config_path(capital_topup=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        oversized_current = {
            "L1USDT": 100.0,
            "L2USDT": 100.0,
            "L3USDT": 100.0,
            "S1USDT": -100.0,
            "S2USDT": -100.0,
            "S3USDT": -100.0,
        }

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions=oversized_current,
                total_wallet_balance=1000.0,
                available_balance=1000.0,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["capital_topup_gate_status"], "blocked")
        self.assertTrue(any(item.startswith("capital_topup_disallows_reduce_flip_exit:") for item in summary["blockers"]))
        self.assertEqual(summary["orders_submitted"], 0)

    def test_capital_topup_blocks_mixed_executable_and_dust_legs(self) -> None:
        config_path = self._config_path(capital_topup=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        current = {
            "L1USDT": 1.0,
            "L2USDT": 1.0,
            "L3USDT": 1.0,
            "S1USDT": -1.0,
            "S2USDT": -1.0,
            "S3USDT": -1.0,
        }

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions=current,
                total_wallet_balance=1000.0,
                available_balance=1000.0,
                symbol_min_notional={"L1USDT": 1000.0},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["capital_topup_gate_status"], "blocked")
        self.assertTrue(any(item.startswith("capital_topup_all_or_none_dust_residual_leg:") for item in summary["blockers"]))
        self.assertEqual(summary["orders_submitted"], 0)
        gate = json.loads((Path(summary["artifact_root"]) / "capital_topup_gate.json").read_text(encoding="utf-8"))
        self.assertTrue(gate["require_balanced_all_or_none"])
        self.assertEqual(gate["dust_symbols"], ["L1USDT"])

    def test_capital_deployment_gate_defers_mixed_topup_without_hard_blocking(self) -> None:
        config_path = self._config_path(capital_topup=True, capital_deployment=True)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        current = {
            "L1USDT": 1.0,
            "L2USDT": 1.0,
            "L3USDT": 1.0,
            "S1USDT": -1.0,
            "S2USDT": -1.0,
            "S3USDT": -1.0,
        }

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions=current,
                total_wallet_balance=1000.0,
                available_balance=360.0,
                symbol_min_notional={"L1USDT": 1000.0},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_current_position_rebalance_deferred")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["capital_topup_gate_status"], "deferred")
        artifact_root = Path(summary["artifact_root"])
        gate = json.loads((artifact_root / "capital_topup_gate.json").read_text(encoding="utf-8"))
        self.assertTrue(gate["deferred"])
        self.assertEqual(gate["deployment_gate"]["status"], "deferred")
        self.assertIn("all_or_none_dust_residual_leg:L1USDT", gate["defer_reasons"])
        self.assertTrue(
            any(reason.startswith("planned_entry_initial_margin_exceeds_deployable_budget:") for reason in gate["defer_reasons"])
        )

    def test_capital_topup_can_accept_dust_noop_while_preserving_material_entries(self) -> None:
        config_path = self._config_path(
            capital_topup=True,
            capital_deployment=True,
            allow_dust_residual_noop_in_all_or_none=True,
            max_deploy_fraction_of_surplus=0.95,
            defer_if_all_or_none_has_dust_leg=False,
        )
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)
        current = {
            "L1USDT": 1.0,
            "L2USDT": 1.0,
            "L3USDT": 1.0,
            "S1USDT": -1.0,
            "S2USDT": -1.0,
            "S3USDT": -1.0,
        }

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions=current,
                total_wallet_balance=1000.0,
                available_balance=1000.0,
                symbol_min_notional={"L1USDT": 1000.0},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_current_position_rebalance_plan_ready")
        self.assertEqual(summary["capital_topup_gate_status"], "passed")
        self.assertEqual(summary["blockers"], [])
        gate = json.loads((Path(summary["artifact_root"]) / "capital_topup_gate.json").read_text(encoding="utf-8"))
        self.assertTrue(gate["require_balanced_all_or_none"])
        self.assertTrue(gate["allow_dust_residual_noop_in_all_or_none"])
        self.assertEqual(gate["dust_symbols"], ["L1USDT"])
        self.assertEqual(gate["deployment_gate"]["status"], "passed")

    def test_capital_topup_flag_requires_enabled_config(self) -> None:
        config_path = self._config_path(capital_topup=False)
        panel_path = self.temp_dir / "panel.csv"
        _fixture_panel().to_csv(panel_path, index=False)

        summary, exit_code = run_mainnet_current_position_rebalance_plan(
            _args(config_path=config_path, panel_path=panel_path, capital_topup=True),
            env=_env(),
            account_client_factory=lambda **_kwargs: _FakeAccountClient(
                positions={},
                total_wallet_balance=1000.0,
                available_balance=1000.0,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            market_client_factory=_forbidden_market_client,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["capital_topup_gate_status"], "blocked")
        self.assertIn("capital_topup_disabled_in_config", summary["blockers"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _config_path(
        self,
        *,
        venue: str = "usdm_futures",
        capital_topup: bool = False,
        capital_deployment: bool = False,
        target_safety_buffer: bool = False,
        allow_dust_residual_noop_in_all_or_none: bool = False,
        max_deploy_fraction_of_surplus: float = 0.8,
        defer_if_all_or_none_has_dust_leg: bool = True,
    ) -> Path:
        config_path = self.temp_dir / "hv_balanced_binance_usdm_mainnet.yaml"
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
                    f"  venue: {venue}",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    "  max_leverage: 2",
                    "capital:",
                    "  allocated_capital_usdt: 500.0",
                    "  sizing_basis: static_allocated_capital_usdt",
                    "  max_gross_leverage: 2.0",
                    "  max_symbol_notional_usdt: 100.0",
                    "  max_order_notional_usdt: 100.0",
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
                                else ["  reserve_available_balance_usdt: 100.0"]
                            ),
                            "  require_balanced_all_or_none: true",
                            *(
                                ["  allow_dust_residual_noop_in_all_or_none: true"]
                                if allow_dust_residual_noop_in_all_or_none
                                else []
                            ),
                            "  dynamic_risk_caps_from_resolved_capital: true",
                            "  max_symbol_weight_cap: 0.35",
                            "  max_order_weight_cap: 0.35",
                            "  allowed_delta_classifications: increase_same_side,new_entry,dust_residual,no_delta",
                        ]
                        if capital_topup
                        else []
                    ),
                    *(
                        [
                            "capital_deployment:",
                            "  enabled: true",
                            "  margin_safety_buffer_usdt: 300.0",
                            "  min_deployable_surplus_usdt: 50.0",
                            f"  max_deploy_fraction_of_surplus: {max_deploy_fraction_of_surplus}",
                            "  defer_if_post_plan_available_below_buffer: true",
                            f"  defer_if_all_or_none_has_dust_leg: {str(bool(defer_if_all_or_none_has_dust_leg)).lower()}",
                            "  defer_if_all_or_none_incomplete_entry: true",
                        ]
                        if capital_deployment
                        else []
                    ),
                    "risk:",
                    "  trading_enabled: false",
                    "  max_allocated_capital_usdt: 500.0",
                    "  max_gross_notional_usdt: 500.0",
                    "  max_symbol_notional_usdt: 100.0",
                    "  max_order_notional_usdt: 100.0",
                    "market_data:",
                    "  public_data_enabled: false",
                    "state:",
                    f"  artifact_root: {artifact_root}",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


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
    def __init__(
        self,
        *,
        positions: dict[str, float],
        open_orders: list[dict] | None = None,
        hedge: bool = False,
        margin_type: str = "cross",
        leverage: int = 2,
        min_qty: float = 0.001,
        min_notional: float = 0.0,
        symbol_min_notional: dict[str, float] | None = None,
        total_wallet_balance: float = 1000.0,
        available_balance: float = 1000.0,
        **_kwargs,
    ) -> None:
        self.positions = {symbol: float(amount) for symbol, amount in positions.items()}
        self.open_orders = list(open_orders or [])
        self.hedge = bool(hedge)
        self.margin_type = margin_type
        self.leverage = int(leverage)
        self.min_qty = float(min_qty)
        self.min_notional = float(min_notional)
        self.symbol_min_notional = {str(symbol): float(value) for symbol, value in dict(symbol_min_notional or {}).items()}
        self.total_wallet_balance = float(total_wallet_balance)
        self.available_balance = float(available_balance)
        self.submitted: list[dict] = []

    def account_information_v3(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "canTrade": True,
                "availableBalance": str(self.available_balance),
                "totalWalletBalance": str(self.total_wallet_balance),
                "positions": [
                    {
                        "symbol": symbol,
                        "positionSide": "BOTH",
                        "positionAmt": str(amount),
                        "entryPrice": "100",
                        "unrealizedProfit": "0",
                    }
                    for symbol, amount in sorted(self.positions.items())
                ],
            },
        )

    def account_config(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"canTrade": True})

    def position_mode(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"dualSidePosition": self.hedge})

    def current_all_open_orders(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=list(self.open_orders))

    def position_information_v2(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload=[
                {
                    "symbol": symbol,
                    "positionSide": "BOTH",
                    "positionAmt": str(amount),
                    "notional": str(amount * 100.0),
                    "entryPrice": "100",
                    "markPrice": "100",
                    "unRealizedProfit": "0",
                    "marginType": self.margin_type,
                    "leverage": str(self.leverage),
                    "isolated": self.margin_type == "isolated",
                }
                for symbol, amount in sorted(self.positions.items())
            ],
        )

    def exchange_info(self):
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbols": [
                    {
                        "symbol": symbol,
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                        "filters": [
                            {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": str(self.min_qty)},
                            {
                                "filterType": "MIN_NOTIONAL",
                                "notional": str(self.symbol_min_notional.get(symbol, self.min_notional)),
                            },
                        ],
                    }
                    for symbol in self.positions
                ]
            },
        )


def _account_factory(
    created: list[_FakeAccountClient],
    *,
    positions: dict[str, float],
    open_orders: list[dict] | None = None,
):
    def build(**kwargs) -> _FakeAccountClient:
        client = _FakeAccountClient(positions=positions, open_orders=open_orders, **kwargs)
        created.append(client)
        return client

    return build


def _args(*, config_path: Path, panel_path: Path, as_of: str = "now", capital_topup: bool = False) -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of=as_of,
        fixture_panel=str(panel_path),
        symbols="",
        public_market_data=False,
        api_key_env="",
        api_secret_env="",
        capital_topup=capital_topup,
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 15, 0, 0, tzinfo=UTC)


def _fixed_now_later() -> datetime:
    return datetime(2026, 5, 17, 15, 1, 0, tzinfo=UTC)


def _forbidden_market_client(**_kwargs):
    raise AssertionError("fixture panel should not build public market data client")


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


def _fixture_panel_with_latest_non_rebalance_bar() -> pd.DataFrame:
    first_slot = _fixture_panel()
    next_day = first_slot.copy()
    next_day["timestamp_ms"] = 86_400_000
    next_day["perp_close"] = pd.to_numeric(next_day["perp_close"], errors="coerce") * 1.01
    return pd.concat([first_slot, next_day], ignore_index=True)


class FrontierSidecarHourLookbackDefaultTests(unittest.TestCase):
    """The sidecar hourly lookback default must cover the full multiphase sleeve window so the
    intraday CoinGlass factor (coinglass_taker_imb_intraday_dispersion_24h) is decision-eligible at
    ALL 10 phase rows. The historical default (3) only covered ~2 days => 8/10 sleeves fail closed."""

    def test_default_covers_multiphase_sleeve_span_plus_24h_window(self) -> None:
        from enhengclaw.live_trading.mainnet_rebalance_plan_runner import (
            _MULTIPHASE_SLEEVE_SPAN_DAYS,
            _frontier_sidecar_args,
        )

        ns = _frontier_sidecar_args(Namespace(), {})
        # Must cover the 10 phase decision days + at least the trailing 24h dispersion window.
        self.assertGreaterEqual(ns.sidecar_hour_lookback_days, _MULTIPHASE_SLEEVE_SPAN_DAYS + 1)

    def test_sleeve_span_matches_multiphase_phase_count(self) -> None:
        from enhengclaw.live_trading.mainnet_rebalance_plan_runner import _MULTIPHASE_SLEEVE_SPAN_DAYS
        from enhengclaw.live_trading.mainnet_multiphase_target_shadow import PHASES

        # Guard against the constant drifting from the actual multiphase phase count.
        self.assertEqual(_MULTIPHASE_SLEEVE_SPAN_DAYS, len(PHASES))

    def test_config_override_is_honoured(self) -> None:
        from enhengclaw.live_trading.mainnet_rebalance_plan_runner import _frontier_sidecar_args

        payload = {"strategy": {"frontier": {"sidecar": {"sidecar_hour_lookback_days": 21}}}}
        ns = _frontier_sidecar_args(Namespace(), payload)
        self.assertEqual(ns.sidecar_hour_lookback_days, 21)

    def test_min_symbol_coverage_defaults_to_full_coverage_fail_closed(self) -> None:
        # #9: default must require ALL symbols so a silent partial CoinGlass fetch (e.g. 19/20 on a
        # timeout) BLOCKS the cycle instead of trading a degraded universe.
        from enhengclaw.live_trading.mainnet_rebalance_plan_runner import _frontier_sidecar_args

        self.assertEqual(_frontier_sidecar_args(Namespace(), {}).min_symbol_coverage, 1.0)

    def test_min_symbol_coverage_override_is_honoured_including_zero(self) -> None:
        from enhengclaw.live_trading.mainnet_rebalance_plan_runner import _frontier_sidecar_args

        for override in (0.5, 0.0):
            payload = {"strategy": {"frontier": {"sidecar": {"min_symbol_coverage": override}}}}
            self.assertEqual(_frontier_sidecar_args(Namespace(), payload).min_symbol_coverage, override)
