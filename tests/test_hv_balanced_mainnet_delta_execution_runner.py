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

from enhengclaw.live_trading.binance_usdm_client import (  # noqa: E402
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmResponse,
    BinanceUsdmUnknownExecutionStatus,
)
from enhengclaw.live_trading.hv_balanced_live_signal import file_sha256  # noqa: E402
from enhengclaw.live_trading.mainnet_delta_execution_runner import (  # noqa: E402
    _load_source_plan,
    _required_confirmation,
    run_mainnet_delta_execution,
)
from enhengclaw.live_trading.live_pit_universe import LIVE_UNIVERSE_ARTIFACT  # noqa: E402
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402


class HvBalancedMainnetDeltaExecutionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-delta-exec-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_dry_run_validates_current_position_aware_plan_without_submitting(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 1.0, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_execution_ready")
        self.assertEqual(summary["planned_delta_order_count"], 2)
        self.assertEqual(summary["execution_stage"], "entry_second")
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["required_confirmation"].startswith("LIVE_DELTA_EXECUTION:HV_BALANCED:MAINNET:PLAN_SHA256="))
        self.assertIn(":EXECUTION_STAGE=ENTRY_SECOND:", summary["required_confirmation"])
        self.assertEqual(created[0].submitted, [])
        artifact_root = Path(summary["artifact_root"])
        preflight = json.loads((artifact_root / "mainnet_delta_preflight.json").read_text(encoding="utf-8"))
        self.assertEqual(preflight["status"], "passed")
        self.assertEqual(preflight["execution_stage"], "entry_second")
        self.assertGreater(preflight["estimated_additional_initial_margin_usdt"], 0.0)

    def test_dry_run_reuses_source_reduce_only_margin_override(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(execution_stage="reduce_first")
        (plan_root / "margin_cushion_gate.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "passed": True,
                    "blockers": [],
                    "warnings": ["reduce_only_plan_allowed_below_margin_floor"],
                    "available_balance_usdt": 40.0,
                    "total_wallet_balance_usdt": 1000.0,
                    "planned_additional_initial_margin_usdt": 0.0,
                    "post_plan_available_balance_usdt": 40.0,
                    "post_plan_available_balance_ratio": 0.04,
                    "min_available_balance_ratio_after_plan": 0.05,
                    "reduce_only_margin_floor_override": True,
                    "reason": "active_plan_is_reduce_only_and_adds_no_initial_margin",
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "pre_reduce_only_margin_cushion_gate.json").write_text(
            json.dumps(
                {
                    "status": "blocked",
                    "passed": False,
                    "blockers": ["available_balance_ratio_below_min_after_plan:0.04<0.05"],
                    "available_balance_usdt": 40.0,
                    "total_wallet_balance_usdt": 1000.0,
                    "planned_additional_initial_margin_usdt": 0.0,
                    "post_plan_available_balance_ratio": 0.04,
                    "min_available_balance_ratio_after_plan": 0.05,
                }
            ),
            encoding="utf-8",
        )
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 3.0, "S1USDT": -3.0},
                available_balance=40.0,
                total_wallet_balance=1000.0,
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_execution_ready")
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(created[0].submitted, [])
        preflight = json.loads((Path(summary["artifact_root"]) / "mainnet_delta_preflight.json").read_text(encoding="utf-8"))
        self.assertEqual(preflight["status"], "passed")
        self.assertEqual(preflight["margin_cushion_gate_source"], "source_plan_artifact")
        self.assertTrue(preflight["margin_cushion_gate"]["reduce_only_margin_floor_override"])
        self.assertEqual(preflight["computed_delta_preflight_margin_cushion_gate"]["status"], "blocked")
        self.assertIn(
            "available_balance_ratio_below_min_after_plan:0.04<0.05",
            preflight["source_pre_reduce_only_margin_cushion_gate"]["blockers"],
        )

    def test_dry_run_blocks_new_entry_symbol_when_position_risk_leverage_exceeds_cap(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        intent_frame = pd.read_csv(plan_root / "execution_plan.csv")
        intent_frame["current_position_amt"] = 0.0
        intent_frame.loc[intent_frame["side"].astype(str).str.upper().eq("BUY"), "target_position_amt"] = 2.0
        intent_frame.loc[intent_frame["side"].astype(str).str.upper().eq("BUY"), "delta_position_amt"] = 2.0
        intent_frame.loc[intent_frame["side"].astype(str).str.upper().eq("SELL"), "target_position_amt"] = -2.0
        intent_frame.loc[intent_frame["side"].astype(str).str.upper().eq("SELL"), "delta_position_amt"] = -2.0
        intent_frame.to_csv(plan_root / "execution_plan.csv", index=False)
        pd.DataFrame(columns=["symbol", "positionAmt", "markPrice", "marginType", "leverage"]).to_csv(
            plan_root / "current_positions.csv",
            index=False,
        )
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("planned_symbol_leverage_above_max:L1USDT:max=2:actual=20", summary["blockers"])
        self.assertEqual(created[0].submitted, [])
        preparation = json.loads((Path(summary["artifact_root"]) / "account_setting_preparation.json").read_text(encoding="utf-8"))
        self.assertEqual(preparation["status"], "not_requested")
        self.assertEqual(created[0].leverage_changes, [])

    def test_auto_prepare_enabled_does_not_mutate_on_dry_run(self) -> None:
        config_path = self._config_path(auto_prepare=True)
        plan_root = self._plan_artifact()
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 1.0, "S1USDT": -1.0},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("planned_symbol_leverage_above_max:L1USDT:max=2:actual=20", summary["blockers"])
        self.assertEqual(created[0].leverage_changes, [])

    def test_explicit_prepare_mode_repairs_planned_symbol_without_submitting_orders(self) -> None:
        config_path = self._config_path(auto_prepare=True)
        plan_root = self._plan_artifact()
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                prepare_settings=True,
                enable_settings=True,
                understand_settings=True,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 1.0, "S1USDT": -1.0},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_execution_ready")
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["account_setting_preparation_status"], "prepared")
        self.assertEqual(summary["account_setting_call_count"], 1)
        self.assertEqual(created[0].leverage_changes, [{"symbol": "L1USDT", "leverage": 2}])

    def test_execute_auto_prepares_high_leverage_before_submitting(self) -> None:
        config_path = self._config_path(auto_prepare=True)
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 1.0, "S1USDT": -1.0},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(summary["account_setting_preparation_status"], "prepared")
        self.assertEqual(summary["account_setting_call_count"], 1)
        self.assertEqual(created[0].leverage_changes, [{"symbol": "L1USDT", "leverage": 2}])
        self.assertEqual(created[0].submitted[0]["symbol"], "L1USDT")
        preparation = json.loads((Path(summary["artifact_root"]) / "account_setting_preparation.json").read_text(encoding="utf-8"))
        self.assertEqual(preparation["status"], "prepared")
        self.assertEqual(preparation["actions"][0]["action"], "change_initial_leverage")

    def test_execute_auto_prepare_blocks_when_open_orders_exist(self) -> None:
        config_path = self._config_path(auto_prepare=True)
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 1.0, "S1USDT": -1.0},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2},
                open_orders=[{"symbol": "L1USDT", "orderId": 1, "clientOrderId": "existing"}],
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("account_setting_prepare_open_orders_exist:1", summary["blockers"])
        self.assertEqual(created[0].leverage_changes, [])

    def test_execute_auto_prepare_ignores_removed_daily_pnl_gate(self) -> None:
        config_path = self._config_path(daily_enforcement="active", auto_prepare=True)
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root, daily_pnl_gate_active=True)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_active_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 1.0, "S1USDT": -1.0},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2},
                income_rows=[
                    {"incomeType": "REALIZED_PNL", "income": "-20", "asset": "USDT", "time": 1770000000000},
                ],
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(summary["blockers"], [])
        self.assertEqual(summary["account_setting_preparation_status"], "prepared")
        self.assertEqual(created[0].leverage_changes, [{"symbol": "L1USDT", "leverage": 2}])
        daily_gate = json.loads((Path(summary["artifact_root"]) / "daily_realized_pnl_gate.json").read_text(encoding="utf-8"))
        self.assertEqual(daily_gate["status"], "removed")
        self.assertEqual(daily_gate["enforcement"], "disabled")

    def test_execute_auto_prepare_does_not_mutate_for_unplanned_leverage_blocker(self) -> None:
        config_path = self._config_path(auto_prepare=True)
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 1.0, "S1USDT": -1.0, "X1USDT": 1.0},
                leverage_by_symbol={"L1USDT": 20, "S1USDT": 2, "X1USDT": 20},
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "account_setting_prepare_blocked_by_account_snapshot:leverage_above_max:X1USDT:max=2:actual=20",
            summary["blockers"],
        )
        self.assertEqual(created[0].leverage_changes, [])

    def test_dry_run_accepts_dust_delta_plan_as_noop(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(dust_noop=True)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 0.09995}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_execution_noop")
        self.assertEqual(summary["execution_stage"], "dust_noop")
        self.assertEqual(summary["planned_delta_order_count"], 0)
        self.assertEqual(summary["submitted_order_count"], 0)
        self.assertEqual(created[0].submitted, [])

    def test_execute_requires_explicit_delta_flags_before_client_construction(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()

        def forbidden_client(**_kwargs):
            raise AssertionError("missing execution flags must block before signed order client construction")

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root, execute=True),
            env=_env(),
            mainnet_client_factory=forbidden_client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_operator_enable_mainnet_delta_for_this_run", summary["blockers"])
        self.assertIn("missing_mainnet_delta_order_understanding_flag", summary["blockers"])
        self.assertIn("missing_exact_mainnet_delta_confirmation", summary["blockers"])

    def test_execute_submits_delta_orders_and_reconciles(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 1.0, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(summary["submitted_order_count"], 2)
        self.assertEqual(summary["fill_count"], 2)
        self.assertEqual(summary["reconciliation_status"], "reconciled")
        self.assertEqual(summary["post_trade_reconcile_status"], "direct_delta_reconciled")
        self.assertFalse(summary["post_trade_reconcile"]["accepted_by_prior_live_submission_gate"])
        client = created[0]
        self.assertEqual(len(client.submitted), 2)
        self.assertEqual(client.positions["L1USDT"], 3.0)
        self.assertEqual(client.positions["S1USDT"], -3.0)
        self.assertTrue(all(str(order["newClientOrderId"]).startswith("hvbal-dl-") for order in client.submitted))
        self.assertTrue(all(order.get("reduceOnly") != "true" for order in client.submitted))

    def test_execute_blocks_on_underfilled_order_under_filled_status(self) -> None:
        # #1: a FILLED status with executedQty < origQty must be rejected, not silently accepted as
        # a full fill (which would corrupt the next cycle's delta baseline).
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)

        class _Underfill(_FakeDeltaClient):
            def submit_mainnet_strategy_delta_order(self, **params):
                resp = super().submit_mainnet_strategy_delta_order(**params)
                resp.payload["executedQty"] = str(float(params["quantity"]) * 0.5)
                return resp

        created: list[_FakeDeltaClient] = []

        def factory(**kwargs):
            client = _Underfill(positions={"L1USDT": 1.0, "S1USDT": -1.0}, **kwargs)
            created.append(client)
            return client

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root, execute=True, enable=True,
                  understand=True, daily_review_ack=True, confirmation=confirmation),
            env=_env(),
            mainnet_client_factory=factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertNotEqual(exit_code, 0)
        self.assertTrue(
            any(str(b).startswith("mainnet_delta_order_underfilled_under_filled_status") for b in summary["blockers"]),
            summary["blockers"],
        )
        self.assertEqual(summary["fill_count"], 0)

    def test_plan_hash_binds_decision_snapshot_provenance(self) -> None:
        # #3: tampering the decision snapshot must change plan_hash (and thus the confirmation token).
        plan_root = self._plan_artifact()
        snap = plan_root / "decision_snapshot.json"
        snap.write_text(json.dumps({"decision_id": "d1", "scores": [1.0, 2.0]}), encoding="utf-8")
        h1 = str(_load_source_plan(str(plan_root))["plan_hash"])
        snap.write_text(json.dumps({"decision_id": "d1", "scores": [9.0, 9.0]}), encoding="utf-8")
        h2 = str(_load_source_plan(str(plan_root))["plan_hash"])
        self.assertNotEqual(h1, h2)

    def test_execute_blocks_when_operator_disarms_during_preflight_window(self) -> None:
        # #4: an operator disarm issued AFTER the entry operator_state read but BEFORE submit (during
        # the account/leverage/preflight REST calls) must be caught by the pre-submit re-check.
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.record_operator_action(run_id="op-arm", action_type="arm-live-delta", reason="arm",
                                     created_at_utc="2026-05-17T15:59:00Z")

        class _DisarmMidRun(_FakeDeltaClient):
            def __init__(self, *, _store, **kwargs):
                super().__init__(**kwargs)
                self._store = _store
                self._fired = False

            def _maybe_disarm(self) -> None:
                if not self._fired:
                    self._fired = True
                    self._store.record_operator_action(run_id="op-mid", action_type="disarm-live-delta",
                                                        reason="mid-cycle disarm", created_at_utc="2026-05-17T15:59:30Z")

            def account_information_v3(self):
                self._maybe_disarm()
                return super().account_information_v3()

            def position_information_v2(self):
                self._maybe_disarm()
                return super().position_information_v2()

        created: list[_FakeDeltaClient] = []

        def factory(**kwargs):
            client = _DisarmMidRun(_store=store, positions={"L1USDT": 1.0, "S1USDT": -1.0}, **kwargs)
            created.append(client)
            return client

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root, execute=True, enable=True,
                  understand=True, daily_review_ack=True, confirmation=confirmation),
            env=_env(),
            mainnet_client_factory=factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertNotEqual(exit_code, 0)
        self.assertIn("operator_disarmed_before_submit", summary["blockers"])
        self.assertEqual(int(summary.get("submitted_order_count") or 0), 0)
        self.assertEqual(len(created[0].submitted), 0)

    def test_execute_fails_closed_when_resnapshot_after_leverage_change_raises(self) -> None:
        # #5: a transient REST failure on the account re-snapshot AFTER a leverage change must fail
        # closed with a blocker, not crash the runner with the account already modified.
        config_path = self._config_path(auto_prepare=True)
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)

        class _RaiseAfterLeverageChange(_FakeDeltaClient):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._lev_changed = False

            def change_initial_leverage(self, **kwargs):
                self._lev_changed = True
                return super().change_initial_leverage(**kwargs)

            def account_information_v3(self):
                if self._lev_changed:
                    raise RuntimeError("binance resnapshot timeout")
                return super().account_information_v3()

            def position_information_v2(self):
                if self._lev_changed:
                    raise RuntimeError("binance resnapshot timeout")
                return super().position_information_v2()

        created: list[_FakeDeltaClient] = []

        def factory(**kwargs):
            client = _RaiseAfterLeverageChange(positions={"L1USDT": 1.0, "S1USDT": -1.0},
                                               leverage_by_symbol={"L1USDT": 20, "S1USDT": 2}, **kwargs)
            created.append(client)
            return client

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root, execute=True, enable=True,
                  understand=True, daily_review_ack=True, confirmation=confirmation),
            env=_env(),
            mainnet_client_factory=factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertNotEqual(exit_code, 0)
        self.assertTrue(
            any(str(b).startswith("account_resnapshot_after_leverage_change_failed") for b in summary["blockers"]),
            summary["blockers"],
        )
        self.assertEqual(int(summary.get("submitted_order_count") or 0), 0)
        self.assertEqual(len(created[0].submitted), 0)

    def test_execute_blocks_when_concurrent_live_run_starts_before_submit(self) -> None:
        # #2: a concurrent live run that starts AFTER the entry health check but BEFORE submit must
        # be caught by the pre-submit re-check (active_run_in_progress), preventing a double-submit.
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        fresh = "2026-05-17T16:00:00Z"

        class _ForeignHeartbeatMidRun(_FakeDeltaClient):
            def __init__(self, *, _store, **kwargs):
                super().__init__(**kwargs)
                self._store = _store
                self._fired = False

            def _maybe(self) -> None:
                if not self._fired:
                    self._fired = True
                    self._store.write_heartbeat(run_id="other-live-run", mode="live", status="running",
                                                started_at_utc=fresh, updated_at_utc=fresh, artifact_root="x")

            def account_information_v3(self):
                self._maybe()
                return super().account_information_v3()

            def position_information_v2(self):
                self._maybe()
                return super().position_information_v2()

        created: list[_FakeDeltaClient] = []

        def factory(**kwargs):
            client = _ForeignHeartbeatMidRun(_store=store, positions={"L1USDT": 1.0, "S1USDT": -1.0}, **kwargs)
            created.append(client)
            return client

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root, execute=True, enable=True,
                  understand=True, daily_review_ack=True, confirmation=confirmation),
            env=_env(),
            mainnet_client_factory=factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertNotEqual(exit_code, 0)
        self.assertTrue(
            any(str(b).startswith("active_run_in_progress") for b in summary["blockers"]), summary["blockers"]
        )
        self.assertEqual(len(created[0].submitted), 0)

    def test_reduce_first_confirmation_is_stage_aware_and_reduce_only(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(execution_stage="reduce_first")
        confirmation = _confirmation(plan_root)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 3.0, "S1USDT": -3.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(summary["execution_stage"], "reduce_first")
        self.assertIn(":EXECUTION_STAGE=REDUCE_FIRST:", summary["required_confirmation"])
        self.assertEqual(created[0].positions["L1USDT"], 1.0)
        self.assertEqual(created[0].positions["S1USDT"], -1.0)
        self.assertTrue(all(order["reduceOnly"] == "true" for order in created[0].submitted))

    def test_removed_daily_pnl_gate_does_not_affect_reduce_first_execution(self) -> None:
        config_path = self._config_path(daily_enforcement="active", auto_prepare=True)
        plan_root = self._plan_artifact(execution_stage="reduce_first")
        confirmation = _confirmation(plan_root, daily_pnl_gate_active=True)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_active_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(
                created,
                positions={"L1USDT": 3.0, "S1USDT": -3.0},
                income_rows=[
                    {"incomeType": "REALIZED_PNL", "income": "-20", "asset": "USDT", "time": 1770000000000},
                ],
            ),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(summary["submitted_order_count"], 2)
        self.assertTrue(all(order["reduceOnly"] == "true" for order in created[0].submitted))
        daily_gate = json.loads((Path(summary["artifact_root"]) / "daily_realized_pnl_gate.json").read_text(encoding="utf-8"))
        self.assertEqual(daily_gate["status"], "removed")
        self.assertFalse((Path(summary["artifact_root"]) / "daily_pnl_delta_policy.json").exists())

    def test_execute_rejects_confirmation_for_wrong_execution_stage(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(execution_stage="entry_second")
        source = _load_source_plan(str(plan_root))
        wrong_confirmation = _required_confirmation(
            plan_hash=str(source["plan_hash"]),
            execution_stage="reduce_first",
        )

        def forbidden_client(**_kwargs):
            raise AssertionError("wrong stage confirmation must block before signed client construction")

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=wrong_confirmation,
            ),
            env=_env(),
            mainnet_client_factory=forbidden_client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("missing_exact_mainnet_delta_confirmation", summary["blockers"])

    def test_blocks_source_plan_with_mixed_execution_phases_before_client_construction(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(mixed_phases=True)

        def forbidden_client(**_kwargs):
            raise AssertionError("mixed stage source plan must block before signed client construction")

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=forbidden_client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("source_plan_mixed_execution_phases:entry_second,reduce_first", summary["blockers"])

    def test_blocks_source_plan_missing_execution_phase_before_client_construction(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(missing_phase=True)

        def forbidden_client(**_kwargs):
            raise AssertionError("missing stage source plan must block before signed client construction")

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=forbidden_client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("source_plan_missing_active_execution_phase", summary["blockers"])
        self.assertTrue(any(item.startswith("source_plan_missing_row_execution_phase:") for item in summary["blockers"]))

    def test_active_daily_pnl_config_is_inert_for_confirmation_and_ack(self) -> None:
        config_path = self._config_path(daily_enforcement="active")
        plan_root = self._plan_artifact()
        legacy_confirmation = _confirmation(plan_root)
        confirmation = _confirmation(plan_root, daily_pnl_gate_active=True)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=legacy_confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 1.0, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(summary["required_confirmation"], legacy_confirmation)
        self.assertEqual(confirmation, legacy_confirmation)
        self.assertIn("NO_DAILY_PNL_GATE", confirmation)
        self.assertNotIn("DAILY_PNL_GATE_ACTIVE", confirmation)

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_active_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 1.0, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        daily_gate = json.loads((Path(summary["artifact_root"]) / "daily_realized_pnl_gate.json").read_text(encoding="utf-8"))
        self.assertEqual(daily_gate["status"], "removed")
        self.assertEqual(daily_gate["enforcement"], "disabled")

    def test_execute_blocks_when_live_position_drifted_from_source_plan(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 1.1, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertTrue(any(item.startswith("position_drift:L1USDT:") for item in summary["blockers"]))
        self.assertEqual(created[0].submitted, [])

    def test_unknown_status_recovery_stops_without_duplicate_delta_submit(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        created: list[_UnknownStatusDeltaClient] = []

        def client_factory(**_kwargs):
            client = _UnknownStatusDeltaClient(positions={"L1USDT": 1.0, "S1USDT": -1.0})
            created.append(client)
            return client

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=client_factory,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "mainnet_delta_reconcile_required")
        self.assertEqual(len(created[0].submitted), 1)
        self.assertEqual(created[0].query_count, 1)
        execution = json.loads((Path(summary["artifact_root"]) / "mainnet_delta_execution.json").read_text(encoding="utf-8"))
        self.assertEqual(execution["recoveries"][0]["status"], "resolved")
        self.assertTrue(execution["blockers"][0].startswith("unknown_order_status_recovered_stop_for_reconcile:"))

    def test_blocks_source_plan_that_is_not_current_position_aware(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact(current_position_aware=False)

        def forbidden_client(**_kwargs):
            raise AssertionError("invalid source plan must block before client construction")

        summary, exit_code = run_mainnet_delta_execution(
            _args(config_path=config_path, plan_root=plan_root),
            env=_env(),
            mainnet_client_factory=forbidden_client,
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("source_plan_not_current_position_aware", summary["blockers"])

    def test_delta_preflight_can_ignore_multiple_parent_heartbeats(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        for run_id in ("supervisor-parent", "core-loop-parent"):
            store.write_heartbeat(
                run_id=run_id,
                mode="live",
                status="running",
                started_at_utc="2026-05-17T16:00:00Z",
                updated_at_utc="2026-05-17T16:00:00Z",
            )

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                ignore_heartbeat_run_id="core-loop-parent,supervisor-parent",
            ),
            env=_env(),
            mainnet_client_factory=_client_factory([], positions={"L1USDT": 1.0, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_execution_ready")
        self.assertNotIn("active_run_in_progress:core-loop-parent", summary["blockers"])
        self.assertNotIn("active_run_in_progress:supervisor-parent", summary["blockers"])

    def test_execute_ignores_concurrent_daily_policy_orchestrator_heartbeat(self) -> None:
        config_path = self._config_path()
        plan_root = self._plan_artifact()
        confirmation = _confirmation(plan_root)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.write_heartbeat(
            run_id="daily-policy-running",
            mode="unattended_daily_policy",
            status="running",
            started_at_utc="2026-05-17T16:00:00Z",
            updated_at_utc="2026-05-17T16:00:00Z",
            artifact_root=str(self.temp_dir / "daily-policy"),
        )
        created: list[_FakeDeltaClient] = []

        summary, exit_code = run_mainnet_delta_execution(
            _args(
                config_path=config_path,
                plan_root=plan_root,
                execute=True,
                enable=True,
                understand=True,
                daily_review_ack=True,
                confirmation=confirmation,
            ),
            env=_env(),
            mainnet_client_factory=_client_factory(created, positions={"L1USDT": 1.0, "S1USDT": -1.0}),
            permission_client_factory=lambda **_kwargs: _FakePermissionClient(),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_delta_orders_submitted")
        self.assertEqual(len(created[0].submitted), 2)
        self.assertNotIn("active_run_in_progress:daily-policy-running", summary["blockers"])
        local_state = json.loads((Path(summary["artifact_root"]) / "local_state_health.json").read_text(encoding="utf-8"))
        self.assertEqual(local_state["ignored_orchestrator_run_ids"], ["daily-policy-running"])
        self.assertTrue(local_state["running_heartbeats"][0]["ignored_for_delta_execution"])
        self.assertFalse((Path(summary["artifact_root"]) / "pre_submit_revalidation.json").exists())

    def _config_path(self, *, daily_enforcement: str = "review_only_not_active", auto_prepare: bool = False) -> Path:
        config_path = self.temp_dir / "hv_balanced_delta.yaml"
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
                    "binance:",
                    "  venue: usdm_futures",
                    "  api_key_env: LIVE_KEY",
                    "  api_secret_env: LIVE_SECRET",
                    "  recv_window_ms: 5000",
                    "  position_mode: one_way",
                    "  margin_type: cross",
                    "  max_leverage: 2",
                    f"  auto_prepare_planned_symbol_settings: {str(bool(auto_prepare)).lower()}",
                    "capital:",
                    "  allocated_capital_usdt: 300.0",
                    "  max_symbol_notional_usdt: 200.0",
                    "  max_order_notional_usdt: 200.0",
                    "risk:",
                    "  trading_enabled: false",
                    "  require_manual_live_confirm: true",
                    "  max_allocated_capital_usdt: 300.0",
                    "  max_gross_notional_usdt: 300.0",
                    "  max_symbol_notional_usdt: 200.0",
                    "  max_order_notional_usdt: 200.0",
                    "  max_daily_realized_loss_usdt: 10.0",
                    f"  max_daily_realized_loss_enforcement: {daily_enforcement}",
                    "  min_available_balance_ratio_after_plan: 0.05",
                    "  min_margin_cushion_after_plan_usdt: 100.0",
                    "  daily_realized_pnl_income_types: REALIZED_PNL,COMMISSION,FUNDING_FEE",
                    "market_data:",
                    "  public_data_enabled: false",
                    "state:",
                    f"  sqlite_path: {sqlite_path}",
                    f"  artifact_root: {artifact_root}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path

    def test_live_universe_is_bound_into_plan_hash(self) -> None:
        # A fixed-universe / frontier-off plan has no live_universe.json => its plan_hash is
        # byte-for-byte unchanged (the artifact is skipped when absent). Writing a PIT universe
        # record into the plan binds it: the hash changes, and tampering with the record changes
        # it again => the operator confirmation token refuses a drifted universe at submit.
        plan_root = self._plan_artifact(execution_stage="entry_second")
        baseline_hash = str(_load_source_plan(str(plan_root))["plan_hash"])

        (plan_root / LIVE_UNIVERSE_ARTIFACT).write_text(
            json.dumps({"status": "ok", "active_symbols": ["AUSDT", "BUSDT"], "universe_binding": "sha-1"}),
            encoding="utf-8",
        )
        bound_hash = str(_load_source_plan(str(plan_root))["plan_hash"])
        self.assertNotEqual(baseline_hash, bound_hash)  # universe now contributes to plan_hash

        (plan_root / LIVE_UNIVERSE_ARTIFACT).write_text(
            json.dumps({"status": "ok", "active_symbols": ["AUSDT", "CUSDT"], "universe_binding": "sha-2"}),
            encoding="utf-8",
        )
        drifted_hash = str(_load_source_plan(str(plan_root))["plan_hash"])
        self.assertNotEqual(bound_hash, drifted_hash)  # tampering / drift is tamper-evident

    def _plan_artifact(
        self,
        *,
        current_position_aware: bool = True,
        dust_noop: bool = False,
        execution_stage: str = "entry_second",
        mixed_phases: bool = False,
        missing_phase: bool = False,
    ) -> Path:
        plan_root = self.temp_dir / f"plan-{current_position_aware}-{dust_noop}-{execution_stage}-{mixed_phases}-{missing_phase}"
        plan_root.mkdir(parents=True, exist_ok=True)
        active_execution_phase = (
            "dust_noop"
            if dust_noop
            else "" if missing_phase else "reduce_first" if mixed_phases else str(execution_stage)
        )
        phase_counts = (
            {"dust_noop": 1}
            if dust_noop
            else {} if missing_phase else {"reduce_first": 1, "entry_second": 1} if mixed_phases else {str(execution_stage): 2}
        )
        run_summary = {
            "run_id": "source-plan-1",
            "status": "mainnet_current_position_rebalance_dust_noop" if dust_noop else "mainnet_current_position_rebalance_plan_ready",
            "blockers": [],
            "current_position_aware": current_position_aware,
            "plan_only": True,
            "mainnet_order_submission_authorized": False,
            "recurring_mainnet_enabled": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "risk_gate_status": "passed",
            "execution_plan_status": "dust_noop" if dust_noop else "ok",
            "active_execution_phase": active_execution_phase,
            "phase_counts": phase_counts,
            "deferred_phase_counts": {},
            "dust_delta_noop": dust_noop,
            "dust_delta_symbols": ["L1USDT"] if dust_noop else [],
            "dust_delta_blockers": ["quantity_below_min:L1USDT", "notional_below_min:L1USDT"] if dust_noop else [],
        }
        (plan_root / "run_summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
        (plan_root / "runtime_gate_context.json").write_text(
            json.dumps(
                {
                    "current_position_aware": current_position_aware,
                    "mainnet_order_submission_authorized": False,
                    "recurring_mainnet_authorized": False,
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "execution_plan.json").write_text(
            json.dumps(
                {
                    "plan_id": "portfolio-1:plan:plan_only",
                    "portfolio_id": "portfolio-1",
                    "mode": "plan_only",
                    "status": "dust_noop" if dust_noop else "ok",
                    "blockers": ["quantity_below_min:L1USDT", "notional_below_min:L1USDT"] if dust_noop else [],
                    "active_execution_phase": active_execution_phase,
                    "phase_counts": phase_counts,
                    "deferred_phase_counts": {},
                }
            ),
            encoding="utf-8",
        )
        (plan_root / "risk_gate.json").write_text(
            json.dumps({"decision": "allow_plan", "passed": True, "blockers": []}),
            encoding="utf-8",
        )
        (plan_root / "target_portfolio.json").write_text(
            json.dumps({"portfolio_id": "portfolio-1", "allocated_capital_usdt": 300.0, "status": "ok", "blockers": []}),
            encoding="utf-8",
        )
        intent_rows = []
        if not dust_noop:
            if str(execution_stage) == "reduce_first" or mixed_phases:
                intent_rows.append(
                    {
                        "intent_id": "intent-1",
                        "portfolio_id": "portfolio-1",
                        "symbol": "L1USDT",
                        "side": "SELL",
                        "position_side": "BOTH",
                        "order_type": "MARKET",
                        "quantity": 2.0,
                        "reduce_only": True,
                        "target_position_amt": 1.0,
                        "current_position_amt": 3.0,
                        "delta_position_amt": -2.0,
                        "max_slippage_bps": 20.0,
                        "client_order_id": "hvbal-pl-old-1",
                        "execution_phase": "reduce_first",
                        "delta_classification": "reduce_same_side",
                        "final_target_position_amt": 1.0,
                        "second_phase_required": False,
                    }
                )
            else:
                intent_rows.append(
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
                    }
                )
            if str(execution_stage) == "reduce_first" and not mixed_phases:
                intent_rows.append(
                    {
                        "intent_id": "intent-2",
                        "portfolio_id": "portfolio-1",
                        "symbol": "S1USDT",
                        "side": "BUY",
                        "position_side": "BOTH",
                        "order_type": "MARKET",
                        "quantity": 2.0,
                        "reduce_only": True,
                        "target_position_amt": -1.0,
                        "current_position_amt": -3.0,
                        "delta_position_amt": 2.0,
                        "max_slippage_bps": 20.0,
                        "client_order_id": "hvbal-pl-old-2",
                        "execution_phase": "reduce_first",
                        "delta_classification": "reduce_same_side",
                        "final_target_position_amt": -1.0,
                        "second_phase_required": False,
                    }
                )
            else:
                intent_rows.append(
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
                    }
                )
            if missing_phase:
                for row in intent_rows:
                    row.pop("execution_phase", None)
        pd.DataFrame(intent_rows).to_csv(plan_root / "execution_plan.csv", index=False)
        sizing_rows = (
            [
                {
                    "symbol": "L1USDT",
                    "no_order_required": False,
                    "current_position_amt": 0.09995,
                    "target_position_amt": 0.1,
                    "delta_position_amt": 0.00005,
                    "rounded_notional_usdt": 0.0,
                    "blockers": "notional_below_min:L1USDT;quantity_below_min:L1USDT",
                    "execution_phase": "dust_noop",
                }
            ]
            if dust_noop
            else [
                {
                    "symbol": row["symbol"],
                    "rounded_notional_usdt": 200.0,
                    "blockers": "",
                    "execution_phase": row.get("execution_phase", ""),
                }
                for row in intent_rows
            ]
        )
        pd.DataFrame(sizing_rows).to_csv(plan_root / "order_sizing_report.csv", index=False)
        current_rows = (
            [{"symbol": "L1USDT", "positionAmt": 0.09995, "markPrice": 100.0, "marginType": "cross", "leverage": "2"}]
            if dust_noop
            else [
                {"symbol": "L1USDT", "positionAmt": 3.0, "markPrice": 100.0, "marginType": "cross", "leverage": "2"},
                {"symbol": "S1USDT", "positionAmt": -3.0, "markPrice": 100.0, "marginType": "cross", "leverage": "2"},
            ]
            if str(execution_stage) == "reduce_first" and not mixed_phases
            else [
                {"symbol": "L1USDT", "positionAmt": 1.0, "markPrice": 100.0, "marginType": "cross", "leverage": "2"},
                {"symbol": "S1USDT", "positionAmt": -1.0, "markPrice": 100.0, "marginType": "cross", "leverage": "2"},
            ]
        )
        pd.DataFrame(current_rows).to_csv(plan_root / "current_positions.csv", index=False)
        return plan_root


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


class _FakeDeltaClient:
    def __init__(
        self,
        *,
        positions: dict[str, float],
        open_orders: list[dict] | None = None,
        margin_type: str = "cross",
        leverage: int = 2,
        leverage_by_symbol: dict[str, int] | None = None,
        available_balance: float = 1000.0,
        total_wallet_balance: float = 1000.0,
        income_rows: list[dict] | None = None,
        **_kwargs,
    ) -> None:
        self.positions = {symbol: float(amount) for symbol, amount in positions.items()}
        self.open_orders = list(open_orders or [])
        self.margin_type = margin_type
        self.leverage = int(leverage)
        self.leverage_by_symbol = {str(symbol): int(value) for symbol, value in dict(leverage_by_symbol or {}).items()}
        self.submitted: list[dict] = []
        self.leverage_changes: list[dict] = []
        self.margin_type_changes: list[dict] = []
        self.available_balance = float(available_balance)
        self.total_wallet_balance = float(total_wallet_balance)
        self.income_rows = list(income_rows or [])

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
        return BinanceUsdmResponse(status_code=200, headers={}, payload={"dualSidePosition": False})

    def current_all_open_orders(self):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=list(self.open_orders))

    def position_information_v2(self):
        symbols = sorted({"L1USDT", "S1USDT", *self.positions})
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload=[
                {
                    "symbol": symbol,
                    "positionSide": "BOTH",
                    "positionAmt": str(self.positions.get(symbol, 0.0)),
                    "notional": str(self.positions.get(symbol, 0.0) * 100.0),
                    "entryPrice": "100",
                    "markPrice": "100",
                    "unRealizedProfit": "0",
                    "marginType": self.margin_type,
                    "leverage": str(self.leverage_by_symbol.get(symbol, self.leverage)),
                    "isolated": self.margin_type == "isolated",
                }
                for symbol in symbols
            ],
        )

    def income_history(self, **_kwargs):
        return BinanceUsdmResponse(status_code=200, headers={}, payload=list(self.income_rows))

    def submit_mainnet_strategy_delta_order(self, **params):
        self.submitted.append(dict(params))
        quantity = float(params["quantity"])
        signed = quantity if str(params["side"]).upper() == "BUY" else -quantity
        symbol = str(params["symbol"])
        self.positions[symbol] = round(self.positions.get(symbol, 0.0) + signed, 12)
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": params["newClientOrderId"],
                "orderId": 90_000 + len(self.submitted),
                "status": "FILLED",
                "side": params["side"],
                "type": params["type"],
                "positionSide": params["positionSide"],
                "reduceOnly": params.get("reduceOnly") == "true",
                "origQty": params["quantity"],
                "executedQty": params["quantity"],
                "avgPrice": "100",
                "updateTime": 1770000000000,
            },
        )

    def change_initial_leverage(self, *, symbol: str, leverage: int):
        self.leverage_by_symbol[str(symbol)] = int(leverage)
        self.leverage_changes.append({"symbol": str(symbol), "leverage": int(leverage)})
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={"symbol": str(symbol), "leverage": int(leverage), "maxNotionalValue": "1000000"},
        )

    def change_margin_type(self, *, symbol: str, margin_type: str):
        self.margin_type = "cross" if str(margin_type).upper() == "CROSSED" else "isolated"
        self.margin_type_changes.append({"symbol": str(symbol), "marginType": str(margin_type)})
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={"code": 200, "msg": "success"},
        )

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        params = next(item for item in self.submitted if item["newClientOrderId"] == orig_client_order_id)
        return BinanceUsdmResponse(
            status_code=200,
            headers={},
            payload={
                "symbol": symbol,
                "clientOrderId": orig_client_order_id,
                "orderId": 91_001,
                "status": "FILLED",
                "side": params["side"],
                "type": params["type"],
                "positionSide": params["positionSide"],
                "reduceOnly": params.get("reduceOnly") == "true",
                "origQty": params["quantity"],
                "executedQty": params["quantity"],
                "avgPrice": "100",
                "updateTime": 1770000000000,
            },
        )


class _UnknownStatusDeltaClient(_FakeDeltaClient):
    def __init__(self, *, positions: dict[str, float]) -> None:
        super().__init__(positions=positions)
        self.query_count = 0

    def submit_mainnet_strategy_delta_order(self, **params):
        self.submitted.append(dict(params))
        raise BinanceUsdmUnknownExecutionStatus(
            method="POST",
            path="/fapi/v1/order",
            detail='{"code":-1000,"msg":"Unknown error, please check your request or try again later."}',
        )

    def query_order(self, *, symbol: str, orig_client_order_id: str):
        self.query_count += 1
        return super().query_order(symbol=symbol, orig_client_order_id=orig_client_order_id)


def _client_factory(
    created: list[_FakeDeltaClient],
    *,
    positions: dict[str, float],
    leverage_by_symbol: dict[str, int] | None = None,
    **client_kwargs,
):
    def build(**kwargs) -> _FakeDeltaClient:
        self_url = kwargs.get("base_url")
        if self_url is not None:
            assert self_url == BINANCE_USDM_MAINNET_BASE_URL
        client = _FakeDeltaClient(positions=positions, leverage_by_symbol=leverage_by_symbol, **client_kwargs, **kwargs)
        created.append(client)
        return client

    return build


def _args(
    *,
    config_path: Path,
    plan_root: Path,
    execute: bool = False,
    enable: bool = False,
    understand: bool = False,
    daily_review_ack: bool = False,
    daily_active_ack: bool = False,
    prepare_settings: bool = False,
    enable_settings: bool = False,
    understand_settings: bool = False,
    confirmation: str = "",
    ignore_heartbeat_run_id: str = "",
) -> Namespace:
    return Namespace(
        config=str(config_path),
        plan_artifact=str(plan_root),
        execute_mainnet_delta_orders=execute,
        prepare_planned_symbol_account_settings=prepare_settings,
        operator_enable_mainnet_delta_for_this_run=enable,
        operator_enable_mainnet_account_settings_for_this_run=enable_settings,
        i_understand_this_places_real_mainnet_delta_orders=understand,
        i_understand_this_modifies_mainnet_account_settings=understand_settings,
        i_understand_daily_loss_budget_is_review_only=daily_review_ack,
        i_understand_daily_realized_pnl_gate_is_active=daily_active_ack,
        confirm_mainnet_delta_execution=confirmation,
        position_tolerance=1e-9,
        ignore_heartbeat_run_id=ignore_heartbeat_run_id,
    )


def _env() -> dict[str, str]:
    return {"LIVE_KEY": "key", "LIVE_SECRET": "secret"}


def _fixed_now() -> datetime:
    return datetime(2026, 5, 17, 16, 0, 0, tzinfo=UTC)


def _confirmation(plan_root: Path, *, daily_pnl_gate_active: bool = False) -> str:
    source = _load_source_plan(str(plan_root))
    return _required_confirmation(
        plan_hash=str(source["plan_hash"]),
        execution_stage=str(source["execution_stage"]),
    )


if __name__ == "__main__":
    unittest.main()
