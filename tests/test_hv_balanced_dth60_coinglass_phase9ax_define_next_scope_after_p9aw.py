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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aw_review_after_p9av import (  # noqa: E402
    APPROVE_P9AW_DECISION,
    P9AX_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ax_define_next_scope_after_p9aw import (  # noqa: E402
    APPROVE_P9AX_DECISION,
    NEXT_GATE_ID,
    NEXT_GATE_SCOPE,
    build_phase9ax,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AXDefineNextScopeAfterP9AWTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ax-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p9ax_ready_defines_next_gate_scope_only(self) -> None:
        paths = self._write_ready_p9aw_bundle()
        output_root = self.temp_dir / "p9ax"

        summary, exit_code = build_phase9ax(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ax_next_gate_scope_definition_ready"])
        self.assertTrue(summary["next_gate_scope_defined"])
        self.assertEqual(summary["defined_next_gate"], NEXT_GATE_ID)
        self.assertEqual(summary["defined_next_gate_scope"], NEXT_GATE_SCOPE)
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE_ID)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertTrue(summary["eligible_for_future_p9ay_owner_gate_request"])
        self.assertFalse(summary["defined_next_gate_authorized_in_p9ax"])
        self.assertFalse(summary["defined_next_gate_execution_authorized"])
        self.assertFalse(summary["prepare_gate_authorized"])
        self.assertFalse(summary["proposal_body_write_authorized"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_shadow_readback_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["candidate_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9ax" / "20260608T150000Z"
        scope = self._load_json(proof_root / "next_gate_scope_definition.json")
        checklist = self._load_json(proof_root / "scope_acceptance_checklist.json")
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        control = self._load_json(proof_root / "control_boundary_readback.json")
        self.assertEqual(scope["defined_next_gate"], NEXT_GATE_ID)
        self.assertEqual(
            scope["scope_defined_for_question"],
            "whether_to_allow_preparing_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate",
        )
        self.assertFalse(scope["defined_next_gate_executes_in_p9ax"])
        self.assertFalse(scope["defined_next_gate_authorized_in_p9ax"])
        self.assertTrue(scope["required_boundaries"]["default_off_required"])
        self.assertTrue(scope["required_boundaries"]["observe_only_required"])
        self.assertTrue(scope["required_boundaries"]["executor_input_must_remain_baseline_only"])
        self.assertFalse(scope["required_boundaries"]["timer_path_shadow_readback_execution_authorized"])
        self.assertFalse(scope["required_boundaries"]["live_order_submission_authorized"])
        self.assertTrue(checklist["checklist"]["defined_gate_only_decides_whether_to_allow_preparing_gate"])
        self.assertTrue(matrix["authorizations"]["define_next_gate_scope"])
        self.assertFalse(matrix["authorizations"]["prepare_shadow_readback_gate"])
        self.assertFalse(matrix["authorizations"]["write_proposal_body"])
        self.assertFalse(matrix["authorizations"]["timer_path_shadow_readback_execution"])
        self.assertFalse(matrix["authorizations"]["live_timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["prepare_gate_authorized"])
        self.assertFalse(control["timer_path_shadow_readback_authorized"])
        self.assertFalse(control["entered_timer_path"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_p9ax_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9aw_bundle()

        summary, exit_code = build_phase9ax(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_timer_path_load",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 15, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ax_define_scope_only", summary["blockers"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["defined_next_gate_execution_authorized"])
        self.assertFalse(summary["prepare_gate_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p9ax_blocks_if_p9aw_no_longer_allows_p9ax(self) -> None:
        paths = self._write_ready_p9aw_bundle(
            p9aw_overrides={
                "allowed_next_gate": "P9BAD_live_order_gate",
                "recommended_next_gate": "P9BAD_live_order_gate",
            }
        )

        summary, exit_code = build_phase9ax(
            self._args(paths, output_root=self.temp_dir / "bad-p9aw-next"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9aw_retained_evidence_review_ready", summary["blockers"])
        self.assertIn("p9aw_allows_p9ax_scope_definition", summary["blockers"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9ax_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9aw_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_phase9ax(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9aw_retained_evidence_review_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AX_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9aw_summary=str(paths["p9aw_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9aw_bundle(
        self,
        *,
        p9aw_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        control_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9aw_root = self.temp_dir / "p9aw"
        proof_root = p9aw_root / "proof_artifacts" / "p9aw" / "run"
        p9aw_summary = p9aw_root / "summary.json"
        owner_record_path = p9aw_root / "owner_decision_record.json"
        review_packet_path = proof_root / "owner_review_packet.json"
        checklist_path = proof_root / "sufficiency_checklist.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        control_path = proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})

        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        owner_record = self._p9aw_owner_record()
        self._write_json(owner_record_path, owner_record)
        review_packet = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aw_owner_review_packet.v1",
            "run_id": "unit-test-p9aw",
            "review_mode": "retained_p9av_evidence_sufficiency_only",
            "reviewed_only_retained_evidence": True,
            "owner_decision": owner_record,
            "p9av_retained_evidence_sufficient": True,
            "sufficient_for_next_gate_scope_discussion": True,
            "allowed_next_gate_if_separately_requested": P9AX_GATE,
            "define_next_gate_scope_in_p9aw_authorized": False,
            "next_gate_execution_authorized": False,
            "entered_timer_path": False,
            "dry_load_readback_executed_in_p9aw": False,
            "supervisor_run": False,
            "remote_sync_performed": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
            "timer_state_mutated": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "verdict": {
                "p9av_ready": True,
                "p9av_local_proof_artifacts_only": True,
                "p9av_executor_baseline_only": True,
                "p9av_candidate_shadow_only": True,
                "p9av_zero_orders_fills": True,
                "sufficient_for_p9ax_scope_discussion_only": True,
            },
        }
        self._write_json(review_packet_path, review_packet)
        gates = self._p9aw_gates()
        checklist = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aw_sufficiency_checklist.v1",
            "run_id": "unit-test-p9aw",
            "checks": gates,
        }
        self._write_json(checklist_path, checklist)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aw_non_authorization_matrix.v1",
            "run_id": "unit-test-p9aw",
            "authorizations": {
                "retained_evidence_review": True,
                "future_next_gate_scope_discussion_request": True,
                "define_next_gate_scope_in_p9aw": False,
                "next_gate_execution": False,
                "dry_load_readback_execution": False,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "live_timer_path_load": False,
                "production_timer_service_load": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "remote_sync": False,
                "remote_execution": False,
                "supervisor_invocation": False,
                "supervisor_run": False,
                "stage_governance_change": False,
            },
        }
        self._deep_update(matrix, matrix_overrides or {})
        self._write_json(matrix_path, matrix)
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aw_control_boundary_readback.v1",
            "run_id": "unit-test-p9aw",
            "scope": "retained_p9av_evidence_review_only",
            "live_supervisor_sha256_before": supervisor_sha,
            "live_supervisor_sha256_after": supervisor_sha,
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_sha256_before": live_config_sha,
            "live_config_dir_sha256_after": live_config_sha,
            "live_config_dir_unchanged": True,
            "define_next_gate_scope_authorized": False,
            "next_gate_execution_authorized": False,
            "dry_load_readback_executed": False,
            "entered_timer_path": False,
            "live_timer_path_loaded": False,
            "ran_supervisor": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._deep_update(control, control_overrides or {})
        self._write_json(control_path, control)
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aw_review_after_p9av.v1",
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9aw",
            "gate_scope": "p9aw_retained_p9av_evidence_review_only",
            "owner_decision": owner_record,
            "source_evidence": {
                "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            },
            "p9aw_retained_evidence_review_ready": True,
            "p9av_retained_evidence_sufficient": True,
            "sufficient_for_next_gate_scope_discussion": True,
            "eligible_for_future_next_gate_scope_definition_request": True,
            "allowed_next_gate": P9AX_GATE,
            "recommended_next_gate": P9AX_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "retained_evidence_review_authorized": True,
            "p9av_sufficiency_review_authorized": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "gates": gates,
            "output_files": {
                "summary": str(p9aw_summary),
                "owner_decision_record": str(owner_record_path),
                "owner_review_packet": str(review_packet_path),
                "sufficiency_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in (
            "define_next_gate_scope_authorized",
            "next_gate_execution_authorized",
            "dry_load_readback_execution_authorized",
            "timer_hook_implementation_authorized",
            "hook_deployment_authorized",
            "timer_path_load_authorized",
            "supervisor_invocation_authorized",
            "supervisor_run_authorized",
            "remote_sync_authorized",
            "remote_execution_authorized",
            "candidate_execution_authorized",
            "candidate_live_order_submission_authorized",
            "live_order_submission_authorized",
            "target_plan_replacement_authorized",
            "executor_input_mutation_authorized",
            "live_config_mutation_authorized",
            "operator_state_mutation_authorized",
            "timer_or_service_mutation_authorized",
            "production_timer_service_load_authorized",
            "repo_stage_change_authorized",
            "entered_timer_path",
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
            "target_plan_replaced",
            "executor_input_changed",
        ):
            summary[key] = False
        self._deep_update(summary, p9aw_overrides or {})
        self._write_json(p9aw_summary, summary)
        return {
            "project_profile": project_profile,
            "p9aw_summary": p9aw_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _p9aw_owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aw_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9AW_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T14:00:00Z",
            "decision_question": "review_p9av_retained_evidence_sufficiency_only",
            "decision_effect": "review_retained_p9av_evidence_without_opening_execution_gate",
            "retained_evidence_review_approved": True,
            "p9av_sufficiency_review_approved": True,
        }
        for key in (
            "define_next_gate_scope_approved",
            "next_gate_execution_approved",
            "dry_load_readback_execution_approved",
            "candidate_execution_approved",
            "candidate_live_order_submission_approved",
            "timer_hook_implementation_approved",
            "hook_deployment_approved",
            "live_timer_path_load_approved",
            "production_timer_service_load_approved",
            "live_order_submission_approved",
            "target_plan_replacement_approved",
            "executor_input_mutation_approved",
            "live_config_mutation_approved",
            "operator_state_mutation_approved",
            "timer_or_service_mutation_approved",
            "remote_sync_approved",
            "remote_execution_approved",
            "supervisor_invocation_approved",
            "supervisor_run_approved",
            "repo_stage_change_approved",
        ):
            record[key] = False
        return record

    @staticmethod
    def _p9aw_gates() -> dict:
        return {
            "owner_decision_p9aw_review_only": True,
            "project_stage_boundary_preserved": True,
            "p9av_retained_evidence_sufficient": True,
            "p9av_allows_p9aw_only": True,
            "p9av_required_separate_request": True,
            "review_packet_under_proof_artifacts": True,
            "sufficiency_checklist_under_proof_artifacts": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9av_source": True,
            "current_supervisor_hash_matches_p9av_source": True,
            "current_live_config_hash_matches_p9av_source": True,
            "p9aw_reviews_only_retained_evidence": True,
            "p9aw_does_not_define_next_gate_scope": True,
            "p9aw_does_not_execute_next_gate": True,
            "p9aw_does_not_execute_dry_load_readback": True,
            "p9aw_does_not_enter_timer_path": True,
            "p9aw_does_not_run_supervisor": True,
            "p9aw_does_not_remote_sync": True,
            "p9aw_does_not_mutate_executor_input": True,
            "p9aw_does_not_replace_target_plan": True,
            "p9aw_does_not_mutate_live_config": True,
            "p9aw_does_not_mutate_operator_state": True,
            "p9aw_does_not_mutate_timer_state": True,
            "zero_orders_fills_in_p9aw": True,
        }

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Phase9AXDefineNextScopeAfterP9AWTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
