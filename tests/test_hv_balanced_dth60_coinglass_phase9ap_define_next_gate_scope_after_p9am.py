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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ap_define_next_gate_scope_after_p9am import (  # noqa: E402
    APPROVE_P9AP_DECISION,
    NEXT_GATE_ID,
    NEXT_GATE_SCOPE,
    build_phase9ap,
    p9ao_ready_for_p9ap,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9APDefineNextGateScopeAfterP9AMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ap-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9ap_ready_defines_next_gate_scope_only(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p9ap-ready"

        summary, exit_code = build_phase9ap(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 9, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ap_next_gate_scope_definition_ready"])
        self.assertTrue(summary["next_gate_scope_defined"])
        self.assertEqual(summary["defined_next_gate"], NEXT_GATE_ID)
        self.assertEqual(summary["defined_next_gate_scope"], NEXT_GATE_SCOPE)
        self.assertFalse(summary["defined_next_gate_authorized_in_p9ap"])
        self.assertFalse(summary["defined_next_gate_execution_authorized"])
        self.assertTrue(summary["defined_next_gate_must_be_separately_requested"])
        self.assertTrue(summary["defined_next_gate_must_be_proof_artifacts_only"])
        self.assertFalse(summary["prepare_proposal_authorized"])
        self.assertFalse(summary["proposal_body_write_authorized"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9ap" / "20260608T090000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "next_gate_scope_definition.json").exists())
        self.assertTrue((proof_root / "scope_acceptance_checklist.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        scope = self._load_json(proof_root / "next_gate_scope_definition.json")
        self.assertEqual(scope["defined_next_gate"], NEXT_GATE_ID)
        self.assertFalse(scope["defined_next_gate_executes_in_p9ap"])
        self.assertFalse(scope["defined_next_gate_authorized_in_p9ap"])
        self.assertTrue(scope["defined_next_gate_required_boundaries"]["proof_artifacts_only"])
        self.assertFalse(scope["defined_next_gate_required_boundaries"]["live_order_submission_authorized"])
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(matrix["authorizations"]["define_next_gate_scope_after_p9am"])
        self.assertFalse(matrix["authorizations"]["execute_defined_next_gate"])
        self.assertFalse(matrix["authorizations"]["prepare_proposal"])
        self.assertFalse(matrix["authorizations"]["proposal_body_write"])
        self.assertFalse(matrix["authorizations"]["dry_load_readback_execution"])
        self.assertFalse(matrix["authorizations"]["live_timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9ap_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9ap(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 8, 9, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ap_define_scope_only", summary["blockers"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9ap_blocks_when_p9ao_authorizes_next_gate_execution(self) -> None:
        paths = self._write_ready_inputs(
            p9ao_overrides={
                "next_gate_execution_authorized": True,
                "gates": {"no_next_gate_execution_in_p9ao": False},
            },
            matrix_overrides={
                "authorizations": {
                    "execute_next_gate": True,
                    "live_timer_path_load": True,
                }
            },
        )
        p9ao = self._load_json(paths["phase9ao"])
        permission = self._load_json(paths["permission"])
        matrix = self._load_json(paths["matrix"])
        self.assertFalse(
            p9ao_ready_for_p9ap(
                p9ao,
                permission,
                matrix,
                current_hook_sha256=file_sha256(paths["hook_module"]),
                current_supervisor_sha256=file_sha256(paths["supervisor"]),
                current_live_config_sha256=tree_sha256(paths["live_config_dir"]),
                current_supervisor_loads_candidate_hook=False,
            )
        )

        summary, exit_code = build_phase9ap(
            self._args(paths, output_root=self.temp_dir / "bad-p9ao"),
            now_fn=lambda: datetime(2026, 6, 8, 9, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ao_scope_permission_gate_ready", summary["blockers"])
        self.assertIn("p9ao_did_not_execute_next_gate", summary["blockers"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9ap_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9ap(
            self._args(paths, output_root=self.temp_dir / "supervisor-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 9, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ao_scope_permission_gate_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AP_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ao_summary=str(paths["phase9ao"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9ao_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        permission_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9ao = self.temp_dir / "p9ao" / "summary.json"
        proof_root = self.temp_dir / "p9ao" / "proof_artifacts" / "p9ao" / "run"
        permission_path = proof_root / "next_gate_scope_permission_gate.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)

        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        constraints = {
            "scope_definition_only": True,
            "proof_artifacts_only": True,
            "must_consume_p9an_proof": True,
            "must_not_execute_next_gate": True,
            "must_not_prepare_proposal": True,
            "must_not_write_proposal_body": True,
            "must_not_execute_dry_load_readback": True,
            "must_not_implement_hook": True,
            "must_not_deploy_hook": True,
            "must_not_load_live_timer_path": True,
            "must_not_invoke_supervisor": True,
            "must_not_replace_target_plan": True,
            "must_not_mutate_executor_input": True,
            "must_not_modify_live_config": True,
            "must_not_modify_operator_state": True,
            "must_not_modify_timer_or_service_state": True,
            "must_not_remote_sync": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        }
        permission = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ao_next_gate_scope_permission_gate.v1",
            "run_id": "unit-test-p9ao",
            "allowed_next_action": "define_next_gate_scope_after_p9am_readback",
            "allowed_next_gate": "P9AP_define_next_gate_scope_after_p9am_only_if_separately_requested",
            "allowed_next_gate_must_be_separately_requested": True,
            "defined_in_p9ao": False,
            "executed_in_p9ao": False,
            "allowed_next_action_constraints": constraints,
        }
        self._deep_update(permission, permission_overrides or {})
        self._write_json(permission_path, permission)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ao_non_authorization_matrix.v1",
            "run_id": "unit-test-p9ao",
            "authorizations": {
                "future_next_gate_scope_definition_after_p9am": True,
                "define_next_gate_scope_in_p9ao": False,
                "execute_next_gate": False,
                "proposal_body_write": False,
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
        gates = {
            "owner_decision_p9ao_allow_define_scope_only": True,
            "project_stage_boundary_preserved": True,
            "p9an_review_ready": True,
            "p9an_sufficient_for_next_owner_gate_discussion": True,
            "p9an_allows_p9ao_only": True,
            "p9an_did_not_define_scope": True,
            "p9an_next_gate_execution_not_authorized": True,
            "p9an_zero_orders_fills": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9an_source": True,
            "current_supervisor_hash_matches_p9an_source": True,
            "current_live_config_hash_matches_p9an_source": True,
            "scope_permission_output_under_proof_artifacts": True,
            "future_scope_definition_must_be_proof_artifacts_only": True,
            "future_scope_definition_must_not_execute_next_gate": True,
            "future_scope_definition_must_not_prepare_proposal": True,
            "future_scope_definition_must_keep_order_authority_disabled": True,
            "future_scope_definition_must_not_authorize_live_order_submission": True,
            "future_scope_definition_must_not_load_live_timer_path": True,
            "future_scope_definition_must_not_mutate_executor_input": True,
            "future_scope_definition_must_not_replace_target_plan": True,
            "future_scope_definition_must_not_remote_sync": True,
            "no_scope_definition_in_p9ao": True,
            "no_next_gate_execution_in_p9ao": True,
            "no_proposal_body_write_in_p9ao": True,
            "no_dry_load_readback_execution_in_p9ao": True,
            "no_timer_hook_implementation_in_p9ao": True,
            "no_hook_deployment_in_p9ao": True,
            "no_live_timer_path_load_in_p9ao": True,
            "no_production_timer_service_load_in_p9ao": True,
            "no_supervisor_run_in_p9ao": True,
            "no_remote_execution_in_p9ao": True,
            "no_candidate_execution_in_p9ao": True,
            "no_executor_input_mutation_in_p9ao": True,
            "no_target_plan_replacement_in_p9ao": True,
            "no_live_mutation_in_p9ao": True,
            "zero_orders_fills_in_p9ao": True,
        }
        no_order = {
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        no_live = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
        }
        p9ao = {
            **no_order,
            **no_live,
            "contract_version": "hv_balanced_dth60_coinglass_phase9ao_allow_define_next_gate_scope_after_p9am.v1",
            "status": "ready",
            "blockers": [],
            "gate_scope": "owner_gated_allow_future_next_gate_scope_definition_after_p9am_readback_only",
            "p9ao_allow_define_next_gate_scope_after_p9am_ready": True,
            "eligible_to_define_next_gate_scope_after_p9am": True,
            "allowed_next_gate": "P9AP_define_next_gate_scope_after_p9am_only_if_separately_requested",
            "allowed_next_gate_must_be_separately_requested": True,
            "future_scope_definition_must_be_proof_artifacts_only": True,
            "future_scope_definition_must_not_execute_next_gate": True,
            "future_scope_definition_must_not_prepare_proposal": True,
            "future_scope_definition_must_keep_order_authority_disabled": True,
            "future_scope_definition_must_not_authorize_live_order_submission": True,
            "p9an_default_off_observe_only_readback_review_ready": True,
            "p9an_sufficient_for_next_owner_gate_discussion": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "owner_decision": {
                "decision": "approve_p9ao_allow_define_next_gate_scope_after_p9am_only",
                "future_next_gate_scope_definition_after_p9am_approved": True,
                "define_next_gate_scope_in_p9ao_approved": False,
                "execute_next_gate_approved": False,
                "proposal_body_write_approved": False,
                "dry_load_readback_execution_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            },
            "gates": gates,
            "output_files": {
                "next_gate_scope_permission_gate": str(permission_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        for key in (
            "defined_next_gate_scope",
            "next_gate_scope_definition_in_p9ao_authorized",
            "next_gate_execution_authorized",
            "eligible_for_timer_hook_implementation",
            "eligible_for_hook_deployment",
            "eligible_for_live_timer_path_load",
            "eligible_for_supervisor_invocation",
            "eligible_for_remote_sync",
            "eligible_for_live_order_submission",
            "eligible_for_stage_governance_change",
            "timer_hook_implementation_authorized",
            "hook_deployment_authorized",
            "timer_path_load_authorized",
            "supervisor_invocation_authorized",
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
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "target_plan_replaced",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
            "executor_input_changed",
        ):
            p9ao[key] = False
        self._deep_update(p9ao, p9ao_overrides or {})
        self._write_json(phase9ao, p9ao)
        return {
            "project_profile": project_profile,
            "phase9ao": phase9ao,
            "permission": permission_path,
            "matrix": matrix_path,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Phase9APDefineNextGateScopeAfterP9AMTests._deep_update(target[key], value)
            else:
                target[key] = value

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
