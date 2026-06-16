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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9s_define_next_gate_scope import (  # noqa: E402
    APPROVE_P9S_DECISION,
    NEXT_GATE_ID,
    NEXT_GATE_SCOPE,
    build_phase9s,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9sDefineNextGateScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9s-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9s_ready_defines_next_gate_scope_only(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9s"

        summary, exit_code = build_phase9s(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 2, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9s_next_gate_scope_definition_ready"])
        self.assertTrue(summary["next_gate_scope_defined"])
        self.assertEqual(summary["defined_next_gate"], NEXT_GATE_ID)
        self.assertEqual(summary["defined_next_gate_scope"], NEXT_GATE_SCOPE)
        self.assertFalse(summary["defined_next_gate_authorized_in_p9s"])
        self.assertFalse(summary["defined_next_gate_execution_authorized"])
        self.assertTrue(summary["defined_next_gate_must_be_separately_requested"])
        self.assertTrue(summary["defined_next_gate_must_be_proof_artifacts_only"])
        self.assertFalse(summary["prepare_proposal_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9s" / "20260608T020000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "next_gate_scope_definition.json").exists())
        self.assertTrue((proof_root / "scope_acceptance_checklist.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        scope = self._load_json(proof_root / "next_gate_scope_definition.json")
        self.assertEqual(scope["defined_next_gate"], NEXT_GATE_ID)
        self.assertFalse(scope["defined_next_gate_executes_in_p9s"])
        self.assertFalse(scope["defined_next_gate_authorized_in_p9s"])
        self.assertTrue(scope["defined_next_gate_required_boundaries"]["proof_artifacts_only"])
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(matrix["authorizations"]["define_next_gate_scope"])
        self.assertFalse(matrix["authorizations"]["execute_defined_next_gate"])
        self.assertFalse(matrix["authorizations"]["prepare_proposal"])
        self.assertFalse(matrix["authorizations"]["live_timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9s_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9s(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 8, 2, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9s_define_scope_only", summary["blockers"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9s_blocks_when_p9q_authorizes_timer_path_load(self) -> None:
        paths = self._write_ready_inputs(
            p9q_overrides={
                "timer_path_load_authorized": True,
                "gates": {
                    "no_live_timer_path_load_in_p9q": False,
                },
            },
            matrix_overrides={
                "authorizations": {
                    "live_timer_path_load": True,
                }
            },
        )

        summary, exit_code = build_phase9s(
            self._args(paths, output_root=self.temp_dir / "bad-p9q"),
            now_fn=lambda: datetime(2026, 6, 8, 2, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9q_owner_gate_ready", summary["blockers"])
        self.assertFalse(summary["next_gate_scope_defined"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9s_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9s(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 2, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9q_owner_gate_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9S_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9q_summary=str(paths["phase9q"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9q_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        scope_gate_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9q = self.temp_dir / "phase9q" / "summary.json"
        scope_gate_path = self.temp_dir / "phase9q" / "proof_artifacts" / "p9q" / "run" / (
            "next_gate_scope_definition_gate.json"
        )
        matrix_path = self.temp_dir / "phase9q" / "proof_artifacts" / "p9q" / "run" / (
            "non_authorization_matrix.json"
        )
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        scope_gate = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9q_next_gate_scope_definition_gate.v1",
            "run_id": "unit-test-p9q",
            "allowed_next_action": "define_next_gate_concrete_scope",
            "allowed_next_gate": "P9S_define_next_gate_scope_only_if_separately_requested",
            "defined_in_p9q": False,
            "executed_in_p9q": False,
            "allowed_next_action_constraints": {
                "scope_definition_only": True,
                "proof_artifacts_only": True,
                "must_not_execute_next_gate": True,
                "must_not_implement_hook": True,
                "must_not_deploy_hook": True,
                "must_not_load_live_timer_path": True,
                "must_not_replace_target_plan": True,
                "must_not_mutate_executor_input": True,
                "must_not_modify_live_config": True,
                "must_not_modify_operator_state": True,
                "must_not_modify_timer_or_service_state": True,
                "must_not_remote_sync": True,
                "must_not_run_supervisor": True,
                "candidate_order_authority": "disabled",
                "candidate_live_order_submission_authorized": False,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
        }
        self._deep_update(scope_gate, scope_gate_overrides or {})
        self._write_json(scope_gate_path, scope_gate)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9q_non_authorization_matrix.v1",
            "run_id": "unit-test-p9q",
            "authorizations": {
                "future_next_gate_scope_definition": True,
                "define_next_gate_scope_in_p9q": False,
                "execute_next_gate": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "live_timer_path_load": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "remote_sync": False,
                "supervisor_run": False,
                "stage_governance_change": False,
            },
        }
        self._deep_update(matrix, matrix_overrides or {})
        self._write_json(matrix_path, matrix)
        gates = {
            "owner_decision_p9q_define_scope_only": True,
            "project_stage_boundary_preserved": True,
            "p9p_owner_review_ready": True,
            "p9p_sufficient_for_next_owner_gate_discussion": True,
            "p9p_next_gate_execution_not_authorized": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9p_source": True,
            "current_supervisor_hash_matches_p9p_source": True,
            "scope_definition_gate_output_under_proof_artifacts": True,
            "future_scope_definition_must_be_proof_artifacts_only": True,
            "future_scope_definition_must_not_execute_next_gate": True,
            "future_scope_definition_must_keep_order_authority_disabled": True,
            "future_scope_definition_must_not_authorize_live_order_submission": True,
            "no_scope_definition_in_p9q": True,
            "no_next_gate_execution_in_p9q": True,
            "no_timer_hook_implementation_in_p9q": True,
            "no_hook_deployment_in_p9q": True,
            "no_live_timer_path_load_in_p9q": True,
            "no_supervisor_run_in_p9q": True,
            "no_remote_execution_in_p9q": True,
            "no_executor_input_mutation_in_p9q": True,
            "no_target_plan_replacement_in_p9q": True,
            "no_live_mutation_in_p9q": True,
            "zero_orders_fills_in_p9q": True,
        }
        p9q = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate.v1",
            "status": "ready",
            "blockers": [],
            "gate_scope": "owner_gated_allow_future_next_gate_scope_definition_only",
            "p9q_define_next_gate_scope_owner_gate_ready": True,
            "eligible_to_define_next_gate_scope": True,
            "defined_next_gate_scope": False,
            "next_gate_scope_definition_in_p9q_authorized": False,
            "next_gate_execution_authorized": False,
            "allowed_next_gate": "P9S_define_next_gate_scope_only_if_separately_requested",
            "future_scope_definition_must_be_proof_artifacts_only": True,
            "future_scope_definition_must_not_execute_next_gate": True,
            "future_scope_definition_must_keep_order_authority_disabled": True,
            "future_scope_definition_must_not_authorize_live_order_submission": True,
            "eligible_for_live_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "eligible_for_stage_governance_change": False,
            "timer_hook_implementation_authorized": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "wrote_live_hook_config": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "owner_decision": {
                "decision": "approve_p9q_allow_define_next_gate_scope_only",
                "future_next_gate_scope_definition_approved": True,
                "define_next_gate_scope_in_p9q_approved": False,
                "execute_next_gate_approved": False,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "live_timer_path_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "live_config_mutation_approved": False,
                "operator_state_mutation_approved": False,
                "timer_or_service_mutation_approved": False,
                "remote_sync_approved": False,
                "supervisor_run_approved": False,
                "repo_stage_change_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "gates": gates,
            "output_files": {
                "next_gate_scope_definition_gate": str(scope_gate_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        self._deep_update(p9q, p9q_overrides or {})
        self._write_json(phase9q, p9q)
        return {
            "project_profile": project_profile,
            "phase9q": phase9q,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                HvBalancedDth60CoinglassPhase9sDefineNextGateScopeTests._deep_update(target[key], value)
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
