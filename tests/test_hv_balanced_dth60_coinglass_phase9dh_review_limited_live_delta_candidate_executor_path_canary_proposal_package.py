from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dg_prepare_limited_live_delta_candidate_executor_path_canary_proposal_package import (
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_TIME_IN_FORCE,
    P9DH_GATE,
    P9DH_SCOPE,
    baseline_fallback_and_kill_switch_contract,
    candidate_plan_hash_binding_contract,
    post_run_reconciliation_contract,
    proposal_package,
    proposal_terms,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dh_review_limited_live_delta_candidate_executor_path_canary_proposal_package import (
    APPROVE_P9DH_DECISION,
    P9DI_GATE,
    build_phase9dh,
)


class Phase9DHReviewCandidateExecutorPathCanaryProposalPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9dh-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9dg_package_but_does_not_authorize_execution(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9dh(
            self._args(paths, output_root=self.temp_dir / "p9dh"),
            now_fn=lambda: datetime(2026, 6, 8, 23, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(
            summary[
                "p9dh_review_limited_live_delta_candidate_executor_path_canary_proposal_package_ready"
            ]
        )
        self.assertTrue(summary["p9dg_retained_proposal_sufficient_for_p9dh_review"])
        self.assertTrue(
            summary[
                "p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion"
            ]
        )
        self.assertTrue(summary["eligible_for_future_p9di_execution_owner_gate"])
        self.assertEqual(summary["allowed_next_gate"], P9DI_GATE)
        self.assertFalse(summary["proposal_package_sufficient_for_live_order_submission"])
        self.assertFalse(summary["proposal_package_sufficient_for_candidate_execution"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        review = _load_json(Path(summary["output_files"]["proposal_package_review"]))
        readiness = _load_json(
            Path(summary["output_files"]["execution_owner_gate_readiness"])
        )
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertTrue(
            review[
                "p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion"
            ]
        )
        self.assertFalse(review["p9dh_authorizes_execution"])
        self.assertIn(
            "distance_to_high_60_contribution_delta_sha256",
            review["candidate_plan_hash_binding_reviewed"]["required_hashes"],
        )
        self.assertEqual(
            readiness["future_gate_terms_locked_by_review"]["max_orders_total"],
            2,
        )
        self.assertIn(
            "fresh /fapi/v2/account.canTrade readback",
            readiness["future_gate_required_fresh_inputs"],
        )
        self.assertTrue(
            non_auth["authorizations"][
                "future_p9di_execution_owner_gate_request_allowed"
            ]
        )
        self.assertFalse(non_auth["authorizations"]["live_order_submission_in_p9dh"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_blocks_if_retained_p9dg_terms_allow_market_orders(self) -> None:
        paths = self._write_ready_inputs()
        terms = _load_json(paths["risk_order_terms"])
        terms["market_orders_allowed"] = True
        _write_json(paths["risk_order_terms"], terms)

        summary, exit_code = build_phase9dh(
            self._args(paths, output_root=self.temp_dir / "bad-p9dh"),
            now_fn=lambda: datetime(2026, 6, 8, 23, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9dg_risk_order_terms_ready", summary["blockers"])
        self.assertFalse(
            summary[
                "p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion"
            ]
        )
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9dg_summary=str(paths["p9dg_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DH_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "p9dg"
        proof = root / "proof_artifacts" / "p9dg" / "20260608T225000Z"
        project_profile = self.temp_dir / "project_profile.json"
        p9dg_summary = root / "summary.json"
        package_path = proof / "proposal_package.json"
        terms_path = proof / "risk_order_terms.json"
        hash_binding_path = proof / "candidate_plan_hash_binding.json"
        fallback_path = proof / "baseline_fallback_kill_switch.json"
        reconciliation_path = proof / "post_run_reconciliation.json"
        non_auth_path = proof / "non_authorization.json"
        control_path = proof / "control_boundary_readback.json"
        manifest_path = proof / "proof_artifact_manifest.json"

        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        p9dg_args = Namespace(
            owner="rulebook_owner",
            max_notional_per_order_usdt=DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
            max_gross_turnover_usdt=DEFAULT_MAX_GROSS_TURNOVER_USDT,
            max_orders_total=2,
            max_symbols_total=1,
            order_type=DEFAULT_ORDER_TYPE,
            time_in_force=DEFAULT_TIME_IN_FORCE,
        )
        run_id = "20260608T225000Z"
        now = datetime(2026, 6, 8, 22, 50, 0, tzinfo=UTC)
        terms = proposal_terms(p9dg_args)
        hash_binding = candidate_plan_hash_binding_contract(run_id)
        fallback = baseline_fallback_and_kill_switch_contract(run_id)
        reconciliation = post_run_reconciliation_contract(run_id)
        package = proposal_package(
            run_id=run_id,
            now=now,
            args=p9dg_args,
            terms=terms,
            hash_binding=hash_binding,
            fallback=fallback,
            reconciliation=reconciliation,
        )
        non_auth = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9dg_non_authorization.v1",
            "authorizations": {
                "prepare_proposal_package": True,
                "future_p9dh_review_request_allowed": True,
                "live_order_submission_in_p9dg": False,
                "candidate_executor_path_execution_in_p9dg": False,
                "actual_target_plan_replacement_in_p9dg": False,
                "executor_input_mutation_in_p9dg": False,
                "timer_path_load_in_p9dg": False,
                "supervisor_invocation_in_p9dg": False,
                "remote_execution_in_p9dg": False,
                "remote_sync_in_p9dg": False,
                "remote_file_write_in_p9dg": False,
                "continuous_automated_order_flow": False,
                "stage_governance_change": False,
            },
        }
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9dg_control_boundary.v1",
            "scope": "proposal_package_preparation_only",
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
        }

        _write_json(package_path, package)
        _write_json(terms_path, terms)
        _write_json(hash_binding_path, hash_binding)
        _write_json(fallback_path, fallback)
        _write_json(reconciliation_path, reconciliation)
        _write_json(non_auth_path, non_auth)
        _write_json(control_path, control)
        _write_json(
            manifest_path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9dg_proof_artifact_manifest.v1",
                "artifact_count": 7,
            },
        )
        _write_json(
            p9dg_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9dg_limited_live_delta_candidate_executor_path_canary_proposal_package.v1",
                "run_id": run_id,
                "generated_at_utc": "2026-06-08T22:50:00Z",
                "status": "ready",
                "blockers": [],
                "p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package_ready": True,
                "p9df_sufficient_for_p9dg_proposal_package": True,
                "proposal_package_prepared": True,
                "proposal_package_only": True,
                "proposal_scope": "single_cycle_limited_live_delta_candidate_executor_path_canary",
                "max_cycles_total": 1,
                "max_symbols_total": 1,
                "max_orders_total": 2,
                "max_notional_per_order_usdt": 75.0,
                "max_gross_turnover_usdt": 150.0,
                "order_type": "limit_ioc",
                "time_in_force": "IOC",
                "market_orders_allowed": False,
                "emergency_market_fallback_allowed": False,
                "candidate_plan_hash_binding_defined": True,
                "baseline_fallback_defined": True,
                "kill_switch_defined": True,
                "post_run_reconciliation_defined": True,
                "future_execution_gate_required": True,
                "eligible_for_future_p9dh_review_gate": True,
                "live_order_submission_authorized": False,
                "candidate_executor_path_execution_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "continuous_automated_order_flow_authorized": False,
                "remote_execution_performed": False,
                "remote_sync_performed": False,
                "remote_files_written": 0,
                "orders_submitted": 0,
                "orders_canceled": 0,
                "fill_count": 0,
                "trade_count": 0,
                "allowed_next_gate": P9DH_GATE,
                "allowed_next_gate_scope": P9DH_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "summary": str(p9dg_summary),
                    "proof_artifact_manifest": str(manifest_path),
                    "proposal_package": str(package_path),
                    "risk_order_terms": str(terms_path),
                    "candidate_plan_hash_binding": str(hash_binding_path),
                    "baseline_fallback_kill_switch": str(fallback_path),
                    "post_run_reconciliation": str(reconciliation_path),
                    "non_authorization": str(non_auth_path),
                    "control_boundary_readback": str(control_path),
                },
            },
        )
        return {
            "project_profile": project_profile,
            "p9dg_summary": p9dg_summary,
            "risk_order_terms": terms_path,
        }


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
