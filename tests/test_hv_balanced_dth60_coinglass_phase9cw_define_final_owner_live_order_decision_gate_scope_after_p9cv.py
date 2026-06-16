from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest


from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (
    EXPECTED_FINAL_EVIDENCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct import (
    CONTRACT_VERSION as P9CV_CONTRACT,
    P9CW_GATE,
    P9CW_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv import (
    APPROVE_P9CW_DECISION,
    CONTRACT_VERSION as P9CW_CONTRACT,
    P9CX_GATE,
    build_phase9cw,
)


class Phase9CWDefineP9CXBigPackageScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cw-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_defines_p9cx_big_package_scope_without_execution_authority(self) -> None:
        paths = self._write_ready_p9cv_inputs()

        summary, exit_code = build_phase9cw(
            self._args(paths, output_root=self.temp_dir / "p9cw"),
            now_fn=lambda: datetime(2026, 6, 8, 14, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CW_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9cw_final_owner_live_order_decision_gate_scope_defined"])
        self.assertTrue(summary["p9cx_big_package_scope_defined"])
        self.assertTrue(summary["p9cx_fresh_proof_collection_in_scope"])
        self.assertTrue(summary["p9cx_no_order_candidate_replacement_dry_run_in_scope"])
        self.assertTrue(summary["p9cx_pre_order_control_readback_in_scope"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9cw"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CX_GATE)

        scope = _load_json(Path(summary["output_files"]["p9cx_big_package_scope"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertEqual(
            set(scope["p9cx_big_package_components"]),
            {
                "fresh_proof_collection",
                "no_order_candidate_target_plan_replacement_dry_run",
                "pre_order_control_boundary_readback",
            },
        )
        self.assertIn("live order submission", scope["p9cx_may_not_execute"])
        self.assertIn("actual executor-input mutation", scope["p9cx_may_not_execute"])
        self.assertTrue(non_auth["authorizations"]["allow_future_p9cx_execution_request"])
        self.assertFalse(non_auth["authorizations"]["execute_p9cx_in_p9cw"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9cv_does_not_allow_p9cw(self) -> None:
        paths = self._write_ready_p9cv_inputs()
        p9cv = _load_json(paths["p9cv_summary"])
        p9cv["allowed_next_gate"] = "P9CX_skip_p9cw"
        _write_json(paths["p9cv_summary"], p9cv)

        summary, exit_code = build_phase9cw(
            self._args(paths, output_root=self.temp_dir / "blocked-next-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 14, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cv_summary_ready_for_p9cw_scope", summary["blockers"])
        self.assertFalse(summary["p9cw_final_owner_live_order_decision_gate_scope_defined"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_if_p9cv_non_authorization_was_mutated(self) -> None:
        paths = self._write_ready_p9cv_inputs()
        non_auth = _load_json(paths["non_authorization"])
        non_auth["authorizations"]["live_order_submission"] = True
        _write_json(paths["non_authorization"], non_auth)

        summary, exit_code = build_phase9cw(
            self._args(paths, output_root=self.temp_dir / "bad-non-auth"),
            now_fn=lambda: datetime(2026, 6, 8, 14, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cv_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cv_summary=str(paths["p9cv_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9CW_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cv_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "p9cv"
        proof_root = root / "proof_artifacts" / "p9cv" / "run"
        paths = {
            "project_profile": self.temp_dir / "project_profile.json",
            "p9cv_summary": root / "summary.json",
            "sufficiency_review": proof_root / "p9cu_sufficiency_review.json",
            "gap_matrix": proof_root / "final_decision_gap_matrix.json",
            "non_authorization": proof_root / "non_authorization.json",
            "control": proof_root / "control_boundary_readback.json",
        }
        _write_json(paths["project_profile"], {"current_stage": "stage_3_human_approved_execution"})
        _write_json(paths["sufficiency_review"], _p9cv_sufficiency_review())
        _write_json(paths["gap_matrix"], _p9cv_gap_matrix())
        _write_json(paths["non_authorization"], _p9cv_non_authorization())
        _write_json(paths["control"], _p9cv_control())
        _write_json(paths["p9cv_summary"], _p9cv_summary(paths))
        return paths


def _p9cv_summary(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "contract_version": P9CV_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_ready": True,
        "p9cu_package_sufficient_for_p9cv_review": True,
        "p9cu_package_sufficient_for_future_p9cw_scope_definition": True,
        "p9cu_package_sufficient_for_live_order_submission": False,
        "p9cu_package_sufficient_for_candidate_execution": False,
        "p9cu_package_sufficient_for_candidate_executor_path_entry": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_decision_collected_in_p9cu": False,
        "final_decision_evidence_collected_in_p9cu": False,
        "fresh_proofs_collected_in_p9cu": False,
        "required_final_decision_evidence_count": len(EXPECTED_FINAL_EVIDENCE),
        "remaining_evidence_gap_count": len(EXPECTED_FINAL_EVIDENCE),
        "decision_checklist_unsatisfied_count": 8,
        "eligible_for_future_p9cw_scope_definition": True,
        "allowed_next_gate": P9CW_GATE,
        "allowed_next_gate_scope": P9CW_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "baseline_target_plan_sha256": "baseline-sha",
        "candidate_target_plan_sha256": "candidate-sha",
        "only_distance_to_high_60_contribution_changed": True,
        "output_files": {
            "p9cu_sufficiency_review": str(paths["sufficiency_review"]),
            "final_decision_gap_matrix": str(paths["gap_matrix"]),
            "non_authorization": str(paths["non_authorization"]),
            "control_boundary_readback": str(paths["control"]),
        },
    }


def _p9cv_sufficiency_review() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_p9cu_sufficiency_review.v1",
        "review_only": True,
        "p9cu_package_sufficient_for_p9cv_review": True,
        "p9cu_package_sufficient_for_future_p9cw_scope_definition": True,
        "p9cu_package_sufficient_for_live_order_submission": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_decision_evidence_collected_in_p9cu": False,
        "fresh_proofs_collected_in_p9cu": False,
        "final_decision_actionable_items_satisfied": False,
        "future_gate": P9CW_GATE,
        "future_gate_scope": P9CW_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "checks": {"retained_package_reviewed": True},
    }


def _p9cv_gap_matrix() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_final_decision_gap_matrix.v1",
        "run_scope": "review_p9cu_package_only",
        "p9cu_package_sufficient_for_p9cv_review": True,
        "p9cu_package_sufficient_for_future_p9cw_scope_definition": True,
        "p9cu_package_sufficient_for_live_order_submission": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "evidence_rows": [
            {
                "evidence_id": key,
                "status_in_p9cu": "packaged_for_future_decision_not_collected",
                "collection_status_in_p9cu": "not_collected",
                "freshness_status_in_p9cu": "not_evaluated",
                "remaining_gap_for_final_live_order_gate": True,
            }
            for key in EXPECTED_FINAL_EVIDENCE
        ],
        "remaining_evidence_gap_count": len(EXPECTED_FINAL_EVIDENCE),
        "checklist_rows": [{"check_id": f"check_{idx}"} for idx in range(10)],
        "remaining_checklist_gap_count": 8,
    }


def _p9cv_non_authorization() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_non_authorization.v1",
        "authorizations": {
            "review_p9cu_final_owner_live_order_decision_review_package": True,
            "allow_future_p9cw_scope_definition_request": True,
            "define_p9cw_scope_in_p9cv": False,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "final_owner_live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
        },
    }


def _p9cv_control() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_control_boundary.v1",
        "scope": "p9cu_retained_final_owner_live_order_decision_review_package_review_only",
        "ssh_invoked": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "fresh_proofs_collected": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
