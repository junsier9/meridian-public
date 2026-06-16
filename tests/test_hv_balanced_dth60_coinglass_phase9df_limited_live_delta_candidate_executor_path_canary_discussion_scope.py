from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9de_review_p9dd_limited_live_delta_executor_path_discussion import (
    P9DF_GATE,
    P9DF_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9df_define_limited_live_delta_candidate_executor_path_canary_discussion_scope import (
    APPROVE_P9DF_DECISION,
    P9DG_GATE,
    build_phase9df,
)


class Phase9DFLimitedLiveDeltaDiscussionScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9df-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_scope_definition_authorizes_only_future_proposal_package(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9df(
            self._args(paths, output_root=self.temp_dir / "p9df"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(
            summary[
                "p9df_limited_live_delta_candidate_executor_path_canary_discussion_scope_ready"
            ]
        )
        self.assertTrue(summary["scope_definition_only"])
        self.assertTrue(summary["eligible_for_future_p9dg_proposal_package_gate"])
        self.assertEqual(summary["allowed_next_gate"], P9DG_GATE)
        self.assertEqual(summary["max_cycles_discussion_scope"], 1)
        self.assertEqual(summary["default_order_state"], "disabled_until_separate_execution_gate")
        self.assertFalse(summary["continuous_automated_order_flow_allowed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        scope = _load_json(Path(summary["output_files"]["discussion_scope"]))
        self.assertTrue(scope["scope_only"])
        self.assertIn("live order submission", scope["not_authorized_by_this_scope"])
        self.assertEqual(scope["hard_limits_for_discussion"]["max_cycles"], 1)
        self.assertEqual(
            scope["hard_limits_for_discussion"]["default_order_state"],
            "disabled_until_separate_execution_gate",
        )
        self.assertFalse(scope["hard_limits_for_discussion"]["continuous_automated_order_flow"])

        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["live_order_submission_performed"])
        self.assertFalse(control["candidate_execution_performed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_blocks_if_p9de_claims_candidate_execution_authorization(self) -> None:
        paths = self._write_ready_inputs()
        p9de = _load_json(paths["p9de_summary"])
        p9de["candidate_executor_path_execution_authorized"] = True
        _write_json(paths["p9de_summary"], p9de)

        summary, exit_code = build_phase9df(
            self._args(paths, output_root=self.temp_dir / "bad-p9df"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9de_summary_ready_for_p9df", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9de_summary=str(paths["p9de_summary"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9DF_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self) -> dict[str, Path]:
        root = self.temp_dir / "p9de"
        proof = root / "proof_artifacts" / "p9de" / "run"
        project_profile = self.temp_dir / "project_profile.json"
        p9de_summary = root / "summary.json"
        review = proof / "p9dd_limited_executor_path_discussion_review.json"
        non_auth = proof / "non_authorization.json"
        control = proof / "control_boundary_readback.json"

        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            review,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9de_p9dd_limited_executor_path_discussion_review.v1",
                "review_only": True,
                "p9dd_retained_evidence_sufficient_for_review": True,
                "p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion": True,
                "p9dd_sufficient_for_live_order_submission_without_new_gate": False,
                "p9dd_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
                "p9dd_sufficient_for_continuous_automated_order_flow": False,
                "required_next_discussion_constraints": {
                    "scope_type": "discussion_and_scope_definition_only",
                    "max_cycles_to_discuss": 1,
                    "candidate_path_mode": "single_cycle_canary_only",
                    "continuous_automated_order_flow": "not_allowed",
                    "default_order_state": "disabled_until_separate_execution_gate",
                    "must_define_kill_switch": True,
                    "must_define_max_notional": True,
                    "must_define_candidate_plan_hash_binding": True,
                    "must_define_baseline_fallback": True,
                    "must_define_post_run_position_reconciliation": True,
                },
            },
        )
        _write_json(
            non_auth,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9de_non_authorization.v1",
                "authorizations": {
                    "review_p9dd_retained_evidence": True,
                    "allow_future_limited_live_delta_candidate_executor_path_discussion_scope_gate": True,
                    "live_order_submission_in_p9de": False,
                    "candidate_executor_path_execution_in_p9de": False,
                    "candidate_target_plan_replacement_in_p9de": False,
                    "executor_input_mutation_in_p9de": False,
                    "timer_path_load_in_p9de": False,
                    "supervisor_invocation_in_p9de": False,
                    "remote_execution_in_p9de": False,
                    "remote_sync_in_p9de": False,
                    "remote_file_write_in_p9de": False,
                    "continuous_automated_order_flow": False,
                    "stage_governance_change": False,
                },
            },
        )
        _write_json(
            control,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9de_control_boundary.v1",
                "scope": "retained_evidence_review_only",
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
            p9de_summary,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9de_review_p9dd_limited_live_delta_executor_path_discussion.v1",
                "status": "ready",
                "blockers": [],
                "p9de_review_p9dd_limited_live_delta_executor_path_discussion_ready": True,
                "p9dd_retained_evidence_sufficient_for_p9de_review": True,
                "p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion": True,
                "p9dd_sufficient_for_live_order_submission_without_new_gate": False,
                "p9dd_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
                "p9dd_sufficient_for_continuous_automated_order_flow": False,
                "allowed_scope_after_p9de": "discussion_and_scope_definition_only",
                "eligible_for_future_p9df_scope_definition_gate": True,
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
                "p9dd_orders_submitted": 2,
                "p9dd_fill_count": 2,
                "p9dd_trade_count": 2,
                "p9dd_remote_control_boundary_unchanged": True,
                "allowed_next_gate": P9DF_GATE,
                "allowed_next_gate_scope": P9DF_SCOPE,
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "p9dd_limited_executor_path_discussion_review": str(review),
                    "non_authorization": str(non_auth),
                    "control_boundary_readback": str(control),
                },
            },
        )
        return {"project_profile": project_profile, "p9de_summary": p9de_summary}


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
