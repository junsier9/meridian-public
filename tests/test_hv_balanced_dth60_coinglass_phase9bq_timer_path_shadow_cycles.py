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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bp_owner_gate_allow_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9BP_DECISION,
    CONTRACT_VERSION as P9BP_CONTRACT,
    P9BQ_GATE,
    P9BQ_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bq_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9BQ_DECISION,
    P9BR_GATE,
    build_p9bq,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class FixtureAwareContinuousSupervisorRunner:
    def __init__(self, *, orders_submitted: int = 0, blockers: list[str] | None = None) -> None:
        self.calls: list[Namespace] = []
        self.orders_submitted = int(orders_submitted)
        self.blockers = list(blockers or [])

    def __call__(self, args: Namespace, **kwargs: object) -> tuple[dict[str, object], int]:
        self.calls.append(args)
        core_loop_runner = kwargs.get("core_loop_runner")
        if not callable(core_loop_runner):
            raise AssertionError("P9BQ expected retained core_loop_runner injection")
        core_summary, core_exit = core_loop_runner(Namespace(), env=kwargs.get("env", {}))
        core_blockers = list(core_summary.get("blockers") or []) + self.blockers
        orders = self.orders_submitted
        cycle_index = len(self.calls)
        supervisor_cycle = {
            "cycle_index": 1,
            "status": "cycle_observed_no_order" if int(core_exit) == 0 and not core_blockers else "cycle_blocked",
            "blockers": core_blockers,
            "execute_live_delta_requested": False,
            "live_delta_authorized": False,
            "orders_submitted": orders,
            "fill_count": 0,
            "core_loop_summary": core_summary,
        }
        summary = {
            "run_id": f"fake-p9bq-supervisor-{cycle_index:03d}",
            "status": "mainnet_live_supervisor_completed"
            if int(core_exit) == 0 and not core_blockers
            else "mainnet_live_supervisor_blocked",
            "blockers": core_blockers,
            "artifact_root": str(Path(args.config).parent / f"fake-supervisor-{cycle_index:03d}"),
            "configured_cycle_count": 1,
            "requested_cycle_count": 1,
            "completed_cycle_count": 1,
            "orders_submitted": orders,
            "fill_count": 0,
            "fills_observed": 0,
            "live_delta_authorized": False,
            "exchange_order_submission": "disabled",
            "cycles": [supervisor_cycle],
        }
        return summary, 0 if summary["status"] == "mainnet_live_supervisor_completed" and orders == 0 else 2


class Phase9BQTimerPathShadowCyclesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bq-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_executes_three_continuous_shadow_cycles_no_order(self) -> None:
        paths = self._write_ready_inputs()
        runner = FixtureAwareContinuousSupervisorRunner()

        summary, exit_code = build_p9bq(
            self._args(paths, output_root=self.temp_dir / "p9bq"),
            now_fn=lambda: datetime(2026, 6, 10, 4, 0, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
            sleep_fn=lambda _: None,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bq_timer_path_shadow_cycles_ready"])
        self.assertTrue(summary["continuous_timer_path_shadow_cycles_executed"])
        self.assertEqual(summary["completed_shadow_cycles"], 3)
        self.assertTrue(summary["fresh_proof_each_cycle"])
        self.assertTrue(summary["same_risk_no_order_config_each_cycle"])
        self.assertTrue(summary["same_target_plan_hash_each_cycle"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_shadow_only"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["production_timer_service_loaded_or_modified"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9BR_GATE)

        generated_config = _load_json(Path(summary["output_files"]["generated_no_order_config"]))
        self.assertFalse(generated_config["risk"]["trading_enabled"])
        self.assertFalse(generated_config["core_loop"]["live_delta_enabled"])
        self.assertFalse(generated_config["core_loop"]["submit_orders"])
        self.assertFalse(generated_config["mainnet_live_supervisor"]["allow_live_delta_when_armed"])
        self.assertIn("proof_artifacts", Path(summary["proof_root"]).parts)

        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization_matrix"]))
        self.assertTrue(control["supervisor_entrypoint_invoked"])
        self.assertEqual(control["completed_shadow_cycles"], 3)
        self.assertFalse(control["production_timer_service_loaded_or_modified"])
        self.assertFalse(control["remote_sync_performed"])
        self.assertEqual(control["orders_submitted"], 0)
        self.assertTrue(matrix["authorizations"]["continuous_timer_path_shadow_cycles_execution"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        for index in range(1, 4):
            self.assertTrue(Path(summary["output_files"][f"cycle_{index:03d}_readback"]).exists())

    def test_wrong_owner_decision_blocks_before_supervisor(self) -> None:
        paths = self._write_ready_inputs()
        runner = FixtureAwareContinuousSupervisorRunner()

        summary, exit_code = build_p9bq(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 4, 5, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
            sleep_fn=lambda _: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(runner.calls), 0)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bq_execute_cycles_no_order_only", summary["blockers"])
        self.assertFalse(summary["p9bq_timer_path_shadow_cycles_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_bad_p9bp_bundle_blocks_before_supervisor(self) -> None:
        paths = self._write_ready_inputs(p9bp_overrides={"allowed_next_gate": "P9LIVE_ORDER"})
        runner = FixtureAwareContinuousSupervisorRunner()

        summary, exit_code = build_p9bq(
            self._args(paths, output_root=self.temp_dir / "bad-p9bp"),
            now_fn=lambda: datetime(2026, 6, 10, 4, 10, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
            sleep_fn=lambda _: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(runner.calls), 0)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bp_owner_gate_ready_for_p9bq", summary["blockers"])
        self.assertFalse(summary["continuous_timer_path_shadow_cycles_executed"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_order_delta_blocks_and_still_does_not_authorize_live_order(self) -> None:
        paths = self._write_ready_inputs()
        runner = FixtureAwareContinuousSupervisorRunner(orders_submitted=1)

        summary, exit_code = build_p9bq(
            self._args(paths, output_root=self.temp_dir / "order-delta"),
            now_fn=lambda: datetime(2026, 6, 10, 4, 15, tzinfo=UTC),
            supervisor_runner=runner,
            env={},
            sleep_fn=lambda _: None,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("ran_requested_cycle_count", summary["blockers"])
        self.assertIn("ran_at_least_three_cycles", summary["blockers"])
        self.assertIn("all_supervisor_orders_zero", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 1)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BQ_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bp_summary=str(paths["p9bp_summary"]),
            base_config=str(paths["base_config"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            shadow_cycles=3,
            interval_seconds=0.0,
            as_of="now",
            symbols="BTCUSDT",
            fixture_panel="",
            public_market_data=False,
            target_engine="multiphase_equal_sleeve",
            account_proof_source="",
            position_reference_source="",
            retained_p9aa_summary="",
            position_tolerance=1e-9,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self, *, p9bp_overrides: dict[str, object] | None = None) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        base_config = self.temp_dir / "base_no_order.yaml"
        retained = self._write_retained_sources()
        p9bm_summary = self.temp_dir / "p9bm" / "summary.json"
        p9bn_summary = self.temp_dir / "p9bn" / "summary.json"
        p9bo_summary = self.temp_dir / "p9bo" / "summary.json"
        p9bp_root = self.temp_dir / "p9bp"
        p9bp_summary = p9bp_root / "summary.json"
        proof_root = p9bp_root / "proof_artifacts" / "p9bp" / "run"
        owner_path = p9bp_root / "owner_decision_record.json"
        permission_path = proof_root / "execution_permission.json"
        acceptance_path = proof_root / "acceptance_contract.json"
        checklist_path = proof_root / "acceptance_checklist.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        control_path = proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text("# baseline supervisor\n", encoding="utf-8")
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

        _write_json(
            p9bm_summary,
            {
                "source_evidence": {
                    "account_proof_source": _evidence(retained["account_proof"]),
                    "position_reference_source": _evidence(retained["position_fingerprint"]),
                    "retained_p9aa_summary": _evidence(retained["p9aa_summary"]),
                }
            },
        )
        _write_json(p9bn_summary, {"source_evidence": {"phase9bm_summary": _evidence(p9bm_summary)}})
        _write_json(p9bo_summary, {"source_evidence": {"phase9bn_summary": _evidence(p9bn_summary)}})

        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        source = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
            "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            "phase9bo_summary": _evidence(p9bo_summary),
        }
        owner = self._p9bp_owner()
        acceptance = self._p9bp_acceptance()
        permission = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bp_execution_permission.v1",
            "permission_ready": True,
            "allowed_next_gate": P9BQ_GATE,
            "allowed_next_gate_scope": P9BQ_SCOPE,
            "continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate": True,
            "p9bq_execution_gate_authorized": True,
            "execute_cycles_inside_p9bp": False,
            "candidate_order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "acceptance_contract": acceptance,
        }
        checklist = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bp_acceptance_checklist.v1",
            "checks": {
                "p9bo_status_ready": True,
                "p9bo_blockers_empty": True,
                "p9bo_proposal_package_ready": True,
                "p9bo_acceptance_contract_ready": True,
                "future_gate_requires_at_least_three_cycles": True,
                "future_gate_requires_fresh_proof_each_cycle": True,
                "future_gate_requires_same_risk_inputs": True,
                "future_gate_requires_baseline_only_executor": True,
                "future_gate_requires_candidate_shadow_only": True,
                "future_gate_requires_zero_order_cancel_fill_trade": True,
                "future_gate_keeps_live_order_submission_disabled": True,
                "p9bp_executes_nothing": True,
            },
        }
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bp_non_authorization_matrix.v1",
            "authorizations": {
                "future_continuous_timer_path_shadow_cycles_execution": True,
                "p9bq_execution_gate": True,
                "execute_cycles_inside_p9bp": False,
                "candidate_execution": False,
                "live_order_submission": False,
            },
        }
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bp_control_boundary_readback.v1",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "continuous_timer_path_shadow_cycles_executed_in_p9bp": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        summary = {
            "contract_version": P9BP_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bp_owner_gate_ready": True,
            "p9bo_proposal_review_package_ready_for_p9bp": True,
            "eligible_for_future_p9bq_continuous_timer_path_shadow_cycles": True,
            "allowed_next_gate": P9BQ_GATE,
            "allowed_next_gate_scope": P9BQ_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "future_continuous_timer_path_shadow_cycles_execution_authorized": True,
            "continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate": True,
            "p9bq_execution_gate_authorized": True,
            "continuous_timer_path_shadow_cycles_execution_authorized": False,
            "continuous_timer_path_shadow_cycles_executed_in_p9bp": False,
            "execute_cycles_inside_p9bp_authorized": False,
            "timer_path_load_authorized_in_p9bp": False,
            "supervisor_invocation_authorized_in_p9bp": False,
            "remote_sync_authorized_in_p9bp": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "entered_timer_path": False,
            "ran_supervisor": False,
            "remote_execution_performed": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "owner_decision": owner,
            "source_evidence": source,
            "output_files": {
                "summary": str(p9bp_summary),
                "owner_decision_record": str(owner_path),
                "execution_permission": str(permission_path),
                "acceptance_contract": str(acceptance_path),
                "acceptance_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        if p9bp_overrides:
            summary.update(p9bp_overrides)

        _write_json(owner_path, owner)
        _write_json(permission_path, permission)
        _write_json(acceptance_path, acceptance)
        _write_json(checklist_path, checklist)
        _write_json(matrix_path, matrix)
        _write_json(control_path, control)
        _write_json(p9bp_summary, summary)
        return {
            "project_profile": project_profile,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
            "base_config": base_config,
            "p9bp_summary": p9bp_summary,
        }

    def _write_retained_sources(self) -> dict[str, Path]:
        root = self.temp_dir / "retained"
        root.mkdir(parents=True)
        account_proof = root / "fresh_remote_account_read_pre.json"
        position_fingerprint = root / "position_fingerprint_pre.json"
        p9aa_summary = root / "p9aa_summary.json"
        finished_at = "2026-06-09T01:00:00Z"
        side_effects = {
            "only_http_get_endpoints": True,
            "order_test_calls": 0,
            "orders_canceled": 0,
            "orders_submitted": 0,
        }
        endpoints = {
            name: {"status": "ok"}
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
                "endpoint_results": endpoints,
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
            }
        ]
        strategy_artifacts = {
            "current_positions": current_positions,
            "target_portfolio": {
                "contract_version": "unit_test_retained_target_portfolio.v1",
                "portfolio_id": "retained-portfolio",
                "status": "ok",
                "target_gross_weight": 0.0,
                "target_net_weight": 0.0,
                "blockers": [],
            },
            "target_positions": [],
            "execution_plan": {"status": "dust_noop", "mode": "plan_only", "blockers": []},
            "order_sizing_report": [],
            "delta_orders": [],
            "risk_gate": {"decision": "allow_plan", "passed": True, "blockers": []},
            "run_summary": {
                "status": "mainnet_current_position_rebalance_dust_noop",
                "blockers": [],
                "orders_submitted": 0,
                "fill_count": 0,
                "plan_only": True,
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
            "target_engine": "multiphase_equal_sleeve",
            "account_reconcile_artifacts": account_artifacts,
            "strategy_plan_artifacts": strategy_artifacts,
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
    def _p9bp_owner() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bp_owner_decision.v1",
            "decision": APPROVE_P9BP_DECISION,
            "future_continuous_timer_path_shadow_cycles_execution_approved": True,
            "p9bq_execution_gate_approved": True,
            "execute_cycles_inside_p9bp_approved": False,
            "candidate_execution_approved": False,
            "live_order_submission_approved": False,
        }

    @staticmethod
    def _p9bp_acceptance() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bp_p9bq_acceptance_contract.v1",
            "accepted_next_gate": P9BQ_GATE,
            "accepted_next_gate_scope": P9BQ_SCOPE,
            "p9bq_must_be_separately_requested": True,
            "minimum_cycle_count": 3,
            "cycles_must_be_continuous": True,
            "cycles_must_share_same_no_order_config": True,
            "cycles_must_use_real_live_supervisor_timer_path": True,
            "fresh_proof_each_cycle": True,
            "same_risk_inputs_as_baseline_plan_each_cycle": True,
            "baseline_only_executor_input_each_cycle": True,
            "candidate_shadow_only_each_cycle": True,
            "candidate_artifacts_under_proof_artifacts_only_each_cycle": True,
            "candidate_plan_must_not_be_referenced_by_executor_each_cycle": True,
            "target_plan_must_not_be_replaced_each_cycle": True,
            "executor_input_must_not_change_each_cycle": True,
            "zero_order_delta_each_cycle": True,
            "zero_cancel_delta_each_cycle": True,
            "zero_fill_delta_each_cycle": True,
            "zero_trade_delta_each_cycle": True,
            "live_config_must_not_change": True,
            "operator_state_must_not_change": True,
            "timer_state_must_not_change": True,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), "exists": path.exists(), "sha256": file_sha256(path) if path.exists() else ""}


if __name__ == "__main__":
    unittest.main()
