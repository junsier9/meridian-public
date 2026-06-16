from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9CM_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
    P9CN_GATE,
    P9CN_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate import (  # noqa: E402
    APPROVE_P9CN_DECISION,
    CONTRACT_VERSION as P9CN_CONTRACT,
    P9CO_GATE,
    P9CO_SCOPE,
    build_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate,
)


class Phase9CNOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cn-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ready_allows_future_p9co_request_only(self) -> None:
        paths = self._write_p9cm_fixture()
        summary, exit_code = self._run(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CN_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(
            summary[
                "p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_ready"
            ]
        )
        self.assertTrue(summary["eligible_for_future_p9co_execution_gate_request"])
        self.assertFalse(summary["fresh_remote_proof_collection_execution_approved_in_p9cn"])
        self.assertFalse(summary["fresh_remote_proof_collection_performed_in_p9cn"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CO_GATE)
        self.assertEqual(summary["allowed_next_gate_scope"], P9CO_SCOPE)

        owner_gate = self._read_json(
            Path(summary["output_files"]["read_only_fresh_remote_proof_collection_owner_gate"])
        )
        self.assertTrue(owner_gate["owner_gate_only"])
        self.assertTrue(owner_gate["eligible_for_future_p9co_execution_gate_request"])
        self.assertFalse(owner_gate["fresh_remote_proof_collection_execution_approved_in_p9cn"])
        self.assertEqual(len(owner_gate["required_proofs_to_collect_later"]), len(EXPECTED_PROOFS))

        future_scope = self._read_json(Path(summary["output_files"]["future_p9co_execution_gate_scope"]))
        self.assertEqual(future_scope["future_gate"], P9CO_GATE)
        self.assertIn("live order submission", future_scope["future_gate_may_not_execute"])
        self.assertFalse(future_scope["live_order_submission_authorized"])

    def test_wrong_owner_decision_blocks_without_granting_authority(self) -> None:
        paths = self._write_p9cm_fixture()
        summary, exit_code = self._run(paths, owner_decision="approve_wrong_gate")

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cn_owner_gate_only_recorded", summary["blockers"])
        self.assertFalse(summary["eligible_for_future_p9co_execution_gate_request"])
        self.assertFalse(summary["fresh_remote_proof_collection_execution_approved_in_p9cn"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

        non_auth = self._read_json(Path(summary["output_files"]["non_authorization"]))
        self.assertFalse(non_auth["authorizations"]["allow_future_p9co_execution_gate_request"])
        self.assertFalse(non_auth["authorizations"]["fresh_remote_proof_collection_execution"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])

    def test_polluted_p9cm_summary_or_future_readiness_blocks(self) -> None:
        paths = self._write_p9cm_fixture()
        summary_payload = self._read_json(paths["summary"])
        summary_payload["eligible_for_future_fresh_remote_proof_collection"] = True
        self._write_json(paths["summary"], summary_payload)
        readiness = self._read_json(paths["readiness"])
        readiness["future_gate_may_not_approve"].remove("fresh remote proof collection execution")
        self._write_json(paths["readiness"], readiness)

        summary, exit_code = self._run(paths)

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cm_summary_ready_for_p9cn_owner_gate", summary["blockers"])
        self.assertIn("p9cm_future_p9cn_readiness_ready", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_execution_approved_in_p9cn"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_polluted_p9cm_non_auth_or_control_blocks(self) -> None:
        paths = self._write_p9cm_fixture()
        matrix = self._read_json(paths["non_authorization"])
        matrix["authorizations"]["fresh_remote_proof_collection"] = True
        self._write_json(paths["non_authorization"], matrix)
        control = self._read_json(paths["control"])
        control["remote_execution_performed"] = True
        self._write_json(paths["control"], control)

        summary, exit_code = self._run(paths)

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cm_non_authorization_ready", summary["blockers"])
        self.assertIn("p9cm_control_boundary_ready", summary["blockers"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _run(
        self,
        paths: dict[str, Path],
        *,
        owner_decision: str = APPROVE_P9CN_DECISION,
    ) -> tuple[dict[str, Any], int]:
        args = argparse.Namespace(
            output_root=str(self.temp_dir / "p9cn-output"),
            project_profile=str(paths["project_profile"]),
            phase9cm_summary=str(paths["summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )
        return build_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate(
            args,
            now_fn=lambda: datetime(2026, 6, 8, 1, 30, 0, tzinfo=UTC),
        )

    def _write_p9cm_fixture(self) -> dict[str, Path]:
        evidence_root = self.temp_dir / "p9cm" / "proof_artifacts" / "p9cm" / "run"
        paths = {
            "summary": self.temp_dir / "p9cm" / "summary.json",
            "review": evidence_root / "p9cl_package_sufficiency_review.json",
            "readiness": evidence_root / "future_p9cn_owner_gate_readiness.json",
            "non_authorization": evidence_root / "non_authorization.json",
            "control": evidence_root / "control_boundary_readback.json",
            "project_profile": self.temp_dir / "project_profile.json",
        }
        self._write_json(paths["project_profile"], {"current_stage": "stage_3_human_approved_execution"})
        self._write_json(paths["review"], self._review())
        self._write_json(paths["readiness"], self._readiness())
        self._write_json(paths["non_authorization"], self._non_authorization())
        self._write_json(paths["control"], self._control())
        self._write_json(paths["summary"], self._summary(paths))
        return paths

    def _summary(self, paths: dict[str, Path]) -> dict[str, Any]:
        return {
            "contract_version": P9CM_CONTRACT,
            "status": "ready",
            "blockers": [],
            "checks": {key: True for key in (
                "owner_decision_p9cm_review_only_recorded",
                "project_profile_exists",
                "current_stage_is_stage3",
                "p9cl_summary_exists",
                "p9cl_summary_ready_for_p9cm_review",
                "p9cl_review_package_ready",
                "p9cl_canary_terms_ready",
                "p9cl_fresh_proof_plan_ready",
                "p9cl_approval_checklist_ready",
                "p9cl_non_authorization_ready",
                "p9cl_control_boundary_ready",
            )},
            "p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_ready": True,
            "p9cl_package_sufficient_for_p9cm_review": True,
            "p9cl_package_sufficient_for_future_p9cn_owner_gate": True,
            "p9cl_package_sufficient_for_fresh_remote_proof_collection": False,
            "p9cl_package_sufficient_for_live_order_submission": False,
            "account_blocker_cleared_before_p9cm": True,
            "required_fresh_proof_count": len(EXPECTED_PROOFS),
            "fresh_proofs_collected_in_p9cm": False,
            "fresh_proofs_satisfied_by_p9cm": False,
            "fresh_remote_proof_collection_approved_in_p9cm": False,
            "eligible_for_future_p9cn_owner_gate": True,
            "eligible_for_future_fresh_remote_proof_collection": False,
            "eligible_for_future_live_order_submission": False,
            "eligible_for_future_candidate_execution": False,
            "eligible_for_future_candidate_executor_path_entry": False,
            "fresh_remote_account_read_performed": False,
            "fresh_order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "order_test_endpoint_called": False,
            "remote_execution_performed": False,
            "remote_sync_performed": False,
            "remote_files_written": 0,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "allowed_next_gate": P9CN_GATE,
            "allowed_next_gate_scope": P9CN_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "canary_symbol": CANARY_SYMBOL,
            "canary_side": CANARY_SIDE,
            "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
            "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "source_p9cl_fresh_proofs_collected": False,
            "source_p9cl_fresh_remote_proof_collection_approved": False,
            "output_files": {
                "p9cl_package_sufficiency_review": str(paths["review"]),
                "future_p9cn_owner_gate_readiness": str(paths["readiness"]),
                "non_authorization": str(paths["non_authorization"]),
                "control_boundary_readback": str(paths["control"]),
            },
        }

    def _review(self) -> dict[str, Any]:
        checks = {
            "owner_decision_p9cm_review_only_recorded": True,
            "project_profile_exists": True,
            "current_stage_is_stage3": True,
            "p9cl_summary_exists": True,
            "p9cl_summary_ready_for_p9cm_review": True,
            "p9cl_review_package_ready": True,
            "p9cl_canary_terms_ready": True,
            "p9cl_fresh_proof_plan_ready": True,
            "p9cl_approval_checklist_ready": True,
            "p9cl_non_authorization_ready": True,
            "p9cl_control_boundary_ready": True,
        }
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cm_p9cl_package_sufficiency_review.v1",
            "review_only": True,
            "p9cl_package_sufficient_for_future_p9cn_owner_gate": True,
            "p9cl_package_sufficient_for_fresh_remote_proof_collection": False,
            "p9cl_package_sufficient_for_live_order_submission": False,
            "fresh_proof_collection_plan_present": True,
            "required_fresh_proof_count": len(EXPECTED_PROOFS),
            "fresh_proofs_collected_in_p9cm": False,
            "fresh_remote_proof_collection_approved_in_p9cm": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "checks": checks,
        }

    def _readiness(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cm_future_p9cn_owner_gate_readiness.v1",
            "review_only": True,
            "future_gate": P9CN_GATE,
            "future_gate_scope": P9CN_SCOPE,
            "future_gate_must_be_separately_requested": True,
            "future_gate_may_only_discuss": [
                "whether to allow read-only fresh remote proof collection",
            ],
            "future_gate_may_not_approve": [
                "fresh remote proof collection execution",
                "live order submission",
                "candidate execution",
                "target-plan replacement",
                "executor-input mutation",
                "timer or supervisor invocation",
            ],
            "required_proofs_to_discuss_later": self._proof_rows(),
            "fresh_proofs_collected_in_p9cm": False,
            "fresh_remote_proof_collection_approved_in_p9cm": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
        }

    def _proof_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "proof_id": proof_id,
                "required": True,
                "max_age_seconds": max_age,
                "required_before": "any_order_submission"
                if proof_id == "final_owner_live_order_gate_approval"
                else "future_live_order_gate_approval",
                "acceptance": ["fixture acceptance"],
                "collection_status_in_p9cl": "not_collected",
                "future_collection_requires_separate_owner_gate": True,
            }
            for proof_id, max_age in EXPECTED_PROOFS.items()
        ]

    def _non_authorization(self) -> dict[str, Any]:
        authorizations = {
            "review_p9cl_package_sufficiency": True,
            "allow_future_p9cn_owner_gate_request": True,
        }
        for key in (
            "fresh_remote_proof_collection",
            "fresh_remote_account_read",
            "fresh_order_book_read",
            "exchange_filter_read",
            "order_test_endpoint",
            "remote_execution",
            "remote_sync",
            "live_order_gate_approval",
            "actual_candidate_executor_target_path_entry",
            "candidate_execution",
            "live_order_submission",
            "actual_target_plan_replacement",
            "actual_executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "timer_path_load",
            "production_timer_service_load",
            "supervisor_invocation",
            "stage_governance_change",
        ):
            authorizations[key] = False
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cm_non_authorization.v1",
            "authorizations": authorizations,
        }

    def _control(self) -> dict[str, Any]:
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cm_control_boundary.v1",
            "scope": "p9cl_package_sufficiency_review_only",
        }
        for key in (
            "ssh_invoked",
            "remote_network_connection_performed",
            "fresh_remote_account_read_performed",
            "fresh_order_book_read_performed",
            "exchange_filter_read_performed",
            "order_test_endpoint_called",
            "fresh_proofs_collected",
            "entered_timer_path",
            "ran_supervisor",
            "remote_sync_performed",
            "remote_execution_performed",
            "candidate_execution_performed",
            "candidate_entered_actual_executor_target_plan_path",
            "live_order_submission_performed",
            "target_plan_replaced",
            "executor_input_changed",
            "live_config_changed",
            "operator_state_changed",
            "timer_state_changed",
        ):
            control[key] = False
        control.update({"orders_submitted": 0, "orders_canceled": 0, "fill_count": 0, "trade_count": 0})
        return control

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
