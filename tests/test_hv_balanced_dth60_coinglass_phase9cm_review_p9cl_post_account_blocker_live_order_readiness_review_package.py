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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9CL_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
    P9CM_GATE,
    P9CM_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    APPROVE_P9CM_DECISION,
    CONTRACT_VERSION as P9CM_CONTRACT,
    P9CN_GATE,
    P9CN_SCOPE,
    build_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package,
)


class Phase9CMReviewP9CLPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cm-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ready_reviews_p9cl_package_only(self) -> None:
        paths = self._write_p9cl_fixture()
        summary, exit_code = self._run(paths)

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CM_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(
            summary[
                "p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_ready"
            ]
        )
        self.assertTrue(summary["p9cl_package_sufficient_for_future_p9cn_owner_gate"])
        self.assertFalse(summary["p9cl_package_sufficient_for_fresh_remote_proof_collection"])
        self.assertFalse(summary["p9cl_package_sufficient_for_live_order_submission"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9cm"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cm"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CN_GATE)
        self.assertEqual(summary["allowed_next_gate_scope"], P9CN_SCOPE)

        review = self._read_json(Path(summary["output_files"]["p9cl_package_sufficiency_review"]))
        self.assertTrue(review["review_only"])
        self.assertTrue(review["p9cl_package_sufficient_for_future_p9cn_owner_gate"])
        self.assertFalse(review["p9cl_package_sufficient_for_fresh_remote_proof_collection"])
        self.assertFalse(review["live_order_submission_authorized"])

        future = self._read_json(Path(summary["output_files"]["future_p9cn_owner_gate_readiness"]))
        self.assertEqual(future["future_gate"], P9CN_GATE)
        self.assertTrue(future["future_gate_must_be_separately_requested"])
        self.assertEqual(len(future["required_proofs_to_discuss_later"]), len(EXPECTED_PROOFS))
        self.assertFalse(future["fresh_remote_proof_collection_approved_in_p9cm"])

    def test_wrong_owner_decision_blocks_without_granting_authority(self) -> None:
        paths = self._write_p9cl_fixture()
        summary, exit_code = self._run(paths, owner_decision="approve_wrong_gate")

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cm_review_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9cl_package_sufficient_for_future_p9cn_owner_gate"])
        self.assertFalse(summary["eligible_for_future_p9cn_owner_gate"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cm"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_polluted_p9cl_summary_or_plan_blocks_review(self) -> None:
        paths = self._write_p9cl_fixture()
        summary_payload = self._read_json(paths["summary"])
        summary_payload["eligible_for_future_fresh_remote_proof_collection"] = True
        self._write_json(paths["summary"], summary_payload)
        plan = self._read_json(paths["fresh_plan"])
        plan["proofs"][0]["collection_status_in_p9cl"] = "collected"
        self._write_json(paths["fresh_plan"], plan)
        package = self._read_json(paths["package"])
        package["fresh_proof_collection_plan"] = plan
        self._write_json(paths["package"], package)

        summary, exit_code = self._run(paths)

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cl_summary_ready_for_p9cm_review", summary["blockers"])
        self.assertIn("p9cl_review_package_ready", summary["blockers"])
        self.assertIn("p9cl_fresh_proof_plan_ready", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cm"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_polluted_p9cl_non_auth_or_control_blocks_review(self) -> None:
        paths = self._write_p9cl_fixture()
        non_auth = self._read_json(paths["non_authorization"])
        non_auth["authorizations"]["fresh_remote_proof_collection"] = True
        self._write_json(paths["non_authorization"], non_auth)
        control = self._read_json(paths["control"])
        control["remote_execution_performed"] = True
        self._write_json(paths["control"], control)

        summary, exit_code = self._run(paths)

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cl_non_authorization_ready", summary["blockers"])
        self.assertIn("p9cl_control_boundary_ready", summary["blockers"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _run(
        self,
        paths: dict[str, Path],
        *,
        owner_decision: str = APPROVE_P9CM_DECISION,
    ) -> tuple[dict[str, Any], int]:
        args = argparse.Namespace(
            output_root=str(self.temp_dir / "p9cm-output"),
            project_profile=str(paths["project_profile"]),
            phase9cl_summary=str(paths["summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )
        return build_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package(
            args,
            now_fn=lambda: datetime(2026, 6, 7, 19, 20, 0, tzinfo=UTC),
        )

    def _write_p9cl_fixture(self) -> dict[str, Path]:
        evidence_root = self.temp_dir / "p9cl" / "proof_artifacts" / "p9cl" / "run"
        paths = {
            "summary": self.temp_dir / "p9cl" / "summary.json",
            "package": evidence_root / "post_account_blocker_live_order_readiness_review_package.json",
            "canary": evidence_root / "canary_order_terms.json",
            "fresh_plan": evidence_root / "fresh_proof_collection_plan.json",
            "approval": evidence_root / "approval_checklist.json",
            "non_authorization": evidence_root / "non_authorization.json",
            "control": evidence_root / "control_boundary_readback.json",
            "project_profile": self.temp_dir / "project_profile.json",
        }
        canary = self._canary_terms()
        fresh_plan = self._fresh_plan()
        approval = self._approval_checklist()
        self._write_json(paths["project_profile"], {"current_stage": "stage_3_human_approved_execution"})
        self._write_json(paths["canary"], canary)
        self._write_json(paths["fresh_plan"], fresh_plan)
        self._write_json(paths["approval"], approval)
        self._write_json(paths["package"], self._review_package(canary, fresh_plan, approval))
        self._write_json(paths["non_authorization"], self._non_authorization())
        self._write_json(paths["control"], self._control())
        self._write_json(paths["summary"], self._summary(paths))
        return paths

    def _summary(self, paths: dict[str, Path]) -> dict[str, Any]:
        return {
            "contract_version": P9CL_CONTRACT,
            "status": "ready",
            "blockers": [],
            "checks": {key: True for key in (
                "owner_decision_p9cl_package_only_recorded",
                "project_profile_exists",
                "current_stage_is_stage3",
                "p9ck_summary_exists",
                "p9ck_summary_ready_for_p9cl_package",
                "p9ck_scope_ready",
                "p9ck_required_fresh_proofs_ready",
                "p9ck_non_authorization_ready",
                "p9ck_control_boundary_ready",
            )},
            "p9cl_post_account_blocker_live_order_readiness_review_package_prepared": True,
            "p9ck_sufficient_for_p9cl_review_package": True,
            "account_blocker_cleared_before_p9cl": True,
            "review_package_prepared_after_account_blocker_clearance": True,
            "required_fresh_proof_count": len(EXPECTED_PROOFS),
            "fresh_proofs_collected_in_p9cl": False,
            "fresh_proofs_satisfied_by_p9cl": False,
            "fresh_remote_proof_collection_approved_in_p9cl": False,
            "eligible_for_future_p9cm_package_review": True,
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
            "allowed_next_gate": P9CM_GATE,
            "allowed_next_gate_scope": P9CM_SCOPE,
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
            "source_p9ck_account_blocker_cleared": True,
            "source_p9ck_fresh_proofs_satisfied": False,
            "source_p9ck_eligible_for_future_fresh_remote_proof_collection": False,
            "output_files": {
                "post_account_blocker_live_order_readiness_review_package": str(paths["package"]),
                "canary_order_terms": str(paths["canary"]),
                "fresh_proof_collection_plan": str(paths["fresh_plan"]),
                "approval_checklist": str(paths["approval"]),
                "non_authorization": str(paths["non_authorization"]),
                "control_boundary_readback": str(paths["control"]),
            },
        }

    def _review_package(
        self,
        canary: dict[str, Any],
        fresh_plan: dict[str, Any],
        approval: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cl_review_package.v1",
            "package_only": True,
            "package_decision": "prepared_for_future_review_only",
            "account_blocker_status": "cleared_by_p9cj_retained_review",
            "future_gate_name": "post_account_blocker_live_order_readiness_review",
            "canary_order_terms": canary,
            "fresh_proof_collection_plan": fresh_plan,
            "approval_checklist": approval,
            "future_gate_may_discuss": [
                "whether to request fresh read-only remote proof collection in a later separate gate",
            ],
            "future_gate_may_not_skip": [
                "new PIT-safe v2/v3 account proof after P9CJ",
                "separate final owner live-order gate",
            ],
            "required_fresh_proof_count": len(EXPECTED_PROOFS),
            "fresh_proofs_collected_in_p9cl": False,
            "fresh_proofs_satisfied_by_p9cl": False,
            "fresh_remote_proof_collection_approved_in_p9cl": False,
            "live_order_gate_approved": False,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "source_p9ck_account_blocker_cleared": True,
        }

    def _canary_terms(self) -> dict[str, Any]:
        return {
            "symbol": CANARY_SYMBOL,
            "side": CANARY_SIDE,
            "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
            "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "post_only_required": True,
            "maker_only_required": True,
            "candidate_delta_source": "distance_to_high_60_contribution_only",
            "would_submit_order": False,
        }

    def _fresh_plan(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cl_fresh_proof_collection_plan.v1",
            "package_only": True,
            "fresh_proofs_collected_in_p9cl": False,
            "remote_account_read_performed": False,
            "order_book_read_performed": False,
            "exchange_filter_read_performed": False,
            "future_collection_requires_separate_owner_gate": True,
            "proofs": [
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
            ],
        }

    def _approval_checklist(self) -> dict[str, Any]:
        items = [
            ("account_blocker_cleared_by_p9cj", True),
            ("all_required_fresh_proofs_present_and_unexpired", False),
            ("fresh_v2_account_canTrade_true", False),
            ("same_risk_candidate_target_plan_hash_bound", False),
            ("distance_to_high_60_only_delta", False),
            ("no_order_replacement_dry_run_passed", False),
            ("post_only_limit_price_does_not_cross_spread", False),
            ("kill_switch_and_rollback_readback_available", False),
            ("final_owner_live_order_gate_approval", False),
        ]
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cl_approval_checklist.v1",
            "package_only": True,
            "approval_items": [
                {
                    "item": item,
                    "required_for_live_order_gate": True,
                    "satisfied_in_p9cl": satisfied,
                }
                for item, satisfied in items
            ],
            "rollback_conditions": [f"rollback condition {index}" for index in range(8)],
        }

    def _non_authorization(self) -> dict[str, Any]:
        authorizations = {
            "prepare_post_account_blocker_live_order_readiness_review_package": True,
            "review_p9cl_package": True,
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
            "contract_version": "hv_balanced_dth60_coinglass_phase9cl_non_authorization.v1",
            "authorizations": authorizations,
        }

    def _control(self) -> dict[str, Any]:
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cl_control_boundary.v1",
            "scope": "post_account_blocker_live_order_readiness_review_package_preparation_only",
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
