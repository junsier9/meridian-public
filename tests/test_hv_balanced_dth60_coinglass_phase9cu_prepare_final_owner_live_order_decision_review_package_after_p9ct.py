from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import shutil
import tempfile
import unittest


from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs import (
    APPROVE_P9CT_DECISION,
    build_phase9ct,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cu_prepare_final_owner_live_order_decision_review_package_after_p9ct import (
    APPROVE_P9CU_DECISION,
    CONTRACT_VERSION as P9CU_CONTRACT,
    P9CV_GATE,
    build_phase9cu,
)
from tests.test_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (
    _load_json,
    _write_json,
)
from tests.test_hv_balanced_dth60_coinglass_phase9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs import (
    Phase9CTFinalOwnerDecisionScopeTests,
)


class Phase9CUFinalOwnerDecisionReviewPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cu-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_prepares_final_owner_decision_review_package_only(self) -> None:
        paths = self._write_ready_p9ct_inputs()

        summary, exit_code = build_phase9cu(
            self._args(paths, output_root=self.temp_dir / "p9cu"),
            now_fn=lambda: datetime(2026, 6, 8, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CU_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9cu_final_owner_live_order_decision_review_package_prepared"])
        self.assertTrue(summary["p9ct_sufficient_for_p9cu_package_preparation"])
        self.assertTrue(summary["decision_review_package_prepared_after_p9ct"])
        self.assertEqual(summary["required_final_decision_evidence_count"], 12)
        self.assertFalse(summary["final_decision_evidence_collected_in_p9cu"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9cu"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cu"])
        self.assertFalse(summary["final_owner_live_order_gate_approval_collected"])
        self.assertFalse(summary["p9cu_satisfies_final_owner_live_order_gate"])
        self.assertTrue(summary["eligible_for_future_p9cv_package_review"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["eligible_for_future_candidate_execution"])
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
        self.assertTrue(summary["final_owner_decision_template_only"])
        self.assertFalse(summary["final_owner_decision_collected_in_p9cu"])
        self.assertEqual(summary["decision_checklist_total_count"], 10)
        self.assertEqual(summary["decision_checklist_satisfied_count"], 2)
        self.assertEqual(summary["decision_checklist_unsatisfied_count"], 8)
        self.assertEqual(summary["allowed_next_gate"], P9CV_GATE)

        package = _load_json(
            Path(summary["output_files"]["final_owner_live_order_decision_review_package"])
        )
        evidence = _load_json(
            Path(summary["output_files"]["required_final_decision_evidence_package"])
        )
        template = _load_json(Path(summary["output_files"]["final_owner_decision_template"]))
        checklist = _load_json(Path(summary["output_files"]["final_decision_checklist"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertTrue(package["package_only"])
        self.assertFalse(package["final_owner_live_order_decision_collected"])
        self.assertFalse(package["live_order_submission_authorized"])
        self.assertFalse(package["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(package["target_plan_replacement_authorized"])
        self.assertEqual(len(evidence["evidence"]), 12)
        self.assertEqual(
            {row["status_in_p9cu"] for row in evidence["evidence"]},
            {"packaged_for_future_decision_not_collected"},
        )
        self.assertEqual(
            {row["collection_status_in_p9cu"] for row in evidence["evidence"]},
            {"not_collected"},
        )
        self.assertTrue(template["template_only"])
        self.assertFalse(template["approval_collected_in_p9cu"])
        self.assertIn("candidate_target_plan_sha256", template["must_explicitly_name"])
        self.assertEqual(len(checklist["approval_items"]), 10)
        self.assertFalse(checklist["p9cu_satisfies_final_owner_live_order_gate"])
        self.assertTrue(
            non_auth["authorizations"][
                "prepare_final_owner_live_order_decision_review_package"
            ]
        )
        self.assertFalse(non_auth["authorizations"]["final_owner_live_order_gate_approval"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["candidate_entered_actual_executor_target_plan_path"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9ct_allowed_next_gate_is_not_p9cu(self) -> None:
        paths = self._write_ready_p9ct_inputs()
        p9ct = _load_json(paths["p9ct_summary"])
        p9ct["allowed_next_gate"] = "P9CV_skip_package_preparation"
        _write_json(paths["p9ct_summary"], p9ct)

        summary, exit_code = build_phase9cu(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 12, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ct_summary_ready_for_p9cu_package", summary["blockers"])
        self.assertFalse(summary["p9cu_final_owner_live_order_decision_review_package_prepared"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_live_order_authority(self) -> None:
        paths = self._write_ready_p9ct_inputs()

        summary, exit_code = build_phase9cu(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 12, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cu_package_only_recorded", summary["blockers"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_if_p9ct_scope_contains_execution_authority(self) -> None:
        paths = self._write_ready_p9ct_inputs()
        p9ct = _load_json(paths["p9ct_summary"])
        scope_path = Path(p9ct["output_files"]["final_owner_live_order_gate_decision_scope"])
        scope = _load_json(scope_path)
        scope["live_order_submission_authorized"] = True
        _write_json(scope_path, scope)

        summary, exit_code = build_phase9cu(
            self._args(paths, output_root=self.temp_dir / "polluted-scope"),
            now_fn=lambda: datetime(2026, 6, 8, 12, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ct_decision_scope_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_if_p9ct_non_authorization_was_mutated(self) -> None:
        paths = self._write_ready_p9ct_inputs()
        p9ct = _load_json(paths["p9ct_summary"])
        non_auth_path = Path(p9ct["output_files"]["non_authorization"])
        non_auth = _load_json(non_auth_path)
        non_auth["authorizations"]["candidate_execution"] = True
        _write_json(non_auth_path, non_auth)

        summary, exit_code = build_phase9cu(
            self._args(paths, output_root=self.temp_dir / "bad-non-auth"),
            now_fn=lambda: datetime(2026, 6, 8, 12, 20, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ct_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["trade_count"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CU_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ct_summary=str(paths["p9ct_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ct_inputs(self) -> dict[str, Path]:
        helper = Phase9CTFinalOwnerDecisionScopeTests(methodName="test_ready_defines_final_owner_decision_scope_only")
        helper.temp_dir = self.temp_dir / "helper"
        helper.temp_dir.mkdir(parents=True, exist_ok=True)
        paths = helper._write_ready_p9cs_inputs()
        p9ct_summary, exit_code = build_phase9ct(
            Namespace(
                output_root=str(self.temp_dir / "p9ct"),
                project_profile=str(paths["project_profile"]),
                phase9cs_summary=str(paths["p9cs_summary"]),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9CT_DECISION,
                owner_decision_source="unit_test",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 11, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(exit_code, 0)
        paths["p9ct_summary"] = Path(p9ct_summary["output_files"]["summary"])
        return paths


if __name__ == "__main__":
    unittest.main()
