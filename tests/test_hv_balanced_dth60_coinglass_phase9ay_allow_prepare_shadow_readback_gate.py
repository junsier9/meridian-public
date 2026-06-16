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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ax_define_next_scope_after_p9aw import (  # noqa: E402
    APPROVE_P9AX_DECISION,
    CONTRACT_VERSION as P9AX_CONTRACT,
    NEXT_GATE_ID as P9AY_GATE,
    NEXT_GATE_SCOPE as P9AY_DEFINED_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ay_allow_prepare_shadow_readback_gate import (  # noqa: E402
    APPROVE_P9AY_DECISION,
    P9AZ_GATE,
    P9AZ_SCOPE,
    build_phase9ay,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AYAllowPrepareShadowReadbackGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ay-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p9ay_ready_allows_future_package_preparation_request_only(self) -> None:
        paths = self._write_ready_p9ax_bundle()
        output_root = self.temp_dir / "p9ay"

        summary, exit_code = build_phase9ay(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ay_allow_prepare_shadow_readback_gate_ready"])
        self.assertTrue(summary["eligible_for_future_shadow_readback_gate_package_preparation_request"])
        self.assertTrue(summary["future_shadow_readback_gate_package_preparation_request_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9AZ_GATE)
        self.assertEqual(summary["allowed_next_gate_scope"], P9AZ_SCOPE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["prepare_shadow_readback_gate_in_p9ay_authorized"])
        self.assertFalse(summary["execute_p9az_authorized"])
        self.assertFalse(summary["prepare_gate_package_authorized"])
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

        proof_root = output_root / "proof_artifacts" / "p9ay" / "20260608T160000Z"
        permission = self._load_json(proof_root / "shadow_readback_gate_preparation_permission.json")
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        control = self._load_json(proof_root / "control_boundary_readback.json")
        self.assertEqual(permission["allowed_next_gate"], P9AZ_GATE)
        self.assertTrue(permission["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(permission["opened_in_p9ay"])
        self.assertFalse(permission["prepared_in_p9ay"])
        self.assertTrue(permission["p9az_required_boundaries"]["executor_input_must_remain_baseline_only"])
        self.assertFalse(permission["p9az_required_boundaries"]["timer_path_shadow_readback_execution_authorized"])
        self.assertFalse(permission["p9az_required_boundaries"]["live_order_submission_authorized"])
        self.assertTrue(matrix["authorizations"]["future_shadow_readback_gate_package_preparation_request"])
        self.assertFalse(matrix["authorizations"]["prepare_gate_package"])
        self.assertFalse(matrix["authorizations"]["timer_path_shadow_readback_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertTrue(control["future_shadow_readback_gate_package_preparation_request_authorized"])
        self.assertFalse(control["prepare_gate_package_authorized"])
        self.assertFalse(control["entered_timer_path"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_p9ay_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9ax_bundle()

        summary, exit_code = build_phase9ay(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ay_allow_prepare_shadow_readback_gate_only", summary["blockers"])
        self.assertFalse(summary["future_shadow_readback_gate_package_preparation_request_authorized"])
        self.assertFalse(summary["prepare_gate_package_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p9ay_blocks_if_p9ax_does_not_define_p9ay(self) -> None:
        paths = self._write_ready_p9ax_bundle(
            p9ax_overrides={
                "defined_next_gate": "P9BAD_live_order_gate",
                "allowed_next_gate": "P9BAD_live_order_gate",
                "recommended_next_gate": "P9BAD_live_order_gate",
            }
        )

        summary, exit_code = build_phase9ay(
            self._args(paths, output_root=self.temp_dir / "bad-p9ax"),
            now_fn=lambda: datetime(2026, 6, 8, 16, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ax_scope_definition_ready", summary["blockers"])
        self.assertIn("p9ax_defined_p9ay_only", summary["blockers"])
        self.assertIn("p9ax_allowed_p9ay_only", summary["blockers"])
        self.assertFalse(summary["future_shadow_readback_gate_package_preparation_request_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9ay_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9ax_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_phase9ay(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 16, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ax_scope_definition_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["future_shadow_readback_gate_package_preparation_request_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AY_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ax_summary=str(paths["p9ax_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ax_bundle(
        self,
        *,
        p9ax_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9ax_root = self.temp_dir / "p9ax"
        proof_root = p9ax_root / "proof_artifacts" / "p9ax" / "run"
        p9ax_summary = p9ax_root / "summary.json"
        owner_record_path = p9ax_root / "owner_decision_record.json"
        scope_path = proof_root / "next_gate_scope_definition.json"
        checklist_path = proof_root / "scope_acceptance_checklist.json"
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
        sources = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
            "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        owner_record = self._p9ax_owner_record()
        self._write_json(owner_record_path, owner_record)
        scope = self._p9ax_scope(owner_record, sources)
        self._write_json(scope_path, scope)
        checklist = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ax_scope_acceptance_checklist.v1",
            "run_id": "unit-test-p9ax",
            "defined_next_gate": P9AY_GATE,
            "scope_defined_for_question": scope["scope_defined_for_question"],
            "checklist": {
                "p9ax_defines_scope_only": True,
                "defined_gate_must_be_separately_requested": True,
                "defined_gate_is_owner_gated": True,
                "defined_gate_only_decides_whether_to_allow_preparing_gate": True,
                "defined_gate_cannot_prepare_gate_inside_p9ax": True,
                "defined_gate_cannot_write_proposal_body_inside_p9ax": True,
                "defined_gate_cannot_execute_dry_load_readback": True,
                "defined_gate_cannot_load_timer_path": True,
                "defined_gate_cannot_run_supervisor": True,
                "defined_gate_cannot_remote_sync": True,
                "defined_gate_cannot_mutate_executor_input": True,
                "defined_gate_cannot_replace_target_plan": True,
                "defined_gate_cannot_submit_orders": True,
                "defined_gate_must_keep_executor_baseline_only": True,
                "defined_gate_must_keep_order_authority_disabled": True,
                "future_remote_or_timer_path_requires_fresh_account_read": True,
            },
        }
        self._write_json(checklist_path, checklist)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ax_non_authorization_matrix.v1",
            "run_id": "unit-test-p9ax",
            "authorizations": {
                "define_next_gate_scope": True,
                "allow_prepare_shadow_readback_gate_in_p9ax": False,
                "execute_defined_next_gate": False,
                "prepare_shadow_readback_gate": False,
                "prepare_proposal_package": False,
                "write_proposal_body": False,
                "dry_load_readback_execution": False,
                "timer_path_shadow_readback_execution": False,
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
        self._write_json(matrix_path, matrix)
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ax_control_boundary_readback.v1",
            "run_id": "unit-test-p9ax",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "defined_next_gate": P9AY_GATE,
            "defined_next_gate_authorized_in_p9ax": False,
            "defined_next_gate_execution_authorized": False,
            "prepare_gate_authorized": False,
            "proposal_body_write_authorized": False,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "supervisor_run_authorized": False,
            "remote_sync_authorized": False,
            "remote_execution_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
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
        self._write_json(control_path, control)
        summary = {
            "contract_version": P9AX_CONTRACT,
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9ax",
            "p9ax_next_gate_scope_definition_ready": True,
            "next_gate_scope_defined": True,
            "defined_next_gate": P9AY_GATE,
            "defined_next_gate_scope": P9AY_DEFINED_SCOPE,
            "defined_next_gate_must_be_separately_requested": True,
            "eligible_for_future_p9ay_owner_gate_request": True,
            "allowed_next_gate": P9AY_GATE,
            "recommended_next_gate": P9AY_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "owner_decision": owner_record,
            "source_evidence": sources,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "output_files": {
                "summary": str(p9ax_summary),
                "owner_decision_record": str(owner_record_path),
                "next_gate_scope_definition": str(scope_path),
                "scope_acceptance_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in (
            "defined_next_gate_authorized_in_p9ax",
            "defined_next_gate_execution_authorized",
            "prepare_gate_authorized",
            "proposal_body_write_authorized",
            "dry_load_readback_execution_authorized",
            "timer_path_shadow_readback_authorized",
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
            "live_supervisor_loads_candidate_hook",
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
        self._deep_update(summary, p9ax_overrides or {})
        self._write_json(p9ax_summary, summary)
        return {
            "project_profile": project_profile,
            "p9ax_summary": p9ax_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _p9ax_owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ax_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9AX_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T15:00:00Z",
            "decision_question": "define_next_gate_scope_after_p9aw_only",
            "decision_effect": "define_concrete_next_gate_scope_under_proof_artifacts_only",
            "define_next_gate_scope_approved": True,
            "defined_next_gate": P9AY_GATE,
            "defined_next_gate_question": (
                "whether_to_allow_preparing_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate"
            ),
        }
        for key in (
            "allow_prepare_shadow_readback_gate_approved_in_p9ax",
            "execute_defined_next_gate_approved",
            "prepare_shadow_readback_gate_approved",
            "prepare_proposal_package_approved",
            "proposal_body_write_approved",
            "dry_load_readback_execution_approved",
            "timer_path_shadow_readback_execution_approved",
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
    def _p9ax_scope(owner_record: dict, sources: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ax_next_gate_scope_definition.v1",
            "run_id": "unit-test-p9ax",
            "source_evidence": sources,
            "owner_decision": owner_record,
            "scope_defined_for_question": (
                "whether_to_allow_preparing_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate"
            ),
            "defined_next_gate": P9AY_GATE,
            "defined_next_gate_scope": P9AY_DEFINED_SCOPE,
            "defined_next_gate_must_be_separately_requested": True,
            "defined_next_gate_executes_in_p9ax": False,
            "defined_next_gate_authorized_in_p9ax": False,
            "defined_next_gate_execution_authorized": False,
            "prepare_gate_authorized_in_p9ax": False,
            "proposal_body_write_authorized_in_p9ax": False,
            "dry_load_readback_execution_authorized_in_p9ax": False,
            "timer_path_shadow_readback_execution_authorized_in_p9ax": False,
            "required_boundaries": {
                "owner_gated": True,
                "proof_artifacts_only": True,
                "default_off_required": True,
                "observe_only_required": True,
                "no_order_required": True,
                "executor_input_must_remain_baseline_only": True,
                "candidate_shadow_only": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "live_order_submission_authorized": False,
                "candidate_order_authority": "disabled",
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
                "dry_load_readback_execution_authorized": False,
                "timer_path_shadow_readback_execution_authorized": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "production_timer_service_load_authorized": False,
                "remote_sync_authorized": False,
                "real_timer_path_shadow_readback_requires_separate_gate": True,
                "account_read_proof_required_before_any_remote_or_timer_path": True,
            },
            "disallowed_actions_in_p9ax": {
                "execute_defined_next_gate": True,
                "prepare_shadow_readback_gate": True,
                "prepare_proposal_package": True,
                "write_proposal_body": True,
                "execute_dry_load_readback": True,
                "execute_timer_path_shadow_readback": True,
                "implement_hook": True,
                "deploy_hook": True,
                "load_live_timer_path": True,
                "run_supervisor": True,
                "invoke_timer_or_service": True,
                "mutate_executor_input": True,
                "replace_target_plan": True,
                "mutate_live_config": True,
                "mutate_operator_state": True,
                "mutate_timer_or_service_state": True,
                "remote_sync": True,
                "stage_governance_change": True,
                "submit_orders": True,
            },
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
                Phase9AYAllowPrepareShadowReadbackGateTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
