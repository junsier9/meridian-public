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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review import (  # noqa: E402
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    CONTRACT_VERSION as P9CJ_CONTRACT,
    P9CK_GATE,
    P9CK_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ck_define_post_account_blocker_live_order_readiness_scope import (  # noqa: E402
    APPROVE_P9CK_DECISION,
    CONTRACT_VERSION as P9CK_CONTRACT,
    P9CL_GATE,
    build_phase9ck,
)


class Phase9CKPostAccountBlockerScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ck-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_defines_post_account_blocker_scope_only(self) -> None:
        paths = self._write_ready_p9cj_inputs()

        summary, exit_code = build_phase9ck(
            self._args(paths, output_root=self.temp_dir / "p9ck"),
            now_fn=lambda: datetime(2026, 6, 11, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CK_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9ck_post_account_blocker_live_order_readiness_scope_defined"])
        self.assertTrue(summary["p9cj_sufficient_for_p9ck_scope_definition"])
        self.assertTrue(summary["account_blocker_cleared_before_p9ck"])
        self.assertTrue(
            summary["live_order_readiness_scope_defined_after_account_blocker_clearance"]
        )
        self.assertFalse(summary["fresh_proofs_satisfied_by_p9ck"])
        self.assertFalse(summary["eligible_for_future_fresh_remote_proof_collection"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["eligible_for_future_candidate_execution"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["risk_ceiling_usdt"], DEFAULT_RISK_CEILING_USDT)
        self.assertEqual(summary["max_notional_usdt"], DEFAULT_MAX_NOTIONAL_USDT)
        self.assertEqual(summary["order_type"], DEFAULT_ORDER_TYPE)
        self.assertEqual(summary["time_in_force"], DEFAULT_TIME_IN_FORCE)
        self.assertEqual(summary["allowed_next_gate"], P9CL_GATE)

        scope = _load_json(
            Path(summary["output_files"]["post_account_blocker_live_order_readiness_scope"])
        )
        proofs = _load_json(Path(summary["output_files"]["required_fresh_proofs"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))

        self.assertEqual(scope["account_blocker_status"], "cleared_by_p9cj_retained_review")
        self.assertIn("fresh remote proof collection", scope["out_of_scope_for_p9ck"])
        proof_ids = [item["proof_id"] for item in proofs["proofs"]]
        self.assertIn("pit_safe_v2v3_account_proof", proof_ids)
        self.assertIn("fresh_order_book_and_exchange_filters", proof_ids)
        self.assertIn("final_owner_live_order_gate_approval", proof_ids)
        self.assertFalse(proofs["p9ck_satisfies_fresh_proofs"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(non_auth["authorizations"]["candidate_execution"])

    def test_blocks_when_p9cj_did_not_clear_account_blocker(self) -> None:
        paths = self._write_ready_p9cj_inputs(account_cleared=False)

        summary, exit_code = build_phase9ck(
            self._args(paths, output_root=self.temp_dir / "p9ck-blocked-account"),
            now_fn=lambda: datetime(2026, 6, 11, 1, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "p9cj_summary_ready_for_post_account_blocker_scope",
            summary["blockers"],
        )
        self.assertIn("p9cj_account_blocker_clearance_ready", summary["blockers"])
        self.assertFalse(summary["account_blocker_cleared_before_p9ck"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9cj_inputs()

        summary, exit_code = build_phase9ck(
            self._args(
                paths,
                output_root=self.temp_dir / "p9ck-wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 11, 1, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9ck_scope_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9ck_post_account_blocker_live_order_readiness_scope_defined"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_blocks_if_p9cj_boundary_is_not_review_only(self) -> None:
        paths = self._write_ready_p9cj_inputs()
        control = _load_json(paths["control"])
        control["remote_execution_performed"] = True
        _write_json(paths["control"], control)

        summary, exit_code = build_phase9ck(
            self._args(paths, output_root=self.temp_dir / "p9ck-bad-control"),
            now_fn=lambda: datetime(2026, 6, 11, 1, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cj_control_boundary_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CK_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cj_summary=str(paths["p9cj_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cj_inputs(self, *, account_cleared: bool = True) -> dict[str, Path]:
        root = self.temp_dir / ("p9cj-ready" if account_cleared else "p9cj-blocked")
        proof_root = root / "proof_artifacts" / "p9cj" / "20260611T000000Z"
        proof_root.mkdir(parents=True)

        project_profile = self.temp_dir / "project_profile.json"
        _write_json(
            project_profile,
            {
                "current_stage": "stage_3_human_approved_execution",
                "target_stage": "stage_4_automated_execution",
            },
        )
        live_blockers = [] if account_cleared else ["account_can_trade_false_or_missing"]
        remaining = [] if account_cleared else ["account_can_trade_false_or_missing"]
        checks = {
            "owner_decision_p9cj_review_only_recorded": True,
            "project_profile_exists": True,
            "current_stage_is_stage3": True,
            "p9ci_summary_exists": True,
            "p9ci_summary_ready_for_account_blocker_review": account_cleared,
            "p9ci_proof_manifest_ready": True,
            "p9ci_pit_safe_account_proof_ready": account_cleared,
            "p9ci_account_delta_acceptance_ready": True,
            "p9ci_history_delta_acceptance_ready": True,
            "p9ci_remote_stdout_collector_sanitized_ready": True,
            "p9ci_remote_runner_identity_ready": True,
            "p9ci_non_authorization_ready": True,
            "p9ci_control_boundary_ready": True,
            "p9ci_command_records_ready": True,
            "retained_p9ci_payload_keys_absent": True,
        }
        p9cj_summary = {
            "contract_version": P9CJ_CONTRACT,
            "run_id": "20260611T000000Z",
            "generated_at_utc": "2026-06-11T00:00:00Z",
            "status": "ready" if account_cleared else "blocked",
            "blockers": [] if account_cleared else ["p9ci_pit_safe_account_proof_ready"],
            "p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_ready": account_cleared,
            "p9ci_sufficient_for_p9cj_review": account_cleared,
            "p9ci_sufficient_to_clear_account_can_trade_blocker": account_cleared,
            "account_can_trade_blocker_cleared_by_p9cj_review": account_cleared,
            "p9ce_false_or_missing_reclassified_as_endpoint_schema_gap": account_cleared,
            "live_order_readiness_blockers_after_account_review": live_blockers,
            "remaining_account_permission_blockers": remaining,
            "eligible_for_future_p9ck_scope_gate": account_cleared,
            "eligible_for_future_live_order_submission": False,
            "eligible_for_future_candidate_execution": False,
            "eligible_for_future_candidate_executor_path_entry": False,
            "fresh_remote_account_read_performed_in_p9cj": False,
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
            "source_p9ci_can_trade_decision_source": "/fapi/v2/account.canTrade",
            "source_p9ci_can_trade_pre": account_cleared,
            "source_p9ci_can_trade_post": account_cleared,
            "source_p9ci_account_v2_has_canTrade_pre": True,
            "source_p9ci_account_v2_has_canTrade_post": True,
            "source_p9ci_account_v3_canTrade_ignored_for_permission_decision": True,
            "source_p9ci_live_order_readiness_blockers": live_blockers,
            "source_p9ci_position_fingerprint_stable": True,
            "source_p9ci_open_order_fingerprint_stable": True,
            "source_p9ci_balance_fingerprint_stable": True,
            "source_p9ci_order_cancel_fill_trade_delta_zero": True,
            "source_p9ci_remote_control_boundary_unchanged": True,
            "source_p9ci_open_position_count_pre": 11,
            "source_p9ci_open_position_count_post": 11,
            "source_p9ci_open_order_count_pre": 0,
            "source_p9ci_open_order_count_post": 0,
            "retained_p9ci_payload_key_count": 0,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "allowed_next_gate": P9CK_GATE,
            "allowed_next_gate_scope": P9CK_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "checks": checks,
        }
        clearance = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cj_account_blocker_clearance_decision.v1",
            "run_id": "20260611T000000Z",
            "status": "ready" if account_cleared else "blocked",
            "prior_blocker": "account_can_trade_false_or_missing",
            "can_trade_decision_source": "/fapi/v2/account.canTrade",
            "source_p9ci_can_trade_pre": account_cleared,
            "source_p9ci_can_trade_post": account_cleared,
            "source_p9ci_account_v2_has_canTrade_pre": True,
            "source_p9ci_account_v2_has_canTrade_post": True,
            "source_p9ci_account_v3_canTrade_ignored_for_permission_decision": True,
            "source_p9ci_live_order_readiness_blockers": live_blockers,
            "source_p9ci_eligible_to_clear_p9cf_account_can_trade_blocker": account_cleared,
            "p9ce_false_or_missing_reclassified_as_endpoint_schema_gap": account_cleared,
            "account_can_trade_blocker_cleared_by_p9cj_review": account_cleared,
            "remaining_account_permission_blockers": remaining,
            "live_order_readiness_blockers_after_account_review": live_blockers,
            "clears_live_order_gate": False,
            "approves_live_order_submission": False,
            "approves_candidate_execution": False,
            "approves_target_plan_replacement": False,
            "approves_executor_input_mutation": False,
        }
        review = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cj_sufficiency_review.v1",
            "status": "ready" if account_cleared else "blocked",
            "blockers": [] if account_cleared else ["account_can_trade_false_or_missing"],
            "p9ci_sufficient_for_p9cj_review": account_cleared,
            "p9ci_sufficient_to_clear_account_can_trade_blocker": account_cleared,
            "account_blocker_clearance_conclusion": (
                "clear_account_can_trade_false_or_missing_as_endpoint_schema_gap"
                if account_cleared
                else "do_not_clear_account_can_trade_false_or_missing"
            ),
            "live_order_gate_conclusion": "not_approved_by_p9cj_review",
            "fresh_remote_account_read_performed_in_p9cj": False,
            "remote_execution_performed_in_p9cj": False,
            "retained_p9ci_payload_key_count": 0,
        }
        non_auth = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cj_non_authorization.v1",
            "authorizations": {
                "review_p9ci_retained_pit_safe_account_proof": True,
                "clear_account_can_trade_blocker_for_future_discussion": account_cleared,
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
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "timer_path_load": False,
                "production_timer_service_load": False,
                "supervisor_invocation": False,
                "stage_governance_change": False,
            },
        }
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9cj_control_boundary.v1",
            "scope": "p9ci_retained_evidence_review_only",
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
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
        }

        paths = {
            "project_profile": project_profile,
            "p9cj_summary": root / "summary.json",
            "clearance": proof_root / "account_blocker_clearance_decision.json",
            "review": proof_root / "p9ci_sufficiency_review.json",
            "non_auth": proof_root / "non_authorization.json",
            "control": proof_root / "control_boundary_readback.json",
        }
        p9cj_summary["output_files"] = {
            "account_blocker_clearance_decision": str(paths["clearance"]),
            "p9ci_sufficiency_review": str(paths["review"]),
            "non_authorization": str(paths["non_auth"]),
            "control_boundary_readback": str(paths["control"]),
            "summary": str(paths["p9cj_summary"]),
        }
        _write_json(paths["clearance"], clearance)
        _write_json(paths["review"], review)
        _write_json(paths["non_auth"], non_auth)
        _write_json(paths["control"], control)
        _write_json(paths["p9cj_summary"], p9cj_summary)
        return paths


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
