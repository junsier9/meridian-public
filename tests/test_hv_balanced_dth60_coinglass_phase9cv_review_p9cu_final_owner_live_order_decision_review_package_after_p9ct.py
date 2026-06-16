from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import shutil
import tempfile
import unittest


from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (
    APPROVE_P9CR_DECISION,
    build_phase9cr,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co import (
    APPROVE_P9CS_DECISION,
    build_phase9cs,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs import (
    APPROVE_P9CT_DECISION,
    build_phase9ct,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cu_prepare_final_owner_live_order_decision_review_package_after_p9ct import (
    APPROVE_P9CU_DECISION,
    build_phase9cu,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct import (
    APPROVE_P9CV_DECISION,
    CONTRACT_VERSION as P9CV_CONTRACT,
    P9CW_GATE,
    build_phase9cv,
)
from tests.test_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (
    _load_json,
    _p9cq_control,
    _p9cq_non_authorization,
    _p9cq_scope,
    _p9cq_summary,
    _required_final_gate_evidence,
    _write_json,
)


class Phase9CVReviewP9CUFinalOwnerDecisionPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cv-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9cu_package_only_without_live_order_authority(self) -> None:
        paths = self._write_ready_p9cu_inputs()

        summary, exit_code = build_phase9cv(
            self._args(paths, output_root=self.temp_dir / "p9cv"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CV_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary[
                "p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_ready"
            ]
        )
        self.assertTrue(summary["p9cu_package_sufficient_for_p9cv_review"])
        self.assertTrue(summary["p9cu_package_sufficient_for_future_p9cw_scope_definition"])
        self.assertFalse(summary["p9cu_package_sufficient_for_live_order_submission"])
        self.assertFalse(summary["p9cu_package_sufficient_for_candidate_execution"])
        self.assertFalse(summary["p9cu_satisfies_final_owner_live_order_gate"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertFalse(summary["final_owner_decision_collected_in_p9cu"])
        self.assertFalse(summary["final_decision_evidence_collected_in_p9cu"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9cu"])
        self.assertFalse(summary["final_decision_actionable_items_satisfied"])
        self.assertEqual(summary["required_final_decision_evidence_count"], 12)
        self.assertEqual(summary["remaining_evidence_gap_count"], 12)
        self.assertEqual(summary["decision_checklist_total_count"], 10)
        self.assertEqual(summary["decision_checklist_satisfied_count"], 2)
        self.assertEqual(summary["decision_checklist_unsatisfied_count"], 8)
        self.assertTrue(summary["eligible_for_future_p9cw_scope_definition"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["order_test_endpoint_called"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["canary_symbol"], "BTCUSDT")
        self.assertEqual(summary["canary_side"], "BUY")
        self.assertEqual(summary["max_notional_usdt"], 10.0)
        self.assertEqual(summary["order_type"], "post_only_limit")
        self.assertEqual(summary["time_in_force"], "GTX")
        self.assertEqual(summary["allowed_next_gate"], P9CW_GATE)

        review = _load_json(Path(summary["output_files"]["p9cu_sufficiency_review"]))
        gap_matrix = _load_json(Path(summary["output_files"]["final_decision_gap_matrix"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertTrue(review["review_only"])
        self.assertTrue(review["p9cu_package_sufficient_for_p9cv_review"])
        self.assertTrue(review["p9cu_package_sufficient_for_future_p9cw_scope_definition"])
        self.assertFalse(review["p9cu_package_sufficient_for_live_order_submission"])
        self.assertFalse(review["final_decision_actionable_items_satisfied"])
        self.assertEqual(gap_matrix["remaining_evidence_gap_count"], 12)
        self.assertEqual(gap_matrix["remaining_checklist_gap_count"], 8)
        self.assertTrue(
            non_auth["authorizations"][
                "review_p9cu_final_owner_live_order_decision_review_package"
            ]
        )
        self.assertFalse(non_auth["authorizations"]["final_owner_live_order_gate_approval"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9cu_allowed_next_gate_is_not_p9cv(self) -> None:
        paths = self._write_ready_p9cu_inputs()
        p9cu = _load_json(paths["p9cu_summary"])
        p9cu["allowed_next_gate"] = "P9CW_skip_p9cv_review"
        _write_json(paths["p9cu_summary"], p9cu)

        summary, exit_code = build_phase9cv(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cu_summary_ready_for_p9cv_review", summary["blockers"])
        self.assertFalse(summary["p9cu_package_sufficient_for_p9cv_review"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_candidate_authority(self) -> None:
        paths = self._write_ready_p9cu_inputs()

        summary, exit_code = build_phase9cv(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 13, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cv_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_if_p9cu_package_contains_live_order_authorization(self) -> None:
        paths = self._write_ready_p9cu_inputs()
        p9cu = _load_json(paths["p9cu_summary"])
        package_path = Path(
            p9cu["output_files"]["final_owner_live_order_decision_review_package"]
        )
        package = _load_json(package_path)
        package["live_order_submission_authorized"] = True
        _write_json(package_path, package)

        summary, exit_code = build_phase9cv(
            self._args(paths, output_root=self.temp_dir / "polluted-package"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cu_review_package_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_if_p9cu_checklist_claims_final_gate_satisfied(self) -> None:
        paths = self._write_ready_p9cu_inputs()
        p9cu = _load_json(paths["p9cu_summary"])
        checklist_path = Path(p9cu["output_files"]["final_decision_checklist"])
        checklist = _load_json(checklist_path)
        checklist["p9cu_satisfies_final_owner_live_order_gate"] = True
        checklist["approval_items"][2]["satisfied_in_p9cu"] = True
        _write_json(checklist_path, checklist)

        summary, exit_code = build_phase9cv(
            self._args(paths, output_root=self.temp_dir / "bad-checklist"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 20, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cu_final_decision_checklist_file_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["trade_count"], 0)

    def test_blocks_if_p9cu_non_authorization_was_mutated(self) -> None:
        paths = self._write_ready_p9cu_inputs()
        p9cu = _load_json(paths["p9cu_summary"])
        non_auth_path = Path(p9cu["output_files"]["non_authorization"])
        non_auth = _load_json(non_auth_path)
        non_auth["authorizations"]["live_order_submission"] = True
        _write_json(non_auth_path, non_auth)

        summary, exit_code = build_phase9cv(
            self._args(paths, output_root=self.temp_dir / "bad-non-auth"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 25, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cu_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["trade_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CV_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cu_summary=str(paths["p9cu_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cu_inputs(self) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        p9cq_root = self.temp_dir / "p9cq"
        p9cq_proof_root = p9cq_root / "proof_artifacts" / "p9cq" / "run"
        paths = {
            "project_profile": project_profile,
            "p9cq_summary": p9cq_root / "summary.json",
            "scope": p9cq_proof_root / "final_owner_live_order_gate_scope.json",
            "evidence": p9cq_proof_root / "required_final_gate_evidence.json",
            "non_auth": p9cq_proof_root / "non_authorization.json",
            "control": p9cq_proof_root / "control_boundary_readback.json",
        }
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(paths["scope"], _p9cq_scope())
        _write_json(paths["evidence"], _required_final_gate_evidence())
        _write_json(paths["non_auth"], _p9cq_non_authorization())
        _write_json(paths["control"], _p9cq_control())
        _write_json(paths["p9cq_summary"], _p9cq_summary(paths))

        p9cr_summary, p9cr_exit_code = build_phase9cr(
            Namespace(
                output_root=str(self.temp_dir / "p9cr"),
                project_profile=str(project_profile),
                phase9cq_summary=str(paths["p9cq_summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CR_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 9, 30, 0, tzinfo=UTC),
        )
        self.assertEqual(p9cr_exit_code, 0)
        p9cs_summary, p9cs_exit_code = build_phase9cs(
            Namespace(
                output_root=str(self.temp_dir / "p9cs"),
                project_profile=str(project_profile),
                phase9cr_summary=str(p9cr_summary["output_files"]["summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CS_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 10, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(p9cs_exit_code, 0)
        p9ct_summary, p9ct_exit_code = build_phase9ct(
            Namespace(
                output_root=str(self.temp_dir / "p9ct"),
                project_profile=str(project_profile),
                phase9cs_summary=str(p9cs_summary["output_files"]["summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CT_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 11, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(p9ct_exit_code, 0)
        p9cu_summary, p9cu_exit_code = build_phase9cu(
            Namespace(
                output_root=str(self.temp_dir / "p9cu"),
                project_profile=str(project_profile),
                phase9ct_summary=str(p9ct_summary["output_files"]["summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CU_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 12, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(p9cu_exit_code, 0)
        paths["p9cu_summary"] = Path(p9cu_summary["output_files"]["summary"])
        return paths


if __name__ == "__main__":
    unittest.main()
