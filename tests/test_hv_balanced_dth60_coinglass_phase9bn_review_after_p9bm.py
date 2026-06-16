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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bm_real_timer_path_shadow_readback import (  # noqa: E402
    APPROVE_P9BM_DECISION,
    CONTRACT_VERSION as P9BM_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bn_review_after_p9bm import (  # noqa: E402
    APPROVE_P9BN_DECISION,
    P9BO_GATE,
    build_p9bn,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BNReviewAfterP9BMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bn-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_p9bm_retained_evidence_allows_next_proposal_review_gate_only(self) -> None:
        paths = self._write_ready_p9bm_bundle()

        summary, exit_code = build_p9bn(
            self._args(paths, output_root=self.temp_dir / "p9bn"),
            now_fn=lambda: datetime(2026, 6, 10, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bn_owner_gate_ready"])
        self.assertTrue(summary["p9bm_retained_evidence_sufficient"])
        self.assertTrue(summary["sufficient_for_next_proposal_review_gate"])
        self.assertEqual(summary["allowed_next_gate"], P9BO_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertTrue(summary["eligible_for_future_p9bo_proposal_review_gate_request"])
        self.assertFalse(summary["proposal_preparation_authorized"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertFalse(summary["timer_path_shadow_readback_execution_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        review_packet = _load_json(Path(summary["output_files"]["owner_review_packet"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization_matrix"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertTrue(review_packet["sufficient_for_next_proposal_review_gate"])
        self.assertFalse(matrix["authorizations"]["prepare_proposal"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["live_supervisor_loads_candidate_hook"])
        self.assertIn("proof_artifacts", Path(summary["output_files"]["owner_review_packet"]).parts)

    def test_wrong_p9bn_owner_decision_blocks_without_authorizing_next_gate(self) -> None:
        paths = self._write_ready_p9bm_bundle()

        summary, exit_code = build_p9bn(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_prepare_live_order_gate",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 1, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bn_review_only", summary["blockers"])
        self.assertEqual(summary["allowed_next_gate"], "")
        self.assertFalse(summary["p9bn_owner_gate_ready"])
        self.assertFalse(summary["proposal_preparation_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_candidate_plan_referenced_by_executor_blocks_sufficiency(self) -> None:
        paths = self._write_ready_p9bm_bundle(
            p9bm_overrides={"candidate_plan_referenced_by_executor": True},
            hook_overrides={"candidate_plan_referenced_by_executor": True},
        )

        summary, exit_code = build_p9bn(
            self._args(paths, output_root=self.temp_dir / "bad-candidate-reference"),
            now_fn=lambda: datetime(2026, 6, 10, 1, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bm_retained_evidence_sufficient", summary["blockers"])
        self.assertIn("p9bm_executor_baseline_only", summary["blockers"])
        self.assertFalse(summary["sufficient_for_next_proposal_review_gate"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_current_supervisor_loading_hook_blocks_review(self) -> None:
        paths = self._write_ready_p9bm_bundle(
            supervisor_text="from enhengclaw.live_trading import dth60_observe_only_shadow_hook\n"
        )

        summary, exit_code = build_p9bn(
            self._args(paths, output_root=self.temp_dir / "supervisor-loads-hook"),
            now_fn=lambda: datetime(2026, 6, 10, 1, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bm_retained_evidence_sufficient", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BN_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bm_summary=str(paths["p9bm_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bm_bundle(
        self,
        *,
        p9bm_overrides: dict[str, object] | None = None,
        hook_overrides: dict[str, object] | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        run_id = "20260610T010000Z"
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9bm_root = self.temp_dir / "p9bm"
        proof_root = p9bm_root / "proof_artifacts" / "p9bm" / run_id
        summary_path = p9bm_root / "summary.json"
        owner_path = p9bm_root / "owner_decision_record.json"
        generated_config_path = proof_root / "generated_no_order_timer_path_config.json"
        supervisor_summary_path = proof_root / "supervisor_readback_summary.json"
        hook_summary_path = proof_root / "hook_shadow_readback_summary.json"
        position_path = proof_root / "position_reference" / "run_summary.json"
        retained_fixture_path = proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
        control_path = proof_root / "control_boundary_readback.json"
        matrix_path = proof_root / "non_authorization_matrix.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        _write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})

        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        owner = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bm_owner_decision.v1",
            "decision": APPROVE_P9BM_DECISION,
            "real_timer_path_shadow_readback_execution_approved": True,
            "supervisor_entrypoint_invocation_approved": True,
            "observe_only_hook_invocation_approved": True,
            "generated_no_order_config_approved": True,
            "candidate_execution_approved": False,
            "candidate_live_order_submission_approved": False,
            "live_order_submission_approved": False,
            "target_plan_replacement_approved": False,
            "executor_input_mutation_approved": False,
            "live_config_mutation_approved": False,
            "operator_state_mutation_approved": False,
            "timer_or_service_mutation_approved": False,
            "production_timer_service_load_approved": False,
            "remote_sync_approved": False,
            "repo_stage_change_approved": False,
        }
        generated_config = {"risk": {"trading_enabled": False}, "state": {"artifact_root": str(proof_root)}}
        supervisor_summary = self._supervisor_summary()
        hook_summary = self._hook_summary(hook_overrides=hook_overrides)
        position = self._position_reference()
        retained_fixture = self._retained_fixture(proof_root)
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bm_control_boundary_readback.v1",
            "run_id": run_id,
            "scope": "real_supervisor_entrypoint_shadow_readback_no_order_only",
            "live_supervisor_sha256_before": supervisor_sha,
            "live_supervisor_sha256_after": supervisor_sha,
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_sha256_before": live_config_sha,
            "live_config_dir_sha256_after": live_config_sha,
            "live_config_dir_unchanged": True,
            "generated_config": {"exists": True, "path": str(generated_config_path), "sha256": ""},
            "generated_config_under_proof_artifacts": True,
            "supervisor_entrypoint_invoked": True,
            "systemd_timer_service_invoked": False,
            "production_timer_service_loaded_or_modified": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "candidate_execution_performed": False,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed_outside_generated_p9bm_state": False,
            "timer_state_changed": False,
        }
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bm_non_authorization_matrix.v1",
            "run_id": run_id,
            "authorizations": {
                "real_timer_path_shadow_readback_execution": True,
                "supervisor_entrypoint_invocation": True,
                "observe_only_hook_invocation": True,
                "generated_no_order_config": True,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "live_order_submission": False,
                "operator_state_mutation": False,
                "production_timer_service_load": False,
                "remote_sync": False,
                "stage_governance_change": False,
                "target_plan_replacement": False,
                "timer_or_service_mutation": False,
            },
        }

        _write_json(owner_path, owner)
        _write_json(generated_config_path, generated_config)
        _write_json(supervisor_summary_path, supervisor_summary)
        _write_json(hook_summary_path, hook_summary)
        _write_json(position_path, position)
        _write_json(retained_fixture_path, retained_fixture)
        control["generated_config"]["sha256"] = file_sha256(generated_config_path)
        _write_json(control_path, control)
        _write_json(matrix_path, matrix)
        source_evidence = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
            "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        gates = {
            "owner_decision_p9bm_execute_real_timer_path_shadow_readback_no_order_only": True,
            "project_stage_boundary_preserved": True,
            "p9bl_owner_gate_ready_for_p9bm": True,
            "retained_account_fixture_sources_complete": True,
            "retained_account_proof_read_only_ready": True,
            "pit_safe_position_reference_fixture_ready": True,
            "retained_p9aa_summary_ready": True,
            "retained_account_plan_fixture_ready": True,
            "generated_no_order_config_written": True,
            "generated_config_under_proof_artifacts": True,
            "real_supervisor_entrypoint_invoked": True,
            "supervisor_exit_zero": True,
            "supervisor_completed": True,
            "supervisor_no_blockers": True,
            "supervisor_cycle_observed_no_order": True,
            "supervisor_execute_live_delta_requested_false": True,
            "supervisor_live_delta_authorized_false": True,
            "supervisor_orders_fills_zero": True,
            "core_loop_execution_requested_false": True,
            "core_loop_orders_fills_zero": True,
            "core_cycle_plan_artifact_root_present": True,
            "hook_invoked_with_supervisor_cycle_context": True,
            "hook_ready_observe_only_shadow": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "executor_consumes_baseline_only": True,
            "executor_input_plan_hash_equals_baseline": True,
            "candidate_plan_not_referenced_by_executor": not bool(
                hook_summary.get("candidate_plan_referenced_by_executor")
            ),
            "candidate_shadow_hash_differs_from_executor": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_not_mutated": True,
            "zero_order_action_delta": True,
            "zero_cancel_action_delta": True,
            "zero_fill_action_delta": True,
            "zero_trade_action_delta": True,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "no_production_timer_service_load_or_mutation": True,
            "no_remote_sync": True,
            "retained_account_fixture_if_requested_ready": True,
        }
        summary = {
            "contract_version": P9BM_CONTRACT,
            "status": "ready",
            "run_id": run_id,
            "generated_at_utc": "2026-06-10T01:00:00Z",
            "gate_scope": "p9bm_real_timer_path_shadow_readback_no_order_only",
            "owner_decision": owner,
            "source_evidence": source_evidence,
            "p9bm_real_timer_path_shadow_readback_ready": True,
            "real_timer_path_shadow_readback_executed": True,
            "timer_path_shadow_readback_mode": (
                "real_supervisor_entrypoint_with_retained_pit_safe_account_position_reference_fixture"
            ),
            "account_proof_mode": "retained_pit_safe_read_only_fixture",
            "retained_account_fixture_requested": True,
            "retained_account_proof_ready": True,
            "pit_safe_position_reference_fixture_ready": True,
            "position_reference_fixture_summary": position,
            "retained_account_plan_fixture_summary": retained_fixture,
            "supervisor_entrypoint_invoked": True,
            "systemd_timer_service_invoked": False,
            "production_timer_service_loaded_or_modified": False,
            "supervisor_exit_code": 0,
            "supervisor_summary": supervisor_summary,
            "hook_summary": hook_summary,
            "supervisor_or_core_loop_blockers": [],
            "account_read_blockers": [],
            "plan_artifact_missing": False,
            "completed_shadow_cycles": 1,
            "fresh_proof": True,
            "same_risk_no_order_config": True,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_execution_authorized": False,
            "candidate_execution_performed": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "live_order_submission_authorized": False,
            "candidate_shadow_only": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "zero_order_cancel_fill_trade_delta": True,
            "live_config_changed": False,
            "operator_state_changed_outside_generated_p9bm_state": False,
            "timer_state_changed": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "gates": gates,
            "blockers": [],
            "output_files": {
                "summary": str(summary_path),
                "owner_decision_record": str(owner_path),
                "generated_no_order_config": str(generated_config_path),
                "supervisor_readback_summary": str(supervisor_summary_path),
                "hook_shadow_readback_summary": str(hook_summary_path),
                "position_reference_fixture": str(position_path),
                "retained_account_plan_fixture": str(retained_fixture_path),
                "control_boundary_readback": str(control_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        if p9bm_overrides:
            summary.update(p9bm_overrides)
        _write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
            "p9bm_summary": summary_path,
        }

    @staticmethod
    def _supervisor_summary() -> dict[str, object]:
        core = {
            "status": "mainnet_core_loop_completed",
            "blockers": [],
            "execution_requested": False,
            "live_delta_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        return {
            "status": "mainnet_live_supervisor_completed",
            "blockers": [],
            "supervisor_uses_core_loop": True,
            "completed_cycle_count": 1,
            "live_delta_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "cycles": [
                {
                    "status": "cycle_observed_no_order",
                    "execute_live_delta_requested": False,
                    "live_delta_authorized": False,
                    "orders_submitted": 0,
                    "fill_count": 0,
                    "fills_observed": 0,
                    "exchange_order_submission": "disabled",
                    "core_loop_summary": core,
                }
            ],
        }

    @staticmethod
    def _hook_summary(*, hook_overrides: dict[str, object] | None = None) -> dict[str, object]:
        hook = {
            "contract_version": "hv_balanced_dth60_observe_only_shadow_hook.v1",
            "status": "ready",
            "blockers": [],
            "hook_enabled": True,
            "mode": "observe_only",
            "artifact_sink": "proof_artifacts_only",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "mainnet_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_artifacts_written_count": 4,
            "executor_consumes_baseline_only": True,
            "executor_input_plan_hash_equals_baseline": True,
            "executor_input_plan_hash_unchanged": True,
            "candidate_plan_referenced_by_executor": False,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "candidate_shadow_plan_sha256": "candidate-shadow",
            "executor_input_plan_sha256_after_hook": "baseline-plan",
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        if hook_overrides:
            hook.update(hook_overrides)
        return hook

    @staticmethod
    def _position_reference() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aa_nonflat_position_reference_fixture.v1",
            "status": "position_genesis_snapshot",
            "read_only": True,
            "proof_artifacts_only": True,
            "source_created_before_p9aa": True,
            "source_open_order_count": 0,
            "source_open_position_count": 1,
            "expected_position_count": 1,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "side_effects": {
                "only_http_get_endpoints": True,
                "order_test_calls": 0,
                "orders_canceled": 0,
                "orders_submitted": 0,
            },
        }

    @staticmethod
    def _retained_fixture(proof_root: Path) -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bm_retained_account_plan_fixture.v1",
            "status": "ready",
            "account_proof_mode": "retained_pit_safe_read_only_fixture",
            "read_only": True,
            "proof_artifacts_only": True,
            "position_reference_fixture_status": "position_genesis_snapshot",
            "position_reference_source_created_before_p9bm": True,
            "source_account_proof_finished_before_p9bm": True,
            "open_order_count": 0,
            "open_position_count": 1,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "side_effects": {
                "only_http_get_endpoints": True,
                "order_test_calls": 0,
                "orders_canceled": 0,
                "orders_submitted": 0,
            },
            "output_files": {"target_portfolio": str(proof_root / "acct_fx" / "plan" / "target_portfolio.json")},
            "core_loop_summary": {
                "status": "mainnet_core_loop_completed",
                "blockers": [],
                "execution_requested": False,
                "live_delta_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "fills_observed": 0,
                "exchange_order_submission": "disabled",
            },
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


if __name__ == "__main__":
    unittest.main()
