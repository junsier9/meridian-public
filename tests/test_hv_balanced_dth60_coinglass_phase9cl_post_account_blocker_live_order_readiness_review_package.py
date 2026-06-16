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
    APPROVE_P9CL_DECISION,
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
    P9CL_GATE,
    P9CL_SCOPE,
    P9CM_GATE,
    P9CM_SCOPE,
    build_phase9cl_post_account_blocker_live_order_readiness_review_package,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ck_define_post_account_blocker_live_order_readiness_scope import (  # noqa: E402
    CONTRACT_VERSION as P9CK_CONTRACT,
)


class Phase9CLPostAccountBlockerReviewPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cl-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ready_prepares_review_package_only(self) -> None:
        paths = self._write_p9ck_fixture()

        summary, exit_code = build_phase9cl_post_account_blocker_live_order_readiness_review_package(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 7, 19, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CL_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(
            summary["p9cl_post_account_blocker_live_order_readiness_review_package_prepared"]
        )
        self.assertTrue(summary["p9ck_sufficient_for_p9cl_review_package"])
        self.assertTrue(summary["account_blocker_cleared_before_p9cl"])
        self.assertFalse(summary["fresh_proofs_collected_in_p9cl"])
        self.assertFalse(summary["fresh_proofs_satisfied_by_p9cl"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cl"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CM_GATE)
        self.assertEqual(summary["allowed_next_gate_scope"], P9CM_SCOPE)

        package = self._read_json(
            Path(summary["output_files"]["post_account_blocker_live_order_readiness_review_package"])
        )
        self.assertTrue(package["package_only"])
        self.assertEqual(package["package_decision"], "prepared_for_future_review_only")
        self.assertFalse(package["live_order_submission_authorized"])
        self.assertFalse(package["target_plan_replacement_authorized"])
        self.assertEqual(package["orders_submitted"], 0)

        canary = self._read_json(Path(summary["output_files"]["canary_order_terms"]))
        self.assertEqual(canary["symbol"], CANARY_SYMBOL)
        self.assertEqual(canary["side"], CANARY_SIDE)
        self.assertFalse(canary["would_submit_order"])
        self.assertFalse(canary["market_orders_allowed"])

        fresh_plan = self._read_json(Path(summary["output_files"]["fresh_proof_collection_plan"]))
        self.assertFalse(fresh_plan["fresh_proofs_collected_in_p9cl"])
        self.assertEqual(len(fresh_plan["proofs"]), len(EXPECTED_PROOFS))
        self.assertTrue(
            all(row["collection_status_in_p9cl"] == "not_collected" for row in fresh_plan["proofs"])
        )
        self.assertTrue(
            all(row["future_collection_requires_separate_owner_gate"] for row in fresh_plan["proofs"])
        )

        checklist = self._read_json(Path(summary["output_files"]["approval_checklist"]))
        by_item = {row["item"]: row for row in checklist["approval_items"]}
        self.assertTrue(by_item["account_blocker_cleared_by_p9cj"]["satisfied_in_p9cl"])
        self.assertFalse(
            by_item["all_required_fresh_proofs_present_and_unexpired"]["satisfied_in_p9cl"]
        )
        self.assertFalse(by_item["final_owner_live_order_gate_approval"]["satisfied_in_p9cl"])

        control = self._read_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["fresh_remote_account_read_performed"])
        self.assertFalse(control["entered_timer_path"])
        self.assertFalse(control["candidate_execution_performed"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_granting_remote_or_order_authority(self) -> None:
        paths = self._write_p9ck_fixture()

        summary, exit_code = build_phase9cl_post_account_blocker_live_order_readiness_review_package(
            self._args(paths, owner_decision="approve_wrong_gate"),
            now_fn=lambda: datetime(2026, 6, 7, 19, 11, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9cl_package_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9cl_post_account_blocker_live_order_readiness_review_package_prepared"])
        self.assertFalse(summary["eligible_for_future_p9cm_package_review"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

        non_auth = self._read_json(Path(summary["output_files"]["non_authorization"]))
        self.assertFalse(
            non_auth["authorizations"]["prepare_post_account_blocker_live_order_readiness_review_package"]
        )
        self.assertFalse(non_auth["authorizations"]["fresh_remote_proof_collection"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])

    def test_missing_p9ck_scope_executor_boundary_blocks_package(self) -> None:
        paths = self._write_p9ck_fixture()
        scope = self._read_json(paths["scope"])
        scope["out_of_scope_for_p9ck"].remove("executor-input mutation")
        self._write_json(paths["scope"], scope)

        summary, exit_code = build_phase9cl_post_account_blocker_live_order_readiness_review_package(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 7, 19, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ck_scope_ready", summary["blockers"])
        self.assertFalse(summary["eligible_for_future_p9cm_package_review"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_polluted_p9ck_non_auth_or_control_blocks_package(self) -> None:
        paths = self._write_p9ck_fixture()
        matrix = self._read_json(paths["non_authorization"])
        matrix["authorizations"]["fresh_remote_proof_collection"] = True
        self._write_json(paths["non_authorization"], matrix)
        control = self._read_json(paths["control"])
        control["remote_execution_performed"] = True
        self._write_json(paths["control"], control)

        summary, exit_code = build_phase9cl_post_account_blocker_live_order_readiness_review_package(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 7, 19, 13, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ck_non_authorization_ready", summary["blockers"])
        self.assertIn("p9ck_control_boundary_ready", summary["blockers"])
        self.assertFalse(summary["fresh_remote_proof_collection_approved_in_p9cl"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        owner_decision: str = APPROVE_P9CL_DECISION,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            output_root=str(self.temp_dir / "p9cl-output"),
            project_profile=str(paths["project_profile"]),
            phase9ck_summary=str(paths["summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_p9ck_fixture(self) -> dict[str, Path]:
        evidence_root = self.temp_dir / "p9ck" / "proof_artifacts" / "p9ck" / "20260607T184044Z"
        evidence_root.mkdir(parents=True)
        paths = {
            "summary": self.temp_dir / "p9ck" / "summary.json",
            "scope": evidence_root / "post_account_blocker_live_order_readiness_scope.json",
            "proofs": evidence_root / "required_fresh_proofs.json",
            "non_authorization": evidence_root / "non_authorization.json",
            "control": evidence_root / "control_boundary_readback.json",
            "project_profile": self.temp_dir / "project_profile.json",
        }
        self._write_json(paths["project_profile"], {"current_stage": "stage_3_human_approved_execution"})
        self._write_json(paths["scope"], self._p9ck_scope())
        self._write_json(paths["proofs"], self._p9ck_required_proofs())
        self._write_json(paths["non_authorization"], self._p9ck_non_authorization())
        self._write_json(paths["control"], self._p9ck_control())
        self._write_json(paths["summary"], self._p9ck_summary(paths))
        return paths

    def _p9ck_summary(self, paths: dict[str, Path]) -> dict[str, Any]:
        checks = {
            "owner_decision_p9ck_scope_only_recorded": True,
            "project_profile_exists": True,
            "current_stage_is_stage3": True,
            "p9cj_summary_exists": True,
            "p9cj_summary_ready_for_post_account_blocker_scope": True,
            "p9cj_account_blocker_clearance_ready": True,
            "p9cj_sufficiency_review_ready": True,
            "p9cj_non_authorization_ready": True,
            "p9cj_control_boundary_ready": True,
        }
        return {
            "contract_version": P9CK_CONTRACT,
            "status": "ready",
            "blockers": [],
            "checks": checks,
            "p9ck_post_account_blocker_live_order_readiness_scope_defined": True,
            "p9cj_sufficient_for_p9ck_scope_definition": True,
            "account_blocker_cleared_before_p9ck": True,
            "live_order_readiness_scope_defined_after_account_blocker_clearance": True,
            "required_fresh_proof_count": len(EXPECTED_PROOFS),
            "fresh_proofs_required_before_any_future_order_submission": True,
            "fresh_proofs_satisfied_by_p9ck": False,
            "eligible_for_future_p9cl_review_package": True,
            "eligible_for_future_fresh_remote_proof_collection": False,
            "eligible_for_future_live_order_submission": False,
            "eligible_for_future_candidate_execution": False,
            "eligible_for_future_candidate_executor_path_entry": False,
            "fresh_remote_proof_collection_performed_in_p9ck": False,
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
            "allowed_next_gate": P9CL_GATE,
            "allowed_next_gate_scope": P9CL_SCOPE,
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
            "source_p9cj_account_blocker_cleared": True,
            "source_p9cj_live_order_readiness_blockers_after_account_review": [],
            "source_p9cj_remaining_account_permission_blockers": [],
            "source_p9cj_can_trade_decision_source": "/fapi/v2/account.canTrade",
            "source_p9cj_can_trade_pre": True,
            "source_p9cj_can_trade_post": True,
            "source_p9cj_order_cancel_fill_trade_delta_zero": True,
            "source_p9cj_remote_control_boundary_unchanged": True,
            "output_files": {
                "post_account_blocker_live_order_readiness_scope": str(paths["scope"]),
                "required_fresh_proofs": str(paths["proofs"]),
                "non_authorization": str(paths["non_authorization"]),
                "control_boundary_readback": str(paths["control"]),
            },
        }

    def _p9ck_scope(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ck_post_account_blocker_live_order_readiness_scope.v1",
            "scope_definition_only": True,
            "account_blocker_status": "cleared_by_p9cj_retained_review",
            "future_gate_name": "post_account_blocker_live_order_readiness_review",
            "future_gate_may_discuss": [
                "whether a post-account-blocker review package is complete",
                "whether to request fresh read-only remote proof collection in a later separate gate",
            ],
            "future_gate_may_not_skip": [
                "new PIT-safe v2/v3 account proof after P9CJ",
                "same-risk paired target-plan binding",
                "separate final owner live-order gate",
            ],
            "canary_terms": {
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
            },
            "target_runner": {
                "remote_host": "root@203.0.113.10",
                "expected_egress_ip": "203.0.113.10",
                "remote_repo": "/root/meridian_alpha_live_runner/repo",
                "remote_config": "/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml",
            },
            "out_of_scope_for_p9ck": [
                "fresh remote proof collection",
                "actual order placement",
                "candidate execution",
                "actual target-plan replacement",
                "executor-input mutation",
                "timer or service mutation",
                "supervisor invocation",
                "remote execution",
            ],
            "rollback_conditions": [
                "any required fresh proof is missing, stale, or hash-mismatched",
                "future v2 account canTrade is false or missing",
                "v3 account canTrade is used for permission decisions",
                "candidate target-plan hash differs from the no-order approved hash",
                "executor input is not explicitly baseline-only before final gate",
                "candidate delta affects anything outside distance_to_high_60 contribution",
                "open-order, fill, trade, balance, or position delta is unexplained",
                "order book no longer supports maker-only post-only execution",
            ],
        }

    def _p9ck_required_proofs(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ck_required_fresh_proofs.v1",
            "scope_definition_only": True,
            "fresh_proofs_required_before_any_future_order_submission": True,
            "p9ck_satisfies_fresh_proofs": False,
            "fresh_remote_proof_collection_performed_in_p9ck": False,
            "proofs": [
                {
                    "proof_id": proof_id,
                    "max_age_seconds": max_age,
                    "required_before": (
                        "any_order_submission"
                        if proof_id == "final_owner_live_order_gate_approval"
                        else "future_live_order_gate_approval"
                    ),
                    "acceptance": ["fixture acceptance"],
                }
                for proof_id, max_age in EXPECTED_PROOFS.items()
            ],
        }

    def _p9ck_non_authorization(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ck_non_authorization.v1",
            "run_id": "20260607T184044Z",
            "authorizations": {
                "define_post_account_blocker_live_order_readiness_scope": True,
                "prepare_future_p9cl_review_package": True,
                "fresh_remote_proof_collection": False,
                "fresh_remote_account_read": False,
                "fresh_order_book_read": False,
                "exchange_filter_read": False,
                "order_test_endpoint": False,
                "remote_execution": False,
                "remote_sync": False,
                "live_order_gate_approval": False,
                "actual_candidate_executor_target_path_entry": False,
                "candidate_execution": False,
                "live_order_submission": False,
                "actual_target_plan_replacement": False,
                "actual_executor_input_mutation": False,
                "timer_path_load": False,
                "production_timer_service_load": False,
                "supervisor_invocation": False,
                "stage_governance_change": False,
            },
        }

    def _p9ck_control(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ck_control_boundary.v1",
            "run_id": "20260607T184044Z",
            "scope": "post_account_blocker_live_order_readiness_scope_definition_only",
            "ssh_invoked": False,
            "remote_network_connection_performed": False,
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

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
