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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bl_real_timer_path_shadow_readback_owner_gate import (  # noqa: E402
    APPROVE_P9BL_DECISION,
    P9BM_GATE,
    P9BM_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bm_real_timer_path_shadow_readback import (  # noqa: E402
    APPROVE_P9BM_DECISION,
    build_phase9bm,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class FakeSupervisorRunner:
    def __init__(self, *, orders_submitted: int = 0, blockers: list[str] | None = None) -> None:
        self.calls: list[Namespace] = []
        self.orders_submitted = int(orders_submitted)
        self.blockers = list(blockers or [])

    def __call__(self, args: Namespace, **_: object) -> tuple[dict[str, object], int]:
        self.calls.append(args)
        config = _load_json(Path(args.config))
        artifact_root = Path(str(dict(config.get("state") or {})["artifact_root"]))
        run_root = artifact_root / "mainnet_live_supervisor" / "fake-supervisor-run"
        plan_root = artifact_root / "core_loop" / "fake-core-plan"
        plan_root.mkdir(parents=True, exist_ok=True)
        target_portfolio = {
            "contract_version": "unit_test_target_portfolio.v1",
            "run_id": "fake-core-plan",
            "risk_inputs": {
                "trading_enabled": False,
                "live_delta_enabled": False,
                "submit_orders": False,
            },
            "target_weights": [{"symbol": "BTCUSDT", "target_weight": 0.0}],
        }
        _write_json(plan_root / "target_portfolio.json", target_portfolio)
        core_summary = {
            "status": "mainnet_core_loop_completed" if not self.blockers else "mainnet_core_loop_blocked",
            "blockers": self.blockers,
            "artifact_root": str(run_root / "core"),
            "execution_requested": False,
            "orders_submitted": self.orders_submitted,
            "fill_count": 0,
            "fills_observed": 0,
            "live_delta_authorized": False,
            "exchange_order_submission": "disabled",
            "cycles": [
                {
                    "cycle_index": 1,
                    "status": "plan_only_completed",
                    "blockers": self.blockers,
                    "plan_artifact_root": str(plan_root),
                    "orders_submitted": self.orders_submitted,
                    "fill_count": 0,
                }
            ],
        }
        supervisor_cycle = {
            "cycle_index": 1,
            "status": "cycle_observed_no_order" if not self.blockers else "cycle_blocked",
            "blockers": self.blockers,
            "execute_live_delta_requested": False,
            "live_delta_authorized": False,
            "orders_submitted": self.orders_submitted,
            "fill_count": 0,
            "core_loop_summary": core_summary,
        }
        summary = {
            "run_id": "fake-supervisor-run",
            "status": "mainnet_live_supervisor_completed" if not self.blockers else "mainnet_live_supervisor_blocked",
            "blockers": self.blockers,
            "artifact_root": str(run_root),
            "orders_submitted": self.orders_submitted,
            "fill_count": 0,
            "fills_observed": 0,
            "live_delta_authorized": False,
            "exchange_order_submission": "disabled",
            "cycles": [supervisor_cycle],
        }
        return summary, 0 if not self.blockers and self.orders_submitted == 0 else 2


class FixtureAwareSupervisorRunner:
    def __init__(self) -> None:
        self.calls: list[Namespace] = []
        self.core_loop_called = False

    def __call__(self, args: Namespace, **kwargs: object) -> tuple[dict[str, object], int]:
        self.calls.append(args)
        core_loop_runner = kwargs.get("core_loop_runner")
        if not callable(core_loop_runner):
            raise AssertionError("retained fixture test expected core_loop_runner injection")
        self.core_loop_called = True
        core_summary, core_exit = core_loop_runner(Namespace(), env=kwargs.get("env", {}))
        core_blockers = list(core_summary.get("blockers") or [])
        supervisor_cycle = {
            "cycle_index": 1,
            "status": "cycle_observed_no_order" if int(core_exit) == 0 and not core_blockers else "cycle_blocked",
            "blockers": core_blockers,
            "execute_live_delta_requested": False,
            "live_delta_authorized": False,
            "orders_submitted": int(core_summary.get("orders_submitted") or 0),
            "fill_count": int(core_summary.get("fill_count") or 0),
            "core_loop_summary": core_summary,
        }
        summary = {
            "run_id": "fixture-aware-supervisor",
            "status": "mainnet_live_supervisor_completed" if int(core_exit) == 0 and not core_blockers else "mainnet_live_supervisor_blocked",
            "blockers": core_blockers,
            "artifact_root": str(Path(args.config).parent / "fixture-aware-supervisor"),
            "orders_submitted": int(core_summary.get("orders_submitted") or 0),
            "fill_count": int(core_summary.get("fill_count") or 0),
            "fills_observed": 0,
            "live_delta_authorized": False,
            "exchange_order_submission": "disabled",
            "cycles": [supervisor_cycle],
        }
        return summary, 0 if summary["status"] == "mainnet_live_supervisor_completed" else 2


class Phase9BMRealTimerPathShadowReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bm-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_executes_default_off_observe_only_shadow_readback_no_order(self) -> None:
        paths = self._write_ready_p9bl_bundle()
        output_root = self.temp_dir / "p9bm"
        fake_supervisor = FakeSupervisorRunner()

        summary, exit_code = build_phase9bm(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 9, 1, 0, tzinfo=UTC),
            supervisor_runner=fake_supervisor,
            env={},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(fake_supervisor.calls), 1)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bm_real_timer_path_shadow_readback_ready"])
        self.assertTrue(summary["real_timer_path_shadow_readback_executed"])
        self.assertTrue(summary["supervisor_entrypoint_invoked"])
        self.assertFalse(summary["systemd_timer_service_invoked"])
        self.assertFalse(summary["production_timer_service_loaded_or_modified"])
        self.assertEqual(summary["execution_target_source"], "baseline_only")
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertTrue(summary["candidate_shadow_only"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["zero_order_cancel_fill_trade_delta"])

        generated_config = _load_json(Path(summary["output_files"]["generated_no_order_config"]))
        self.assertFalse(generated_config["risk"]["trading_enabled"])
        self.assertFalse(generated_config["core_loop"]["live_delta_enabled"])
        self.assertFalse(generated_config["core_loop"]["submit_orders"])
        self.assertFalse(generated_config["mainnet_live_supervisor"]["allow_live_delta_when_armed"])
        self.assertIn("proof_artifacts", Path(summary["proof_root"]).parts)

        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization_matrix"]))
        hook = _load_json(Path(summary["output_files"]["hook_shadow_readback_summary"]))
        self.assertTrue(control["supervisor_entrypoint_invoked"])
        self.assertFalse(control["production_timer_service_loaded_or_modified"])
        self.assertFalse(control["remote_sync_performed"])
        self.assertFalse(control["candidate_execution_performed"])
        self.assertEqual(control["orders_submitted"], 0)
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertEqual(hook["status"], "ready")
        self.assertFalse(hook["candidate_plan_referenced_by_executor"])

    def test_retained_account_position_fixture_unblocks_no_order_shadow_readback(self) -> None:
        paths = self._write_ready_p9bl_bundle()
        retained = self._write_retained_account_position_sources()
        output_root = self.temp_dir / "p9bm-retained"
        fixture_supervisor = FixtureAwareSupervisorRunner()

        summary, exit_code = build_phase9bm(
            self._args(
                paths,
                output_root=output_root,
                account_proof_source=retained["account_proof"],
                position_reference_source=retained["position_fingerprint"],
                retained_p9aa_summary=retained["p9aa_summary"],
            ),
            now_fn=lambda: datetime(2026, 6, 9, 2, 0, tzinfo=UTC),
            supervisor_runner=fixture_supervisor,
            env={},
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(fixture_supervisor.core_loop_called)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["account_proof_mode"], "retained_pit_safe_read_only_fixture")
        self.assertTrue(summary["retained_account_fixture_requested"])
        self.assertTrue(summary["retained_account_proof_ready"])
        self.assertTrue(summary["pit_safe_position_reference_fixture_ready"])
        self.assertTrue(summary["gates"]["retained_account_plan_fixture_ready"])
        self.assertTrue(summary["gates"]["retained_account_fixture_if_requested_ready"])
        self.assertTrue(summary["real_timer_path_shadow_readback_executed"])
        self.assertTrue(summary["supervisor_entrypoint_invoked"])
        self.assertTrue(summary["candidate_shadow_only"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        self.assertTrue(Path(summary["output_files"]["position_reference_fixture"]).exists())
        self.assertTrue(Path(summary["output_files"]["retained_account_plan_fixture"]).exists())
        fixture_summary = _load_json(Path(summary["output_files"]["retained_account_plan_fixture"]))
        self.assertEqual(fixture_summary["status"], "ready")
        self.assertTrue(fixture_summary["read_only"])
        self.assertTrue(fixture_summary["proof_artifacts_only"])
        target_portfolio = Path(fixture_summary["output_files"]["target_portfolio"])
        self.assertTrue(target_portfolio.exists())

    def test_wrong_owner_decision_blocks_without_supervisor_call(self) -> None:
        paths = self._write_ready_p9bl_bundle()
        fake_supervisor = FakeSupervisorRunner()

        summary, exit_code = build_phase9bm(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 1, 5, tzinfo=UTC),
            supervisor_runner=fake_supervisor,
            env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(fake_supervisor.calls), 0)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "owner_decision_p9bm_execute_real_timer_path_shadow_readback_no_order_only",
            summary["blockers"],
        )
        self.assertFalse(summary["supervisor_entrypoint_invoked"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_bad_p9bl_bundle_blocks_without_supervisor_call(self) -> None:
        paths = self._write_ready_p9bl_bundle(p9bl_overrides={"allowed_next_gate": "P9LIVE_ORDER"})
        fake_supervisor = FakeSupervisorRunner()

        summary, exit_code = build_phase9bm(
            self._args(paths, output_root=self.temp_dir / "bad-p9bl"),
            now_fn=lambda: datetime(2026, 6, 9, 1, 10, tzinfo=UTC),
            supervisor_runner=fake_supervisor,
            env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(fake_supervisor.calls), 0)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bl_owner_gate_ready_for_p9bm", summary["blockers"])
        self.assertFalse(summary["real_timer_path_shadow_readback_executed"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_supervisor_order_delta_blocks_even_though_live_order_remains_unauthorized(self) -> None:
        paths = self._write_ready_p9bl_bundle()
        fake_supervisor = FakeSupervisorRunner(orders_submitted=1)

        summary, exit_code = build_phase9bm(
            self._args(paths, output_root=self.temp_dir / "order-delta"),
            now_fn=lambda: datetime(2026, 6, 9, 1, 15, tzinfo=UTC),
            supervisor_runner=fake_supervisor,
            env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(fake_supervisor.calls), 1)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("supervisor_exit_zero", summary["blockers"])
        self.assertIn("supervisor_orders_fills_zero", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 1)
        self.assertFalse(summary["zero_order_cancel_fill_trade_delta"])

    def test_supervisor_exception_is_retained_blocked_evidence(self) -> None:
        paths = self._write_ready_p9bl_bundle()

        def raising_supervisor(_: Namespace, **__: object) -> tuple[dict[str, object], int]:
            raise FileNotFoundError("path too long")

        summary, exit_code = build_phase9bm(
            self._args(paths, output_root=self.temp_dir / "supervisor-exception"),
            now_fn=lambda: datetime(2026, 6, 9, 1, 20, tzinfo=UTC),
            supervisor_runner=raising_supervisor,
            env={},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertTrue(summary["supervisor_entrypoint_invoked"])
        self.assertFalse(summary["real_timer_path_shadow_readback_executed"])
        self.assertIn("supervisor_completed", summary["blockers"])
        self.assertIn("hook_invoked_with_supervisor_cycle_context", summary["blockers"])
        self.assertIn("supervisor_or_core_loop_blockers_present", summary["blockers"])
        self.assertEqual(summary["supervisor_summary"]["exception_type"], "FileNotFoundError")
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertTrue(Path(summary["output_files"]["supervisor_readback_summary"]).exists())

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BM_DECISION,
        account_proof_source: Path | None = None,
        position_reference_source: Path | None = None,
        retained_p9aa_summary: Path | None = None,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bl_summary=str(paths["p9bl_summary"]),
            base_config=str(paths["base_config"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            as_of="now",
            symbols="BTCUSDT,ETHUSDT",
            fixture_panel="",
            public_market_data=False,
            target_engine="multiphase_equal_sleeve",
            account_proof_source=str(account_proof_source or ""),
            position_reference_source=str(position_reference_source or ""),
            retained_p9aa_summary=str(retained_p9aa_summary or ""),
            position_tolerance=1e-9,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bl_bundle(
        self,
        *,
        p9bl_overrides: dict[str, object] | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        base_config = self.temp_dir / "base_no_order.yaml"
        p9bl_root = self.temp_dir / "p9bl"
        proof_root = p9bl_root / "proof_artifacts" / "p9bl" / "run"
        summary_path = p9bl_root / "summary.json"
        owner_path = p9bl_root / "owner_decision_record.json"
        permission_path = proof_root / "execution_permission.json"
        acceptance_path = proof_root / "acceptance_contract.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        control_path = proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        _write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        base_config.write_text(
            "\n".join(
                [
                    "binance:",
                    "  venue: usdm_futures",
                    "risk:",
                    "  trading_enabled: false",
                    "core_loop:",
                    "  live_delta_enabled: false",
                    "  submit_orders: false",
                    "  auto_confirm_delta_after_preflight: false",
                    "  max_cycles_per_invocation: 1",
                    "mainnet_live_supervisor:",
                    "  allow_live_delta_when_armed: false",
                    "  allow_multiphase_live_delta: false",
                    "  max_cycles_per_invocation: 1",
                    "  interval_seconds: 0",
                    "  disarm_on_blocker: false",
                    "mainnet_health_monitor:",
                    "  no_order_expected: true",
                    "  require_systemd_timer_active: false",
                    "state:",
                    f"  sqlite_path: {self.temp_dir / 'state' / 'live_trading.sqlite3'}",
                    f"  artifact_root: {self.temp_dir / 'runs'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        source = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
            "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        owner = self._p9bl_owner()
        permission = self._p9bl_permission(owner)
        acceptance = self._p9bl_acceptance()
        matrix = self._p9bl_matrix()
        control = self._p9bl_control(supervisor_sha, live_config_sha)
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bl_real_timer_path_shadow_readback_owner_gate.v1",
            "status": "ready",
            "blockers": [],
            "p9bl_owner_gate_ready": True,
            "p9bk_retained_evidence_ready_for_p9bl": True,
            "future_real_timer_path_shadow_readback_authorized": True,
            "p9bm_execution_gate_authorized": True,
            "allowed_next_gate": P9BM_GATE,
            "allowed_next_gate_scope": P9BM_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "real_timer_path_shadow_readback_executed_in_p9bl": False,
            "timer_path_load_authorized_in_p9bl": False,
            "supervisor_invocation_authorized_in_p9bl": False,
            "remote_sync_authorized_in_p9bl": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "live_supervisor_loads_candidate_hook": False,
            "live_timer_path_loaded": False,
            "ran_supervisor": False,
            "remote_execution_performed": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "owner_decision": owner,
            "source_evidence": source,
            "output_files": {
                "summary": str(summary_path),
                "owner_decision_record": str(owner_path),
                "execution_permission": str(permission_path),
                "acceptance_contract": str(acceptance_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        if p9bl_overrides:
            summary.update(p9bl_overrides)

        _write_json(owner_path, owner)
        _write_json(permission_path, permission)
        _write_json(acceptance_path, acceptance)
        _write_json(matrix_path, matrix)
        _write_json(control_path, control)
        _write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
            "base_config": base_config,
            "p9bl_summary": summary_path,
        }

    def _write_retained_account_position_sources(self) -> dict[str, Path]:
        source_root = self.temp_dir / "retained-sources"
        source_root.mkdir(parents=True)
        account_proof = source_root / "fresh_remote_account_read_pre.json"
        position_fingerprint = source_root / "position_fingerprint_pre.json"
        p9aa_summary = source_root / "p9aa_summary.json"
        finished_at = "2026-06-09T01:59:00Z"
        side_effects = {
            "only_http_get_endpoints": True,
            "order_test_calls": 0,
            "orders_canceled": 0,
            "orders_submitted": 0,
        }
        endpoint_results = {
            name: {"status": "ok", "status_code": 200, "path": f"/fixture/{name}"}
            for name in (
                "account_config",
                "account_information_v3",
                "api_key_permissions",
                "exchange_info",
                "open_orders",
                "position_mode",
            )
        }
        _write_json(
            account_proof,
            {
                "account_readable": True,
                "can_trade": True,
                "position_mode": "one_way",
                "egress_ip": "203.0.113.10",
                "expected_egress_ip": "203.0.113.10",
                "open_order_count": 0,
                "open_position_count": 1,
                "blockers": ["mainnet_open_positions_exist:1"],
                "endpoint_results": endpoint_results,
                "finished_at_utc": finished_at,
                "side_effects": side_effects,
            },
        )
        _write_json(
            position_fingerprint,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ag_position_fingerprint.v1",
                "status": "ready",
                "blockers": [],
                "account_readable": True,
                "position_mode": "one_way",
                "open_order_count": 0,
                "open_position_count": 1,
                "finished_at_utc": finished_at,
                "side_effects": side_effects,
                "position_fingerprint": {
                    "stable_hash": "btc-stable-hash",
                    "stable_rows": [
                        {
                            "symbol": "BTCUSDT",
                            "positionAmt": "0.01",
                            "positionSide": "BOTH",
                            "entryPrice": "61000",
                            "breakEvenPrice": "61000",
                            "isolated": "false",
                            "isolatedWallet": "0",
                        }
                    ],
                },
                "order_history_fingerprint": {"history_hash": "orders-hash"},
                "trade_history_fingerprint": {"history_hash": "trades-hash"},
            },
        )
        current_positions = [
            {
                "symbol": "BTCUSDT",
                "positionSide": "BOTH",
                "positionAmt": 0.01,
                "notional": 610.0,
                "entryPrice": 61000.0,
                "markPrice": 61000.0,
                "unrealizedProfit": 0.0,
                "marginType": "cross",
                "leverage": 2,
                "isolated": False,
            }
        ]
        strategy_plan_artifacts = {
            "current_positions": current_positions,
            "target_portfolio": {
                "contract_version": "unit_test_retained_target_portfolio.v1",
                "portfolio_id": "retained-portfolio",
                "status": "ok",
                "allocated_capital_usdt": 1000.0,
                "target_gross_weight": 0.0,
                "target_net_weight": 0.0,
                "blockers": [],
            },
            "target_positions": [],
            "execution_plan": {
                "status": "dust_noop",
                "mode": "plan_only",
                "active_execution_phase": "dust_noop",
                "blockers": [],
            },
            "order_sizing_report": [],
            "delta_orders": [],
            "risk_gate": {"decision": "allow_plan", "passed": True, "blockers": []},
            "run_summary": {
                "status": "mainnet_current_position_rebalance_dust_noop",
                "blockers": [],
                "orders_submitted": 0,
                "fill_count": 0,
                "current_position_aware": True,
                "plan_only": True,
                "recurring_mainnet_enabled": False,
                "mainnet_order_submission_authorized": False,
                "open_order_count": 0,
            },
        }
        account_artifacts = {
            "account": {
                "account_readable": True,
                "account_config_readable": True,
                "can_trade": True,
                "available_balance_usdt": 500.0,
                "total_wallet_balance_usdt": 1200.0,
                "total_margin_balance_usdt": 1200.0,
            },
            "monitor_report": {
                "status": "passed_live_position_monitor",
                "blockers": [],
                "read_only": True,
                "account": {
                    "account_readable": True,
                    "account_config_readable": True,
                    "can_trade": True,
                    "available_balance_usdt": 500.0,
                    "total_wallet_balance_usdt": 1200.0,
                    "total_margin_balance_usdt": 1200.0,
                },
                "open_orders": {"open_order_count": 0, "open_orders_redacted": []},
            },
        }
        core_cycle = {
            "cycle_index": 1,
            "status": "cycle_dust_noop",
            "blockers": [],
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "plan_artifact_root": "/remote/proof/retained-plan",
            "monitor_artifact_root": "/remote/proof/retained-monitor",
            "target_engine": "multiphase_equal_sleeve",
            "plan_status": "mainnet_current_position_rebalance_dust_noop",
            "execution_status": "noop_dust_delta",
            "account_reconcile_artifacts": account_artifacts,
            "strategy_plan_artifacts": strategy_plan_artifacts,
        }
        core_summary = {
            "status": "mainnet_core_loop_completed",
            "blockers": [],
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "execution_requested": False,
            "cycles": [core_cycle],
        }
        supervisor_summary = {
            "status": "mainnet_live_supervisor_completed",
            "blockers": [],
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "cycles": [
                {
                    "cycle_index": 1,
                    "status": "cycle_observed_no_order",
                    "blockers": [],
                    "execute_live_delta_requested": False,
                    "live_delta_authorized": False,
                    "orders_submitted": 0,
                    "fill_count": 0,
                    "core_loop_summary": core_summary,
                }
            ],
        }
        _write_json(
            p9aa_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1",
                "status": "ready",
                "blockers": [],
                "completed_shadow_cycles": 1,
                "fresh_proof_each_cycle": True,
                "same_risk_no_order_config_each_cycle": True,
                "baseline_only_executor_input": True,
                "candidate_shadow_only": True,
                "position_reference_fixture_ready": True,
                "position_reference_fixture_requested": True,
                "account_read_blockers": [],
                "orders_submitted": 0,
                "fill_count": 0,
                "cycle_rows": [
                    {
                        "cycle_index": 1,
                        "cycle_ready": True,
                        "hook_summary": {
                            "status": "ready",
                            "executor_consumes_baseline_only": True,
                            "candidate_plan_referenced_by_executor": False,
                            "candidate_artifacts_under_proof_artifacts_only": True,
                            "orders_submitted": 0,
                            "fill_count": 0,
                        },
                        "supervisor_exit_code": 0,
                        "supervisor_summary": supervisor_summary,
                    }
                ],
            },
        )
        return {
            "account_proof": account_proof,
            "position_fingerprint": position_fingerprint,
            "p9aa_summary": p9aa_summary,
        }

    @staticmethod
    def _p9bl_owner() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bl_owner_decision.v1",
            "decision": APPROVE_P9BL_DECISION,
            "future_real_timer_path_shadow_readback_approved": True,
            "p9bm_execution_gate_approved": True,
            "execute_readback_inside_p9bl_approved": False,
            "candidate_execution_approved": False,
            "live_order_submission_approved": False,
        }

    @staticmethod
    def _p9bl_permission(owner: dict[str, object]) -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bl_execution_permission.v1",
            "permission_ready": True,
            "allowed_next_gate": P9BM_GATE,
            "allowed_next_gate_scope": P9BM_SCOPE,
            "readback_execution_authorized_for_future_gate": True,
            "readback_executed_in_p9bl": False,
            "real_live_supervisor_timer_path_allowed_for_future_gate": True,
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "owner_decision": owner,
        }

    @staticmethod
    def _p9bl_acceptance() -> dict[str, object]:
        required_checks = {
            "default_off": True,
            "observe_only": True,
            "baseline_only_executor": True,
            "candidate_shadow_only": True,
            "candidate_plan_not_referenced_by_executor": True,
            "fresh_proof": True,
            "same_risk_inputs": True,
            "zero_orders": True,
            "zero_cancels": True,
            "zero_fills": True,
            "zero_trades": True,
            "no_target_plan_replacement": True,
            "no_executor_input_mutation": True,
            "no_live_config_mutation": True,
            "no_operator_state_mutation": True,
            "no_timer_state_mutation": True,
            "production_timer_service_not_enabled": True,
            "live_order_submission_authorized": False,
        }
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bl_acceptance_contract.v1",
            "accepted_next_gate": P9BM_GATE,
            "p9bm_must_be_separately_requested": True,
            "checks_required_before_p9bm_can_pass": required_checks,
            "p9bl_executed_readback": False,
            "p9bl_loaded_timer_path": False,
            "p9bl_invoked_supervisor": False,
            "p9bl_remote_synced": False,
            "p9bl_submitted_orders": False,
        }

    @staticmethod
    def _p9bl_matrix() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bl_non_authorization_matrix.v1",
            "authorizations": {
                "future_real_timer_path_shadow_readback": True,
                "p9bm_execution_gate": True,
                "execute_readback_inside_p9bl": False,
                "candidate_execution": False,
                "live_order_submission": False,
            },
        }

    @staticmethod
    def _p9bl_control(supervisor_sha: str, live_config_sha: str) -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bl_control_boundary_readback.v1",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "live_supervisor_sha256_before": supervisor_sha,
            "live_supervisor_sha256_after": supervisor_sha,
            "live_config_dir_sha256_before": live_config_sha,
            "live_config_dir_sha256_after": live_config_sha,
            "future_real_timer_path_shadow_readback_authorized": True,
            "p9bm_execution_gate_authorized": True,
            "real_timer_path_shadow_readback_executed_in_p9bl": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


if __name__ == "__main__":
    unittest.main()
