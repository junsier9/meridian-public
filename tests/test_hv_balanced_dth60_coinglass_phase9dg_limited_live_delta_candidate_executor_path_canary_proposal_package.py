from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9df_define_limited_live_delta_candidate_executor_path_canary_discussion_scope import (
    P9DG_GATE,
    P9DG_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dg_prepare_limited_live_delta_candidate_executor_path_canary_proposal_package import (
    APPROVE_P9DG_DECISION,
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_TIME_IN_FORCE,
    P9DH_GATE,
    build_phase9dg,
)


class Phase9DGLimitedExecutorPathCanaryProposalPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9dg-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_prepares_terms_hash_binding_fallback_kill_switch_and_reconciliation_only(
        self,
    ) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9dg(
            self._args(paths, output_root=self.temp_dir / "p9dg"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(
            summary[
                "p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package_ready"
            ]
        )
        self.assertTrue(summary["proposal_package_prepared"])
        self.assertTrue(summary["proposal_package_only"])
        self.assertEqual(summary["max_cycles_total"], 1)
        self.assertEqual(summary["max_symbols_total"], 1)
        self.assertEqual(summary["max_orders_total"], 2)
        self.assertEqual(summary["max_notional_per_order_usdt"], 75.0)
        self.assertEqual(summary["max_gross_turnover_usdt"], 150.0)
        self.assertEqual(summary["order_type"], DEFAULT_ORDER_TYPE)
        self.assertEqual(summary["time_in_force"], DEFAULT_TIME_IN_FORCE)
        self.assertTrue(summary["candidate_plan_hash_binding_defined"])
        self.assertTrue(summary["baseline_fallback_defined"])
        self.assertTrue(summary["kill_switch_defined"])
        self.assertTrue(summary["post_run_reconciliation_defined"])
        self.assertEqual(summary["allowed_next_gate"], P9DH_GATE)
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        package = _load_json(Path(summary["output_files"]["proposal_package"]))
        terms = _load_json(Path(summary["output_files"]["risk_order_terms"]))
        hash_binding = _load_json(Path(summary["output_files"]["candidate_plan_hash_binding"]))
        fallback = _load_json(Path(summary["output_files"]["baseline_fallback_kill_switch"]))
        reconciliation = _load_json(Path(summary["output_files"]["post_run_reconciliation"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertEqual(package["max_notional"]["per_order_usdt"], 75.0)
        self.assertEqual(package["order_type"]["type"], "limit_ioc")
        self.assertFalse(package["p9dg_authorizes_execution"])
        self.assertFalse(package["p9dg_authorizes_live_order"])
        self.assertEqual(terms["max_notional_per_order_usdt"], DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT)
        self.assertEqual(terms["max_gross_turnover_usdt"], DEFAULT_MAX_GROSS_TURNOVER_USDT)
        self.assertFalse(terms["market_orders_allowed"])
        self.assertIn("candidate_target_plan_sha256", hash_binding["required_hashes_before_future_execution"])
        self.assertEqual(
            hash_binding["same_context_requirements"]["overlay_may_change_only"],
            "distance_to_high_60_contribution",
        )
        self.assertTrue(fallback["kill_switch"]["required"])
        self.assertIn(
            "keep executor input baseline-only",
            fallback["baseline_fallback_policy"]["fallback_action_before_submit"],
        )
        self.assertEqual(
            reconciliation["acceptance_conditions_for_future_execution_gate"][
                "completed_cycles_exactly"
            ],
            1,
        )
        self.assertTrue(non_auth["authorizations"]["future_p9dh_review_request_allowed"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission_in_p9dg"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_blocks_if_p9df_scope_claims_actual_target_plan_replacement_allowed(self) -> None:
        paths = self._write_ready_inputs()
        p9df = _load_json(paths["p9df_summary"])
        scope_path = Path(p9df["output_files"]["discussion_scope"])
        scope = _load_json(scope_path)
        scope["not_authorized_by_this_scope"].remove("actual target-plan replacement")
        _write_json(scope_path, scope)

        summary, exit_code = build_phase9dg(
            self._args(paths, output_root=self.temp_dir / "bad-p9dg"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9df_discussion_scope_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9df_summary=str(paths["p9df_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DG_DECISION,
            owner_decision_source="unit_test",
            max_notional_per_order_usdt=DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
            max_gross_turnover_usdt=DEFAULT_MAX_GROSS_TURNOVER_USDT,
            max_orders_total=2,
            max_symbols_total=1,
            order_type=DEFAULT_ORDER_TYPE,
            time_in_force=DEFAULT_TIME_IN_FORCE,
        )

    def _write_ready_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "p9df"
        proof = root / "proof_artifacts" / "p9df" / "run"
        project_profile = self.temp_dir / "project_profile.json"
        p9df_summary = root / "summary.json"
        scope = proof / "discussion_scope.json"
        non_auth = proof / "non_authorization.json"
        control = proof / "control_boundary_readback.json"

        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            scope,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9df_limited_live_delta_candidate_executor_path_canary_discussion_scope.v1",
                "scope_only": True,
                "scope_label": "single_cycle_limited_live_delta_candidate_executor_path_canary_discussion",
                "hard_limits_for_discussion": {
                    "max_cycles": 1,
                    "continuous_automated_order_flow": False,
                    "default_order_state": "disabled_until_separate_execution_gate",
                    "default_timer_path_state": "not_loaded",
                    "default_supervisor_invocation": "not_invoked",
                    "default_candidate_execution": "not_executed",
                    "default_target_plan_replacement": "not_replaced",
                    "default_executor_input_mutation": "not_mutated",
                    "default_remote_sync": "not_performed",
                    "default_remote_file_write": 0,
                    "must_remain_stage_3_human_approved_execution": True,
                },
                "must_define_before_any_future_execution_gate": [
                    "explicit owner approval for execution-path canary",
                    "fresh account proof source /fapi/v2/account.canTrade",
                    "pre/post position fingerprint acceptance",
                    "pre/post open-order fingerprint acceptance",
                    "max cycles exactly one unless a later gate says otherwise",
                    "max candidate symbols and orders",
                    "max notional per order and gross turnover",
                    "allowed order types and time-in-force",
                    "candidate target plan hash binding",
                    "baseline fallback and rollback conditions",
                    "timer/supervisor load state and remote control-boundary invariants",
                ],
                "not_authorized_by_this_scope": [
                    "live order submission",
                    "candidate executor-path execution",
                    "actual target-plan replacement",
                    "executor input mutation",
                    "timer path load",
                    "supervisor invocation",
                    "remote sync",
                    "remote file write",
                    "continuous automated order flow",
                    "stage governance change",
                ],
                "allowed_next_gate": P9DG_GATE,
                "allowed_next_gate_scope": P9DG_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
            },
        )
        _write_json(
            non_auth,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9df_non_authorization.v1",
                "authorizations": {
                    "define_discussion_scope": True,
                    "future_p9dg_proposal_package_request_allowed": True,
                    "live_order_submission_in_p9df": False,
                    "candidate_executor_path_execution_in_p9df": False,
                    "candidate_target_plan_replacement_in_p9df": False,
                    "executor_input_mutation_in_p9df": False,
                    "timer_path_load_in_p9df": False,
                    "supervisor_invocation_in_p9df": False,
                    "remote_execution_in_p9df": False,
                    "remote_sync_in_p9df": False,
                    "remote_file_write_in_p9df": False,
                    "continuous_automated_order_flow": False,
                    "stage_governance_change": False,
                },
            },
        )
        _write_json(
            control,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9df_control_boundary.v1",
                "scope": "scope_definition_only",
                "ssh_invoked": False,
                "remote_network_connection_performed": False,
                "fresh_remote_account_read_performed": False,
                "fresh_order_book_read_performed": False,
                "exchange_filter_read_performed": False,
                "order_test_endpoint_called": False,
                "live_order_submission_performed": False,
                "candidate_execution_performed": False,
                "target_plan_replaced": False,
                "executor_input_changed": False,
                "entered_timer_path": False,
                "ran_supervisor": False,
                "timer_path_loaded": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
            },
        )
        _write_json(
            p9df_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9df_define_limited_live_delta_candidate_executor_path_canary_discussion_scope.v1",
                "status": "ready",
                "blockers": [],
                "p9df_limited_live_delta_candidate_executor_path_canary_discussion_scope_ready": True,
                "p9de_sufficient_for_p9df_scope_definition": True,
                "scope_definition_only": True,
                "scope_label": "single_cycle_limited_live_delta_candidate_executor_path_canary_discussion",
                "allowed_scope_after_p9df": "proposal_package_preparation_only",
                "eligible_for_future_p9dg_proposal_package_gate": True,
                "max_cycles_discussion_scope": 1,
                "default_order_state": "disabled_until_separate_execution_gate",
                "continuous_automated_order_flow_allowed": False,
                "live_order_submission_authorized": False,
                "candidate_executor_path_execution_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "remote_execution_performed": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
                "allowed_next_gate": P9DG_GATE,
                "allowed_next_gate_scope": P9DG_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "discussion_scope": str(scope),
                    "non_authorization": str(non_auth),
                    "control_boundary_readback": str(control),
                },
            },
        )
        return {"project_profile": project_profile, "p9df_summary": p9df_summary}


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
