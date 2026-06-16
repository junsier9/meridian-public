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
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10k_define_limited_live_delta_candidate_executor_path_discussion_scope import (  # noqa: E402
    APPROVE_P10K_DECISION,
    P10L_GATE,
    build_p10k,
)


class HvBalanced12FactorP10kScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10k-scope-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_defines_scope_only_and_allows_only_p10l_package_gate(self) -> None:
        paths = self._write_ready_p10j_bundle()

        summary, exit_code = build_p10k(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10k-ready"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p10k_limited_live_delta_candidate_executor_path_discussion_scope_ready"])
        self.assertTrue(summary["p10j_sufficient_for_p10k_scope_definition"])
        self.assertTrue(summary["scope_definition_only"])
        self.assertEqual(summary["max_cycles_discussion_scope"], 1)
        self.assertEqual(summary["max_symbols_discussion_scope"], 1)
        self.assertEqual(summary["default_order_state"], "disabled_until_separate_execution_gate")
        self.assertFalse(summary["continuous_automated_order_flow_allowed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P10L_GATE)

        scope = _load_json(Path(summary["output_files"]["discussion_scope"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertTrue(scope["scope_only"])
        self.assertEqual(scope["hard_limits_for_discussion"]["max_cycles"], 1)
        self.assertEqual(scope["hard_limits_for_discussion"]["max_symbols"], 1)
        self.assertFalse(scope["hard_limits_for_discussion"]["continuous_automated_order_flow"])
        self.assertIn("live order submission", scope["not_authorized_by_this_scope"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission_in_p10k"])
        self.assertFalse(non_auth["authorizations"]["candidate_executor_path_execution_in_p10k"])
        self.assertFalse(non_auth["authorizations"]["continuous_automated_order_flow"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_network_connection_performed"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_bad_p10j_summary_blocks_scope_definition(self) -> None:
        paths = self._write_ready_p10j_bundle()
        p10j = _load_json(paths["p10j_summary"])
        p10j["status"] = "blocked"
        p10j["blockers"] = ["unit_test_blocker"]
        _write_json(paths["p10j_summary"], p10j)

        summary, exit_code = build_p10k(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10k-bad-p10j"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10j_summary_ready_for_p10k", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_authorizing_execution(self) -> None:
        paths = self._write_ready_p10j_bundle()

        summary, exit_code = build_p10k(
            self._args(
                paths,
                output_root=self.temp_dir / "proof_artifacts" / "p10k-wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 22, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p10k_scope_definition_recorded", summary["blockers"])
        self.assertFalse(summary["candidate_executor_path_execution_authorized"])
        self.assertFalse(summary["continuous_automated_order_flow_allowed"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P10K_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            p10j_summary=str(paths["p10j_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p10j_bundle(self) -> dict[str, Path]:
        root = self.temp_dir / "p10j"
        proof = root / "proof"
        project_profile = self.temp_dir / "project_profile.json"
        p10j_summary = root / "summary.json"
        review = proof / "p10i_retained_evidence_review.json"
        non_auth = proof / "non_authorization.json"
        control = proof / "control_boundary_readback.json"
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(
            review,
            {
                "contract_version": "hv_balanced_12factor_p10j_p10i_retained_evidence_review.v1",
                "review_only": True,
                "p10i_retained_evidence_sufficient_for_p10j_review": True,
                "p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion": True,
                "p10i_sufficient_for_live_order_submission_without_new_gate": False,
                "p10i_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
                "p10i_sufficient_for_continuous_automated_order_flow": False,
                "required_next_discussion_constraints": {
                    "scope_type": "discussion_and_scope_definition_only",
                    "max_cycles_to_discuss": 1,
                    "candidate_path_mode": "limited_single_cycle_canary_discussion_only",
                    "continuous_automated_order_flow": "not_allowed",
                    "default_order_state": "disabled_until_separate_execution_gate",
                    "must_define_candidate_plan_hash_binding": True,
                    "must_define_exact_executor_target_plan_replacement_semantics": True,
                    "must_define_baseline_fallback": True,
                    "must_define_kill_switch": True,
                    "must_define_max_notional_and_symbol_universe": True,
                    "must_define_post_run_reconciliation": True,
                },
            },
        )
        _write_json(
            non_auth,
            {
                "contract_version": "hv_balanced_12factor_p10j_non_authorization.v1",
                "authorizations": {
                    "review_p10i_retained_evidence": True,
                    "allow_future_limited_live_delta_candidate_executor_path_discussion_scope_gate": True,
                    "live_order_submission_in_p10j": False,
                    "candidate_executor_path_execution_in_p10j": False,
                    "candidate_target_plan_replacement_in_p10j": False,
                    "executor_input_mutation_in_p10j": False,
                    "timer_path_load_in_p10j": False,
                    "supervisor_invocation_in_p10j": False,
                    "remote_execution_in_p10j": False,
                    "remote_sync_in_p10j": False,
                    "remote_file_write_in_p10j": False,
                    "continuous_automated_order_flow": False,
                    "stage_governance_change": False,
                },
            },
        )
        _write_json(
            control,
            {
                "contract_version": "hv_balanced_12factor_p10j_control_boundary.v1",
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
            p10j_summary,
            {
                "contract_version": "hv_balanced_12factor_p10j_review_p10i_single_cycle_live_delta_canary.v1",
                "status": "ready",
                "blockers": [],
                "p10j_review_p10i_single_cycle_live_delta_canary_ready": True,
                "p10i_retained_evidence_sufficient_for_p10j_review": True,
                "p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion": True,
                "p10i_sufficient_for_live_order_submission_without_new_gate": False,
                "p10i_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
                "p10i_sufficient_for_continuous_automated_order_flow": False,
                "allowed_scope_after_p10j": "discussion_and_scope_definition_only",
                "eligible_for_future_p10k_scope_definition_gate": True,
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
                "p10i_orders_submitted": 1,
                "p10i_orders_canceled": 1,
                "p10i_fill_count": 0,
                "p10i_trade_count": 0,
                "p10i_remote_control_boundary_unchanged": True,
                "allowed_next_gate": "P10K_define_limited_live_delta_candidate_executor_path_discussion_scope_only_if_separately_requested",
                "allowed_next_gate_scope": "define_scope_only_for_limited_live_delta_candidate_executor_path_discussion_after_p10i_no_execution_no_continuous_automation",
                "allowed_next_gate_must_be_separately_requested": True,
                "output_files": {
                    "p10i_retained_evidence_review": str(review),
                    "non_authorization": str(non_auth),
                    "control_boundary_readback": str(control),
                },
            },
        )
        return {"project_profile": project_profile, "p10j_summary": p10j_summary}


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
