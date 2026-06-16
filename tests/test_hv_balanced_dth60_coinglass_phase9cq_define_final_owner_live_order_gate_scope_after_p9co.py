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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CP_CONTRACT,
    P9CQ_GATE,
    P9CQ_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cq_define_final_owner_live_order_gate_scope_after_p9co import (  # noqa: E402
    APPROVE_P9CQ_DECISION,
    CONTRACT_VERSION as P9CQ_CONTRACT,
    P9CR_GATE,
    build_phase9cq,
)


class Phase9CQFinalOwnerLiveOrderGateScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9cq-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_defines_final_owner_scope_only_after_p9co_review(self) -> None:
        paths = self._write_ready_p9cp_inputs()

        summary, exit_code = build_phase9cq(
            self._args(paths, output_root=self.temp_dir / "p9cq"),
            now_fn=lambda: datetime(2026, 6, 8, 8, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["contract_version"], P9CQ_CONTRACT)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p9cq_final_owner_live_order_gate_scope_defined"])
        self.assertTrue(summary["p9cp_sufficient_for_p9cq_scope_definition"])
        self.assertTrue(summary["p9co_retained_read_only_fresh_proofs_ready"])
        self.assertTrue(summary["account_blocker_cleared_by_p9co"])
        self.assertFalse(summary["p9cq_satisfies_final_owner_live_order_gate"])
        self.assertTrue(summary["eligible_for_future_p9cr_review_package"])
        self.assertFalse(summary["eligible_for_future_live_order_submission"])
        self.assertFalse(summary["eligible_for_future_candidate_execution"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["fresh_remote_account_read_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["orders_canceled"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["trade_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P9CR_GATE)
        self.assertEqual(summary["canary_symbol"], "BTCUSDT")
        self.assertEqual(summary["canary_side"], "BUY")
        self.assertEqual(summary["max_notional_usdt"], 10.0)
        self.assertEqual(summary["order_type"], "post_only_limit")
        self.assertEqual(summary["time_in_force"], "GTX")

        scope = _load_json(Path(summary["output_files"]["final_owner_live_order_gate_scope"]))
        evidence = _load_json(Path(summary["output_files"]["required_final_gate_evidence"]))
        non_auth = _load_json(Path(summary["output_files"]["non_authorization"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))

        self.assertEqual(scope["final_owner_gate_name"], "final_owner_live_order_gate_after_p9co")
        self.assertIn(
            "whether to approve candidate entry into the executor target-plan path",
            scope["final_owner_gate_may_discuss"],
        )
        self.assertIn("actual order placement", scope["out_of_scope_for_p9cq"])
        self.assertIn("fresh remote proof collection", scope["out_of_scope_for_p9cq"])
        evidence_ids = {row["evidence_id"] for row in evidence["evidence"]}
        self.assertIn("pit_safe_v2v3_account_proof", evidence_ids)
        self.assertIn("final_owner_live_order_gate_approval", evidence_ids)
        self.assertIn("explicit_final_owner_live_order_decision", evidence_ids)
        self.assertFalse(evidence["p9cq_satisfies_final_owner_live_order_gate"])
        self.assertTrue(non_auth["authorizations"]["define_final_owner_live_order_gate_scope"])
        self.assertTrue(non_auth["authorizations"]["prepare_future_p9cr_review_package"])
        self.assertFalse(non_auth["authorizations"]["live_order_submission"])
        self.assertFalse(non_auth["authorizations"]["candidate_execution"])
        self.assertFalse(control["ssh_invoked"])
        self.assertFalse(control["remote_execution_performed"])
        self.assertFalse(control["live_order_submission_performed"])

    def test_blocks_when_p9cp_allowed_next_gate_is_not_p9cq(self) -> None:
        paths = self._write_ready_p9cp_inputs(
            summary_overrides={"allowed_next_gate": "P9CR_skip_scope"}
        )

        summary, exit_code = build_phase9cq(
            self._args(paths, output_root=self.temp_dir / "wrong-next-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 8, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9cp_summary_ready_for_p9cq_scope_definition", summary["blockers"])
        self.assertFalse(summary["p9cq_final_owner_live_order_gate_scope_defined"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_live_order_authority(self) -> None:
        paths = self._write_ready_p9cp_inputs()

        summary, exit_code = build_phase9cq(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 8, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9cq_scope_only_recorded", summary["blockers"])
        self.assertFalse(summary["p9cq_final_owner_live_order_gate_scope_defined"])
        self.assertFalse(summary["live_order_gate_approved"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["fill_count"], 0)

    def test_blocks_if_p9cp_non_authorization_was_mutated(self) -> None:
        paths = self._write_ready_p9cp_inputs()
        matrix = _load_json(paths["non_auth"])
        matrix["authorizations"]["live_order_submission"] = True
        _write_json(paths["non_auth"], matrix)

        summary, exit_code = build_phase9cq(
            self._args(paths, output_root=self.temp_dir / "bad-non-auth"),
            now_fn=lambda: datetime(2026, 6, 8, 8, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9cp_non_authorization_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["candidate_enter_executor_target_plan_path_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9CQ_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9cp_summary=str(paths["p9cp_summary"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9cp_inputs(
        self,
        *,
        summary_overrides: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        root = self.temp_dir / "p9cp"
        proof_root = root / "proof_artifacts" / "p9cp" / "run"
        paths = {
            "project_profile": project_profile,
            "p9cp_summary": root / "summary.json",
            "sufficiency": proof_root / "p9co_sufficiency_review.json",
            "non_auth": proof_root / "non_authorization.json",
            "control": proof_root / "control_boundary_readback.json",
        }
        _write_json(project_profile, {"current_stage": "stage_3_human_approved_execution"})
        _write_json(paths["sufficiency"], _p9cp_sufficiency())
        _write_json(paths["non_auth"], _p9cp_non_authorization())
        _write_json(paths["control"], _p9cp_control())
        summary = _p9cp_summary(paths)
        summary.update(summary_overrides or {})
        _write_json(paths["p9cp_summary"], summary)
        return paths


def _p9cp_summary(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "contract_version": P9CP_CONTRACT,
        "status": "ready",
        "blockers": [],
        "p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready": True,
        "p9co_retained_evidence_sufficient_for_p9cp_review": True,
        "p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate": True,
        "p9co_sufficient_for_live_order_submission": False,
        "p9co_sufficient_for_candidate_execution": False,
        "account_blocker_cleared_by_p9co": True,
        "read_only_fresh_proofs_ready": True,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_live_order_gate_approval_required_next": True,
        "eligible_for_future_p9cq_scope_definition": True,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "remote_execution_authorized": False,
        "remote_sync_authorized": False,
        "fresh_remote_proof_collection_performed_in_p9cp": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_p9co_can_trade_pre": True,
        "source_p9co_can_trade_post": True,
        "source_p9co_open_position_count_pre": 11,
        "source_p9co_open_position_count_post": 11,
        "source_p9co_open_order_count_pre": 0,
        "source_p9co_open_order_count_post": 0,
        "source_p9co_order_cancel_fill_trade_delta_zero": True,
        "source_p9co_remote_control_boundary_unchanged": True,
        "source_p9co_only_distance_to_high_60_contribution_changed": True,
        "source_p9co_baseline_target_plan_sha256": BASELINE_SHA,
        "source_p9co_candidate_target_plan_sha256": CANDIDATE_SHA,
        "allowed_next_gate": P9CQ_GATE,
        "allowed_next_gate_scope": P9CQ_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "checks": {"all_p9cp_checks": True},
        "output_files": {
            "summary": str(paths["p9cp_summary"]),
            "p9co_sufficiency_review": str(paths["sufficiency"]),
            "non_authorization": str(paths["non_auth"]),
            "control_boundary_readback": str(paths["control"]),
        },
    }


def _p9cp_sufficiency() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_p9co_sufficiency_review.v1",
        "review_only": True,
        "p9co_retained_evidence_sufficient_for_p9cp_review": True,
        "p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate": True,
        "p9co_sufficient_for_live_order_submission": False,
        "p9co_sufficient_for_candidate_execution": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_live_order_gate_approval_required_next": True,
        "eligible_for_future_p9cq_scope_definition": True,
        "future_gate": P9CQ_GATE,
        "future_gate_scope": P9CQ_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "read_only_fresh_proofs_ready": True,
        "account_blocker_cleared_by_p9co": True,
        "live_order_readiness_blockers_after_p9co": [],
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "checks": {"all_p9co_checks": True},
    }


def _p9cp_non_authorization() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_non_authorization.v1",
        "authorizations": {
            "review_p9co_retained_evidence": True,
            "allow_future_p9cq_scope_definition_request": True,
            "define_p9cq_scope_in_p9cp": False,
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
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }


def _p9cp_control() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_control_boundary.v1",
        "scope": "p9co_retained_evidence_review_only",
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


BASELINE_SHA = "f2c49b0f409b41eac06a4b104bfa707da06b4e9be6dc7c3a15ba809ababe3e14"
CANDIDATE_SHA = "c1bc8b82192ce26bfe3b13d493c4d7dd19e5bf10c1f29fbe6d0d64f71f4aa2f0"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
